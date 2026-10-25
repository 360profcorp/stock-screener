"""Synthetic unit tests: no outside data and no broker code."""
import unittest
import pandas as pd
import numpy as np
from research.long_diagnostic.run import trade_path, reconcile, summarize_fills, equity_exposure

class Tests(unittest.TestCase):
    def test_path_and_post_exit(self):
        dates=pd.bdate_range('2022-01-03',periods=8)
        x=dict(dates=dates.values,H=[101,110,102,103,110,112,115,105],
               L=[99,96,90,92,99,105,95,90],C=[100,98,95,99,101,109,111,99])
        p=trade_path(x,dates[1],dates[3],100,95)
        self.assertAlmostEqual(p['mfe_r'],2)
        self.assertAlmostEqual(p['mae_r'],-2)
        self.assertIsNone(p['post_exit_5_close_ret_pct'])
        self.assertIsNone(p['post_exit_10_close_ret_pct'])
    def test_single_bar_unknown_order(self):
        x=dict(dates=pd.bdate_range('2022-03-01',periods=3),H=[110,111,102],L=[90,90,95],C=[100,99,98])
        p=trade_path(x,x['dates'][0],x['dates'][0],100,95)
        self.assertIsNone(p['mfe_r_excluding_exit_day'])
        self.assertTrue(p['exit_bar_intraday_order_unknown'])
    def test_recon_open_fee_only_entry(self):
        eq=pd.DataFrame([dict(equity=10009.)]);fills=pd.DataFrame(columns=['net_pnl'])
        openp=[dict(shares=1,entry=100,mark=109)]
        r=reconcile(eq,fills,openp,10000,0)
        self.assertTrue(r['matches_cent'])
    def test_recon_loss(self):
        eq=pd.DataFrame([dict(equity=9995.)]);fills=pd.DataFrame([dict(net_pnl=-5)])
        self.assertTrue(reconcile(eq,fills,[],10000,10)['matches_cent'])
    def test_stats(self):
        s=summarize_fills(pd.DataFrame(dict(net_pnl=[10,-5,-5],net_r=[2,-1,-1])))
        self.assertAlmostEqual(s['win_rate_pct'],100/3)
        self.assertEqual(s['profit_factor'],1)
        self.assertEqual(s['total_pnl_usd'],0)
    def test_exposure(self):
        d=pd.DataFrame([dict(equity=100,cash=80,open_positions=1),dict(equity=120,cash=120,open_positions=0)])
        self.assertAlmostEqual(equity_exposure(d)['average_invested_pct'],10)

if __name__=='__main__':unittest.main()
