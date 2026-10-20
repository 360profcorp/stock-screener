"""Audit regression tests: full paper-trade cycle, data gaps, reruns, restore, concurrency.

    python -m unittest test_audit_cycle -v

Everything runs on isolated synthetic data in temporary directories; the working state
(state/trader.enc, paper/state, paper/data) is never read or written.
"""
import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
os.environ.update(TRADING="dry", STATE_PASSWORD="audit-test-password", RISK_USD="15",
                  MAX_POSITION_USD="500", MAX_POSITIONS="5", MAX_NEW_PER_DAY="3",
                  HOLD_DAYS="20", TRADE_SETUPS="breakout,vcp,retest", NTFY_TOPIC="")
import core  # noqa: E402
import trader  # noqa: E402
import vault  # noqa: E402
import bot_status  # noqa: E402

trader = importlib.reload(trader)


class FakeBroker:
    """Dry broker on fixed daily bars; same semantics as trader.DryBroker."""
    dry = True

    def __init__(self, frames):
        self.frames = frames

    def bars(self, t, after, upto):
        df = self.frames.get(t)
        if df is None:
            return None
        d = df.index.normalize()
        return df[(d > pd.Timestamp(after)) & (d <= pd.Timestamp(upto))]

    def bar(self, t, day):
        b = self.bars(t, pd.Timestamp(day) - pd.Timedelta(days=1), day)
        return None if b is None or b.empty else b.iloc[-1]


def run_ex(st, fr, k, ev, hm=(9, 0)):
    """Morning run at hm (ET) on session k."""
    day = DAYS[k]
    now = datetime(day.year, day.month, day.day, hm[0], hm[1], tzinfo=core.NY)
    trader.run_execute(st, FakeBroker(fr), d(k), ev, now)


DAYS = pd.bdate_range("2026-10-19", periods=40, freq="C", holidays=trader.HOLIDAYS)


def frame(o=100., h=101., l=99., c=100., n=len(DAYS)):
    return pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c, "Volume": 1e6},
                        index=DAYS[:n]).astype(float)


def d(k):
    return DAYS[k].strftime("%Y-%m-%d")


def signals(day, rows):
    return pd.DataFrame([dict(date=day, ticker=t, mode=m, rs=rs, close=c, level=c * .98,
                              stop=s) for t, m, rs, c, s in rows])


def empty_state():
    st = vault.empty_state()
    st.update(orders=[], positions=[], closed=[], mode="dry")
    return st


