"""Task 10 tests: paper portfolio equivalence with the Task 6 replay engine, scanner equivalence
with backtest.find_signals, no look-ahead, persistence, signal timestamps, metrics.

Synthetic, seeded data only (deterministic). Run: python -m unittest test_paper -v
"""
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import backtest as bt
import core
from paper import metrics as pm
from paper import store
from paper import verify as V
from paper.config import DEFAULT, PaperConfig
from paper.portfolio import PaperPortfolio
from paper.screener import scan_day, truncate


def market(seed, n_t=25, n=420, drop=0):
    """Random-walk OHLCV for n_t tickers (+ optional missing bars late in the series)."""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2024-01-02", periods=n)
    fr = {}
    for k in range(n_t):
        c = 50 * np.exp(np.cumsum(rng.normal(0.0007, 0.02, n)))
        o = c * np.exp(rng.normal(0, 0.008, n))
        h = np.maximum(o, c) * np.exp(np.abs(rng.normal(0, 0.01, n)))
        l = np.minimum(o, c) * np.exp(-np.abs(rng.normal(0, 0.01, n)))
        df = pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c,
                           "Volume": rng.integers(1e5, 1e6, n).astype(float)}, index=days)
        if drop and k < 5:
            d = rng.choice(np.arange(300, n), drop, replace=False)
            df = df.drop(df.index[d])
        fr[f"T{k:02d}"] = df
    c = 400 * np.exp(np.cumsum(rng.normal(0.0004, 0.01, n)))
    spy = pd.DataFrame({"Open": c, "High": c * 1.005, "Low": c * .995, "Close": c,
                        "Volume": 1e7}, index=days)
    return fr, spy


CFG = PaperConfig(min_rs=50)          # lower RS only so synthetic data produces enough trades


class Equivalence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = []
        for seed, drop in ((1, 0), (2, 8), (3, 0)):
            fr, spy = market(seed, drop=drop)
            sig, data = bt.find_signals(fr, modes=["retest"])
            mo = core.regime_mask(core.market_regime(spy), "ma50")
            cls.cases.append((fr, spy, sig, data, mo))

    def test_stepper_equals_replay(self):
        for k, (fr, spy, sig, data, mo) in enumerate(self.cases):
            for cfg in (CFG, PaperConfig(min_rs=0, max_positions=10, max_new_per_day=5),
                        PaperConfig(min_rs=60, hold_days=5, cost_bps=0, risk_fraction=.03)):
                cal = V.calendar(data)
                S, E = cal[270], cal[-1]
                r = V.compare(V.run_stepper(sig, data, mo, S, E, cfg),
                              V.reference_replay(sig, data, mo, S, E, cfg))
                self.assertTrue(r["ok"], (k, cfg, r))
                self.assertGreater(r["fills_ref"], 5)

    def test_screener_equals_history(self):
        for fr, spy, sig, data, mo in self.cases[:2]:
            days = sorted(pd.to_datetime(sig["date"]).dt.normalize().unique())[::12]
            for day, ok, detail in V.screener_vs_history(fr, spy, sig, mo, days, CFG):
                self.assertTrue(ok, (day, detail))

    def test_live_path_equals_replay(self):
        fr, spy, sig, data, mo = self.cases[0]
        cal = V.calendar(data)
        S, E = cal[-35], cal[-1]
        r = V.compare(V.run_stepper(sig, data, mo, S, E, CFG, scanner=(fr, spy)),
                      V.reference_replay(sig, data, mo, S, E, CFG))
        self.assertTrue(r["ok"], r)


