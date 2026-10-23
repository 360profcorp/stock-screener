"""Regression tests for the Trading tab tables (duplicate column labels crashed st.dataframe).

    python -m unittest test_trade_tab -v

The PyArrow and Streamlit AppTest checks run when those packages are installed (CI installs
them; set REQUIRE_UI_TESTS=1 to make their absence a failure instead of a skip).
"""
import importlib.util
import os
import unittest

import numpy as np
import pandas as pd

import trade_tab as tt

HAVE_PA = importlib.util.find_spec("pyarrow") is not None
try:
    from streamlit.testing.v1 import AppTest  # noqa: F401
    HAVE_ST = True
except Exception:
    HAVE_ST = False
REQUIRE = os.environ.get("REQUIRE_UI_TESTS") == "1"
T = {"mode_retest": "Retest", "mode_breakout": "Breakout", "mode_vcp": "VCP"}

# the exact shape the bot stores (trader.py: morning fill and same-day breakout)
POSITION = {"ticker": "AAPL", "mode": "retest", "rs": 91, "entry_date": "2026-10-13",
            "entry": 230.5, "stop": 221.0, "qty": 4, "dry": True, "checked": "2026-10-14",
            "signal_date": "2026-10-10", "how": "open"}
POSITION_CLOSE = dict(POSITION, ticker="NVDA", mode="breakout", how="close", qty=2,
                      entry=180.0, stop=172.0, dry=False, order_id="1", pending_fill=True,
                      entry_day_stop="unverified", entry_time="15:31")
OLD_POSITION = {k: v for k, v in POSITION.items() if k not in ("how", "dry")}  # older state
CLOSED = {"ticker": "MSFT", "mode": "vcp", "entry_date": "2026-09-01", "entry": 400.0,
          "exit_date": "2026-09-29", "exit": 420.0, "qty": 2, "reason": "time", "pnl": 40.0,
          "r": 1.2, "dry": True}
PLAN = {"ticker": "AMD", "mode": "retest", "rs": 95, "close": 150.0, "stop": 144.0,
        "est_qty": 6, "est_cost": 900.0}
ORDER = {"ticker": "AMD", "mode": "retest", "date": "2026-10-15", "est": 150.0, "stop": 144.0,
         "qty": 6, "dry": True}


def prices(tickers):
    idx = pd.bdate_range("2026-10-01", periods=10)
    return pd.concat({t: pd.DataFrame({"Close": np.linspace(200, 240, 10)}, index=idx)
                      for t in tickers}, axis=1)


def no_prices(tickers):
    raise RuntimeError("offline")


def tables(lang):
    X = tt.TX[lang]
    return {"plan": tt.plan_table([PLAN], T, X),
            "orders": tt.orders_table([ORDER], T, X),
            "positions": tt.positions_table([POSITION, POSITION_CLOSE, OLD_POSITION], T, X,
                                            prices, today="2026-10-15"),
            "positions_offline": tt.positions_table([POSITION], T, X, no_prices,
                                                    today="2026-10-15"),
            "closed": tt.closed_table([CLOSED], T, X)}


class TestLabels(unittest.TestCase):
    def test_old_labels_reproduce_the_crash_cause(self):
        old = dict(tt.TX["ru"]["cols"], how="Вход", entry_date="Вход")
        with self.assertRaises(ValueError) as e:
            tt._view(pd.DataFrame([POSITION]), tt.POS_COLS, old)
        self.assertIn("how", str(e.exception))
        self.assertIn("entry_date", str(e.exception))

    def test_all_labels_unique_per_language(self):
        for lang, X in tt.TX.items():
            v = list(X["cols"].values())
            self.assertEqual(len(v), len(set(v)), lang)
        self.assertEqual(set(tt.TX["ru"]["cols"]), set(tt.TX["en"]["cols"]))

    def test_every_table_unique_and_keeps_all_fields(self):
        for lang in tt.TX:
            C = tt.TX[lang]["cols"]
            for name, df in tables(lang).items():
                self.assertTrue(df.columns.is_unique, (lang, name, list(df.columns)))
            pos = tables(lang)["positions"]
            self.assertEqual(list(pos.columns), [C[c] for c in tt.POS_COLS])
            self.assertEqual(len(pos), 3)
            row = pos.iloc[0]
            self.assertEqual(row[C["ticker"]], "AAPL")
            self.assertEqual(row[C["entry_date"]], "2026-10-13")
            self.assertEqual(row[C["how"]], tt.TX[lang]["how"]["open"])
            self.assertEqual(pos.iloc[1][C["how"]], tt.TX[lang]["how"]["close"])
            self.assertEqual(pos.iloc[1][C["entry_day_stop"]],
                             tt.TX[lang]["eds"]["unverified"])            # limitation visible
            self.assertTrue(pd.isna(pos.iloc[2][C["how"]]))          # old state: empty, kept
            self.assertEqual(row[C["days"]], 2)
            self.assertAlmostEqual(row[C["last"]], 240.0)
            self.assertAlmostEqual(row[C["pnl_now"]], (240.0 - 230.5) * 4)
            self.assertTrue(pd.isna(tables(lang)["positions_offline"].iloc[0][C["last"]]))
            cl = tables(lang)["closed"].iloc[0]
            self.assertEqual((cl[C["entry_date"]], cl[C["exit_date"]]),
                             ("2026-09-01", "2026-09-29"))

    @unittest.skipUnless(HAVE_PA or REQUIRE, "pyarrow not installed")
    def test_tables_convert_to_pyarrow(self):
        import pyarrow as pa
        for lang in tt.TX:
            for name, df in tables(lang).items():
                pa.Table.from_pandas(df)                         # raised before the fix
        with self.assertRaises(ValueError):
            bad = pd.DataFrame([[1, 2]], columns=["Вход", "Вход"])
            pa.Table.from_pandas(bad)


