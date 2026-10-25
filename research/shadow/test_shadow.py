"""Shadow books (synthetic, seeded, no network). Run: python -m unittest research.shadow.test_shadow"""
import difflib
import inspect
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

import backtest as bt
import core
import portfolio_bt as pf
from paper import store
from paper import verify as V
from paper.portfolio import PaperPortfolio, new_state
from research.shadow import books as SB
from research.shadow import f13
from research.shadow import run as R
from test_paper import market


def prices_of(fr, spy):
    return pd.concat({**fr, "SPY": spy}, axis=1)


class Engine(unittest.TestCase):
    def test_step_differs_from_paper_in_the_sort_line_only(self):
        a = inspect.getsource(PaperPortfolio.step).splitlines()
        b = inspect.getsource(SB.RankedPortfolio.step).splitlines()
        d = [l for l in difflib.unified_diff(a, b, lineterm="", n=0)
             if l[:1] in "+-" and not l.startswith(("+++", "---"))]
        self.assertEqual(len(d), 2, d)
        self.assertIn("due.sort(", d[0])
        self.assertIn('o.get("f2", 0.0)', d[1])

    def test_books_differ_only_in_ranking(self):
        a, b = SB.BOOKS["rs"].as_dict(), SB.BOOKS["br"].as_dict()
        self.assertEqual({k for k in a if a[k] != b[k]}, {"ranking"})
        c = SB.BOOKS["rs"]
        self.assertEqual((c.mode, c.min_rs, c.market_filter, c.risk_fraction, c.max_positions,
                          c.max_new_per_day, c.max_position_fraction, c.entry_at, c.cost_bps,
                          c.hold_days, c.stop_buf_pct, c.lookback),
                         ("breakout", 85, "ma50", .01, 5, 3, .2, "open", 10., 20, 3., 3))

    def test_task10_fingerprint_unchanged(self):
        self.assertEqual(store.code_fingerprint()["combined"], "17454c61f631")


class Equivalence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fr, cls.spy = market(5, n_t=30, n=420)
        cls.sig, cls.data = bt.find_signals(cls.fr, modes=["breakout"])
        cls.mo = core.regime_mask(core.market_regime(cls.spy), "ma50")
        cls.cfg = replace(SB.BOOKS["br"], min_rs=50)
        rng = np.random.default_rng(1)
        cls.f2 = {t: rng.normal(0, .05) for t in cls.fr}

    def drive(self, cls_, ranker):
        cal = V.calendar(self.data)
        S, E = cal[270], cal[-1]
        el = V.eligible_signals(self.sig, self.mo, self.cfg)
        idx = V.bar_index(self.data)
        port = cls_(new_state(self.cfg, "verification"), cfg=self.cfg, kind="verification", trace=True)

        def sig(day):
            d = el[el["date"] == day]
            if d.empty:
                return d
            d = d.assign(eligible=True).sort_values(["rs", "ticker"], ascending=[False, True], kind="stable")
            d = d.assign(rank=np.arange(1, len(d) + 1), F2=[self.f2[t] for t in d["ticker"]])
            return ranker(d)
        g = "2000-01-01T00:00:00+00:00"
        port.queue_signals([d for d in cal if d < S][-1], sig([d for d in cal if d < S][-1]), g)
        for day in [d for d in cal if S <= d <= E]:
            port.step(day, V.bars_on(self.data, idx, day))
            port.queue_signals(day, sig(day), g)
        return port, S, E

    def test_ranked_with_zero_f2_is_paper_portfolio(self):
        z = lambda d: d.assign(F2=0.0)                     # noqa: E731
        a, _, _ = self.drive(PaperPortfolio, z)
        b, _, _ = self.drive(SB.RankedPortfolio, z)
        self.assertEqual(a.s["ledger"], b.s["ledger"])
        self.assertEqual(a.s["equity"], b.s["equity"])
        self.assertEqual([{k: v for k, v in o.items() if k != "f2"} for o in b.s["orders_log"]],
                         a.s["orders_log"])

    def test_br_book_equals_replay_on_the_br_order(self):
        port, S, E = self.drive(SB.RankedPortfolio, SB.rank_br)
        cfg = self.cfg
        tr = bt.simulate(self.sig, self.data, cfg.mode, hold=cfg.hold_days, stop_buf=cfg.stop_buf_pct,
                         min_rs=cfg.min_rs, min_vol=0.0, max_risk=cfg.max_risk_pct, market_ok=self.mo,
                         entry_at="open", one_per_ticker=False, include_open=True)
        tr["F2"] = [self.f2[t] for t in tr["ticker"]]
        tr = tr.sort_values(["date", "F2", "rs", "ticker"], ascending=[True, False, False, True],
                            kind="stable").reset_index(drop=True)
        ref = pf.replay(tr, self.data, initial_cash=cfg.initial_cash, risk_fraction=cfg.risk_fraction,
                        max_positions=cfg.max_positions, max_new_per_day=cfg.max_new_per_day,
                        max_position_fraction=cfg.max_position_fraction, cost_bps=cfg.cost_bps,
                        start=S, end=E, open_at_end="mark", record_decisions=True)
        r = V.compare(port, ref, cfg)
        self.assertTrue(r["ok"], r)
        self.assertGreater(r["fills_ref"], 5)
        rs_port, _, _ = self.drive(PaperPortfolio, lambda d: d)
        self.assertNotEqual(rs_port.s["ledger"], port.s["ledger"])     # the order matters here