class NoLookAhead(unittest.TestCase):
    def test_future_bars_cannot_change_the_past(self):
        fr, spy = market(5)
        sig, data = bt.find_signals(fr, modes=["retest"])
        mo = core.regime_mask(core.market_regime(spy), "ma50")
        cal = V.calendar(data)
        S, D = cal[280], cal[350]
        a = V.run_stepper(sig, data, mo, S, D, CFG)
        # perturb every bar AFTER D wildly, then re-run the scanner + portfolio through D
        fr2 = {t: df.copy() for t, df in fr.items()}
        for df in fr2.values():
            late = df.index > D
            df.loc[late, ["Open", "High", "Low", "Close"]] *= 3.0
        sig2, data2 = bt.find_signals(fr2, modes=["retest"])
        b = V.run_stepper(sig2, data2, mo, S, D, CFG)
        clock = ("generated_at", "signal_generated_at")                       # wall clock only
        strip0 = lambda lst: [{k: v for k, v in o.items() if k not in clock} for o in lst]
        self.assertEqual(strip0(a.s["ledger"]), strip0(b.s["ledger"]))
        self.assertEqual(a.s["equity"], b.s["equity"])
        strip = lambda lst: [{k: v for k, v in o.items() if k != "generated_at"} for o in lst]
        self.assertEqual(strip(a.s["pending"]), strip(b.s["pending"]))      # wall clock aside
        self.assertEqual(sorted(a.s["positions"]), sorted(b.s["positions"]))

    def test_scan_never_sees_later_bars(self):
        fr, spy = market(6)
        day = fr["T00"].index[330]
        s1 = scan_day(fr, spy, day, CFG)                          # truncates internally
        s2 = scan_day(truncate(fr, day), spy, day, CFG, already_truncated=True)
        pd.testing.assert_frame_equal(s1, s2)


class PortfolioMechanics(unittest.TestCase):
    def bars(self, o, h, l, c):
        return {"O": o, "H": h, "L": l, "C": c}

    def test_fill_stop_time_exit_and_sizing(self):
        cfg = PaperConfig(hold_days=2, cost_bps=0)
        p = PaperPortfolio(cfg=cfg)
        p.step("2026-01-05", {})
        scan = pd.DataFrame([dict(ticker="AAA", rs=90., stop=95., eligible=True, rank=1)])
        p.queue_signals("2026-01-05", scan, "2026-01-05T21:00:00+00:00", "2026-01-06")
        p.step("2026-01-06", {"AAA": self.bars(100, 101, 99, 100)})
        pos = p.s["positions"]["AAA"]
        self.assertEqual(pos["qty"], 20)                   # min(1% risk: 20, 20% cap: 20)
        p.step("2026-01-07", {"AAA": self.bars(100, 102, 99, 101)})
        p.step("2026-01-08", {"AAA": self.bars(101, 103, 100, 102)})   # 2nd bar -> time exit
        self.assertEqual(p.s["ledger"][0]["reason"], "time")
        self.assertAlmostEqual(p.s["ledger"][0]["net_pnl"], 20 * 2)

    def test_gap_below_stop_is_no_trade(self):
        p = PaperPortfolio(cfg=DEFAULT)
        p.step("2026-01-05", {})
        p.queue_signals("2026-01-05", pd.DataFrame([dict(ticker="AAA", rs=90., stop=95.,
                                                         eligible=True, rank=1)]))
        p.step("2026-01-06", {"AAA": self.bars(94, 96, 93, 95)})
        self.assertEqual(p.s["positions"], {})
        self.assertEqual(p.s["orders_log"][-1]["outcome"], "no_trade_open_below_stop")

    def test_order_waits_for_next_bar(self):
        p = PaperPortfolio(cfg=DEFAULT)
        p.step("2026-01-05", {})
        p.queue_signals("2026-01-05", pd.DataFrame([dict(ticker="AAA", rs=90., stop=95.,
                                                         eligible=True, rank=1)]))
        p.step("2026-01-06", {"BBB": self.bars(10, 10, 10, 10)})      # no AAA bar
        self.assertEqual(len(p.s["pending"]), 1)
        p.step("2026-01-07", {"AAA": self.bars(100, 101, 99, 100)})
        self.assertIn("AAA", p.s["positions"])

    def test_same_session_twice_rejected(self):
        p = PaperPortfolio(cfg=DEFAULT)
        p.step("2026-01-05", {})
        with self.assertRaises(ValueError):
            p.step("2026-01-05", {})


