"""Tests for the parallel paper comparison (Breakout RS-first vs Retest RS-first control).
Synthetic, seeded data only. Run: python -m unittest test_compare -v
"""
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import backtest as bt
import compare_run as CR
import core
from paper import books as B
from paper import store
from paper import verify as V
from paper.screener import scan_day, truncate
from test_paper import market


def prices_of(fr, spy):
    return pd.concat({**fr, "SPY": spy}, axis=1)


class Identity(unittest.TestCase):
    def test_task10_fingerprint_unchanged(self):
        self.assertEqual(store.code_fingerprint()["combined"], "17454c61f631")

    def test_books_differ_only_in_the_detector(self):
        a, b = B.BOOKS["breakout"].as_dict(), B.BOOKS["retest"].as_dict()
        self.assertEqual({k for k in a if a[k] != b[k]}, {"mode"})
        self.assertEqual(B.BOOKS["retest"], store_default())
        self.assertNotEqual(B.strategy_id("breakout"), B.strategy_id("retest"))
        c = B.BOOKS["breakout"]
        self.assertEqual((c.min_rs, c.market_filter, c.risk_fraction, c.max_positions,
                          c.max_new_per_day, c.max_position_fraction, c.entry_at, c.cost_bps,
                          c.hold_days, c.stop_buf_pct, c.ranking),
                         (85, "ma50", .01, 5, 3, .2, "open", 10., 20, 3., "rs_first"))


def store_default():
    from paper.config import DEFAULT
    return DEFAULT


