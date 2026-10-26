import unittest

import numpy as np
import pandas as pd

from research.retest_robustness import run as R


class Coverage(unittest.TestCase):
    def test_member_days_and_survivor_split(self):
        cal = pd.bdate_range("2010-01-04", periods=10)
        tl = [(pd.Timestamp("2020-01-01"), {"A", "B"}), (cal[5], {"A", "C"})]   # C removed at cal[5]
        f = pd.DataFrame({"Open": 1., "High": 1., "Low": 1., "Close": 1., "Volume": 1.}, index=cal)
        by, tab = R.coverage({"A": f, "B": f.iloc[5:]}, tl, cal)
        y = by[2010]
        self.assertEqual(y["member_days"], 20)            # 2 members x 10 days
        self.assertEqual(y["covered"], 15)                # A 10, B 5, C 0
        self.assertEqual(y["removed_days"], 5)            # C
        self.assertEqual(y["removed_cov_pct"], 0.0)
        self.assertFalse(bool(tab.set_index("ticker").loc["C", "has_data"]))


class Verdict(unittest.TestCase):
    def _res(self, cagr=5., pf=1.2, dd=-15., trades=120, sub=40, ret=10.):
        b = {}
        for w in ("U", "U1", "U2"):
            for bps in (10, 25, 50):
                b[f"{w}|{bps}bps"] = dict(cagr_pct=cagr, profit_factor=pf, max_dd_pct=dd, return_pct=ret,
                                         closed_trades=trades if w == "U" else sub)
        return dict(books=b, benchmarks={"U": {"SPY50_BIL50": dict(cagr_pct=4., max_dd_pct=-17.)}})

    def test_pass_fail_inconclusive(self):
        cov = dict(coverage_gate_passed=True)
        self.assertEqual(R.verdict(self._res(), cov)[1], "PASS")
        self.assertEqual(R.verdict(self._res(dd=-21.), cov)[1], "FAIL")
        self.assertEqual(R.verdict(self._res(cagr=3.), cov)[1], "FAIL")
        self.assertEqual(R.verdict(self._res(trades=90), cov)[1], "INCONCLUSIVE")
        self.assertEqual(R.verdict(self._res(), dict(coverage_gate_passed=False))[1], "INCONCLUSIVE")


class Bootstrap(unittest.TestCase):
    def test_deterministic(self):
        d = pd.bdate_range("2010-01-01", periods=300)
        a = pd.Series(10000 * np.cumprod(1 + np.random.default_rng(1).normal(0, .01, 300)), index=d)
        b = pd.Series(10000 * np.cumprod(1 + np.random.default_rng(2).normal(0, .01, 300)), index=d)
        self.assertEqual(R.bootstrap(a, b, n=50), R.bootstrap(a, b, n=50))


if __name__ == "__main__":
    unittest.main()