class TestTradeCycle(unittest.TestCase):
    """signal -> plan -> order (morning) -> fill (evening) -> position -> exit -> journal."""

    def open_position(self, fr, stop=95.):
        st = empty_state()
        plan = trader.build_plan(signals(d(0), [("AAA", "retest", 92, 100., stop)]), st, d(0))
        self.assertEqual([i["ticker"] for i in plan["items"]], ["AAA"])
        self.assertEqual(plan["for"], d(1))                   # next session, never the same day
        st["plan"] = plan
        ev = []
        run_ex(st, fr, 1, ev)      # morning of d1: order only
        self.assertEqual(len(st["orders"]), 1)
        self.assertEqual(st["positions"], [])                 # nothing filled before the open
        trader.reconcile_dry(st, FakeBroker(fr), d(1), ev)    # evening of d1: fill at d1 open
        return st, ev

    def test_full_cycle_time_exit(self):
        fr = {"AAA": frame()}
        fr["AAA"].loc[DAYS[21], "Open"] = 104.
        st, _ = self.open_position(fr)
        p = st["positions"][0]
        self.assertEqual((p["entry"], p["qty"], p["entry_date"]), (100., 3, d(1)))  # 15/5
        for k in range(2, 21):
            run_ex(st, fr, k, [])
            trader.reconcile_dry(st, FakeBroker(fr), d(k), [])
        self.assertEqual(len(st["positions"]), 1)
        run_ex(st, fr, 21, [])     # 20 sessions held -> exit at open
        self.assertEqual(st["positions"][0]["exiting"], d(21))
        trader.reconcile_dry(st, FakeBroker(fr), d(21), [])
        self.assertEqual(st["positions"], [])
        rec = st["closed"][0]
        self.assertEqual((rec["reason"], rec["exit"], rec["exit_date"]), ("time", 104., d(21)))
        self.assertAlmostEqual(rec["pnl"], 12.)
        self.assertAlmostEqual(rec["r"], 0.8)

    def test_gap_below_stop_at_open_is_not_bought(self):
        fr = {"AAA": frame()}
        fr["AAA"].loc[DAYS[1], ["Open", "Low"]] = [94., 93.]
        st, ev = self.open_position(fr)
        self.assertEqual((st["positions"], st["closed"]), ([], []))
        self.assertTrue(any("ниже стопа" in e for e in ev))

    def test_stop_on_entry_day_fills_at_stop(self):
        fr = {"AAA": frame()}
        fr["AAA"].loc[DAYS[1], "Low"] = 90.
        st, _ = self.open_position(fr)
        self.assertEqual(st["positions"], [])
        self.assertEqual((st["closed"][0]["exit"], st["closed"][0]["reason"]), (95., "stop"))

    def test_gap_through_stop_later_fills_at_open(self):
        fr = {"AAA": frame()}
        fr["AAA"].loc[DAYS[3], ["Open", "Low"]] = [92., 91.]
        st, _ = self.open_position(fr)
        trader.reconcile_dry(st, FakeBroker(fr), d(4), [])
        rec = st["closed"][0]
        self.assertEqual((rec["exit"], rec["exit_date"], rec["reason"]), (92., d(3), "stop"))
        self.assertAlmostEqual(rec["r"], -1.6)

    def test_no_profit_target_exists(self):
        fr = {"AAA": frame()}
        fr["AAA"].loc[DAYS[2], ["High", "Close"]] = [200., 150.]   # +20R intraday
        st, _ = self.open_position(fr)
        trader.reconcile_dry(st, FakeBroker(fr), d(2), [])
        self.assertEqual(len(st["positions"]), 1)              # only stop / time exits

    def test_stop_before_the_exit_day_is_not_skipped(self):
        """Fixed: a stop hit between the last check and the time-exit day was ignored."""
        fr = {"AAA": frame()}
        fr["AAA"].loc[DAYS[20], "Low"] = 90.                   # stop on the last held day
        fr["AAA"].loc[DAYS[21], "Open"] = 104.
        st, _ = self.open_position(fr)
        run_ex(st, fr, 21, [])      # evening runs d2..d20 missed
        trader.reconcile_dry(st, FakeBroker(fr), d(21), [])
        rec = st["closed"][0]
        self.assertEqual((rec["reason"], rec["exit_date"], rec["exit"]), ("stop", d(20), 95.))

    def test_time_exit_without_quote_is_not_invented(self):
        """Fixed: a missing exit bar closed the trade at the entry price (invented P&L 0)."""
        fr = {"AAA": frame(n=21)}                              # no bar for the exit day d21
        st, _ = self.open_position(fr)
        run_ex(st, fr, 21, [])
        ev = []
        trader.reconcile_dry(st, FakeBroker(fr), d(21), ev)
        self.assertEqual(st["closed"], [])
        self.assertEqual(len(st["positions"]), 1)
        self.assertTrue(any("нет котировки" in e for e in ev))
        fr["AAA"] = frame()                                    # data arrives later
        fr["AAA"].loc[DAYS[21], "Open"] = 101.
        trader.reconcile_dry(st, FakeBroker(fr), d(22), [])
        self.assertEqual((st["closed"][0]["exit"], st["closed"][0]["exit_date"]), (101., d(21)))

    def test_order_waits_for_missing_open_bar_then_expires(self):
        """Fixed: an order whose open bar was not yet available was silently dropped."""
        fr = {"AAA": frame(n=1)}                                # no bar for d1 yet
        st, ev = self.open_position(fr)
        self.assertEqual(len(st["orders"]), 1)
        self.assertTrue(st["orders"][0]["waiting_data"])
        fr["AAA"] = frame()
        trader.reconcile_dry(st, FakeBroker(fr), d(2), [])
        self.assertEqual((len(st["orders"]), st["positions"][0]["entry_date"]), (0, d(1)))
        fr = {"AAA": frame(n=1)}
        st, _ = self.open_position(fr)
        trader.reconcile_dry(st, FakeBroker(fr), d(4), [])     # 3 sessions without data
        self.assertEqual((st["orders"], st["positions"]), ([], []))

    def test_stale_bars_do_not_advance_the_check(self):
        """Fixed: with no new bars the position was marked checked through today, so a stop
        on that day was never examined once the data arrived."""
        fr = {"AAA": frame(n=2)}
        st, _ = self.open_position(fr)
        trader.reconcile_dry(st, FakeBroker(fr), d(2), [])     # d2 bar not available
        self.assertEqual(st["positions"][0]["checked"], d(1))
        fr["AAA"] = frame()
        fr["AAA"].loc[DAYS[2], "Low"] = 90.
        trader.reconcile_dry(st, FakeBroker(fr), d(3), [])
        self.assertEqual(st["closed"][0]["exit_date"], d(2))

    def test_missing_latest_bar_is_reported(self):
        fr = {"AAA": frame(n=3)}                               # bars through d2 only
        st, _ = self.open_position(fr)
        ev = []
        gaps = trader.reconcile_dry(st, FakeBroker(fr), d(3), ev)  # evening of d3, no d3 bar
        self.assertEqual(gaps, ["AAA"])
        self.assertTrue(any("Нет котировок" in e and "AAA" in e for e in ev))
        self.assertEqual(st["positions"][0]["checked"], d(2))  # not marked as checked
        fr["AAA"] = frame()
        self.assertEqual(trader.reconcile_dry(st, FakeBroker(fr), d(3), []), [])
        st2 = empty_state()
        st2["runs"] = {"plan": {"at": f"{d(3)} 20:41", "result": "ok", "reason": "x",
                                "quote_gaps": ["AAA"]}}
        r = bot_status.no_trade_reasons(st2, "ru", d(3))
        self.assertTrue(any("нет котировок" in x and "AAA" in x for x in r))
        self.assertTrue(any("no quotes" in x for x in bot_status.no_trade_reasons(st2, "en", d(3))))

    def test_future_bars_are_never_used(self):
        fr = {"AAA": frame()}
        fr["AAA"].loc[DAYS[5], "Low"] = 80.                    # in the future at d2
        st, _ = self.open_position(fr)
        trader.reconcile_dry(st, FakeBroker(fr), d(2), [])
        self.assertEqual((len(st["positions"]), st["positions"][0]["checked"]), (1, d(2)))


