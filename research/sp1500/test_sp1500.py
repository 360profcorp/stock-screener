"""Tests for the S&P 1500 research (synthetic data only — they prove mechanics, not edge).

    python -m unittest research.sp1500.test_sp1500 -v
"""
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import backtest as bt
from research.sp1500 import data as D
from research.sp1500 import engine as E
from research.sp1500 import rules as R
from research.sp1500 import run as RUN
from research.sp1500 import universe as U


def walk(n=420, seed=0, start=50.0, drift=0.0005):
    rng = np.random.default_rng(seed)
    c = start * np.exp(np.cumsum(rng.normal(drift, 0.02, n)))
    o = c * np.exp(rng.normal(0, 0.005, n))
    h = np.maximum(o, c) * (1 + rng.uniform(0, 0.015, n))
    lo = np.minimum(o, c) * (1 - rng.uniform(0, 0.015, n))
    v = rng.uniform(1e6, 3e6, n)
    idx = pd.bdate_range("2022-01-03", periods=n)
    return pd.DataFrame(dict(Open=o, High=h, Low=lo, Close=c, Volume=v, Dividends=0.0,
                             **{"Stock Splits": 0.0}), index=idx)


def flat(n=40, px=100.0):
    idx = pd.bdate_range("2024-01-02", periods=n)
    return pd.DataFrame(dict(Open=px, High=px * 1.02, Low=px * 0.98, Close=px, Volume=1e6,
                             Dividends=0.0), index=idx)


def universe_frames(k=8, n=420):
    frames = {f"T{j}": walk(n, seed=j, drift=0.001 * (j - k / 2) / k) for j in range(k)}
    spy = walk(n, seed=99)
    meta = pd.DataFrame(dict(ticker=list(frames), group=["sp500"] * 4 + ["sp400"] * 2 +
                             ["sp600"] * (k - 6), sector="S"))
    return frames, spy, meta


