"""Tests for trade_metrics (per-strategy trading-bot stats).

    python -m unittest test_trade_metrics -v
"""
import math
import unittest

import numpy as np
import pandas as pd

import trade_metrics as tm


def C(ticker, mode, pnl, r, entry_date="2026-09-01", exit_date="2026-09-15"):
    return {"ticker": ticker, "mode": mode, "entry_date": entry_date, "entry": 100.0,
            "exit_date": exit_date, "exit": 110.0, "qty": 1, "reason": "time",
            "pnl": pnl, "r": r, "dry": True}


# breakout: +100/+2.0, -50/-1.0 ; retest: +40/+1.2 ; vcp: 0/0.0 (breakeven=loser), -30/-1.0
CLOSED = [
    C("AAA", "breakout", 100.0, 2.0, "2026-09-01", "2026-09-15"),
    C("BBB", "breakout", -50.0, -1.0, "2026-09-02", "2026-09-09"),
    C("CCC", "retest", 40.0, 1.2, "2026-09-03", "2026-09-17"),
    C("DDD", "vcp", 0.0, 0.0, "2026-09-04", "2026-09-11"),
    C("EEE", "vcp", -30.0, -1.0, "2026-09-05", "2026-09-12"),
]
POSITIONS = [
    {"ticker": "FFF", "mode": "breakout", "entry_date": "2026-10-01", "entry": 50, "qty": 2},
    {"ticker": "GGG", "mode": "retest", "entry_date": "2026-10-02", "entry": 60, "qty": 1},
    {"ticker": "HHH", "mode": "retest", "entry_date": "2026-10-03", "entry": 70, "qty": 1},
]


class TestStrategyStats(unittest.TestCase):
    def test_all(self):
        s = tm.strategy_stats(CLOSED, POSITIONS, "all")
        self.assertEqual(s["total_trades"], 5)
        self.assertEqual(s["open_positions"], 3)
        self.assertAlmostEqual(s["total_pnl_usd"], 60.0)
        self.assertAlmostEqual(s["avg_pnl_usd"], 12.0)
        self.assertAlmostEqual(s["win_rate_pct"], 40.0)          # 2 of 5 pnl>0
        self.assertAlmostEqual(s["profit_factor"], 140.0 / 80.0)  # 1.75
        self.assertAlmostEqual(s["avg_winner_usd"], 70.0)         # (100+40)/2
        self.assertAlmostEqual(s["avg_loser_usd"], -80.0 / 3)     # (-50+0-30)/3
        self.assertAlmostEqual(s["expectancy_r"], (2.0 - 1.0 + 1.2 + 0.0 - 1.0) / 5)
        self.assertIsNone(s["max_drawdown_pct"])                  # no equity model

    def test_breakout_only(self):
        s = tm.strategy_stats(CLOSED, POSITIONS, "breakout")
        self.assertEqual(s["total_trades"], 2)
        self.assertEqual(s["open_positions"], 1)
        self.assertAlmostEqual(s["total_pnl_usd"], 50.0)
        self.assertAlmostEqual(s["win_rate_pct"], 50.0)
        self.assertAlmostEqual(s["profit_factor"], 2.0)
        self.assertAlmostEqual(s["avg_winner_usd"], 100.0)
        self.assertAlmostEqual(s["avg_loser_usd"], -50.0)
        self.assertAlmostEqual(s["expectancy_r"], 0.5)

    def test_retest_has_no_losers_so_profit_factor_is_none(self):
        s = tm.strategy_stats(CLOSED, POSITIONS, "retest")
        self.assertEqual(s["total_trades"], 1)
        self.assertEqual(s["open_positions"], 2)
        self.assertEqual(s["win_rate_pct"], 100.0)
        self.assertIsNone(s["profit_factor"])                     # no losing trades
        self.assertIsNone(s["avg_loser_usd"])

    def test_holding_days_nyse_calendar(self):
        # NYSE sessions (Labor Day 2026-09-07 excluded):
        #   09-01 -> 09-15 = 9 sessions ; 09-02 -> 09-09 = 4 sessions
        s = tm.strategy_stats(CLOSED, None, "breakout")
        self.assertIsNone(s["open_positions"])                    # positions not provided
        self.assertAlmostEqual(s["avg_holding_days"], (9 + 4) / 2)

    def test_holding_days_excludes_nyse_holiday(self):
        # 09-04 (Fri) -> 09-08 (Tue): Mon 09-07 is Labor Day, so 1 session, not 2
        self.assertEqual(tm.holding_days("2026-09-04", "2026-09-08"), 1.0)
        self.assertTrue(np.isnan(tm.holding_days(None, "2026-09-08")))
        self.assertTrue(np.isnan(tm.holding_days("2026-09-04", "not-a-date")))

    def test_empty(self):
        s = tm.strategy_stats([], [], "all")
        self.assertEqual(s["total_trades"], 0)
        self.assertEqual(s["open_positions"], 0)
        self.assertEqual(s["total_pnl_usd"], 0.0)
        self.assertIsNone(s["win_rate_pct"])
        self.assertIsNone(s["profit_factor"])
        self.assertIsNone(s["expectancy_r"])

    def test_missing_r_still_counts_pnl(self):
        rows = [C("X", "vcp", 10.0, None), C("Y", "vcp", -5.0, -0.5)]
        s = tm.strategy_stats(rows, None, "vcp")
        self.assertEqual(s["total_trades"], 2)
        self.assertAlmostEqual(s["total_pnl_usd"], 5.0)           # both counted
        self.assertAlmostEqual(s["expectancy_r"], -0.5)          # only the one with R


