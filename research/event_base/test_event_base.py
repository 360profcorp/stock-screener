"""Mandatory technical tests (PLAN.md §8). Synthetic data only; no network, no broker code."""
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from research.event_base import bases as B
from research.event_base import events as EV
from research.event_base import execution as X
from research.event_base import run as R
from research.sp1500 import run as RUN

CAL = pd.bdate_range("2021-01-04", periods=120)


def arrays(O, H, L, C, dates, div=None):
    n = len(C)
    return dict(O=np.asarray(O, float), H=np.asarray(H, float), L=np.asarray(L, float), C=np.asarray(C, float),
                dates=pd.DatetimeIndex(dates).values, div=np.zeros(n) if div is None else np.asarray(div, float))


def base_pattern(n=80, breakout_at=37, after=104.0):
    """30 wide bars (TR 4), then tight bars (TR 1); close above the base high at `breakout_at`."""
    H, L, C = [], [], []
    for k in range(n):
        if k < 30:
            H.append(102.), L.append(98.), C.append(100.)
        elif k < breakout_at:
            H.append(100.5), L.append(99.5), C.append(100.)
        else:
            H.append(after + 1), L.append(after - 1), C.append(after)
    O = list(C)
    return arrays(O, H, L, C, CAL[:n])


def sess_of(x):
    pos = {d: k for k, d in enumerate(CAL)}
    return B.session_index(x["dates"], pos)


class Bases(unittest.TestCase):
    def test_detects_first_exit(self):
        x = base_pattern()
        bs = B.scan(x, sess_of(x), start_i=21)
        self.assertEqual(bs[0]["i_end"], 31)   # first t with mean TR(last 5) <= 0.75 * mean TR(first 10)
        self.assertEqual((bs[0]["base_high"], bs[0]["base_low"]), (102., 98.))
        self.assertEqual(bs[0]["outcome"], "signal")
        self.assertEqual(bs[0]["i_outcome"], 37)

    def test_future_bars_do_not_change_past_bases(self):
        rng = np.random.default_rng(1)
        C = 100 * np.exp(np.cumsum(rng.normal(0, .004, 400)))
        H, L = C * (1 + rng.uniform(0, .01, 400)), C * (1 - rng.uniform(0, .01, 400))
        cal = pd.bdate_range("2019-01-01", periods=400)
        pos = {d: k for k, d in enumerate(cal)}
        x = arrays(C, H, L, C, cal)
        full = B.scan(x, B.session_index(x["dates"], pos), start_i=21)
        self.assertGreater(len(full), 5)
        t0 = 250
        y = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in x.items()}
        y["C"][t0 + 1:] *= 1.3
        y["H"][t0 + 1:] *= 1.5
        y["L"][t0 + 1:] *= 0.9
        cut = B.scan(y, B.session_index(y["dates"], pos), start_i=21)
        key = lambda b: (b["i_start"], b["i_end"], b["base_high"], b["base_low"])    # noqa: E731
        self.assertEqual([key(b) for b in full if b["i_end"] <= t0], [key(b) for b in cut if b["i_end"] <= t0])
        self.assertEqual([(key(b), b["outcome"]) for b in full if b["i_outcome"] <= t0],
                         [(key(b), b["outcome"]) for b in cut if b["i_outcome"] <= t0])

    def test_first_signal_used_once_and_windows_never_overlap(self):
        x = base_pattern(n=110)
        bs = B.scan(x, sess_of(x), start_i=21)
        sig = [b for b in bs if b["outcome"] == "signal"]
        self.assertEqual(len([b for b in sig if b["i_end"] == 31]), 1)
        for a, b in zip(bs, bs[1:]):
            self.assertGreater(b["i_start"], a["i_end"])

    def test_filtered_first_exit_is_consumed(self):
        x = base_pattern(n=110)
        data = {"AAA": x}
        cal = CAL[:110]
        spy = pd.DataFrame({"Close": np.linspace(100, 200, 400)}, index=pd.bdate_range("2019-07-01", periods=400))
        spy = spy[spy.index <= cal[-1]]
        pm = pd.DataFrame(True, index=cal, columns=["AAA"])
        rs = pd.DataFrame(99., index=cal, columns=["AAA"])
        rs.loc[cal[37], "AAA"] = 50.                        # the first exit fails RS
        bs = R.s_bases(data, cal, spy, pm, rs, start_i=21)
        first = bs[bs["i_end"] == 31].iloc[0]
        self.assertEqual(first["status"], "signal_filtered_rs")
        S = R.s_candidates(bs)
        self.assertFalse(((S["signal_date"] > cal[37]) & (S["signal_date"] <= cal[47])).any())

    def test_missing_bar_breaks_base(self):
        x = base_pattern()
        keep = np.ones(len(x["C"]), bool)
        keep[25] = False                                    # session missing inside the window
        y = {k: (v[keep] if isinstance(v, np.ndarray) else v) for k, v in x.items()}
        bs = B.scan(y, sess_of(y), start_i=21)
        for b in bs:
            d0, d1 = pd.Timestamp(b["base_start"]), pd.Timestamp(b["base_end"])
            self.assertFalse(d0 <= CAL[25] <= d1)
        x2 = base_pattern()
        keep = np.ones(len(x2["C"]), bool)
        keep[36] = False                                    # missing session during the watch
        y2 = {k: (v[keep] if isinstance(v, np.ndarray) else v) for k, v in x2.items()}
        bs2 = B.scan(y2, sess_of(y2), start_i=21)
        self.assertEqual(bs2[0]["outcome"], "broken")