class TestTrades(unittest.TestCase):
    def x(self, f):
        return E.arrays(f)

    def test_short_gap_through_stop_is_no_trade(self):
        f = flat()
        f.loc[f.index[11], ["Open", "High", "Low", "Close"]] = [112, 113, 108, 110]
        r = E.model_trade(self.x(f), 10, "short", stop=110.0)
        self.assertEqual(r["trade_status"], "no_trade_gap_through_stop")

    def test_short_stop_on_entry_bar_fills_at_stop_later_gap_at_open(self):
        f = flat()
        f.loc[f.index[11], ["High"]] = 106
        r = E.model_trade(self.x(f), 10, "short", stop=105.0)
        self.assertEqual((r["exit_reason"], r["exit"], r["bars_held"]), ("stop", 105.0, 0))
        g = flat()
        g.loc[g.index[13], ["Open", "High", "Low", "Close"]] = [109, 110, 107, 108]
        r = E.model_trade(self.x(g), 10, "short", stop=105.0)
        self.assertEqual((r["exit"], r["bars_held"]), (109, 2))           # gap: worse than stop
        self.assertAlmostEqual(r["gross_ret"], -0.09)
        self.assertAlmostEqual(r["gross_r"], -0.09 / 0.05)

    def test_short_pnl_dividends_and_borrow(self):
        f = flat(60)
        f.loc[f.index[11:], ["Open", "High", "Low", "Close"]] = [100, 101, 89, 90]
        f.loc[f.index[11], "Open"] = 100
        f.loc[f.index[15], "Dividends"] = 1.0           # ex-date inside (entry, exit]
        f.loc[f.index[11], "Dividends"] = 5.0           # ex-date ON the entry day: not owed
        r = E.model_trade(self.x(f), 10, "short", stop=110.0)
        self.assertEqual((r["exit_reason"], r["bars_held"]), ("time", 20))
        self.assertAlmostEqual(r["gross_ret"], 0.10)
        self.assertAlmostEqual(r["dividends_ps"], 1.0)
        row = E.apply_costs(dict(r, direction="short"))
        self.assertIsNone(row["net_r_base_unknown"])
        days = r["calendar_days"]
        exp = (0.10 - 10 / 1e4 * (100 + 90) / 100 - 0.10 * days / 365 - 0.01) / 0.10
        self.assertAlmostEqual(row["net_r_base_hot"], exp)
        self.assertLess(row["net_r_stress_hot"], row["net_r_base_hot"])

    def test_mfe_mae_truncated_at_exit(self):
        f = flat(60)
        f.loc[f.index[12], "Low"] = 90                  # long stopped at 95
        f.loc[f.index[20], "High"] = 200                # after the exit: must not count
        r = E.model_trade(self.x(f), 10, "long", stop=95.0)
        self.assertEqual(r["exit_reason"], "stop")
        self.assertLess(r["mfe_pct"], 3)

    def test_same_bar_stop_and_target_is_stop(self):
        f = flat()
        f.loc[f.index[12], ["High", "Low"]] = [150, 90]
        b = E.barrier(self.x(f), 10, "long", stop=95.0)
        self.assertEqual((b["barrier"], b["barrier_r"]), ("ambiguous_same_bar", -1.0))
        f = flat()
        f.loc[f.index[12], ["High", "Low"]] = [110, 70]
        b = E.barrier(self.x(f), 10, "short", stop=105.0)
        self.assertEqual(b["barrier"], "ambiguous_same_bar")
        f = flat()
        f.loc[f.index[12], "Low"] = 75
        self.assertEqual(E.barrier(self.x(f), 10, "short", stop=105.0)["barrier"], "target")

    def test_long_trade_equals_production_simulate(self):
        frames, spy, meta = universe_frames()
        sig, data = E.detect(frames, spy, meta, ref500=list(frames)[:4])
        lab = E.add_outcomes(sig[sig["direction"] == "long"], data, spy.index, spy.index[-1])
        self.assertGreater(len(lab), 0)
        for mode in lab["strategy"].unique():
            s = lab[lab["strategy"] == mode]
            raw = pd.DataFrame(dict(ticker=s["ticker"], mode=mode, i=s["i"],
                                    date=s["signal_date"], close=s["close"], level=s["level"],
                                    stop_base=s["stop_base"], rs=99, vol_ratio=1.0))
            tr = bt.simulate(raw, data, mode, hold=20, stop_buf=3.0, min_rs=0, entry_at="open",
                             one_per_ticker=False, include_open=True)
            mine = s[s["trade_status"] == "closed"].sort_values(["ticker", "i"])
            ref = tr[tr["status"] == "closed"].sort_values(["ticker", "signal_date"])
            self.assertEqual(len(mine), len(ref))
            np.testing.assert_allclose(mine["gross_r"].values, ref["r"].values, rtol=1e-9)


class TestNonOverlap(unittest.TestCase):
    def test_matches_production_one_per_ticker(self):
        frames, spy, meta = universe_frames()
        sig, data = E.detect(frames, spy, meta, ref500=list(frames)[:4])
        lab = E.add_outcomes(sig[sig["strategy"] == "breakout"], data, spy.index,
                             spy.index[-1])
        keep = lab[E.non_overlapping(lab) & (lab["trade_status"] == "closed")]
        raw = pd.DataFrame(dict(ticker=lab["ticker"], mode="breakout", i=lab["i"],
                                date=lab["signal_date"], close=lab["close"], level=lab["level"],
                                stop_base=lab["stop_base"], rs=99, vol_ratio=1.0))
        tr = bt.simulate(raw, data, "breakout", hold=20, stop_buf=3.0, min_rs=0,
                         entry_at="open", one_per_ticker=True)
        self.assertGreater(len(tr), 0)
        self.assertEqual(len(keep), len(tr))
        np.testing.assert_allclose(np.sort(keep["gross_r"].values), np.sort(tr["r"].values))