class FakeIntraday(FakeBroker):
    def __init__(self, frames, minutes):
        super().__init__(frames)
        self.minutes = minutes                                 # {ticker: DataFrame} or {}

    def intraday(self, t, day):
        return self.minutes.get(t)


def minutes(day, lows):
    """Minute bars 09:30..15:59 of `day` at 100, with {"HH:MM": low} overrides."""
    idx = pd.date_range(f"{day} 09:30", f"{day} 15:59", freq="1min", tz=core.NY)
    df = pd.DataFrame({"Open": 100., "High": 100.5, "Low": 99.5, "Close": 100.}, index=idx)
    for hm, low in lows.items():
        df.loc[df.index.strftime("%H:%M") == hm, ["Open", "Low"]] = [low + .2, low]
    return df


class TestLateMorningRun(unittest.TestCase):
    """GitHub cron delays: the 09:15 ET paper run starts 35-90 min late."""

    def plan_state(self, created):
        st = empty_state()
        st["plan"] = trader.build_plan(signals(d(0), [("AAA", "retest", 92, 100., 95.),
                                                      ("BBB", "vcp", 90, 100., 95.)]), st, d(0))
        st["plan"]["created"] = created
        return st

    def test_delay_35_to_90_minutes_fills_at_that_sessions_open_once(self):
        for delay in (35, 50, 75, 90):
            hm = divmod(9 * 60 + 15 + delay, 60)
            fr = {"AAA": frame(), "BBB": frame()}
            fr["AAA"].loc[DAYS[1], "Open"] = 101.
            fr["AAA"].loc[DAYS[1], ["High", "Close"]] = [130., 125.]   # rally after the open
            st = self.plan_state(f"{d(0)} 20:38")                     # committed the evening before
            ev = []
            run_ex(st, fr, 1, ev, hm=hm)
            self.assertEqual(sorted(o["ticker"] for o in st["orders"]), ["AAA", "BBB"], delay)
            self.assertTrue(all(o["late_run"] and o["fill_session"] == d(1) for o in st["orders"]))
            run_ex(st, fr, 1, [], hm=(hm[0] + 1, hm[1]))               # second delayed cron
            self.assertEqual(len(st["orders"]), 2)                      # no duplicate buys
            trader.reconcile_dry(st, FakeBroker(fr), d(1), [])
            aaa = next(p for p in st["positions"] if p["ticker"] == "AAA")
            self.assertEqual((aaa["entry"], aaa["entry_date"]), (101., d(1)))  # the open, not later
            self.assertTrue(aaa["late_run"])

    def test_decision_after_the_open_gets_no_opening_price(self):
        fr = {"AAA": frame(), "BBB": frame()}
        st = self.plan_state(f"{d(1)} 09:45")                         # fixed after the open
        ev = []
        run_ex(st, fr, 1, ev, hm=(9, 50))
        self.assertEqual((st["orders"], st["plan"]["status"]), ([], "expired"))
        st = self.plan_state(f"{d(1)} 09:45")
        run_ex(st, fr, 1, [], hm=(9, 0))                              # if run before the open: ok
        self.assertEqual(len(st["orders"]), 2)

    def test_windows_per_mode(self):
        st = empty_state()
        at = lambda h, m: datetime(2026, 10, 15, h, m, tzinfo=core.NY)    # noqa: E731
        with tempfile.TemporaryDirectory() as tmp:
            trader.STATE_FILE = Path(tmp) / "s.enc"
            ok = lambda w, h, m: trader.check_day(at(h, m), dict(st), "last_execute", w,   # noqa
                                                  "pre-market", None)
            self.assertTrue(ok(trader.DRY_EXECUTE_WINDOW, 10, 45))
            self.assertFalse(ok(trader.DRY_EXECUTE_WINDOW, 16, 30))
            self.assertFalse(ok(trader.LIVE_EXECUTE_WINDOW, 9, 50))   # real orders unchanged
            self.assertTrue(ok(trader.LIVE_EXECUTE_WINDOW, 9, 15))
        trader.STATE_FILE = trader.ROOT / vault.STATE_PATH

    def test_cmd_execute_twice_late_does_not_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            trader.STATE_FILE = Path(tmp) / "s.enc"
            st = self.plan_state(f"{d(0)} 20:38")
            vault.save_file(trader.STATE_FILE, st, os.environ["STATE_PASSWORD"])
            orig = trader.now_ny
            try:
                for h, m in ((9, 50), (10, 41)):
                    day = DAYS[1]
                    trader.now_ny = lambda h=h, m=m, day=day: datetime(          # noqa: E731
                        day.year, day.month, day.day, h, m, tzinfo=core.NY)
                    trader.cmd_execute()
            finally:
                trader.now_ny = orig
            saved = vault.load_file(trader.STATE_FILE, os.environ["STATE_PASSWORD"])
            self.assertEqual(sorted(o["ticker"] for o in saved["orders"]), ["AAA", "BBB"])
            self.assertEqual(saved["last_execute"], d(1))
            self.assertTrue(saved["runs"]["execute"]["late"])
        trader.STATE_FILE = trader.ROOT / vault.STATE_PATH


