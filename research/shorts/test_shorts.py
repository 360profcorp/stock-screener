"""Tests for the 10-year short study: independent eligibility, non-overlap rule, cost recompute,
short portfolio replay. Synthetic data only. Run: python -m unittest research.shorts.test_shorts
"""
import unittest

import numpy as np
import pandas as pd

from research.shorts import analyze as AN
from research.shorts import portfolio as PF
from research.sp1500 import engine as E
from research.sp1500 import rules as R

D = pd.bdate_range("2022-01-03", periods=40)


def closes(path):
    return {"AAA": pd.Series(path, index=D[:len(path)])}


def trade(**kw):
    t = dict(ticker="AAA", rs=10.0, signal_date=D[0], entry_date=D[1], entry=100.0, stop=105.0,
             exit_date=D[9], exit=90.0, dividends_ps=1.0)
    t.update(kw)
    return t


class Replay(unittest.TestCase):
    def test_one_short_by_hand(self):
        tr = pd.DataFrame([trade()])
        cv, fl, m = PF.replay(tr, closes([100.0] * 12), D[0], D[11])
        qty = 20                                                   # min(100/5, 2000/100)
        days = (D[9] - D[1]).days
        pnl = qty * 100 * .999 - qty * 90 * 1.001 - .03 * days / 365 * 100 * qty - qty * 1.0
        self.assertEqual(int(fl["qty"][0]), qty)
        self.assertAlmostEqual(fl["net_pnl"][0], pnl, places=6)
        self.assertAlmostEqual(cv["equity"].iloc[-1], 10000 + pnl, places=6)
        self.assertAlmostEqual(fl["net_r"][0], pnl / (qty * 5.0), places=9)

    def test_mark_to_market_while_short(self):
        path = [100.0, 100.0, 110.0] + [100.0] * 9
        cv, _, _ = PF.replay(pd.DataFrame([trade()]), closes(path), D[0], D[11])
        row = cv[cv["date"] == D[2]].iloc[0]
        self.assertAlmostEqual(row["equity"], 10000 + 20 * 100 * .999 - 20 * 110, places=6)

    def test_stop_on_the_entry_bar(self):
        tr = pd.DataFrame([trade(exit_date=D[1], exit=105.0)])
        _, fl, _ = PF.replay(tr, closes([100.0] * 5), D[0], D[4])
        self.assertEqual(fl["exit_date"][0], D[1])
        self.assertLess(fl["net_r"][0], -1)

    def test_limits_and_order(self):
        rows = [trade(ticker=t, rs=rs, exit_date=D[20]) for t, rs in
                (("E", 5.0), ("A", 9.0), ("B", 1.0), ("C", 3.0), ("D", 3.0))]
        cl = {t: pd.Series(100.0, index=D) for t in "ABCDE"}
        _, fl, m = PF.replay(pd.DataFrame(rows), cl, D[0], D[25])
        self.assertEqual(sorted(fl["ticker"]), ["B", "C", "D"])    # weakest RS, then ticker
        self.assertEqual(m["skipped"], {"daily_entries": 2})
        rows = [trade(ticker="A", entry_date=D[k], exit_date=D[30]) for k in (1, 2)]
        _, fl, m = PF.replay(pd.DataFrame(rows), {"A": pd.Series(100.0, index=D)}, D[0], D[35])
        self.assertEqual((len(fl), m["skipped"]), (1, {"ticker_open": 1}))

    def test_no_leverage(self):
        rows = [trade(ticker=t, stop=100.5, exit_date=D[20]) for t in "AB"]
        cl = {t: pd.Series(100.0, index=D) for t in "AB"}
        _, fl, m = PF.replay(pd.DataFrame(rows), cl, D[0], D[25], cap=1.0)
        self.assertEqual(m["skipped"].get("no_leverage"), 1)

    def test_open_trade_is_marked_not_exited(self):
        tr = pd.DataFrame([trade(exit_date=pd.NaT, exit=np.nan)])
        cv, fl, m = PF.replay(tr, closes([100.0] * 6 + [95.0]), D[0], D[6])
        self.assertEqual((len(fl), m["open_at_end"]), (0, 1))
        self.assertAlmostEqual(cv["equity"].iloc[-1], 10000 + 20 * 100 * .999 - 20 * 95, places=6)


