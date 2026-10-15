"""Task 6 regression tests: sizing leakage (P1), signal/position ownership (P2),
terminal-date handling (P3), daily-limit non-monotonicity (P4).

Run:  python -m unittest test_task6_engine test_portfolio_bt -v
All tests are deterministic (fixed data, fixed seeds).
"""
import unittest

import numpy as np
import pandas as pd

import backtest as bt
from portfolio_bt import replay

DAYS = pd.date_range('2026-01-05', periods=60, freq='B')


def flat(n=60, price=100.):
    """Flat OHLC bars: close = price, high +1, low -1."""
    c = np.full(n, price, float)
    return {'O': c.copy(), 'H': c + 1, 'L': c - 1, 'C': c.copy(), 'V': np.full(n, 1e6),
            'dates': DAYS[:n]}


def trade(ticker, d, x, entry=100., stop=90., exit_=100., at='close', mode='retest'):
    return dict(ticker=ticker, date=DAYS[d], exit_date=(DAYS[x] if x is not None else pd.NaT),
                entry=entry, stop=stop, exit=exit_, entry_at=at, mode=mode)


def sig_rows(ticker, idx, close=100., stop_base=95., mode='breakout'):
    return pd.DataFrame([dict(ticker=ticker, mode=mode, i=i, date=DAYS[i], close=close,
                              level=stop_base, stop_base=stop_base, rs=90, vol_ratio=1.5)
                         for i in idx])


def qty_of(fills, metrics, ticker):
    if len(fills) and ticker in set(fills['ticker']):
        return int(fills.loc[fills['ticker'] == ticker, 'shares'].iloc[0])
    for p in metrics['open_positions']:
        if p['ticker'] == ticker:
            return int(p['shares'])
    return None


# =====================================================================
# P1 — no future information in pre-open sizing
# =====================================================================
class P1Leakage(unittest.TestCase):
    def setUp(self):
        self.data = {t: flat() for t in ('AAA', 'BBB', 'CCC')}

    def run_pair(self, exit_price, at):
        # AAA held from day 0, exits on day 5 at `exit_price`; BBB enters on day 5.
        tr = pd.DataFrame([trade('AAA', 0, 5, exit_=exit_price, at='close'),
                           trade('BBB', 5, 20, at=at)])
        return replay(tr, self.data, risk_fraction=.05, max_position_fraction=1,
                      max_positions=5, cost_bps=0)

    def test_preopen_qty_ignores_same_day_exit_price(self):
        q = {px: qty_of(*self.run_pair(px, 'open')[1:], 'BBB') for px in (10., 100., 400.)}
        self.assertEqual(len(set(q.values())), 1, q)

    def test_close_entry_still_uses_known_exit(self):
        # Sensitivity check: at the close the exit IS known, so share counts may differ.
        q = {px: qty_of(*self.run_pair(px, 'close')[1:], 'BBB') for px in (10., 400.)}
        self.assertNotEqual(q[10.], q[400.])

    def test_same_day_stop_of_other_new_entry_cannot_resize(self):
        def run(px):
            tr = pd.DataFrame([trade('AAA', 3, 3, exit_=px, at='open'),     # stopped same day
                               trade('BBB', 3, 20, at='open')])
            return replay(tr, self.data, risk_fraction=.05, max_position_fraction=1,
                          cost_bps=0)
        q = {px: qty_of(*run(px)[1:], 'BBB') for px in (50., 90., 99.)}
        self.assertEqual(len(set(q.values())), 1, q)

    def test_slot_not_freed_by_later_exit_for_preopen(self):
        tr = pd.DataFrame([trade('AAA', 0, 5), trade('BBB', 5, 20, at='open')])
        _, fills, m = replay(tr, self.data, max_positions=1)
        self.assertEqual(m['skipped'].get('positions'), 1)
        tr.loc[1, 'entry_at'] = 'close'                                     # known at close
        _, fills, m = replay(tr, self.data, max_positions=1)
        self.assertNotIn('positions', m['skipped'])

    def test_preopen_cash_excludes_same_day_proceeds(self):
        tr = pd.DataFrame([trade('AAA', 0, 5, stop=1.), trade('BBB', 5, 20, stop=1., at='open')])
        _, _, m = replay(tr, self.data, risk_fraction=1, max_position_fraction=1, cost_bps=0)
        self.assertEqual(m['skipped'].get('capital_or_risk'), 1)           # all cash in AAA

    def test_property_future_exit_prices_never_change_earlier_preopen_sizes(self):
        rng = np.random.default_rng(7)
        tickers = [f'T{k}' for k in range(12)]
        data = {}
        for t in tickers:
            c = 100 * np.exp(np.cumsum(rng.normal(0, .02, 60)))
            data[t] = {'C': c, 'dates': DAYS}
        rows = []
        for k in range(250):
            t = tickers[rng.integers(len(tickers))]
            d = int(rng.integers(0, 45)); x = d + int(rng.integers(0, 12))
            e = float(data[t]['C'][max(d - 1, 0)])
            rows.append(trade(t, d, x, entry=e, stop=e * .93,
                              exit_=float(data[t]['C'][x]), at=rng.choice(['open', 'stop'])))
        base = pd.DataFrame(rows)
        for D in (10, 20, 30):
            pert = base.copy()
            late = pert['exit_date'] >= DAYS[D]
            pert.loc[late, 'exit'] = pert.loc[late, 'exit'] * rng.uniform(.3, 3, late.sum())
            sizes = []
            for tr in (base, pert):
                _, f, m = replay(tr, data, max_positions=8, max_new_per_day=4,
                                 risk_fraction=.01, max_position_fraction=.5, cost_bps=10)
                rows_ = [(r.ticker, r.entry_date, r.shares) for r in f.itertuples()] + \
                        [(p['ticker'], p['entry_date'], p['shares']) for p in m['open_positions']]
                sizes.append(sorted((a, b, c) for a, b, c in rows_ if b <= DAYS[D]))
            self.assertEqual(sizes[0], sizes[1], f'D={D}')