def flat(n, px=100., cal=CAL):
    return arrays([px] * n, [px * 1.005] * n, [px * .995] * n, [px] * n, cal[:n])


def cands(rows):
    return pd.DataFrame(rows, columns=["ticker", "i", "signal_date", "close", "stop", "rs"])


class Execution(unittest.TestCase):
    def test_qty_fixed_before_open_and_fill(self):
        x = flat(40)
        x["O"][6] = 99.
        b = X.run_book(cands([("A", 5, CAL[5], 100., 95., 90)]), {"A": x}, CAL[:40], CAL[0], CAL[39], 10.)
        t = b["trades"].iloc[0]
        lim = 101.
        q = int(min(50 / (lim - 95), 1000 / (lim * 1.001), 10000 / (lim * 1.001)))
        self.assertEqual(t["qty"], q)
        self.assertEqual(t["entry"], 99.)
        self.assertEqual(pd.Timestamp(t["entry_date"]), CAL[6])

    def test_expiry_above_limit_and_missing_bar(self):
        x = flat(40)
        x["O"][6] = 101.5
        b = X.run_book(cands([("A", 5, CAL[5], 100., 95., 90)]), {"A": x}, CAL[:40], CAL[0], CAL[39], 10.)
        self.assertEqual(b["orders"]["outcome"].tolist(), ["placed", "expired_above_limit"])
        self.assertEqual(len(b["trades"]), 0)
        y = flat(40)
        keep = np.ones(40, bool)
        keep[6] = False
        y = {k: (v[keep] if isinstance(v, np.ndarray) else v) for k, v in y.items()}
        b = X.run_book(cands([("A", 5, CAL[5], 100., 95., 90)]), {"A": y}, CAL[:40], CAL[0], CAL[39], 10.)
        self.assertEqual(b["orders"]["outcome"].tolist(), ["placed", "expired_no_bar"])
        self.assertEqual(len(b["trades"]), 0)

    def test_entry_at_or_below_stop_is_kept(self):
        x = flat(40)
        x["O"][6], x["L"][6] = 94., 93.
        b = X.run_book(cands([("A", 5, CAL[5], 100., 95., 90)]), {"A": x}, CAL[:40], CAL[0], CAL[39], 10.)
        t = b["trades"].iloc[0]
        self.assertEqual(t["reason"], "entry_at_or_below_stop")
        self.assertAlmostEqual(t["net_pnl"], t["qty"] * 94 * (1 - .001) - t["qty"] * 94 * (1 + .001))
        self.assertTrue(b["recon"]["matches_cent"])

    def test_no_cash_from_same_session_exits(self):
        a = flat(40)
        a["L"][7] = 94.                                     # A stops out during session 7
        bb = flat(40, px=1000.)
        c = cands([("A", 5, CAL[5], 100., 95., 99), ("B", 6, CAL[6], 1000., 950., 90),
                   ("B", 7, CAL[7], 1000., 950., 90)])
        b = X.run_book(c, {"A": a, "B": bb}, CAL[:40], CAL[0], CAL[39], 10., risk_fraction=1.0,
                       max_position_fraction=1.0)
        o = b["orders"]
        self.assertEqual(o.loc[(o["ticker"] == "B") & (o["signal_date"] == CAL[6]), "outcome"].tolist(),
                         ["skip_capital_or_risk"])
        self.assertIn("placed", o.loc[(o["ticker"] == "B") & (o["signal_date"] == CAL[7]), "outcome"].tolist())

    def test_dividends_once(self):
        x = flat(40)
        x["div"][10] = 1.0
        x["div"][6] = 5.0                                   # ex-date on the entry day: not entitled
        b = X.run_book(cands([("A", 5, CAL[5], 100., 95., 90)]), {"A": x}, CAL[:40], CAL[0], CAL[39], 10.)
        t = b["trades"].iloc[0]
        self.assertAlmostEqual(t["dividends"], t["qty"] * 1.0)
        self.assertAlmostEqual(b["totals"]["dividends"], t["qty"] * 1.0)
        self.assertEqual(t["reason"], "time")
        self.assertEqual(pd.Timestamp(t["exit_date"]), CAL[26])

    def test_reconciliation_random_book_and_rerun(self):
        rng = np.random.default_rng(3)
        data, rows = {}, []
        for k in range(12):
            C = 50 * np.exp(np.cumsum(rng.normal(0, .02, 120)))
            O = C * (1 + rng.normal(0, .005, 120))
            H = np.maximum(C, O) * (1 + rng.uniform(0, .02, 120))
            L = np.minimum(C, O) * (1 - rng.uniform(0, .02, 120))
            div = np.where(rng.uniform(size=120) < .02, .3, 0.)
            data[f"T{k}"] = arrays(O, H, L, C, CAL, div)
            for i in rng.choice(np.arange(5, 115), 8, replace=False):
                rows.append((f"T{k}", int(i), CAL[i], C[i], C[i] * .95, float(rng.integers(85, 100))))
        c = cands(rows)
        for kw in X.SENSITIVITY.values():
            b = X.run_book(c, data, CAL, CAL[0], CAL[-1], 25., **kw)
            self.assertTrue(b["recon"]["matches_cent"])
            self.assertTrue((b["curve"]["cash"] >= -1e-6).all())
            self.assertLessEqual(b["curve"]["positions"].max(), 5)
            per_day = b["orders"][b["orders"]["outcome"] == "placed"].groupby("signal_date").size()
            self.assertLessEqual(per_day.max(), 3)
        b1 = X.run_book(c, data, CAL, CAL[0], CAL[-1], 10.)
        b2 = X.run_book(c, data, CAL, CAL[0], CAL[-1], 10.)
        pd.testing.assert_frame_equal(b1["trades"], b2["trades"])
        pd.testing.assert_frame_equal(b1["curve"], b2["curve"])
        with tempfile.TemporaryDirectory() as d:
            root, man = Path(d), {}
            p = root / "run" / "trades.csv"
            RUN.write_once(p, RUN.csv_bytes(b1["trades"]), man, root)
            RUN.write_once(p, RUN.csv_bytes(b2["trades"]), man, root)          # identical rerun: allowed
            with self.assertRaises(FileExistsError):
                RUN.write_once(p, b"different", man, root)
            self.assertEqual(len(list((root / "run").iterdir())), 1)