class TestLabels(unittest.TestCase):
    def setUp(self):
        self.frames, self.spy, self.meta = universe_frames()
        self.sig, self.data = E.detect(self.frames, self.spy, self.meta, list(self.frames)[:4])

    def test_features_do_not_see_future(self):
        day = self.spy.index[350]
        ch = {t: f.copy() for t, f in self.frames.items()}
        for f in list(ch.values()) + []:
            f.loc[f.index > day, ["Open", "High", "Low", "Close"]] *= 3.0
            f.loc[f.index > day, "Volume"] *= 7
        spy2 = self.spy.copy()
        spy2.loc[spy2.index > day, ["Open", "High", "Low", "Close"]] *= 0.3
        s2, _ = E.detect(ch, spy2, self.meta, list(self.frames)[:4])
        cols = ["signal_id", "level", "stop_base", "stop"] + E.FEATURES
        a = self.sig[self.sig["signal_date"] <= day][cols].reset_index(drop=True)
        b = s2[s2["signal_date"] <= day][cols].reset_index(drop=True)
        self.assertGreater(len(a), 0)
        pd.testing.assert_frame_equal(a, b)

    def test_labels_only_when_observable(self):
        end = self.spy.index[-1]
        lab = E.add_outcomes(self.sig, self.data, self.spy.index, end)
        for h in R.LABEL_HORIZONS:
            m = lab[lab[f"px_ret_{h}_status"] == "mature"]
            self.assertTrue((pd.to_datetime(m[f"px_ret_{h}_observable"]) <= end).all())
            late = lab[pd.to_datetime(lab["signal_date"]) > self.spy.index[-1 - h]]
            self.assertTrue((late[f"px_ret_{h}_status"] == "immature").all())
            self.assertTrue(late[f"px_ret_{h}"].isna().all())
        closed = lab[lab["trade_status"] == "closed"]
        self.assertTrue((pd.to_datetime(closed["observable_trade"]) <= end).all())

    def test_missing_bar_label_empty_not_shifted(self):
        f = flat(60)
        cal = f.index
        g = f.drop(f.index[15])                          # ticker misses one market session
        x = E.arrays(g)
        sig = pd.DataFrame([dict(ticker="X", i=10, signal_date=g.index[10], direction="long",
                                 stop=90.0, strategy="retest")])
        lab = E.add_outcomes(sig, {"X": x}, cal, cal[-1])
        self.assertEqual(lab.iloc[0]["px_ret_5_status"], "missing_bar")
        self.assertTrue(pd.isna(lab.iloc[0]["px_ret_5"]))
        self.assertEqual(lab.iloc[0]["px_ret_1_status"], "mature")
        h = flat(60).drop(f.index[11])                   # missing entry session
        lab = E.add_outcomes(sig, {"X": E.arrays(h)}, cal, cal[-1])
        self.assertEqual(lab.iloc[0]["entry_delay_sessions"], 1)

    def test_splits_chronological_with_purge(self):
        lab = E.assign_splits(E.add_outcomes(self.sig, self.data, self.spy.index,
                                             self.spy.index[-1]), self.spy.index)
        v0 = pd.Timestamp(lab["split_validation_start"].iloc[0])
        t0 = pd.Timestamp(lab["split_test_start"].iloc[0])
        sd = pd.to_datetime(lab["signal_date"])
        cal = pd.DatetimeIndex(self.spy.index)
        pos = {d: k for k, d in enumerate(cal)}
        hend = sd.map(lambda d: cal[min(pos[d] + 21, len(cal) - 1)])   # entry + 20 bars
        tr = lab["split"] == "train"
        self.assertTrue((hend[tr] < v0).all())
        ex = pd.to_datetime(lab["exit_date"], errors="coerce")
        self.assertTrue((ex[tr].dropna() < v0).all())                  # every label observed
        self.assertTrue((ex[lab["split"] == "validation"].dropna() < t0).all())
        # the v1.0 purge (signal + 20 sessions) would have let labels end ON the boundary
        old = sd.map(lambda d: cal[min(pos[d] + 20, len(cal) - 1)])
        leak = (sd < v0) & (old < v0) & (hend >= v0)
        self.assertTrue(leak.any())                                    # the case exists
        self.assertFalse((tr & leak).any())                            # and is purged now
        self.assertTrue((sd[lab["split"] == "validation"] >= v0).all())
        self.assertTrue((hend[lab["split"] == "validation"] < t0).all())
        self.assertTrue((sd[lab["split"] == "test"] >= t0).all())

    def test_rejection_reasons(self):
        r = E.rejection_reasons(self.sig)
        long = self.sig["direction"] == "long"
        bad_rs = long & ~(self.sig["rs_ref500"] >= 85)
        self.assertTrue(r[bad_rs].str.contains("rs").all())
        self.assertTrue(len(r[(r == "")]) <= len(r))
        off = E.rejection_reasons(self.sig, market="off")
        self.assertFalse(off.str.contains("market").any())


