"""Ten-year Long attribution, diagnostics only (PLAN.md). Requires the PR #19 research base.

Run from repo root:
 python -m research.long_diagnostic.run --dataset /path/to/unpacked/shorts10y-dataset-40152515701

No trading rule is changed. The baseline is replayed with the unchanged engine and must equal
PR #19 at 10 and 25 bps before any diagnostic is written. Price paths after an exit are
studied only as hindsight diagnostics; they are NOT trading signals and NOT a hypothetical
equity curve.

Audit changes vs the package version (rules unchanged):
- duplicate (ticker, entry) keys checked on executions too; cash identity added to the money
  reconciliation;
- costs paid and gross price P&L per trade, with an exact $ decomposition of the 10-year result;
- candidate funnel: all eligible candidates, non-overlapping model trades, portfolio entrants,
  skips by reason (hypothetical R of skipped candidates is reported separately, never added);
- MFE before the exit bar for stops, give-back for time exits, post-exit close returns,
  recovery above entry after a stop;
- top losses / winners, concentration curve, regimes incl. 2018 and 2022 with monthly detail,
  calendar-year equity return vs SPY price-only, exposure, cash-limited entries;
- dividends that a long holder would have received (not credited by the engine, diagnostic);
- coverage table, a no-look-ahead check on truncated data, provenance and charts.
"""
import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

STRATS = ("breakout", "retest")
COSTS = (10, 25)
HORIZONS = (5, 10, 20)
REGIMES = {"2017": ("2017-01-01", "2017-12-31"), "2018": ("2018-01-01", "2018-12-31"),
           "2019": ("2019-01-01", "2019-12-31"), "covid_crash": ("2020-02-19", "2020-03-23"),
           "covid_recovery": ("2020-03-24", "2020-12-31"), "2021": ("2021-01-01", "2021-12-31"),
           "bear_2022": ("2022-01-03", "2022-10-12"), "rebound_2022": ("2022-10-13", "2023-07-31"),
           "2023_2026": ("2023-08-01", "2026-12-31")}
ROOT = Path(__file__).resolve().parents[2]


def finite(x):
    """Convert scalar to JSON-safe float or None."""
    if x is None:
        return None
    try:
        v = float(x)
        return v if np.isfinite(v) else None
    except (TypeError, ValueError):
        return None


# =====================================================================
# per-trade observations
# =====================================================================
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
        ok = i1 + n < len(closes) and closes[i1] > 0
        out[f"post_exit_{n}_close_ret_pct"] = 100 * (closes[i1+n] / closes[i1] - 1) if ok else None
        # hindsight: is the close n sessions after the exit above the ENTRY price?
        out[f"post_exit_{n}_close_above_entry"] = bool(closes[i1+n] > entry) if ok else None
        out[f"post_exit_{n}_max_high_vs_exit_close_pct"] = (
            100 * (np.max(hi[i1+1:i1+n+1]) / closes[i1] - 1) if ok else None)
    return out


def dividends_held(x, entry_day, exit_day, shares):
    """Cash dividends a long holder would have received: ex-dates in (entry, exit]. The
    engine does not credit them (split-adjusted, not dividend-adjusted prices)."""
    dates = pd.DatetimeIndex(pd.to_datetime(x["dates"])).normalize()
    div = np.asarray(x.get("div", np.zeros(len(dates))), dtype=float)
    m = (dates > pd.Timestamp(entry_day)) & (dates <= pd.Timestamp(exit_day))
    return float(shares) * float(np.nansum(div[m]))


def non_overlap(trades):
    """Model trades without portfolio limits: per ticker, a candidate is taken only if it
    enters after the previous taken trade has exited (open trades block the ticker)."""
    keep, busy = [], {}
    for idx, r in trades.sort_values(["ticker", "date"], kind="stable").iterrows():
        b = busy.get(r["ticker"])
        if b is not None and (pd.isna(b) or r["date"] <= b):
            continue
        keep.append(idx)
        busy[r["ticker"]] = r["exit_date"]
    return trades.loc[keep]


def hypo_net_r(t, cost_bps):
    f = cost_bps / 10000
    return np.where(t["status"] == "closed",
                    (t["exit"] * (1 - f) - t["entry"] * (1 + f)) / (t["entry"] - t["stop"]), np.nan)


def r_stats(r):
    r = pd.Series(r, dtype=float).dropna()
    if not len(r):
        return dict(n=0)
    w, l = r[r > 0], r[r <= 0]
    return dict(n=int(len(r)), mean_r=float(r.mean()), median_r=float(r.median()),
                win_rate_pct=float(100 * (r > 0).mean()),
                avg_win_r=finite(w.mean()), avg_loss_r=finite(l.mean()),
                profit_factor_r=finite(w.sum() / -l.sum()) if l.sum() < 0 else None)


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
                avg_win_r=finite(r[pnl > 0].mean()), avg_loss_r=finite(r[pnl <= 0].mean()),
                profit_factor=float(win.sum() / (-loss.sum())) if loss.sum() < 0 else None,
                mean_win_usd=float(win.mean()) if len(win) else None,
                mean_loss_usd=float(loss.mean()) if len(loss) else None)


# =====================================================================
# money
# =====================================================================
def reconcile(curve, fills, open_positions, initial, cost_bps):
    """Portfolio marks OPEN positions without hypothetical exit fees.

    portfolio_bt.replay's open-position `unrealized_pnl` *includes* an exit fee that is not
    yet charged to equity. Reconstruct the open mark explicitly to reconcile correctly.
    Also checks the cash identity: final cash = initial + closed net P&L - open entry costs.
    """
    fee = cost_bps / 10000
    closed = float(fills["net_pnl"].sum()) if len(fills) else 0.0
    marked = sum(float(p["shares"]) * (float(p["mark"]) -
                  float(p["entry"]) * (1 + fee)) for p in open_positions)
    profit = float(curve.iloc[-1]["equity"]) - initial
    residual = profit - (closed + marked)
    out = dict(profit_usd=profit, realized_net_usd=closed,
               open_unrealized_on_curve_usd=marked,
               residual_usd=residual, matches_cent=bool(abs(residual) <= 0.01))
    if "cash" in curve:
        open_cost = sum(float(p["shares"]) * float(p["entry"]) * (1 + fee) for p in open_positions)
        cres = float(curve.iloc[-1]["cash"]) - (initial + closed - open_cost)
        out.update(cash_residual_usd=cres, cash_matches_cent=bool(abs(cres) <= 0.01))
        out["matches_cent"] = out["matches_cent"] and out["cash_matches_cent"]
    return out


