"""Retest M (Retest + SPY > MA200) — independent robustness check (PLAN.md §10). Research only.

    python -m research.retest_robustness.run repro   --dataset DIR10Y          # §10.2 gate
    python -m research.retest_robustness.run data    --dist DIR                # 2006-2016 download + coverage
    python -m research.retest_robustness.run analyze --dataset DIR             # §7 books, if the gates pass

The strategy code path is the PR #19 one (research/crisis/run.py) unchanged: eligible(sig, ma200=True),
trades_for(..., "retest"), gated_replay(dd=None) = portfolio_bt.replay with the production CFG.
Results are written once under research/results/retest_robustness/.
"""
import argparse
import gzip
import hashlib
import io
import json
import math
import pickle
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import backtest as bt
from research.crisis import run as CR
from research.retest_robustness import benchmarks as BM
from research.sp1500 import data as D
from research.sp1500 import engine as E
from research.sp1500 import run as RUN
from research.sp1500 import universe as U

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research/results/retest_robustness"
REF = ROOT / "research/results/crisis/runs/2026-10-25T0255Z/results.json"
MODE = "retest"
U_START, U_END = pd.Timestamp("2007-06-01"), pd.Timestamp("2016-10-21")
WINDOWS = {"U": ("2007-06-01", "2016-10-21"), "U1": ("2007-06-01", "2011-12-30"),
           "U2": ("2012-01-03", "2016-10-21")}
BPS = (10., 25., 50.)
DOWNLOAD_START, DOWNLOAD_END = "2005-12-01", "2016-10-25"   # yfinance end is exclusive
NAMED = {"bear_2007_09": ("2007-10-09", "2009-03-09"), "recovery_2009_10": ("2009-03-10", "2010-04-23"),
         "correction_2010": ("2010-04-23", "2010-07-02"), "correction_2011": ("2011-04-29", "2011-10-03"),
         "correction_2015_16": ("2015-05-21", "2016-02-11")}
COVERAGE_MIN = 85.0
DD_LIMIT = -20.0
SEED = 20261026


def _stamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")


def _writer(sub):
    out = OUT / sub / _stamp()
    man = {}
    return out, man, (lambda n, b: RUN.write_once(out / n, b, man, ROOT))


# =====================================================================
# 1. reproduction gate (§10.2)
# =====================================================================
def repro(dataset):
    ref = json.loads(REF.read_text())
    frames, spy, pit_text, sha = CR.load(dataset)
    assert sha == ref["dataset_sha256"], f"dataset differs: {sha}"
    sig, data, cal, info = CR.build(frames, spy, pit_text)
    start = cal[min(260, len(cal) - 1)]
    windows = dict(full=(start, cal[-1]), development=(start, pd.Timestamp("2021-12-31")),
                   holdout=(cal[cal >= CR.HOLDOUT][0], cal[-1]))
    rows, ok = [], True
    for vid, ma in (("M", True), ("C", False)):
        tr = CR.trades_for(CR.eligible(sig, ma), data, MODE)
        for w, (a, b) in windows.items():
            for bps in (10., 25.):
                curve, ex, m, _ = CR.gated_replay(tr, data, a, b, None, bps)
                got = CR.metrics(curve, ex, m, spy)
                key = f"retest|{vid}|{w}|{int(bps)}bps"
                r = ref["books"][key]
                d_ret, d_dd = abs(got["return_pct"] - r["return_pct"]), abs(got["max_dd_pct"] - r["max_dd_pct"])
                good = d_ret <= 1e-6 and d_dd <= 1e-6 and got["trades"] == r["trades"]
                ok &= good
                rows.append(dict(book=key, ref_return=r["return_pct"], got_return=got["return_pct"],
                                 ref_dd=r["max_dd_pct"], got_dd=got["max_dd_pct"], ref_trades=r["trades"],
                                 got_trades=got["trades"], ok=good,
                                 cagr=got["cagr_pct"], profit_factor=got["profit_factor"]))
    out, man, W = _writer("repro")
    res = dict(passed=bool(ok), reference=str(REF.relative_to(ROOT)), dataset_sha256=sha, data=info,
               git=RUN._git_rev(), books=rows)
    W("repro.json", json.dumps(res, indent=1, default=str))
    W("manifest.json", json.dumps(dict(files=dict(man)), indent=1))
    print(json.dumps(dict(passed=ok), indent=1))
    return 0 if ok else 3