class TestRS(unittest.TestCase):
    def test_percentile_matches_production(self):
        frames, _, _ = universe_frames()
        sc = E.rs_scores(frames)
        pd.testing.assert_frame_equal(E.rs_percentile(sc), bt.rs_history(frames))
        sub = list(frames)[:4]
        ref = E.rs_percentile(sc, sub)[sub]
        prod = bt.rs_history({t: frames[t] for t in sub})
        pd.testing.assert_frame_equal(ref, prod, check_names=False)

    def test_pit_mask_reference(self):
        frames, _, _ = universe_frames()
        sc = E.rs_scores(frames)
        day = sc.index[300]
        tl = [(sc.index[-1] + pd.Timedelta(days=1), {"T0", "T1"}), (day, {"T0", "T2"})]
        m = E.pit_mask(tl, sc.index, sc.columns)
        self.assertTrue(m.loc[sc.index[299], "T2"] and not m.loc[day, "T2"])
        self.assertTrue(m.loc[day, "T1"] and not m.loc[sc.index[299], "T1"])


class TestUniverse(unittest.TestCase):
    def test_overlap_resolution_needs_dated_evidence(self):
        lists = {"sp400": {"CORT", "EAT", "FORM", "A"}, "sp600": {"CORT", "EAT", "FORM", "B"}}
        ch = {"sp400": pd.DataFrame(dict(date=pd.to_datetime(["2025-03-01"]), added=["EAT"],
                                         removed=[None])),
              "sp600": pd.DataFrame(dict(date=pd.to_datetime(["2025-06-01"]), added=[None],
                                         removed=["FORM"]))}
        res = U.resolve_overlaps(lists, {"sp400": None, "sp600": None}, ch).set_index("ticker")
        self.assertEqual(res.at["EAT", "group"], "sp400")
        self.assertEqual(res.at["FORM", "group"], "sp400")   # removed from 600 -> other list
        self.assertEqual(res.at["CORT", "group"], "ambiguous")
        self.assertEqual(res.at["A", "resolution"], "single")
        res2 = U.resolve_overlaps(lists, {"sp400": pd.Timestamp("2026-10-01").date(),
                                          "sp600": pd.Timestamp("2026-10-10").date()}, ch)
        self.assertEqual(res2.set_index("ticker").at["CORT", "group"], "sp600")

    def test_pit_members(self):
        ch = pd.DataFrame(dict(date=pd.to_datetime(["2025-01-10", "2025-06-02"]),
                               added=["NEW", "N2"], removed=["OLD", "O2"]))
        tl = U.pit_members({"NEW", "N2", "X"}, ch, "2024-01-01", "2026-01-01")
        self.assertEqual(U.member_on(tl, "2024-12-31"), {"OLD", "O2", "X"})
        self.assertEqual(U.member_on(tl, "2025-03-01"), {"NEW", "O2", "X"})
        self.assertEqual(U.member_on(tl, "2025-12-01"), {"NEW", "N2", "X"})
        self.assertEqual(U.removed_since(ch, "2025-01-01", {"NEW", "N2", "X"}), ["O2", "OLD"])

    def test_share_class_alignment(self):
        self.assertEqual(U.align_share_class(["BRKB", "AAPL", "BFB"], ["BRK-B", "AAPL", "BF-B"]),
                         {"BRKB": "BRK-B", "BFB": "BF-B"})

    def test_parse_ishares(self):
        txt = ("iShares Core S&P Mid-Cap ETF\nFund Holdings as of,\"Oct 10, 2026\"\n\n"
               "Ticker,Name,Sector,Asset Class\nCORT,CORCEPT,Health Care,Equity\n"
               "BRKB,BERKSHIRE,Financials,Equity\nUSD,CASH,Cash,Cash\n")
        df, as_of = U.parse_ishares(txt)
        self.assertEqual(str(as_of), "2026-10-10")
        self.assertEqual(list(df["ticker"]), ["CORT", "BRKB"])