def costs_paid(fills, open_positions, cost_bps):
    f = cost_bps / 10000
    closed = float((fills["shares"] * (fills["entry"] + fills["exit"]) * f).sum()) if len(fills) else 0.0
    opn = sum(float(p["shares"]) * float(p["entry"]) * f for p in open_positions)
    return dict(closed_usd=closed, open_entry_usd=opn, total_usd=closed + opn)


def decomposition(ex, open_positions, curve, initial, cost_bps):
    """Exact $ decomposition of the book's profit (sums to equity - initial)."""
    f = cost_bps / 10000
    gross = ex["shares"] * (ex["exit"] - ex["entry"])
    cost = ex["shares"] * (ex["entry"] + ex["exit"]) * f
    if not np.allclose(gross - cost, ex["net_pnl"], atol=1e-6):
        raise RuntimeError("net P&L != gross - costs for some fills")
    gap = ex["gap_extra_loss_usd"] if "gap_extra_loss_usd" in ex else 0.0
    st, tm = ex["reason"] == "stop", ex["reason"] == "time"
    open_net = sum(float(p["shares"]) * (float(p["mark"]) - float(p["entry"]) * (1 + f))
                   for p in open_positions)
    profit = float(curve.iloc[-1]["equity"]) - initial
    rows = {"gross price P&L, time exits": float(gross[tm].sum()),
            "gross price P&L, stop exits at the planned stop": float((gross[st] - gap[st]).sum()),
            "extra loss: gaps through the stop": float(gap[st].sum()),
            "costs on closed trades": -float(cost.sum()),
            "open positions at the end (mark, after entry fee)": open_net}
    other = profit - sum(rows.values())
    if abs(other) > 0.01:
        raise RuntimeError(f"decomposition residual {other}")
    rows["total = final equity - initial"] = profit
    return rows


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
    for label, group in df.groupby(key, dropna=False, observed=True):
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


def drawdown_episodes(curve, n=5):
    eq = curve.set_index("date")["equity"]
    peak = eq.cummax()
    dd = eq / peak - 1
    eps, in_dd, start = [], False, None
    for d, v in dd.items():
        if v < 0 and not in_dd:
            in_dd, start = True, d
        if in_dd and v == 0:
            seg = dd[start:d]
            eps.append(dict(start=str(start.date()), trough=str(seg.idxmin().date()),
                            recovered=str(d.date()), depth_pct=float(100 * seg.min())))
            in_dd = False
    if in_dd:
        seg = dd[start:]
        eps.append(dict(start=str(start.date()), trough=str(seg.idxmin().date()), recovered=None,
                        depth_pct=float(100 * seg.min())))
    return sorted(eps, key=lambda e: e["depth_pct"])[:n]


def window_stats(curve, ex, spy, a, b, initial):
    a = max(pd.Timestamp(a), pd.Timestamp(curve["date"].iloc[0]))      # the book starts in Nov 2017
    eq = curve.set_index("date")["equity"]
    x = eq[(eq.index >= a) & (eq.index <= b)]
    if not len(x):
        return None
    p = eq[eq.index < a]
    base = p.iloc[-1] if len(p) else initial
    c = spy["Close"]
    w = c[(c.index >= a) & (c.index <= b)]
    sp = c[c.index < a]
    sbase = sp.iloc[-1] if len(sp) else w.iloc[0]
    cv = curve[(curve["date"] >= a) & (curve["date"] <= b)]
    inv = ((cv["equity"] - cv["cash"]) / cv["equity"]).mean() * 100
    pk = np.maximum(base, x.cummax())
    e = ex[(ex["exit_date"] >= a) & (ex["exit_date"] <= b)]
    return dict(book_return_pct=float((x.iloc[-1] / base - 1) * 100),
                spy_price_return_pct=float((w.iloc[-1] / sbase - 1) * 100),
                max_dd_in_window_pct=float(100 * (x / pk - 1).min()),
                invested_pct=float(inv), exits=summarize_fills(e),
                stop_share_pct=float(100 * (e["reason"] == "stop").mean()) if len(e) else None)


