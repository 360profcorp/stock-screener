"""Pilot engine tests on scripted (fake) Schwab responses. No network, no real orders.
Run: python -m unittest test_pilot -v
"""
import copy
import itertools
import unittest
from datetime import datetime, timedelta, timezone

from pilot import engine as EN
from pilot.broker import (BrokerUnavailable, OrderRejected, ReadOnlyHTTP, ReadOnlyViolation,
                          SendUnknown, norm_order)

T0 = datetime(2026, 10, 22, 14, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self):
        self.t = T0

    def __call__(self):
        return self.t

    def adv(self, minutes):
        self.t += timedelta(minutes=minutes)


class FakeBroker:
    """Broker state machine. place_script: list of behaviours consumed per place() call:
    'ok' | 'timeout_created' | 'timeout_lost' | 'reject' | 'stop_reject' | 'unavailable'."""
    def __init__(self, clock, positions=None, cash=500.0, quote=50.0):
        self.clock, self.ids = clock, itertools.count(1000)
        self.positions = dict(positions or {})          # ticker -> qty
        self.orders = {}                                 # id -> normalised order
        self.cash, self.q = cash, quote
        self.script, self.fill_qty = [], None            # fill_qty: partial fill on next buy
        self.sent, self.cancels, self.down = [], [], False

    # ---- helpers
    def _new(self, order, status):
        oid = str(next(self.ids))
        leg = order["orderLegCollection"][0]
        o = dict(id=oid, parent=None, status=status, symbol=leg["instrument"]["symbol"],
                 instruction=leg["instruction"], type=order["orderType"],
                 duration=order["duration"], qty=float(leg["quantity"]), filled=0.0,
                 remaining=float(leg["quantity"]), stop_price=order.get("stopPrice"),
                 entered=self.clock().isoformat(), closed=None, avg_price=None, legs=1,
                 strategy="SINGLE")
        self.orders[oid] = o
        return o

    def fill(self, oid, qty, px):
        o = self.orders[oid]
        o["filled"] += qty
        o["remaining"] -= qty
        o["avg_price"] = px
        sgn = 1 if o["instruction"] == "BUY" else -1
        self.positions[o["symbol"]] = self.positions.get(o["symbol"], 0) + sgn * qty
        if not self.positions[o["symbol"]]:
            del self.positions[o["symbol"]]
        o["status"] = "FILLED" if o["remaining"] <= 0 else "WORKING"

    # ---- broker API
    def snapshot(self):
        if self.down:
            raise BrokerUnavailable("Schwab login expired (7 days)")
        return dict(account_number="99991234", type="CASH",
                    positions={t: dict(qty=q, asset="EQUITY", avg=None)
                               for t, q in self.positions.items()},
                    orders=[copy.deepcopy(o) for o in self.orders.values()],
                    balances=dict(cash=self.cash, cash_available=self.cash, buying_power=self.cash,
                                  liquidation_value=self.cash), flags={})

    def get_order(self, oid):
        return copy.deepcopy(self.orders[str(oid)])

    def quote(self, t):
        if self.down:
            raise BrokerUnavailable("expired")
        return self.q

    def place(self, order):
        b = self.script.pop(0) if self.script else "ok"
        self.sent.append((b, copy.deepcopy(order)))
        if b == "unavailable":
            raise BrokerUnavailable("login expired")
        if b == "reject" or (b == "stop_reject" and order["orderType"] == "STOP"):
            raise OrderRejected("400: rejected")
        if b == "timeout_lost":
            raise SendUnknown("ReadTimeout after sending")
        o = self._new(order, "WORKING" if order["orderType"] == "STOP" else "QUEUED")
        if order["orderType"] == "MARKET":
            q = self.fill_qty if (self.fill_qty and o["instruction"] == "BUY") else o["qty"]
            self.fill_qty = None
            self.fill(o["id"], q, self.q)
        if b == "timeout_created":
            raise SendUnknown("ReadTimeout after sending")
        return o["id"]

    def cancel(self, oid):
        self.cancels.append(str(oid))
        o = self.orders[str(oid)]
        if o["status"] in ("FILLED", "CANCELED"):
            raise OrderRejected("400: not cancelable")
        o["status"] = "CANCELED"

    # ---- test helpers
    def live_stops(self, t):
        return [o for o in self.orders.values() if o["symbol"] == t and o["type"] == "STOP"
                and o["status"] == "WORKING"]

    def buys(self):
        return [o for b, o in self.sent if o["orderLegCollection"][0]["instruction"] == "BUY"
                and b != "reject"]


