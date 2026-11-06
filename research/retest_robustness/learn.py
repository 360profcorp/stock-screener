"""Separate test L of Retest M on the QuantRocket learning bundle (PLAN.md §11). Research only.

    python -m research.retest_robustness.learn symbols --pit PIT_CSV --out FILE      # symbols to export
    python -m research.retest_robustness.learn run --export PKL --pit PIT_CSV [--diag JSON]

The bundle export never leaves the runner: only aggregates are written (licensed data, public repo).
Universe keyed by QuantRocket Sid: each PIT S&P 500 ticker is mapped to the Sid whose symbol it was on
that day (ticker reuse resolved by date). Prices are converted to the engine's basis: raw bars with
split adjustments only (Yahoo auto_adjust=False); dividends kept as amounts, not in prices.
SPY and BIL (benchmarks, market regime) come from Yahoo; BIL is needed only on the window T.
"""
import argparse
import gzip
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

from research.crisis import run as CR
from research.retest_robustness import run as RR
from research.sp1500 import engine as E
from research.sp1500 import run as RUN
from research.sp1500 import universe as U

ROOT = Path(__file__).resolve().parents[2]
T_END = pd.Timestamp("2011-12-30")
T_START_EXPECTED = pd.Timestamp("2008-01-15")
BASIS_TICKERS = ("AAPL", "MSFT", "XOM", "JNJ", "PG", "KO", "WMT", "IBM")
COVERAGE_MIN = 85.0


def norm(s):
    return "".join(ch for ch in str(s).upper() if ch.isalnum())


def snapshots(pit_text):
    snaps = U.parse_pit500(pit_text)
    return snaps[(snaps["date"] <= T_END)].reset_index(drop=True)


def symbols(pit, out):
    snaps = snapshots(Path(pit).read_text())
    s = snaps[snaps["date"] >= pd.Timestamp("2006-06-01")]
    ever = set().union(*s["members"])
    Path(out).write_text("\n".join(sorted(ever | set(BASIS_TICKERS) | {"SPY", "BIL"})))
    print(len(ever))
    return 0


# ----------------------------------------------------------------- conversion
def split_adjusted_frames(blob):
    """{sid: OHLCV(+Dividends) DataFrame} on the split-only basis."""
    sess = pd.DatetimeIndex(blob["sessions"]).tz_localize(None).normalize()
    A = blob["arrays"]
    sp = blob["splits"].copy()
    dv = blob["divs"].copy()
    frames = {}
    for k, sid in enumerate(blob["sids"]):
        df = pd.DataFrame({c.capitalize(): A[c][:, k].astype(float) for c in ("open", "high", "low", "close", "volume")},
                          index=sess)
        df = df[(df["Close"] > 0) & df["Close"].notna()]
        if df.empty:
            continue
        f = np.ones(len(df))
        for _, r in sp[sp["sid"] == sid].iterrows():
            eff = pd.Timestamp(r["effective_date"]).normalize()
            f[df.index < eff] *= float(r["ratio"])           # zipline: prices before eff x ratio
        for c in ("Open", "High", "Low", "Close"):
            df[c] = df[c] * f
        df["Volume"] = df["Volume"] / f
        df["Dividends"] = 0.0
        if len(dv):
            for _, r in dv[dv["sid"] == sid].iterrows():
                ex = pd.Timestamp(r["ex_date"]).normalize()
                if ex in df.index:
                    df.loc[ex, "Dividends"] = float(r["amount"]) * f[df.index.get_loc(ex)]
        df["Stock Splits"] = 0.0
        frames[sid] = df
    return frames, sess


def sid_on(maps, ticker, day):
    by = maps.attrs.get("_by")
    if by is None:
        by = maps.attrs["_by"] = {k: g for k, g in maps.groupby("key")}
    g = by.get(norm(ticker))
    if g is None:
        return None
    s = set(g.loc[(g["start_date"] <= day) & (g["end_date"] >= day), "sid"])
    return next(iter(s)) if len(s) == 1 else (None if not s else "AMBIGUOUS")