class PersistenceAndTimestamps(unittest.TestCase):
    def test_save_load_continue_equals_uninterrupted(self):
        fr, spy = market(7)
        sig, data = bt.find_signals(fr, modes=["retest"])
        mo = core.regime_mask(core.market_regime(spy), "ma50")
        cal = V.calendar(data)
        S, M, E = cal[280], cal[340], cal[-1]
        full = V.run_stepper(sig, data, mo, S, E, CFG)
        # run to M, persist, reload, continue
        part = V.run_stepper(sig, data, mo, S, M, CFG)
        with tempfile.TemporaryDirectory() as d:
            store.save_state(part.s, Path(d) / "p.json")
            st = store.load_state(Path(d) / "p.json")
        cont = PaperPortfolio(st, CFG)
        idx, el = V.bar_index(data), V.eligible_signals(sig, mo, CFG)
        for day in [x for x in cal if M < x <= E]:
            cont.step(day, V.bars_on(data, idx, day))
            dd = el[el["date"] == day]
            if len(dd):
                dd = dd.assign(eligible=True).sort_values(["rs", "ticker"],
                                                          ascending=[False, True])
                cont.queue_signals(day, dd.assign(rank=np.arange(1, len(dd) + 1)))
        a, b = full.equity_df(), cont.equity_df()
        np.testing.assert_allclose(a["equity"].values, b["equity"].values)
        self.assertEqual(len(full.s["ledger"]), len(cont.s["ledger"]))

    def test_signal_store_first_write_wins_and_late_flag(self):
        scan = pd.DataFrame([dict(ticker="AAA", signal_date="2026-01-05", rs=90., stop=95.,
                                  eligible=True, rank=1)])
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.csv"
            store.append_signals(scan, "2026-01-05T21:00:00+00:00", "2026-01-06", False, "r1", p)
            store.append_signals(scan, "2026-01-07T21:00:00+00:00", "2026-01-06", True, "r2", p)
            df = pd.read_csv(p)
        self.assertEqual(len(df), 1)
        self.assertEqual(df["generated_at"][0], "2026-01-05T21:00:00+00:00")
        self.assertFalse(df["late"][0])
        self.assertLess(pd.Timestamp(df["generated_at"][0]).tz_convert(None),
                        pd.Timestamp(df["scheduled_for"][0]))

    def test_daily_runner_catch_up_and_idempotent(self):
        import paper_run
        fr, spy = market(8, n_t=20, n=380)
        prices = pd.concat({**fr, "SPY": spy}, axis=1)
        uni = pd.DataFrame({"ticker": list(fr), "name": "", "sector": "Tech"})
        days = spy.index
        with tempfile.TemporaryDirectory() as d:
            kw = dict(universe=uni, root=Path(d), cfg=CFG)
            cut = lambda k: prices[prices.index <= days[k]]
            now = lambda k: datetime(days[k].year, days[k].month, days[k].day, 23, 0,
                                     tzinfo=timezone.utc)
            s1 = paper_run.daily(prices=cut(300), now=now(300), **kw)
            self.assertEqual([x["day"] for x in s1["sessions"]], [str(days[300].date())])
            s2 = paper_run.daily(prices=cut(304), now=now(304), **kw)     # 4 sessions missed
            self.assertEqual(len(s2["sessions"]), 4)
            self.assertTrue(all(x["late"] and x["queued"] == 0 for x in s2["sessions"][:-1]))
            self.assertFalse(s2["sessions"][-1]["late"])
            s3 = paper_run.daily(prices=cut(304), now=now(304), **kw)     # same data again
            self.assertEqual(s3["sessions"], [])
            P = store.paths("forward", Path(d))
            st = json.loads(P["state_file"].read_text())
            self.assertEqual(st["processed_through"], str(days[304].date()))
            self.assertEqual(st["kind"], "forward")
            self.assertTrue((P["state_dir"] / "summary.json").exists())
            # the 4 caught-up sessions produced snapshots, flagged late, never traded forward
            self.assertEqual(len(list(P["snapshots"].glob("*.json"))), 5)
            late_logged = [o for o in st["orders_log"] if o["outcome"] == "not_traded_late"]
            self.assertTrue(late_logged)
            self.assertTrue(all(t["origin"] == "forward" and not t["entry_processed_late"]
                                or t["entry_processed_late"] for t in st["ledger"]))

    def test_unfinished_bar_is_ignored(self):
        import paper_run
        fr, _ = market(9, n_t=3, n=300)
        today = fr["T00"].index[-1]
        intraday = datetime(today.year, today.month, today.day, 18, 0, tzinfo=timezone.utc)
        self.assertEqual(paper_run.closed_data_date(fr, intraday), fr["T00"].index[-2])