def rel(acc, day, lo=None, hi=None, year=2024, retrieved=True):
    g = [] if lo is None else [dict(year=year, low=lo, high=hi, excerpt="")]
    return dict(accession=acc, accepted=pd.Timestamp(day) + pd.Timedelta(hours=16, minutes=5), retrieved=retrieved,
                guidance=g)


class Events(unittest.TestCase):
    sessions = pd.bdate_range("2023-01-02", "2024-12-31")
    cand = dict(base_start=pd.Timestamp("2024-05-20"), signal_date=pd.Timestamp("2024-06-20"))

    def test_raise_and_later_update_cancels(self):
        r1, r2 = rel("a1", "2024-02-01", 10e9, 11e9), rel("a2", "2024-05-01", 10.5e9, 11.5e9)
        s = EV.candidate_status(self.cand, [r1, r2], "1231", self.sessions)
        self.assertEqual(s["status"], "raise")
        r3 = rel("a3", "2024-06-03", 10.5e9, 11.5e9)       # reiterated (neutral) before the signal
        s = EV.candidate_status(self.cand, [r1, r2, r3], "1231", self.sessions)
        self.assertEqual((s["status"], s["reason"]), ("known_no_raise", "latest_update_not_a_raise"))
        r3b = rel("a3", "2024-06-03", 10.0e9, 11.6e9)      # lower low: not a raise
        self.assertEqual(EV.candidate_status(self.cand, [r1, r2, r3b], "1231", self.sessions)["status"],
                         "known_no_raise")

    def test_timing_rules(self):
        r1 = rel("a1", "2024-02-01", 10e9, 11e9)
        same_day = rel("a2", "2024-05-20", 10.5e9, 11.5e9)  # accepted on base start: not known before
        s = EV.candidate_status(self.cand, [r1, same_day], "1231", self.sessions)
        self.assertEqual(s["reason"], "raise_not_known_before_base_start")
        old = dict(base_start=pd.Timestamp("2024-05-20"), signal_date=pd.Timestamp("2024-08-30"))
        r2 = rel("a2", "2024-05-01", 10.5e9, 11.5e9)
        self.assertEqual(EV.candidate_status(old, [r1, r2], "1231", self.sessions)["reason"],
                         "raise_older_than_60_sessions")

    def test_unknown_is_not_absent(self):
        r1 = rel("a1", "2024-02-01", 10e9, 11e9)
        no_g = rel("a2", "2024-05-01")                      # release without a parsed range
        self.assertEqual(EV.candidate_status(self.cand, [r1, no_g], "1231", self.sessions)["status"], "unknown")
        self.assertEqual(EV.candidate_status(self.cand, [], "1231", self.sessions)["status"], "unknown")
        bad = rel("a2", "2024-05-01", 10.5e9, 11.5e9, retrieved=False)
        self.assertEqual(EV.candidate_status(self.cand, [r1, bad], "1231", self.sessions)["reason"],
                         "release_not_retrieved")
        self.assertEqual(EV.candidate_status(self.cand, [r1], "0131", self.sessions)["status"], "unknown")
        st = pd.DataFrame([dict(ticker="A", signal_date="2024-06-20", status="unknown", reason="x")])
        cov = EV.coverage(st, years=[2024])
        self.assertEqual(cov["by_year"][2024]["coverage_pct"], 0.0)
        self.assertFalse(cov["all_years_ge_80"])

    def test_no_issuer_confusion(self):
        f = pd.DataFrame(dict(issuer_cik=[1, 2, 3], sym=["XYZ", "XYZ", "ABC"],
                              filing_date=pd.to_datetime(["2015-03-01", "2022-03-01", "2022-04-01"])))
        self.assertEqual(EV.resolve_cik("XYZ", "2022-06-01", f)[0], 2)
        self.assertEqual(EV.resolve_cik("XYZ", "2015-06-01", f)[0], 1)
        self.assertIsNone(EV.resolve_cik("XYZ", "2018-09-01", f)[0])
        g = pd.concat([f, pd.DataFrame(dict(issuer_cik=[9], sym=["ABC"], filing_date=[pd.Timestamp("2022-05-01")]))])
        self.assertIsNone(EV.resolve_cik("ABC", "2022-06-01", g)[0])

    def test_parse_and_consume(self):
        t = ("Acme reports results. For fiscal 2024, the Company now expects revenue in the range of $4.10 billion "
             "to $4.30 billion and EPS of $2.10 to $2.20. Separately, EPS is expected to be $2.10 to $2.20 for "
             "fiscal 2024. Sales for full-year 2024 are expected between €3.0 billion and €3.2 billion.")
        g, rej = EV.parse_guidance(t)
        self.assertEqual([(x["year"], x["low"], x["high"]) for x in g], [(2024, 4.1e9, 4.3e9)])
        self.assertEqual(rej, 1)
        st = pd.DataFrame([dict(ticker="A", cik=1, signal_date=pd.Timestamp("2024-06-20"), status="raise", event="e1",
                                reason="confirmed_raise"),
                           dict(ticker="A", cik=1, signal_date=pd.Timestamp("2024-07-20"), status="raise", event="e1",
                                reason="confirmed_raise")])
        out = EV.consume_events(st)
        self.assertEqual(out["status"].tolist(), ["raise", "known_no_raise"])


