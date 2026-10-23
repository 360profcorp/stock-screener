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

    def test_schwab_return_with_a_foreign_state_is_rejected_and_url_cleaned(self):
        from streamlit.testing.v1 import AppTest
        for lang in ("ru", "en"):
            at = AppTest.from_file("app.py", default_timeout=180)
            at.secrets["STATE_PASSWORD"] = "test"
            at.secrets["SCHWAB_APP_KEY"] = "k"
            at.secrets["SCHWAB_APP_SECRET"] = "s"
            at.secrets["SCHWAB_CALLBACK_URL"] = "https://example.streamlit.app"
            at.session_state["lang"] = "EN" if lang == "en" else "RU"
            at.query_params["code"] = "SECRET-CODE"
            at.query_params["state"] = "forged"
            at.run()
            self.assertEqual(len(at.exception), 0, [e.value for e in at.exception])
            errs = " ".join(e.value for e in at.error)
            self.assertIn(tt.TX[lang]["renew_fail"].split("{")[0].strip(" ❌:"), errs)
            self.assertIn("unknown", errs)
            self.assertNotIn("SECRET-CODE", errs)
            self.assertNotIn("code", dict(at.query_params))
            self.assertEqual(at.session_state["sch_last_result"]["step"], "state")
            ok_txt = tt.TX[lang]["renew_ok"].split("{")[0].strip(" ✅")[:20]
            self.assertFalse(any(ok_txt in m.value for m in at.success))   # never "renewed"


if __name__ == "__main__":
    unittest.main()