class TestSessionBoundFill(unittest.TestCase):
    def test_missing_session_bar_never_moves_the_purchase(self):
        fr = {"AAA": frame().drop(DAYS[1])}                           # d1 missing, d2.. exist
        st = empty_state()
        st["plan"] = trader.build_plan(signals(d(0), [("AAA", "retest", 92, 100., 95.)]), st, d(0))
        run_ex(st, fr, 1, [])
        for k in (1, 2, 3):
            trader.reconcile_dry(st, FakeBroker(fr), d(k), [])
            self.assertEqual(st["positions"], [])                     # never filled at d2/d3
        trader.reconcile_dry(st, FakeBroker(fr), d(4), [])
        self.assertEqual((st["orders"], st["positions"], st["closed"]), ([], [], []))


class TestEntryDayStop(unittest.TestCase):
    """Breakouts bought ~15:30: the entry day's daily low may be BEFORE the purchase."""

    def bought(self, entry_time="15:30"):
        st = empty_state()
        st["positions"] = [{"ticker": "AAA", "mode": "breakout", "entry_date": d(1),
                            "entry": 100., "stop": 95., "qty": 3, "dry": True,
                            "checked": d(1), "how": "close", "entry_time": entry_time}]
        fr = {"AAA": frame()}
        fr["AAA"].loc[DAYS[1], "Low"] = 90.                           # daily low below the stop
        return st, fr

    def test_low_before_the_purchase_is_not_a_stop(self):
        st, fr = self.bought()
        b = FakeIntraday(fr, {"AAA": minutes(d(1), {"10:05": 90.})})
        trader.reconcile_dry(st, b, d(1), [])
        self.assertEqual((len(st["positions"]), st["positions"][0]["entry_day_stop"]),
                         (1, "intraday_ok"))

    def test_low_after_the_purchase_is_a_stop(self):
        st, fr = self.bought()
        b = FakeIntraday(fr, {"AAA": minutes(d(1), {"15:47": 94.})})
        trader.reconcile_dry(st, b, d(1), [])
        rec = st["closed"][0]
        self.assertEqual((rec["reason"], rec["exit_date"], rec["exit"]), ("stop", d(1), 94.2))
        self.assertEqual(rec["entry_day_stop"], "intraday_hit")

    def test_without_minute_data_the_limitation_is_recorded(self):
        st, fr = self.bought()
        trader.reconcile_dry(st, FakeIntraday(fr, {}), d(1), [])
        self.assertEqual((len(st["positions"]), st["positions"][0]["entry_day_stop"]),
                         (1, "unverified"))
        st, fr = self.bought(entry_time=None)                         # old position: time unknown
        trader.reconcile_dry(st, FakeIntraday(fr, {"AAA": minutes(d(1), {})}), d(1), [])
        self.assertEqual(st["positions"][0]["entry_day_stop"], "unverified")