class Decision(unittest.TestCase):
    def test_rule_and_insufficient(self):
        def bk(cagr, dd, ret=10., pf=1.2, n=200):
            return dict(cagr_pct=cagr, max_dd_pct=dd, return_pct=ret, profit_factor=pf, trades_closed=n)
        books = {}
        for v, cg in (("C", 3.), ("S", 6.)):
            for w in ("full", "y2017_2021", "y2022_2026"):
                for c in (10, 25):
                    books[f"{v}|{w}|{c}"] = bk(cg, -15.)
        bench = {"SPY50_BIL50|full|2": dict(cagr_pct=4.5, max_dd_pct=-17.), "SPY100|full|2": dict(cagr_pct=12., max_dd_pct=-34.)}
        d = R.decide(books, bench, "S", ref="C")
        self.assertEqual(d["verdict"], "RESEARCH_CANDIDATE")
        bench["SPY_TIMING50|full|2"] = dict(cagr_pct=7., max_dd_pct=-10.)
        self.assertEqual(R.decide(books, bench, "S", ref="C")["verdict"], "NOT_A_CANDIDATE")
        books["S|y2017_2021|10"]["trades_closed"] = 10
        self.assertEqual(R.decide(books, bench, "S", ref="C")["verdict"], "INSUFFICIENT_DATA")


