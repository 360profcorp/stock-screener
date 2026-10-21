"""Synthetic tests for the bull flag v1 detector (PREREG_BULLFLAG_v1 §2). No real data."""
import unittest

import numpy as np
import pandas as pd

import backtest as bt
from research.bull_flag import rules as F


def make(pole_gain=0.15, pole_len=10, flag_len=6, depth=0.06, flag_vol=0.5,
         brk_vol=1.5, brk_above=0.01, base=300, tail=5, top_extra_in_flag=None):
    """Flat base, then a pole, a flag, a breakout bar (index returned), then `tail` bars."""
    o, h, l, c, v = [], [], [], [], []

    def bar(close, rng=0.004, vol=1.0, high=None, low=None):
        o.append(close * (1 - rng / 4)); c.append(close)
        h.append(high if high is not None else close * (1 + rng))
        l.append(low if low is not None else close * (1 - rng))
        v.append(vol * 1e6)
    for k in range(base):
        bar(100.0)                                            # base: high 100.4, low 99.6
    start = 100.0
    for k in range(1, pole_len + 1):                          # pole: steady rise
        bar(start * (1 + pole_gain * k / pole_len) * 0.995, vol=2.0)
    top = h[-1] = start * (1 + pole_gain) * 0.995 * 1.004
    T = len(c) - 1
    flag_low = top * (1 - depth)
    for k in range(flag_len):                                  # flag: drifts down, low volume
        close = top * (1 - depth * 0.6) * (1 + 0.002 * ((k % 2) - 0.5))
        lo = flag_low if k == flag_len // 2 else close * 0.996
        hi = top * 0.985 if k == 0 else close * 1.003
        if top_extra_in_flag is not None and k == flag_len - 1:
            hi = top * (1 + top_extra_in_flag)
        bar(close, vol=flag_vol, high=hi, low=lo)
    flag_high = max(h[T + 1:])
    bar(flag_high * (1 + brk_above), vol=brk_vol, high=flag_high * (1 + brk_above + 0.003),
        low=flag_high * 0.99)
    i = len(c) - 1
    for k in range(tail):
        bar(c[-1] * 1.002)
    idx = pd.bdate_range("2023-01-02", periods=len(c))
    df = pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c, "Volume": v}, index=idx)
    return df, i, T


def at(df, i):
    return F.flag_at(bt.indicators(df), i)


class TestFlagRules(unittest.TestCase):
    def test_reference_flag_detected_on_the_breakout_bar_only(self):
        df, i, T = make()
        x = bt.indicators(df)
        d = F.flag_at(x, i, return_detail=True)
        self.assertIsNotNone(d)
        self.assertEqual((d["T"], d["n_flag"]), (T, 6))
        self.assertAlmostEqual(d["level"], df["High"].iloc[T + 1:i].max())
        self.assertAlmostEqual(d["stop_base"], min(df["Low"].iloc[T + 1:i].min(), df["Low"].iloc[i]))
        self.assertIsNone(F.flag_at(x, i - 1))               # no breakout yet
        for k in range(i - 20, i):
            self.assertIsNone(F.flag_at(x, k), k)

    def test_pole_too_small(self):
        df, i, _ = make(pole_gain=0.09)
        self.assertIsNone(at(df, i))

    def test_pole_too_slow(self):
        df, i, _ = make(pole_len=25)                          # 15 % spread over 25 sessions
        self.assertIsNone(at(df, i))

    def test_depth_bounds(self):
        self.assertIsNone(at(*make(depth=0.02)[:2]))
        self.assertIsNone(at(*make(depth=0.14)[:2]))
        self.assertIsNotNone(at(*make(depth=0.10, pole_gain=0.30)[:2]))

    def test_retracement_above_half_of_the_pole(self):
        df, i, _ = make(pole_gain=0.13, depth=0.09)           # 9 % of top > 50 % of the pole
        self.assertIsNone(at(df, i))

    def test_flag_length_bounds(self):
        self.assertIsNone(at(*make(flag_len=2)[:2]))
        self.assertIsNotNone(at(*make(flag_len=3)[:2]))
        self.assertIsNotNone(at(*make(flag_len=12)[:2]))
        self.assertIsNone(at(*make(flag_len=13)[:2]))

    def test_long_flag_is_not_reread_as_a_shorter_one(self):
        df, i, T = make(flag_len=13)
        self.assertEqual(i - 1 - T, 13)
        self.assertIsNone(at(df, i))

    def test_flag_bar_above_the_top(self):
        df, i, _ = make(top_extra_in_flag=0.002)
        self.assertIsNone(at(df, i))

    def test_volume_rules(self):
        self.assertIsNone(at(*make(flag_vol=2.5)[:2]))        # flag volume not lower than the pole
        self.assertIsNone(at(*make(brk_vol=0.4)[:2]))         # breakout volume below the flag's

    def test_close_must_exceed_the_flag_high(self):
        self.assertIsNone(at(*make(brk_above=-0.002)[:2]))

    def test_warmup(self):
        df, i, _ = make(base=200)                             # breakout before bar 260
        self.assertLess(i, F.MIN_BARS)
        self.assertIsNone(at(df, i))


class TestNoLookAhead(unittest.TestCase):
    def test_future_bars_never_change_a_decision(self):
        rng = np.random.default_rng(1)
        for kw in ({}, dict(flag_len=3), dict(flag_len=12), dict(depth=0.11, pole_gain=0.3)):
            df, i, _ = make(tail=30, **kw)
            full = bt.indicators(df)
            fut = df.copy()
            fut.iloc[i + 1:, :4] *= rng.uniform(0.5, 1.5, size=(len(df) - i - 1, 1))
            fut.iloc[i + 1:, 4] *= 10
            pert = bt.indicators(fut)
            for k in range(i - 30, i + 1):
                cut = bt.indicators(df.iloc[:k + 1])
                self.assertEqual(F.flag_at(full, k), F.flag_at(cut, k), (kw, k))
                self.assertEqual(F.flag_at(full, k), F.flag_at(pert, k), (kw, k))