# =====================================================================
# diagnostics of one book
# =====================================================================
def make_diagnostics(trades, fills, curves, book_metrics, data, spy, cost_bps, initial=10000.):
    """trades = all precomputed candidates; fills = real portfolio closed executions."""
    if trades.duplicated(["ticker", "date"]).any():
        raise ValueError("Duplicate ticker/date candidates, cannot merge by keys")
    if len(fills) and fills.duplicated(["ticker", "entry_date"]).any():
        raise ValueError("Duplicate ticker/entry executions")
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
        ex["signal_date"] = pd.to_datetime(ex["signal_date"]).dt.normalize()
        ex["exit_date"] = pd.to_datetime(ex["exit_date"]).dt.normalize()
        dctx, divs = [], []
        for r in ex.itertuples(index=False):
            if r.ticker not in data:
                raise ValueError(f"Missing price history for {r.ticker}")
            dctx.append(trade_path(data[r.ticker], r.entry_date, r.exit_date, r.entry, r.stop))
            divs.append(dividends_held(data[r.ticker], r.entry_date, r.exit_date, r.shares))
        ex = pd.concat([ex.reset_index(drop=True), pd.DataFrame(dctx)], axis=1)
        ex["dividends_not_credited_usd"] = divs
        f = cost_bps / 10000
        ex["gross_pnl"] = ex["shares"] * (ex["exit"] - ex["entry"])
        ex["costs_usd"] = ex["shares"] * (ex["entry"] + ex["exit"]) * f
        ex["cost_r"] = ex["costs_usd"] / ex["initial_risk"]
        ex["gross_r"] = ex["gross_pnl"] / ex["initial_risk"]
        ex["notional_usd"] = ex["shares"] * ex["entry"]
        ex["gap_beyond_stop"] = (ex["reason"] == "stop") & (ex["exit"] < ex["stop"])
        ex["gap_extra_loss_usd"] = np.where(ex["gap_beyond_stop"],
                                             ex["shares"] * (ex["exit"] - ex["stop"]), 0.0)
        ex["gap_extra_r"] = ex["gap_extra_loss_usd"] / ex["initial_risk"]
        ex["entry_day_stop"] = (ex["reason"] == "stop") & (ex["exit_date"] == ex["entry_date"])
        ex["exit_year"] = ex["exit_date"].dt.year.astype(int)
        ex["exit_month"] = ex["exit_date"].dt.to_period("M").astype(str)
        ex["signal_year"] = ex["signal_date"].dt.year.astype(int)
        ex["cohort"] = np.where(ex["signal_year"] < 2022, "2017-2021", "2022-2026")
        ex["rs_bucket"] = pd.cut(ex["rs"], [84, 89, 94, 99, 101],
                                 labels=["85-89", "90-94", "95-99", "100"], include_lowest=True)
        ex["risk_bucket"] = pd.cut(ex["risk_pct"], [0, 2, 4, 6, 10, 100],
                                   labels=["<2%", "2-4%", "4-6%", "6-10%", ">10%"])
        reg = spy["Close"].astype(float)
        reg.index = pd.DatetimeIndex(reg.index).normalize()
        ma200 = reg.rolling(200).mean()
        ex["spy_above200_signal"] = ex["signal_date"].map((reg > ma200).to_dict())
        ex["r_bucket"] = pd.cut(ex["net_r"], [-100, -1.5, -1, -0.5, 0, 1, 2, 3, 5, 1000],
                                labels=["<-1.5", "-1.5..-1", "-1..-0.5", "-0.5..0", "0..1", "1..2",
                                        "2..3", "3..5", ">5"])
    else:
        raise ValueError("no executions")
    gap = ex[ex["gap_beyond_stop"]]
    winners = ex.sort_values("net_pnl", ascending=False)
    total_pnl = float(ex["net_pnl"].sum())
    gw = float(ex.loc[ex["net_pnl"] > 0, "net_pnl"].sum())
    opn = book_metrics["open_positions"]

    # ---- candidate funnel (Q1)
    cand = trades.copy()
    cand["hypo_net_r"] = hypo_net_r(cand, cost_bps)
    no = non_overlap(cand)
    funnel = dict(all_candidates=dict(count=int(len(cand)), **r_stats(cand["hypo_net_r"])),
                  non_overlap_model_trades=dict(count=int(len(no)), **r_stats(no["hypo_net_r"])),
                  portfolio_closed=dict(count=int(len(ex)), **r_stats(ex["net_r"])),
                  portfolio_open_at_end=len(opn))
    decisions = pd.DataFrame(book_metrics.get("decisions", []))
    cand_dec = {}
    if len(decisions):
        decisions["day"] = pd.to_datetime(decisions["day"]).dt.normalize()
        c2 = cand[["ticker", "date", "hypo_net_r"]].copy()
        c2["date"] = pd.to_datetime(c2["date"]).dt.normalize()
        dec = decisions.merge(c2, left_on=["ticker", "day"], right_on=["ticker", "date"],
                              validate="one_to_one", how="left")
        cand_dec = {str(k): dict(count=int(len(v)), **{f"hypothetical_{a}": b for a, b in
                                                      r_stats(v["hypo_net_r"]).items()})
                    for k, v in dec.groupby("outcome")}

    # ---- exits (Q2) and post-exit (Q3)
    st, tm = ex[ex["reason"] == "stop"], ex[ex["reason"] == "time"]
    post = {}
    for name, g in (("time", tm), ("stop", st), ("top_decile_winners", winners.head(max(1, len(ex) // 10)))):
        row = dict(n=int(len(g)))
        for h in HORIZONS:
            s = pd.to_numeric(g[f"post_exit_{h}_close_ret_pct"], errors="coerce").dropna()
            a_ = g[f"post_exit_{h}_close_above_entry"].dropna().astype(bool)
            mh = pd.to_numeric(g[f"post_exit_{h}_max_high_vs_exit_close_pct"], errors="coerce").dropna()
            row[f"+{h}"] = dict(n=int(len(s)), mean_pct=finite(s.mean()), median_pct=finite(s.median()),
                                positive_pct=finite(100 * (s > 0).mean()) if len(s) else None,
                                close_above_entry_pct=finite(100 * a_.mean()) if len(a_) else None,
                                mean_max_high_after_exit_pct=finite(mh.mean()))
        post[name] = row
    stops_mfe = pd.to_numeric(st["mfe_r_excluding_exit_day"], errors="coerce")
    exits = dict(
        by_reason=group_summary(ex, "reason"),
        entry_day_stops=int(ex["entry_day_stop"].sum()),
        stops_that_were_up_1r_before_the_exit_day=int((stops_mfe >= 1).sum()),
        stops_that_were_up_0_5r_before_the_exit_day=int((stops_mfe >= 0.5).sum()),
        stops_never_above_entry_before_exit_day=int((stops_mfe.fillna(0) <= 0).sum()),
        time_exit_give_back_from_mfe_r_mean=finite((tm["mfe_r"] - tm["net_r"]).mean()),
        time_exit_mfe_r_mean=finite(tm["mfe_r"].mean()),
        time_exit_final_r_mean=finite(tm["net_r"].mean()),
        bars_held_median_stop=finite(st["bars_in_window"].median()),
        post_exit=post)

    # ---- winners / losers / concentration
    cols = ["ticker", "signal_date", "entry_date", "exit_date", "reason", "shares", "entry", "exit",
            "stop", "net_pnl", "net_r", "mfe_r", "rs"]
    conc = dict(total_closed_pnl_usd=total_pnl, gross_winning_pnl_usd=gw,
                top5_pnl_usd=float(winners["net_pnl"].head(5).sum()),
                top10_pnl_usd=float(winners["net_pnl"].head(10).sum()),
                top20_pnl_usd=float(winners["net_pnl"].head(20).sum()),
                remainder_without_top10_usd=float(winners["net_pnl"].iloc[10:].sum()),
                remainder_without_top20_usd=float(winners["net_pnl"].iloc[20:].sum()),
                mean_r_without_top10=finite(winners["net_r"].iloc[10:].mean()),
                trades_r_ge_3=int((ex["net_r"] >= 3).sum()), trades_r_ge_5=int((ex["net_r"] >= 5).sum()),
                pnl_of_r_ge_3_usd=float(ex.loc[ex["net_r"] >= 3, "net_pnl"].sum()),
                r_ge_3_by_exit_year=ex[ex["net_r"] >= 3].groupby("exit_year").size().astype(int).to_dict(),
                r_ge_3_time_exit_share_pct=finite(100 * (ex.loc[ex["net_r"] >= 3, "reason"] == "time").mean()),
                top10=winners.head(10)[cols].to_dict("records"),
                worst15=ex.sort_values("net_pnl").head(15)[cols].to_dict("records"),
                r_distribution=ex.groupby("r_bucket", observed=False).agg(
                    n=("net_r", "size"), pnl=("net_pnl", "sum")).to_dict("index"))

    # ---- calendar-year equity vs SPY; regimes (Q4)
    eq = curves.set_index("date")["equity"]
    ye = eq.groupby(eq.index.year).last()
    yp = ye.shift(1).fillna(initial)
    c = spy["Close"].copy()
    c.index = pd.DatetimeIndex(c.index).normalize()
    c = c[(c.index >= eq.index[0]) & (c.index <= eq.index[-1])]
    sy = c.groupby(c.index.year).last()
    sp = sy.shift(1)
    sp.iloc[0] = float(spy["Close"][pd.DatetimeIndex(spy.index).normalize() < eq.index[0]].iloc[-1])
    years = {int(y): dict(book_return_pct=float((ye[y] / yp[y] - 1) * 100), book_change_usd=float(ye[y] - yp[y]),
                          spy_price_return_pct=float((sy[y] / sp[y] - 1) * 100),
                          exits=summarize_fills(ex[ex["exit_year"] == y]))
             for y in ye.index}
    regimes = {k: window_stats(curves, ex, spy, pd.Timestamp(a), pd.Timestamp(b), initial)
               for k, (a, b) in REGIMES.items()}
    monthly = {}
    for y in (2018, 2022):
        m_ = eq[eq.index.year == y]
        prev = eq[eq.index < f"{y}-01-01"]
        base = prev.iloc[-1] if len(prev) else initial
        me = m_.groupby(m_.index.month).last()
        mp = me.shift(1).fillna(base)
        e = ex[ex["exit_year"] == y]
        monthly[str(y)] = {int(k): dict(book_return_pct=float((me[k] / mp[k] - 1) * 100),
                                        exits=int((e["exit_date"].dt.month == k).sum()),
                                        stops=int(((e["exit_date"].dt.month == k) & (e["reason"] == "stop")).sum()),
                                        pnl_usd=float(e.loc[e["exit_date"].dt.month == k, "net_pnl"].sum()))
                           for k in me.index}

    expo = equity_exposure(curves)
    expo.update(cash_limited_entries=int(book_metrics.get("cash_limited_entries", 0)),
                skipped=book_metrics.get("skipped", {}),
                mean_notional_pct_of_equity_at_entry=None)
    diag = dict(closed=summarize_fills(ex), funnel=funnel, candidate_decisions=cand_dec,
                exits=exits, by_exit_year=group_summary(ex, "exit_year"),
                by_signal_year=group_summary(ex, "signal_year"), by_cohort=group_summary(ex, "cohort"),
                by_rs_bucket=group_summary(ex, "rs_bucket"), by_risk_bucket=group_summary(ex, "risk_bucket"),
                by_spy_ma200_signal=group_summary(ex, "spy_above200_signal"),
                gap_through_stop=dict(trades=int(len(gap)), total_extra_loss_usd=float(gap["gap_extra_loss_usd"].sum()),
                                      mean_extra_r=finite(gap["gap_extra_r"].mean()), pnl_usd=float(gap["net_pnl"].sum()),
                                      by_year=gap.groupby("exit_year")["gap_extra_loss_usd"].sum().to_dict()),
                costs=dict(costs_paid(ex, opn, cost_bps), mean_cost_r=float(ex["cost_r"].mean()),
                           mean_gross_r=float(ex["gross_r"].mean())),
                dividends_not_credited_usd=float(ex["dividends_not_credited_usd"].sum()),
                decomposition_usd=decomposition(ex, opn, curves, initial, cost_bps),
                expectancy_r=dict(
                    n=int(len(ex)),
                    time_exits_gross_r_per_trade=float(ex.loc[ex["reason"] == "time", "gross_r"].sum() / len(ex)),
                    stops_at_planned_stop_gross_r_per_trade=float(
                        (ex.loc[ex["reason"] == "stop", "gross_r"] - ex.loc[ex["reason"] == "stop", "gap_extra_r"]).sum() / len(ex)),
                    gaps_through_stop_r_per_trade=float(ex["gap_extra_r"].sum() / len(ex)),
                    costs_r_per_trade=-float(ex["cost_r"].mean()),
                    net_r_per_trade=float(ex["net_r"].mean()),
                    win_rate=float((ex["net_r"] > 0).mean()), avg_win_r=float(ex.loc[ex["net_r"] > 0, "net_r"].mean()),
                    avg_loss_r=float(ex.loc[ex["net_r"] <= 0, "net_r"].mean()),
                    breakeven_win_rate_at_these_payoffs=float(
                        -ex.loc[ex["net_r"] <= 0, "net_r"].mean() /
                        (ex.loc[ex["net_r"] > 0, "net_r"].mean() - ex.loc[ex["net_r"] <= 0, "net_r"].mean())),
                    mean_risk_pct=float(ex["risk_pct"].mean())),
                concentration=conc, calendar_years=years, regimes=regimes, monthly_2018_2022=monthly,
                drawdown_episodes=drawdown_episodes(curves), exposure=expo,
                open_at_end=[dict(p) for p in opn],
                execution_caveats={"exit_day_h_l_sequence_known": False,
                                   "entry_day_stop_assumed_at_stop_price": True,
                                   "forward_return_labels_not_signals": True,
                                   "dividends_not_credited": True, "cash_yield_not_credited": True,
                                   "prices_split_adjusted_not_dividend_adjusted": True})
    return ex, diag


# =====================================================================
# checks around the run
# =====================================================================
def coverage(info, trades, ex, book_metrics, data):
    post_missing = {h: int(ex[f"post_exit_{h}_close_ret_pct"].isna().sum()) for h in HORIZONS}
    return dict(tickers_ever_member=info.get("tickers_ever_member"), tickers_with_prices=info.get("with_prices"),
                tickers_ever_member_without_prices=(info.get("tickers_ever_member") or 0) - (info.get("with_prices") or 0),
                candidates=int(len(trades)), candidates_open_at_data_end=int((trades["status"] == "open").sum()),
                candidates_window_incomplete=int((~trades["window_complete"].astype(bool)).sum())
                if "window_complete" in trades else None,
                portfolio_skips_missing_prices=int(book_metrics["skipped"].get("missing_prices", 0)),
                closed_trades=int(len(ex)), post_exit_window_missing=post_missing,
                closed_trades_with_dividend=int((ex["dividends_not_credited_usd"] > 0).sum()))


def no_lookahead_check(frames, spy, pit_text, trades_full, cut="2021-12-31", compare_until="2021-11-30"):
    """Detection on data truncated at `cut` must give the same candidates (entry, stop, RS)
    for entries up to `compare_until`. Exits may differ only for trades whose 20-bar window
    crosses the cut, so only the signal-side fields are compared."""
    from research.crisis import run as CR
    cutd = pd.Timestamp(cut)
    fr = {t: f[f.index <= cutd] for t, f in frames.items()}
    sp = spy[spy.index <= cutd]
    sig, data, _, _ = CR.build(fr, sp, pit_text)
    el = CR.eligible(sig, False)
    out = {}
    for st, tf in trades_full.items():
        a = CR.trades_for(el, data, st)
        k = ["ticker", "date"]
        x = a[a["date"] <= compare_until].set_index(k).sort_index()
        y = tf[tf["date"] <= compare_until].set_index(k).sort_index()
        same_keys = x.index.equals(y.index)
        num = same_keys and np.allclose(x["entry"], y["entry"]) and np.allclose(x["stop"], y["stop"]) and \
            np.allclose(x["rs"].fillna(-1), y["rs"].fillna(-1))
        out[st] = dict(candidates_truncated=int(len(x)), candidates_full=int(len(y)), identical=bool(num))
    return out


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def provenance(dataset_sha, reference):
    def git(*a):
        try:
            return subprocess.run(["git", *a], capture_output=True, text=True, cwd=ROOT).stdout.strip()
        except Exception:
            return None
    files = ["research/crisis/PREREG_CRISIS.md", "research/crisis/run.py", "portfolio_bt.py", "backtest.py",
             "research/sp1500/engine.py", "research/long_diagnostic/PLAN.md", "research/long_diagnostic/run.py"]
    return dict(commit=git("rev-parse", "HEAD"), branch=git("rev-parse", "--abbrev-ref", "HEAD"),
                dataset_sha256=dataset_sha, reference=str(reference), reference_sha256=sha(reference),
                files_sha256={f: sha(ROOT / f) for f in files if (ROOT / f).exists()},
                production_diff_vs_main=git("diff", "--stat", "origin/main", "--", "paper", "state",
                                            "trader.py", "core.py"),
                generated=datetime.now(timezone.utc).isoformat(timespec="seconds"))


# =====================================================================
# charts
# =====================================================================
def charts(out, st, curves, ex, spy, diag):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    files = []

    def save(fig, name):
        p = out / f"{st}_{name}.png"
        fig.tight_layout()
        fig.savefig(p, dpi=110)
        plt.close(fig)
        files.append(p.name)

    c10, c25 = curves[10], curves[25]
    fig, ax = plt.subplots(2, 1, figsize=(10, 6), sharex=True, gridspec_kw=dict(height_ratios=[3, 1]))
    s = spy["Close"].copy()
    s.index = pd.DatetimeIndex(s.index).normalize()
    s = s[(s.index >= c10["date"].iloc[0]) & (s.index <= c10["date"].iloc[-1])]
    ax[0].plot(c10["date"], c10["equity"], label="book, 10 bps")
    ax[0].plot(c25["date"], c25["equity"], label="book, 25 bps", alpha=.7)
    ax[0].plot(s.index, 10000 * s / s.iloc[0], label="SPY price only", color="grey", alpha=.6)
    ax[0].set_ylabel("$"); ax[0].legend(); ax[0].set_title(f"{st}: equity (start $10,000)")
    ax[1].fill_between(c10["date"], c10["drawdown_pct"], 0, color="tab:red", alpha=.4)
    ax[1].set_ylabel("DD %")
    save(fig, "equity")

    y = pd.DataFrame(diag["calendar_years"]).T
    fig, ax = plt.subplots(figsize=(10, 4))
    xi = np.arange(len(y))
    ax.bar(xi - .2, y["book_return_pct"], .4, label="book (10 bps)")
    ax.bar(xi + .2, y["spy_price_return_pct"], .4, label="SPY price", color="grey")
    ax.set_xticks(xi, y.index); ax.axhline(0, color="k", lw=.5); ax.legend()
    ax.set_title(f"{st}: calendar-year return"); ax.set_ylabel("%")
    save(fig, "years")

    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    for reason, color in (("stop", "tab:red"), ("time", "tab:blue")):
        g = ex[ex["reason"] == reason]
        ax[0].hist(g["net_r"].clip(-3, 8), bins=44, alpha=.6, label=f"{reason} ({len(g)})", color=color)
    ax[0].set_title("net R by exit reason (clipped -3..8)"); ax[0].legend()
    yy = ex.groupby(["exit_year", "reason"])["net_pnl"].sum().unstack(fill_value=0)
    yy.plot(kind="bar", ax=ax[1], color={"stop": "tab:red", "time": "tab:blue"})
    ax[1].set_title("net P&L by exit year and reason ($)"); ax[1].axhline(0, color="k", lw=.5)
    save(fig, "exits")

    fig, ax = plt.subplots(figsize=(7, 5))
    for reason, color in (("stop", "tab:red"), ("time", "tab:blue")):
        g = ex[ex["reason"] == reason]
        ax.scatter(g["mfe_r"].clip(upper=10), g["net_r"].clip(-3, 10), s=8, alpha=.5, color=color, label=reason)
    ax.plot([0, 10], [0, 10], color="k", lw=.5)
    ax.set_xlabel("MFE during the hold (R, exit bar included; clipped)"); ax.set_ylabel("net R")
    ax.legend(); ax.set_title(f"{st}: how much of the best move was kept")
    save(fig, "mfe")

    w = ex.sort_values("net_pnl", ascending=False)["net_pnl"].values
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(np.arange(1, len(w) + 1), np.cumsum(w))
    ax.axhline(0, color="k", lw=.5); ax.set_xlabel("trades ranked from the best")
    ax.set_ylabel("cumulative net P&L $"); ax.set_title(f"{st}: concentration in the best trades")
    save(fig, "concentration")

    fig, ax = plt.subplots(figsize=(8, 4))
    for i_, name in enumerate(("time", "stop")):
        g = ex[ex["reason"] == name]
        vals = [pd.to_numeric(g[f"post_exit_{h}_close_ret_pct"], errors="coerce").dropna() for h in HORIZONS]
        ax.boxplot(vals, positions=np.arange(len(HORIZONS)) * 3 + i_, widths=.8, showfliers=False)
    ax.set_xticks(np.arange(len(HORIZONS)) * 3 + .5, [f"+{h} sessions" for h in HORIZONS])
    ax.axhline(0, color="k", lw=.5); ax.set_ylabel("% close-to-close after the exit")
    ax.set_title(f"{st}: after-exit returns (left: time exits, right: stops) — hindsight only")
    save(fig, "post_exit")

    fig, ax = plt.subplots(figsize=(10, 3.5))
    inv = 100 * (c10["equity"] - c10["cash"]) / c10["equity"]
    ax.plot(c10["date"], inv.rolling(20).mean(), label="invested % (20-day mean)")
    ax2 = ax.twinx()
    ax2.plot(c10["date"], c10["open_positions"].rolling(20).mean(), color="tab:orange", alpha=.6,
             label="open positions (20-day mean)")
    ax.set_ylabel("% of equity"); ax2.set_ylabel("positions")
    ax.set_title(f"{st}: capital deployment")
    save(fig, "exposure")

    g = ex[ex["gap_beyond_stop"]].groupby("exit_year")["gap_extra_loss_usd"].sum()
    fig, ax = plt.subplots(figsize=(8, 3.5))
    ax.bar(g.index.astype(str), g.values, color="tab:red")
    ax.set_title(f"{st}: extra loss from gaps through the stop ($, by exit year)")
    save(fig, "gaps")
    return files


# =====================================================================
# report
# =====================================================================
def money(v):
    return "—" if v is None else f"${v:,.0f}"


def pct(v, d=1):
    return "—" if v is None else f"{v:+.{d}f} %"


def report(result, out):
    L = ["# Long Breakout / Retest — ten-year diagnostic (exploratory)", "",
         "Baseline C of PR #19 only (PIT S&P 500, RS ≥ 85, SPY > MA50, entry at the next open, "
         "stop = base × 0.97, exit by stop or at the close of the 20th bar, 1 % risk, 5 positions, "
         "3 a day, 20 % cap, $10,000, RS-first). The ten years were already examined in PR #19: this "
         "is **not** independent validation. Research Breakout enters at the **next-session open**, "
         "unlike `trader.py` pre-close buys.", "",
         f"Window {result['dates'][0]} → {result['dates'][1]}. Dataset SHA-256: "
         f"`{json.dumps(result['dataset_sha256'])}`.", "",
         "## 1. Baseline reproduced (fail-closed)", "",
         "| Book | Return | Max DD | Executed | Closed | Open at end | P&L reconciled to the cent | PR #19 |",
         "|---|---:|---:|---:|---:|---:|---|---|"]
    for st in STRATS:
        for bps in COSTS:
            m = result["baselines"][f"{st}_{bps}bps"]
            L.append(f"| {st} / {bps} bps per side | {m['total_return_pct']:.2f} % | {m['max_dd_pct']:.2f} % | "
                     f"{m['executed']} | {m['closed']} | {m['open_end']} | {m['reconciliation']['matches_cent']} "
                     f"(residual ${m['reconciliation']['residual_usd']:.4f}) | matched |")
    nl = result.get("no_lookahead", {})
    L += ["", f"No-look-ahead check (detection on data truncated at 2021-12-31, entries to 2021-11-30): "
          + ", ".join(f"{k}: {v['identical']} ({v['candidates_truncated']} candidates)" for k, v in nl.items()), ""]
    for st in STRATS:
        d = result["diagnostics"][st]
        L += [f"## {st.capitalize()} (10 bps book)", "", f"![equity]({st}_equity.png)", "",
              "### Where the ten-year result comes from (exact $ decomposition)", "",
              "| Component | $ |", "|---|---:|"]
        L += [f"| {k} | {v:,.2f} |" for k, v in d["decomposition_usd"].items()]
        c, co = d["closed"], d["costs"]
        L += ["", f"Closed trades {c['trades']}: win rate {c['win_rate_pct']:.1f} %, mean {c['mean_r']:+.3f} R "
              f"(avg win {c['avg_win_r']:+.2f} R, avg loss {c['avg_loss_r']:+.2f} R), PF {c['profit_factor']:.2f}. "
              f"Gross mean {co['mean_gross_r']:+.3f} R, costs {co['mean_cost_r']:.3f} R per trade. "
              f"Dividends a holder would have received but the engine does not credit: "
              f"{money(d['dividends_not_credited_usd'])}.", "",
              "### Expectancy per closed trade, in R (exact: components add up to the net mean)", "",
              "| Component | R per trade |", "|---|---:|"]
        xr = d["expectancy_r"]
        L += [f"| time exits, gross | {xr['time_exits_gross_r_per_trade']:+.3f} |",
              f"| stops at the planned stop, gross | {xr['stops_at_planned_stop_gross_r_per_trade']:+.3f} |",
              f"| gaps through the stop | {xr['gaps_through_stop_r_per_trade']:+.3f} |",
              f"| costs ({result['baselines'][st + '_10bps']['costs']['total_usd']:,.0f} $ at 10 bps) | {xr['costs_r_per_trade']:+.3f} |",
              f"| **net** | **{xr['net_r_per_trade']:+.3f}** |", "",
              f"Win rate {100 * xr['win_rate']:.1f} % against a break-even win rate of "
              f"{100 * xr['breakeven_win_rate_at_these_payoffs']:.1f} % at these payoffs (avg win {xr['avg_win_r']:+.2f} R, "
              f"avg loss {xr['avg_loss_r']:+.2f} R). Mean planned risk {xr['mean_risk_pct']:.1f} % of the entry price. "
              f"Cost sensitivity (independent full replays): {d['cost_sensitivity']['return_10bps_pct']:+.2f} % at 10 bps vs "
              f"{d['cost_sensitivity']['return_25bps_pct']:+.2f} % at 25 bps.", "",
              "### Candidate funnel (hypothetical R only for comparison, never added to P&L)", "",
              "| Set | Count | Mean R | Win % | PF (R) |", "|---|---:|---:|---:|---:|"]
        for k, v in d["funnel"].items():
            if isinstance(v, dict):
                L.append(f"| {k} | {v['count']} | {v.get('mean_r', 0):+.3f} | {v.get('win_rate_pct', 0):.1f} | "
                         f"{(v.get('profit_factor_r') or 0):.2f} |")
        L += ["", "| Portfolio decision | Count | Hypothetical mean R |", "|---|---:|---:|"]
        for k, v in d["candidate_decisions"].items():
            L.append(f"| {k} | {v['count']} | {(v.get('hypothetical_mean_r') or 0):+.3f} |")
        e = d["exits"]
        L += ["", "### Exits", "", f"![exits]({st}_exits.png)", "",
              "| Reason | Trades | Net P&L | Mean R | Win % | PF | MFE R (mean) |", "|---|---:|---:|---:|---:|---:|---:|"]
        for r_, v in e["by_reason"].items():
            L.append(f"| {r_} | {v['trades']} | {money(v['total_pnl_usd'])} | {v['mean_r']:+.3f} | "
                     f"{v['win_rate_pct']:.1f} | {(v['profit_factor'] or 0):.2f} | {(v.get('mfe_r_mean') or 0):.2f} |")
        g = d["gap_through_stop"]
        L += ["", f"- Stops on the entry day: {e['entry_day_stops']}. Stops that had been ≥ +1 R before the exit "
              f"day: {e['stops_that_were_up_1r_before_the_exit_day']}; ≥ +0.5 R: "
              f"{e['stops_that_were_up_0_5r_before_the_exit_day']}; never above entry: "
              f"{e['stops_never_above_entry_before_exit_day']}.",
              f"- Gaps through the stop: {g['trades']} trades, extra loss {money(g['total_extra_loss_usd'])} "
              f"(mean {(g['mean_extra_r'] or 0):+.2f} R each).",
              f"- Time exits: mean MFE {e['time_exit_mfe_r_mean']:.2f} R, kept {e['time_exit_final_r_mean']:+.2f} R "
              f"(gave back {e['time_exit_give_back_from_mfe_r_mean']:.2f} R from the best intraday high).", "",
              f"![mfe]({st}_mfe.png)", "", "### After the exit (hindsight, NOT a longer-hold backtest)", "",
              f"![post]({st}_post_exit.png)", "",
              "| Exit group | Horizon | n | Mean % | Median % | % positive | Close above entry % | Best high after exit (mean) |",
              "|---|---|---:|---:|---:|---:|---:|---:|"]
        for grp, v in e["post_exit"].items():
            for h in HORIZONS:
                x = v[f"+{h}"]
                L.append(f"| {grp} | +{h} | {x['n']} | {pct(x['mean_pct'], 2)} | {pct(x['median_pct'], 2)} | "
                         f"{(x['positive_pct'] or 0):.1f} | {(x['close_above_entry_pct'] or 0):.1f} | "
                         f"{pct(x['mean_max_high_after_exit_pct'], 2)} |")
        k = d["concentration"]
        L += ["", "### Rare large winners", "", f"![conc]({st}_concentration.png)", "",
              f"Closed net P&L {money(k['total_closed_pnl_usd'])}; top 5 {money(k['top5_pnl_usd'])}, top 10 "
              f"{money(k['top10_pnl_usd'])}, top 20 {money(k['top20_pnl_usd'])}. Without the top 10: "
              f"{money(k['remainder_without_top10_usd'])} (mean {(k['mean_r_without_top10'] or 0):+.3f} R) — "
              "arithmetic only, not a re-simulated portfolio. Trades ≥ 3 R: "
              f"{k['trades_r_ge_3']} ({money(k['pnl_of_r_ge_3_usd'])}), {(k['r_ge_3_time_exit_share_pct'] or 0):.0f} % "
              f"of them ended by the 20-day time exit; by exit year {k['r_ge_3_by_exit_year']}.", "",
              "| Top 10 | Entry | Exit | Reason | Net P&L | R | MFE R |", "|---|---|---|---|---:|---:|---:|"]
        for t in k["top10"]:
            L.append(f"| {t['ticker']} | {str(t['entry_date'])[:10]} | {str(t['exit_date'])[:10]} | {t['reason']} | "
                     f"{money(t['net_pnl'])} | {t['net_r']:+.2f} | {t['mfe_r']:.2f} |")
        L += ["", "| Worst 15 | Entry | Exit | Reason | Net P&L | R |", "|---|---|---|---|---:|---:|"]
        for t in k["worst15"]:
            L.append(f"| {t['ticker']} | {str(t['entry_date'])[:10]} | {str(t['exit_date'])[:10]} | {t['reason']} | "
                     f"{money(t['net_pnl'])} | {t['net_r']:+.2f} |")
        L += ["", "### Calendar years vs SPY (price only) and regimes", "", f"![years]({st}_years.png)", "",
              "| Year | Book | Book $ | SPY price | Exits | Win % | Mean R |", "|---|---:|---:|---:|---:|---:|---:|"]
        for y, v in d["calendar_years"].items():
            x = v["exits"]
            L.append(f"| {y} | {pct(v['book_return_pct'])} | {money(v['book_change_usd'])} | "
                     f"{pct(v['spy_price_return_pct'])} | {x.get('trades', 0)} | {x.get('win_rate_pct', 0):.1f} | "
                     f"{x.get('mean_r', 0):+.3f} |")
        L += ["", "| Regime | Book | SPY price | Max DD inside | Invested % | Exits | Mean R | Stop share |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for name, v in d["regimes"].items():
            if v:
                L.append(f"| {name} | {pct(v['book_return_pct'])} | {pct(v['spy_price_return_pct'])} | "
                         f"{v['max_dd_in_window_pct']:.1f} % | {v['invested_pct']:.0f} | {v['exits'].get('trades', 0)} | "
                         f"{v['exits'].get('mean_r', 0):+.3f} | {(v['stop_share_pct'] or 0):.0f} % |")
        for y, mm in d["monthly_2018_2022"].items():
            L += ["", f"{y} by month: " + "; ".join(f"{k}: {v['book_return_pct']:+.1f} % ({v['stops']}/{v['exits']} stops, "
                                                    f"{money(v['pnl_usd'])})" for k, v in mm.items())]
        x = d["exposure"]
        L += ["", "### Capital deployment", "", f"![exposure]({st}_exposure.png)", "",
              f"Invested on average {x['average_invested_pct']:.1f} % of equity; {x['avg_open_positions']:.2f} positions; "
              f"fully in cash {x['fully_cash_pct']:.1f} % of sessions; all 5 slots full {x['full_five_slots_pct']:.1f} %. "
              f"Cash-limited entries {x['cash_limited_entries']}. Skips: {x['skipped']}.", "",
              "Worst drawdowns: " + "; ".join(f"{e_['depth_pct']:.1f} % ({e_['start']} → trough {e_['trough']}, "
                                               f"recovered {e_['recovered']})" for e_ in d["drawdown_episodes"]), "",
              f"![gaps]({st}_gaps.png)", "", "### By RS, risk size and SPY MA200 at the signal (correlations)", "",
              "| Group | Value | Trades | Mean R | Win % | P&L |", "|---|---|---:|---:|---:|---:|"]
        for gname in ("by_rs_bucket", "by_risk_bucket", "by_spy_ma200_signal", "by_cohort"):
            for kk, v in d[gname].items():
                L.append(f"| {gname[3:]} | {kk} | {v['trades']} | {v['mean_r']:+.3f} | {v['win_rate_pct']:.1f} | "
                         f"{money(v['total_pnl_usd'])} |")
        L.append("")
    cv = result["coverage"]
    L += ["## Data coverage and limitations", "",
          f"- Coverage: {json.dumps(cv)}",
          "- OHLC bars cannot tell whether the exit-day high came before a stop; MFE including the exit bar is an "
          "upper bound. Entry-day stops are filled at the stop price (engine rule).",
          "- Prices are split-adjusted, not dividend-adjusted (`auto_adjust=False`). The engine credits no "
          "dividends and no cash interest; SPY comparisons are price only.",
          "- Former members without price history cannot be traded in the backtest (see coverage).",
          "- Post-exit returns are hindsight. They do not show that a longer hold is better: a different hold "
          "changes slots, capital and later choices, and would need its own pre-registered full replay.",
          "- All group splits are descriptive correlations on data already examined, not proof of cause.", ""]
    (out / "REPORT.md").write_text("\n".join(L), encoding="utf-8")


# =====================================================================
# main
# =====================================================================
def run_study(dataset, reference, out, lookahead=True):
    import portfolio_bt as pf
    from research.crisis import run as CR

    frames, spy, pit_text, dsha = CR.load(dataset)
    sig, data, cal, info = CR.build(frames, spy, pit_text)
    eligible = CR.eligible(sig, False)
    start = cal[min(260, len(cal)-1)]
    end = cal[-1]
    ref = json.loads(Path(reference).read_text(encoding="utf-8"))
    result = {"study": "Long 10Y trade-level attribution", "dataset_sha256": dsha,
              "reference_sha256": sha(reference), "data": info,
              "dates": [str(start.date()), str(end.date())], "baselines": {}, "diagnostics": {}}
    trades_all, cov = {}, {}
    for st in STRATS:
        trades = CR.trades_for(eligible, data, st)
        trades_all[st] = trades
        curves = {}
        for fee in COSTS:
            curve, executions, m = pf.replay(trades, data, start=start, end=end, cost_bps=float(fee),
                                             open_at_end="mark", record_decisions=True, **CR.CFG)
            anchor = ref["books"][f"{st}|C|full|{fee}bps"]
            mismatch = {k: (float(m[metric]) - float(anchor[k])) for k, metric in
                        (("return_pct", "return_pct"), ("max_dd_pct", "max_drawdown_pct"))}
            if any(abs(v) > 1e-6 for v in mismatch.values()) or m["executed_trades"] != anchor["trades"]:
                raise RuntimeError(f"STOP baseline mismatch {st}/{fee}bps: {mismatch}, "
                                   f"trades {m['executed_trades']} vs {anchor['trades']}")
            if len(executions) and executions.duplicated(["ticker", "entry_date"]).any():
                raise RuntimeError(f"STOP duplicated ticker-entry executions {st}/{fee}bps")
            rec = reconcile(curve, executions, m["open_positions"], CR.CFG["initial_cash"], fee)
            if not rec["matches_cent"]:
                raise RuntimeError(f"STOP money reconciliation failed for {st}/{fee}bps: {rec}")
            key = f"{st}_{fee}bps"
            result["baselines"][key] = dict(total_return_pct=m["return_pct"], cagr_pct=m["cagr_pct"],
                                            max_dd_pct=m["max_drawdown_pct"], executed=m["executed_trades"],
                                            closed=len(executions), open_end=len(m["open_positions"]),
                                            costs=costs_paid(executions, m["open_positions"], fee),
                                            reconciliation=rec, reference=anchor, mismatch=mismatch,
                                            control_matched=True)
            curves[fee] = curve
            if fee == 10:
                observed, diags = make_diagnostics(trades, executions, curve, m, data, spy, fee)
                result["diagnostics"][st] = diags
                cov[st] = coverage(info, trades, observed, m, data)
                observed.to_csv(out / f"closed_{st}.csv", index=False)
                curve.drop(columns=["holdings"], errors="ignore").to_csv(out / f"equity_{st}.csv", index=False)
                trades.drop(columns=[c for c in trades.columns if c.startswith("_")]).to_csv(
                    out / f"candidates_{st}.csv.gz", index=False)
                pd.DataFrame(m["decisions"]).to_csv(out / f"decisions_{st}.csv.gz", index=False)
        result["diagnostics"][st]["cost_sensitivity"] = dict(
            return_10bps_pct=result["baselines"][f"{st}_10bps"]["total_return_pct"],
            return_25bps_pct=result["baselines"][f"{st}_25bps"]["total_return_pct"],
            difference_pct_points=result["baselines"][f"{st}_10bps"]["total_return_pct"]
            - result["baselines"][f"{st}_25bps"]["total_return_pct"])
        result["diagnostics"][st]["charts"] = charts(out, st, curves, observed, spy, result["diagnostics"][st])
        (out / f"diagnostics_{st}.json").write_text(json.dumps(result["diagnostics"][st], indent=2, default=str))
    result["coverage"] = cov
    if lookahead:
        result["no_lookahead"] = no_lookahead_check(frames, spy, pit_text, trades_all)
        if not all(v["identical"] for v in result["no_lookahead"].values()):
            raise RuntimeError(f"STOP look-ahead check failed: {result['no_lookahead']}")
    (out / "reconciliation.json").write_text(json.dumps({k: v["reconciliation"] for k, v in result["baselines"].items()},
                                                        indent=2, default=str))
    (out / "provenance.json").write_text(json.dumps(provenance(dsha, reference), indent=2, default=str))
    pd.DataFrame([dict(strategy=k, **{a: (json.dumps(b) if isinstance(b, dict) else b) for a, b in v.items()})
                  for k, v in cov.items()]).to_csv(out / "coverage.csv", index=False)
    (out / "results.json").write_text(json.dumps(result, indent=2, default=str))
    report(result, out)
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--reference", default="research/results/crisis/runs/2026-10-25T0255Z/results.json")
    ap.add_argument("--out", default="research/results/long_diagnostic/runs")
    ap.add_argument("--no-lookahead-check", action="store_true")
    args = ap.parse_args(argv)
    path = Path(args.out) / datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    path.mkdir(parents=True, exist_ok=False)
    result = run_study(args.dataset, args.reference, path, lookahead=not args.no_lookahead_check)
    print(json.dumps({"path": str(path), "matched": {k: {a: v[a] for a in ("total_return_pct", "max_dd_pct",
                                                                           "executed", "control_matched")}
                                                     for k, v in result["baselines"].items()},
                      "no_lookahead": result.get("no_lookahead")}, indent=2, default=str))


if __name__ == "__main__":
    main()
