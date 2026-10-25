"""Ten-year Long attribution, diagnostics only. Requires stock-screener PR #19 research base.

Run from repo root:
 python -m research.long_diagnostic.run --dataset /path/to/unpacked/shorts10y-dataset-40152515701

No trading rules are changed. Actual OHLC paths are only studied after simulated exits;
look-ahead statistics here are explanatory diagnostics, NOT trading signals.
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

STRATS = ("breakout", "retest")
COSTS = (10, 25)
HORIZONS = (5, 10, 20)


def finite(x):
    """Convert scalar to JSON-safe float or None."""
    if x is None:
        return None
    try:
        v = float(x)
        return v if np.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def trade_path(x, entry_day, exit_day, entry, stop, horizons=HORIZONS):
    """Observations only, using the stock's bars. Exit-day H/L bounds lack intraday ordering."""
    dates = pd.DatetimeIndex(pd.to_datetime(x["dates"])).normalize()
    d0, d1 = pd.Timestamp(entry_day).normalize(), pd.Timestamp(exit_day).normalize()
    where0, where1 = np.flatnonzero(dates == d0), np.flatnonzero(dates == d1)
    if len(where0) != 1 or len(where1) != 1 or where1[0] < where0[0]:
        raise ValueError(f"Missing/invalid entry-exit bar: {d0}, {d1}")
    i0, i1 = int(where0[0]), int(where1[0])
    risk = float(entry) - float(stop)
    if risk <= 0:
        raise ValueError("Invalid entry-stop risk")
    hi = np.asarray(x["H"], dtype=float)
    lo = np.asarray(x["L"], dtype=float)
    closes = np.asarray(x["C"], dtype=float)
    if not np.isfinite(hi[i0:i1+1]).all() or not np.isfinite(lo[i0:i1+1]).all():
        raise ValueError("Nonfinite OHLC during holding period")
    out = dict(
        bars_in_window=i1 - i0 + 1,
        mfe_pct=100 * (np.max(hi[i0:i1+1]) / entry - 1),
        mae_pct=100 * (np.min(lo[i0:i1+1]) / entry - 1),
        mfe_r=(np.max(hi[i0:i1+1]) - entry) / risk,
        mae_r=(np.min(lo[i0:i1+1]) - entry) / risk,
        # Exclude exit-day high to form a safer bound for trades stopped intraday.
        mfe_r_excluding_exit_day=((np.max(hi[i0:i1]) - entry) / risk
                                  if i1 > i0 else None),
        close_at_exit_bar=float(closes[i1]),
        exit_bar_intraday_order_unknown=True,
    )
    for n in horizons:
        k = f"post_exit_{n}_close_ret_pct"
        out[k] = (100 * (closes[i1+n] / closes[i1] - 1)
                  if i1 + n < len(closes) and closes[i1] > 0 else None)
    return out


def summarize_fills(df):
    if len(df) == 0:
        return dict(trades=0)
    pnl = pd.to_numeric(df["net_pnl"], errors="raise")
    r = pd.to_numeric(df["net_r"], errors="raise")
    win = pnl[pnl > 0]
    loss = pnl[pnl <= 0]
    return dict(trades=int(len(df)), total_pnl_usd=float(pnl.sum()),
                winning_pnl_usd=float(win.sum()), losing_pnl_usd=float(loss.sum()),
                win_rate_pct=float(100 * (pnl > 0).mean()),
                mean_r=float(r.mean()), median_r=float(r.median()),
                profit_factor=float(win.sum() / (-loss.sum())) if loss.sum() < 0 else None,
                mean_win_usd=float(win.mean()) if len(win) else None,
                mean_loss_usd=float(loss.mean()) if len(loss) else None)


def reconcile(curve, fills, open_positions, initial, cost_bps):
    """Portfolio marks OPEN positions without hypothetical exit fees.

    portfolio_bt.replay's open-position `unrealized_pnl` *includes* an exit fee that is not
    yet charged to equity. Reconstruct the open mark explicitly to reconcile correctly.
    """
    fee = cost_bps / 10000
    closed = float(fills["net_pnl"].sum()) if len(fills) else 0.0
    marked = sum(float(p["shares"]) * (float(p["mark"]) -
                  float(p["entry"]) * (1 + fee)) for p in open_positions)
    profit = float(curve.iloc[-1]["equity"]) - initial
    residual = profit - (closed + marked)
    return dict(profit_usd=profit, realized_net_usd=closed,
                open_unrealized_on_curve_usd=marked,
                residual_usd=residual, matches_cent=bool(abs(residual) <= 0.01))


