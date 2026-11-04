"""Event & First-Base Breakout v1: M reproduction, C vs S (and E when its data pass), index
alternatives (PLAN.md). Research only; never touches paper/, state/ or the bot.

    python -m research.event_base.run --dataset DIR [--events DIR] [--out DIR]
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import core
import portfolio_bt as pf
from research.crisis import run as CR
from research.event_base import bases as B
from research.event_base import benchmarks as BM
from research.event_base import execution as X
from research.sp1500 import engine as E
from research.sp1500 import run as RUN
from research.sp1500 import universe as U

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / "research/results/breakout_ma200/runs/2026-10-25T205752Z/results.json"
FULL_START, FULL_END = pd.Timestamp("2017-11-03"), pd.Timestamp("2026-10-23")
COSTS = (10, 25, 50)
ETF_COSTS = (2, 5)
SEED = 20261025
N_BOOT = 2000
WIN_REF = {"full": "full", "y2017_2021": "y2017_2021", "y2022_2026": "y2022_2026"}


# =====================================================================
# data
# =====================================================================
def build(frames, spy, pit_text):
    uni = pd.read_csv(CR.UNIVERSE_CSV)
    cal = pd.DatetimeIndex(spy.index).normalize()
    cur500 = set(uni.loc[uni["group"] == "sp500", "ticker"])
    snaps = U.parse_pit500(pit_text)
    tl = U.pit_from_snapshots(snaps, cur500, cal[-1])
    ever = set().union(*[U.member_on(tl, d) for d in cal[::5]]) | cur500
    fr = {t: f for t, f in frames.items() if t in ever}
    meta = pd.DataFrame(dict(ticker=list(fr), group="sp500", sector=""))
    ref500 = sorted(cur500 & set(fr))
    sig, data = E.detect(fr, spy, meta, ref500, pit500=tl, strategies=["breakout"])
    scores = E.rs_scores(fr)
    pmask = E.pit_mask(tl, scores.index, scores.columns)
    rs_pit = E.rs_percentile(scores, ref_mask=pmask)
    info = dict(tickers_ever_member=len(ever), with_prices=len(fr), breakout_detections=len(sig),
                pit_first=str(snaps["date"].iloc[0].date()), pit_last=str(snaps["date"].iloc[-1].date()))
    return sig, data, cal, tl, pmask, rs_pit, info


def missing_history(frames, cal, tl, cur500_n):
    have = {t: set(pd.DatetimeIndex(f.index).normalize()) for t, f in frames.items()}
    rows = []
    for d in cal[cal >= "2017-01-01"][::21]:
        mem = U.member_on(tl, d)
        rows.append(dict(date=d, members=len(mem), without_price=sum(d not in have.get(t, ()) for t in mem)))
    D = pd.DataFrame(rows)
    by = D.groupby(D["date"].dt.year).agg(members=("members", "mean"), without_price=("without_price", "mean"))
    by["share_pct"] = 100 * by["without_price"] / by["members"]
    return {int(k): {a: round(float(b), 2) for a, b in v.items()} for k, v in by.to_dict("index").items()}


def lookup(df, tickers, dates):
    """Values of a (date x ticker) frame at (date, ticker) pairs; NaN if absent."""
    out = np.full(len(tickers), np.nan, dtype=object)
    col = {c: k for k, c in enumerate(df.columns)}
    row = {d: k for k, d in enumerate(pd.DatetimeIndex(df.index).normalize())}
    arr = df.to_numpy()
    for n, (t, d) in enumerate(zip(tickers, dates)):
        r, c = row.get(pd.Timestamp(d).normalize()), col.get(t)
        if r is not None and c is not None:
            out[n] = arr[r, c]
    return out


def c_candidates(sig):
    s = CR.eligible(sig[sig["strategy"] == "breakout"], True)
    return pd.DataFrame(dict(ticker=s["ticker"].values, i=s["i"].values.astype(int),
                             signal_date=pd.to_datetime(s["signal_date"]).dt.normalize().values,
                             close=s["close"].values, stop=s["stop"].values,
                             rs=s["rs_pit500"].values.astype(float))).reset_index(drop=True)


def s_bases(data, cal, spy, pmask, rs_pit, start_i=260):
    bs = B.detect_all(data, cal, start_i)
    reg = core.market_regime(spy)
    sg = bs["outcome"] == "signal"
    bs["pit_member"] = None
    bs["rs_pit500"] = np.nan
    bs["spy_above50"] = None
    bs["spy_above200"] = None
    if sg.any():
        s = bs[sg]
        bs.loc[sg, "pit_member"] = lookup(pmask, s["ticker"].values, s["signal_date"].values)
        bs.loc[sg, "rs_pit500"] = lookup(rs_pit, s["ticker"].values, s["signal_date"].values).astype(float)
        bs.loc[sg, "spy_above50"] = reg["above50"].reindex(pd.DatetimeIndex(s["signal_date"])).values
        bs.loc[sg, "spy_above200"] = reg["above200"].reindex(pd.DatetimeIndex(s["signal_date"])).values

    def yes(v):
        return v is not None and v == v and bool(v)

    def status(r):
        if r["outcome"] != "signal":
            return r["outcome"]
        if not yes(r["pit_member"]):
            return "signal_filtered_not_member"
        if not (r["rs_pit500"] >= 85):
            return "signal_filtered_rs"
        if not (yes(r["spy_above50"]) and yes(r["spy_above200"])):
            return "signal_filtered_market"
        return "candidate"
    bs["status"] = bs.apply(status, axis=1) if len(bs) else []
    return bs


def s_candidates(bs):
    s = bs[bs["status"] == "candidate"]
    return pd.DataFrame(dict(ticker=s["ticker"].values, i=s["i"].values.astype(int),
                             signal_date=pd.to_datetime(s["signal_date"]).values, close=s["close"].values,
                             stop=s["stop"].values, rs=s["rs_pit500"].values.astype(float),
                             base_start=pd.to_datetime(s["base_start"]).values)).reset_index(drop=True)


# =====================================================================
# metrics
# =====================================================================
def curve_metrics(curve, initial):
    eq = curve.set_index("date")["equity"].astype(float)
    years = (eq.index[-1] - eq.index[0]).days / 365.25
    final = float(eq.iloc[-1])
    peak = np.maximum(initial, eq.cummax())
    dd = eq / peak - 1
    ret = pd.concat([pd.Series([initial]), eq.reset_index(drop=True)]).pct_change().dropna()
    yearly = eq.groupby(eq.index.year).last()
    prev = yearly.shift(1).fillna(initial)
    yr = {int(y): round(float((v / p - 1) * 100), 2) for y, v, p in zip(yearly.index, yearly, prev)}
    return dict(start=str(eq.index[0].date()), end=str(eq.index[-1].date()), final_equity=final,
                return_pct=100 * (final / initial - 1),
                cagr_pct=100 * ((final / initial) ** (1 / years) - 1) if years > 0 else None,
                max_dd_pct=100 * float(dd.min()), max_dd_trough=str(dd.idxmin().date()),
                vol_pct=100 * float(ret.std(ddof=1) * np.sqrt(252)), yearly_return_pct=yr,
                negative_years=[y for y, v in yr.items() if v < 0])


def book_metrics(b):
    m = curve_metrics(b["curve"], b["initial"])
    tr, c, o = b["trades"], b["curve"], b["orders"]
    closed = tr[tr["status"] == "closed"] if len(tr) else tr
    res = (closed["net_pnl"] + closed["dividends"]) if len(closed) else pd.Series(dtype=float)
    years = (c["date"].iloc[-1] - c["date"].iloc[0]).days / 365.25
    tot = b["totals"]
    oc = o["outcome"].value_counts().to_dict() if len(o) else {}
    m.update(trades_executed=int(len(tr)), trades_closed=int(len(closed)),
             open_at_end=int((tr["status"] == "open").sum()) if len(tr) else 0,
             profit_factor=float(res[res > 0].sum() / -res[res <= 0].sum()) if (res <= 0).any() and res[res <= 0].sum() < 0 else None,
             win_rate_pct=float(100 * (res > 0).mean()) if len(res) else None,
             expectancy_r=float(closed["net_r"].mean()) if len(closed) else None,
             turnover_per_year=float((tot.get("notional", 0) + tot.get("notional_open", 0)) / c["equity"].mean() / years)
             if years > 0 else None,
             costs_usd=float(tot.get("fees", 0)), dividends_usd=float(tot.get("dividends", 0)),
             invested_pct=float(100 * (c["market_value"] / c["equity"]).mean()),
             orders=dict(placed=int(oc.get("placed", 0)), filled=int(oc.get("filled", 0)),
                         filled_at_or_below_stop=int(oc.get("filled_at_or_below_stop", 0)),
                         expired_above_limit=int(oc.get("expired_above_limit", 0)),
                         expired_no_bar=int(oc.get("expired_no_bar", 0)),
                         simulated_nonfill=int(oc.get("simulated_nonfill", 0))),
             skips={k: int(v) for k, v in oc.items() if k.startswith("skip_") or k == "after_window"},
             exit_reasons=closed["reason"].value_counts().to_dict() if len(closed) else {},
             reconciliation=b["recon"])
    return m


def etf_metrics(b, initial=10000.):
    m = curve_metrics(b["curve"], initial)
    years = (b["curve"]["date"].iloc[-1] - b["curve"]["date"].iloc[0]).days / 365.25
    m.update(turnover_per_year=float(b["totals"]["notional"] / b["curve"]["equity"].mean() / years),
             costs_usd=float(b["totals"]["fees"]), distributions_usd=float(b["totals"]["distributions"]),
             invested_pct=float(100 * (b["curve"]["market_value"] / b["curve"]["equity"]).mean()))
    return m


def paired_bootstrap(ca, cb, initial_a=10000., initial_b=10000., n=N_BOOT, seed=SEED):
    """Annualised mean of daily return differences a - b; monthly block bootstrap."""
    def rets(c, ini):
        e = c.set_index("date")["equity"].astype(float)
        return pd.concat([pd.Series([ini], index=[e.index[0] - pd.Timedelta(days=1)]), e]).pct_change().iloc[1:]
    d = (rets(ca, initial_a) - rets(cb, initial_b)).dropna()
    months = d.groupby([d.index.year, d.index.month])
    blocks = [g.values for _, g in months]
    rng = np.random.default_rng(seed)
    stats = np.empty(n)
    for k in range(n):
        pick = rng.integers(0, len(blocks), len(blocks))
        stats[k] = 252 * np.concatenate([blocks[i] for i in pick]).mean()
    return dict(mean_annual_pct=float(100 * 252 * d.mean()), ci90_pct=[float(100 * np.percentile(stats, 5)),
                                                                     float(100 * np.percentile(stats, 95))],
                share_above_0=float((stats > 0).mean()), months=len(blocks), resamples=n, seed=seed)


# =====================================================================
# decision (PLAN.md §7)
# =====================================================================
def decide(books, bench, variant, ref=None, extra=None, min_full=100, min_half=30):
    g = lambda w, c: books[f"{variant}|{w}|{c}"]                                # noqa: E731
    chk = {}
    chk["1_drawdown"] = all(g(w, c)["max_dd_pct"] >= -20.0 for w in ("full", "y2017_2021", "y2022_2026")
                            for c in (10, 25))
    chk["2_result"] = (all(g("full", c)["return_pct"] > 0 and (g("full", c)["profit_factor"] or 0) > 1
                           for c in (10, 25))
                       and all(g(w, 25)["return_pct"] > 0 for w in ("y2017_2021", "y2022_2026")))
    if ref is not None:
        chk["3_signal_benefit"] = all(g("full", c)["cagr_pct"] > books[f"{ref}|full|{c}"]["cagr_pct"] for c in (10, 25))
    b5 = bench.get("SPY50_BIL50|full|2")
    if b5 is None:
        chk["4_vs_5050_bil"] = None
    else:
        ok = True
        for c in (10, 25):
            x = g("full", c)
            dc, ddd = x["cagr_pct"] - b5["cagr_pct"], x["max_dd_pct"] - b5["max_dd_pct"]
            ok &= (dc >= 1.0 and ddd >= -1.0) or (ddd >= 3.0 and dc >= -0.5)
        chk["4_vs_5050_bil"] = bool(ok)
    dom = []
    for k, v in bench.items():
        name, w, ec = k.split("|")
        if w != "full" or ec != "2" or v["max_dd_pct"] < -20.0:
            continue
        for c in (10, 25):
            x = g("full", c)
            if v["cagr_pct"] > x["cagr_pct"] and v["max_dd_pct"] > x["max_dd_pct"]:
                dom.append(f"{name} dominates at {c} bps")
    chk["5_no_simpler_dominates"] = not dom
    n_full = g("full", 10)["trades_closed"]
    n_h = min(g(w, 10)["trades_closed"] for w in ("y2017_2021", "y2022_2026"))
    chk["6_sample"] = n_full >= min_full and n_h >= min_half
    if extra:
        chk.update(extra)
    if chk["6_sample"] is False or any(v is None for v in chk.values()) or chk.get("7_event_coverage") is False:
        verdict = "INSUFFICIENT_DATA"
    else:
        verdict = "RESEARCH_CANDIDATE" if all(chk.values()) else "NOT_A_CANDIDATE"
    return dict(checks=chk, dominated_by=dom, closed_trades_full=int(n_full), closed_trades_min_half=int(n_h),
                verdict=verdict)


# =====================================================================
# main
# =====================================================================
def fetch_etf(sym):
    import yfinance as yf
    df = yf.download(sym, start="2016-01-01", end="2026-10-24", interval="1d", auto_adjust=False,
                     actions=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    return df


def frame_sha(df):
    cols = [c for c in ("Open", "High", "Low", "Close", "Dividends") if c in df]
    return hashlib.sha256(pd.util.hash_pandas_object(df[cols].round(8), index=True).values.tobytes()).hexdigest()


def reproduce_m(sig, data, cal, windows):
    ref = json.loads(REF.read_text())["books"]
    tr = CR.trades_for(CR.eligible(sig, True), data, "breakout")
    rows, ok = [], True
    for w, (s0, s1) in windows.items():
        for c in COSTS:
            curve, ex, m = pf.replay(tr, data, start=s0, end=s1, open_at_end="mark", cost_bps=float(c), **CR.CFG)
            r = ref[f"M|{WIN_REF[w]}|{c}"]
            d = dict(window=w, bps=c, return_pct=m["return_pct"], ref_return_pct=r["return_pct"],
                     max_dd_pct=m["max_drawdown_pct"], ref_max_dd_pct=r["max_dd_pct"],
                     trades=m["executed_trades"], ref_trades=r["trades"])
            d["match"] = (abs(d["return_pct"] - d["ref_return_pct"]) <= 1e-6 and
                          abs(d["max_dd_pct"] - d["ref_max_dd_pct"]) <= 1e-6 and d["trades"] == d["ref_trades"])
            ok &= d["match"]
            rows.append(d)
    return ok, rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--events", default=None, help="events folder with event_status.csv (optional)")
    ap.add_argument("--out", default=str(ROOT / "research/results/event_base/runs"))
    ap.add_argument("--run-id", default=None)
    a = ap.parse_args(argv)
    run_id = a.run_id or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    out = Path(a.out).resolve() / run_id
    root = ROOT if ROOT in out.parents else Path(a.out).resolve()
    man = {}
    W = lambda n, b: RUN.write_once(out / n, b, man, root)                      # noqa: E731

    frames, spy, pit_text, sha = CR.load(a.dataset)
    sig, data, cal, tl, pmask, rs_pit, info = build(frames, spy, pit_text)
    if cal[min(260, len(cal) - 1)] != FULL_START or cal[-1] != FULL_END:
        raise SystemExit(f"calendar mismatch: {cal[260]} .. {cal[-1]}")
    windows = dict(full=(FULL_START, FULL_END), y2017_2021=(FULL_START, pd.Timestamp("2021-12-31")),
                   y2022_2026=(cal[cal >= "2022-01-01"][0], FULL_END))
    res = dict(plan="research/event_base/PLAN.md", git=RUN._git_rev(), dataset_sha256=sha,
               dataset_artifact="shorts10y-dataset-40152515701 (run 40152515701)", data=info,
               windows={k: [str(v[0].date()), str(v[1].date())] for k, v in windows.items()})
    uni = pd.read_csv(CR.UNIVERSE_CSV)
    res["missing_history_by_year"] = missing_history(frames, cal, tl, int((uni["group"] == "sp500").sum()))

    # ---- 1) reproduction gate
    ok, rep = reproduce_m(sig, data, cal, windows)
    res["reproduction_M"] = dict(passed=bool(ok), rows=rep)
    if not ok:
        W("results.json", json.dumps(res, indent=1, default=str))
        raise SystemExit("reproduction of M failed: stop")

    # ---- 2) candidates
    C = c_candidates(sig)
    rs_chk = lookup(rs_pit, C["ticker"].values, C["signal_date"].values).astype(float)
    res["rs_consistency_C"] = bool(np.allclose(rs_chk, C["rs"].values, equal_nan=True))
    if not res["rs_consistency_C"]:
        raise SystemExit("RS recomputation differs from detect(): stop")
    bs = s_bases(data, cal, spy, pmask, rs_pit)
    S = s_candidates(bs)
    in_full = lambda d: (pd.to_datetime(d) >= FULL_START) & (pd.to_datetime(d) <= FULL_END)  # noqa: E731
    res["candidates"] = dict(C=int(in_full(C["signal_date"]).sum()), S=int(in_full(S["signal_date"]).sum()),
                             S_bases_by_outcome=bs[in_full(bs["base_end"])]["status"].value_counts().to_dict())
    W("s_candidates.csv", RUN.csv_bytes(bs))
    cands = {"C": C, "S": S}

    ev = None
    if a.events:
        ev_path = Path(a.events) / "event_status.csv"
        cov = json.loads((Path(a.events) / "coverage.json").read_text())
        res["events"] = dict(folder=str(a.events), coverage=cov)
        if cov.get("full_collection_passed"):
            ev = pd.read_csv(ev_path, parse_dates=["signal_date"])
    if ev is not None:
        key = ev.set_index(["ticker", "signal_date"])["status"]
        st = [key.get((t, pd.Timestamp(d)), "unknown") for t, d in zip(S["ticker"], S["signal_date"])]
        S = S.assign(event_status=st)
        cands["S_covered"] = S[S["event_status"].isin(["raise", "known_no_raise"])].reset_index(drop=True)
        cands["E"] = S[S["event_status"] == "raise"].reset_index(drop=True)

    # ---- 3) books
    books, raw = {}, {}
    for v, cd in cands.items():
        for w, (s0, s1) in windows.items():
            for c in COSTS:
                b = X.run_book(cd, data, cal, s0, s1, float(c), tag=v)
                books[f"{v}|{w}|{c}"] = book_metrics(b)
                raw[(v, w, c)] = b
        for name, kw in X.SENSITIVITY.items():
            if name == "base":
                continue
            for c in (10, 25):
                b = X.run_book(cd, data, cal, *windows["full"], float(c), tag=v, **kw)
                books[f"{v}|full|{c}|{name}"] = book_metrics(b)
    for v in cands:
        b = raw[(v, "full", 10)]
        W(f"trades_{v}_full_10bps.csv", RUN.csv_bytes(b["trades"]))
        W(f"orders_{v}_full_10bps.csv", RUN.csv_bytes(b["orders"]))
        W(f"equity_{v}_full_10bps.csv", RUN.csv_bytes(b["curve"]))
        W(f"trades_{v}_full_25bps.csv", RUN.csv_bytes(raw[(v, "full", 25)]["trades"]))

    # ---- 4) index alternatives
    prices, etf_src = {"SPY": spy.copy()}, {}
    spy_div = "Dividends" in spy and float(spy["Dividends"].fillna(0).sum()) > 0
    etf_src["SPY"] = dict(source="dataset bars.pkl.gz", distributions_in_dataset=bool(spy_div), sha256=frame_sha(spy))
    if not spy_div:
        try:
            sd = fetch_etf("SPY")
            prices["SPY"]["Dividends"] = sd["Dividends"].reindex(pd.DatetimeIndex(spy.index).normalize()).fillna(0).values
            etf_src["SPY"].update(distributions="yfinance SPY actions", dist_sha256=frame_sha(sd))
        except Exception as e:                                       # noqa: BLE001
            etf_src["SPY"]["distributions_error"] = str(e)[:200]
    try:
        bil = fetch_etf("BIL")
        if bil.empty:
            raise ValueError("empty BIL")
        prices["BIL"] = bil
        etf_src["BIL"] = dict(source="yfinance BIL auto_adjust=False actions=True", rows=len(bil),
                              first=str(bil.index[0].date()), last=str(bil.index[-1].date()), sha256=frame_sha(bil),
                              distributions_sum=float(bil["Dividends"].sum()))
        W("bil_prices.csv", RUN.csv_bytes(bil.reset_index()))
    except Exception as e:                                           # noqa: BLE001
        etf_src["BIL"] = dict(error=str(e)[:200])
    res["etf_sources"] = etf_src
    bench, bench_price_only, bcurves = {}, {}, {}
    complete = "BIL" in prices and (spy_div or "distributions" in etf_src["SPY"])
    for w, (s0, s1) in windows.items():
        days = [d for d in cal if s0 <= d <= s1]
        for name, rule in BM.rules(spy, days).items():
            if name == "SPY50_BIL50" and "BIL" not in prices:
                continue
            px = {s: prices[s] for s in (("SPY", "BIL") if name == "SPY50_BIL50" else ("SPY",))}
            for ec in ETF_COSTS:
                rule_fn = BM.rules(spy, days)[name]
                b = BM.etf_book(px, days, rule_fn, cost_bps=float(ec))
                bench[f"{name}|{w}|{ec}"] = etf_metrics(b)
                if w == "full" and ec == 2:
                    bcurves[name] = b["curve"]
            b = BM.etf_book(px, days, BM.rules(spy, days)[name], cost_bps=2.0, with_dist=False)
            bench_price_only[f"{name}|{w}|2"] = etf_metrics(b)
    res["benchmarks"] = bench
    res["benchmarks_price_only"] = bench_price_only
    res["benchmarks_economic_complete"] = bool(complete)
    for k, cv in bcurves.items():
        W(f"equity_bench_{k}.csv", RUN.csv_bytes(cv))
    res["books"] = books

    # ---- 5) decisions + bootstrap
    dec = {"C": decide(books, bench, "C"), "S": decide(books, bench, "S", ref="C")}
    if ev is not None:
        cov_ok = bool(res["events"]["coverage"].get("all_years_ge_80"))
        dec["E"] = decide(books, bench, "E", ref="S_covered", min_full=50, min_half=20,
                          extra={"7_event_coverage": cov_ok})
    else:
        dec["E"] = dict(verdict="INSUFFICIENT_DATA", reason="event data did not pass the pilot / coverage gate "
                        "(see events coverage); no E return computed")
    res["decision"] = dec
    boot = {}
    for c in (10, 25):
        boot[f"S-C|{c}"] = paired_bootstrap(raw[("S", "full", c)]["curve"], raw[("C", "full", c)]["curve"])
        if "SPY50_BIL50" in bcurves:
            boot[f"S-SPY50_BIL50|{c}"] = paired_bootstrap(raw[("S", "full", c)]["curve"], bcurves["SPY50_BIL50"])
        if ev is not None:
            boot[f"E-S_covered|{c}"] = paired_bootstrap(raw[("E", "full", c)]["curve"],
                                                        raw[("S_covered", "full", c)]["curve"])
    res["bootstrap"] = dict(note="exploratory; monthly blocks; no multiplicity correction", results=boot)
    W("results.json", json.dumps(res, indent=1, default=str))
    W("REPORT.md", report(res))
    W("manifest.json", json.dumps(dict(files=dict(man), dataset=sha, etf=etf_src), indent=1, default=str))
    print(json.dumps({k: v["verdict"] for k, v in dec.items()}, indent=1))
    return 0


def report(res):
    L = ["# Event & First-Base Breakout v1 — run report (exploratory)", "",
         f"git `{res['git']}`; dataset {res['dataset_artifact']}; plan `{res['plan']}`.", "",
         f"Reproduction of M (PR #23): **{'passed' if res['reproduction_M']['passed'] else 'FAILED'}**.", "",
         "## Books (new execution model)", "",
         "| book | window | bps | return % | CAGR % | max DD % | vol % | PF | closed | turnover/yr | invested % | expired>limit | no bar |",
         "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for k, v in res["books"].items():
        p = k.split("|")
        if len(p) != 3:
            continue
        f = lambda x: "—" if x is None else f"{x:.2f}"                          # noqa: E731
        L.append(f"| {p[0]} | {p[1]} | {p[2]} | {f(v['return_pct'])} | {f(v['cagr_pct'])} | {f(v['max_dd_pct'])} | "
                 f"{f(v['vol_pct'])} | {f(v['profit_factor'])} | {v['trades_closed']} | {f(v['turnover_per_year'])} | "
                 f"{f(v['invested_pct'])} | {v['orders']['expired_above_limit']} | {v['orders']['expired_no_bar']} |")
    L += ["", "## Index alternatives", "", "| benchmark | window | ETF bps | return % | CAGR % | max DD % | vol % |",
          "|---|---|---:|---:|---:|---:|---:|"]
    for k, v in res["benchmarks"].items():
        p = k.split("|")
        L.append(f"| {p[0]} | {p[1]} | {p[2]} | {v['return_pct']:.2f} | {v['cagr_pct']:.2f} | {v['max_dd_pct']:.2f} | {v['vol_pct']:.2f} |")
    L += ["", "## Decisions", ""]
    for k, v in res["decision"].items():
        L.append(f"- **{k}: {v['verdict']}** — {json.dumps(v.get('checks', v.get('reason')), default=str)}")
    L += ["", "## Bootstrap (exploratory)", ""]
    for k, v in res["bootstrap"]["results"].items():
        L.append(f"- {k}: mean {v['mean_annual_pct']:.2f} %/yr, 90 % CI {v['ci90_pct'][0]:.2f}…{v['ci90_pct'][1]:.2f}, "
                 f"P(>0) {v['share_above_0']:.2f}")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