class TestData(unittest.TestCase):
    def test_clean_bars_counts_invalid(self):
        f = flat(10)
        f.iloc[3, f.columns.get_loc("High")] = 50
        f.iloc[5, f.columns.get_loc("Close")] = -1
        c, n = D.clean_bars(f)
        self.assertEqual((len(c), n), (8, 2))

    def test_download_retries_cache_and_no_substitution(self):
        calls = []

        def dl(ch):
            calls.append(list(ch))
            if len(calls) == 1:
                raise RuntimeError("429 Too Many Requests")
            f = flat(30)
            return pd.concat({"AAA": f}, axis=1)              # BBB absent from the response
        with tempfile.TemporaryDirectory() as d:
            fr, rep = D.download(["AAA", "BBB"], cache_dir=d, asof="x", pause=0,
                                 downloader=dl, log=lambda m: None)
            self.assertEqual(len(calls), 2)
            self.assertEqual(set(fr), {"AAA"})
            r = rep.set_index("ticker")
            self.assertEqual(r.at["BBB", "status"], "missing")
            fr2, _ = D.download(["AAA", "BBB"], cache_dir=d, asof="x", pause=0,
                                downloader=dl, log=lambda m: None)
            self.assertEqual(len(calls), 2)                   # served from cache
            self.assertEqual(D.frame_sha(fr["AAA"]), D.frame_sha(fr2["AAA"]))

    def test_download_gives_up_after_bounded_retries(self):
        n = []

        def dl(ch):
            n.append(1)
            raise RuntimeError("429")
        fr, rep = D.download(["AAA"], retries=2, pause=0, downloader=dl, log=lambda m: None)
        self.assertEqual((len(n), fr), (3, {}))
        self.assertEqual(rep.iloc[0]["status"], "missing")

    def test_missing_sessions(self):
        f = flat(20)
        m = D.missing_sessions({"X": f.drop(f.index[5])}, f.index)
        self.assertEqual(int(m.iloc[0]["missing_sessions"]), 1)