# =====================================================================
# 2. data: PIT members 2006-2016, Yahoo bars, coverage + survivorship (§10.6)
# =====================================================================
def coverage(frames, tl, cal):
    """Per year: PIT member-days, member-days with a bar on that session, %; plus per-ticker table."""
    idx = {t: set(pd.DatetimeIndex(f.index).normalize()) for t, f in frames.items()}
    yr, per_t = {}, {}
    end_members = U.member_on(tl, cal[-1])
    for d in cal:
        mem = U.member_on(tl, d)
        y = d.year
        a = yr.setdefault(y, [0, 0, 0, 0, 0, 0])
        for t in mem:
            has = t in idx and d in idx[t]
            stay = t in end_members
            a[0] += 1
            a[1] += has
            a[2 if stay else 4] += 1
            a[3 if stay else 5] += has
            p = per_t.setdefault(t, [0, 0, None, None])
            p[0] += 1
            p[1] += has
            p[2] = p[2] or d
            p[3] = d
    by_year = {int(y): dict(member_days=v[0], covered=v[1], coverage_pct=round(100 * v[1] / v[0], 2),
                            stayed_days=v[2], stayed_cov_pct=round(100 * v[3] / v[2], 2) if v[2] else None,
                            removed_days=v[4], removed_cov_pct=round(100 * v[5] / v[4], 2) if v[4] else None)
               for y, v in sorted(yr.items())}
    rows = []
    for t, (n, c, a, b) in per_t.items():
        f = frames.get(t)
        rows.append(dict(ticker=t, member_days=n, covered_days=c, coverage_pct=round(100 * c / n, 2),
                         first_member_day=str(a.date()), last_member_day=str(b.date()),
                         member_at_end=t in end_members, has_data=f is not None,
                         first_bar=str(f.index[0].date()) if f is not None else None,
                         last_bar=str(f.index[-1].date()) if f is not None else None))
    tab = pd.DataFrame(rows).sort_values(["has_data", "member_days"], ascending=[True, False])
    return by_year, tab


