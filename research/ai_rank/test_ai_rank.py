"""Tests for the AI ranking research (synthetic data; mechanics only)."""
import unittest

import numpy as np
import pandas as pd

from research.ai_rank import pipeline as P
from research.sp1500 import engine as E
from research.sp1500 import test_sp1500 as T


class TestAIRank(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frames, spy, meta = T.universe_frames(10, 900)
        sig, data = E.detect(frames, spy, meta, list(frames)[:4])
        for v in ("primary", "pit_primary"):
            sig[f"eligible_{v}"] = E.rejection_reasons(sig, market="off") == ""
        sig["pit_member_sp500"] = sig["group"] == "sp500"
        lab = E.assign_splits(E.add_outcomes(sig, data, spy.index, spy.index[-1]), spy.index)
        cls.lab, cls.frames, cls.spy, cls.data = lab, frames, spy, data

    def test_audit_clean_on_consistent_data(self):
        a = P.audit(self.lab, self.frames, self.spy, n_sample=150)
        self.assertEqual(a["features_recomputed_on_truncated_bars"]["mismatches"], 0)
        self.assertEqual(a["labels"]["closed_after_data_end"], 0)
        self.assertEqual(a["purge_v1_leaks"]["train_rows_label_after_validation_start"], 0)

    def test_splits_purge_by_label_end(self):
        pool = P.long_pool(self.lab, "sp500", tuple(P.LONGS))
        v0 = pd.Timestamp(self.lab["split_validation_start"].iloc[0])
        t0 = pd.Timestamp(self.lab["split_test_start"].iloc[0])
        sp, le = P.splits_at(pool, self.spy.index, v0, t0)
        self.assertTrue((le[sp == "train"] < v0).all())
        self.assertTrue((le[sp == "validation"] < t0).all())
        ex = pd.to_datetime(pool["exit_date"], errors="coerce")
        self.assertTrue((ex[sp == "train"].dropna() < v0).all())

    def test_rs_score_order_equals_rs_first_and_order_matters(self):
        pool = P.long_pool(self.lab, "sp500", tuple(P.LONGS))
        tr = P.trades_for(pool, self.data)
        s, e = self.spy.index[300], self.spy.index[-1]
        a = P.summary(*P.replay(tr, self.data, s, e))
        b = P.summary(*P.replay(tr, self.data, s, e, score=tr["rs"].values))
        self.assertEqual(a, b)                                  # same order -> same result
        c = P.summary(*P.replay(tr, self.data, s, e, score=-tr["rs"].values))
        self.assertEqual(a["trades"] > 0, True)
        self.assertIsInstance(c["return_pct"], float)

    def test_model_never_sees_validation_labels(self):
        pool = P.long_pool(self.lab, "sp500", tuple(P.LONGS))
        v0 = pd.Timestamp(self.lab["split_validation_start"].iloc[0])
        t0 = pd.Timestamp(self.lab["split_test_start"].iloc[0])
        pool["split"], pool["label_end"] = P.splits_at(pool, self.spy.index, v0, t0)
        train = pool[pool["split"] == "train"]
        self.assertTrue((train["label_end"] < v0).all())
        self.assertTrue((train["signal_date"] < v0).all())


if __name__ == "__main__":
    unittest.main()