class TestClosedSummary(unittest.TestCase):
    """Legacy one-line closed-trades summary must tolerate sparse/absent columns and show
    '—' (never 'nan') for unavailable metrics."""

    def test_normal(self):
        for lang in ("ru", "en"):
            s = tt.closed_summary([CLOSED], tt.TX[lang])
            self.assertNotIn("nan", s.lower())
            self.assertIn("1.20R", s)                      # avg R present
            self.assertIn("$+40", s)                       # total P&L present

    def test_both_pnl_and_r_columns_entirely_absent(self):
        # several closed trades, NONE carrying pnl or r
        closed = [{"ticker": "X1", "mode": "breakout", "entry_date": "2026-09-01",
                   "exit_date": "2026-09-15", "qty": 1},
                  {"ticker": "X2", "mode": "vcp", "entry_date": "2026-09-02",
                   "exit_date": "2026-09-09", "qty": 2}]
        for lang in ("ru", "en"):
            s = tt.closed_summary(closed, tt.TX[lang])
            self.assertNotIn("nan", s.lower())
            self.assertEqual(s.count("—"), 3)              # win rate, total P&L, avg R
            self.assertIn("2", s)                          # trade count still shown

    def test_pnl_present_r_absent(self):
        closed = [dict(CLOSED), {"ticker": "Y", "mode": "retest", "pnl": -5.0}]
        for c in closed:
            c.pop("r", None)
        for lang in ("ru", "en"):
            s = tt.closed_summary(closed, tt.TX[lang])
            self.assertNotIn("nan", s.lower())
            self.assertEqual(s.count("—"), 1)              # only avg R is "—"
            self.assertIn("$+35", s)                       # 40 + (-5)


