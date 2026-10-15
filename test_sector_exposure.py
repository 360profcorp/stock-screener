"""Task 9 tests: per-sector cap in replay + sector_exposure module. Deterministic."""
import unittest

import numpy as np
import pandas as pd

import sector_exposure as se
from portfolio_bt import replay

DAYS = pd.date_range('2026-01-05', periods=30, freq='B')
SECTORS = {'E1': 'Energy', 'E2': 'Energy', 'E3': 'Energy', 'H1': 'Health Care', 'X1': None}


def flat(price=100.):
    return {'C': np.full(len(DAYS), price), 'dates': DAYS}


def trade(t, d, x, at='close', rs=90, entry=100., stop=95., exit_=100.):
    return dict(ticker=t, date=DAYS[d], exit_date=DAYS[x] if x is not None else pd.NaT,
                entry=entry, stop=stop, exit=exit_, entry_at=at, rs=rs, mode='retest')


class SectorCap(unittest.TestCase):
    def setUp(self):
        self.data = {t: flat() for t in SECTORS}
        self.data['E3'] = flat(110.)

    def test_default_is_unchanged(self):
        tr = pd.DataFrame([trade('E1', 0, 10), trade('E2', 0, 12), trade('H1', 1, 9)])
        a = replay(tr, self.data)
        b = replay(tr, self.data, sector_map=SECTORS, max_per_sector=None)
        pd.testing.assert_frame_equal(a[0], b[0])
        pd.testing.assert_frame_equal(a[1], b[1])

    def test_limit_one_rejects_second_same_sector(self):
        tr = pd.DataFrame([trade('E1', 0, 10), trade('E2', 0, 12), trade('H1', 0, 9)])
        _, f, m = replay(tr, self.data, sector_map=SECTORS, max_per_sector=1)
        self.assertEqual(set(f['ticker']), {'E1', 'H1'})
        self.assertEqual(m['skipped']['sector_limit'], 1)
        self.assertEqual(m['sector_limit_rejections'], {'Energy': 1})

    def test_limit_two_allows_two(self):
        tr = pd.DataFrame([trade(t, 0, 10) for t in ('E1', 'E2', 'E3')])
        _, f, m = replay(tr, self.data, sector_map=SECTORS, max_per_sector=2)
        self.assertEqual(len(f), 2)
        self.assertEqual(m['sector_limit_rejections'], {'Energy': 1})

    def test_slot_reopens_after_exit_close_entry(self):
        tr = pd.DataFrame([trade('E1', 0, 5), trade('E2', 5, 12)])     # close entry, exit day
        _, f, m = replay(tr, self.data, sector_map=SECTORS, max_per_sector=1)
        self.assertEqual(len(f), 2)

    def test_preopen_counts_position_exiting_later_today(self):
        tr = pd.DataFrame([trade('E1', 0, 5), trade('E2', 5, 12, at='open'),
                           trade('E3', 6, 12, at='open', entry=110., stop=104.)])
        _, f, m = replay(tr, self.data, sector_map=SECTORS, max_per_sector=1)
        self.assertEqual(m['sector_limit_rejections'], {'Energy': 1})   # E2 blocked at the open
        self.assertIn('E3', set(f['ticker']))                          # next day is fine

    def test_unknown_sector_bucket(self):
        tr = pd.DataFrame([trade('X1', 0, 10), trade('ZZ', 0, 10)])
        data = {**self.data, 'ZZ': flat()}
        _, f, m = replay(tr, data, sector_map=SECTORS, max_per_sector=1)
        self.assertEqual(m['sector_limit_rejections'], {'Unknown': 1})

    def test_reconciliation_with_sector_limit(self):
        tr = pd.DataFrame([trade(t, d, d + 8) for d in range(0, 12, 3)
                           for t in ('E1', 'E2', 'E3', 'H1')])
        _, f, m = replay(tr, self.data, sector_map=SECTORS, max_per_sector=1,
                         max_positions=3, max_new_per_day=None)
        self.assertEqual(m['executed_trades'] + sum(m['skipped'].values()), m['candidate_trades'])

    def test_requires_map(self):
        with self.assertRaises(ValueError):
            replay(pd.DataFrame([trade('E1', 0, 5)]), self.data, max_per_sector=1)


