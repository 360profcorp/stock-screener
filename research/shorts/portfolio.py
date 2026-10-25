"""Short-only portfolio replay of precomputed model trades (PREREG_SHORTS §5).

Each candidate is an engine model trade (research.sp1500.engine.model_trade for direction
"short"): entry at the next open, stop / time exit already resolved from the bars. The book
decides only WHICH trades it can take and how many shares:

  per session d (calendar of all tickers):
    1. pre-open entries (entry_date == d), weakest RS first, then ticker: skipped if the ticker
       is already held, 5 positions are open, or 3 entries were made today; size =
       floor(min(1 % of equity at the previous close / (stop - entry),
                 20 % of that equity / entry)); total short notional at entry prices may not
       exceed that equity (no leverage beyond 1x);
    2. exits due today (stop / time): buy back at the trade's exit price; slippage on both
       sides, borrow fee for the calendar days held and dividends with ex-dates in
       (entry, exit] are charged at the exit;
    3. mark to market at the close: equity = cash - sum(shares x close).
  Trades still open at the end are marked at the last close (borrow and dividends accrued to
  the last day are charged in the mark).
No margin interest, no locate failures (borrow availability is unknown: see the report).
"""
import numpy as np
import pandas as pd


def replay(trades: pd.DataFrame, closes: dict, start, end, initial=10000.0, risk=0.01,
           max_positions=5, max_new=3, cap=0.20, slip_bps=10.0, borrow_apr=0.03):
    """trades: rows with ticker, rs, entry_date, entry, stop, exit_date (NaT if open), exit,
    dividends_ps, signal_date. closes: {ticker: pd.Series(close, index=dates)}.
    Returns (curve DataFrame[date, equity, cash, positions, notional], fills DataFrame,
    metrics dict)."""
    fee = slip_bps / 1e4
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    cal = sorted({d for s in closes.values() for d in s.index if start <= d <= end})
    t = trades.copy()
    for c in ("entry_date", "exit_date", "signal_date"):
        t[c] = pd.to_datetime(t[c])
    t = t[(t["entry_date"] >= start) & (t["entry_date"] <= end)]
    t = t.sort_values(["entry_date", "rs", "ticker"], ascending=[True, True, True],
                      kind="stable")
    by_day = {d: g for d, g in t.groupby("entry_date")}
    cash, held, last = float(initial), {}, {}
    curve, fills, skipped = [], [], {}

    def equity_at(prices):
        return cash - sum(p["qty"] * prices.get(tk, p["entry"]) for tk, p in held.items())

    def close_out(tk, px, day, status):
        nonlocal cash
        p = held.pop(tk)
        days = max(1, (day - p["entry_date"]).days)
        borrow = borrow_apr * days / 365 * p["entry"] * p["qty"]
        div = p["div_ps"] * p["qty"] if status == "closed" else 0.0
        cost_back = p["qty"] * px * (1 + fee)
        cash -= cost_back + borrow + div
        pnl = p["proceeds"] - cost_back - borrow - div
        fills.append(dict(ticker=tk, signal_date=p["signal_date"], entry_date=p["entry_date"],
                          exit_date=day, qty=p["qty"], entry=p["entry"], exit=px,
                          stop=p["stop"], borrow=borrow, dividends=div, net_pnl=pnl,
                          risk_usd=p["risk_usd"], net_r=pnl / p["risk_usd"], status=status))

    for day in cal:
        basis = equity_at(last)
        notional = sum(p["qty"] * p["entry"] for p in held.values())
        new = 0
        for r in (by_day[day].itertuples() if day in by_day else []):
            why = None
            if r.ticker in held:
                why = "ticker_open"
            elif len(held) >= max_positions:
                why = "positions"
            elif new >= max_new:
                why = "daily_entries"
            elif not (r.stop > r.entry > 0):
                why = "invalid"
            if why is None:
                qty = int(min(basis * risk / (r.stop - r.entry), basis * cap / r.entry))
                if qty < 1:
                    why = "size"
                elif notional + qty * r.entry > basis:
                    why = "no_leverage"
            if why:
                skipped[why] = skipped.get(why, 0) + 1
                continue
            proceeds = qty * r.entry * (1 - fee)
            cash += proceeds
            notional += qty * r.entry
            held[r.ticker] = dict(qty=qty, entry=r.entry, stop=r.stop, proceeds=proceeds,
                                  entry_date=day, signal_date=r.signal_date,
                                  exit_date=r.exit_date, exit=r.exit,
                                  div_ps=0.0 if pd.isna(r.dividends_ps) else float(r.dividends_ps),
                                  risk_usd=qty * (r.stop - r.entry))
            new += 1
        for tk in [k for k, p in held.items() if pd.notna(p["exit_date"]) and p["exit_date"] == day]:
            close_out(tk, held[tk]["exit"], day, "closed")
        for tk, s in closes.items():
            if day in s.index:
                last[tk] = float(s.loc[day])
        curve.append(dict(date=day, equity=equity_at(last), cash=cash, positions=len(held),
                          notional=sum(p["qty"] * last.get(k, p["entry"])
                                       for k, p in held.items())))
    open_end = []
    for tk in list(held):                                   # mark, do not invent an exit
        p = held[tk]
        days = max(1, (cal[-1] - p["entry_date"]).days)
        mark = last.get(tk, p["entry"])
        pnl = p["proceeds"] - p["qty"] * mark * (1 + fee) - borrow_apr * days / 365 * \
            p["entry"] * p["qty"]
        open_end.append(dict(ticker=tk, entry_date=p["entry_date"], qty=p["qty"], mark=mark,
                             unrealized_pnl=pnl))
    cv = pd.DataFrame(curve)
    fl = pd.DataFrame(fills)
    m = metrics(cv, fl, initial)
    m.update(open_at_end=len(open_end), skipped=skipped, candidates=int(len(t)))
    return cv, fl, m


def metrics(curve: pd.DataFrame, fills: pd.DataFrame, initial: float) -> dict:
    if curve.empty:
        return dict(final_equity=initial, return_pct=0.0, max_dd_pct=0.0, trades=0)
    eq = curve.set_index("date")["equity"]
    peak = np.maximum(initial, eq.cummax())
    dd = (eq / peak - 1) * 100
    yearly = eq.groupby(eq.index.year).last()
    prev = yearly.shift(1).fillna(initial)
    years = (eq.index[-1] - eq.index[0]).days / 365.25
    out = dict(first=str(eq.index[0].date()), last=str(eq.index[-1].date()),
               final_equity=float(eq.iloc[-1]), return_pct=float((eq.iloc[-1] / initial - 1) * 100),
               cagr_pct=float(((eq.iloc[-1] / initial) ** (1 / years) - 1) * 100)
               if years > 0.25 and eq.iloc[-1] > 0 else None,
               max_dd_pct=float(dd.min()),
               yearly_return_pct={int(y): round(float((v / p - 1) * 100), 2)
                                  for y, v, p in zip(yearly.index, yearly, prev)},
               trades=int(len(fills)),
               exposure_pct=float((curve["positions"] > 0).mean() * 100))
    if len(fills):
        r = fills["net_r"]
        w, l = fills.loc[fills["net_pnl"] > 0, "net_pnl"], fills.loc[fills["net_pnl"] <= 0, "net_pnl"]
        out.update(win_rate=float((r > 0).mean() * 100), expectancy_r=float(r.mean()),
                   profit_factor=float(w.sum() / -l.sum()) if l.sum() < 0 else None,
                   borrow_paid=float(fills["borrow"].sum()),
                   dividends_paid=float(fills["dividends"].sum()))
    return out
