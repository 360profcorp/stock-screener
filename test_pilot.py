"""Pilot engine v2 tests on scripted (fake) Schwab responses. No network, no real orders.
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

    def adv(self, seconds):
        self.t += timedelta(seconds=seconds)


class FakeBroker:
    """Scripted broker. place script entries (consumed per place()):
    'ok' | 'lost_after_accept' (accepted, response lost) | 'lost' (never reached) | 'reject'.
    cancel_mode: 'now' (CANCELED at once) | 'pending' (PENDING_CANCEL until settle_cancels())."""
    def __init__(self, clock, quote=50.0, cash=500.0):
        self.clock, self.ids = clock, itertools.count(1000)
        self.positions, self.orders = {}, {}
        self.q, self.cash = quote, cash
        self.script, self.fill_qty, self.cancel_mode = [], None, "now"
        self.sent, self.cancels, self.down = [], [], False
        self.on_sleep = None
        self.window_days = 7          # the order list only shows recently entered orders
        self.cancel_fills = None      # qty that fills while a cancel is requested

    def _new(self, order, status):
        oid = str(next(self.ids))
        leg = order["orderLegCollection"][0]
        o = dict(id=oid, parent=None, status=status, symbol=leg["instrument"]["symbol"],
                 instruction=leg["instruction"], type=order["orderType"],
                 duration=order["duration"], qty=float(leg["quantity"]), filled=0.0,
                 remaining=float(leg["quantity"]), stop_price=order.get("stopPrice"),
                 price=order.get("price"), entered=self.clock().isoformat(), closed=None,
                 avg_price=None, legs=1, strategy="SINGLE")
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

    def snapshot(self):
        if self.down:
            raise BrokerUnavailable("Schwab login expired (7 days)")
        return dict(account_number="99991234", type="CASH",
                    positions={t: dict(qty=q, asset="EQUITY", avg=None)
                               for t, q in self.positions.items()},
                    orders=[copy.deepcopy(o) for o in self.orders.values()
                            if datetime.fromisoformat(o["entered"]) >=
                            self.clock() - timedelta(days=self.window_days)],
                    balances=dict(cash=self.cash, cash_available=self.cash), flags={})

    def get_order(self, oid):
        if self.down:
            raise BrokerUnavailable("down")
        return copy.deepcopy(self.orders[str(oid)])

    def quote(self, t):
        return self.q

    def place(self, order):
        b = self.script.pop(0) if self.script else "ok"
        self.sent.append((b, copy.deepcopy(order)))
        if b == "reject":
            raise OrderRejected("400: rejected")
        if b == "lost":
            raise SendUnknown("ReadTimeout")
        o = self._new(order, "WORKING")
        if o["type"] == "MARKET" or (o["type"] == "LIMIT" and self.q <= o["price"]):
            q = self.fill_qty if (self.fill_qty and o["instruction"] == "BUY") else o["qty"]
            self.fill_qty = None
            self.fill(o["id"], q, min(self.q, o["price"] or self.q))
        if b == "lost_after_accept":
            raise SendUnknown("ReadTimeout after the broker accepted")
        return o["id"]

    def cancel(self, oid):
        self.cancels.append(str(oid))
        o = self.orders[str(oid)]
        if o["status"] in ("FILLED", "CANCELED"):
            raise OrderRejected("400: not cancelable")
        if self.cancel_fills:                         # the stop triggers before the cancel lands
            q, self.cancel_fills = self.cancel_fills, None
            self.fill(o["id"], q, 44.9)
            if o["status"] == "FILLED":
                raise OrderRejected("400: order already filled")
        o["status"] = "CANCELED" if self.cancel_mode == "now" else "PENDING_CANCEL"

    def settle_cancels(self):
        for o in self.orders.values():
            if o["status"] == "PENDING_CANCEL":
                o["status"] = "CANCELED"

    def sleep(self, sec):
        self.clock.adv(sec)
        if self.on_sleep:
            self.on_sleep()

    def stops(self, t, statuses=("WORKING", "PENDING_CANCEL")):
        return [o for o in self.orders.values() if o["symbol"] == t and o["type"] == "STOP"
                and o["status"] in statuses]

    def sent_types(self, kind, instr=None):
        return [o for _, o in self.sent if o["orderType"] == kind and (
            instr is None or o["orderLegCollection"][0]["instruction"] == instr)]


def approval(**kw):
    a = dict(approval_id="A1", ticker="XYZ", side="BUY", asset="EQUITY", qty=1,
             max_price=60.0, stop_price=45.0, expires_at=(T0 + timedelta(hours=2)).isoformat(),
             account_last4="1234")
    a.update(kw)
    return a


def _ts_of(o):
    return datetime.fromisoformat(o["entered"])


class Base(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.b = FakeBroker(self.clock)
        self.saves = []
        self.p = self.make()

    def make(self, state=None, **kw):
        args = dict(live=True, entries_enabled=True, account_suffix="1234", now=self.clock,
                    save=lambda s: self.saves.append(s), sleep=self.b.sleep)
        args.update(kw)
        return EN.Pilot(self.b, state, **args)

    def after_trade(self, qty=1):
        if qty > 1:
            self.p.s["closed"].append(dict(ticker="OLD"))
        r = self.p.cycle(approval(qty=qty))
        self.assertEqual(r["entry"]["monitor"], "done", r)
        return self.p.s["positions"][0]


# ================================================================= 1) LIMIT entry
class LimitEntry(Base):
    def test_buy_is_limit_at_the_approved_max_price(self):
        self.after_trade()
        buy = self.b.sent_types("LIMIT", "BUY")
        self.assertEqual(len(buy), 1)
        self.assertEqual((buy[0]["price"], buy[0]["duration"]), (60.0, "DAY"))
        self.assertEqual(self.b.sent_types("MARKET", "BUY"), [])

    def test_price_above_limit_never_fills_and_order_is_cancelled(self):
        self.b.q = 61.0
        r = self.p.cycle(approval())
        self.assertEqual(r["entry"]["monitor"], "done")
        self.assertEqual(self.p.s["positions"], [])
        buy = next(o for o in self.b.orders.values() if o["type"] == "LIMIT")
        self.assertEqual((buy["status"], buy["filled"]), ("CANCELED", 0))

    def test_budget_uses_the_limit_not_the_quote(self):
        self.b.q = 30.0
        r = self.p.cycle(approval(qty=2, max_price=55.0))          # 2 x 55 > $100 first trade
        self.assertTrue(any("first trade" in w for w in r["entry"]["why"]))
        p = self.make()
        p.s["closed"].append(dict(ticker="OLD"))
        self.b.cash = 5000
        r = p.cycle(approval(approval_id="A2", qty=17, max_price=60.0))   # 1,020 > $1,000
        self.assertTrue(any("budget" in w for w in r["entry"]["why"]))
        self.assertEqual(self.b.sent, [])


# ================================================================= 2) stop send path
class StopSendPath(Base):
    def test_stop_accepted_but_response_lost_is_matched_not_resent(self):
        self.b.script = ["ok", "lost_after_accept"]
        r = self.p.cycle(approval())
        self.assertEqual(r["entry"]["monitor"], "done")
        for _ in range(4):
            self.clock.adv(30)
            self.p.cycle()
        self.assertEqual(len(self.b.sent_types("STOP")), 1)
        self.assertEqual(len(self.b.stops("XYZ")), 1)
        self.assertTrue(self.p.s["positions"][0]["protected"])

    def test_stop_lost_entirely_is_never_resent_and_blocks(self):
        self.b.script = ["ok", "lost"]
        r = self.p.cycle(approval())
        self.assertEqual(r["entry"]["monitor"], "emergency")
        self.assertIn("EMERGENCY", self.p.s["blocked"])
        self.clock.adv(EN.UNKNOWN_WINDOW_MIN * 60 + 1)
        self.p.cycle()
        self.assertEqual(len(self.b.sent_types("STOP")), 1)
        self.assertEqual(self.b.stops("XYZ"), [])

    def test_intents_saved_before_sending(self):
        seen = []
        orig = self.b.place

        def place(order):
            seen.append((order["orderType"], copy.deepcopy(self.saves[-1]["intents"][-1])))
            return orig(order)
        self.b.place = place
        self.p.cycle(approval())
        kinds = dict(seen)
        self.assertEqual((kinds["STOP"]["kind"], kinds["STOP"]["status"]), ("STOP", "submitting"))
        self.assertEqual((kinds["LIMIT"]["kind"], kinds["LIMIT"]["status"]), ("BUY", "submitting"))

    def test_stop_rejected_three_times_protection_failed(self):
        self.b.script = ["ok", "reject", "reject", "reject"]
        r = self.p.cycle(approval())
        self.assertEqual(r["entry"]["monitor"], "emergency")
        for _ in range(3):
            self.p.cycle()
        self.assertTrue(any("PROTECTION FAILED" in a["text"] for a in self.p.s["alerts"]))
        self.assertEqual(len(self.b.sent_types("STOP")), 3)


# ================================================================= 3) replacing a stop
class ReplaceStop(Base):
    def test_new_stop_only_after_cancel_is_confirmed(self):
        pos = self.after_trade()
        old = self.b.stops("XYZ")[0]
        old["stop_price"] = 44.0                                   # wrong price at the broker
        self.b.cancel_mode = "pending"
        self.p.cycle()
        self.assertEqual(self.b.orders[old["id"]]["status"], "PENDING_CANCEL")
        self.assertEqual(len(self.b.sent_types("STOP")), 1)
        self.assertFalse(self.p.s["positions"][0]["protected"])
        self.p.cycle()
        self.assertEqual(len(self.b.sent_types("STOP")), 1)
        self.b.settle_cancels()
        self.p.cycle()
        self.assertEqual(len(self.b.sent_types("STOP")), 2)
        live = self.b.stops("XYZ", ("WORKING",))
        self.assertEqual([(o["stop_price"], o["qty"]) for o in live], [(45.0, 1.0)])
        self.assertTrue(self.p.s["positions"][0]["protected"])
        del pos

    def test_pending_cancel_and_day_stop_are_not_protection(self):
        self.after_trade()
        st = self.b.stops("XYZ")[0]
        st["status"] = "PENDING_CANCEL"
        self.b.cancel_mode = "pending"
        self.p.cycle()
        self.assertFalse(self.p.s["positions"][0]["protected"])
        self.b.settle_cancels()
        self.p.cycle()
        self.assertTrue(self.p.s["positions"][0]["protected"])
        st2 = self.b.stops("XYZ", ("WORKING",))[0]
        st2["duration"] = "DAY"
        self.b.cancel_mode = "now"
        self.p.cycle()
        self.assertEqual([o["duration"] for o in self.b.stops("XYZ", ("WORKING",))],
                         ["GOOD_TILL_CANCEL"])

    def test_two_live_stops_are_reduced_to_one(self):
        self.after_trade()
        extra = self.b._new(EN.stop_sell("XYZ", 1, 45.0), "WORKING")
        self.p.s["positions"][0]["order_ids"].append(extra["id"])
        self.p.cycle()
        self.assertEqual(len(self.b.stops("XYZ", ("WORKING",))), 1)
        self.assertTrue(self.p.s["positions"][0]["protected"])


class ReviewTwo(Base):
    def test_gtc_stop_older_than_the_order_window_is_not_duplicated(self):
        self.after_trade()
        self.clock.adv(9 * 86400)                                 # stop now outside the list
        self.assertEqual(self.b.snapshot()["orders"], [])
        for _ in range(3):
            self.p.cycle()
        self.assertEqual(len(self.b.sent_types("STOP")), 1)
        self.assertEqual(len(self.b.stops("XYZ", ("WORKING",))), 1)
        self.assertTrue(self.p.s["positions"][0]["protected"])

    def test_old_stop_filled_during_cancel_no_new_stop(self):
        self.after_trade()
        st = self.b.stops("XYZ")[0]
        st["stop_price"] = 44.0                                   # needs replacing ...
        self.b.cancel_fills = 1                                   # ... but it fires first
        self.p.cycle()
        self.assertEqual(len(self.b.sent_types("STOP")), 1)       # no stop on sold shares
        self.assertEqual(self.b.sent_types("MARKET", "SELL"), [])
        self.assertEqual(self.p.s["positions"], [])
        self.assertEqual(self.p.s["closed"][0]["exit_reason"], "stop")

    def test_old_stop_partly_filled_during_cancel_new_stop_for_the_rest(self):
        self.p.s["closed"].append(dict(ticker="OLD"))
        self.p.cycle(approval(qty=3))
        st = self.b.stops("XYZ")[0]
        st["stop_price"] = 44.0
        self.b.cancel_fills = 1                                   # 1 of 3 sold, rest cancelled
        self.p.cycle()
        self.assertEqual(self.p.s["positions"][0]["qty"], 2)
        self.assertEqual([o["qty"] for o in self.b.stops("XYZ", ("WORKING",))], [2.0])
        self.assertEqual(self.b.positions["XYZ"], 2)

    def test_old_stop_filled_during_exit_cancel_no_sell(self):
        self.after_trade()
        self.p.request_exit("XYZ")
        self.b.cancel_fills = 1
        self.p.cycle()
        self.assertEqual(self.b.sent_types("MARKET", "SELL"), [])
        self.assertEqual(self.p.s["closed"][0]["exit_reason"], "stop")


# ================================================================= 4) immediate protection
class ImmediateProtection(Base):
    def test_stop_placed_in_the_same_call_as_the_fill(self):
        r = self.p.cycle(approval())
        self.assertEqual(r["entry"]["monitor"], "done")
        self.assertEqual(len(self.b.stops("XYZ", ("WORKING",))), 1)
        self.assertTrue(self.p.s["positions"][0]["protected"])

    def test_fill_arriving_during_monitoring_is_protected_at_once(self):
        self.b.q = 61.0

        def later():
            if self.clock() >= T0 + timedelta(seconds=10):
                buy = next(o for o in self.b.orders.values() if o["type"] == "LIMIT")
                if buy["status"] == "WORKING":
                    self.b.fill(buy["id"], 1, 59.0)
        self.b.on_sleep = later
        r = self.p.cycle(approval())
        self.assertEqual(r["entry"]["monitor"], "done")
        st = self.b.stops("XYZ", ("WORKING",))
        self.assertEqual(len(st), 1)
        self.assertLessEqual(_ts_of(st[0]) - T0, timedelta(seconds=12))

    def test_partial_fills_stop_follows_bought_shares(self):
        self.p.s["closed"].append(dict(ticker="OLD"))
        self.b.fill_qty = 1
        n = {"k": 0}

        def later():
            n["k"] += 1
            buy = next(o for o in self.b.orders.values() if o["type"] == "LIMIT")
            if n["k"] == 3 and buy["status"] == "WORKING":
                self.b.fill(buy["id"], 1, 50.0)
        self.b.on_sleep = later
        r = self.p.cycle(approval(qty=3))
        self.assertEqual(r["entry"]["monitor"], "done")
        self.assertEqual(self.p.s["positions"][0]["qty"], 2)
        self.assertEqual([o["qty"] for o in self.b.stops("XYZ", ("WORKING",))], [2.0])
        buy = next(o for o in self.b.orders.values() if o["type"] == "LIMIT")
        self.assertEqual(buy["status"], "CANCELED")

    def test_broker_lost_during_monitoring_is_an_emergency(self):
        self.b.q = 61.0

        def drop():
            self.b.down = True
        self.b.on_sleep = drop
        r = self.p.cycle(approval())
        self.assertEqual(r["entry"]["monitor"], "emergency")
        self.assertIn("EMERGENCY", self.p.s["blocked"])


# ================================================================= 5) exits, partial, manual
class Exits(Base):
    def test_close_cancels_confirmed_then_sells(self):
        self.after_trade()
        self.p.request_exit("XYZ")
        self.b.q = 55.0
        self.p.cycle()
        self.p.cycle()
        self.assertEqual(self.p.s["positions"], [])
        c = self.p.s["closed"][0]
        self.assertEqual((c["exit_reason"], c["exit"], c["realized_pnl"]), ("owner", 55.0, 5.0))
        self.assertEqual(self.b.stops("XYZ"), [])
        self.assertNotIn("XYZ", self.b.positions)

    def test_no_sell_while_stop_cancel_is_pending(self):
        self.after_trade()
        self.p.request_exit("XYZ")
        self.b.cancel_mode = "pending"
        self.p.cycle()
        self.assertEqual(self.b.sent_types("MARKET", "SELL"), [])
        self.b.settle_cancels()
        self.p.cycle()
        self.assertEqual(len(self.b.sent_types("MARKET", "SELL")), 1)

    def test_partial_sell_rest_goes_back_under_protection(self):
        self.p.s["closed"].append(dict(ticker="OLD"))
        self.p.cycle(approval(qty=3))
        self.p.request_exit("XYZ")
        orig = self.b.place

        def place(order):
            if order["orderType"] != "MARKET":
                return orig(order)
            self.b.sent.append(("ok", copy.deepcopy(order)))
            o = self.b._new(order, "WORKING")
            self.b.fill(o["id"], 1, 52.0)                          # 1 of 3 sold ...
            o["status"], o["remaining"] = "CANCELED", 0            # ... rest cancelled
            return o["id"]
        self.b.place = place
        self.p.cycle()
        self.p.cycle()
        pos = self.p.s["positions"][0]
        self.assertEqual((pos["status"], pos["qty"]), ("open", 2))
        self.assertEqual([o["qty"] for o in self.b.stops("XYZ", ("WORKING",))], [2.0])

    def test_stop_partial_fill_reduces_shares(self):
        self.p.s["closed"].append(dict(ticker="OLD"))
        self.p.cycle(approval(qty=3))
        st = self.b.stops("XYZ")[0]
        self.b.fill(st["id"], 1, 44.9)
        self.p.cycle()
        pos = self.p.s["positions"][0]
        self.assertEqual(pos["qty"], 2)
        self.assertTrue(pos["protected"])
        self.assertEqual(len(self.b.sent_types("STOP")), 1)
        self.b.fill(st["id"], 2, 44.9)
        self.p.cycle()
        self.assertEqual(self.p.s["positions"], [])
        self.assertEqual(self.p.s["closed"][-1]["exit_reason"], "stop")

    def test_exit_requested_but_stop_fired_first(self):
        self.after_trade()
        st = self.b.stops("XYZ")[0]
        self.p.request_exit("XYZ")
        self.b.fill(st["id"], 1, 44.9)
        self.p.cycle()
        self.assertEqual(self.b.sent_types("MARKET", "SELL"), [])
        self.assertEqual(self.p.s["closed"][0]["exit_reason"], "stop")

    def test_manual_close_cancels_the_pilot_stop(self):
        self.after_trade()
        st = self.b.stops("XYZ")[0]
        del self.b.positions["XYZ"]                                 # owner sold at Schwab
        self.p.cycle()
        self.assertEqual(self.b.orders[st["id"]]["status"], "CANCELED")
        self.assertEqual(self.p.s["positions"], [])
        self.assertEqual(self.p.s["closed"][0]["exit_reason"], "outside")
        self.assertIn("outside the pilot", self.p.s["blocked"])
        self.assertEqual(self.b.sent_types("MARKET", "SELL"), [])

    def test_partial_manual_sale_cuts_the_stop(self):
        self.p.s["closed"].append(dict(ticker="OLD"))
        self.p.cycle(approval(qty=3))
        self.b.positions["XYZ"] = 1
        self.p.cycle()
        self.assertEqual(self.p.s["positions"][0]["qty"], 1)
        self.assertEqual([o["qty"] for o in self.b.stops("XYZ", ("WORKING",))], [1.0])

    def test_sell_response_lost_never_sold_twice(self):
        self.after_trade()
        self.p.request_exit("XYZ")
        self.b.script = ["lost_after_accept"]
        self.p.cycle()
        for _ in range(3):
            self.clock.adv(30)
            self.p.cycle()
        self.assertEqual(len(self.b.sent_types("MARKET", "SELL")), 1)
        self.assertEqual(self.p.s["closed"][0]["exit_reason"], "owner")

    def test_manual_shares_and_orders_never_touched(self):
        self.after_trade()
        manual = self.b._new(EN.stop_sell("XYZ", 7, 40.0), "WORKING")
        self.b.positions["XYZ"] += 7
        self.p.cycle()
        self.p.request_exit("XYZ")
        self.p.cycle()
        self.p.cycle()
        sells = self.b.sent_types("MARKET", "SELL")
        self.assertEqual([o["orderLegCollection"][0]["quantity"] for o in sells], [1])
        self.assertNotIn(manual["id"], self.b.cancels)
        self.assertEqual(self.b.positions["XYZ"], 7)


# ================================================================= guards
class Guards(Base):
    def test_live_off_and_entries_off_send_nothing(self):
        for p in (self.make(live=False), self.make(entries_enabled=False)):
            self.assertFalse(p.cycle(approval())["entry"]["sent"])
        self.assertEqual(self.b.sent, [])

    def test_duplicate_run_same_approval(self):
        self.after_trade()
        self.assertFalse(self.p.cycle(approval())["entry"]["sent"])
        self.assertEqual(len(self.b.sent_types("LIMIT", "BUY")), 1)

    def test_one_position(self):
        self.after_trade()
        r = self.p.cycle(approval(approval_id="A2", ticker="ABC"))
        self.assertTrue(any("max 1 pilot position" in w for w in r["entry"]["why"]))

    def test_manual_position_or_order_in_the_ticker(self):
        self.b.positions["XYZ"] = 10
        self.assertTrue(any("manual" in w for w in self.p.cycle(approval())["entry"]["why"]))
        del self.b.positions["XYZ"]
        self.b._new(EN.limit_buy("XYZ", 5, 40.0), "WORKING")
        r = self.p.cycle(approval(approval_id="A2"))
        self.assertTrue(any("not from the pilot" in w for w in r["entry"]["why"]))
        self.assertEqual(self.b.sent, [])

    def test_expired_token_and_account_mismatch(self):
        self.b.down = True
        self.assertIn("unavailable", self.p.cycle(approval())["broker"])
        self.b.down = False
        p = self.make(account_suffix="0000")
        p.cycle(approval())
        self.assertTrue(p.s["blocked"])
        self.assertEqual(self.b.sent, [])

    def test_expired_approval_and_bad_stop(self):
        self.clock.adv(3 * 3600)
        self.assertTrue(any("expired" in w for w in self.p.cycle(approval())["entry"]["why"]))
        r = self.p.cycle(approval(approval_id="A2",
                                  expires_at=(T0 + timedelta(hours=9)).isoformat(), stop_price=61.0))
        self.assertTrue(any("stop" in w for w in r["entry"]["why"]))

    def test_buy_response_lost_matched_and_protected(self):
        self.b.script = ["lost_after_accept"]
        r = self.p.cycle(approval())
        self.assertEqual(r["entry"]["monitor"], "done")
        self.assertEqual(len(self.b.sent_types("LIMIT", "BUY")), 1)
        self.assertEqual(len(self.b.stops("XYZ", ("WORKING",))), 1)

    def test_crash_between_save_and_send(self):
        st = EN.new_state()
        st["intents"].append(dict(id="i1", kind="BUY", ticker="XYZ", qty=1,
                                  order=EN.limit_buy("XYZ", 1, 60.0), status="submitting",
                                  created=T0.isoformat(), sent=None, order_id=None, filled=0,
                                  position="p1", limit=60.0, stop_price=45.0, approval_id="A1"))
        p = self.make(state=st)
        p.cycle()
        self.assertEqual(p.s["intents"][0]["status"], "unknown")
        self.clock.adv(EN.UNKNOWN_WINDOW_MIN * 60 + 1)
        p.cycle()
        self.assertEqual(p.s["intents"][0]["status"], "not_found")
        self.assertEqual(self.b.sent, [])

    def test_broker_lost_mid_pass_does_not_crash_or_send(self):
        self.after_trade()
        orig = self.b.get_order

        def flaky(oid):
            self.b.down = True
            return orig(oid)
        self.b.get_order = flaky
        self.p.request_exit("XYZ")
        r = self.p.cycle()
        self.assertIn("lost", r.get("broker", ""))
        self.assertEqual(self.b.sent_types("MARKET", "SELL"), [])
        self.b.get_order, self.b.down = orig, False
        self.p.cycle()
        self.p.cycle()
        self.assertEqual(len(self.b.sent_types("MARKET", "SELL")), 1)

    def test_kill_switch_keeps_protection(self):
        self.after_trade()
        st = self.b.stops("XYZ")[0]
        self.b.orders[st["id"]]["status"] = "CANCELED"
        off = self.make(state=self.p.s, entries_enabled=False)
        r = off.cycle(approval(approval_id="A2", ticker="ABC"))
        self.assertFalse(r["entry"]["sent"])
        self.assertEqual(len(self.b.stops("XYZ", ("WORKING",))), 1)


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

    def test_norm_order(self):
        o = {"orderId": 5, "status": "FILLED", "orderType": "LIMIT", "price": 60, "quantity": 3,
             "filledQuantity": 3, "orderLegCollection": [{"instruction": "BUY", "quantity": 3,
                                                          "instrument": {"symbol": "BRK/B"}}],
             "orderActivityCollection": [{"executionLegs": [{"quantity": 1, "price": 10},
                                                           {"quantity": 2, "price": 13}]}]}
        n = norm_order(o)[0]
        self.assertEqual((n["symbol"], n["avg_price"], n["price"]), ("BRK-B", 12.0, 60))


if __name__ == "__main__":
    unittest.main()