class ExposureModule(unittest.TestCase):
    def setUp(self):
        self.data = {t: flat() for t in SECTORS}
        self.data['H1'] = {'C': np.linspace(100, 129, len(DAYS)), 'dates': DAYS}

    def test_sector_map_from_universe(self):
        u = pd.DataFrame({'ticker': ['A', 'B', 'C'], 'sector': ['Energy', '', np.nan]})
        self.assertEqual(se.sector_map_from_universe(u),
                         {'A': 'Energy', 'B': 'Unknown', 'C': 'Unknown'})

    def test_snapshot_roundtrip(self, ):
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 's.csv')
            se.save_sector_snapshot({'A': 'Energy'}, p, as_of='2026-10-14')
            self.assertEqual(se.load_sector_snapshot(p), {'A': 'Energy'})
            self.assertEqual(pd.read_csv(p)['as_of'][0], '2026-10-14')

    def test_daily_exposure_counts_and_values(self):
        ex = pd.DataFrame([dict(ticker='E1', entry_date=DAYS[0], exit_date=DAYS[3], shares=10),
                           dict(ticker='E2', entry_date=DAYS[2], exit_date=DAYS[2], shares=5)])
        opn = [dict(ticker='H1', entry_date=DAYS[1], shares=2)]
        e = se.daily_exposure(ex, opn, self.data, SECTORS, days=DAYS)
        en = e[e['sector'] == 'Energy'].set_index('date')['positions']
        self.assertEqual(list(en.index), list(DAYS[0:3]))               # exit day excluded
        self.assertEqual(int(en.max()), 1)                              # same-day trip ignored
        h = e[e['sector'] == 'Health Care'].set_index('date')
        self.assertEqual(len(h), len(DAYS) - 1)                         # open to the end
        self.assertAlmostEqual(h.loc[DAYS[-1], 'value'], 2 * 129.)

    def test_concentration_metrics(self):
        exp = pd.DataFrame([(DAYS[0], 'Energy', 2, 200.), (DAYS[0], 'Health Care', 1, 200.),
                            (DAYS[1], 'Energy', 1, 100.)],
                           columns=['date', 'sector', 'positions', 'value'])
        m = se.concentration_metrics(exp, n_days=4)
        self.assertEqual(m['max_same_sector'], 2)
        self.assertAlmostEqual(m['days_ge2_same_sector_pct'], 25.0)
        self.assertAlmostEqual(m['avg_hhi'], (0.5 + 1.0) / 2)           # 0.25+0.25, then 1
        self.assertAlmostEqual(m['max_top_sector_weight_pct'], 100.0)
        self.assertAlmostEqual(m['invested_days_pct'], 50.0)

    def test_breakdown(self):
        exp = pd.DataFrame([(DAYS[0], 'Energy', 3, 300.), (DAYS[0], 'Health Care', 1, 100.)],
                           columns=['date', 'sector', 'positions', 'value'])
        b = se.sector_breakdown(exp)
        self.assertEqual(b.iloc[0]['sector'], 'Energy')
        self.assertAlmostEqual(b.iloc[0]['position_days_pct'], 75.0)

    def test_downside_metrics(self):
        curve = pd.DataFrame({'date': DAYS[:5], 'equity': [100., 110., 99., 104.5, 121.]})
        m = se.downside_metrics(curve)
        self.assertAlmostEqual(m['max_drawdown_pct'], -10.0)
        self.assertAlmostEqual(m['worst_day_pct'], -10.0)
        self.assertEqual(m['longest_drawdown_days'], 2)

    def test_end_to_end_limit_reduces_concentration(self):
        tr = pd.DataFrame([trade(t, 0, 20) for t in ('E1', 'E2', 'E3', 'H1')])
        res = {}
        for lim in (None, 1):
            c, f, m = replay(tr, self.data, sector_map=SECTORS, max_per_sector=lim,
                             max_positions=5, max_new_per_day=None, risk_fraction=.01)
            e = se.daily_exposure(f, m['open_positions'], self.data, SECTORS, days=c['date'])
            res[lim] = se.concentration_metrics(e, len(c))['max_same_sector']
        self.assertEqual((res[None], res[1]), (3, 1))


if __name__ == '__main__':
    unittest.main()
