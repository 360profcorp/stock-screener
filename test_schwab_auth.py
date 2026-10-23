"""Weekly Schwab renewal: one-time state, callback handling, saving, expiry notices, monitor,
merges, and the bot's behaviour after expiry / reconnect. No network.
Run: python -m unittest test_schwab_auth -v
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import schwab_auth as A
import vault
from schwab_api import SchwabError

T = 1_800_000_000.0
TOKEN = {"access_token": "AT-secret", "refresh_token": "RT-secret", "access_expires": T + 1700,
         "refresh_created": T}


class R:
    def __init__(self, code, body):
        self.status_code, self._b, self.text = code, body, json.dumps(body)

    def json(self):
        return self._b


class Http:
    def __init__(self, *responses):
        self.r, self.calls = list(responses), []

    def post(self, url, **kw):
        self.calls.append((url, kw))
        return self.r.pop(0)


class States(unittest.TestCase):
    def test_one_time_states_bound_to_the_browser(self):
        p = A.PendingStates()
        a, b = "browser-A-secret", "browser-B-secret"
        s = p.issue(a, now=T)
        self.assertEqual(p.consume(s, b, now=T + 5), "other_browser")   # valid state, browser B
        self.assertEqual(p.consume(s, a, now=T + 6), "used")            # burnt by that attempt
        s = p.issue(a, now=T)
        self.assertEqual(p.consume(s, a, now=T + 5), "ok")
        self.assertEqual(p.consume(s, a, now=T + 6), "used")            # replay
        self.assertEqual(p.consume("forged", a, now=T), "unknown")
        self.assertEqual(p.consume("", a, now=T), "missing")
        s = p.issue(a, now=T)
        self.assertEqual(p.consume(s, "", now=T + 1), "other_browser")  # no cookie at all
        s = p.issue(a, now=T)
        self.assertEqual(p.consume(s, a, now=T + A.STATE_TTL + 1), "expired")
        dump = json.dumps(p._p)
        self.assertNotIn(s, dump)
        self.assertNotIn(a, dump)                                        # only hashes kept
        with self.assertRaises(ValueError):
            p.issue("", now=T)

    def test_consume_is_atomic(self):
        import threading
        p = A.PendingStates()
        s = p.issue("A", now=T)
        results, start = [], threading.Barrier(16)

        def go():
            start.wait()
            results.append(p.consume(s, "A", now=T + 1))
        th = [threading.Thread(target=go) for _ in range(16)]
        [t.start() for t in th]
        [t.join() for t in th]
        self.assertEqual(results.count("ok"), 1)
        self.assertEqual(results.count("used"), 15)

    def test_login_url(self):
        u = A.login_url("KEY", "https://app.example", "st123")
        self.assertIn("state=st123", u)
        self.assertIn("redirect_uri=https%3A%2F%2Fapp.example", u)


class Callback(unittest.TestCase):
    B = "browser-A"

    def setUp(self):
        self.p = A.PendingStates()
        self.state = self.p.issue(self.B, now=T)
        self.saved, self.exchanged = [], []

    def ex(self, code):
        self.exchanged.append(code)
        return dict(TOKEN, refresh_created=T + 10)

    def run_cb(self, params, ex=None, save=None, browser=None):
        return A.handle_callback(params, self.B if browser is None else browser, self.p,
                                 ex or self.ex, save or self.saved.append, now=T + 10)

    def test_success_only_after_save(self):
        r = self.run_cb({"code": "C1", "state": self.state})
        self.assertTrue(r["ok"])
        self.assertEqual(len(self.saved), 1)
        self.assertEqual(r["expires_at"], T + 10 + A.REFRESH_TTL)
        self.assertNotIn("RT-secret", json.dumps(r))

    def test_valid_state_from_another_browser_is_rejected(self):
        r = self.run_cb({"code": "C1", "state": self.state}, browser="browser-B")
        self.assertEqual((r["ok"], r["step"], r["state_check"]), (False, "state", "other_browser"))
        self.assertEqual(self.exchanged, [])
        r = self.run_cb({"code": "C1", "state": self.state})              # owner retries: burnt
        self.assertEqual(r["state_check"], "used")
        self.assertEqual(self.exchanged, [])

    def test_wrong_or_replayed_state_never_reaches_schwab(self):
        r = self.run_cb({"code": "C1", "state": "someone-else"})
        self.assertEqual((r["ok"], r["step"]), (False, "state"))
        self.assertTrue(self.run_cb({"code": "C1", "state": self.state})["ok"])
        r = self.run_cb({"code": "C2", "state": self.state})
        self.assertEqual(r["state_check"], "used")
        self.assertEqual(self.exchanged, ["C1"])

    def test_expired_code(self):
        def ex(code):
            raise SchwabError("the login code was rejected or expired (400 invalid_grant)")
        r = self.run_cb({"code": "C1", "state": self.state}, ex=ex)
        self.assertEqual((r["ok"], r["step"]), (False, "exchange"))
        self.assertEqual(self.saved, [])

    def test_save_failure_is_not_success(self):
        def bad(token):
            raise PermissionError("GH_TOKEN is not set")
        r = self.run_cb({"code": "C1", "state": self.state}, save=bad)
        self.assertEqual((r["ok"], r["step"]), (False, "save"))
        self.assertIn("NOT saved", r["reason"])

    def test_no_code_and_no_callback(self):
        self.assertIsNone(self.run_cb({})["ok"])
        r = self.run_cb({"state": self.state, "error": "access_denied"})
        self.assertFalse(r["ok"])
        self.assertEqual(self.p.consume(self.state, self.B, now=T + 20), "used")


class Exchange(unittest.TestCase):
    def test_success(self):
        h = Http(R(200, {"access_token": "a", "refresh_token": "r", "expires_in": 1800}))
        t = A.exchange("k", "s", "CODE@", "https://cb", h, now=T)
        self.assertEqual((t["refresh_token"], t["refresh_created"]), ("r", T))
        self.assertEqual(h.calls[0][1]["data"]["redirect_uri"], "https://cb")

    def test_expired_code_message_has_no_code(self):
        h = Http(R(400, {"error": "invalid_grant"}))
        with self.assertRaises(SchwabError) as e:
            A.exchange("k", "s", "SECRET-CODE", "https://cb", h, now=T)
        self.assertIn("expired", str(e.exception))
        self.assertNotIn("SECRET-CODE", str(e.exception))


class Classification(unittest.TestCase):
    def test_classify(self):
        cases = [(400, {"error": "invalid_grant"}, "token_refused"),
                 (400, {"error": "refresh_token_authentication_error"}, "token_refused"),
                 (401, {"error": "invalid_client"}, "client_or_token"),
                 (500, {}, "temporary"), (503, {"error": "x"}, "temporary"), (429, {}, "temporary"),
                 (400, {"error": "weird"}, "other")]
        for code, body, want in cases:
            self.assertEqual(A.classify(code, body), want, body)

    def test_no_check_calls_the_token_endpoint(self):
        import inspect
        with open("scripts/schwab_monitor.py") as f:
            src = (inspect.getsource(A) + f.read()).replace("'", '"')
        self.assertNotIn("check_refresh", src)
        self.assertNotIn('"grant_type": "refresh_token"', src)

    def test_exchange_errors_name_the_action(self):
        for resp, word in ((R(401, {"error": "invalid_client"}), "SCHWAB_APP_KEY"),
                           (R(500, {}), "temporarily"), (R(400, {"error": "invalid_grant"}),
                                                          "renew button")):
            with self.assertRaises(SchwabError) as e:
                A.exchange("k", "s", "SECRET-CODE", "https://cb", Http(resp), now=T)
            self.assertIn(word, str(e.exception))
            self.assertNotIn("SECRET-CODE", str(e.exception))


class Expiry(unittest.TestCase):
    def test_status(self):
        self.assertEqual(A.status(None)["state"], "none")
        self.assertEqual(A.status(TOKEN, T + 3600)["state"], "ok")
        self.assertEqual(A.status(TOKEN, T + A.REFRESH_TTL - 3600)["state"], "expiring")
        self.assertEqual(A.status(TOKEN, T + A.REFRESH_TTL)["state"], "expired")

    def deliver(self, sent, now, refresh=None):
        out = A.due_notices(TOKEN, sent, now, refresh)
        for n in out:
            A.mark_sent(TOKEN, sent, n)
        return out

    def test_notices_once_each(self):
        sent, end = {}, T + A.REFRESH_TTL
        self.assertEqual(self.deliver(sent, end - 30 * 3600), [])
        self.assertEqual(self.deliver(sent, end - 23 * 3600), ["24h"])
        self.assertEqual(self.deliver(sent, end - 20 * 3600), [])
        self.assertEqual(self.deliver(sent, end - 1.5 * 3600), ["2h"])
        self.assertEqual(self.deliver(sent, end - 1 * 3600), [])
        self.assertEqual(self.deliver(sent, end + 60), ["expired"])
        self.assertEqual(self.deliver(sent, end + 3600), [])

    def test_not_marked_until_delivered(self):
        sent = {}
        due = A.due_notices(TOKEN, sent, T + A.REFRESH_TTL - 3600)
        self.assertEqual(due, ["24h", "2h"])
        self.assertEqual(A.due_notices(TOKEN, sent, T + A.REFRESH_TTL - 3500), ["24h", "2h"])

    def test_missed_warnings_are_not_sent_after_expiry(self):
        sent = {}
        self.assertEqual(self.deliver(sent, T + A.REFRESH_TTL + 5), ["expired"])
        self.assertEqual(self.deliver(sent, T + A.REFRESH_TTL + 50), [])

    def test_refusal_notices_once_and_new_login_resets(self):
        sent = {}
        self.assertEqual(self.deliver(sent, T + 3600, "token_refused"), ["revoked"])
        self.assertEqual(self.deliver(sent, T + 7200, "token_refused"), [])
        self.assertEqual(self.deliver(sent, T + 7300, "client_or_token"), ["client"])
        self.assertEqual(self.deliver(sent, T + 7400, "temporary"), [])
        new = dict(TOKEN, refresh_created=T + 10000)
        due = A.due_notices(new, sent, T + 10000 + A.REFRESH_TTL - 3600)
        self.assertEqual(due, ["24h", "2h"])
        A.mark_sent(new, sent, "24h")
        self.assertEqual(list(sent), [str(int(T + 10000))])


class Monitor(unittest.TestCase):
    def load(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("mon", "scripts/schwab_monitor.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    def test_monitor_never_calls_schwab(self):
        m = self.load()
        with mock.patch("requests.post") as post, mock.patch("requests.request") as req:
            rep = m.run({"token": dict(TOKEN)}, lambda t, x: True, now=T + 3600)
        post.assert_not_called()
        req.assert_not_called()
        self.assertEqual(rep["sent"], [])

    def test_failed_delivery_is_retried(self):
        m = self.load()
        st = {"token": dict(TOKEN)}
        when = T + A.REFRESH_TTL - 20 * 3600                               # 24 h notice due

        class Ntfy:
            def __init__(self, mode):
                self.mode = mode

            def post(self, url, **kw):
                if self.mode == "timeout":
                    raise TimeoutError("read timeout")
                return R(500 if self.mode == "500" else 200, {})
        for mode in ("timeout", "500"):
            rep = m.run(st, lambda t, x, h=Ntfy(mode): A.send_ntfy("topic", t, x, h), now=when)
            self.assertEqual((rep["sent"], rep["failed"]), ([], ["24h"]), mode)
            self.assertNotIn("24h", st.get("schwab_notices", {}).get(A.login_key(TOKEN), []))
        ok = lambda t, x: A.send_ntfy("topic", t, x, Ntfy("ok"))           # noqa: E731
        self.assertEqual(m.run(st, ok, now=when + 1800)["sent"], ["24h"])
        self.assertEqual(m.run(st, ok, now=when + 3600)["sent"], [])

    def test_state_file_round_trip_is_what_actions_read(self):
        m = self.load()
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "trader.enc"
            vault.save_file(str(path), {"token": dict(TOKEN), "positions": []}, "pw")
            with mock.patch.object(vault, "STATE_PATH", str(path)), \
                    mock.patch.dict(os.environ, {"STATE_PASSWORD": "pw", "NTFY_TOPIC": ""}):
                before = path.read_bytes()
                m.main()                                    # nothing due, nothing delivered
                self.assertEqual(path.read_bytes(), before)
            st = vault.load_file(str(path), "pw")
            self.assertEqual(st["token"]["refresh_token"], "RT-secret")


class Merges(unittest.TestCase):
    def test_bot_save_keeps_monitor_and_app_changes(self):
        base = {"token": TOKEN, "positions": [], "schwab_notices": {}, "log": []}
        ours = dict(base, positions=[{"t": "X"}],
                    schwab_notices={str(int(T)): ["expired"]})
        new_tok = dict(TOKEN, refresh_created=T + 99)
        theirs = dict(base, token=new_tok, schwab_reconnected_at="2026-10-21 20:00:00",
                      schwab_notices={str(int(T)): ["24h"]},
                      schwab_auth={"login": str(int(T)), "blocked": "token_refused"})
        out = vault.merge_states(base, ours, theirs)
        self.assertEqual(out["token"], new_tok)
        self.assertEqual(out["schwab_reconnected_at"], "2026-10-21 20:00:00")
        self.assertEqual(out["schwab_notices"], {str(int(T)): ["24h", "expired"]})
        self.assertEqual(out["schwab_auth"]["blocked"], "token_refused")
        self.assertEqual(out["positions"], [{"t": "X"}])

    def test_token_rotation_by_the_bot_is_kept_and_a_new_login_wins(self):
        rotated = dict(TOKEN, refresh_token="RT-rotated")
        base = {"token": TOKEN, "positions": [], "log": []}
        out = vault.merge_states(base, dict(base, token=rotated), dict(base))
        self.assertEqual(out["token"]["refresh_token"], "RT-rotated")   # app did not touch it
        new_login = dict(TOKEN, refresh_token="RT-new-login", refresh_created=T + 500)
        out = vault.merge_states(base, dict(base, token=rotated), dict(base, token=new_login))
        self.assertEqual(out["token"]["refresh_token"], "RT-new-login")  # the newer login wins
        out = vault.merge_monitor(base, dict(base, schwab_notices={"1": ["24h"]}),
                                  dict(base, token=rotated))
        self.assertEqual(out["token"]["refresh_token"], "RT-rotated")   # monitor never writes it

    def test_monitor_save_never_touches_bot_fields(self):
        base = {"positions": [], "schwab_auth": None}
        ours = dict(base, schwab_auth={"login": "1", "blocked": "token_refused"})
        theirs = dict(base, positions=[{"t": "BOT"}], orders=[1])
        out = vault.merge_monitor(base, ours, theirs)
        self.assertEqual((out["positions"], out["orders"]), ([{"t": "BOT"}], [1]))
        self.assertEqual(out["schwab_auth"]["blocked"], "token_refused")


class FakeSchwab:
    """Stands in for schwab_api.Schwab: scripted _access() and orders()."""
    def __init__(self, err=None, rotate=False, orders=None, positions=None):
        self.err, self.rotate = err, rotate
        self._orders, self._pos = orders or [], positions or {}

    def __call__(self, key, secret, token, account):
        self.token = token
        return self

    def _access(self):
        if self.err:
            raise self.err
        if self.rotate:
            self.token["refresh_token"] = "RT-rotated"                 # same dict as the state
        return "AT"

    def orders(self, days=60):
        return self._orders

    def positions(self):
        return self._pos

    def last_fill(self, t, instr="BUY"):
        return None


def stop_order(sym, qty, px, status="WORKING", oid=7):
    return {"orderId": oid, "orderType": "STOP", "status": status, "quantity": qty,
            "filledQuantity": 0, "stopPrice": px, "duration": "GOOD_TILL_CANCEL",
            "orderLegCollection": [{"instruction": "SELL", "quantity": qty,
                                    "instrument": {"symbol": sym}}]}


class Bot(unittest.TestCase):
    def setUp(self):
        import time
        import trader
        self.trader = trader
        self.tok = dict(TOKEN, refresh_created=time.time() - 3600)
        self.p = mock.patch.multiple(trader, APP_KEY="k", APP_SECRET="s")
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_expired_blocks_without_cancelling_notice_recorded_after_delivery(self):
        import time
        st = {"token": dict(TOKEN, refresh_created=time.time() - A.REFRESH_TTL - 10)}
        with mock.patch.object(A, "send_ntfy", return_value=False) as sn, \
                mock.patch.object(self.trader, "Schwab") as S:
            self.assertIsNone(self.trader.schwab_or_none(st))
            self.assertIsNone(self.trader.schwab_or_none(st))
        self.assertEqual(sn.call_count, 2)                    # not delivered -> retried
        with mock.patch.object(A, "send_ntfy", return_value=True) as sn:
            self.trader.schwab_or_none(st)
            self.trader.schwab_or_none(st)
        self.assertEqual(sn.call_count, 1)
        S.assert_not_called()                                 # no broker: nothing cancelled

    def test_refusals_classified_from_the_bots_own_refresh(self):
        for status, body, blocked, word in (
                (400, {"error": "invalid_grant"}, "token_refused", "досрочно"),
                (401, {"error": "invalid_client"}, "client_or_token", "ключи")):
            st = {"token": dict(self.tok)}
            fake = FakeSchwab(err=SchwabError("x", status_code=status, body=body))
            with mock.patch.object(self.trader, "Schwab", fake), \
                    mock.patch.object(A, "send_ntfy", return_value=True) as sn:
                self.assertIsNone(self.trader.schwab_or_none(st))
            self.assertEqual(st["schwab_auth"]["blocked"], blocked)
            self.assertIn(word, sn.call_args[0][1])

    def test_temporary_failure_blocks_this_run_only(self):
        st = {"token": dict(self.tok)}
        fake = FakeSchwab(err=SchwabError("x", status_code=503, body={}))
        with mock.patch.object(self.trader, "Schwab", fake), \
                mock.patch.object(A, "send_ntfy") as sn:
            self.assertIsNone(self.trader.schwab_or_none(st))
        sn.assert_not_called()
        self.assertIsNone(st["schwab_auth"]["blocked"])

    def test_rotated_refresh_token_lands_in_the_state(self):
        st = {"token": dict(self.tok)}
        with mock.patch.object(self.trader, "Schwab", FakeSchwab(rotate=True)):
            self.assertIsNotNone(self.trader.schwab_or_none(st))
        self.assertEqual(st["token"]["refresh_token"], "RT-rotated")

    def pos(self, **kw):
        p = {"ticker": "BRK-B", "mode": "retest", "qty": 3, "stop": 400.0, "entry": 420.0,
             "entry_date": "2026-10-20", "dry": False}
        p.update(kw)
        return p

    def check(self, orders, positions, st=None):
        st = st or {"positions": [self.pos()], "orders": [], "closed": []}
        ev = []
        ok = self.trader.live_safety_check(st, FakeSchwab(orders=orders, positions=positions),
                                           "2026-10-23", ev)
        return ok, st, ev

    def test_safety_check_requires_a_working_stop_at_schwab(self):
        ok, st, ev = self.check([stop_order("BRK/B", 3, 400.0)], {"BRK-B": 3})
        self.assertTrue(ok)
        self.assertIsNone(st["live_block"])
        self.assertEqual(st["positions"][0]["protection"], "ok")
        for orders, why in (([], "missing"), ([stop_order("BRK/B", 2, 400.0)], "mismatch"),
                            ([stop_order("BRK/B", 3, 390.0)], "mismatch"),
                            ([stop_order("BRK/B", 3, 400.0, status="CANCELED")], "missing"),
                            ([stop_order("BRK/B", 3, 400.0, status="PENDING_CANCEL")], "missing")):
            ok, st, ev = self.check(orders, {"BRK-B": 3})
            self.assertFalse(ok, orders)
            self.assertEqual(st["positions"][0]["protection"], why)
            self.assertIn("заблокированы", " ".join(ev))

    def test_child_stop_of_a_trigger_order_counts(self):
        parent = {"orderId": 1, "orderType": "MARKET", "status": "FILLED",
                  "orderLegCollection": [{"instruction": "BUY", "instrument": {"symbol": "BRK/B"}}],
                  "childOrderStrategies": [stop_order("BRK/B", 3, 400.0)]}
        self.assertTrue(self.check([parent], {"BRK-B": 3})[0])

    def test_blocked_check_stops_new_entries_but_not_exits(self):
        st = {"positions": [], "orders": [], "closed": [], "live_block": {"reason": "x"},
              "plan": {"status": "new", "date": "2026-10-22", "created": "2026-10-22 20:00",
                       "for": "2026-10-23", "items": [{"ticker": "AAA", "mode": "retest",
                                                       "rs": 90, "close": 10, "stop": 9}]}}
        broker = mock.Mock(dry=False)
        ev = []
        from datetime import datetime
        import core
        self.trader.run_execute(st, broker, "2026-10-23", ev,
                                datetime(2026, 10, 23, 9, 0, tzinfo=core.NY))
        self.assertEqual(st["plan"]["status"], "blocked")
        broker.buy_with_stop.assert_not_called()
        broker.cancel.assert_not_called()

    def test_failed_check_blocks(self):
        class Down(FakeSchwab):
            def positions(self):
                raise SchwabError("down")
        st = {"positions": [], "orders": [], "closed": []}
        self.assertFalse(self.trader.live_safety_check(st, Down(), "2026-10-23", []))
        self.assertIn("не выполнена", st["live_block"]["reason"])

    def test_reconciled_marker_only_after_a_passing_check(self):
        st = {"positions": [self.pos()], "orders": [], "closed": [],
              "schwab_reconnected_at": "2026-10-23 10:00:00"}
        self.check([], {"BRK-B": 3}, st)
        self.assertIsNone(st.get("schwab_reconciled_at"))
        self.check([stop_order("BRK/B", 3, 400.0)], {"BRK-B": 3}, st)
        self.assertEqual(st["schwab_reconciled_at"], "2026-10-23 10:00:00")


class AppSave(unittest.TestCase):
    def test_save_token_retries_on_conflict_and_raises_on_failure(self):
        try:
            import trade_tab
        except Exception as e:                      # streamlit missing locally
            self.skipTest(f"streamlit: {e}")

        class Store:
            def __init__(self, fail_times, always=False):
                self.n, self.fail, self.always, self.saved = 0, fail_times, always, None

            def get(self):
                return {"positions": ["BOT"]}, f"sha{self.n}"

            def put(self, state, sha, msg):
                self.n += 1
                if self.always or self.n <= self.fail:
                    raise RuntimeError("state changed in the meantime")
                self.saved = state
                return "new"
        s = Store(1)
        out = trade_tab.save_token(s, dict(TOKEN))
        self.assertEqual(s.saved["token"]["refresh_token"], "RT-secret")
        self.assertEqual(s.saved["positions"], ["BOT"])                    # reloaded, kept
        self.assertIn("schwab_reconnected_at", out)
        with self.assertRaises(RuntimeError):
            trade_tab.save_token(Store(0, always=True), dict(TOKEN))


if __name__ == "__main__":
    unittest.main()