class TestBreakoutImplication(unittest.TestCase):
    def test_every_flag_is_a_3_day_breakout(self):
        rng = np.random.default_rng(7)
        hits = 0
        for _ in range(200):
            kw = dict(pole_gain=rng.uniform(0.12, 0.4), pole_len=int(rng.integers(3, 15)),
                      flag_len=int(rng.integers(3, 13)), depth=rng.uniform(0.03, 0.12),
                      flag_vol=rng.uniform(0.2, 1.5), brk_vol=rng.uniform(0.5, 3),
                      brk_above=rng.uniform(-0.005, 0.03))
            df, i, _ = make(**kw)
            x = bt.indicators(df)
            if F.flag_at(x, i) is not None:
                hits += 1
                self.assertIsNotNone(bt.breakout_at(x, i, 3), kw)
        # random walks as well: wherever a flag fires, breakout fires
        for s in range(30):
            r = np.random.default_rng(100 + s)
            n = 700
            cl = 50 * np.exp(np.cumsum(r.normal(0.001, 0.025, n)))
            op = cl * np.exp(r.normal(0, 0.008, n))
            df = pd.DataFrame({"Open": op, "High": np.maximum(op, cl) * (1 + r.uniform(0, .02, n)),
                               "Low": np.minimum(op, cl) * (1 - r.uniform(0, .02, n)), "Close": cl,
                               "Volume": r.uniform(5e5, 3e6, n)},
                              index=pd.bdate_range("2021-01-04", periods=n))
            x = bt.indicators(df)
            for k in range(F.MIN_BARS, n):
                if F.flag_at(x, k) is not None:
                    hits += 1
                    self.assertIsNotNone(bt.breakout_at(x, k, 3), (s, k))
        self.assertGreater(hits, 50)


if __name__ == "__main__":
    unittest.main()


class TestProtocolV11(unittest.TestCase):
    def test_experiment_a_uses_the_breakout_stop(self):
        from research.bull_flag import protocol as Pr
        df, i, _ = make()
        x = bt.indicators(df)
        a = Pr.flag_filter_at(x, i)
        self.assertEqual(a, bt.breakout_at(x, i, 3))              # breakout level and stop
        self.assertNotEqual(a[1], F.flag_at(x, i)[1])             # differs from the structural stop
        self.assertIsNone(Pr.flag_filter_at(x, i - 1))
        df2, i2, _ = make(pole_gain=0.05)                         # no flag -> no A signal
        x2 = bt.indicators(df2)
        self.assertIsNone(Pr.flag_filter_at(x2, i2))

    def test_s4_matched_days_equal_weights_paired_bootstrap(self):
        from research.bull_flag import protocol as Pr
        rows = [("2024-01-02", "flag", 1.0), ("2024-01-02", "nonflag", 0.0),
                ("2024-01-02", "nonflag", 0.0), ("2024-01-02", "nonflag", 0.0),
                ("2024-02-05", "flag", 0.0), ("2024-02-05", "flag", 2.0),
                ("2024-02-05", "nonflag", 0.5),
                ("2024-03-04", "flag", 9.0),                        # unmatched: no non-flag
                ("2024-03-05", "nonflag", -9.0)]                    # unmatched: no flag
        t = pd.DataFrame(rows, columns=["signal_date", "group", "net_r"])
        r = Pr.s4_statistic(t, n_boot=2000)
        self.assertEqual(r["matched_days"], 2)
        self.assertAlmostEqual(r["S4"], ((1 - 0) + (1 - 0.5)) / 2)  # equal day weights
        self.assertEqual((r["n_flag"], r["n_nonflag"]), (3, 4))
        lo, hi = r["ci90"]
        self.assertTrue(lo <= r["S4"] <= hi)
        self.assertEqual(Pr.s4_statistic(t, n_boot=2000), r)        # deterministic seed
        neg = t.assign(net_r=-t["net_r"])
        self.assertAlmostEqual(Pr.s4_statistic(neg, n_boot=500)["S4"], -r["S4"])

    def test_combined_book_one_order_per_ticker_day_retest_first(self):
        from research.bull_flag import protocol as Pr
        d = pd.Timestamp("2024-01-03"); s = pd.Timestamp("2024-01-02")
        ret = pd.DataFrame([dict(ticker="AAA", date=d, signal_date=s, rs=90., entry=10., stop=9.5),
                            dict(ticker="BBB", date=d, signal_date=s, rs=95., entry=20., stop=19.)])
        flg = pd.DataFrame([dict(ticker="AAA", date=d, signal_date=s, rs=90., entry=10., stop=8.0),
                            dict(ticker="CCC", date=d, signal_date=s, rs=90., entry=30., stop=28.),
                            dict(ticker="DDD", date=d, signal_date=s, rs=99., entry=5., stop=4.5)])
        m = Pr.merge_candidates(ret, flg)
        self.assertEqual(list(m["ticker"]), ["DDD", "BBB", "AAA", "CCC"])  # RS desc, retest wins tie
        aaa = m[m["ticker"] == "AAA"].iloc[0]
        self.assertEqual((aaa["kind"], aaa["stop"]), ("retest", 9.5))     # retest's stop kept
        self.assertEqual(len(m), 4)                                       # one order for AAA