def equity_exposure(curve):
    df = curve.copy()
    total = pd.to_numeric(df["equity"], errors="raise")
    cash = pd.to_numeric(df["cash"], errors="raise")
    if (total <= 0).any():
        raise ValueError("Nonpositive equity: exposure fraction undefined")
    inv = (total - cash) / total
    n = pd.to_numeric(df["open_positions"], errors="raise")
    return dict(days=int(len(df)), average_invested_pct=float(100 * inv.mean()),
                avg_open_positions=float(n.mean()), fully_cash_pct=float(100 * (n == 0).mean()),
                full_five_slots_pct=float(100 * (n >= 5).mean()),
                mean_cash_pct=float(100 * (cash / total).mean()))


def group_summary(df, key):
    out = {}
    for label, group in df.groupby(key, dropna=False):
        val = str(label)
        row = summarize_fills(group)
        for k in ("mfe_r", "mae_r", "mfe_r_excluding_exit_day", *
                  [f"post_exit_{h}_close_ret_pct" for h in HORIZONS]):
            if k in group:
                s = pd.to_numeric(group[k], errors="coerce").dropna()
                row[k+"_mean"] = finite(s.mean()) if len(s) else None
                row[k+"_n"] = int(len(s))
                if k.startswith("post_exit_"):
                    row[k+"_positive_pct"] = finite(100 * (s > 0).mean()) if len(s) else None
        out[val] = row
    return out


def make_diagnostics(trades, fills, curves, book_metrics, data, spy, cost_bps):
    """trades = all precomputed candidates; fills = real portfolio closed executions."""
    if trades.duplicated(["ticker", "date"]).any():
        raise ValueError("Duplicate ticker/date candidates, cannot merge by keys")
    ex = fills.copy()
    if len(ex):
        t = trades[["ticker", "date", "signal_date", "reason", "rs", "stop", "risk_pct"]].copy()
        ex["entry_date"] = pd.to_datetime(ex["entry_date"]).dt.normalize()
        t["date"] = pd.to_datetime(t["date"]).dt.normalize()
        ex = ex.merge(t, left_on=["ticker", "entry_date"], right_on=["ticker", "date"],
                      how="left", validate="one_to_one", indicator=True)
        if not ex["_merge"].eq("both").all():
            raise ValueError("Execution with no matching precomputed candidate")
        ex = ex.drop(columns=["_merge", "date"])
        ex["signal_date"] = pd.to_datetime(ex["signal_date"])
        ex["exit_date"] = pd.to_datetime(ex["exit_date"]).dt.normalize()
        dctx = []
        for r in ex.itertuples(index=False):
            if r.ticker not in data:
                raise ValueError(f"Missing price history for {r.ticker}")
            dctx.append(trade_path(data[r.ticker], r.entry_date, r.exit_date,
                                   r.entry, r.stop))
        ex = pd.concat([ex.reset_index(drop=True), pd.DataFrame(dctx)], axis=1)
        ex["gap_beyond_stop"] = (ex["reason"] == "stop") & (ex["exit"] < ex["stop"])
        ex["gap_extra_loss_usd"] = np.where(ex["gap_beyond_stop"],
                                             ex["shares"] * (ex["exit"] - ex["stop"]), 0.0)
        ex["exit_year"] = ex["exit_date"].dt.year.astype(int)
        ex["signal_year"] = ex["signal_date"].dt.year.astype(int)
        ex["cohort"] = np.where(ex["signal_year"] < 2022, "2017-2021", "2022-2026")
        ex["rs_bucket"] = pd.cut(ex["rs"], [84, 89, 94, 99, 101],
                                  labels=["85-89", "90-94", "95-99", "100"], include_lowest=True)
        reg = spy["Close"].astype(float)
        ma200 = reg.rolling(200).mean()
        lookup = (reg > ma200).to_dict()
        ex["spy_above200_signal"] = ex["signal_date"].map(lookup)
    else:
        ex = pd.DataFrame(columns=["ticker", "net_pnl", "net_r", "reason", "exit_year",
                                   "signal_year", "cohort", "rs_bucket"])
    gap = ex[ex.get("gap_beyond_stop",pd.Series(False,index=ex.index))] if len(ex) else ex
    winners = ex.sort_values("net_pnl", ascending=False) if len(ex) else ex
    total_pnl = float(ex["net_pnl"].sum()) if len(ex) else 0
    diag = dict(closed=summarize_fills(ex), by_exit_reason=group_summary(ex, "reason"),
                by_exit_year=group_summary(ex, "exit_year"),
                by_signal_year=group_summary(ex, "signal_year"),
                by_cohort=group_summary(ex, "cohort"),
                by_rs_bucket=group_summary(ex, "rs_bucket"),
                by_spy_ma200_signal=group_summary(ex, "spy_above200_signal") if len(ex) else {},
                gap_through_stop=dict(trades=len(gap), total_extra_loss_usd=float(gap["gap_extra_loss_usd"].sum()) if len(gap) else 0,
                                      pnl_usd=float(gap["net_pnl"].sum()) if len(gap) else 0),
                concentration=dict(total_closed_pnl_usd=total_pnl,
                                   top5_pnl_usd=float(winners["net_pnl"].head(5).sum()) if len(ex) else 0,
                                   top10_pnl_usd=float(winners["net_pnl"].head(10).sum()) if len(ex) else 0,
                                   remainder_without_top10_usd=float(winners["net_pnl"].iloc[10:].sum()) if len(ex) else 0,
                                   mean_r_without_top10=float(winners["net_r"].iloc[10:].mean()) if len(ex)>10 else None),
                exposure=equity_exposure(curves),
                skipped=book_metrics.get("skipped",{}),
                execution_caveats={"exit_day_h_l_sequence_known":False,
                                   "forward_return_labels_not_signals":True,
                                   "corporate_actions_need_independent_audit":True})
    # Hypothetical skipped R is a diagnostic only (these were not actual positions).
    decisions = pd.DataFrame(book_metrics.get("decisions", []))
    if len(decisions):
        eligible_return = trades[["ticker", "date", "entry", "exit", "stop", "status"]].copy()
        eligible_return["date"] = pd.to_datetime(eligible_return["date"]).dt.normalize()
        eligible_return["hypo_net_r"] = np.where(eligible_return["status"] == "closed",
              (eligible_return["exit"]*(1-cost_bps/10000) -
               eligible_return["entry"]*(1+cost_bps/10000)) /
              (eligible_return["entry"]-eligible_return["stop"]), np.nan)
        decisions["day"] = pd.to_datetime(decisions["day"]).dt.normalize()
        dec = decisions.merge(eligible_return[["ticker", "date", "hypo_net_r"]],
                              left_on=["ticker", "day"],right_on=["ticker", "date"],
                              validate="one_to_one",how="left")
        diag["candidate_decisions"] = {str(k):{"count":int(len(v)),"hypothetical_closed_mean_r":finite(v["hypo_net_r"].mean())}
                                       for k,v in dec.groupby("outcome")}
    return ex, diag


