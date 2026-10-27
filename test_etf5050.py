"""50/50 SPY/BIL paper book: activation, timing, rebalancing, fees, dividends, identities."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import paper_etf as P
from paper import nyse


def bars(start="2026-09-21", end="2026-11-20", spy=500.0, bil=91.5, spy_div=None, bil_div=None, gap=None):
    days = pd.DatetimeIndex([d for d in pd.bdate_range(start, end) if nyse.is_session(d)])
    out = {}
    for s, base, divs in (("SPY", spy, spy_div or {}), ("BIL", bil, bil_div or {})):
        k = np.arange(len(days))
        c = base * (1 + (0.001 if s == "SPY" else 0.0001)) ** k
        df = pd.DataFrame(dict(Open=c * 0.999, High=c * 1.01, Low=c * 0.99, Close=c, Volume=1e6), index=days)
        df["Dividends"] = 0.0
        for d, a in divs.items():
            df.loc[pd.Timestamp(d), "Dividends"] = a
        df["Stock Splits"] = 0.0
        out[s] = df
    if gap:
        out["BIL"] = out["BIL"].drop(pd.Timestamp(gap))
    return out


def at(day, hh=22, mm=15):
    return datetime(*pd.Timestamp(day).timetuple()[:3], hh, mm, tzinfo=timezone.utc)


class Book(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def run_on(self, b, day, **kw):
        sub = {s: f[f.index <= pd.Timestamp(day)] for s, f in b.items()}
        return P.run_daily(bars=sub, now=at(day, **kw), folder=self.dir)

    def test_activation_buys_nothing_and_queues_next_open(self):
        b = bars()
        s = self.run_on(b, "2026-10-26")
        self.assertEqual(s["activation_session"], "2026-10-26")
        self.assertEqual(s["fills"], [])
        self.assertEqual(s["shares"], {"SPY": 0, "BIL": 0})
        self.assertEqual(len(s["equity"]), 1)
        self.assertEqual(s["equity"][0]["equity"], 10000.0)
        self.assertEqual(s["pending"][0]["scheduled_for"], "2026-10-27")
        self.assertFalse(s["pending"][0]["late"])

    def test_first_fill_at_next_open_sized_50_50(self):
        b = bars()
        self.run_on(b, "2026-10-26")
        s = self.run_on(b, "2026-10-27")
        f = pd.DataFrame(s["fills"])
        self.assertEqual(set(f["date"]), {"2026-10-27"})
        self.assertTrue((f["side"] == "BUY").all())
        for _, r in f.iterrows():
            self.assertAlmostEqual(r["price"], float(b[r["symbol"]].loc["2026-10-27", "Open"]))
        w = s["equity"][-1]
        tol = float(b["SPY"].loc["2026-10-27", "Close"]) / 10000 + 0.01     # whole-share granularity
        self.assertAlmostEqual(w["w_SPY"], 0.5, delta=tol)
        self.assertAlmostEqual(w["w_BIL"], 0.5, delta=tol)
        self.assertLessEqual(w["w_SPY"], 0.5)                                 # never above target
        self.assertGreater(s["fees_total"], 0)
        self.assertGreaterEqual(s["cash"], 0)

    def test_monthly_rebalance_decided_on_last_session_executed_next(self):
        b = bars()
        self.run_on(b, "2026-10-26")
        self.run_on(b, "2026-10-27")
        s = self.run_on(b, "2026-10-30")                   # last session of October
        self.assertEqual(s["pending"][-1]["scheduled_for"], "2026-11-02")
        self.assertEqual(s["pending"][-1]["decided_on"], "2026-10-30")
        s = self.run_on(b, "2026-11-02")
        r = s["rebalances"][-1]
        self.assertEqual((r["decided_on"], r["executed_on"], r["reason"]), ("2026-10-30", "2026-11-02",
                                                                             "monthly_rebalance"))
        self.assertEqual(s["pending"], [])
        P.reconcile(s)

    def test_rerun_same_day_is_idempotent_and_catchup_flags_late(self):
        b = bars()
        self.run_on(b, "2026-10-26")
        a = self.run_on(b, "2026-10-27")
        n = len(a["equity"])
        a2 = self.run_on(b, "2026-10-27")
        self.assertEqual(len(a2["equity"]), n)
        self.assertEqual(len(a2["fills"]), len(a["fills"]))
        d2 = Path(tempfile.mkdtemp())
        P.run_daily(bars={s: f[f.index <= "2026-10-26"] for s, f in b.items()}, now=at("2026-10-26"), folder=d2)
        late = P.run_daily(bars={s: f[f.index <= "2026-10-28"] for s, f in b.items()}, now=at("2026-10-28"),
                           folder=d2)                      # missed the 27th's evening; fills are reconstructed
        self.assertTrue(all(f["late"] for f in late["fills"]))

    def test_dividends_receivable_then_cash_on_pay_date(self):
        b = bars(bil_div={"2026-11-02": 0.30})
        self.run_on(b, "2026-10-26")
        self.run_on(b, "2026-10-27")
        s = self.run_on(b, "2026-11-02")
        held = s["shares"]["BIL"]
        self.assertTrue(s["receivables"])
        amt = s["receivables"][0]["amount"]
        self.assertGreater(amt, 0)
        pay = s["receivables"][0]["pay_date"]
        s = self.run_on(b, pay)
        self.assertEqual(s["receivables"], [])
        self.assertAlmostEqual(s["dividends_received"], amt)
        self.assertTrue(s["dividends"][0]["paid"])
        P.reconcile(s)
        self.assertGreater(held, 0)

    def test_missing_bar_stops_processing(self):
        b = bars(gap="2026-10-28")
        self.run_on(b, "2026-10-26")
        s = self.run_on(b, "2026-10-29")
        self.assertEqual(s["processed_through"], "2026-10-27")
        self.assertTrue(s["problems"])

    def test_no_strategy_logic_and_other_books_untouched(self):
        src = Path(P.__file__).read_text()
        for w in ("rs_history", "retest_at", "breakout_at", "stop_buf", "hold_days", "ma200", "ma50"):
            self.assertNotIn(w, src)
        self.assertEqual(P.DIR.relative_to(P.ROOT).as_posix(), "paper/etf5050")

    def test_pay_dates(self):
        self.assertEqual(str(P.pay_date("SPY", "2026-09-18").date()), "2026-10-30")
        self.assertEqual(str(P.pay_date("BIL", "2026-11-02").date()), "2026-11-09")


if __name__ == "__main__":
    unittest.main()
