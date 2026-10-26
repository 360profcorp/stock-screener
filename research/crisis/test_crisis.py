"""Crisis-protection research: the drawdown breaker keeps the replay engine unchanged.
Synthetic data only. Run: python -m unittest research.crisis.test_crisis"""
import unittest

import numpy as np
import pandas as pd

import backtest as bt
import portfolio_bt as pf
from research.crisis import run as CR
from test_paper import market


class Breaker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fr, spy = market(5, n_t=25, n=520)
        sig, data = bt.find_signals(fr, modes=["breakout"])
        t = bt.simulate(sig, data, "breakout", hold=20, stop_buf=3.0, min_rs=50, min_vol=0.0,
                        max_risk=0.0, market_ok=None, entry_at="open", one_per_ticker=False,
                        include_open=True)
        t["date"] = pd.to_datetime(t["date"]).dt.normalize()
        cls.tr = t.sort_values(["date", "rs", "ticker"], ascending=[True, False, True],
                               kind="stable").reset_index(drop=True)
        cls.data = data
        cal = sorted({pd.Timestamp(d) for x in data.values() for d in x["dates"]})
        cls.start, cls.end = cal[270], cal[-1]

    def plain(self):
        return pf.replay(self.tr, self.data, start=self.start, end=self.end, open_at_end="mark",
                         cost_bps=10., **CR.CFG)

    def test_without_breaker_equals_the_plain_replay(self):
        a = self.plain()
        for dd in (None, 0.99):
            b = CR.gated_replay(self.tr, self.data, self.start, self.end, dd, 10.)
            self.assertTrue(a[0]["equity"].equals(b[0]["equity"]))
            self.assertEqual(b[3], [])

    def test_breaker_pauses_only_new_entries_after_a_trigger(self):
        curve, ex, m, pauses = CR.gated_replay(self.tr, self.data, self.start, self.end, 0.03, 10.)
        self.assertTrue(pauses)
        eq = curve.set_index("date")["equity"]
        for a, b in pauses:
            entered = ex[(pd.to_datetime(ex["entry_date"]) > a) &
                         (pd.to_datetime(ex["entry_date"]) <= b)] if len(ex) else ex
            self.assertEqual(len(entered), 0)                      # nothing entered while paused
            peak = max(10000., eq[eq.index <= a].max())
            self.assertLessEqual(eq.loc[a], peak * 0.97 + 1e-6)    # trigger was a real drawdown
        plain = self.plain()[0].set_index("date")["equity"]
        first = pauses[0][0]
        self.assertTrue(np.allclose(eq[eq.index <= first], plain[plain.index <= first]))


if __name__ == "__main__":
    unittest.main()