class TestShortRules(unittest.TestCase):
    def test_breakdown(self):
        f = flat(40)
        f.loc[f.index[-1], ["Open", "High", "Low", "Close"]] = [99, 100, 94, 95]
        x = E.arrays(f)
        lvl, sb = R.breakdown_at(x, len(f) - 1)
        self.assertAlmostEqual(lvl, 98)
        self.assertAlmostEqual(sb, 102)
        self.assertIsNone(R.breakdown_at(x, len(f) - 2))

    def test_failed_breakout(self):
        f = flat(40)
        f.loc[f.index[-3], ["Open", "High", "Low", "Close"]] = [101, 106, 100, 105]
        f.loc[f.index[-2], ["Open", "High", "Low", "Close"]] = [104, 105, 101, 102]
        f.loc[f.index[-1], ["Open", "High", "Low", "Close"]] = [101, 101.5, 97, 98]
        lvl, sb = R.failed_breakout_at(E.arrays(f), len(f) - 1)
        self.assertAlmostEqual(lvl, 102)
        self.assertAlmostEqual(sb, 106)

    def test_breakdown_retest(self):
        f = flat(45)
        seq = [(97, 97.5, 95, 95.5), (95.5, 96, 93, 93.5), (93.5, 96.5, 93.4, 96.2),
               (96.2, 98.5, 95.8, 97.0), (97, 97.2, 94, 94.5)]
        for k, bar in enumerate(seq):
            f.loc[f.index[-len(seq) + k], ["Open", "High", "Low", "Close"]] = bar
        hit = R.breakdown_retest_at(E.arrays(f), len(f) - 1)
        self.assertIsNotNone(hit)
        self.assertAlmostEqual(hit[0], 98)
        self.assertAlmostEqual(hit[1], 98.5)

    def test_short_rules_ignore_future_bars(self):
        f = walk(200, seed=3, drift=-0.002)
        x = E.arrays(f)
        g = f.copy()
        g.iloc[150:, :4] *= 5
        y = E.arrays(g)
        for name, rule in R.SHORT_RULES.items():
            for i in range(30, 150):
                self.assertEqual(rule(x, i), rule(y, i), name)


class TestRun(unittest.TestCase):
    def test_write_once(self):
        with tempfile.TemporaryDirectory() as d:
            p, m = Path(d) / "a" / "x.csv", {}
            RUN.write_once(p, "1", m, Path(d))
            RUN.write_once(p, "1", m, Path(d))
            with self.assertRaises(FileExistsError):
                RUN.write_once(p, "2", m, Path(d))
            self.assertEqual(p.read_text(), "1")
            self.assertIn("a/x.csv", m)

    def test_completed_end(self):
        spy = flat(10)
        last = spy.index[-1]
        early = datetime(last.year, last.month, last.day, 15, 0, tzinfo=timezone.utc)  # 11 NY
        late = datetime(last.year, last.month, last.day, 23, 0, tzinfo=timezone.utc)   # 19 NY
        self.assertEqual(RUN.completed_end(spy, early), spy.index[-2])
        self.assertEqual(RUN.completed_end(spy, late), last)

    def test_equivalence_with_find_signals(self):
        frames, spy, meta = universe_frames()
        ref = list(frames)[:4]
        sig, _ = E.detect(frames, spy, meta, ref)
        eq = RUN.equivalence({t: frames[t] for t in ref}, sig)
        self.assertTrue(eq["ok"], eq)


if __name__ == "__main__":
    unittest.main()


class TestPitSnapshots(unittest.TestCase):
    def test_snapshots_timeline_and_press_release_evidence(self):
        snaps = U.parse_pit500('date,tickers\n2024-01-02,"A,B,BRK.B"\n2025-03-01,"A,C,BRK.B"\n')
        tl = U.pit_from_snapshots(snaps, {"A", "C", "D"}, "2026-10-14")
        self.assertEqual(U.member_on(tl, "2024-06-01"), {"A", "B", "BRK-B"})
        self.assertEqual(U.member_on(tl, "2025-03-01"), {"A", "C", "BRK-B"})
        self.assertEqual(U.member_on(tl, "2026-10-14"), {"A", "C", "D"})
        ev = U.load_evidence()
        res = U.resolve_overlaps({"sp400": {"FORM"}, "sp600": {"FORM"}},
                                 {"sp400": None, "sp600": None}, {}, ev).iloc[0]
        self.assertEqual((res["group"], res["resolution"]), ("sp400", "press_release"))
