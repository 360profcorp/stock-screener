"""Synthetic tests for the Turnover & Selection Audit (no data, no network)."""
import unittest

import numpy as np
import pandas as pd

import backtest as bt
import portfolio_bt as pf
from research.breakout_ma200 import run as R
from research.crisis import run as CR
from research.long_diagnostic.test_diagnostic import market
from research.turnover_selection import run as TS


def setup(seed=4):
    fr, spy = market(seed, n_t=30, n=700)
    sig, data = bt.find_signals(fr, modes=["breakout"])
    for x in data.values():
        x["atr14"] = pd.Series(np.maximum(x["H"] - x["L"], 0)).rolling(14).mean().values
    M = bt.simulate(sig, data, "breakout", hold=20, stop_buf=3.0, min_rs=0, min_vol=0.0, max_risk=0.0,
                    market_ok=None, entry_at="open", one_per_ticker=False, include_open=True)
    M["date"] = pd.to_datetime(M["date"]).dt.normalize()
    M = M.sort_values(["date", "rs", "ticker"], ascending=[True, False, True], kind="stable").reset_index(drop=True)
    return spy, data, M


class Books(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spy, cls.data, cls.M = setup()
        cls.B = R.runner_book(cls.M, cls.data)
        cls.cal = sorted(cls.spy.index)

    def test_b0_keeps_b_dates_and_m_prices(self):
        B0 = TS.b0_book(self.M, self.B)
        r = self.B["runner"] & (self.B["status"] == "closed")
        self.assertGreater(r.sum(), 0)
        self.assertTrue((B0.loc[r, "exit_date"] == self.B.loc[r, "exit_date"]).all())
        self.assertTrue(np.allclose(B0.loc[r, "exit"], self.M.loc[r, "exit"]))
        self.assertTrue(B0.loc[~r].equals(self.B.loc[~r]))

    def test_split_adds_up_exactly(self):
        s0, s1 = self.cal[260], self.cal[-1]
        for bps in (10, 25):
            cm, em, mm = TS.replay(self.M, self.data, s0, s1, bps)
            cb, eb, mb = TS.replay(self.B, self.data, s0, s1, bps)
            sp = TS.split_b_vs_m(em, mm, eb, mb, cm, cb, bps)            # raises if the parts do not add up
            parts = sum(v["usd"] for k, v in sp.items() if not k.startswith("total"))
            self.assertAlmostEqual(parts, sp["total (profit B - profit M)"]["usd"], places=2)

    def test_extend_all_and_apply(self):
        ext = TS.extend_all(self.M, self.data)
        self.assertEqual(len(ext), int(((self.M["reason"] == "time") & (self.M["status"] == "closed")).sum()))
        keys = list(ext)[:5]
        t = TS.apply_ext(self.M, ext, keys)
        self.assertTrue(all(t.at[k, "runner"] for k in keys))
        rest = t.drop(index=keys)[self.M.columns]
        pd.testing.assert_frame_equal(rest, self.M.drop(index=keys), check_dtype=False)

    def test_shuffle_keeps_days_and_set(self):
        t = TS.shuffle_day(self.M, 3)
        self.assertTrue(t["date"].is_monotonic_increasing)
        self.assertEqual(sorted(zip(t["ticker"], t["date"])), sorted(zip(self.M["ticker"], self.M["date"])))

    def test_selection_chain_identities(self):
        s0, s1 = self.cal[260], self.cal[-1]
        cm, em, mm = TS.replay(self.M, self.data, s0, s1, 10, decisions=True)
        s = TS.selection_chain(self.M[self.M["date"] >= s0], em, mm["decisions"], self.spy)
        a = s["all"]
        self.assertLessEqual(a["entered"], a["candidates"])
        t = s["terciles_n"]
        self.assertEqual(sum(t[k]["candidates"] for k in ("T1", "T2", "T3")), a["candidates"])


class Decision(unittest.TestCase):
    def test_rule(self):
        q = lambda p10, p50, p80, p90: dict(p10=p10, p50=p50, p80=p80, p90=p90)       # noqa: E731
        res = dict(books={f"B|full|{c}": dict(cagr_pct=5.0, profit_factor=1.2, max_dd_pct=-34.0) for c in (10, 25)},
                   controls=dict(R1={f"full|{c}": dict(cagr_pct=q(1, 2, 3, 4), profit_factor=q(1, 1, 1.1, 1.15),
                                                       max_dd_pct=q(-40, -32, -30, -29)) for c in (10, 25)}),
                   b_minus_b0={"full|10": 50.0, "full|25": 10.0})
        self.assertTrue(TS.decide(res)["verdict"].startswith("B shows"))
        res["b_minus_b0"]["full|25"] = -1.0
        self.assertIn("do not implement B", TS.decide(res)["verdict"])


if __name__ == "__main__":
    unittest.main()