def run_study(dataset, reference, out):
    import portfolio_bt as pf
    from research.crisis import run as CR

    frames, spy, pit_text, sha = CR.load(dataset)
    sig, data, cal, info = CR.build(frames, spy, pit_text)
    eligible = CR.eligible(sig, False)
    start = cal[min(260, len(cal)-1)]
    end = cal[-1]
    ref = json.loads(Path(reference).read_text(encoding="utf-8"))
    result = {"study":"Long 10Y trade-level attribution", "dataset_sha256":sha,
              "reference_sha256": hashlib.sha256(Path(reference).read_bytes()).hexdigest(),
              "data":info,"dates":[str(start.date()),str(end.date())],
              "baselines":{}, "diagnostics":{}}
    for st in STRATS:
        trades=CR.trades_for(eligible, data, st)
        for fee in COSTS:
            curve, executions, m = pf.replay(trades, data, start=start, end=end,
                     cost_bps=float(fee), open_at_end="mark",record_decisions=(fee == 10),**CR.CFG)
            anchor = ref["books"][f"{st}|C|full|{fee}bps"]
            mismatch = {k: (float(m[metric])-float(anchor[k])) for k,metric in
                      (("return_pct","return_pct"),("max_dd_pct","max_drawdown_pct"))}
            if any(abs(v)>1e-6 for v in mismatch.values()) or m["executed_trades"]!=anchor["trades"]:
                raise RuntimeError(f"STOP baseline mismatch {st}/{fee}bps: {mismatch}, "
                                   f"trades {m['executed_trades']} vs {anchor['trades']}")
            rec = reconcile(curve, executions, m["open_positions"], CR.CFG["initial_cash"],fee)
            if not rec["matches_cent"]:
                raise RuntimeError(f"STOP money reconciliation failed for {st}/{fee}bps: {rec}")
            key=f"{st}_{fee}bps"
            result["baselines"][key]=dict(total_return_pct=m["return_pct"],
                        max_dd_pct=m["max_drawdown_pct"],executed=m["executed_trades"],
                        closed=len(executions),open_end=len(m["open_positions"]),
                        reconciliation=rec, control_matched=True)
            if fee==10:
                observed,diags=make_diagnostics(trades, executions, curve, m, data, spy,fee)
                result["diagnostics"][st]=diags
                observed.to_csv(out/f"closed_{st}.csv",index=False)
                curve.to_csv(out/f"equity_{st}.csv",index=False)
                (out/f"diagnostics_{st}.json").write_text(json.dumps(diags,indent=2,default=str))
    (out/"results.json").write_text(json.dumps(result,indent=2,default=str))
    lines=["# Long Breakout / Retest — ten-year diagnostic (exploratory)", "",
           "Baseline C of PR #19 only. Past ten years were already examined; this is NOT independent validation.",
           "Research Breakout enters at **next-session open**, unlike `trader.py` pre-close buys.", "",
           "## Baseline reproduced", "",
           "| Book | Return | Max DD | Executed | Closed | Reconciled |", "|---|---:|---:|---:|---:|---|"]
    for st in STRATS:
        for bps in COSTS:
            m=result["baselines"][f"{st}_{bps}bps"]
            lines.append(f"| {st} / {bps} bps per side | {m['total_return_pct']:.2f}% | "
                         f"{m['max_dd_pct']:.2f}% | {m['executed']} | {m['closed']} | "
                         f"{m['reconciliation']['matches_cent']} |")
    for st in STRATS:
        d=result["diagnostics"][st]
        lines.extend(["",f"## {st}: where gains and losses came from", "",
                      f"Average capital invested: {d['exposure']['average_invested_pct']:.1f}%.",
                      f"Closed P&L: ${d['closed']['total_pnl_usd']:,.2f} across "
                      f"{d['closed']['trades']} closed trades.",
                      f"Top 10 winners: ${d['concentration']['top10_pnl_usd']:,.2f}; "
                      f"residual closed P&L without them: "
                      f"${d['concentration']['remainder_without_top10_usd']:,.2f} "
                      f"(arithmetic only, NOT a re-simulated portfolio).", "",
                      "### Exit reasons", "",
                      "| Reason | Trades | Closed P&L | Mean R | PF |", "|---|---:|---:|---:|---:|"])
        for reason,vals in d['by_exit_reason'].items():
            lines.append(f"| {reason} | {vals['trades']} | ${vals['total_pnl_usd']:,.2f} | "
                         f"{vals['mean_r']:+.3f} | {vals['profit_factor']} |")
        lines.extend(["", f"Stop gaps: {d['gap_through_stop']['trades']} positions; "
                      f"additional loss beyond stop "
                      f"${d['gap_through_stop']['total_extra_loss_usd']:,.2f}.", "",
                      "### By signal cohort", "",
                      "| Cohort | Trades | P&L | Avg R |", "|---|---:|---:|---:|"])
        for k, v in d['by_cohort'].items():
            lines.append(f"| {k} | {v['trades']} | ${v['total_pnl_usd']:,.2f} | {v['mean_r']:+.3f} |")
        lines.extend(["", "### Candidate decisions", "", "```json",
                      json.dumps(d.get('candidate_decisions', {}),indent=2), "```", "",
                      "### Post-exit close returns (DIAGNOSTIC ONLY)",
                      "The `diagnostics_*.json` report gives means and counts for 5/10/20 bars "
                      "after each exit, stratified by stop vs time. These future returns "
                      "do **not** establish that holding longer would outperform."])
    lines.extend(["", "## Data and execution limitations", "",
                  "- OHLC bars cannot determine whether exit-day high occurred before a stop. "
                  "MFE/MAE on the exit bar are upper/lower observational bounds.",
                  "- `auto_adjust=False` price data require separate checks for historical "
                  "splits/dividend treatment and delisted equities. Portfolio has not "
                  "credited cash interest or long stock dividends.",
                  "- Static 20-bar rule was *not changed*. Comparing it to another rule "
                  "requires a new prospective hypothesis and fully rerun portfolio with "
                  "unchanged risk settings.",
                  "- Results are descriptive correlations, not proof that an observed "
                  "phenomenon causes low returns.", ""])
    (out/"REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    return result


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset",required=True)
    ap.add_argument("--reference",default="research/results/crisis/runs/2026-10-25T0255Z/results.json")
    ap.add_argument("--out",default="research/results/long_diagnostic/runs")
    args=ap.parse_args(argv)
    path=Path(args.out)/datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    path.mkdir(parents=True,exist_ok=False)
    result=run_study(args.dataset,args.reference,path)
    print(json.dumps({"path":str(path),"matched":result["baselines"],
                      "diagnostics_files":list(result["diagnostics"])},indent=2,default=str))

if __name__=="__main__":
    main()