class Scanner(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fr, cls.spy = market(4, n_t=25, n=420)
        cls.sig, cls.data = bt.find_signals(cls.fr, modes=["breakout", "retest"])
        cls.mo = core.regime_mask(core.market_regime(cls.spy), "ma50")

    def test_control_scan_is_task10_scan_day(self):
        cfg = B.BOOKS["retest"]
        for day in self.spy.index[265::9]:
            a = B.scan_mode(truncate(self.fr, day), self.spy, day, cfg, already_truncated=True)
            c = scan_day(truncate(self.fr, day), self.spy, day, cfg, already_truncated=True)
            self.assertTrue(a.equals(c), day)

    def test_scanners_equal_history(self):
        for b in B.BOOKS:
            cfg = replace(B.BOOKS[b], min_rs=50)
            days = sorted(pd.to_datetime(self.sig[self.sig["mode"] == b]["date"])
                          .dt.normalize().unique())[::7]
            self.assertGreater(len(days), 5)
            for day, ok, detail in CR.screener_vs_history(self.fr, self.spy, self.sig, self.mo,
                                                          days, cfg):
                self.assertTrue(ok, (b, day, detail))

    def test_both_books_equal_replay_full_and_live(self):
        cal = V.calendar(self.data)
        for b in B.BOOKS:
            cfg = replace(B.BOOKS[b], min_rs=50)
            S, E = cal[270], cal[-1]
            r = V.compare(V.run_stepper(self.sig, self.data, self.mo, S, E, cfg),
                          V.reference_replay(self.sig, self.data, self.mo, S, E, cfg), cfg)
            self.assertTrue(r["ok"], (b, r))
            self.assertGreater(r["fills_ref"], 5)
            S2 = cal[-40]
            r = V.compare(CR.run_stepper_live(self.fr, self.spy, self.data, S2, E, cfg),
                          V.reference_replay(self.sig, self.data, self.mo, S2, E, cfg), cfg)
            self.assertTrue(r["ok"], (b, "live", r))

    def test_no_look_ahead(self):
        cfg = B.BOOKS["breakout"]
        day = self.spy.index[350]
        fut = {t: df.assign(Close=df["Close"].where(df.index <= day, df["Close"] * 3))
               for t, df in self.fr.items()}
        a = B.scan_mode(self.fr, self.spy, day, cfg)
        c = B.scan_mode(fut, self.spy, day, cfg)
        self.assertTrue(a.equals(c))


class Runner(unittest.TestCase):
    def setUp(self):
        self.fr, self.spy = market(8, n_t=20, n=380)
        self.prices = prices_of(self.fr, self.spy)
        self.uni = pd.DataFrame({"ticker": list(self.fr), "name": "", "sector": "Tech"})
        self.days = self.spy.index
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        # an existing Task 10 paper book that must never be touched
        old = self.root / "paper" / "state" / "portfolio.json"
        old.parent.mkdir(parents=True)
        old.write_text('{"kind": "forward", "experiment": "old-retest"}')
        (self.root / "paper" / "data").mkdir()
        (self.root / "paper" / "data" / "signals.csv").write_text("signal_date,ticker\n")
        self.old = {p: p.read_bytes() for p in (self.root / "paper").rglob("*") if p.is_file()}

    def tearDown(self):
        self.tmp.cleanup()

    def run_at(self, k, hour=23, **kw):
        d = self.days[k]
        now = datetime(d.year, d.month, d.day, hour, 0, tzinfo=timezone.utc)
        return CR.daily(universe=self.uni, prices=self.prices[self.prices.index <= d], now=now,
                        root=self.root, **kw)

    def state(self, b):
        return store.load_state(B.paths(b, self.root)["state_file"])

    def test_common_start_then_catch_up_idempotent_and_old_book_untouched(self):
        s1 = self.run_at(300)
        exp = json.loads(B.experiment_file(self.root).read_text())
        start = str(self.days[300].date())
        self.assertEqual(exp["start_session"], start)
        self.assertEqual(exp["first_entry_session"], store.next_session(self.days[300]))
        for b in B.BOOKS:
            st = self.state(b)
            self.assertEqual((st["start"], st["processed_through"]), (start, start))
            self.assertEqual(st["positions"], {})
            self.assertEqual(st["ledger"], [])
            self.assertAlmostEqual(st["equity"][0]["equity"], 10000.0)
            self.assertEqual(st["book"], b)
            for o in st["pending"]:                           # recorded before the next open
                self.assertFalse(store.is_late(o["generated_at"], o["scheduled_for"]))
        snaps = {b: json.loads((B.paths(b, self.root)["snapshots"] / f"{start}.json").read_text())
                 for b in B.BOOKS}
        self.assertEqual(snaps["breakout"]["meta"]["bars_sha"], snaps["retest"]["meta"]["bars_sha"])
        self.assertEqual(snaps["breakout"]["meta"]["source"]["universe_sha"],
                         snaps["retest"]["meta"]["source"]["universe_sha"])
        sig_rows = {b: len(pd.read_csv(B.paths(b, self.root)["signals"]))
                    if B.paths(b, self.root)["signals"].exists() else 0 for b in B.BOOKS}
        # catch-up: 3 sessions missed, then a timely one
        s2 = self.run_at(304)
        self.assertEqual(len(s2["sessions"]), 4)
        for row in s2["sessions"][:-1]:
            for b in B.BOOKS:
                self.assertTrue(row[b]["late"] and row[b]["queued"] == 0)
        for b in B.BOOKS:
            st = self.state(b)
            flags = {r["date"]: r["processed_late"] for r in st["equity"]}
            self.assertTrue(all(flags[str(self.days[k].date())] for k in (301, 302, 303)))
            self.assertFalse(flags[str(self.days[304].date())])
        # re-run with the same data: nothing new, no duplicates
        before = {b: (self.state(b)["orders_log"], self.state(b)["pending"],
                      self.state(b)["ledger"], self.state(b)["equity"]) for b in B.BOOKS}
        nsig = {b: len(pd.read_csv(B.paths(b, self.root)["signals"])) for b in B.BOOKS
                if B.paths(b, self.root)["signals"].exists()}
        s3 = self.run_at(304)
        self.assertEqual(s3["sessions"], [])
        for b in B.BOOKS:
            st = self.state(b)
            self.assertEqual((st["orders_log"], st["pending"], st["ledger"], st["equity"]), before[b])
            if b in nsig:
                self.assertEqual(len(pd.read_csv(B.paths(b, self.root)["signals"])), nsig[b])
        self.assertGreaterEqual(sum(nsig.values()), sum(sig_rows.values()))
        # the original paper book is byte-for-byte unchanged
        for p, body in self.old.items():
            self.assertEqual(p.read_bytes(), body, p)
        comp = json.loads((B.experiment_file(self.root).parent / "comparison.json").read_text())
        self.assertEqual(comp["common_period"], dict(start=start, through=str(self.days[304].date())))

    def test_no_backdated_trades_on_the_first_run(self):
        self.run_at(300)
        for b in B.BOOKS:
            st = self.state(b)
            self.assertEqual(len(st["equity"]), 1)
            self.assertFalse(any(o["outcome"] == "entered" for o in st["orders_log"]))

    def test_late_first_run_never_trades(self):
        self.run_at(300, hour=15)                 # 10:00 New York (EST): after the open
        for b in B.BOOKS:
            st = self.state(b)
            self.assertEqual(st["pending"], [])

    def test_out_of_step_books_refuse_to_run(self):
        self.run_at(300)
        p = B.paths("breakout", self.root)["state_file"]
        body = p.read_text()
        p.unlink()
        with self.assertRaises(B.BooksOutOfStep):
            self.run_at(301)
        p.write_text(body)
        st = self.state("retest")
        st["processed_through"] = str(self.days[299].date())
        store.save_state(st, B.paths("retest", self.root)["state_file"])
        with self.assertRaises(B.BooksOutOfStep):
            self.run_at(301)

    def test_code_change_stops_both_books(self):
        self.run_at(300)
        st = self.state("breakout")
        st["code_fingerprint"]["combined"] = "000000000000"
        store.save_state(st, B.paths("breakout", self.root)["state_file"])
        with self.assertRaises(B.StrategyChanged):
            self.run_at(301)

    def test_restore_all_or_nothing(self):
        self.run_at(300)
        bk = Path(self.tmp.name) / "backup"
        import shutil
        shutil.copytree(self.root / "paper" / "compare", bk)
        with self.assertRaises(RuntimeError):                # not newer
            CR.restore(bk, self.root)
        self.run_at(302)
        newer = Path(self.tmp.name) / "newer"
        shutil.copytree(self.root / "paper" / "compare", newer)
        shutil.rmtree(self.root / "paper" / "compare")
        shutil.copytree(bk, self.root / "paper" / "compare")  # current state = older
        self.assertIn("restored", CR.restore(newer, self.root))
        self.assertEqual(self.state("retest")["processed_through"], str(self.days[302].date()))


if __name__ == "__main__":
    unittest.main()
