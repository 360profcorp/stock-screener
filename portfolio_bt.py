"""Cash-constrained, long-only portfolio replay of already simulated trades.

This does NOT remove biases in upstream signal generation/execution. Close-entry
fills remain optimistic if signals only become known after the closing auction.

Information timing (Task 6, P1)
-------------------------------
Every trade has an entry timing — the `entry_at` column written by backtest.simulate /
simulate_stop, or the `entry_timing` argument when the column is missing:

* "open" (next-day open) and "stop" (intraday buy-stop) — PRE-OPEN entries. They are sized
  and admitted with what is known before the session starts: cash before today's exits,
  held positions valued at the previous close, and positions that will exit later today
  still counted against max_positions. Nothing that happens later in the session (exit
  prices, stop fills, same-day stop of another new entry) can change their share counts.
* "close" (signal-day close) — sized at the close, after today's exits are known
  (original v3 behaviour, unchanged).

Daily order: pre-open entries -> exits due today -> close entries -> cash settles -> mark.

Open trades at the end (Task 6, P3)
-----------------------------------
A trade with no exit inside the evaluation window (status "open" / exit_date NaT, or an
exit after `end`) is handled by `open_at_end`:
  "mark"      (default) held to the end and marked to market at the last close;
              reported in metrics["open_positions"], never given an invented exit.
  "liquidate" sold at the last close of the window (costs applied), status "liquidated".
  "skip"      v3 behaviour: not taken at all, counted as outside_window_or_invalid_dates.
"""
from collections import defaultdict
import numpy as np
import pandas as pd

PRE_OPEN = {"open", "stop"}
TIMINGS = PRE_OPEN | {"close"}


