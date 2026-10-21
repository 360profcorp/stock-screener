"""Retest RS-first v1 diagnostic (research/retest_diag/PLAN.md). Historical backtest only.

    python -m research.retest_diag.run --dataset DIR

DIR = the frozen PR #5 dataset artifact (run 38773034101). Writes a new write-once directory
under research/results/retest_diag/runs/. Aborts unless the saved RS-first result is reproduced.
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
import portfolio_bt as pf
from research.sp1500 import engine as E
from research.sp1500 import rules as R
from research.sp1500 import run as RUN

ROOT = Path(__file__).resolve().parents[2]
CFG = dict(initial_cash=10000., risk_fraction=.01, max_positions=5, max_new_per_day=3,
           max_position_fraction=.20, cost_bps=10.)
EXPECTED_SHA = {"signals.csv.gz": "98b6f816", "bars.pkl.gz": "3df57ff9"}
TARGET = dict(return_pct=68.35310415699882, max_dd_pct=-19.20456303303514, executed=265,
              closed=261, expectancy_r=0.22771964261522995)
SMALL = 30
STOP_BINS = [-np.inf, 3, 5, 8, np.inf]
STOP_LABELS = ["<=3%", "3-5%", "5-8%", ">8%"]


def tb(s):
    return s.map(lambda v: v if isinstance(v, bool) else str(v).lower() == "true")


def load(d):
    d = Path(d)
    sig, bars = next(d.rglob("signals.csv.gz")), next(d.rglob("bars.pkl.gz"))
    sha = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (sig, bars)}
    for name, pre in EXPECTED_SHA.items():
        if not sha[name].startswith(pre):
            raise SystemExit(f"dataset {name} sha {sha[name][:12]} != frozen {pre}")
    lab = pd.read_csv(sig, low_memory=False)
    for c in ("signal_date", "entry_date", "exit_date"):
        lab[c] = pd.to_datetime(lab[c], errors="coerce")
    b = pickle.load(io.BytesIO(gzip.decompress(bars.read_bytes())))
    return lab, b["frames"], b["spy"], sha


def candidates(pool, data):
    raw = pd.DataFrame(dict(ticker=pool["ticker"], mode="retest", i=pool["i"],
                            date=pool["signal_date"], close=pool["close"], level=pool["level"],
                            stop_base=pool["stop_base"], rs=pool["rs"],
                            vol_ratio=pool["vol_ratio"]))
    tr = bt.simulate(raw, data, "retest", hold=R.HOLD, stop_buf=R.LONG_STOP_BUF_PCT, min_rs=0,
                     min_vol=0.0, max_risk=0.0, market_ok=None, entry_at="open",
                     one_per_ticker=False, include_open=True)
    tr["signal_date"] = pd.to_datetime(tr["signal_date"])
    tr["date"] = pd.to_datetime(tr["date"]).dt.normalize()
    return tr.sort_values(["date", "rs", "ticker"], ascending=[True, False, True],
                          kind="stable").reset_index(drop=True)


def net_r_px(entry, exit_, stop, bps):
    f = bps / 1e4
    return (exit_ * (1 - f) - entry * (1 + f)) / (entry - stop)


def label(df, date_col, risk_col):
    d = pd.to_datetime(df[date_col])
    return df.assign(year=d.dt.year.astype(str), quarter=d.dt.year.astype(str) + "Q" +
                     d.dt.quarter.astype(str),
                     market=np.where(tb(df["spy_above200"]), "SPY>MA200", "SPY<=MA200"),
                     stop_dist=pd.cut(df[risk_col], STOP_BINS, labels=STOP_LABELS,
                                      right=True).astype(str),
                     sector=df["sector"].fillna("").replace("", "unknown"))


def grp(df, by, rcol, pnl=None):
    rows = []
    for k, g in df.groupby(by, sort=True):
        r = g[rcol].astype(float).dropna()
        w, l = r[r > 0].sum(), -r[r <= 0].sum()
        row = {by: k, "trades": len(r), "mean_r": r.mean() if len(r) else np.nan,
               "median_r": r.median() if len(r) else np.nan,
               "profit_factor": w / l if l > 0 else np.inf, "win_rate": (r > 0).mean() * 100,
               "small_sample": len(r) < SMALL}
        if pnl:
            row["pnl_usd"] = g[pnl].sum()
        rows.append(row)
    out = pd.DataFrame(rows)
    if pnl and len(out):
        out["pnl_share_pct"] = 100 * out["pnl_usd"] / df[pnl].sum()
    return out


def replay(tr, data, start, end, bps=10., decisions=False):
    cfg = dict(CFG, cost_bps=bps)
    return pf.replay(tr, data, start=start, end=end, open_at_end="mark",
                     record_decisions=decisions, **cfg)


def summary(curve, ex, m):
    closed = ex[ex["status"] == "closed"]
    r = closed["net_r"]
    eq = curve.set_index("date")["equity"]
    last = eq.groupby(eq.index.year).last()
    yr = (last / last.shift(1).fillna(CFG["initial_cash"]) - 1) * 100
    return dict(return_pct=m["return_pct"], cagr_pct=m["cagr_pct"], max_dd_pct=m["max_drawdown_pct"],
                executed=m["executed_trades"], closed=len(closed), open_end=m["open_positions_end"],
                expectancy_r=float(r.mean()), median_r=float(r.median()),
                profit_factor=float(r[r > 0].sum() / -r[r <= 0].sum()),
                win_rate=float((r > 0).mean() * 100), final_equity=m["final_equity"],
                yearly_return_pct={int(k): round(float(v), 2) for k, v in yr.items()})


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--out", default=str(ROOT / "research/results/retest_diag/runs"))
    a = ap.parse_args(argv)
    root = Path(a.out)
    out = root / datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%MZ")
    man = {}
    lab, frames, spy, sha = load(a.dataset)
    cal = pd.DatetimeIndex(spy.index)
    start, end = cal[min(260, len(cal) - 1)], cal[-1]
    uni = sorted(set(lab.loc[lab["group"].isin(["sp500", "sp400", "sp600", "ambiguous"]), "ticker"]) |
                 set(lab.loc[tb(lab["pit_member_sp500"]), "ticker"]))
    data = {t: E.arrays(frames[t]) for t in uni if t in frames and len(frames[t]) > bt.WARMUP + 2}
    pool = lab[(lab["direction"] == "long") & (lab["strategy"] == "retest") &
               tb(lab["pit_member_sp500"]) & tb(lab["eligible_pit_primary"])].copy()
    pool["rs"] = pool["rs_pit500"]
    pool = pool.reset_index(drop=True)
    tr = candidates(pool, data)

    # ---- 1) reproduction gate ----------------------------------------------------------------
    curve, ex, m = replay(tr, data, start, end, decisions=True)
    base = summary(curve, ex, m)
    repro = {k: dict(saved=v, now=base[k if k != "max_dd_pct" else "max_dd_pct"],
                     equal=bool(abs(base[k] - v) <= 1e-9)) for k, v in TARGET.items()}
    repro_ok = all(v["equal"] for v in repro.values())
    if not repro_ok:
        RUN.write_once(out / "REPRODUCTION_FAILED.json", json.dumps(repro, indent=1, default=str),
                       man, root)
        print(json.dumps(repro, indent=1, default=str))
        raise SystemExit("saved RS-first result not reproduced: stop and explain first")

    # ---- context for every candidate (sector, SPY vs MA200) ---------------------------------
    ctx = pool[["ticker", "signal_date", "sector", "spy_above200"]]
    trc = tr.merge(ctx, on=["ticker", "signal_date"], how="left", validate="many_to_one")
    assert trc["spy_above200"].notna().all()
    trc["net_r_10"] = np.where(trc["status"] == "closed",
                               net_r_px(trc["entry"], trc["exit"], trc["stop"], 10), np.nan)

    # ---- 2) layer 2: executed trades ---------------------------------------------------------
    key = ["ticker", "date"]
    exe = ex.rename(columns={"entry_date": "date"}).assign(date=lambda d: pd.to_datetime(d["date"]))
    exe = exe.merge(trc[key + ["signal_date", "stop", "risk_pct", "reason", "days", "rs", "sector",
                               "spy_above200"]], on=key, how="left", validate="one_to_one")
    opn = pd.DataFrame(m["open_positions"])
    if len(opn):
        opn = opn.rename(columns={"entry_date": "date"}).assign(date=lambda d: pd.to_datetime(d["date"]))
        opn = opn.merge(trc[key + ["signal_date", "stop", "risk_pct", "rs", "sector", "spy_above200"]],
                        on=key, how="left", validate="one_to_one")
        fee = CFG["cost_bps"] / 1e4
        opn["entry_cost"] = opn["shares"] * opn["entry"] * (1 + fee)
        opn["equity_pnl"] = opn["shares"] * opn["mark"] - opn["entry_cost"]   # as in the curve
    exe = label(exe, "signal_date", "risk_pct")
    closed = exe[exe["status"] == "closed"].copy()
    closed["gap_through_stop"] = (closed["reason"] == "stop") & (closed["exit"] < closed["stop"] * (1 - 1e-12))
    closed["gap_extra_usd"] = np.where(closed["gap_through_stop"],
                                       closed["shares"] * (closed["exit"] - closed["stop"]), 0.0)

    # ---- reconciliation ---------------------------------------------------------------------
    total = m["final_equity"] - CFG["initial_cash"]
    closed_pnl = float(closed["net_pnl"].sum())
    open_pnl = float(opn["equity_pnl"].sum()) if len(opn) else 0.0
    recon = dict(final_equity=m["final_equity"], initial=CFG["initial_cash"], total_pnl=total,
                 closed_net_pnl=closed_pnl, closed_trades=len(closed), open_positions=len(opn),
                 open_mark_pnl_in_equity=open_pnl,
                 open_exit_fee_not_charged=float((opn["shares"] * opn["mark"] * CFG["cost_bps"] / 1e4).sum())
                 if len(opn) else 0.0,
                 difference=total - closed_pnl - open_pnl)
    recon["reconciled_to_the_cent"] = bool(abs(recon["difference"]) < 0.01)
    if not recon["reconciled_to_the_cent"]:
        raise SystemExit(f"reconciliation failed: {recon}")

    # ---- 1) layer 1: signals, non-overlapping model trades -----------------------------------
    sig = pool.copy()
    nov = sig[E.non_overlapping(sig) & (sig["trade_status"] == "closed")].copy()
    nov = label(nov, "signal_date", "risk_pct")
    nov["gap_through_stop"] = (nov["exit_reason"] == "stop") & (nov["exit"] < nov["stop"] * (1 - 1e-12))

    # ---- 3) layer 3: skipped orders ----------------------------------------------------------
    dec = pd.DataFrame(m["decisions"]).rename(columns={"day": "date"})
    dec["date"] = pd.to_datetime(dec["date"])
    dec = dec.merge(trc[key + ["status", "net_r_10", "signal_date"]], on=key, how="left",
                    validate="one_to_one")
    skipped = dec[dec["outcome"] != "entered"]
    skip_tbl = (skipped.groupby("outcome").agg(orders=("ticker", "size"),
                                               closed=("net_r_10", "count"),
                                               mean_r_if_taken=("net_r_10", "mean"),
                                               median_r_if_taken=("net_r_10", "median"))
                .reset_index())
    outside = m["skipped"].get("outside_window_or_invalid_dates", 0)

    # ---- cuts ----------------------------------------------------------------------------------
    cuts = {}
    for c in ("year", "quarter", "sector", "market", "stop_dist"):
        cuts[c] = dict(signals=grp(nov, c, "net_r_base"),
                       executed=grp(closed, c, "net_r", pnl="net_pnl"))

    # ---- 4) concentration -----------------------------------------------------------------------
    srt = closed.sort_values("net_pnl", ascending=False)
    tick = closed.groupby("ticker")["net_pnl"].sum().sort_values(ascending=False)
    ey = closed.groupby(pd.to_datetime(closed["exit_date"]).dt.year)["net_pnl"].sum()
    r = closed.sort_values("net_r", ascending=False)["net_r"]
    conc = dict(total_pnl=total, closed_pnl=closed_pnl,
                top5_trades_usd=float(srt["net_pnl"].head(5).sum()),
                top10_trades_usd=float(srt["net_pnl"].head(10).sum()),
                top5_tickers={k: round(float(v), 2) for k, v in tick.head(5).items()},
                top5_tickers_usd=float(tick.head(5).sum()),
                worst5_tickers={k: round(float(v), 2) for k, v in tick.tail(5).items()},
                pnl_by_exit_year={int(k): round(float(v), 2) for k, v in ey.items()},
                best_exit_year=int(ey.idxmax()), best_exit_year_usd=float(ey.max()),
                mean_r_all=float(r.mean()), mean_r_ex_top5=float(r.iloc[5:].mean()),
                mean_r_ex_top10=float(r.iloc[10:].mean()),
                top5_trades=srt.head(5)[["ticker", "signal_date", "net_pnl", "net_r"]]
                .assign(signal_date=lambda d: d["signal_date"].dt.date.astype(str)).to_dict("records"),
                worst5_trades=srt.tail(5)[["ticker", "signal_date", "net_pnl", "net_r"]]
                .assign(signal_date=lambda d: d["signal_date"].dt.date.astype(str)).to_dict("records"),
                winners_usd=float(closed.loc[closed["net_pnl"] > 0, "net_pnl"].sum()),
                losers_usd=float(closed.loc[closed["net_pnl"] <= 0, "net_pnl"].sum()))
    for k in ("top5_trades_usd", "top10_trades_usd", "top5_tickers_usd", "best_exit_year_usd"):
        conc[k.replace("_usd", "_residual_usd")] = total - conc[k]

    # ---- 5) execution and costs -----------------------------------------------------------------
    win = curve[(curve["date"] >= start) & (curve["date"] <= end)]
    gaps = closed[closed["gap_through_stop"]]
    execu = dict(sessions=len(win), share_sessions_with_position=float((win["open_positions"] > 0).mean() * 100),
                 mean_slots_used=float(win["open_positions"].mean()),
                 share_sessions_all_5_used=float((win["open_positions"] >= 5).mean() * 100),
                 stops=int((closed["reason"] == "stop").sum()), time_exits=int((closed["reason"] == "time").sum()),
                 gap_through_stop_trades=len(gaps), gap_pnl_usd=float(gaps["net_pnl"].sum()),
                 gap_extra_loss_vs_stop_usd=float(gaps["gap_extra_usd"].sum()),
                 gap_mean_r=float(gaps["net_r"].mean()) if len(gaps) else np.nan,
                 gap_worst_r=float(gaps["net_r"].min()) if len(gaps) else np.nan,
                 signals_gap_through_stop=int(nov["gap_through_stop"].sum()),
                 signals_gap_mean_r=float(nov.loc[nov["gap_through_stop"], "net_r_base"].mean()),
                 mean_bars_held=float(closed["days"].mean()) if "days" in closed else np.nan,
                 candidates=len(tr), entered=int((dec["outcome"] == "entered").sum()),
                 outside_window=outside, skipped=m["skipped"],
                 cash_limited_entries=m["cash_limited_entries"])
    costs = dict(signal_level={k: E.trade_stats(nov, c) for k, c in
                               (("10bps", "net_r_base"), ("25bps", "net_r_wide"), ("50bps", "net_r_stress"))},
                 portfolio_recomputed={})
    for bps in (10., 25., 50.):
        s = base if bps == 10. else summary(*replay(tr, data, start, end, bps=bps))
        costs["portfolio_recomputed"][f"{int(bps)}bps"] = {k: s[k] for k in (
            "return_pct", "cagr_pct", "max_dd_pct", "executed", "expectancy_r", "profit_factor",
            "yearly_return_pct")}

    # ---- write --------------------------------------------------------------------------------
    res = dict(plan="research/retest_diag/PLAN.md", dataset_sha256=sha, data_end=str(end.date()),
               window=[str(start.date()), str(end.date())], git=RUN._git_rev(),
               reproduction=dict(ok=repro_ok, checks=repro), portfolio=base,
               layers=dict(signals_eligible=len(pool), signals_nonoverlap_closed=len(nov),
                           signal_level=E.trade_stats(nov, "net_r_base"),
                           portfolio_candidates=len(tr), executed=base["executed"],
                           skipped_orders=len(skipped), skipped_by_reason=skip_tbl.to_dict("records"),
                           outside_window=outside),
               reconciliation=recon, concentration=conc, execution=execu, costs=costs,
               live_paper_trading="not used (historical backtest only)")
    W = lambda name, b: RUN.write_once(out / name, b, man, root)      # noqa: E731
    W("results.json", json.dumps(res, indent=1, default=str))
    tcols = ["ticker", "signal_date", "date", "exit_date", "status", "reason", "rs", "sector",
             "market", "stop_dist", "year", "quarter", "entry", "stop", "risk_pct", "exit",
             "shares", "initial_risk", "net_pnl", "net_r", "gap_through_stop", "gap_extra_usd"]
    W("executed_trades.csv", RUN.csv_bytes(closed[tcols].rename(columns={"date": "entry_date"})))
    if len(opn):
        W("open_positions.csv", RUN.csv_bytes(opn.rename(columns={"date": "entry_date"})))
    W("skipped_orders.csv", RUN.csv_bytes(skipped))
    W("reconciliation.json", json.dumps(recon, indent=1))
    for c, d in cuts.items():
        for layer, t in d.items():
            W(f"cut_{c}_{layer}.csv", RUN.csv_bytes(t))
    W("REPORT.md", report(res, cuts, skip_tbl))
    RUN.write_once(out / "manifest.json", json.dumps(dict(git=RUN._git_rev(), dataset=sha, files=man),
                                                     indent=1), {}, root)
    print(json.dumps(dict(reproduction=repro_ok, reconciliation=recon["reconciled_to_the_cent"]), indent=1))
    return 0


def report(r, cuts, skip_tbl):
    f = lambda x: RUN.md_table(x)                                      # noqa: E731
    L = ["# Retest RS-first v1 — diagnostic (historical backtest, PIT S&P 500)", "",
         "Exploratory cuts, not evidence for new rules. Live paper trading is not included.", "",
         f"Reproduction of the saved result: **{'OK' if r['reproduction']['ok'] else 'FAILED'}**. "
         f"Reconciliation to the cent: **{r['reconciliation']['reconciled_to_the_cent']}**.", "",
         "## Skipped orders", "", f(skip_tbl)]
    for c, d in cuts.items():
        L += [f"## Cut: {c}", "", "Executed portfolio trades:", "", f(d["executed"]),
              "Signals (non-overlapping model trades, 10 bps):", "", f(d["signals"])]
    L += ["## All numbers", "", "```json", json.dumps({k: v for k, v in r.items()}, indent=1,
                                                      default=str), "```"]
    return "\n".join(L)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:                 # surface the traceback as an annotation (logs not reachable)
        import traceback
        print("::error::" + traceback.format_exc().replace("%", "%25").replace("\n", "%0A"))
        raise
