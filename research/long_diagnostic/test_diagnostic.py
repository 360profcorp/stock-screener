"""Synthetic unit tests: no outside data and no broker code."""
import unittest

import numpy as np
import pandas as pd

import backtest as bt
import portfolio_bt as pf
from research.long_diagnostic import run as LD
from research.long_diagnostic.run import trade_path, reconcile, summarize_fills, equity_exposure


class Tests(unittest.TestCase):
    """Package tests (unchanged)."""

    def test_path_and_post_exit(self):
        dates = pd.bdate_range('2022-01-03', periods=8)
        x = dict(dates=dates.values, H=[101, 110, 102, 103, 110, 112, 115, 105],
                 L=[99, 96, 90, 92, 99, 105, 95, 90], C=[100, 98, 95, 99, 101, 109, 111, 99])
        p = trade_path(x, dates[1], dates[3], 100, 95)
        self.assertAlmostEqual(p['mfe_r'], 2)
        self.assertAlmostEqual(p['mae_r'], -2)
        self.assertIsNone(p['post_exit_5_close_ret_pct'])
        self.assertIsNone(p['post_exit_10_close_ret_pct'])

    def test_single_bar_unknown_order(self):
        x = dict(dates=pd.bdate_range('2022-03-01', periods=3), H=[110, 111, 102], L=[90, 90, 95], C=[100, 99, 98])
        p = trade_path(x, x['dates'][0], x['dates'][0], 100, 95)
        self.assertIsNone(p['mfe_r_excluding_exit_day'])
        self.assertTrue(p['exit_bar_intraday_order_unknown'])

    def test_recon_open_fee_only_entry(self):
        eq = pd.DataFrame([dict(equity=10009.)])
        fills = pd.DataFrame(columns=['net_pnl'])
        openp = [dict(shares=1, entry=100, mark=109)]
        r = reconcile(eq, fills, openp, 10000, 0)
        self.assertTrue(r['matches_cent'])

    def test_recon_loss(self):
        eq = pd.DataFrame([dict(equity=9995.)])
        fills = pd.DataFrame([dict(net_pnl=-5)])
        self.assertTrue(reconcile(eq, fills, [], 10000, 10)['matches_cent'])

    def test_stats(self):
        s = summarize_fills(pd.DataFrame(dict(net_pnl=[10, -5, -5], net_r=[2, -1, -1])))
        self.assertAlmostEqual(s['win_rate_pct'], 100/3)
        self.assertEqual(s['profit_factor'], 1)
        self.assertEqual(s['total_pnl_usd'], 0)

    def test_exposure(self):
        d = pd.DataFrame([dict(equity=100, cash=80, open_positions=1), dict(equity=120, cash=120, open_positions=0)])
        self.assertAlmostEqual(equity_exposure(d)['average_invested_pct'], 10)


class Added(unittest.TestCase):
    """Audit additions."""

    def test_post_exit_bounds_and_recovery(self):
        d = pd.bdate_range("2023-01-02", periods=30)
        C = np.r_[100, 96, 94, np.linspace(95, 120, 27)]
        x = dict(dates=d, H=C + 1, L=C - 1, C=C)
        p = trade_path(x, d[0], d[2], 100, 95)                    # a stop-out on day 3
        self.assertAlmostEqual(p["post_exit_5_close_ret_pct"], 100 * (C[7] / C[2] - 1))
        self.assertTrue(p["post_exit_20_close_above_entry"])
        self.assertAlmostEqual(p["post_exit_5_max_high_vs_exit_close_pct"], 100 * ((C[3:8] + 1).max() / C[2] - 1))
        self.assertAlmostEqual(p["mfe_r_excluding_exit_day"], (101 - 100) / 5)

    def test_dividends_window(self):
        d = pd.bdate_range("2023-01-02", periods=5)
        x = dict(dates=d, div=[0, .5, 0, .25, 1.0])
        self.assertAlmostEqual(LD.dividends_held(x, d[0], d[3], 10), 7.5)   # ex-dates in (entry, exit]

    def test_non_overlap(self):
        t = pd.DataFrame(dict(ticker=["A", "A", "A", "B"], date=pd.to_datetime(["2023-01-02", "2023-01-05", "2023-02-01", "2023-01-05"]),
                              exit_date=pd.to_datetime(["2023-01-20", "2023-01-25", pd.NaT, "2023-01-10"])))
        self.assertEqual(sorted(LD.non_overlap(t).index), [0, 2, 3])

    def test_cash_identity(self):
        op = [dict(shares=1, entry=100, mark=109)]
        ok = reconcile(pd.DataFrame([dict(equity=10009., cash=9900.)]), pd.DataFrame(columns=['net_pnl']), op, 10000, 0)
        self.assertTrue(ok["matches_cent"])
        self.assertAlmostEqual(ok["cash_residual_usd"], 0.0)
        bad = reconcile(pd.DataFrame([dict(equity=10009., cash=9800.)]), pd.DataFrame(columns=['net_pnl']), op, 10000, 0)
        self.assertFalse(bad["matches_cent"])

    def test_hypo_r(self):
        t = pd.DataFrame(dict(status=["closed", "open"], entry=[100., 100.], exit=[110., np.nan], stop=[95., 95.]))
        r = LD.hypo_net_r(t, 10)
        self.assertAlmostEqual(r[0], (110 * .999 - 100 * 1.001) / 5)
        self.assertTrue(np.isnan(r[1]))