def data_stage(dist):
    dist = Path(dist)
    dist.mkdir(parents=True, exist_ok=True)
    rec = U.fetch_pit500()
    if not rec.get("ok"):
        raise SystemExit(f"PIT source failed: {rec.get('error')}")
    (dist / "sp500_pit_fja05680.csv").write_bytes(rec["_raw"])
    snaps = rec["_snaps"]
    # timeline restricted to snapshots up to U_END; after the last one the last snapshot applies
    s2 = snaps[snaps["date"] <= U_END].reset_index(drop=True)
    tl = U.pit_from_snapshots(s2, set(s2.iloc[-1]["members"]), U_END)
    ever = set()
    for _, r in snaps[(snaps["date"] >= pd.Timestamp("2006-01-01")) & (snaps["date"] <= U_END)].iterrows():
        ever |= set(r["members"])
    ever |= set(U.member_on(tl, pd.Timestamp("2006-01-03")))
    import yfinance as yf

    def dl(ch):
        return yf.download(list(ch), start=DOWNLOAD_START, end=DOWNLOAD_END, interval="1d",
                           group_by="ticker", auto_adjust=False, actions=True, threads=True,
                           progress=False)
    tickers = sorted(ever) + ["SPY", "BIL"]
    frames, rep = D.download(tickers, period=f"{DOWNLOAD_START}_{DOWNLOAD_END}", downloader=dl,
                             cache_dir=str(ROOT / ".cache/retest_robustness"), asof=DOWNLOAD_END)
    # §10 addendum (2026-10-26, before any backtest): tickers that came back empty in a 100-ticker
    # chunk are retried one by one (Yahoo returns empty frames under load); still-empty = missing.
    for rnd in range(2):
        miss = rep.loc[rep["status"] != "ok", "ticker"].tolist()
        if not miss:
            break
        f2, r2 = D.download(miss, period=f"{DOWNLOAD_START}_{DOWNLOAD_END}_single{rnd}", downloader=dl, chunk=1,
                            pause=1.0 + rnd, retries=1, cache_dir=str(ROOT / ".cache/retest_robustness"), asof=DOWNLOAD_END)
        frames.update(f2)
        rep = pd.concat([rep[~rep["ticker"].isin(r2.loc[r2["status"] == "ok", "ticker"])],
                         r2[r2["status"] == "ok"].assign(retry_round=rnd + 1)], ignore_index=True)
        print(f"retry round {rnd + 1}: {len(f2)} of {len(miss)} recovered")
    spy, bil = frames.pop("SPY"), frames.pop("BIL")
    cal = pd.DatetimeIndex(spy.index)
    blob = gzip.compress(pickle.dumps(dict(frames=frames, spy=spy, bil=bil)))
    (dist / "bars.pkl.gz").write_bytes(blob)
    rep.to_csv(dist / "download_report.csv", index=False)
    ucal = cal[(cal >= U_START) & (cal <= U_END)]
    by_year, tab = coverage(frames, tl, ucal)
    sha = {"bars.pkl.gz": hashlib.sha256(blob).hexdigest(),
           "sp500_pit_fja05680.csv": rec["sha256"]}
    out, man, W = _writer("data")
    gate = all(v["coverage_pct"] >= COVERAGE_MIN for v in by_year.values())
    res = dict(pit_source=rec["url"], pit_first=rec["first"], pit_last=rec["last"],
               tickers_ever_member=len(ever), with_data=len(frames), spy_first=str(cal[0].date()),
               spy_last=str(cal[-1].date()), bil_first=str(bil.index[0].date()), sha256=sha,
               coverage_by_year=by_year, coverage_gate_passed=bool(gate), threshold_pct=COVERAGE_MIN,
               members_without_data=int((~tab["has_data"]).sum()),
               removed_members_without_data=int(((~tab["has_data"]) & (~tab["member_at_end"])).sum()),
               bars_end_before_membership=int((tab["has_data"] & (tab["last_bar"] < tab["last_member_day"])).sum()),
               git=RUN._git_rev())
    W("coverage.json", json.dumps(res, indent=1, default=str))
    W("members.csv", RUN.csv_bytes(tab))
    W("download_report.csv", RUN.csv_bytes(rep))
    W("manifest.json", json.dumps(dict(files=dict(man), dataset=sha), indent=1))
    print(json.dumps({k: res[k] for k in ("tickers_ever_member", "with_data", "coverage_gate_passed",
                                          "members_without_data")}, indent=1))
    print(json.dumps(by_year, indent=1))
    return 0


# =====================================================================
# 3. analysis (§7, §10)
# =====================================================================
def load_u(dataset):
    d = Path(dataset)
    bars = next(d.rglob("bars.pkl.gz"))
    pit = next(d.rglob("sp500_pit_fja05680.csv"))
    sha = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (bars, pit)}
    b = pickle.loads(gzip.decompress(bars.read_bytes()))
    return b["frames"], b["spy"], b["bil"], pit.read_text(), sha


def build_u(frames, spy, pit_text):
    snaps = U.parse_pit500(pit_text)
    s2 = snaps[snaps["date"] <= U_END].reset_index(drop=True)
    tl = U.pit_from_snapshots(s2, set(s2.iloc[-1]["members"]), U_END)
    end_mem = U.member_on(tl, U_END)
    meta = pd.DataFrame(dict(ticker=list(frames), group="sp500", sector=""))
    ref = sorted(end_mem & set(frames))
    sig, data = E.detect(frames, spy, meta, ref, pit500=tl, strategies=[MODE])
    return sig, data, tl, end_mem


def closed_trades(ex):
    return ex[ex["status"] == "closed"] if len(ex) else ex