def replay(trades, data, initial_cash=10000., risk_fraction=.01,
           max_positions=5, max_new_per_day=3, max_position_fraction=.20,
           cost_bps=10., start=None, end=None, entry_timing="close", open_at_end="mark",
           record_decisions=False):
    """Replay precomputed ticker trades; return (equity, executions, metrics).

    cost_bps: per-side combined commission/slippage in basis points.
    max_new_per_day: int >= 1, or None for no daily limit.
    entry_timing: timing for trades without an `entry_at` column ("close"|"open"|"stop").
    Equity valued at daily closing price; exit proceeds allocated at end of
    exit day, hence not reusable for entries the same day (conservative).
    Whole shares, no leverage, no short sales, fixed stops as provided.
    One position per ticker: the portfolio, not the trade simulator, owns tickers.
    record_decisions (Task 10 audit, default off = unchanged output): metrics['decisions'] lists
    every candidate in processing order with its outcome ('entered' or the skip reason) and
    shares; the curve gets a 'holdings' column (sorted (ticker, shares) at each close).
    """
    if initial_cash <= 0 or not 0 < risk_fraction <= 1 or not 0 < max_position_fraction <= 1:
        raise ValueError('Invalid capital/risk settings')
    if max_positions < 1 or (max_new_per_day is not None and max_new_per_day < 1) or cost_bps < 0:
        raise ValueError('Invalid portfolio limits')
    if entry_timing not in TIMINGS or open_at_end not in ("mark", "liquidate", "skip"):
        raise ValueError('Invalid entry_timing / open_at_end')
    daily_cap = np.inf if max_new_per_day is None else max_new_per_day
    frames = {}
    calendar = set()
    for ticker, x in data.items():
        dates = pd.DatetimeIndex(pd.to_datetime(x['dates'])).normalize()
        closes = np.asarray(x['C'], dtype=float)
        if len(dates) != len(closes):
            continue
        px = {d: float(c) for d, c in zip(dates, closes) if np.isfinite(c) and c > 0}
        frames[ticker] = px
        calendar.update(px)
    if not calendar:
        raise ValueError('No price history available')
    tr = trades.copy()
    if not tr.empty:
        tr['date'] = pd.to_datetime(tr['date']).dt.normalize()
        tr['exit_date'] = pd.to_datetime(tr['exit_date']).dt.normalize()
        if 'entry_at' not in tr:
            tr['entry_at'] = entry_timing
        tr['entry_at'] = tr['entry_at'].fillna(entry_timing)
        bad = ~tr['entry_at'].isin(TIMINGS)
        if bad.any():
            raise ValueError(f"Unknown entry_at values: {sorted(tr.loc[bad, 'entry_at'].unique())}")
        # Same-day candidates preserve caller order. No alphabetical ticker preference.
        # For research, caller should explicitly rank candidates before replay.
        tr = tr.sort_values(['date'], kind='stable').reset_index(drop=True)
    days = sorted(calendar)
    has_open = (not tr.empty and open_at_end != 'skip' and tr['exit_date'].isna().any())
    if start is None:
        start = tr['date'].min() if not tr.empty else days[0]
    if end is None:
        last_exit = tr['exit_date'].max() if not tr.empty else pd.NaT
        end = days[-1] if (has_open or pd.isna(last_exit)) else last_exit
    start, end = pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()
    days = [d for d in days if start <= d <= end]
    candidates = defaultdict(list)
    skipped = defaultdict(int)
    for r in tr.to_dict('records'):
        ex = r['exit_date']
        if not (start <= r['date'] <= end) or (pd.notna(ex) and ex < r['date']):
            skipped['outside_window_or_invalid_dates'] += 1
            continue
        if pd.isna(ex) or ex > end:                   # no exit known inside the window
            if open_at_end == 'skip':
                skipped['outside_window_or_invalid_dates'] += 1
                continue
            r = {**r, 'exit_date': None}              # never use an exit after `end`
        candidates[r['date']].append(r)

    cash = float(initial_cash)
    held = {}
    last_prices = {}                                  # closes up to the previous day
    equity_rows, fills = [], []
    fee = cost_bps / 10000.
    counters = defaultdict(int)
    decisions = []

    def try_enter(r, day, equity_basis, new_count):
        """Admit and size one candidate; returns True if entered."""
        nonlocal cash
        ticker = r['ticker']

        def skip(reason):
            skipped[reason] += 1
            if record_decisions:
                decisions.append(dict(day=day, ticker=ticker, rs=r.get('rs'),
                                      outcome=reason, shares=0))
            return False
        if ticker not in frames or day not in frames[ticker] or (
                r['exit_date'] is not None and r['exit_date'] not in frames[ticker]):
            return skip('missing_prices')
        if ticker in held:
            return skip('ticker_open')
        if len(held) >= max_positions:
            return skip('positions')
        if new_count >= daily_cap:
            return skip('daily_entries')
        entry, stop = float(r['entry']), float(r['stop'])
        if not np.isfinite(entry) or not np.isfinite(stop) or entry <= stop or stop <= 0:
            return skip('invalid')
        risk_budget = equity_basis * risk_fraction
        position_cap = equity_basis * max_position_fraction
        by_risk = risk_budget / (entry - stop)
        by_cap = position_cap / (entry * (1 + fee))
        by_cash = cash / (entry * (1 + fee))
        qty = int(min(by_risk, by_cap, by_cash))
        if qty < 1:
            return skip('capital_or_risk')
        if by_cash < min(by_risk, by_cap):
            counters['cash_limited_entries'] += 1     # size cut by free cash, not by risk
        spend = qty * entry * (1 + fee)
        cash -= spend
        held[ticker] = {**r, 'qty': qty, 'entry_cost': spend,
                        'risk_dollars': qty * (entry - stop)}
        counters['entries_' + ('pre_open' if r['entry_at'] in PRE_OPEN else 'close')] += 1
        if record_decisions:
            decisions.append(dict(day=day, ticker=ticker, rs=r.get('rs'), outcome='entered',
                                  shares=qty))
        return True

    def book_exit(ticker, day, price, status, exits):
        p = held.pop(ticker)
        proceeds = p['qty'] * float(price) * (1 - fee)
        exits.append(proceeds)
        pnl = proceeds - p['entry_cost']
        fills.append(dict(ticker=ticker, mode=p.get('mode', ''), entry_date=p['date'],
                          exit_date=day, shares=p['qty'], entry=p['entry'], exit=float(price),
                          net_pnl=pnl, initial_risk=p['risk_dollars'],
                          net_r=pnl / p['risk_dollars'], status=status))

    for day in days:
        todays = candidates[day]
        new_count = 0
        # 1) PRE-OPEN entries: only information available before the session starts.
        #    Positions exiting later today are still held, valued at the previous close;
        #    cash excludes today's exit proceeds.
        pre = [r for r in todays if r['entry_at'] in PRE_OPEN]
        if pre:
            basis = cash + sum(p['qty'] * last_prices.get(t, p['entry'])
                               for t, p in held.items())
            for r in pre:
                new_count += try_enter(r, day, basis, new_count)
        # 2) Exits due today (incl. same-day stops of pre-open entries). Proceeds settle
        #    at the end of the day and are not reused today.
        exits = []
        for ticker in [t for t, p in held.items() if p['exit_date'] == day]:
            book_exit(ticker, day, held[ticker]['exit'], 'closed', exits)
        # 3) CLOSE entries: today's exits are known (original v3 rules).
        for r in [r for r in todays if r['entry_at'] not in PRE_OPEN]:
            basis = cash + sum(p['qty'] * last_prices.get(t, p['entry'])
                               for t, p in held.items()) + sum(exits)
            if try_enter(r, day, basis, new_count):
                new_count += 1
                if r['exit_date'] == day:             # exits at today's close: settle now
                    book_exit(r['ticker'], day, r['exit'], 'closed', exits)
        for t, px in frames.items():
            if day in px:
                last_prices[t] = px[day]
        # 4) End of the window: optional forced liquidation of still-open positions.
        if open_at_end == 'liquidate' and day == days[-1]:
            for ticker in [t for t, p in held.items() if p['exit_date'] is None]:
                book_exit(ticker, day, last_prices.get(ticker, held[ticker]['entry']),
                          'liquidated', exits)
        cash += sum(exits)
        market_value = sum(p['qty'] * last_prices.get(t, p['entry']) for t, p in held.items())
        row = dict(date=day, equity=cash+market_value, cash=cash, open_positions=len(held))
        if record_decisions:
            row['holdings'] = tuple(sorted((t, p['qty']) for t, p in held.items()))
        equity_rows.append(row)
    curve = pd.DataFrame(equity_rows)
    if curve.empty:
        raise ValueError('No trading dates inside the requested period')
    curve['peak'] = np.maximum(initial_cash, curve['equity'].cummax())
    curve['drawdown_pct'] = 100 * (curve['equity'] / curve['peak'] - 1)
    executions = pd.DataFrame(fills)
    if len(executions):
        executions = executions.sort_values(['exit_date','ticker']).reset_index(drop=True)
    open_rows = []
    for t, p in held.items():                         # still held at the end: marked, not exited
        mark = last_prices.get(t, p['entry'])
        pnl = p['qty'] * mark * (1 - fee) - p['entry_cost']
        open_rows.append(dict(ticker=t, mode=p.get('mode', ''), entry_date=p['date'],
                              shares=p['qty'], entry=p['entry'], mark=mark,
                              unrealized_pnl=pnl, unrealized_r=pnl / p['risk_dollars']))
    years = (curve['date'].iloc[-1] - curve['date'].iloc[0]).days / 365.25
    final = float(curve['equity'].iloc[-1])
    n_closed = int((executions['status'] == 'closed').sum()) if len(executions) else 0
    metrics = dict(initial_capital=initial_cash, final_equity=final,
                   return_pct=100*(final/initial_cash-1),
                   cagr_pct=100*((final/initial_cash)**(1/years)-1) if years>0 else np.nan,
                   max_drawdown_pct=float(curve['drawdown_pct'].min()),
                   executed_trades=len(executions) + len(open_rows),
                   closed_trades=n_closed, liquidated_trades=len(executions) - n_closed,
                   open_positions_end=len(open_rows), open_positions=open_rows,
                   candidate_trades=len(tr), skipped=dict(skipped),
                   max_open_positions=int(curve['open_positions'].max()),
                   cash_limited_entries=counters['cash_limited_entries'],
                   entries_pre_open=counters['entries_pre_open'],
                   entries_close=counters['entries_close'],
                   note='Precomputed trade fills; daily-close mark-to-market; no intraday portfolio simulation.')
    if record_decisions:
        metrics['decisions'] = decisions
    return curve, executions, metrics