def market(seed, n_t=25, n=420):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2019-01-02", periods=n)
    fr = {}
    for k in range(n_t):
        c = 50 * np.exp(np.cumsum(rng.normal(0.0007, 0.02, n)))
        o = c * np.exp(rng.normal(0, 0.012, n))
        h = np.maximum(o, c) * np.exp(np.abs(rng.normal(0, 0.01, n)))
        lo = np.minimum(o, c) * np.exp(-np.abs(rng.normal(0, 0.01, n)))
        fr[f"T{k:02d}"] = pd.DataFrame({"Open": o, "High": h, "Low": lo, "Close": c,
                                        "Volume": rng.integers(1e5, 1e6, n).astype(float)}, index=days)
    c = 400 * np.exp(np.cumsum(rng.normal(0.0004, 0.01, n)))
    spy = pd.DataFrame({"Open": c, "High": c * 1.005, "Low": c * .995, "Close": c, "Volume": 1e7}, index=days)
    return fr, spy


class EndToEnd(unittest.TestCase):
    """The whole diagnostic on a synthetic market: money identities, decomposition, funnel."""

    def test_replay_diagnostics_reconcile(self):
        fr, spy = market(3)
        sig, data = bt.find_signals(fr, modes=["breakout"])
        tr = bt.simulate(sig, data, "breakout", hold=20, stop_buf=3.0, min_rs=0, min_vol=0.0, max_risk=0.0,
                         market_ok=None, entry_at="open", one_per_ticker=False, include_open=True)
        tr["date"] = pd.to_datetime(tr["date"]).dt.normalize()
        tr = tr.sort_values(["date", "rs", "ticker"], ascending=[True, False, True], kind="stable").reset_index(drop=True)
        cal = sorted(spy.index)
        for fee in (10, 25):
            curve, ex, m = pf.replay(tr, data, start=cal[260], end=cal[-1], cost_bps=float(fee), open_at_end="mark",
                                     record_decisions=True, initial_cash=10000., risk_fraction=.01, max_positions=5,
                                     max_new_per_day=3, max_position_fraction=.2)
            rec = reconcile(curve, ex, m["open_positions"], 10000., fee)
            self.assertTrue(rec["matches_cent"], rec)
            obs, d = LD.make_diagnostics(tr, ex, curve, m, data, spy, fee)
            self.assertGreater(len(obs), 10)
            dec = d["decomposition_usd"]
            parts = sum(v for k, v in dec.items() if not k.startswith("total"))
            self.assertAlmostEqual(parts, dec["total = final equity - initial"], places=2)
            self.assertAlmostEqual(dec["total = final equity - initial"], curve["equity"].iloc[-1] - 10000, places=6)
            self.assertEqual(d["funnel"]["portfolio_closed"]["count"], len(ex))
            self.assertLessEqual(d["funnel"]["non_overlap_model_trades"]["count"], d["funnel"]["all_candidates"]["count"])
            self.assertEqual(sum(v["count"] for v in d["candidate_decisions"].values()),
                             len(m["decisions"]))
            g = obs[obs["gap_beyond_stop"]]
            self.assertTrue((g["exit"] < g["stop"]).all())
            self.assertTrue(((obs["reason"] == "time") | (obs["reason"] == "stop")).all())
            self.assertAlmostEqual(d["costs"]["closed_usd"], float(obs["costs_usd"].sum()), places=6)


if __name__ == '__main__':
    unittest.main()