def rows(n=400, seed=3):
    rng = np.random.default_rng(seed)
    return pd.DataFrame(dict(
        direction="short", strategy=rng.choice(AN.SHORTS, n), ticker=rng.choice(list("ABCD"), n),
        i=rng.integers(300, 900, n), rs_ref500=rng.choice([5, 15, 25, np.nan], n),
        rs_pit500=rng.choice([5, 15, 25, np.nan], n), rs_1500=rng.choice([5, 25], n),
        close=rng.choice([3.0, 20.0], n), adv20_usd=rng.choice([1e6, 9e6], n),
        risk_at_close_pct=rng.choice([-1.0, 2.0], n),
        spy_above50=rng.choice([True, False, None], n),
        trade_status=rng.choice(["closed", "closed", "open", "no_trade_gap_through_stop"], n),
        bars_held=rng.integers(0, 21, n)))


class Audits(unittest.TestCase):
    def test_independent_eligibility_equals_the_engine(self):
        s = rows()
        for rs in ("rs_ref500", "rs_pit500", "rs_1500"):
            for mk in ("primary", "off"):
                mine = AN.eligible(s, rs, mk)
                eng = E.rejection_reasons(s, rs_col=rs, market=mk) == ""
                self.assertTrue((mine == eng).all(), (rs, mk))
        prim = AN.eligible(s, "rs_ref500", "primary")
        self.assertFalse((prim & (s["spy_above50"] == True)).any())         # noqa: E712
        self.assertFalse((prim & s["spy_above50"].isna()).any())

    def test_nonoverlap_equals_simulate_rule(self):
        s = rows(800, seed=9).drop_duplicates(["ticker", "strategy", "i"])
        self.assertTrue((AN.nonoverlap_ref(s) == E.non_overlapping(s)).all())

    def test_costs_recomputed_from_first_principles(self):
        n = 60
        O = np.full(n, 100.0)
        H, L, C = O * 1.01, O * 0.99, O.copy()
        C[25:] = 90.0
        O[25:] = 90.0
        H[25:], L[25:] = 90.9, 89.1
        x = dict(O=O, H=H, L=L, C=C, dates=pd.bdate_range("2022-01-03", periods=n).values,
                 div=np.where(np.arange(n) == 10, 0.5, 0.0))
        r = E.model_trade(x, 5, "short", 103.0)
        r = E.apply_costs(dict(r, direction="short"))
        c = pd.DataFrame([r])
        risk = c["risk_pct"] / 100
        gross = -(c["exit"] / c["entry"] - 1)
        for sl, bps in R.SLIPPAGE_SCENARIOS_BPS.items():
            for b in AN.BORROWS:
                apr = R.BORROW_SCENARIOS_APR[b]
                want = (gross - bps / 1e4 * (c["entry"] + c["exit"]) / c["entry"]
                        - apr * c["calendar_days"] / 365 - 0.5 / c["entry"]) / risk
                self.assertAlmostEqual(float(want.iloc[0]), c[f"net_r_{sl}_{b}"][0], places=10)
        self.assertAlmostEqual(r["dividends_ps"], 0.5)

    def test_stats_per_scenario(self):
        d = pd.DataFrame(dict(trade_status="closed", gross_r=[2.0, -1.0, -1.0, 1.0]))
        s = AN.stats(d, "gross_r")
        self.assertEqual((s["trades"], s["win_rate"], s["profit_factor"], s["expectancy_r"]),
                         (4, 50.0, 1.5, 0.25))


if __name__ == "__main__":
    unittest.main()