class TestRerunAndGuards(unittest.TestCase):
    def test_same_day_reruns_do_not_duplicate(self):
        fr = {"AAA": frame(), "BBB": frame()}
        st = empty_state()
        st["plan"] = trader.build_plan(signals(d(0), [("AAA", "retest", 92, 100., 95.),
                                                      ("BBB", "vcp", 90, 100., 95.)]), st, d(0))
        for _ in range(3):                                     # FORCE reruns of the morning
            run_ex(st, fr, 1, [])
        self.assertEqual(sorted(o["ticker"] for o in st["orders"]), ["AAA", "BBB"])
        for _ in range(3):                                     # evening reruns
            trader.reconcile_dry(st, FakeBroker(fr), d(1), [])
        self.assertEqual(sorted(p["ticker"] for p in st["positions"]), ["AAA", "BBB"])
        self.assertEqual(st["closed"], [])
        plan2 = trader.build_plan(signals(d(0), [("AAA", "retest", 92, 100., 95.)]), st, d(0))
        self.assertEqual(plan2["items"], [])                   # held tickers are not re-planned
        self.assertEqual(plan2["already_held"], 1)

    def test_skipped_window_is_recorded_without_overwriting_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            trader.STATE_FILE = Path(tmp) / "s.enc"
            st = empty_state()
            late = datetime(2026, 10, 15, 9, 50, tzinfo=core.NY)
            self.assertFalse(trader.check_day(late, st, "last_execute", ((8, 0), (9, 29)),
                                              "pre-market", "execute"))
            saved = vault.load_file(trader.STATE_FILE, os.environ["STATE_PASSWORD"])
            self.assertEqual(saved["runs"]["execute"]["result"], "skipped")
            self.assertIn("09:50", saved["runs"]["execute"]["reason"])
            st2 = empty_state()
            st2["last_execute"] = "2026-10-15"                 # ran on time today
            trader.STATE_FILE = Path(tmp) / "s2.enc"
            trader.check_day(late, st2, "last_execute", ((8, 0), (9, 29)), "pre-market",
                             "execute")
            self.assertFalse(trader.STATE_FILE.exists())       # benign skip: nothing written
        trader.STATE_FILE = trader.ROOT / vault.STATE_PATH