# =====================================================================
# P2 — the portfolio owns tickers; rejected trades hide nothing
# =====================================================================
class P2Ownership(unittest.TestCase):
    def setUp(self):
        self.data = {'AAA': flat(), 'BBB': flat()}
        self.data['AAA']['L'][12] = 80.                     # AAA stopped out on bar 12
        self.sig = pd.concat([sig_rows('AAA', [5]), sig_rows('BBB', [10, 15])],
                             ignore_index=True)

    def sim(self, **kw):
        return bt.simulate(self.sig, self.data, 'breakout', hold=20, stop_buf=3, min_rs=0, **kw)

    def test_default_keeps_original_one_trade_per_ticker(self):
        legacy = self.sim()
        self.assertEqual(list(legacy['ticker']), ['AAA', 'BBB'])            # BBB@15 hidden
        self.assertNotIn('signal_date', legacy.columns)                     # same columns

    def test_raw_mode_returns_every_valid_signal(self):
        raw = self.sim(one_per_ticker=False)
        self.assertEqual(list(zip(raw['ticker'], raw['signal_date'])),
                         [('AAA', DAYS[5]), ('BBB', DAYS[10]), ('BBB', DAYS[15])])
        self.assertTrue((raw['date'] == raw['signal_date']).all())          # close entry

    def test_rejected_trade_does_not_suppress_later_signal(self):
        legacy = self.sim().assign(mode='breakout')
        raw = self.sim(one_per_ticker=False).assign(mode='breakout')
        _, f_old, _ = replay(legacy, self.data, max_positions=1)
        _, f_new, _ = replay(raw, self.data, max_positions=1)
        self.assertNotIn('BBB', set(f_old['ticker']))     # BBB@10 rejected, @15 never seen
        bbb = f_new[f_new['ticker'] == 'BBB']
        self.assertEqual(list(bbb['entry_date']), [DAYS[15]])

    def test_open_entry_signal_dates_preserved(self):
        raw = self.sim(one_per_ticker=False, entry_at='open')
        self.assertTrue((raw['date'] > raw['signal_date']).all())
        self.assertEqual(list(raw['signal_date']), [DAYS[5], DAYS[10], DAYS[15]])

    def test_stop_mode_raw_vs_legacy(self):
        pend = pd.DataFrame([dict(ticker='BBB', mode='breakout', i=i, date=DAYS[i], close=100.,
                                  pivot=100.5, stop_base=97., rs=90) for i in (10, 15)])
        legacy = bt.simulate_stop(pend, self.data, 'breakout', hold=20, stop_buf=3, min_rs=0)
        raw = bt.simulate_stop(pend, self.data, 'breakout', hold=20, stop_buf=3, min_rs=0,
                               one_per_ticker=False)
        self.assertEqual(len(legacy), 1)
        self.assertEqual(len(raw), 2)
        self.assertTrue((raw['entry_at'] == 'stop').all())

    def test_exit_day_reentry_close_allowed(self):
        tr = pd.DataFrame([trade('AAA', 0, 5, exit_=95.), trade('AAA', 5, 20)])
        _, f, m = replay(tr, self.data)
        self.assertEqual(m['executed_trades'], 2)        # exit realised before the close entry

    def test_exit_day_reentry_preopen_blocked_then_next_day_ok(self):
        tr = pd.DataFrame([trade('AAA', 0, 5, exit_=95.), trade('AAA', 5, 20, at='open'),
                           trade('AAA', 6, 20, at='open')])
        _, f, m = replay(tr, self.data)
        self.assertEqual(m['skipped'].get('ticker_open'), 1)   # still held at the open
        self.assertIn(DAYS[6], set(f['entry_date']))


