"""Bull flag v1.1 — exploratory historical run (PREREG_BULLFLAG_v1 §4-§6).

    python -m research.bull_flag.run --dataset DIR

DIR = the PR #5 dataset artifact (signals.csv.gz, bars.pkl.gz; run 38773034101). Writes a new
directory under research/results/bull_flag/runs/. All history here is EXPLORATORY (already
seen); independent confirmation is forward only (§7).
"""
import argparse
import gzip
import hashlib
import io
import json
import pickle
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import backtest as bt
import core
import portfolio_bt as pf
from research.bull_flag import protocol as Pr
from research.bull_flag import rules as F
from research.sp1500 import engine as E
from research.sp1500 import run as RUN

ROOT = Path(__file__).resolve().parents[2]
CFG = dict(initial_cash=10000., risk_fraction=.01, max_positions=5, max_new_per_day=3,
           max_position_fraction=.20, cost_bps=10.)
OTHER = ("retest", "vcp", "dbottom")
EXPECTED_SHA = {"signals.csv.gz": "98b6f816", "bars.pkl.gz": "3df57ff9"}


def tb(s):
    return s.map(lambda v: v if isinstance(v, bool) else str(v).lower() == "true")


def load(d):
    d = Path(d)
    sig = next(d.rglob("signals.csv.gz"))
    bars = next(d.rglob("bars.pkl.gz"))
    lab = pd.read_csv(sig, low_memory=False)
    for c in ("signal_date", "entry_date", "exit_date"):
        lab[c] = pd.to_datetime(lab[c], errors="coerce")
    b = pickle.load(io.BytesIO(gzip.decompress(bars.read_bytes())))
    sha = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (sig, bars)}
    return lab, b["frames"], b["spy"], sha


def month_boot(values: pd.Series, dates: pd.Series, n=Pr.N_BOOT, seed=Pr.SEED):
    """90 % interval of the mean, resampling calendar months (trades inside a month kept)."""
    v = pd.Series(values.to_numpy(float), index=pd.to_datetime(dates.to_numpy()))
    v = v.dropna()
    if len(v) < 2:
        return (np.nan, np.nan)
    m = v.index.to_period("M")
    groups = [v.values[m == k] for k in sorted(set(m))]
    rng = np.random.default_rng(seed)
    st = np.empty(n)
    for b in range(n):
        st[b] = np.concatenate([groups[k] for k in rng.integers(0, len(groups), len(groups))]).mean()
    return (float(np.quantile(st, .05)), float(np.quantile(st, .95)))


def stats(df, col):
    d = df[(df["trade_status"] == "closed") & df[col].notna()]
    r = d[col].astype(float)
    if not len(r):
        return dict(trades=0)
    w, l = r[r > 0], r[r <= 0]
    return dict(trades=int(len(r)), mean_r=float(r.mean()), median_r=float(r.median()),
                win_rate=float((r > 0).mean() * 100),
                profit_factor=float(w.sum() / -l.sum()) if l.sum() < 0 else np.inf,
                ci90=month_boot(r, d["signal_date"]))


def simulate(rows, data, mode, stop_col):
    raw = pd.DataFrame(dict(ticker=rows["ticker"], mode=mode, i=rows["i"],
                            date=rows["signal_date"], close=rows["close"], level=rows["level"],
                            stop_base=rows[stop_col], rs=rows["rs_pit500"],
                            vol_ratio=rows["vol_ratio"]))
    t = bt.simulate(raw, data, mode, hold=20, stop_buf=3.0, min_rs=0, min_vol=0.0, max_risk=0.0,
                    market_ok=None, entry_at="open", one_per_ticker=False, include_open=True)
    t["signal_date"] = pd.to_datetime(t["signal_date"])
    return t