def book(tr, data, a, b, bps):
    curve, ex, m, _ = CR.gated_replay(tr, data, pd.Timestamp(a), pd.Timestamp(b), None, bps)
    return curve, ex, m


def summary(curve, ex, m, spy):
    base = CR.metrics(curve, ex, m, spy)
    cl = closed_trades(ex)
    eq = curve.set_index("date")["equity"]
    base.pop("windows", None)
    base.update(closed_trades=int(len(cl)), open_at_end=int(m["open_positions_end"]),
                win_rate=float((cl["net_pnl"] > 0).mean()) if len(cl) else None,
                calmar=(base["cagr_pct"] / abs(base["max_dd_pct"])) if base["max_dd_pct"] else None,
                exposure_pct=float((curve["open_positions"] > 0).mean() * 100) if "open_positions" in curve else None,
                worst_month_pct=float((eq.resample("ME").last().pct_change().min()) * 100) if len(eq) > 40 else None)
    return base


def cagr_dd(eq, initial=10000.):
    eq = pd.Series(eq).astype(float)
    yrs = (eq.index[-1] - eq.index[0]).days / 365.25
    tot = eq.iloc[-1] / initial
    peak = np.maximum(initial, eq.cummax())
    return dict(return_pct=float((tot - 1) * 100), cagr_pct=float((tot ** (1 / yrs) - 1) * 100) if yrs > 0 else None,
                max_dd_pct=float((eq / peak - 1).min() * 100))


def bench(spy, bil, a, b, full_cal):
    days = full_cal[(full_cal >= pd.Timestamp(a)) & (full_cal <= pd.Timestamp(b))]
    rules = BM.rules(spy, days)
    out, curves = {}, {}
    for name in ("SPY100", "SPY50_BIL50", "SPY50_CASH50"):
        r = BM.etf_book_v2({"SPY": spy, "BIL": bil}, days, rules[name], cost_bps=2.0, full_cal=full_cal)
        eq = r["curve"].set_index("date")["equity"]
        out[name] = cagr_dd(eq)
        curves[name] = eq
    px = spy["Close"].reindex(days)
    prev = spy["Close"][spy.index < days[0]]
    p0 = float(prev.iloc[-1]) if len(prev) else float(spy["Open"].reindex(days).iloc[0])
    out["SPY_price"] = cagr_dd(10000. * px / p0)
    return out, curves


def regimes(spy):
    c = spy["Close"].astype(float)
    ma200 = c.rolling(200).mean()
    vol = np.log(c).diff().rolling(20).std() * math.sqrt(252) * 100
    trend = np.where(c > ma200, "above_ma200", "below_ma200")
    vb = pd.cut(vol, [-np.inf, 12, 20, np.inf], labels=["low_lt12", "normal_12_20", "high_gt20"], right=False)
    return pd.DataFrame(dict(trend=trend, vol=vb.astype(str)), index=c.index)


def regime_tables(ex, curve, reg):
    cl = closed_trades(ex).copy()
    out = {}
    if len(cl):
        sd = pd.to_datetime(cl["entry_date"]).dt.normalize()     # regime at the close before entry
        rp = reg.shift(1)
        cl["trend"] = rp["trend"].reindex(sd).values
        cl["vol"] = rp["vol"].reindex(sd).values
    eq = curve.set_index("date")["equity"]
    dret = eq.pct_change().fillna(eq.iloc[0] / 10000. - 1)
    rprev = reg.shift(1).reindex(eq.index)          # regime known at the previous close
    for col in ("trend", "vol"):
        t = {}
        for k, g in (cl.groupby(col) if len(cl) else []):
            w, l = g.loc[g["net_pnl"] > 0, "net_pnl"].sum(), -g.loc[g["net_pnl"] <= 0, "net_pnl"].sum()
            t[str(k)] = dict(trades=int(len(g)), mean_r=float(g["net_r"].mean()),
                             profit_factor=float(w / l) if l > 0 else None,
                             win_rate=float((g["net_pnl"] > 0).mean()), net_pnl=float(g["net_pnl"].sum()))
        for k, g in dret.groupby(rprev[col]):
            t.setdefault(str(k), {}).update(sessions=int(len(g)),
                                            compounded_book_return_pct=float((np.prod(1 + g) - 1) * 100))
        out[col] = t
    return out