class TestStatus(unittest.TestCase):
    def test_missed_morning_plan_is_reported_with_its_reason(self):
        st = empty_state()
        st["plan"] = {"kind": "open", "date": "2026-10-14", "for": "2026-10-15", "items":
                      [{"ticker": "MRK"}], "status": "new", "skipped_full": 2,
                      "signals": 4, "already_held": 0, "too_small": 0}
        st["runs"] = {"execute": {"at": "2026-10-15 09:50", "result": "skipped",
                                  "reason": "запуск в 09:50 ET вне окна 8:00–9:29"}}
        r = bot_status.no_trade_reasons(st, "ru", "2026-10-15", after_open=True)
        self.assertTrue(any("не исполнен" in x and "09:50" in x for x in r), r)
        self.assertTrue(any("лимит позиций" in x for x in r))
        self.assertEqual(bot_status.no_trade_reasons(st, "ru", "2026-10-15"), r[1:])
        en = bot_status.no_trade_reasons(st, "en", "2026-10-15", after_open=True)
        self.assertTrue(any("not executed" in x for x in en))

    def test_success_without_trades_differs_from_failure(self):
        ok = empty_state()
        ok["plan"] = {"date": "2026-10-14", "for": "2026-10-15", "items": [], "status": "new",
                      "signals": 0, "skipped_full": 0}
        ok["runs"] = {"plan": {"at": "2026-10-14 20:38", "result": "ok", "reason": ""}}
        r = bot_status.no_trade_reasons(ok, "ru", "2026-10-14")
        self.assertEqual(r, ["нет сигналов за 2026-10-14"])
        bad = empty_state()
        bad["runs"] = {"plan": {"at": "2026-10-14 20:38", "result": "error",
                                "reason": "HTTPError: 429"}}
        r = bot_status.no_trade_reasons(bad, "ru", "2026-10-14")
        self.assertTrue(r and "ошибка" in r[0] and "429" in r[0])
        s = bot_status.bot_status(empty_state(), "ru", "2026-10-14")
        self.assertTrue(all("нет записей" in b for _, b in s["runs"]))  # never guessed