if __name__ == "__main__":
    unittest.main()


class BenchmarkDividendsV2(unittest.TestCase):
    """REVIEW_PLAN.md §5: entitlement at the prior close, accrual, pay date, balance reinvest."""

    def setUp(self):
        from research.event_base import benchmarks as BM
        self.BM = BM
        self.days = pd.bdate_range("2023-03-01", periods=60)
        self.spy = pd.DataFrame({"Open": 100., "Close": 100., "Dividends": 0.}, index=self.days)

    def test_bought_on_exdate_not_entitled(self):
        s = self.spy.copy()
        s.loc[self.days[0], "Dividends"] = 1.0             # ex-date = first session (buy at its open)
        b = self.BM.etf_book_v2({"SPY": s}, list(self.days), lambda k, d, st: {"SPY": 1.0} if k == -1 else None,
                                cost_bps=0., full_cal=self.days, sweep_all=True)
        self.assertEqual(b["totals"]["distributions"], 0.0)
        v1 = self.BM.etf_book({"SPY": s}, list(self.days), lambda k, d, st: {"SPY": 1.0} if k == -1 else None, cost_bps=0.)
        self.assertGreater(v1["totals"]["distributions"], 0.0)   # the v1 fault

    def test_accrual_pay_date_and_balance(self):
        s = self.spy.copy()
        s.loc[self.days[10], "Dividends"] = 0.5            # 100 shares -> $50 accrued
        b = self.BM.etf_book_v2({"SPY": s}, list(self.days), lambda k, d, st: {"SPY": 1.0} if k == -1 else None,
                                cost_bps=0., full_cal=self.days, sweep_all=True)
        c = b["curve"].set_index("date")
        self.assertAlmostEqual(c.loc[self.days[10], "receivable"], 50.0)
        self.assertAlmostEqual(c.loc[self.days[10], "equity"], 10050.0)
        pay = self.BM.pay_dates([self.days[10]], "SPY", self.days)[self.days[10]]
        self.assertEqual(pay.month, 4)                     # last session of the following month
        self.assertAlmostEqual(c.loc[pay, "cash"], 50.0)
        self.assertAlmostEqual(c.loc[pay, "receivable"], 0.0)
        nxt = self.days[self.days.get_loc(pay) + 1]
        self.assertAlmostEqual(c.loc[nxt, "cash"], 50.0)   # $50 < one share: stays as balance
        self.assertAlmostEqual(c["equity"].iloc[-1], 10050.0)

    def test_sold_on_exdate_still_entitled(self):
        s = self.spy.copy()
        s.loc[self.days[5], "Dividends"] = 1.0
        rule = lambda k, d, st: {"SPY": 1.0} if k == -1 else ({"SPY": 0.0} if d == self.days[4] else None)  # noqa: E731
        b = self.BM.etf_book_v2({"SPY": s}, list(self.days), rule, cost_bps=0., full_cal=self.days)
        self.assertAlmostEqual(b["totals"]["distributions"], 100.0)