def named_windows(eq, spy):
    res = {}
    for n, (a, b) in NAMED.items():
        x = eq[(eq.index >= a) & (eq.index <= b)]
        if not len(x):
            continue
        p = eq[eq.index < a]
        base = p.iloc[-1] if len(p) else 10000.
        br, sr = float((x.iloc[-1] / base - 1) * 100), CR.spy_ret(spy, a, b)
        res[n] = dict(book_pct=round(br, 2), spy_price_pct=round(sr, 2) if sr is not None else None)
    return res


def bootstrap(eq_a, eq_b, n=2000, seed=SEED):
    ra, rb = eq_a.pct_change().dropna(), eq_b.reindex(eq_a.index).pct_change().dropna()
    d = (ra - rb).dropna()
    months = [g.values for _, g in d.groupby([d.index.year, d.index.month])]
    rng = np.random.default_rng(seed)
    stats = []
    for _ in range(n):
        pick = rng.integers(0, len(months), len(months))
        s = np.concatenate([months[k] for k in pick])
        stats.append(s.mean() * 252 * 100)
    return dict(observed_ann_diff_pct=float(d.mean() * 252 * 100),
                ci95=[float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))],
                share_gt0=float(np.mean(np.array(stats) > 0)), resamples=n, seed=seed)


def analyze(dataset, coverage_json):
    cov = json.loads(Path(coverage_json).read_text())
    out, man, W = _writer("runs")
    if not cov["coverage_gate_passed"]:
        res = dict(verdict="INCONCLUSIVE", reason="coverage gate failed (§10.6): " + json.dumps(
            {y: v["coverage_pct"] for y, v in cov["coverage_by_year"].items()}), git=RUN._git_rev())
        W("results.json", json.dumps(res, indent=1))
        W("manifest.json", json.dumps(dict(files=dict(man)), indent=1))
        print(json.dumps(res, indent=1))
        return 0
    frames, spy, bil, pit_text, sha = load_u(dataset)
    assert sha == cov["sha256"], "dataset differs from the coverage run"
    sig, data, tl, end_mem = build_u(frames, spy, pit_text)
    cal = pd.DatetimeIndex(spy.index)
    tr = CR.trades_for(CR.eligible(sig, True), data, MODE)
    res = dict(plan="research/retest_robustness/PLAN.md §10", dataset_sha256=sha, git=RUN._git_rev(),
               candidates=int(len(tr)), books={}, benchmarks={}, coverage=cov["coverage_by_year"])
    reg = regimes(spy)
    curves = {}
    for w, (a, b) in WINDOWS.items():
        res["benchmarks"][w], bc = bench(spy, bil, a, b, cal)
        for bps in BPS:
            curve, ex, m = book(tr, data, a, b, bps)
            key = f"{w}|{int(bps)}bps"
            s = summary(curve, ex, m, spy)
            eq = curve.set_index("date")["equity"]
            s["named_windows"] = named_windows(eq, spy) if w == "U" else None
            res["books"][key] = s
            if bps == 10.:
                curves[w] = (curve, ex)
                W(f"equity_{w}_10bps.csv", RUN.csv_bytes(curve))
                W(f"trades_{w}_10bps.csv", RUN.csv_bytes(ex))
            if w == "U":
                res.setdefault("bootstrap_vs_5050", {})[f"{int(bps)}bps"] = bootstrap(eq, bc["SPY50_BIL50"])
    cU, exU = curves["U"]
    res["regimes_U_10bps"] = regime_tables(exU, cU, reg)
    cl = closed_trades(exU)
    tot = float(cl["net_pnl"].sum()) if len(cl) else 0.0
    yearly = res["books"]["U|10bps"]["yearly_return_pct"]
    res["concentration_U_10bps"] = dict(
        net_pnl_closed=tot, best5_share=float(cl["net_pnl"].nlargest(5).sum() / tot) if tot else None,
        best_year=max(yearly, key=yearly.get) if yearly else None)
    # start-date sensitivity: 4-year books from each available start inside U
    sens = {}
    for st in ("2007-06-01", "2008-01-02", "2009-01-02", "2010-01-04", "2011-01-03", "2012-01-03"):
        a = cal[cal >= pd.Timestamp(st)][0]
        b = cal[cal <= a + pd.DateOffset(years=4)][-1]
        for bps in (10., 25.):
            curve, ex, m = book(tr, data, a, b, bps)
            s = summary(curve, ex, m, spy)
            sens[f"{st}|{int(bps)}bps"] = {k: s[k] for k in ("return_pct", "cagr_pct", "max_dd_pct",
                                                             "profit_factor", "closed_trades")}
    res["start_date_sensitivity"] = sens
    # survivorship sensitivity: only tickers that were members at the end of U
    trs = tr[tr["ticker"].isin(end_mem)]
    surv = {}
    for bps in (10., 25.):
        curve, ex, m = book(trs, data, *WINDOWS["U"], bps)
        s = summary(curve, ex, m, spy)
        surv[f"{int(bps)}bps"] = {k: s[k] for k in ("return_pct", "cagr_pct", "max_dd_pct", "profit_factor",
                                                     "closed_trades")}
    res["survivorship_sensitivity_end_members_only"] = dict(candidates=int(len(trs)), books=surv)
    res["omitted_dividends_note"] = "trading books do not credit dividends (unchanged engine rule)"
    res["criteria"], res["verdict"] = verdict(res, cov)
    W("results.json", json.dumps(res, indent=1, default=str))
    W("manifest.json", json.dumps(dict(files=dict(man), dataset=sha), indent=1))
    print(json.dumps(dict(verdict=res["verdict"], criteria=res["criteria"]), indent=1, default=str))
    return 0