class TestConcurrency(unittest.TestCase):
    def test_merge_keeps_app_login_and_approval(self):
        base = {**vault.empty_state(), "plan": {"date": "D", "status": "new", "approved": False},
                "positions": [], "log": [{"t": "1", "msg": "a"}]}
        ours = json.loads(json.dumps(base))
        ours["positions"] = [{"ticker": "AAA"}]
        ours["log"].append({"t": "3", "msg": "bot"})
        theirs = json.loads(json.dumps(base))
        theirs["token"] = {"refresh": "x"}
        theirs["plan"]["approved"] = True
        theirs["log"].append({"t": "2", "msg": "schwab connected"})
        m = vault.merge_states(base, ours, theirs)
        self.assertEqual(m["token"], {"refresh": "x"})
        self.assertTrue(m["plan"]["approved"])
        self.assertEqual(m["positions"], [{"ticker": "AAA"}])
        self.assertEqual([r["msg"] for r in m["log"]], ["a", "schwab connected", "bot"])
        theirs2 = json.loads(json.dumps(base))
        theirs2["positions"] = [{"ticker": "ZZZ"}]                  # bot field changed: refuse
        with self.assertRaises(vault.StateConflict):
            vault.merge_states(base, ours, theirs2)

    def test_save_script_merges_a_concurrent_app_commit(self):
        pw = os.environ["STATE_PASSWORD"]
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)

            def git(cwd, *a):
                return subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True,
                                      text=True).stdout
            git(tmp, "init", "-q", "--bare", "-b", "main", "remote.git")
            git(tmp, "clone", "-q", str(tmp / "remote.git"), "seed")
            seed = tmp / "seed"
            for r in (seed,):
                git(r, "config", "user.email", "t@t"); git(r, "config", "user.name", "t")
            base = {**vault.empty_state(), "positions": [], "plan": None}
            vault.save_file(str(seed / vault.STATE_PATH), base, pw)
            (seed / "other.txt").write_text("v1")
            git(seed, "add", "."); git(seed, "commit", "-qm", "init"); git(seed, "push", "-q",
                                                                           "origin", "main")
            git(tmp, "clone", "-q", str(tmp / "remote.git"), "bot")
            bot = tmp / "bot"
            git(bot, "config", "user.email", "b@b"); git(bot, "config", "user.name", "b")
            base_copy = tmp / "base.enc"
            base_copy.write_bytes((bot / vault.STATE_PATH).read_bytes())
            # the app saves a Schwab login and someone else changes another file meanwhile
            app = {**base, "token": {"refresh": "new"}}
            vault.save_file(str(seed / vault.STATE_PATH), app, pw)
            (seed / "other.txt").write_text("v2")
            git(seed, "commit", "-qam", "app"); git(seed, "push", "-q", "origin", "main")
            # the bot's run result
            vault.save_file(str(bot / vault.STATE_PATH),
                            {**base, "positions": [{"ticker": "AAA"}]}, pw)
            r = subprocess.run([sys.executable, str(ROOT / "scripts/save_trader_state.py"),
                                str(base_copy), "Bot state"], cwd=bot, capture_output=True,
                               text=True, env={**os.environ})
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            git(seed, "pull", "-q")
            final = vault.load_file(str(seed / vault.STATE_PATH), pw)
            self.assertEqual(final["token"], {"refresh": "new"})          # app's login kept
            self.assertEqual(final["positions"], [{"ticker": "AAA"}])      # bot's trade kept
            self.assertEqual((seed / "other.txt").read_text(), "v2")       # nothing reverted