@unittest.skipUnless(HAVE_ST or REQUIRE, "streamlit not installed")
class TestApp(unittest.TestCase):
    """Run the whole app (all tabs execute on every run) with an unlocked Trading tab."""

    def run_app(self, lang, state):
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file("app.py", default_timeout=180)
        at.secrets["STATE_PASSWORD"] = "test"
        at.session_state["lang"] = "EN" if lang == "en" else "RU"
        at.session_state["bot_unlocked"] = True
        at.session_state["bot_state"] = state
        at.session_state["bot_sha"] = "abc"
        at.run()
        return at

    def test_app_with_open_position_and_empty_tables(self):
        full = {"mode": "dry", "positions": [POSITION, POSITION_CLOSE], "closed": [CLOSED],
                "orders": [ORDER], "plan": {"date": "2026-10-14", "status": "done",
                                            "items": [PLAN]}, "log": []}
        empty = {"mode": "dry", "positions": [], "closed": [], "orders": [], "log": []}
        for lang in ("ru", "en"):
            X = tt.TX[lang]
            at = self.run_app(lang, full)
            self.assertEqual(len(at.exception), 0, [e.value for e in at.exception])
            subs = [s.value for s in at.subheader]
            self.assertIn(X["pos"], subs)
            md = [m.value for m in at.markdown]
            self.assertIn(f"**{X['bot_status']}**", md)                # status block rendered
            self.assertGreaterEqual(len(at.dataframe), 4)
            at = self.run_app(lang, empty)
            self.assertEqual(len(at.exception), 0, [e.value for e in at.exception])
            self.assertIn(X["pos_none"], [m.value for m in at.markdown])

    def test_performance_section_renders(self):
        """Trading Performance block: cards, strategy-P&L/R charts, comparison table."""
        closed = [CLOSED,
                  dict(CLOSED, ticker="AAA", mode="breakout", pnl=120.0, r=2.4,
                       entry_date="2026-08-03", exit_date="2026-08-17"),
                  dict(CLOSED, ticker="BBB", mode="breakout", pnl=-40.0, r=-1.0,
                       entry_date="2026-08-04", exit_date="2026-08-11")]
        state = {"mode": "dry", "positions": [POSITION, POSITION_CLOSE], "closed": closed,
                 "log": []}
        for lang in ("ru", "en"):
            P = tt.PERF[lang]
            at = self.run_app(lang, state)
            self.assertEqual(len(at.exception), 0, [e.value for e in at.exception])
            md = [m.value for m in at.markdown]
            self.assertIn(f"### {P['title']}", md)                      # performance header
            self.assertIn(f"**{P['cmp']}**", md)                       # comparison table title
            self.assertGreaterEqual(len(at.metric), 11)                # all metric cards
            labels = [m.label for m in at.metric]
            self.assertIn(P["win"], labels)
            self.assertIn(P["pf"], labels)
            self.assertIn(P["max_dd"], labels)                         # shown as "—"

    def test_strategy_switch_filters_without_error(self):
        closed = [dict(CLOSED, ticker="AAA", mode="breakout", pnl=50.0, r=1.0),
                  dict(CLOSED, ticker="CCC", mode="retest", pnl=10.0, r=0.5)]
        state = {"mode": "dry", "positions": [POSITION], "closed": closed, "log": []}
        for choice in ("BREAKOUT", "RETEST", "VCP", "ALL"):
            from streamlit.testing.v1 import AppTest
            at = AppTest.from_file("app.py", default_timeout=180)
            at.secrets["STATE_PASSWORD"] = "test"
            at.session_state["lang"] = "RU"
            at.session_state["bot_unlocked"] = True
            at.session_state["bot_state"] = state
            at.session_state["bot_sha"] = "abc"
            at.session_state["trade_perf_strategy"] = choice      # pre-set the switcher
            at.run()
            self.assertEqual(len(at.exception), 0,
                             (choice, [e.value for e in at.exception]))
            # comparison table is always present regardless of the filter
            self.assertIn(f"**{tt.PERF['ru']['cmp']}**", [m.value for m in at.markdown])

    def test_sparse_and_old_closed_records_do_not_crash_journal(self):
        """Records missing dry / mode / reason / dates / numeric values must not break
        the tab (old state/trader.enc entries)."""
        sparse = [
            {"ticker": "OLD1", "pnl": 12.0},                           # mode/r/dates/dry absent
            {"ticker": "OLD2", "mode": "breakout", "entry_date": "2026-09-01",
             "exit_date": "2026-09-15", "pnl": -8.0},                  # r/qty/dry/reason absent
            {"ticker": "OLD3", "mode": "vcp", "pnl": "oops", "r": None, "reason": None,
             "dry": True},                                             # non-numeric pnl, no dates
        ]
        state = {"mode": "dry", "positions": [POSITION], "closed": sparse, "log": []}
        for lang in ("ru", "en"):
            at = self.run_app(lang, state)
            self.assertEqual(len(at.exception), 0, [e.value for e in at.exception])

    def test_closed_records_missing_pnl_and_r_columns_do_not_crash(self):
        """All closed trades lack pnl AND r entirely: tab renders, summary shows '—'."""
        closed = [{"ticker": "X1", "mode": "breakout", "entry_date": "2026-09-01",
                   "exit_date": "2026-09-15", "qty": 1, "entry": 100.0, "exit": 110.0,
                   "reason": "time"},
                  {"ticker": "X2", "mode": "vcp", "entry_date": "2026-09-02",
                   "exit_date": "2026-09-09", "qty": 2, "entry": 80.0, "exit": 74.0,
                   "reason": "stop"}]
        state = {"mode": "dry", "positions": [POSITION], "closed": closed, "log": []}
        for lang in ("ru", "en"):
            at = self.run_app(lang, state)
            self.assertEqual(len(at.exception), 0, [e.value for e in at.exception])
            summary = [m.value for m in at.markdown
                       if m.value.startswith(("Сделок:", "Trades:"))]
            self.assertTrue(summary, "summary line not found")
            self.assertNotIn("nan", summary[0].lower())
            self.assertIn("—", summary[0])


@unittest.skipUnless(HAVE_ST or REQUIRE, "streamlit not installed")
class TestJournalHelpers(unittest.TestCase):
    """Row selection -> trade chart path, independent of the live dataframe widget."""

    def test_selected_rows_shapes(self):
        class _Sel:
            def __init__(self, rows): self.rows = rows
        class _Evt:
            def __init__(self, rows): self.selection = _Sel(rows)
        self.assertEqual(tt._selected_rows(_Evt([2])), [2])
        self.assertEqual(tt._selected_rows({"selection": {"rows": [0, 1]}}), [0, 1])
        self.assertEqual(tt._selected_rows(None), [])
        self.assertEqual(tt._selected_rows(_Evt([])), [])

    def test_trade_chart_online_and_offline(self):
        row = {"ticker": "AAPL", "entry_date": "2026-10-13", "exit_date": "2026-10-20",
               "entry": 230.5, "exit": 240.0}

        def prices_ok(tickers):
            idx = pd.bdate_range("2026-10-01", periods=20)
            return pd.concat({t: pd.DataFrame({"Close": np.linspace(220, 245, 20)}, index=idx)
                              for t in tickers}, axis=1)

        def prices_off(tickers):
            raise RuntimeError("offline")

        for lang in ("ru", "en"):
            tt._trade_chart(row, lang, prices_ok)          # should not raise
            tt._trade_chart(row, lang, prices_off)         # offline -> caption, no raise


if __name__ == "__main__":
    unittest.main()
