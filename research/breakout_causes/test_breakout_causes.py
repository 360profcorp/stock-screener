"""Synthetic tests (no data, no network)."""
import unittest

import numpy as np
import pandas as pd

from research.breakout_causes import run as BC


def bars(C, O=None, L=None, start="2024-01-02"):
    d = pd.bdate_range(start, periods=len(C))
    C = np.asarray(C, float)
    return dict(dates=d, O=np.asarray(O if O is not None else C, float), H=C + .5,
                L=np.asarray(L if L is not None else C - .5, float), C=C)


def trade(x, e=0, entry=100., stop=95., reason="time"):
    d = x["dates"]
    return pd.Series(dict(ticker="T", date=d[e], exit_date=d[e + 20], entry=entry, stop=stop, exit=x["C"][e + 20],
                          reason=reason, status="closed", signal_date=d[e]))


class H3(unittest.TestCase):
    def test_weak_position_unchanged(self):
        x = bars([100] * 21 + [104] * 50)                       # close at bar 20 = 100 < 105
        self.assertEqual(BC.extend_strong(trade(x), x), {})

    def test_stop_and_open_trades_unchanged(self):
        x = bars(np.linspace(100, 130, 80))
        self.assertEqual(BC.extend_strong(trade(x, reason="stop"), x), {})

    def test_trailing_exit_uses_previous_closes(self):
        C = list(np.linspace(100, 110, 21)) + [112, 115, 113, 108, 107]
        L = [c - .5 for c in C]
        L[25] = 109.0                                            # trail = max(100, 115 - 5) = 110 -> hit
        x = bars(C + [107] * 50, L=L + [106.5] * 50)
        r = BC.extend_strong(trade(x), x)
        self.assertEqual(r["reason"], "trail")
        self.assertEqual(r["exit_date"], x["dates"][24])         # bar 24: low 107.5 <= 110
        self.assertAlmostEqual(r["exit"], min(x["O"][24], 110.0))

    def test_hard_exit_at_bar_60_and_breakeven_floor(self):
        x = bars(list(np.linspace(100, 106, 21)) + list(np.linspace(106, 140, 60)))
        r = BC.extend_strong(trade(x), x)
        self.assertEqual((r["reason"], r["days"]), ("time60", 60))
        self.assertAlmostEqual(r["exit"], x["C"][60])

    def test_gap_fills_at_open(self):
        C = list(np.linspace(100, 110, 21)) + [111, 99]
        O = list(C)
        O[22] = 98.0
        x = bars(C + [99] * 50, O=O + [99] * 50, L=[c - .5 for c in C] + [98.5] * 50)
        r = BC.extend_strong(trade(x), x)
        self.assertEqual(r["exit"], 98.0)                         # min(open 98, stop 106) = 98


class Split(unittest.TestCase):
    def test_parts_add_up_exactly(self):
        x = bars([100, 102, 101, 96, 94, 97] + [97] * 30)
        data = {"T": x}
        d = x["dates"]
        rows = pd.DataFrame([dict(ticker="T", signal_date=d[0], date=d[1], exit_date=d[4], entry=102., stop=97.,
                                  exit=94., reason="stop", risk_pct=100 * 5 / 102, shares=10.),
                             dict(ticker="T", signal_date=d[0], date=d[1], exit_date=d[5], entry=102., stop=97.,
                                  exit=97.5, reason="time", risk_pct=100 * 5 / 102, shares=4.)])
        s = BC.split_execution(rows, data, 10)
        r0 = s.iloc[0]
        self.assertAlmostEqual(r0["signal_quality_usd"], 10 * (97 - 100))
        self.assertAlmostEqual(r0["entry_gap_usd"], -10 * 2)
        self.assertAlmostEqual(r0["stop_gap_usd"], 10 * (94 - 97))
        self.assertAlmostEqual(r0["net_usd"], 10 * (94 - 102) - 10 * (102 + 94) * .001)
        self.assertAlmostEqual(s.iloc[1]["stop_gap_usd"], 0.0)

    def test_post_exit_vs_spy_same_dates(self):
        x = bars(np.r_[100, np.linspace(100, 110, 30)])
        spy = pd.DataFrame(dict(Close=np.linspace(400, 430, 31)), index=x["dates"])
        e = pd.DataFrame([dict(ticker="T", exit_date=x["dates"][3], reason="time")])
        P = BC.post_exit_vs_spy(e, {"T": x}, spy)
        s = x["C"][8] / x["C"][3] - 1
        m = spy["Close"].iloc[8] / spy["Close"].iloc[3] - 1
        self.assertAlmostEqual(P.loc[0, "excess_5"], 100 * (s - m))
        self.assertNotIn("excess_20", P.columns.intersection(["excess_40"]))

    def test_h1_threshold(self):
        t = pd.DataFrame(dict(risk_pct=[3.99, 4.0, 7.0]))
        self.assertEqual(len(BC.h1(t)), 2)


class Decide(unittest.TestCase):
    def test_all_criteria_needed(self):
        def m(r, pf, dd):
            return dict(return_pct=r, profit_factor=pf, max_dd_pct=dd)
        B = {}
        for w in ("full", "first_half", "second_half"):
            for b in (10, 25):
                B[f"C|{w}|{b}"] = m(0, 1.0, -40)
                B[f"H1|{w}|{b}"] = m(5, 1.1, -41)
                B[f"H2|{w}|{b}"] = m(5, 1.1, -45)           # DD 5 pt deeper
                B[f"H3|{w}|{b}"] = m(5 if w != "first_half" else -1, 1.1, -40)
        d = BC.decide(B, {"H1": dict(p80=4.0), "H2": dict(p80=1.0)})
        self.assertEqual(d["H1"]["verdict"], "supported (exploratory)")
        self.assertEqual(d["H2"]["verdict"], "not supported")
        self.assertEqual(d["H3"]["verdict"], "not supported")


if __name__ == "__main__":
    unittest.main()