class TestPaperPortfolio(unittest.TestCase):
    """paper_run.py (Retest RS-first forward paper portfolio), isolated temp dirs."""

    def test_full_cycle_accounting_identity(self):
        import test_paper as TP
        runs = [(k, "evening") for k in range(0, 9)]
        summ, st = TP.run_scenario(runs, {0: ["AAA", "BBB"], 1: ["CCC"]}, low_on={"BBB": 2})
        led = pd.DataFrame(st["ledger"])
        self.assertIn("BBB", set(led["ticker"]))               # stopped out
        self.assertEqual(led.loc[led["ticker"] == "BBB", "reason"].iloc[0], "stop")
        init = st["config"]["initial_cash"]
        unreal = sum(p["qty"] * st["last_prices"][t] - p["entry_cost"]
                     for t, p in st["positions"].items())
        eq = st["equity"][-1]["equity"]
        self.assertAlmostEqual(init + led["net_pnl"].sum() + unreal, eq, places=6)
        self.assertAlmostEqual(eq, st["cash"] + sum(p["qty"] * st["last_prices"][t]
                                                    for t, p in st["positions"].items()))
        log = pd.DataFrame(st["orders_log"])
        self.assertTrue((log["outcome"] == "entered").sum() >= 2)

    def test_unrealized_matches_equity_with_fees(self):
        from paper.config import PaperConfig
        from paper.portfolio import PaperPortfolio
        port = PaperPortfolio(cfg=PaperConfig(cost_bps=10.))
        port.queue_signals("2026-10-14", pd.DataFrame([dict(ticker="AAA", rs=90., rank=1,
                                                            stop=95., eligible=True)]))
        port.step("2026-10-15", {"AAA": {"O": 100., "H": 103., "L": 99., "C": 102.}})
        s, p = port.s, port.s["positions"]["AAA"]
        unreal = p["qty"] * s["last_prices"]["AAA"] - p["entry_cost"]       # paper_tab model
        self.assertAlmostEqual(s["config"]["initial_cash"] + unreal, port.equity_now())
        old_ui = (s["last_prices"]["AAA"] - p["entry"]) * p["qty"]          # before the fix
        self.assertNotAlmostEqual(s["config"]["initial_cash"] + old_ui, port.equity_now())

    def test_stale_download_for_held_position_stops_the_run(self):
        import paper_run
        import test_paper as TP
        from paper import store
        prices = TP._scenario_prices()
        uni = pd.DataFrame({"ticker": ["AAA", "BBB", "CCC"], "name": "", "sector": "X"})
        with tempfile.TemporaryDirectory() as tmp:
            def at(k):
                day = TP.SC_DAYS[k]
                return datetime(day.year, day.month, day.day, 18, 0, tzinfo=core.NY)
            kw = dict(universe=uni, root=Path(tmp), cfg=TP.SC_CFG, scan_fn=TP._scan_fn({0: ["AAA"]}))
            paper_run.daily(prices=prices[prices.index <= TP.SC_DAYS[0]], now=at(0), **kw)
            paper_run.daily(prices=prices[prices.index <= TP.SC_DAYS[1]], now=at(1), **kw)
            f = store.paths("forward", Path(tmp))["state_file"]
            before = f.read_text()
            self.assertIn("AAA", json.loads(before)["positions"])
            stale = prices[prices.index <= TP.SC_DAYS[2]].copy()
            stale.loc[TP.SC_DAYS[2], ("AAA", slice(None))] = np.nan   # AAA download stale
            with self.assertRaises(paper_run.DataError) as e:
                paper_run.daily(prices=stale, now=at(2), **kw)
            self.assertIn("AAA", str(e.exception))
            self.assertEqual(f.read_text(), before)                   # nothing saved
            s = paper_run.daily(prices=prices[prices.index <= TP.SC_DAYS[2]], now=at(2), **kw)
            self.assertEqual(s["processed_through"], str(TP.SC_DAYS[2].date()))

    def test_paper_status_flags_behind_and_waiting(self):
        st = {"processed_through": "2026-10-14", "pending": [
            {"ticker": "HUM", "signal_date": "2026-10-14", "scheduled_for": "2026-10-15"}],
              "positions": {}, "orders_log": [], "config": {"max_positions": 5}}
        now = datetime(2026, 10, 15, 18, 0, tzinfo=core.NY)
        s = bot_status.paper_status(st, {"updated": "x", "sessions": []}, "ru", now)
        self.assertEqual(s["flag"], "behind")
        self.assertTrue(any("2026-10-15" in x and "отстают" in x for x in s["lines"]))
        now = datetime(2026, 10, 15, 12, 0, tzinfo=core.NY)
        s = bot_status.paper_status(st, {"updated": "x", "sessions": []}, "en", now)
        self.assertEqual(s["flag"], "ok")
        self.assertTrue(any("Waiting for fills: 1" in x for x in s["lines"]))


if __name__ == "__main__":
    unittest.main()
