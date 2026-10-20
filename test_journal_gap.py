"""Journal evaluation: stop exits, including gaps through the stop (core.evaluate_journal)."""
import unittest

import numpy as np
import pandas as pd

import core

ENTRY, STOP = 100.0, 95.0


def prices(n=12, overrides=None, ticker="AAA"):
    idx = pd.bdate_range("2026-10-13", periods=n)               # first bar = day 1 after signal
    df = pd.DataFrame({"Open": 100.5, "High": 101.0, "Low": 99.0, "Close": 100.0 + np.arange(n),
                       "Volume": 1e6}, index=idx)
    for day, vals in (overrides or {}).items():                 # day is 1-based
        for col, v in vals.items():
            df.iloc[day - 1, df.columns.get_loc(col)] = v
    return pd.concat({ticker: df}, axis=1)


def journal(ticker="AAA"):
    return pd.DataFrame([dict(date="2026-10-12", mode="breakout", ticker=ticker, rs=90,
                              close=ENTRY, stop=STOP)])


def ev(px):
    return core.evaluate_journal(journal(), px).iloc[0]


class TestJournalStops(unittest.TestCase):
    def test_normal_stop_exits_at_the_stop(self):
        r = ev(prices(overrides={3: {"Open": 98.0, "Low": 94.0}}))
        self.assertEqual((r["status"], r["stop_day"], r["exit_price"]), ("stopped", 3, STOP))
        self.assertFalse(r["gap_through_stop"])
        for k in ("ret_5d", "ret_10d", "ret_now"):
            self.assertAlmostEqual(r[k], STOP / ENTRY - 1, msg=k)

    def test_gap_below_the_stop_exits_at_the_open(self):
        r = ev(prices(overrides={3: {"Open": 90.0, "High": 91.0, "Low": 89.0, "Close": 90.5}}))
        self.assertEqual((r["stop_day"], r["exit_price"]), (3, 90.0))
        self.assertTrue(r["gap_through_stop"])
        for k in ("ret_5d", "ret_10d", "ret_now"):
            self.assertAlmostEqual(r[k], 90.0 / ENTRY - 1, msg=k)       # -10 %, not -5 %

    def test_recovery_after_the_stop_is_ignored(self):
        r = ev(prices(overrides={2: {"Open": 92.0, "Low": 91.0, "High": 93.0},
                                 8: {"High": 140.0, "Close": 139.0}}))
        self.assertAlmostEqual(r["ret_now"], 92.0 / ENTRY - 1)
        self.assertAlmostEqual(r["ret_10d"], 92.0 / ENTRY - 1)
        self.assertAlmostEqual(r["max_up"], 101.0 / ENTRY - 1)           # only up to the stop day

    def test_stop_on_day_six_does_not_change_the_first_five_days(self):
        base = ev(prices())
        r = ev(prices(overrides={6: {"Open": 88.0, "High": 89.0, "Low": 87.0}}))
        self.assertEqual(r["stop_day"], 6)
        self.assertAlmostEqual(r["ret_5d"], base["ret_5d"])               # close of day 5
        self.assertAlmostEqual(r["ret_5d"], 104.0 / ENTRY - 1)
        self.assertAlmostEqual(r["ret_10d"], 88.0 / ENTRY - 1)            # gap exit on day 6
        self.assertAlmostEqual(r["ret_now"], 88.0 / ENTRY - 1)

    def test_gap_with_same_day_recovery_excludes_exit_day_high(self):
        r = ev(prices(overrides={3: {"Open": 90.0, "Low": 89.0, "High": 112.0, "Close": 110.0}}))
        self.assertTrue(r["gap_through_stop"])
        self.assertAlmostEqual(r["ret_now"], 90.0 / ENTRY - 1)
        self.assertAlmostEqual(r["max_up"], 101.0 / ENTRY - 1)       # days 1-2 only, not 112

    def test_gap_on_the_first_day_after_the_signal(self):
        r = ev(prices(overrides={1: {"Open": 91.0, "Low": 90.0, "High": 104.0, "Close": 103.0}}))
        self.assertEqual((r["stop_day"], r["exit_price"]), (1, 91.0))
        for k in ("ret_5d", "ret_10d", "ret_now"):
            self.assertAlmostEqual(r[k], 91.0 / ENTRY - 1, msg=k)
        self.assertAlmostEqual(r["max_up"], 91.0 / ENTRY - 1)        # only the exit price

    def test_missing_or_invalid_open_asserts_no_exit(self):
        for bad in (np.nan, 0.0, 120.0):                             # missing / zero / above High
            r = ev(prices(overrides={3: {"Open": bad, "Low": 94.0}}))
            self.assertEqual((r["status"], r["stop_day"]), ("stopped", 3), bad)
            self.assertTrue(r["insufficient_data"], bad)
            self.assertTrue(np.isnan(r["exit_price"]), bad)          # the stop is NOT assumed
            for k in ("ret_5d", "ret_10d", "ret_now"):
                self.assertTrue(np.isnan(r[k]), (bad, k))
        ok = ev(prices(overrides={3: {"Open": 98.0, "Low": 94.0}}))
        self.assertFalse(ok["insufficient_data"])

    def test_invalid_open_after_the_horizon_keeps_earlier_results(self):
        r = ev(prices(overrides={7: {"Open": np.nan, "Low": 94.0}}))
        self.assertAlmostEqual(r["ret_5d"], 104.0 / ENTRY - 1)       # day 5 is before the stop
        self.assertTrue(np.isnan(r["ret_10d"]) and np.isnan(r["ret_now"]))

    def test_horizons_not_reached_stay_empty(self):
        r = ev(prices(n=4, overrides={2: {"Open": 90.0, "Low": 89.0}}))
        self.assertTrue(np.isnan(r["ret_5d"]) and np.isnan(r["ret_10d"]))
        self.assertAlmostEqual(r["ret_now"], 90.0 / ENTRY - 1)

    def test_no_stop_unchanged(self):
        r = ev(prices())
        self.assertEqual(r["status"], "done10")
        self.assertTrue(pd.isna(r.get("exit_price", np.nan)))
        self.assertAlmostEqual(r["ret_now"], 111.0 / ENTRY - 1)


if __name__ == "__main__":
    unittest.main()