class TestComparison(unittest.TestCase):
    def test_rows_one_per_strategy_in_order(self):
        rows = tm.comparison_rows(CLOSED, POSITIONS)
        self.assertEqual([r["strategy"] for r in rows], list(tm.STRATEGIES))
        self.assertEqual(rows[0]["total_trades"], 2)             # breakout
        self.assertEqual(rows[2]["total_trades"], 2)             # vcp


class TestCumulativePnl(unittest.TestCase):
    def test_cumsum_and_order(self):
        w = tm.cumulative_pnl_by_strategy(CLOSED, "all")
        self.assertTrue(w.index.is_monotonic_increasing)
        # final cumulative values equal each strategy's total pnl
        self.assertAlmostEqual(w["breakout"].iloc[-1], 50.0)
        self.assertAlmostEqual(w["retest"].iloc[-1], 40.0)
        self.assertAlmostEqual(w["vcp"].iloc[-1], -30.0)

    def test_empty(self):
        self.assertTrue(tm.cumulative_pnl_by_strategy([], "all").empty)


class TestRValues(unittest.TestCase):
    def test_values(self):
        r = tm.r_values(CLOSED, "breakout")
        self.assertEqual(sorted(r.tolist()), [-1.0, 2.0])
        self.assertEqual(len(tm.r_values([], "all")), 0)


class TestSparseRecords(unittest.TestCase):
    """Old/partial state rows must never crash the metrics."""

    SPARSE = [
        {"ticker": "A", "pnl": 10.0},                                  # no mode/r/dates
        {"ticker": "B", "mode": "vcp", "pnl": "bad", "r": None},       # non-numeric pnl
        {"mode": "breakout", "entry_date": "2026-09-01", "exit_date": "2026-09-15",
         "pnl": -5.0, "r": -0.5},                                      # no ticker
        {},                                                            # empty row
    ]

    def test_all_does_not_crash_and_counts_numeric_pnl(self):
        s = tm.strategy_stats(self.SPARSE, None, "all")
        self.assertEqual(s["total_trades"], 4)
        self.assertAlmostEqual(s["total_pnl_usd"], 5.0)                # 10 + (-5); "bad"->NaN
        self.assertAlmostEqual(s["expectancy_r"], -0.5)               # only one real R

    def test_strategy_filter_on_missing_mode(self):
        s = tm.strategy_stats(self.SPARSE, None, "breakout")
        self.assertEqual(s["total_trades"], 1)
        self.assertAlmostEqual(s["total_pnl_usd"], -5.0)

    def test_cumulative_drops_rows_without_exit_date(self):
        w = tm.cumulative_pnl_by_strategy(self.SPARSE, "all")
        # only the breakout row has a usable exit_date
        self.assertEqual(list(w.columns), ["breakout"])
        self.assertAlmostEqual(w["breakout"].iloc[-1], -5.0)

    def test_comparison_rows_never_raise(self):
        rows = tm.comparison_rows(self.SPARSE, None)
        self.assertEqual([r["strategy"] for r in rows], list(tm.STRATEGIES))


if __name__ == "__main__":
    unittest.main()