# =====================================================================
# P3 — terminal dates: no silent drops, no invented exits
# =====================================================================
class P3Terminal(unittest.TestCase):
    def setUp(self):
        self.data = {'AAA': flat(), 'BBB': flat()}
        self.data['AAA']['C'][-1] = 110.                   # last close for marking

    def test_simulate_keeps_open_trades_when_asked(self):
        sig = sig_rows('AAA', [50])                         # 50 + 20 > 59: window incomplete
        self.assertTrue(bt.simulate(sig, self.data, 'breakout', hold=20, stop_buf=3,
                                    min_rs=0).empty)        # default: unchanged
        tr = bt.simulate(sig, self.data, 'breakout', hold=20, stop_buf=3, min_rs=0,
                         include_open=True)
        r = tr.iloc[0]
        self.assertEqual(r['status'], 'open')
        self.assertTrue(pd.isna(r['exit']) and pd.isna(r['exit_date']) and pd.isna(r['r']))
        self.assertEqual(r['mark'], 110.)
        self.assertFalse(r['window_complete'])

    def test_early_stop_inside_incomplete_window_is_closed_but_flagged(self):
        self.data['AAA']['L'][53] = 50.
        tr = bt.simulate(sig_rows('AAA', [50]), self.data, 'breakout', hold=20, stop_buf=3,
                         min_rs=0, include_open=True)
        self.assertEqual(tr.iloc[0]['status'], 'closed')
        self.assertFalse(tr.iloc[0]['window_complete'])

    def test_replay_marks_open_position(self):
        tr = pd.DataFrame([trade('AAA', 40, None, exit_=np.nan)])
        curve, f, m = replay(tr, self.data, cost_bps=0, risk_fraction=.01)
        self.assertEqual(len(f), 0)
        self.assertEqual(m['open_positions_end'], 1)
        q = m['open_positions'][0]['shares']
        self.assertAlmostEqual(m['final_equity'], 10000 + q * 10)          # 100 → 110
        self.assertEqual(curve['date'].iloc[-1], DAYS[-1])
        self.assertEqual(m['executed_trades'] + sum(m['skipped'].values()), m['candidate_trades'])

    def test_exit_after_end_is_never_used(self):
        res = []
        for px in (10., 1000.):
            tr = pd.DataFrame([trade('AAA', 10, 50, exit_=px)])
            res.append(replay(tr, self.data, end=DAYS[30])[2]['final_equity'])
        self.assertEqual(res[0], res[1])

    def test_liquidate_option(self):
        tr = pd.DataFrame([trade('AAA', 40, None, exit_=np.nan)])
        _, f, m = replay(tr, self.data, cost_bps=0, open_at_end='liquidate')
        self.assertEqual(list(f['status']), ['liquidated'])
        self.assertEqual(f.iloc[0]['exit'], 110.)
        self.assertEqual(m['open_positions_end'], 0)

    def test_skip_option_is_v3_behaviour(self):
        tr = pd.DataFrame([trade('AAA', 40, None, exit_=np.nan)])
        _, f, m = replay(tr, self.data, open_at_end='skip')
        self.assertEqual(m['executed_trades'], 0)
        self.assertEqual(m['skipped']['outside_window_or_invalid_dates'], 1)


# =====================================================================
# P4 — more daily entries can lower the return (cash path dependence)
# =====================================================================
class P4Capacity(unittest.TestCase):
    def test_unlimited_daily_entries_can_underperform(self):
        data = {f'M{k}': flat() for k in range(6)}
        data['WIN'] = flat()
        rows = [trade(f'M{k}', 1, 30, exit_=99.) for k in range(6)]          # mediocre, day 1
        rows.append(trade('WIN', 2, 30, exit_=150.))                         # great, day 2
        tr = pd.DataFrame(rows)
        kw = dict(max_positions=20, max_position_fraction=.2, risk_fraction=.05, cost_bps=0)
        _, f_lim, lim = replay(tr, data, max_new_per_day=3, **kw)
        _, f_unl, unl = replay(tr, data, max_new_per_day=None, **kw)
        self.assertIn('WIN', set(f_lim['ticker']))                          # cash left for it
        self.assertNotIn('WIN', set(f_unl['ticker']))                       # day 1 used it up
        self.assertGreater(lim['return_pct'], unl['return_pct'])
        self.assertGreater(unl['skipped'].get('capital_or_risk', 0), 0)    # WIN had no cash

    def test_cash_limited_counter(self):
        data = {f'M{k}': flat() for k in range(6)}
        tr = pd.DataFrame([trade(f'M{k}', 1, 30, stop=99.) for k in range(6)])
        m = replay(tr, data, max_positions=20, max_new_per_day=None, risk_fraction=.5,
                   max_position_fraction=.3, cost_bps=0)[2]
        self.assertGreater(m['cash_limited_entries'], 0)


if __name__ == '__main__':
    unittest.main()
