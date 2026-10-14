import unittest
import numpy as np
import pandas as pd
from portfolio_bt import replay

class PortfolioTests(unittest.TestCase):
    def setUp(self):
        self.days = pd.date_range('2026-01-05', periods=5, freq='B')
        self.data = {s: {'dates': self.days, 'C': np.array(p, dtype=float)} for s, p in {
            'AAA':[100,105,110,120,120], 'BBB':[100,90,85,80,80],
            'CCC':[100,100,100,100,100]}.items()}

    def trades(self):
        return pd.DataFrame([
            dict(ticker='AAA', date=self.days[0], exit_date=self.days[3], entry=100.,stop=90.,exit=120.),
            dict(ticker='BBB', date=self.days[0], exit_date=self.days[3], entry=100.,stop=90.,exit=80.),
            dict(ticker='CCC', date=self.days[0], exit_date=self.days[3], entry=100.,stop=90.,exit=100.)])

    def test_limited_positions(self):
        curve, fills, m = replay(self.trades(), self.data, max_positions=1)
        self.assertEqual(len(fills), 1)
        self.assertEqual(m['max_open_positions'],1)
        self.assertAlmostEqual(m['final_equity'], 10197.8, places=6)
        self.assertLessEqual(curve['drawdown_pct'].max(),0)

    def test_no_leverage(self):
        curve, fills, m = replay(self.trades(), self.data, max_positions=3,
                                 risk_fraction=1, max_position_fraction=1)
        self.assertTrue((curve['cash']>=-1e-8).all())
        self.assertEqual(len(fills),1)

    def test_same_day_stop_is_counted(self):
        tr = pd.DataFrame([dict(ticker='AAA', date=self.days[0],
                                exit_date=self.days[0], entry=100., stop=90., exit=90.)])
        curve, fills, metrics = replay(tr, self.data, cost_bps=0)
        self.assertEqual(metrics['executed_trades'], 1)
        self.assertAlmostEqual(metrics['final_equity'], 9900.)
        self.assertEqual(fills.iloc[0]['net_r'], -1.)

    def test_missing_price_is_not_filled(self):
        tr = pd.DataFrame([dict(ticker='UNKNOWN', date=self.days[0],
                                exit_date=self.days[3], entry=100., stop=90., exit=110.)])
        _, fills, metrics = replay(tr, self.data)
        self.assertEqual(metrics['executed_trades'], 0)
        self.assertEqual(metrics['skipped']['missing_prices'], 1)

    def test_window_candidates_reconcile(self):
        trades = self.trades()
        curve, fills, metrics = replay(trades, self.data, start=self.days[0], end=self.days[2])
        self.assertEqual(metrics['candidate_trades'], 3)
        self.assertEqual(metrics['executed_trades'], 0)
        self.assertEqual(metrics['skipped']['outside_window_or_invalid_dates'], 3)

    def test_window_one_executed_two_excluded(self):
        trades = self.trades().copy()
        trades.loc[0, 'exit_date'] = self.days[1]
        trades.loc[0, 'exit'] = 105.
        _, fills, metrics = replay(trades, self.data, start=self.days[0], end=self.days[2])
        self.assertEqual(metrics['candidate_trades'], 3)
        self.assertEqual(metrics['executed_trades'], 1)
        self.assertEqual(metrics['skipped']['outside_window_or_invalid_dates'], 2)

    def test_same_day_input_order_not_alphabetical(self):
        trades = self.trades().iloc[[2, 1, 0]].reset_index(drop=True)
        _, fills, metrics = replay(trades, self.data, max_positions=1)
        self.assertEqual(fills.iloc[0]['ticker'], 'CCC')
        self.assertEqual(metrics['skipped']['positions'], 2)

    def test_costs(self):
        m0=replay(self.trades().iloc[:1],self.data,cost_bps=0)[2]
        m1=replay(self.trades().iloc[:1],self.data,cost_bps=10)[2]
        self.assertLess(m1['return_pct'],m0['return_pct'])

if __name__=='__main__': unittest.main()