class ExtractV2(unittest.TestCase):
    """Extractor v2 period / range rules (Cadence regression included)."""

    def test_quarterly_vs_full_year(self):
        from research.event_base import extract_v2 as V
        w = ("Business Outlook For the third quarter of 2020, the company expects total revenue in the range of "
             "$630 million to $650 million. For 2020, the company expects total revenue in the range of $2.585 billion "
             "to $2.615 billion.")
        its = V.parse_window(w)
        self.assertIn("quarterly", [i["kind"] for i in its])
        rng = [i for i in its if i["kind"] == "range"]
        self.assertEqual([(r["year"], round(r["low"], 3), round(r["high"], 3)) for r in rng], [(2020, 2.585, 2.615)])
        self.assertEqual([i["kind"] for i in V.parse_window("Third Quarter of Fiscal Year 2021 Financial Outlook: Net revenues "
                                                            "are expected to be in the range of: $1.34 billion to $1.49 billion")],
                         ["quarterly"])

    def test_from_to_and_prior(self):
        from research.event_base import extract_v2 as V
        w = ("We are increasing our fiscal 2020 financial guidance. We are raising our annual revenue expectations from a range "
             "of $7.28 billion to $7.32 billion to a range of $7.29 billion to $7.33 billion")
        r = [i for i in V.parse_window(w) if i["kind"] == "range"][0]
        self.assertEqual((r["year"], r["low"], r["high"], r["old"]), (2020, 7.29, 7.33, (7.28, 7.32)))
        w2 = "Full Year 2021 Guidance: Revenue $5.05-$5.20 billion, versus prior $5.05-$5.25 billion"
        r2 = [i for i in V.parse_window(w2) if i["kind"] == "range"][0]
        self.assertEqual((r2["low"], r2["high"], r2["old"]), (5.05, 5.20, (5.05, 5.25)))
        self.assertFalse(V.is_raise(r2["old"], r2["low"], r2["high"]))

    def test_excluded_metrics(self):
        from research.event_base import extract_v2 as V
        self.assertEqual([i for i in V.parse_window("FY'24 Guidance Closed sales $280M - $320M") if i["kind"] == "range"], [])
        self.assertEqual([i for i in V.parse_window("For fiscal 2024, operating profit of $5.3 billion - $5.7 billion; "
                                                    "revenue growth of 5%") if i["kind"] == "range"], [])