def verdict(res, cov):
    B, BM_ = res["books"], res["benchmarks"]
    c = {}
    c["1_profitable"] = all((B[f"U|{b}bps"]["cagr_pct"] or -1) > 0 and (B[f"U|{b}bps"]["profit_factor"] or 0) > 1
                            for b in (10, 25)) and all(B[f"{w}|25bps"]["return_pct"] > 0 for w in ("U1", "U2"))
    c["2_drawdown"] = all(B[f"{w}|10bps"]["max_dd_pct"] >= DD_LIMIT for w in ("U", "U1", "U2"))
    bb = BM_["U"]["SPY50_BIL50"]
    c["3_vs_5050"] = all((B[f"U|{b}bps"]["cagr_pct"] or -99) >= bb["cagr_pct"] and
                         B[f"U|{b}bps"]["max_dd_pct"] >= bb["max_dd_pct"] for b in (10, 25))
    c["4_trades"] = B["U|10bps"]["closed_trades"] >= 100 and all(B[f"{w}|10bps"]["closed_trades"] >= 30
                                                                 for w in ("U1", "U2"))
    c["5_coverage"] = bool(cov["coverage_gate_passed"])
    if not (c["4_trades"] and c["5_coverage"]):
        v = "INCONCLUSIVE"
    elif c["1_profitable"] and c["2_drawdown"] and c["3_vs_5050"]:
        v = "PASS"
    else:
        v = "FAIL"
    return c, v


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=("repro", "data", "analyze"))
    ap.add_argument("--dataset")
    ap.add_argument("--dist", default=str(ROOT / "dist/retest_robustness"))
    ap.add_argument("--coverage")
    a = ap.parse_args(argv)
    if a.stage == "repro":
        return repro(a.dataset)
    if a.stage == "data":
        return data_stage(a.dist)
    cov = a.coverage or str(sorted((OUT / "data").glob("*/coverage.json"))[-1])
    return analyze(a.dataset, cov)


if __name__ == "__main__":
    raise SystemExit(main())