def book(cands, data, start, end):
    curve, ex, m = pf.replay(cands.drop(columns=[c for c in ("kind",) if c in cands]), data,
                             start=start, end=end, open_at_end="mark", **CFG)
    eq = curve.set_index("date")["equity"]
    last = eq.groupby(eq.index.year).last()
    prev = last.shift(1).fillna(CFG["initial_cash"])
    closed = ex[ex["status"] == "closed"] if len(ex) else ex
    return dict(return_pct=m["return_pct"], cagr_pct=m["cagr_pct"], max_dd_pct=m["max_drawdown_pct"],
                trades=m["executed_trades"], expectancy_r=float(closed["net_r"].mean()) if len(closed) else np.nan,
                yearly_return_pct={int(k): round(float(v), 2) for k, v in ((last / prev - 1) * 100).items()})


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--out", default=str(ROOT / "research/results/bull_flag/runs"))
    a = ap.parse_args(argv)
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%MZ")
    out = Path(a.out) / run_id
    man = {}
    lab, frames, spy, sha = load(a.dataset)
    for name, pre in EXPECTED_SHA.items():                 # the frozen PR #5 dataset only
        if not sha[name].startswith(pre):
            raise SystemExit(f"dataset {name} sha {sha[name][:12]} != frozen {pre}")
    cal = pd.DatetimeIndex(spy.index)
    end = cal[-1]
    pit_t = sorted(set(lab.loc[tb(lab["pit_member_sp500"]), "ticker"]) |
                   set(lab.loc[lab["group"] == "sp500", "ticker"]))
    data = {t: E.arrays(frames[t]) for t in pit_t if t in frames and len(frames[t]) > 262}
    # ---- PIT S&P 500 eligible long detections (production filters, RS vs PIT members)
    pit = lab[(lab["direction"] == "long") & tb(lab["pit_member_sp500"]) &
              tb(lab["eligible_pit_primary"])].copy()
    brk = pit[pit["strategy"] == "breakout"].copy()
    # ---- flag detection on every bar of every PIT ticker (verifies flag ⊂ breakout on data)
    hits, raw_brk_keys = [], set(zip(lab.loc[lab["strategy"] == "breakout", "ticker"],
                                     lab.loc[lab["strategy"] == "breakout", "i"]))
    not_brk = 0
    for t, x in data.items():
        for i in range(F.MIN_BARS, len(x["C"])):
            d = F.flag_at(x, i, return_detail=True)
            if d is None:
                continue
            if (t, i) not in raw_brk_keys:
                not_brk += 1
            hits.append(dict(ticker=t, i=i, flag_level=d["level"], flag_stop_base=d["stop_base"],
                             n_flag=d["n_flag"], pole_gain=d["pole_gain"], depth=d["depth"],
                             retrace=d["retrace"]))
    fl = pd.DataFrame(hits)
    brk = brk.merge(fl, on=["ticker", "i"], how="left")
    brk["group"] = np.where(brk["flag_level"].notna(), "flag", "nonflag")
    # ================= Experiment A (S4): breakout stop for both groups ==================
    keep = E.non_overlapping(brk)                       # one chain per ticker, both groups
    A = brk[keep & (brk["trade_status"] == "closed")].copy()
    s4 = Pr.s4_statistic(A.assign(net_r=A["net_r_base"]))
    s4_wide = Pr.s4_statistic(A.assign(net_r=A["net_r_wide"]))
    allA = brk[brk["trade_status"] == "closed"]
    s4_sens = Pr.s4_statistic(allA.assign(net_r=allA["net_r_base"]))
    A_groups = {g: stats(A[A["group"] == g], "net_r_base") for g in ("flag", "nonflag")}
    # ================= Experiment B: structural stop =====================================
    fb = brk[brk["group"] == "flag"].copy()
    rows = []
    for r in fb.itertuples():
        x = data[r.ticker]
        stop = r.flag_stop_base * (1 - 0.03)
        mt = E.model_trade(x, r.i, "long", stop)
        rec = dict(ticker=r.ticker, i=r.i, signal_date=r.signal_date, strategy="flag",
                   direction="long", sector=r.sector, rs_pit500=r.rs_pit500, close=r.close,
                   stop=stop)
        rec.update(mt)
        rows.append(E.apply_costs(rec))
    B = pd.DataFrame(rows)
    B = B[B["close"] > B["stop"]] if len(B) else B         # valid stop at the close
    Bn = B[E.non_overlapping(B)] if len(B) else B
    Bs = {k: stats(Bn, c) for k, c in (("base_10bps", "net_r_base"), ("wide_25bps", "net_r_wide"),
                                       ("stress_50bps", "net_r_stress"))}
    years = {}
    for y in (2022, 2023, 2024, 2025, 2026):
        s = stats(Bn[pd.to_datetime(Bn["signal_date"]).dt.year == y], "net_r_base")
        years[y] = {k: s.get(k) for k in ("trades", "mean_r", "win_rate")}
    # ---- secondary view: today's S&P 500 list, RS vs the 500 reference
    cur = lab[(lab["strategy"] == "breakout") & (lab["group"] == "sp500") & tb(lab["eligible_primary"])]
    cur = cur.merge(fl, on=["ticker", "i"], how="inner")
    # ================= 4.1 overlap with other setups =====================================
    oth = pit[pit["strategy"].isin(OTHER)][["ticker", "i", "strategy"]]
    ov = []
    for r in fb.itertuples():
        o = oth[(oth["ticker"] == r.ticker) & (oth["i"] >= r.i - 5) & (oth["i"] <= r.i)]
        same = o[o["i"] == r.i]
        ov.append(dict(same_day_retest="retest" in set(same["strategy"]),
                       same_day_vcp="vcp" in set(same["strategy"]),
                       same_day_dbottom="dbottom" in set(same["strategy"]),
                       near_any=len(o) > 0,
                       new_vs_retest_vcp=not o["strategy"].isin(["retest", "vcp"]).any()))
    ov = pd.DataFrame(ov)
    overlap = dict(flags=len(fb), same_day_breakout=len(fb),       # flags are breakout rows
                   **{k: int(ov[k].sum()) for k in ov.columns} if len(ov) else {})
    # ================= portfolio books ====================================================
    start = cal[min(260, len(cal) - 1)]
    ret = pit[pit["strategy"] == "retest"]
    t_ret = simulate(ret, data, "retest", "stop_base")
    t_flag = simulate(fb.assign(stop_base=fb["flag_stop_base"]), data, "flag", "stop_base") \
        if len(fb) else t_ret.iloc[0:0]
    t_brk = simulate(brk, data, "breakout", "stop_base")
    A_book = book(Pr.merge_candidates(t_ret, t_ret.iloc[0:0]), data, start, end)
    B_book = book(Pr.merge_candidates(t_ret, t_flag, "flag"), data, start, end)
    C_book = book(Pr.merge_candidates(t_ret, t_brk, "breakout"), data, start, end)
    # ================= criteria ===========================================================
    b = Bs["base_10bps"]
    full = [years[y] for y in (2023, 2024, 2025)]
    crit = dict(
        S1_trades_ge_100=bool(b.get("trades", 0) >= 100),
        S2_mean_gt_0_and_ci_low_gt_0=bool(b.get("trades", 0) and b["mean_r"] > 0 and b["ci90"][0] > 0),
        S3_mean_25bps_gt_0=bool(Bs["wide_25bps"].get("trades", 0) and Bs["wide_25bps"]["mean_r"] > 0),
        S4_diff_gt_0_and_ci_low_gt_0=bool(np.isfinite(s4["S4"]) and s4["S4"] > 0 and s4["ci90"][0] > 0),
        S5_positive_in_2_of_3_years=bool(sum((y.get("mean_r") or -1) > 0 for y in full) >= 2),
        S6_book_b_ge_a_and_dd_within_3pp=bool(B_book["return_pct"] >= A_book["return_pct"] and
                                               B_book["max_dd_pct"] >= A_book["max_dd_pct"] - 3))
    crit["S1_S5_all"] = all(crit[k] for k in crit if k[:2] in ("S1", "S2", "S3", "S4", "S5"))
    res = dict(prereg="v1.1", rules_version=F.VERSION, dataset_sha256=sha, data_end=str(end.date()),
               exploratory=True, flags_detected_all_bars=len(fl),
               flags_not_a_raw_breakout=not_brk, eligible_breakouts=len(brk),
               eligible_flags=len(fb), overlap=overlap,
               experiment_A=dict(groups_nonoverlap=A_groups, S4_10bps=s4, S4_25bps=s4_wide,
                                 S4_sensitivity_no_overlap_rule=s4_sens),
               experiment_B=dict(signal_level=Bs, by_year=years,
                                 nonoverlap_trades=int(len(Bn)), all_trades=int(len(B))),
               secondary_current_list=dict(eligible_flags=len(cur),
                                           mean_net_r_breakout_stop=float(cur["net_r_base"].mean())
                                           if len(cur) else np.nan),
               portfolio=dict(a_retest=A_book, b_retest_plus_flag=B_book,
                              c_retest_plus_breakouts=C_book),
               criteria=crit,
               verdict=("S1-S5 PASSED (exploratory): eligible for a forward shadow test — owner decides"
                        if crit["S1_S5_all"] else
                        "FAILED: flag v1 is a closed hypothesis (no re-parametrisation)"))
    RUN.write_once(out / "results.json", json.dumps(res, indent=2, default=str), man, Path(a.out))
    keepcols = ["ticker", "signal_date", "i", "rs_pit500", "close", "stop", "entry_date", "entry",
                "exit_date", "exit", "exit_reason", "bars_held", "net_r_base", "net_r_wide"]
    RUN.write_once(out / "experiment_B_trades.csv",
                   RUN.csv_bytes(Bn[[c for c in keepcols if c in Bn]]), man, Path(a.out))
    acols = ["ticker", "signal_date", "i", "group", "rs_pit500", "level", "stop", "entry_date",
             "entry", "exit_date", "exit", "exit_reason", "bars_held", "net_r_base", "net_r_wide"]
    RUN.write_once(out / "experiment_A_trades.csv", RUN.csv_bytes(A[[c for c in acols if c in A]]),
                   man, Path(a.out))
    RUN.write_once(out / "flag_detections.csv", RUN.csv_bytes(fl), man, Path(a.out))
    RUN.write_once(out / "REPORT.md", report(res), man, Path(a.out))
    RUN.write_once(out / "manifest.json", json.dumps(dict(run_id=run_id, git=RUN._git_rev(),
                                                          files=man, dataset=sha), indent=2),
                   {}, Path(a.out))
    print(json.dumps(dict(criteria=crit, verdict=res["verdict"]), indent=1))
    return 0


def report(r):
    L = ["# Bull flag v1.1 — exploratory historical run", "",
         f"Rules `{r['rules_version']}`, PREREG `{r['prereg']}`, data end {r['data_end']}. "
         "**Exploratory:** this history was already seen; confirmation is forward only.", "",
         f"**Verdict: {r['verdict']}**", "", "## Criteria", "", "```json",
         json.dumps(r["criteria"], indent=1), "```", "",
         f"Flags on all bars: {r['flags_detected_all_bars']}; flags that are not a raw breakout: "
         f"{r['flags_not_a_raw_breakout']} (must be 0). Eligible breakouts {r['eligible_breakouts']}, "
         f"eligible flags {r['eligible_flags']}.", "", "## Full results", "", "```json",
         json.dumps({k: v for k, v in r.items() if k != 'criteria'}, indent=1, default=str), "```"]
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