def approval(**kw):
    a = dict(approval_id="A1", ticker="XYZ", side="BUY", asset="EQUITY", qty=1,
             max_price=60.0, stop_price=45.0, expires_at=(T0 + timedelta(hours=2)).isoformat(),
             account_last4="1234")
    a.update(kw)
    return a


class Base(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.b = FakeBroker(self.clock)
        self.saves = []
        self.p = self.make()

    def make(self, **kw):
        args = dict(live=True, entries_enabled=True, account_suffix="1234", now=self.clock,
                    save=lambda s: self.saves.append(s))
        args.update(kw)
        return EN.Pilot(self.b, kw.pop("state", None), **{k: v for k, v in args.items()
                                                            if k != "state"})


class HappyPath(Base):
    def test_buy_fill_stop_then_close(self):
        r = self.p.cycle(approval())
        self.assertTrue(r["entry"]["sent"])
        self.p.cycle()                                          # fill -> stop
        pos = self.p.s["positions"][0]
        self.assertEqual((pos["qty"], pos["entry"]), (1, 50.0))
        st = self.b.live_stops("XYZ")
        self.assertEqual(len(st), 1)
        self.assertEqual((st[0]["qty"], st[0]["stop_price"], st[0]["duration"]),
                         (1.0, 45.0, "GOOD_TILL_CANCEL"))
        self.assertTrue(pos["protected"])
        self.assertIsNone(self.p.s["blocked"])
        for _ in range(3):                                       # re-runs change nothing
            self.p.cycle()
        self.assertEqual(len(self.b.buys()), 1)
        self.assertEqual(len([o for _, o in self.b.sent if o["orderType"] == "STOP"]), 1)
        self.p.request_exit("XYZ")
        self.b.q = 55.0
        self.p.cycle()
        self.assertEqual(self.b.orders[st[0]["id"]]["status"], "CANCELED")
        self.assertEqual(self.p.s["positions"], [])
        c = self.p.s["closed"][0]
        self.assertEqual((c["exit_reason"], c["exit"], c["pnl"]), ("owner", 55.0, 5.0))
        self.assertNotIn("XYZ", self.b.positions)

    def test_intent_saved_before_the_order_leaves(self):
        seen = []
        orig = self.b.place

        def place(order):
            seen.append(copy.deepcopy(self.saves[-1]["intents"]))
            return orig(order)
        self.b.place = place
        self.p.cycle(approval())
        self.assertEqual(seen[0][-1]["status"], "submitting")
        self.assertEqual(seen[0][-1]["side"], "BUY")


class Guards(Base):
    def test_live_off_and_entries_off_send_nothing(self):
        for p in (self.make(live=False), self.make(entries_enabled=False)):
            r = p.cycle(approval())
            self.assertFalse(r["entry"]["sent"])
        self.assertEqual(self.b.sent, [])

    def test_duplicate_run_same_approval(self):
        self.p.cycle(approval())
        self.p.cycle()
        r = self.p.cycle(approval())
        self.assertFalse(r["entry"]["sent"])
        self.assertTrue(any("approval already used" in w for w in r["entry"]["why"]))
        self.assertEqual(len(self.b.buys()), 1)

    def test_budget_first_trade_and_one_position(self):
        r = self.p.cycle(approval(qty=2))                     # 2 x 50 x 1.02 > $100
        self.assertFalse(r["entry"]["sent"])
        self.assertTrue(any("first trade" in w for w in r["entry"]["why"]))
        self.p.cycle(approval(approval_id="A2"))
        self.p.cycle()
        r = self.p.cycle(approval(approval_id="A3", ticker="ABC"))
        self.assertFalse(r["entry"]["sent"])
        self.assertTrue(any("max 1 pilot position" in w for w in r["entry"]["why"]))

    def test_total_budget_cap(self):
        p = self.make()
        p.s["closed"].append(dict(ticker="OLD"))              # not the first trade any more
        self.b.cash = 5000
        r = p.cycle(approval(qty=20, max_price=60))           # 20 x 50 x 1.02 = 1020
        self.assertFalse(r["entry"]["sent"])
        self.assertTrue(any("budget" in w for w in r["entry"]["why"]))

    def test_quote_above_approved_price_and_expired_approval(self):
        self.b.q = 61.0
        self.assertFalse(self.p.cycle(approval())["entry"]["sent"])
        self.clock.adv(180)
        self.b.q = 50.0
        r = self.p.cycle(approval(approval_id="A9"))
        self.assertTrue(any("expired" in w for w in r["entry"]["why"]))
        self.assertEqual(self.b.sent, [])

    def test_manual_position_or_order_in_the_same_ticker(self):
        self.b.positions["XYZ"] = 10                           # owner's own shares
        r = self.p.cycle(approval())
        self.assertFalse(r["entry"]["sent"])
        self.assertTrue(any("manual" in w for w in r["entry"]["why"]))
        del self.b.positions["XYZ"]
        self.b._new({"orderType": "LIMIT", "duration": "DAY", "orderLegCollection": [
            {"instruction": "BUY", "quantity": 5, "instrument": {"symbol": "XYZ"}}]}, "WORKING")
        r = self.p.cycle(approval(approval_id="A2"))
        self.assertTrue(any("not from the pilot" in w for w in r["entry"]["why"]))
        self.assertEqual(self.b.sent, [])

    def test_manual_orders_and_shares_never_touched_on_exit(self):
        self.p.cycle(approval())
        self.p.cycle()
        manual = self.b._new({"orderType": "STOP", "duration": "GOOD_TILL_CANCEL", "stopPrice": 40,
                              "orderLegCollection": [{"instruction": "SELL", "quantity": 7,
                                                      "instrument": {"symbol": "XYZ"}}]}, "WORKING")
        self.b.positions["XYZ"] += 7                            # owner bought 7 more later
        self.p.cycle()
        self.p.request_exit("XYZ")
        self.p.cycle()
        sells = [o for _, o in self.b.sent if o["orderType"] == "MARKET"
                 and o["orderLegCollection"][0]["instruction"] == "SELL"]
        self.assertEqual([o["orderLegCollection"][0]["quantity"] for o in sells], [1])
        self.assertNotIn(manual["id"], self.b.cancels)
        self.assertEqual(self.b.orders[manual["id"]]["status"], "WORKING")
        self.assertEqual(self.b.positions["XYZ"], 7)

    def test_expired_token_sends_nothing(self):
        self.b.down = True
        r = self.p.cycle(approval())
        self.assertIn("unavailable", r["broker"])
        self.assertEqual(self.b.sent, [])
        self.assertTrue(self.p.s["alerts"])

    def test_account_mismatch_blocks(self):
        p = self.make(account_suffix="0000")
        p.cycle(approval())
        self.assertTrue(p.s["blocked"])
        self.assertEqual(self.b.sent, [])


class UnknownResults(Base):
    def test_timeout_but_order_exists_is_matched_never_resent(self):
        self.b.script = ["timeout_created"]
        r = self.p.cycle(approval())
        self.assertEqual(r["entry"]["status"], "unknown")
        self.assertTrue(self.p.s["blocked"])
        self.clock.adv(1)
        self.p.cycle()
        self.assertEqual(len(self.b.buys()), 1)
        self.p.cycle()
        self.assertEqual(self.p.s["positions"][0]["qty"], 1)
        self.assertEqual(len(self.b.live_stops("XYZ")), 1)

    def test_timeout_and_order_lost_stays_blocked(self):
        self.b.script = ["timeout_lost"]
        self.p.cycle(approval())
        self.clock.adv(EN.UNKNOWN_WINDOW_MIN + 1)
        self.p.cycle()
        self.assertEqual(self.p.s["intents"][0]["status"], "not_found")
        self.assertIn("never re-sent", self.p.s["blocked"])
        r = self.p.cycle(approval(approval_id="A2"))
        self.assertFalse(r["entry"]["sent"])
        self.assertEqual(len(self.b.sent), 1)

    def test_restart_after_crash_between_save_and_send(self):
        st = EN.new_state()
        i = dict(id="i1", side="BUY", ticker="XYZ", qty=1, est_price=50.0, stop_price=45.0,
                 order={"orderType": "MARKET"}, status="submitting", created=T0.isoformat(),
                 sent=None, order_id=None, approval_id="A1")
        st["intents"].append(i)
        p = self.make(state=st)
        p.cycle()
        self.assertEqual(p.s["intents"][0]["status"], "unknown")      # not found yet: wait
        self.assertEqual(self.b.sent, [])
        self.clock.adv(EN.UNKNOWN_WINDOW_MIN + 1)
        p.cycle()
        self.assertEqual(p.s["intents"][0]["status"], "not_found")
        self.assertEqual(self.b.sent, [])

    def test_sell_timeout_is_matched_never_sold_twice(self):
        self.p.cycle(approval())
        self.p.cycle()
        self.p.request_exit("XYZ")
        self.b.script = ["timeout_created"]
        self.p.cycle()
        self.clock.adv(1)
        for _ in range(3):
            self.p.cycle()
        sells = [o for _, o in self.b.sent if o["orderType"] == "MARKET"
                 and o["orderLegCollection"][0]["instruction"] == "SELL"]
        self.assertEqual(len(sells), 1)
        self.assertEqual(self.p.s["closed"][0]["exit_reason"], "owner")
        self.assertNotIn("XYZ", self.b.positions)

    def test_buy_rejected(self):
        self.b.script = ["reject"]
        r = self.p.cycle(approval())
        self.assertEqual(r["entry"]["status"], "rejected")
        self.assertEqual(self.p.s["positions"], [])
        self.assertIsNone(self.p.s["blocked"])


class Fills(Base):
    def test_partial_fill_stop_matches_bought_shares(self):
        self.b.cash = 500
        p = self.make()
        p.s["closed"].append(dict(ticker="OLD"))                # allow qty 3 under the budget
        self.b.fill_qty = 2
        p.cycle(approval(qty=3))
        p.cycle()
        self.assertEqual(p.s["positions"][0]["qty"], 2)
        self.assertEqual([o["qty"] for o in self.b.live_stops("XYZ")], [2.0])
        buy = self.b.buys()[0]
        oid = next(o["id"] for o in self.b.orders.values() if o["type"] == "MARKET")
        self.b.fill(oid, 1, 50.0)                                # the rest fills later
        p.cycle()
        self.assertEqual(p.s["positions"][0]["qty"], 3)
        self.assertEqual([o["qty"] for o in self.b.live_stops("XYZ")], [3.0])
        self.assertEqual(buy["orderLegCollection"][0]["quantity"], 3)

    def test_partial_remainder_cancelled_after_timeout(self):
        p = self.make()
        p.s["closed"].append(dict(ticker="OLD"))
        self.b.fill_qty = 1
        p.cycle(approval(qty=3))
        self.clock.adv(EN.ENTRY_TIMEOUT_MIN + 1)
        p.cycle()
        p.cycle()
        oid = next(o["id"] for o in self.b.orders.values() if o["type"] == "MARKET")
        self.assertIn(oid, self.b.cancels)
        self.assertEqual([o["qty"] for o in self.b.live_stops("XYZ")], [1.0])

    def test_stop_rejected_blocks_entries_and_alerts(self):
        self.b.script = ["ok", "stop_reject", "stop_reject", "stop_reject"]
        self.p.cycle(approval())
        for _ in range(4):
            self.p.cycle()
        self.assertIn("PROTECTION FAILED", self.p.s["blocked"])
        self.assertTrue(any("stop placement failed" in a["title"] for a in self.p.s["alerts"]))
        r = self.p.cycle(approval(approval_id="A2", ticker="ABC"))
        self.assertFalse(r["entry"]["sent"])

    def test_stop_cancelled_outside_is_restored(self):
        self.p.cycle(approval())
        self.p.cycle()
        sid = self.b.live_stops("XYZ")[0]["id"]
        self.b.orders[sid]["status"] = "CANCELED"
        self.p.cycle()
        self.assertEqual(len(self.b.live_stops("XYZ")), 1)
        self.assertTrue(self.p.s["positions"][0]["protected"])

    def test_stopped_out_and_exit_race(self):
        self.p.cycle(approval())
        self.p.cycle()
        sid = self.b.live_stops("XYZ")[0]["id"]
        self.p.request_exit("XYZ")
        self.b.fill(sid, 1, 44.9)                                # the stop fires first
        self.p.cycle()
        self.assertEqual(self.p.s["closed"][0]["exit_reason"], "stop")
        sells = [o for _, o in self.b.sent if o["orderType"] == "MARKET"
                 and o["orderLegCollection"][0]["instruction"] == "SELL"]
        self.assertEqual(sells, [])

    def test_owner_sells_manually_no_stop_without_shares(self):
        self.p.cycle(approval())
        self.p.cycle()
        sid = self.b.live_stops("XYZ")[0]["id"]
        self.b.orders[sid]["status"] = "CANCELED"              # owner cancels the stop ...
        del self.b.positions["XYZ"]                              # ... and sells at Schwab
        n = len(self.b.sent)
        self.p.cycle()
        self.assertEqual(len(self.b.sent), n)                    # nothing placed
        self.assertIn("owner must check", self.p.s["blocked"])

    def test_kill_switch_keeps_protection(self):
        self.p.cycle(approval())
        self.p.cycle()
        sid = self.b.live_stops("XYZ")[0]["id"]
        self.b.orders[sid]["status"] = "CANCELED"
        off = self.make(state=self.p.s, entries_enabled=False)
        r = off.cycle(approval(approval_id="A2", ticker="ABC"))
        self.assertFalse(r["entry"]["sent"])
        self.assertEqual(len(self.b.live_stops("XYZ")), 1)


class ReadOnly(unittest.TestCase):
    def test_only_get_and_token_refresh(self):
        class H:
            def request(self, *a, **k):
                return "ok"

            def post(self, *a, **k):
                return "ok"
        ro = ReadOnlyHTTP(H())
        for m in ("POST", "PUT", "DELETE", "PATCH"):
            with self.assertRaises(ReadOnlyViolation):
                ro.request(m, "https://api.schwabapi.com/trader/v1/accounts/h/orders")
        with self.assertRaises(ReadOnlyViolation):
            ro.post("https://api.schwabapi.com/trader/v1/accounts/h/previewOrder")
        self.assertEqual(ro.post("https://api.schwabapi.com/v1/oauth/token"), "ok")
        self.assertEqual(ro.request("GET", "https://api.schwabapi.com/trader/v1/accounts"), "ok")

    def test_norm_order_children_and_avg(self):
        o = {"orderId": 5, "status": "FILLED", "orderType": "MARKET", "quantity": 3,
             "filledQuantity": 3, "orderLegCollection": [{"instruction": "BUY", "quantity": 3,
                                                          "instrument": {"symbol": "BRK/B"}}],
             "orderActivityCollection": [{"executionLegs": [{"quantity": 1, "price": 10},
                                                           {"quantity": 2, "price": 13}]}],
             "childOrderStrategies": [{"orderId": 6, "status": "WORKING", "orderType": "STOP",
                                       "quantity": 3, "stopPrice": 9, "orderLegCollection": [
                                           {"instruction": "SELL", "quantity": 3,
                                            "instrument": {"symbol": "BRK/B"}}]}]}
        n = norm_order(o)
        self.assertEqual((n[0]["symbol"], n[0]["avg_price"], n[1]["parent"]), ("BRK-B", 12.0, "5"))


if __name__ == "__main__":
    unittest.main()