class F2(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        p = Path(self.tmp.name) / "b.csv"
        pd.DataFrame(dict(ticker=["AAA", "AAA", "BBB"], period=["2026-03-31", "2026-06-30", "2026-06-30"],
                          usable_from=["2026-05-16", "2026-08-15", "2026-08-15"], holders_q=[10, 12, 5],
                          holders_q1=[8, 10, 0], common_filers=[100, 100, 100],
                          breadth_change=[0.25, 0.2, np.nan])).to_csv(p, index=False)
        self.t = SB.F2Table(p)

    def tearDown(self):
        self.tmp.cleanup()

    def test_point_in_time(self):
        self.assertEqual(self.t.get("AAA", "2026-08-14")["F2"], 0.25)
        self.assertEqual(self.t.get("AAA", "2026-08-15")["F2"], 0.2)
        self.assertEqual(self.t.get("AAA", "2026-12-13")["F2"], 0.2)          # 120 days
        x = self.t.get("AAA", "2026-12-14")
        self.assertEqual((x["F2"], x["f2_status"]), (0.0, "stale (>120 days)"))
        self.assertEqual(self.t.get("BBB", "2026-09-01")["f2_status"], "no holders in Q-1")
        self.assertEqual(self.t.get("ZZZ", "2026-09-01")["F2"], 0.0)

    def test_rank_br(self):
        s = pd.DataFrame(dict(ticker=["A", "B", "C", "D"], rs=[99, 90, 95, 99], eligible=[True, True, True, False],
                              F2=[0.0, 0.3, 0.3, 0.9], rank=[1, 3, 2, np.nan]))
        r = SB.rank_br(s)
        self.assertEqual(list(r["ticker"]), ["C", "B", "A", "D"])
        self.assertEqual(list(r["rank"][:3]), [1, 2, 3])
        self.assertTrue(np.isnan(r["rank"].iloc[3]))

    def test_latest_due(self):
        self.assertEqual(str(f13.latest_due("2026-11-14").date()), "2026-06-30")
        self.assertEqual(str(f13.latest_due("2026-11-15").date()), "2026-09-30")
        self.assertEqual(str(f13.latest_due("2027-02-15").date()), "2026-12-31")


class Parsers(unittest.TestCase):
    def test_form_idx(self):
        txt = ("Form Type   Company Name      CIK         Date Filed  File Name\n"
               "------------------------------------------------------------------\n"
               "13F-HR      ACME CAPITAL LLC                                              1234567     2026-08-14  edgar/data/1234567/0001234567-26-000001.txt\n"
               "13F-HR/A    ACME CAPITAL LLC                                              1234567     2026-08-20  edgar/data/1234567/0001234567-26-000002.txt\n")
        d = f13.parse_form_idx(txt)
        self.assertEqual(list(d["form"]), ["13F-HR", "13F-HR/A"])
        self.assertEqual(d.loc[0, "path"], "edgar/data/1234567/0001234567-26-000001.txt")
        self.assertEqual(d.loc[0, "cik"], "1234567")

    def test_submission(self):
        txt = ("ACCESSION NUMBER:\t\t0001234567-26-000001\nCONFORMED SUBMISSION TYPE:\t13F-HR\n"
               "CONFORMED PERIOD OF REPORT:\t20260630\nFILED AS OF DATE:\t\t20260814\n"
               "FILER:\n\tCOMPANY DATA:\n\t\tCOMPANY CONFORMED NAME:\tACME\n\t\tCENTRAL INDEX KEY:\t\t\t0001234567\n"
               "<ns1:informationTable xmlns:ns1='x'>"
               "<ns1:infoTable><ns1:nameOfIssuer>APPLE</ns1:nameOfIssuer><ns1:cusip>037833100</ns1:cusip>"
               "<ns1:shrsOrPrnAmt><ns1:sshPrnamt>5</ns1:sshPrnamt><ns1:sshPrnamtType>SH</ns1:sshPrnamtType></ns1:shrsOrPrnAmt></ns1:infoTable>"
               "<ns1:infoTable><ns1:cusip>037833100</ns1:cusip><ns1:shrsOrPrnAmt><ns1:sshPrnamtType>SH</ns1:sshPrnamtType>"
               "</ns1:shrsOrPrnAmt><ns1:putCall>Put</ns1:putCall></ns1:infoTable>"
               "<infoTable><cusip>594918104</cusip><shrsOrPrnAmt><sshPrnamtType>PRN</sshPrnamtType></shrsOrPrnAmt></infoTable>"
               "<infoTable><cusip>02079k305</cusip><shrsOrPrnAmt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt><putCall></putCall></infoTable>"
               "</ns1:informationTable>")
        s = f13.parse_submission(txt)
        self.assertEqual((s["type"], s["period"], s["filed"], s["cik"]), ("13F-HR", "20260630", "20260814", "0001234567"))
        self.assertEqual(s["cusips"], ["037833100", "02079K305"])
        self.assertEqual(s["n_info"], 4)

    def test_breadth_rows_common_filers(self):
        pq = {("1", "C1"), ("2", "C1"), ("9", "C1"), ("1", "C2")}
        pq1 = {("1", "C1"), ("1", "C2"), ("2", "C2"), ("3", "C1")}
        b = f13.breadth_rows("2026-09-30", pq, {"1", "2", "9"}, "2026-06-30", pq1, {"1", "2", "3"},
                             {"C1": "AAA", "C2": "BBB"}).set_index("ticker")
        self.assertEqual((b.at["AAA", "holders_q1"], b.at["AAA", "holders_q"]), (1, 2))
        self.assertEqual((b.at["BBB", "holders_q1"], b.at["BBB", "holders_q"]), (2, 1))
        self.assertEqual(str(b.at["AAA", "usable_from"]), "2026-11-15")
        self.assertEqual(b.at["AAA", "common_filers"], 2)


class Runner(unittest.TestCase):
    def setUp(self):
        self.fr, self.spy = market(8, n_t=20, n=380)
        self.prices = prices_of(self.fr, self.spy)
        self.uni = pd.DataFrame({"ticker": list(self.fr), "name": "", "sector": "Tech"})
        self.days = self.spy.index
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        bp = R.breadth_path(self.root)
        bp.parent.mkdir(parents=True)
        rows = []
        for q in pd.period_range("2024Q1", "2025Q4", freq="Q"):
            p = q.end_time.normalize()
            for k, t in enumerate(self.fr):
                rows.append(dict(ticker=t, period=p.date(), usable_from=(p + pd.Timedelta(days=46)).date(),
                                 holders_q=100 + k, holders_q1=100, common_filers=1000,
                                 breadth_change=k / 100 if q.quarter % 2 else -k / 100))
        pd.DataFrame(rows).to_csv(bp, index=False)
        self.old = {p: p.read_bytes() for p in Path("paper").rglob("*") if p.is_file()}
        self.pat = mock.patch.object(SB, "EARLIEST_START", "2024-01-01")
        self.pat.start()

    def tearDown(self):
        self.pat.stop()
        self.tmp.cleanup()

    def run_at(self, k, hour=23, **kw):
        d = self.days[k]
        now = datetime(d.year, d.month, d.day, hour, 0, tzinfo=timezone.utc)
        kw.setdefault("ingest", lambda p: self.fail(f"unexpected ingest {p}"))
        return R.daily(universe=self.uni, prices=self.prices[self.prices.index <= d], now=now,
                       root=self.root, refetch=None, **kw)

    def state(self, b):
        return store.load_state(SB.paths(b, self.root)["state_file"])

    def test_run_catch_up_report_and_nothing_else_touched(self):
        self.run_at(300)
        exp = json.loads(SB.experiment_file(self.root).read_text())
        self.assertEqual(exp["start_session"], str(self.days[300].date()))
        for b in SB.BOOKS:
            st = self.state(b)
            self.assertEqual((st["positions"], st["ledger"]), ({}, []))
            self.assertFalse(any(o["outcome"] == "entered" for o in st["orders_log"]))
        for k in range(301, 360):
            self.run_at(k)
        r = self.run_at(359)
        self.assertEqual(r["sessions"], [])                                   # idempotent
        rs, br = self.state("rs"), self.state("br")
        self.assertEqual(rs["processed_through"], br["processed_through"])
        rep = json.loads((SB.experiment_file(self.root).parent / "report.json").read_text())
        self.assertIn("overlap", rep)
        D = pd.read_csv(SB.experiment_file(self.root).parent / "decisions.csv")
        self.assertTrue({"rank_rs", "rank_br", "outcome_rs", "outcome_br", "reason_rs", "reason_br",
                         "F2", "holders_q", "f13_quarter"} <= set(D.columns))
        # same candidates in both books every day; only ranks differ
        for b in SB.BOOKS:
            sn = sorted(SB.paths(b, self.root)["snapshots"].glob("*.json"))
            self.assertEqual(len(sn), 60)
        for f in sorted(SB.paths("rs", self.root)["snapshots"].glob("*.json")):
            a = json.loads(f.read_text())["signals"]
            c = json.loads((SB.paths("br", self.root)["snapshots"] / f.name).read_text())["signals"]
            self.assertEqual(sorted(x["ticker"] for x in a), sorted(x["ticker"] for x in c))
        # the repository's paper books are untouched
        for p, body in self.old.items():
            self.assertEqual(p.read_bytes(), body, p)

    def test_start_before_prereg_refused_and_due_quarter_ingested(self):
        with mock.patch.object(SB, "EARLIEST_START", "2099-01-01"):
            with self.assertRaises(SB.BooksOutOfStep):
                self.run_at(300)
        calls = []

        def ing(p):
            calls.append(str(p.date()))
            br = pd.read_csv(R.breadth_path(self.root))
            add = br[br["period"] == "2025-12-31"].assign(period=str(p.date()),
                                                          usable_from=str((p + pd.Timedelta(days=46)).date()))
            pd.concat([br, add]).to_csv(R.breadth_path(self.root), index=False)
            return dict(period=str(p.date()))
        k = next(i for i, d in enumerate(self.days) if d >= pd.Timestamp("2025-05-16"))
        self.assertLess(k, len(self.days))
        # breadth.csv ends at 2025-12-31; first run at a day whose due quarter is missing?
        self.run_at(min(k, len(self.days) - 1), ingest=ing)
        self.assertEqual(calls, [])                          # 2025-03-31 is present: no ingest


if __name__ == "__main__":
    unittest.main()
