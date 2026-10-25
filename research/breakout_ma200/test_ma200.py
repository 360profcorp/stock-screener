"""Synthetic tests for the MA200 Quality & Exit study (no data, no network)."""
import unittest

import numpy as np
import pandas as pd

from research.breakout_ma200 import run as R


def bars(C, O=None, L=None, atr=1.0, start="2024-01-02"):
    d = pd.bdate_range(start, periods=len(C))
    C = np.asarray(C, float)
    return dict(dates=d, O=np.asarray(O if O is not None else C, float), H=C + .5,
                L=np.asarray(L if L is not None else C - .5, float), C=C,
                atr14=np.full(len(C), atr) if np.isscalar(atr) else np.asarray(atr, float))


def trade(x, entry=100., stop=95., reason="time"):
    d = x["dates"]
    return pd.Series(dict(ticker="T", date=d[0], exit_date=d[20], entry=entry, stop=stop, exit=x["C"][20],
                          reason=reason, status="closed", signal_date=d[0]))


class Runner(unittest.TestCase):
    def test_below_2r_exits_as_control(self):
        x = bars(list(np.linspace(100, 109.9, 21)) + [120] * 30)          # +1.98 R at day 20
        self.assertEqual(R.runner_exit(trade(x), x), {})

    def test_stops_unchanged(self):
        x = bars(np.linspace(100, 130, 60))
        self.assertEqual(R.runner_exit(trade(x, reason="stop"), x), {})

    def test_trailing_2atr_from_previous_closes(self):
        C = list(np.linspace(100, 112, 21)) + [114, 116, 115, 112]
        L = [c - .5 for c in C]
        L[24] = 111.9                                                     # level = 116 - 2*2 = 112 -> hit on bar 24
        x = bars(C + [112] * 30, L=L + [111.5] * 30, atr=2.0)
        r = R.runner_exit(trade(x), x)
        self.assertEqual(r["reason"], "runner_stop")
        self.assertEqual(r["exit_date"], x["dates"][24])
        self.assertAlmostEqual(r["exit"], min(x["O"][24], 112.0))

    def test_level_uses_atr_of_previous_session_and_never_falls(self):
        C = list(np.linspace(100, 112, 21)) + [113, 113, 113]
        atr = np.full(60, 1.0)
        atr[22] = 10.0                                                   # a later wide ATR cannot lower the level
        L = [c - .5 for c in C] + [110.5] * 36
        L[23] = 110.9                                                    # level after bar 21: 113 - 2 = 111 -> hit on bar 23
        x = bars(C + [111] * 36, L=L, atr=atr)
        r = R.runner_exit(trade(x), x)
        self.assertEqual(r["exit_date"], x["dates"][23])
        self.assertAlmostEqual(r["exit"], min(x["O"][23], 111.0))

    def test_not_below_original_stop_and_hard_exit_40(self):
        x = bars(list(np.linspace(100, 111, 21)) + list(np.linspace(111, 125, 30)), atr=50.0)   # huge ATR
        r = R.runner_exit(trade(x), x)                                   # level stays at the stop (95): no exit
        self.assertEqual((r["reason"], r["days"]), ("runner_time40", 40))
        self.assertAlmostEqual(r["exit"], x["C"][40])

    def test_gap_fills_at_open(self):
        C = list(np.linspace(100, 112, 21)) + [113, 100]
        O = list(C)
        O[22] = 99.0
        x = bars(C + [100] * 30, O=O + [100] * 30, L=[c - .5 for c in C] + [99.5] * 30)
        self.assertEqual(R.runner_exit(trade(x), x)["exit"], 99.0)

    def test_data_end_marks_open(self):
        x = bars(list(np.linspace(100, 112, 21)) + [113, 114])
        r = R.runner_exit(trade(x), x)
        self.assertEqual((r["status"], r["mark"]), ("open", 114.0))


class Other(unittest.TestCase):
    def test_quality_filter_on_actual_entry(self):
        t = pd.DataFrame(dict(entry=[100., 100., 50.], stop=[96.01, 96., 48.]))
        self.assertEqual(list(R.quality_filter(t).index), [0, 1])
        self.assertEqual(len(R.quality_filter(t)), 2)                    # 3.99 % excluded; 4.0 % kept

    def test_spy_stats(self):
        d = pd.bdate_range("2020-01-01", periods=300)
        spy = pd.DataFrame(dict(Close=np.r_[np.full(10, 100.), np.linspace(100, 80, 100), np.linspace(80, 120, 190)]), index=d)
        s = R.spy_stats(spy, d[10], d[-1])
        self.assertAlmostEqual(s["return_pct"], 20.0)
        self.assertAlmostEqual(s["max_dd_pct"], -20.0)

    def test_next_open_check(self):
        x = bars(np.linspace(100, 110, 10), O=np.linspace(99, 109, 10))
        ok = pd.DataFrame([dict(ticker="T", signal_date=x["dates"][2], date=x["dates"][3], entry=x["O"][3])])
        bad = pd.DataFrame([dict(ticker="T", signal_date=x["dates"][2], date=x["dates"][3], entry=x["C"][2])])
        self.assertEqual(R.next_open_check(ok, {"T": x})["violations"], 0)
        self.assertEqual(R.next_open_check(bad, {"T": x})["violations"], 1)

    def test_decide(self):
        def m(c, pf, dd, r=0):
            return dict(cagr_pct=c, profit_factor=pf, max_dd_pct=dd, return_pct=r)
        B = {}
        for w in ("full", "y2017_2021", "y2022_2026"):
            for b in (10, 25, 50):
                B[f"M|{w}|{b}"] = m(4, 1.1, -32, 40)
                B[f"A|{w}|{b}"] = m(5, 1.2, -33, 50)
                B[f"B|{w}|{b}"] = m(5 if w != "y2017_2021" else 3, 1.2, -32, 50)
        d = R.decide(B, dict(p80=45))
        self.assertEqual(d["A"]["verdict"], "supported (exploratory)")
        self.assertEqual(d["B"]["verdict"], "not supported")
        self.assertEqual(R.decide(B, dict(p80=55))["A"]["verdict"], "not supported")


if __name__ == "__main__":
    unittest.main()