def sid_timeline(snaps, maps, end):
    """member_on-compatible timeline in Sids; returns (timeline, mapping stats)."""
    maps = maps.copy()
    maps["key"] = maps["symbol"].map(norm)
    stats = dict(ticker_days=0, mapped=0, unmapped=0, ambiguous=0)
    sid_snaps = []
    cache = {}
    first = pd.Timestamp("2007-01-03")
    older = snaps[snaps["date"] < first]
    if len(older):                                       # keep only the last snapshot before the bundle
        snaps = snaps[snaps["date"] >= older["date"].iloc[-1]]
    for _, r in snaps.iterrows():
        d, mem = max(r["date"], first), set()           # map as of the first bundle day at the earliest
        for t in r["members"]:
            k = (t, d)
            s = cache.get(k)
            if s is None:
                s = cache[k] = sid_on(maps, t, d)
            stats["ticker_days"] += 1
            if s is None:
                stats["unmapped"] += 1
                mem.add(f"UNMAPPED:{t}")
            elif s == "AMBIGUOUS":
                stats["ambiguous"] += 1
                mem.add(f"AMBIG:{t}")
            else:
                stats["mapped"] += 1
                mem.add(s)
        sid_snaps.append(dict(date=r["date"], members=mem))
    ss = pd.DataFrame(sid_snaps)
    tl = U.pit_from_snapshots(ss, set(ss.iloc[-1]["members"]), end)
    return tl, stats


def basis_check(frames, maps, sess):
    import yfinance as yf
    maps = maps.copy()
    maps["key"] = maps["symbol"].map(norm)
    out = {}
    for t in BASIS_TICKERS:
        sid = sid_on(maps, t, sess[-1])
        if sid in (None, "AMBIGUOUS") or sid not in frames:
            out[t] = dict(ok=False, reason="not mapped")
            continue
        y = yf.download(t, start=str(sess[0].date()), end=str((sess[-1] + pd.Timedelta(days=2)).date()),
                        auto_adjust=False, progress=False)
        yc = (y["Close"][t] if isinstance(y.columns, pd.MultiIndex) else y["Close"]).copy()
        yc.index = pd.to_datetime(yc.index).tz_localize(None).normalize()
        q = frames[sid]["Close"]
        j = q.index.intersection(yc.index)
        rel = (q.loc[j] / yc.loc[j] - 1).abs()
        share = float((rel <= 0.005).mean()) if len(j) else 0.0
        out[t] = dict(ok=share >= 0.99 and len(j) > 1000, sessions=int(len(j)), share_within_0p5pct=round(share, 4),
                      median_abs_rel=float(rel.median()) if len(j) else None)
    return out


def yahoo_etf(sym, start, end):
    import yfinance as yf
    y = yf.download(sym, start=start, end=end, auto_adjust=False, actions=True, progress=False)
    if isinstance(y.columns, pd.MultiIndex):
        y = y.xs(sym, axis=1, level=1) if sym in y.columns.get_level_values(1) else y.droplevel(1, axis=1)
    y.index = pd.to_datetime(y.index).tz_localize(None).normalize()
    for c in ("Dividends", "Stock Splits"):
        if c not in y:
            y[c] = 0.0
    return y


