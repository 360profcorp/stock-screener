"""Cash-constrained, long-only portfolio replay of already simulated trades.

This does NOT remove biases in upstream signal generation/execution. Close-entry
fills remain optimistic if signals only become known after the closing auction.
"""
from collections import defaultdict
import numpy as np
import pandas as pd


def replay(trades, data, initial_cash=10000., risk_fraction=.01,
           max_positions=5, max_new_per_day=3, max_position_fraction=.20,
           cost_bps=10., start=None, end=None):
    """Replay precomputed non-overlapping ticker trades; return (equity, executions, metrics).

    cost_bps: per-side combined commission/slippage in basis points.
    Equity valued at daily closing price; exit proceeds allocated at end of
    exit day, hence not reusable for entries the same day (conservative).
    Whole shares, no leverage, no short sales, fixed stops as provided.
    """
    if initial_cash <= 0 or not 0 < risk_fraction <= 1 or not 0 < max_position_fraction <= 1:
        raise ValueError('Invalid capital/risk settings')
    if max_positions < 1 or max_new_per_day < 1 or cost_bps < 0:
        raise ValueError('Invalid portfolio limits')
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
        # Same-day candidates preserve caller order. No alphabetical ticker preference.
        # For research, caller should explicitly rank candidates before replay.
        tr = tr.sort_values(['date'], kind='stable').reset_index(drop=True)
    days = sorted(calendar)
    if start is None:
        start = tr['date'].min() if not tr.empty else days[0]
    if end is None:
        end = tr['exit_date'].max() if not tr.empty else days[-1]
    start, end = pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()
    days = [d for d in days if start <= d <= end]
    candidates = defaultdict(list)
    skipped = defaultdict(int)
    for r in tr.to_dict('records'):
        if not (start <= r['date'] <= end and r['exit_date'] <= end and r['exit_date'] >= r['date']):
            skipped['outside_window_or_invalid_dates'] += 1
            continue
        candidates[r['date']].append(r)

    cash = float(initial_cash)
    held = {}
    last_prices = {}
    equity_rows, fills = [], []
    fee = cost_bps / 10000.
    for day in days:
        # Long-only positions close at their predefined exit. No proceeds reused today.
        due = [t for t, p in held.items() if p['exit_date'] == day]
        exits = []
        for ticker in due:
            p = held.pop(ticker)
            proceeds = p['qty'] * float(p['exit']) * (1-fee)
            exits.append(proceeds)
            pnl = proceeds - p['entry_cost']
            fills.append(dict(ticker=ticker, mode=p.get('mode', ''), entry_date=p['date'],
                              exit_date=day, shares=p['qty'], entry=p['entry'], exit=p['exit'],
                              net_pnl=pnl, initial_risk=p['risk_dollars'],
                              net_r=pnl / p['risk_dollars']))
        new_count = 0
        for r in candidates[day]:
            ticker = r['ticker']
            if ticker not in frames or day not in frames[ticker] or r['exit_date'] not in frames[ticker]:
                skipped['missing_prices'] += 1; continue
            if ticker in held:
                skipped['ticker_open'] += 1; continue
            if len(held) >= max_positions:
                skipped['positions'] += 1; continue
            if new_count >= max_new_per_day:
                skipped['daily_entries'] += 1; continue
            entry, stop = float(r['entry']), float(r['stop'])
            if not np.isfinite(entry) or not np.isfinite(stop) or entry <= stop or stop <= 0:
                skipped['invalid'] += 1; continue
            # Value previous positions at today's close; new entries do not enlarge equity.
            current_equity = cash + sum(p['qty'] * last_prices.get(t, p['entry'])
                                        for t, p in held.items()) + sum(exits)
            risk_budget = current_equity * risk_fraction
            position_cap = current_equity * max_position_fraction
            qty = int(min(risk_budget / (entry-stop), position_cap / (entry*(1+fee)),
                          cash / (entry*(1+fee))))
            if qty < 1:
                skipped['capital_or_risk'] += 1; continue
            spend = qty * entry * (1+fee)
            cash -= spend
            risk_dollars = qty * (entry-stop)
            if r['exit_date'] == day:
                # Intraday stop: reserve proceeds until end of day to avoid reuse.
                proceeds = qty * float(r['exit']) * (1-fee)
                exits.append(proceeds)
                fills.append(dict(ticker=ticker, mode=r.get('mode', ''), entry_date=day,
                                  exit_date=day, shares=qty, entry=entry, exit=r['exit'],
                                  net_pnl=proceeds-spend, initial_risk=risk_dollars,
                                  net_r=(proceeds-spend)/risk_dollars))
            else:
                held[ticker] = {**r, 'qty': qty, 'entry_cost': spend,
                                'risk_dollars': risk_dollars}
            new_count += 1
        cash += sum(exits)
        for t, px in frames.items():
            if day in px:
                last_prices[t] = px[day]
        market_value = sum(p['qty'] * last_prices.get(t, p['entry']) for t, p in held.items())
        equity_rows.append(dict(date=day, equity=cash+market_value, cash=cash,
                                open_positions=len(held)))
    curve = pd.DataFrame(equity_rows)
    if curve.empty:
        raise ValueError('No trading dates inside the requested period')
    curve['peak'] = np.maximum(initial_cash, curve['equity'].cummax())
    curve['drawdown_pct'] = 100 * (curve['equity'] / curve['peak'] - 1)
    executions = pd.DataFrame(fills)
    if len(executions):
        executions = executions.sort_values(['exit_date','ticker']).reset_index(drop=True)
    years = (curve['date'].iloc[-1] - curve['date'].iloc[0]).days / 365.25
    final = float(curve['equity'].iloc[-1])
    metrics = dict(initial_capital=initial_cash, final_equity=final,
                   return_pct=100*(final/initial_cash-1),
                   cagr_pct=100*((final/initial_cash)**(1/years)-1) if years>0 else np.nan,
                   max_drawdown_pct=float(curve['drawdown_pct'].min()),
                   executed_trades=len(executions), candidate_trades=len(tr),
                   skipped=dict(skipped), max_open_positions=int(curve['open_positions'].max()),
                   note='Precomputed trade fills; daily-close mark-to-market; no intraday portfolio simulation.')
    return curve, executions, metrics
