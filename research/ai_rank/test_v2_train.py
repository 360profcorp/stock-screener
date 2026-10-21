"""Mechanics of the v2 training module (synthetic; no real training here)."""
import unittest

import numpy as np
import pandas as pd

from research.ai_rank import v2_train as V


class TestV2Train(unittest.TestCase):
    def test_daily_ic(self):
        df = pd.DataFrame({"signal_date": ["a"] * 4 + ["b"] * 2,
                           "net_r_base": [1., 2., 3., 4., 1., 2.]})
        ic = V.daily_ic(df, [1, 2, 3, 4, 2, 1])
        self.assertEqual(list(ic.index), ["a"])            # day b has < 3 signals
        self.assertAlmostEqual(ic["a"], 1.0)
        ic2 = V.daily_ic(df, [4, 3, 2, 1, 0, 0])
        self.assertAlmostEqual(ic2["a"], -1.0)

    def test_bootstrap_deterministic_and_ordered(self):
        s = pd.Series(np.linspace(-0.1, 0.3, 50))
        a, b = V.boot_ci(s), V.boot_ci(s)
        self.assertEqual(a, b)
        self.assertLess(a[0], s.mean())
        self.assertGreater(a[1], s.mean())

    def test_feature_sets(self):
        dec = ["rs_score", "rank_rs", "sess_since_earn"]
        self.assertNotIn("earn_within_5", V.features_for("deciding", dec))
        self.assertIn("earn_within_5", V.features_for("sensitivity", dec))
        sec = V.features_for("secondary_all_longs", dec)
        self.assertIn("rank_rs_all", sec)
        self.assertNotIn("rank_rs", sec)

    def test_gate_written_before_historical_window(self):
        import inspect
        src = inspect.getsource(V.main)
        self.assertLess(src.index('"gate.json"'), src.index("historical_window("))


if __name__ == "__main__":
    unittest.main()
