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


class LearnConversion(unittest.TestCase):
    def _blob(self):
        sess = pd.bdate_range("2007-01-03", periods=6)
        close = np.array([[100, 50], [102, 51], [51, 52], [52, 53], [53, 54], [54, 55]], dtype=np.float32)
        arr = {c: close.copy() for c in ("open", "high", "low", "close")}
        arr["volume"] = np.full_like(close, 1000)
        splits = pd.DataFrame(dict(sid=[1], effective_date=[sess[2]], ratio=[0.5]))
        divs = pd.DataFrame(dict(sid=[2], ex_date=[sess[3]], amount=[0.25]))
        maps = pd.DataFrame(dict(sid=[1, 2, 3], symbol=["AAA", "WB", "WB"],
                                 start_date=[sess[0], sess[0], sess[4]], end_date=[sess[-1], sess[3], sess[-1]]))
        return dict(sessions=sess, sids=[1, 2], arrays=arr, splits=splits, divs=divs, maps=maps), sess

    def test_split_only_basis(self):
        from research.retest_robustness import learn as L
        blob, sess = self._blob()
        fr, _ = L.split_adjusted_frames(blob)
        self.assertEqual(list(fr[1]["Close"].round(2)), [50.0, 51.0, 51.0, 52.0, 53.0, 54.0])  # 2:1 split
        self.assertEqual(float(fr[1]["Volume"].iloc[0]), 2000.0)
        self.assertEqual(float(fr[2]["Dividends"].loc[sess[3]]), 0.25)
        self.assertEqual(float(fr[2]["Close"].iloc[0]), 50.0)                                 # no div adj

    def test_ticker_reuse_resolved_by_date(self):
        from research.retest_robustness import learn as L
        blob, sess = self._blob()
        m = blob["maps"].copy()
        m["key"] = m["symbol"].map(L.norm)
        self.assertEqual(L.sid_on(m, "WB", sess[1]), 2)
        self.assertEqual(L.sid_on(m, "WB", sess[5]), 3)
        self.assertIsNone(L.sid_on(m, "ZZZ", sess[1]))