class Acceptance(unittest.TestCase):
    """Task 10 acceptance requirements 1-4."""

    def scan(self, ticker="AAA", rs=90., stop=95.):
        return pd.DataFrame([dict(ticker=ticker, signal_date="2026-01-05", rs=rs, stop=stop,
                                  eligible=True, rank=1, close=100., level=98.)])

    # 1) forward / backfill / historical strictly separated
    def test_forward_never_trades_late_signals(self):
        p = PaperPortfolio(cfg=DEFAULT, kind="forward") if False else \
            PaperPortfolio(__import__("paper.portfolio").portfolio.new_state(DEFAULT, "forward"),
                           DEFAULT, kind="forward")
        p.step("2026-01-05", {})
        n = p.queue_signals("2026-01-05", self.scan(), "2026-01-06T15:00:00+00:00",
                            "2026-01-06", late=True)
        self.assertEqual(n, 0)
        self.assertEqual(p.s["pending"], [])
        self.assertEqual(p.s["orders_log"][-1]["outcome"], "not_traded_late")

    def test_backfill_trades_late_signals_but_is_labelled(self):
        from paper.portfolio import new_state
        p = PaperPortfolio(new_state(DEFAULT, "backfill"), DEFAULT, kind="backfill")
        p.step("2026-01-05", {})
        p.queue_signals("2026-01-05", self.scan(), late=True)
        p.step("2026-01-06", {"AAA": {"O": 100, "H": 101, "L": 90, "C": 92}})
        self.assertEqual(p.s["ledger"][0]["origin"], "backfill")

    def test_kinds_cannot_be_mixed(self):
        from paper.portfolio import new_state
        with self.assertRaises(ValueError):
            PaperPortfolio(new_state(DEFAULT, "backfill"), DEFAULT, kind="forward")
        self.assertNotEqual(store.paths("forward")["state_file"],
                            store.paths("backfill")["state_file"])

    def test_is_late_boundary_is_the_session_open(self):
        self.assertFalse(store.is_late("2026-01-06T14:29:59+00:00", "2026-01-06"))  # 9:29:59 ET
        self.assertTrue(store.is_late("2026-01-06T14:30:00+00:00", "2026-01-06"))   # 9:30 ET
        self.assertFalse(store.is_late("2026-01-05T22:00:00+00:00", "2026-01-06"))

    # 2) immutable snapshots
    def test_snapshot_write_once_and_tamper_check(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d)
            meta = dict(strategy_id=store.strategy_id(DEFAULT), parameters=DEFAULT.as_dict(),
                        code_fingerprint=store.code_fingerprint(),
                        source=dict(downloaded_at="2026-01-05T22:00:00+00:00"))
            p = store.write_snapshot("2026-01-05", self.scan(), meta, f)
            store.write_snapshot("2026-01-05", self.scan(), meta, f)          # identical: ok
            with self.assertRaises(store.ImmutableError):
                store.write_snapshot("2026-01-05", self.scan(rs=99.), meta, f)
            body = json.loads(p.read_text())
            self.assertEqual(body["meta"]["parameters"]["min_rs"], 85)
            self.assertIn("combined", body["meta"]["code_fingerprint"])
            self.assertEqual(body["signals"][0]["rs"], 90.0)
            self.assertEqual(store.verify_snapshots(f), [])
            os.chmod(p, 0o644)
            p.write_text(p.read_text().replace("90.0", "91.0"))
            self.assertEqual(store.verify_snapshots(f), [p.name])

    def test_strategy_id_changes_with_parameters(self):
        self.assertNotEqual(store.strategy_id(DEFAULT), store.strategy_id(PaperConfig(min_rs=80)))

    # 4) rejected signals stored; labels only when observable, never rewritten
    def test_labels_only_when_observable(self):
        fr, _ = market(13, n_t=1, n=80)
        f = fr["T00"]
        sd = f.index[30]
        with tempfile.TemporaryDirectory() as d:
            sp, lp = Path(d) / "s.csv", Path(d) / "l.csv"
            scan = pd.DataFrame([dict(ticker="T00", signal_date=sd, rs=40., eligible=False)])
            store.append_signals(scan, "x", "y", False, "r", sp)              # rejected signal
            store.update_labels(fr, f.index[34], sp, lp)                      # 4 bars later
            a = pd.read_csv(lp).iloc[0]
            self.assertTrue(pd.isna(a["fwd_ret_5"]) and pd.notna(a["fwd_ret_1"]))
            self.assertEqual(a["fwd_ret_1_observed"], str(f.index[31].date()))
            store.update_labels(fr, f.index[60], sp, lp)
            b = pd.read_csv(lp).iloc[0]
            self.assertAlmostEqual(b["fwd_ret_5"], f["Close"].iloc[35] / f["Close"].iloc[30] - 1)
            self.assertEqual(b["fwd_ret_1"], a["fwd_ret_1"])                  # never rewritten
            fr2 = {"T00": f.assign(Close=f["Close"] * 2)}                     # data revised
            store.update_labels(fr2, f.index[70], sp, lp)
            c = pd.read_csv(lp).iloc[0]
            self.assertEqual(c["fwd_ret_5"], b["fwd_ret_5"])
            self.assertFalse(pd.read_csv(sp)["eligible"].iloc[0])             # rejected kept

    def test_signal_rows_are_append_only(self):
        with tempfile.TemporaryDirectory() as d:
            sp = Path(d) / "s.csv"
            store.append_signals(self.scan(), "t1", "2026-01-06", False, "r1", sp)
            before = sp.read_text()
            store.append_signals(self.scan(rs=10.), "t2", "2026-01-06", True, "r2", sp)
            self.assertEqual(sp.read_text(), before)


