"""Tests for the v2 data build (synthetic; mechanics and leakage only, no training)."""
import unittest

import numpy as np
import pandas as pd

from research.ai_rank import v2_build as B
from research.sp1500 import engine as E
from research.sp1500 import test_sp1500 as T


class TestV2Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frames, cls.spy, _ = T.universe_frames(10, 500)
        idx = pd.DataFrame({t: f["Close"] for t, f in cls.frames.items()}).index
        cls.mask = pd.DataFrame(True, index=idx, columns=list(cls.frames))
        cls.mask.iloc[:300, 0] = False                         # T0 joins the index later
        cls.sectors = {t: ("A" if k % 2 else "B") for k, t in enumerate(cls.frames)}

    def test_breadth_and_sector_are_causal(self):
        br, st, _ = B.market_tables(self.frames, self.mask, self.sectors)
        d = br.index[400]
        cut = {t: f.loc[:d] for t, f in self.frames.items()}
        b2, s2, _ = B.market_tables(cut, self.mask.loc[:d], self.sectors)
        for c in ("breadth_ma50", "breadth_new_high", "breadth_chg5"):
            self.assertTrue(np.isclose(br.loc[d, c], b2.loc[d, c]), c)
        a = st[(st["date"] == d)].set_index("sector")["sector_rs_median"]
        b = s2[(s2["date"] == d)].set_index("sector")["sector_rs_median"]
        pd.testing.assert_series_equal(a, b)
        fut = {t: f.copy() for t, f in self.frames.items()}
        for f in fut.values():
            f.loc[f.index > d, "Close"] *= 3
        b3, _, _ = B.market_tables(fut, self.mask, self.sectors)
        self.assertTrue(np.isclose(br.loc[d, "breadth_ma50"], b3.loc[d, "breadth_ma50"]))

    def test_non_members_excluded(self):
        br, _, _ = B.market_tables(self.frames, self.mask, self.sectors)
        self.assertEqual(br["breadth_members"].iloc[299], 9)
        self.assertEqual(br["breadth_members"].iloc[300], 10)

    def test_earnings_features_use_past_reports_only(self):
        cal = pd.bdate_range("2026-01-05", periods=30)
        pool = pd.DataFrame({"ticker": ["X", "X", "Y"],
                             "signal_date": [cal[10], cal[3], cal[10]]})
        earn = {"X": [str(cal[5].date()), str(cal[12].date())], "Y": []}
        f = B.earnings_features(pool, earn, cal)
        self.assertEqual(f["sess_since_earn"].iloc[0], 5.0)          # report 5 sessions ago
        self.assertEqual(f["earn_within_5"].iloc[0], 1.0)            # next report in 2 sessions
        self.assertTrue(np.isnan(f["sess_since_earn"].iloc[1]))      # no past report yet
        self.assertTrue(np.isnan(f["sess_since_earn"].iloc[2]))      # no data
        self.assertTrue(all(pd.Timestamp(a) <= d for a, d in
                            zip(f["earn_last_date_used"], pool["signal_date"]) if pd.notna(a)))

    def test_fetch_earnings_bounded_retries(self):
        calls = []

        def bad(t):
            calls.append(t)
            raise RuntimeError("429")
        out, failed = B.fetch_earnings(["A"], retries=2, pause=0, fetcher=bad, log=lambda m: None)
        self.assertEqual((len(calls), out["A"], "A" in failed), (3, None, True))
        out, failed = B.fetch_earnings(["A"], pause=0, fetcher=lambda t: ["2026-01-05"],
                                       log=lambda m: None)
        self.assertEqual((out["A"], failed), (["2026-01-05"], {}))

    def test_retest_rank_ignores_other_strategies_and_matches_v1(self):
        from research.ai_rank import pipeline as P
        from research.ai_rank.test_ai_rank import TestAIRank
        TestAIRank.setUpClass()
        lab = TestAIRank.lab.copy()
        lab["eligible_pit_primary"] = lab["eligible_primary"]
        lab["rs_pit500"] = lab["rs_ref500"]
        all_longs = B.add_rs_ranks(P.long_pool(lab, "pit500", tuple(P.LONGS)))
        only_ret = B.add_rs_ranks(P.long_pool(lab, "pit500", ("retest",)))
        key = ["ticker", "signal_date"]
        a = all_longs[all_longs["strategy"] == "retest"].set_index(key)["rank_rs"].sort_index()
        b = only_ret.set_index(key)["rank_rs"].sort_index()
        self.assertGreater(len(a), 0)
        self.assertGreater((all_longs["strategy"] != "retest").sum(), 0)   # others really present
        pd.testing.assert_series_equal(a, b)                 # other setups do not move it
        v1 = P.long_pool(lab, "pit500", ("retest",)).set_index(key)["rank_rs"].sort_index()
        pd.testing.assert_series_equal(a, v1)                # identical to v1
        r = all_longs.set_index(key + ["strategy"])
        self.assertTrue(((r["rank_rs_all"] > 0) & (r["rank_rs_all"] <= 1)).all())
        # the all-setups rank is a separate column and does depend on the other setups
        days = all_longs.groupby("signal_date")["strategy"].nunique()
        mixed = days[days > 1].index
        if len(mixed):
            m = all_longs[all_longs["signal_date"].isin(mixed)]
            self.assertFalse(np.allclose(m["rank_rs"], m["rank_rs_all"]))

    def test_rank_uses_all_eligible_before_target_filter(self):
        pool = pd.DataFrame({"signal_date": ["d"] * 4, "strategy": "retest",
                             "rs": [99., 95., 90., 86.],
                             "trade_status": ["closed", "open", "closed", "closed"]})
        r = B.add_rs_ranks(pool)
        self.assertEqual(list(r["rank_rs"]), [1.0, 0.75, 0.5, 0.25])   # open trade still counted

    def test_sensitivity_feature_not_in_deciding_set(self):
        self.assertNotIn("earn_within_5", B.V2_FEATURES)
        self.assertEqual(B.SENSITIVITY_ONLY, ["earn_within_5"])


if __name__ == "__main__":
    unittest.main()
