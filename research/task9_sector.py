"""
Task 9 — sector concentration study for the Retest RS-first portfolio.

Runs on real data (Yahoo, 3 years, today's S&P 500 + current GICS sectors) and writes
research/results/task9/:
  REPORT.md            tables for every configuration
  summary.csv          one row per configuration (return, CAGR, max DD, trades, exposure, ...)
  sector_breakdown.csv position-days / value share per sector and configuration
  rejections.csv       skipped candidates by reason (and sector-limit rejections by sector)
  montecarlo.csv       tie-break robustness (random order among equal-RS candidates)
  sector_map.csv       the sector snapshot used (with as-of date)
  meta.json            data window, counts, parameters

Frozen strategy parameters (app defaults; NOT tuned here): Retest, RS >= 85, stop buffer 3 %,
hold 20 days, market filter SPY > MA50, min volume off, max risk off, lookback 3.
Portfolio: $10,000, risk 1 %, max 20 % per position, 3 new entries/day, 10 bps per side,
open positions marked to market at the end (Task 6 engine).
Varied: sector limit (none, 1, 2, 3) x max positions (5, 10, 20) x entry (next open, close).
RS-first: same-day candidates ordered by RS descending (ties: ticker), research-only —
the production ranking, setup detection and the bot are untouched.

Usage:  python research/task9_sector.py [--mc 100] [--out research/results/task9]
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import backtest as bt          # noqa: E402
import core                    # noqa: E402
import portfolio_bt as pf      # noqa: E402
import sector_exposure as se   # noqa: E402

FROZEN = dict(mode="retest", min_rs=85, stop_buf=3.0, hold=20, market="ma50", min_vol=0.0,
              max_risk=0.0, lookback=3)
PORTFOLIO = dict(initial_cash=10000., risk_fraction=.01, max_position_fraction=.20,
                 max_new_per_day=3, cost_bps=10.)
LIMITS = [None, 1, 2, 3]
POSITIONS = [5, 10, 20]
ENTRIES = ["open", "close"]


def rs_first(trades: pd.DataFrame, rng=None) -> pd.DataFrame:
    """Same-day candidates by RS descending; ties by ticker, or randomly if rng is given."""
    t = trades.copy()
    t["_tie"] = rng.random(len(t)) if rng is not None else t["ticker"].rank(method="first")
    return (t.sort_values(["date", "rs", "_tie"], ascending=[True, False, True], kind="stable")
             .drop(columns="_tie").reset_index(drop=True))


def run_one(trades, data, smap, max_pos, limit):
    curve, ex, m = pf.replay(trades, data, max_positions=max_pos, sector_map=smap,
                             max_per_sector=limit, open_at_end="mark", **PORTFOLIO)
    exp = se.daily_exposure(ex, m["open_positions"], data, smap, days=curve["date"])
    conc = se.concentration_metrics(exp, len(curve))
    down = se.downside_metrics(curve)
    return curve, ex, m, exp, conc, down


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mc", type=int, default=int(os.getenv("MC_RUNS", "100")))
    ap.add_argument("--out", default=str(ROOT / "research" / "results" / "task9"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    # ---- data
    universe = core.get_sp500()
    smap = se.sector_map_from_universe(universe)
    se.save_sector_snapshot(smap, out / "sector_map.csv")
    tickers = tuple(universe["ticker"])
    prices = core.get_prices(tickers + ("SPY",), period="3y")
    frames = {}
    for t in tickers:
        df = core._frame_for(prices, t)
        if df is not None and len(df):
            frames[t] = df
    sig, data = bt.find_signals(frames, lookback=FROZEN["lookback"], modes=[FROZEN["mode"]])
    spy = core._frame_for(prices, "SPY")
    market_ok = core.regime_mask(core.market_regime(spy), FROZEN["market"])
    print(f"data: {len(frames)} tickers, {len(sig)} raw retest signals, {time.time()-t0:.0f}s")

    meta = dict(generated=pd.Timestamp.now(tz="America/New_York").isoformat(timespec="minutes"),
                git_sha=subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                                       capture_output=True, text=True).stdout.strip(),
                tickers_with_data=len(frames), universe=len(universe),
                unknown_sector=sum(v == se.UNKNOWN for v in smap.values()),
                sectors=sorted(set(smap.values())), raw_signals=len(sig),
                signal_window=[str(pd.Timestamp(sig["date"].min()).date()),
                               str(pd.Timestamp(sig["date"].max()).date())] if len(sig) else None,
                frozen=FROZEN, portfolio=PORTFOLIO, limits=LIMITS, positions=POSITIONS,
                entries=ENTRIES, mc_runs=args.mc,
                ranking="RS descending within each day, ties by ticker (MC: random ties)")

    summary, breakdown, rejections, mc_rows = [], [], [], []
    for entry in ENTRIES:
        raw = bt.simulate(sig, data, FROZEN["mode"], hold=FROZEN["hold"],
                          stop_buf=FROZEN["stop_buf"], min_rs=FROZEN["min_rs"],
                          min_vol=FROZEN["min_vol"], max_risk=FROZEN["max_risk"],
                          market_ok=market_ok, entry_at=entry, one_per_ticker=False,
                          include_open=True).assign(mode=FROZEN["mode"])
        sub = {t: data[t] for t in raw["ticker"].unique()}
        ranked = rs_first(raw)
        meta[f"candidates_{entry}"] = len(raw)
        for max_pos in POSITIONS:
            for lim in LIMITS:
                label = "none" if lim is None else str(lim)
                curve, ex, m, exp, conc, down = run_one(ranked, sub, smap, max_pos, lim)
                closed = ex[ex["status"] == "closed"] if len(ex) else ex
                row = dict(entry=entry, max_positions=max_pos, sector_limit=label,
                           return_pct=m["return_pct"], cagr_pct=m["cagr_pct"],
                           max_drawdown_pct=m["max_drawdown_pct"],
                           executed=m["executed_trades"], closed=m["closed_trades"],
                           open_end=m["open_positions_end"], candidates=m["candidate_trades"],
                           rejected_sector=m["skipped"].get("sector_limit", 0),
                           rejected_positions=m["skipped"].get("positions", 0),
                           rejected_daily=m["skipped"].get("daily_entries", 0),
                           rejected_capital=m["skipped"].get("capital_or_risk", 0),
                           rejected_ticker_open=m["skipped"].get("ticker_open", 0),
                           avg_net_r=float(closed["net_r"].mean()) if len(closed) else np.nan,
                           win_rate_pct=100 * float((closed["net_pnl"] > 0).mean())
                           if len(closed) else np.nan,
                           cash_limited=m["cash_limited_entries"], **conc,
                           **{k: v for k, v in down.items() if k != "max_drawdown_pct"})
                summary.append(row)
                b = se.sector_breakdown(exp).assign(entry=entry, max_positions=max_pos,
                                                    sector_limit=label)
                breakdown.append(b)
                for reason, n in m["skipped"].items():
                    rejections.append(dict(entry=entry, max_positions=max_pos,
                                           sector_limit=label, reason=reason, sector="",
                                           count=n))
                for sec, n in m["sector_limit_rejections"].items():
                    rejections.append(dict(entry=entry, max_positions=max_pos,
                                           sector_limit=label, reason="sector_limit_by_sector",
                                           sector=sec, count=n))
                print(f"{entry:5s} pos={max_pos:2d} limit={label:4s} "
                      f"ret={m['return_pct']:+7.1f}% dd={m['max_drawdown_pct']:6.1f}% "
                      f"trades={m['executed_trades']:4d} maxSame={conc['max_same_sector']}")
        # ---- tie-break robustness (Monte Carlo) for the bot's entry (next open) only
        if entry == "open" and args.mc > 0:
            for max_pos in POSITIONS:
                for lim in LIMITS:
                    label = "none" if lim is None else str(lim)
                    rng = np.random.default_rng(9000 + max_pos)
                    vals = []
                    for _ in range(args.mc):
                        c, e, mm = pf.replay(rs_first(raw, rng), sub, max_positions=max_pos,
                                             sector_map=smap, max_per_sector=lim,
                                             open_at_end="mark", **PORTFOLIO)
                        ee = se.daily_exposure(e, mm["open_positions"], sub, smap,
                                               days=c["date"])
                        cc = se.concentration_metrics(ee, len(c))
                        vals.append((mm["return_pct"], mm["max_drawdown_pct"],
                                     cc["max_same_sector"], cc["days_ge2_same_sector_pct"]))
                    v = np.array(vals)
                    q = lambda k, p: float(np.percentile(v[:, k], p))
                    mc_rows.append(dict(entry=entry, max_positions=max_pos, sector_limit=label,
                                        runs=args.mc,
                                        return_p5=q(0, 5), return_median=q(0, 50),
                                        return_p95=q(0, 95),
                                        maxdd_p5=q(1, 5), maxdd_median=q(1, 50),
                                        maxdd_p95=q(1, 95),
                                        max_same_sector_median=q(2, 50),
                                        days_ge2_same_pct_median=q(3, 50)))
                    print(f"MC open pos={max_pos} limit={label}: done")

    S = pd.DataFrame(summary)
    S.to_csv(out / "summary.csv", index=False)
    pd.concat(breakdown, ignore_index=True).to_csv(out / "sector_breakdown.csv", index=False)
    pd.DataFrame(rejections).to_csv(out / "rejections.csv", index=False)
    M = pd.DataFrame(mc_rows)
    M.to_csv(out / "montecarlo.csv", index=False)
    meta["runtime_sec"] = round(time.time() - t0)
    (out / "meta.json").write_text(json.dumps(meta, indent=2, default=str))
    write_report(out, S, M, meta)
    print(f"done in {meta['runtime_sec']}s -> {out}")


def _md(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in df.itertuples(index=False):
        lines.append("| " + " | ".join(f"{v:.2f}" if isinstance(v, float) else str(v)
                                       for v in r) + " |")
    return "\n".join(lines)


def write_report(out, S, M, meta):
    keep = ["sector_limit", "return_pct", "cagr_pct", "max_drawdown_pct", "worst_20d_pct",
            "ulcer_index", "executed", "avg_net_r", "rejected_sector", "max_same_sector",
            "days_ge2_same_sector_pct", "avg_top_sector_weight_pct", "avg_hhi"]
    parts = [f"# Task 9 — sector limits, Retest RS-first portfolio (auto-generated)\n",
             f"Generated {meta['generated']} from commit `{meta['git_sha']}`. "
             f"Signals {meta['signal_window']}, {meta['tickers_with_data']} tickers, "
             f"{meta['raw_signals']} raw retest signals; sector unknown for "
             f"{meta['unknown_sector']} tickers.\n",
             "Frozen: " + json.dumps(meta["frozen"]) + "  \nPortfolio: "
             + json.dumps(meta["portfolio"]) + "\n",
             "Sector source: current Wikipedia GICS snapshot (not point-in-time); "
             "universe: today's S&P 500 (survivorship).\n"]
    for entry in ENTRIES:
        for pos in POSITIONS:
            t = S[(S["entry"] == entry) & (S["max_positions"] == pos)][keep]
            parts.append(f"\n## Entry: {entry} · max positions {pos}\n\n{_md(t)}\n")
    if len(M):
        parts.append("\n## Tie-break Monte Carlo (next-open entry)\n\n" + _md(
            M[["max_positions", "sector_limit", "runs", "return_p5", "return_median",
               "return_p95", "maxdd_p5", "maxdd_median", "maxdd_p95",
               "max_same_sector_median", "days_ge2_same_pct_median"]]) + "\n")
    (out / "REPORT.md").write_text("\n".join(parts))


if __name__ == "__main__":
    main()