class Metrics(unittest.TestCase):
    def test_performance(self):
        eq = pd.DataFrame({"date": pd.bdate_range("2026-01-05", periods=4),
                           "equity": [10000, 11000, 9900, 10450], "positions": [0, 1, 1, 0],
                           "spy_close": [100, 101, 99, 105]})
        led = pd.DataFrame({"net_pnl": [300., -100., -200.], "net_r": [1.5, -0.5, -1.0]})
        m = pm.performance(eq, led, 10000)
        self.assertAlmostEqual(m["return_pct"], 4.5)
        self.assertAlmostEqual(m["max_drawdown_pct"], -10.0)
        self.assertAlmostEqual(m["profit_factor"], 1.0)
        self.assertAlmostEqual(m["expectancy_usd"], 0.0)
        self.assertAlmostEqual(m["win_rate_pct"], 100 / 3)
        self.assertAlmostEqual(m["spy_return_pct"], 5.0)
        self.assertAlmostEqual(m["excess_return_pct"], -0.5)
        self.assertAlmostEqual(m["exposure_pct"], 50.0)

    def test_labels(self):
        fr, _ = market(10, n_t=1, n=60)
        f = fr["T00"]
        d = f.index[10]
        with tempfile.TemporaryDirectory() as tmp:
            p, lp = Path(tmp) / "s.csv", Path(tmp) / "l.csv"
            pd.DataFrame([dict(ticker="T00", signal_date=str(d.date()))]).to_csv(p, index=False)
            store.update_labels(fr, f.index[-1], p, lp)
            r = pd.read_csv(lp).iloc[0]
        self.assertAlmostEqual(r["fwd_ret_5"], f["Close"].iloc[15] / f["Close"].iloc[10] - 1)
        self.assertAlmostEqual(r["mae_20"], f["Low"].iloc[11:31].min() / f["Close"].iloc[10] - 1)


if __name__ == "__main__":
    unittest.main()