# ----------------------------------------------------------------- run
def run(export, pit, diag_json=None):
    out, man, W = RR._writer("learn")
    res = dict(plan="research/retest_robustness/PLAN.md §11", git=RUN._git_rev(), checks={})
    if diag_json and Path(diag_json).exists():
        d = json.loads(Path(diag_json).read_text())
        res["export_diag"] = {k: d.get(k) for k in ("sessions", "first_session", "last_session", "equities",
                                                   "symbol_rows", "selected_sids", "exported_sids", "splits",
                                                   "dividends", "unreadable_sids", "error", "bcolz_error")}

    def stop(reason):
        res.update(verdict="INCONCLUSIVE", reason=reason)
        W("results.json", json.dumps(res, indent=1, default=str))
        W("manifest.json", json.dumps(dict(files=dict(man)), indent=1))
        print(json.dumps(dict(verdict="INCONCLUSIVE", reason=reason, checks=res["checks"]), indent=1, default=str))
        return 0

    if not export or not Path(export).exists():
        return stop("§11.2.1 bundle export missing (license / ingestion)")
    with gzip.open(export, "rb") as f:
        blob = pickle.load(f)
    frames, sess = split_adjusted_frames(blob)
    c1 = sess[0] == pd.Timestamp("2007-01-03") and sess[-1] >= T_END
    res["checks"]["1_ingestion"] = dict(ok=bool(c1), first=str(sess[0].date()), last=str(sess[-1].date()),
                                        securities=len(frames))
    if not c1:
        return stop("§11.2.1 bundle calendar not 2007-01-03 .. 2011-12-30")
    snaps = snapshots(Path(pit).read_text())
    tl, mstats = sid_timeline(snaps, blob["maps"], T_END)
    res["checks"]["2_identifiers"] = dict(mstats, ok=True)
    basis = basis_check(frames, blob["maps"], sess)
    c3 = sum(v["ok"] for v in basis.values()) >= len(basis) - 1     # all but at most one reference
    res["checks"]["3_price_basis"] = dict(ok=bool(c3), tickers=basis)
    if not c3:
        return stop("§11.2.3 price basis not compatible with the engine")
    spy = yahoo_etf("SPY", "2007-01-03", "2012-01-04")
    bil = yahoo_etf("BIL", "2007-05-30", "2012-01-04")
    spy = spy[spy.index.isin(sess)]
    cal = pd.DatetimeIndex(spy.index)
    if not cal.equals(sess[sess <= cal[-1]]):
        return stop("SPY sessions differ from the bundle calendar")
    t0 = cal[260]
    c4 = t0 == T_START_EXPECTED and bil.index[0] <= t0
    res["checks"]["4_spy_bil"] = dict(ok=bool(c4), window_start=str(t0.date()), bil_first=str(bil.index[0].date()))
    if not c4:
        return stop("§11.2.4 / §11.3 window start or BIL availability")
    by_year, tab = RR.coverage(frames, tl, cal)
    c5 = all(v["coverage_pct"] >= COVERAGE_MIN for v in by_year.values())
    res["checks"]["5_coverage"] = dict(ok=bool(c5), by_year=by_year,
                                       members_without_data=int((~tab["has_data"]).sum()),
                                       removed_without_data=int(((~tab["has_data"]) & (~tab["member_at_end"])).sum()))
    if not c5:
        return stop("§11.2.5 coverage below 85 % in a year")
    # ------------------------------------------------- the test (all checks passed)
    end_mem = U.member_on(tl, T_END)
    meta = pd.DataFrame(dict(ticker=list(frames), group="sp500", sector=""))
    sig, data = E.detect(frames, spy, meta, sorted(end_mem & set(frames)), pit500=tl, strategies=[RR.MODE])
    tr = CR.trades_for(CR.eligible(sig, True), data, RR.MODE)
    res.update(candidates=int(len(tr)), window=[str(t0.date()), str(T_END.date())], books={})
    bm, bc = RR.bench(spy, bil, t0, T_END, cal)
    res["benchmarks"] = bm
    for bps in RR.BPS:
        curve, ex, m = RR.book(tr, data, t0, T_END, bps)
        s = RR.summary(curve, ex, m, spy)
        eq = curve.set_index("date")["equity"]
        s["named_windows"] = RR.named_windows(eq, spy)
        res["books"][f"T|{int(bps)}bps"] = s
        res.setdefault("bootstrap_vs_5050", {})[f"{int(bps)}bps"] = RR.bootstrap(eq, bc["SPY50_BIL50"])
        if bps == 10.:
            res["regimes_10bps"] = RR.regime_tables(ex, curve, RR.regimes(spy))
            W("equity_T_10bps.csv", RUN.csv_bytes(curve[["date", "equity", "open_positions"]]))
    B, bb = res["books"], bm["SPY50_BIL50"]
    c = {"1_profitable": all((B[f"T|{b}bps"]["cagr_pct"] or -1) > 0 and (B[f"T|{b}bps"]["profit_factor"] or 0) > 1
                             for b in (10, 25)),
         "2_drawdown": B["T|10bps"]["max_dd_pct"] >= RR.DD_LIMIT,
         "3_vs_5050": all((B[f"T|{b}bps"]["cagr_pct"] or -99) >= bb["cagr_pct"] and
                          B[f"T|{b}bps"]["max_dd_pct"] >= bb["max_dd_pct"] for b in (10, 25)),
         "4_trades": B["T|10bps"]["closed_trades"] >= 30, "5_checks": True}
    res["criteria"] = c
    res["verdict"] = ("INCONCLUSIVE" if not c["4_trades"] else
                      "PASS" if c["1_profitable"] and c["2_drawdown"] and c["3_vs_5050"] else "FAIL")
    W("results.json", json.dumps(res, indent=1, default=str))
    W("manifest.json", json.dumps(dict(files=dict(man)), indent=1))
    print(json.dumps(dict(verdict=res["verdict"], criteria=c), indent=1))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=("symbols", "run"))
    ap.add_argument("--pit", required=True)
    ap.add_argument("--out")
    ap.add_argument("--export")
    ap.add_argument("--diag")
    a = ap.parse_args(argv)
    if a.stage == "symbols":
        return symbols(a.pit, a.out)
    return run(a.export, a.pit, a.diag)


if __name__ == "__main__":
    raise SystemExit(main())
