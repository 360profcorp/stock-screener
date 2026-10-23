"""Real-money pilot engine (Schwab), v2. LIVE IS OFF BY DEFAULT and nothing in this repository
switches it on. One long position at most, $1,000 pilot budget, first trade <= $100, every buy
only after the owner approved its exact parameters.

Every order the pilot sends (BUY, protective STOP, exit SELL) goes through the same path:
  intent saved BEFORE sending -> 4xx = rejected (safe) | timeout / 5xx / no id = UNKNOWN ->
  matched against the broker's own order list (ticker, side, type, quantity, price) ->
  one match adopted | several = blocked | none after UNKNOWN_WINDOW_MIN = blocked.
  An unknown order is NEVER re-sent; while one is unresolved nothing of that kind is sent.

Entry:   LIMIT BUY DAY at the owner-approved max price (the limit, not a quote check, enforces
         price and budget). After sending, the same call monitors the order (POLL_SEC) and
         puts a stop on every filled share at once; an unfilled remainder is cancelled at the
         end of MONITOR_SEC. A fill without a confirmed stop by then -> EMERGENCY alert, entries
         blocked (see PILOT.md for the owner's procedure).
Stop:    exactly one pilot STOP SELL GTC, for exactly the pilot's shares at the approved stop
         price, in a confirmed working status (PENDING_CANCEL / PENDING_REPLACE do not count).
         A wrong stop is cancelled and its cancellation CONFIRMED before a new one is sent.
Exit:    reconcile shares held and stop fills first, cancel the pilot's stop and confirm, then
         sell min(pilot shares, shares held). Partial sells and partial stop fills reduce the
         pilot's shares; the rest stays protected.
Outside: shares sold outside the pilot -> the pilot's stop is cut to the shares still held,
         or cancelled when none are left (never a stop on shares that are gone); owner alerted.

The pilot only touches order ids it recorded. Manual positions and orders are never sold,
cancelled or modified; a ticker with any manual position or order is refused for entry.
"""
import copy
import time as _time
import uuid
from datetime import datetime, timedelta, timezone

from pilot.broker import (LIVE_STATUSES, BrokerUnavailable, OrderRejected, SendUnknown,
                          limit_buy, market_sell, stop_sell)  # noqa: F401 (re-exported for tests)

BUDGET_USD = 1000.0
FIRST_TRADE_MAX_USD = 100.0
MAX_POSITIONS = 1
UNKNOWN_WINDOW_MIN = 10          # an unknown order still unmatched after this: blocked
STOP_ATTEMPTS = 3                # definite rejections of a stop before PROTECTION FAILED
MATCH_SLACK_SEC = 120            # broker clock vs ours when matching an unknown order
POLL_SEC = 2                     # entry monitor
MONITOR_SEC = 120
# a stop counts as protection only in these statuses (not PENDING_CANCEL / _REPLACE / review)
PROTECTING = {"WORKING", "PENDING_ACTIVATION", "AWAITING_STOP_CONDITION", "QUEUED",
              "ACCEPTED", "NEW", "AWAITING_PARENT_ORDER", "AWAITING_CONDITION"}
UNRESOLVED = ("submitting", "unknown", "ambiguous", "not_found")


class PilotBlocked(RuntimeError):
    pass


def new_state():
    return dict(version=2, intents=[], positions=[], closed=[], used_approvals=[],
                blocked=None, alerts=[], log=[])


def _now():
    return datetime.now(timezone.utc)


def _iso(t):
    return t.astimezone(timezone.utc).isoformat(timespec="seconds")


def _ts(s):
    if not s:
        return None
    return datetime.fromisoformat(str(s).replace("Z", "+00:00").replace("+0000", "+00:00"))


def _px(x):
    return None if x is None else round(float(x), 2)


class Pilot:
    def __init__(self, broker, state=None, save=None, live=False, entries_enabled=True,
                 account_suffix="", now=_now, alert=None, sleep=None):
        self.b = broker
        self.s = state if state is not None else new_state()
        self.save = save or (lambda s: None)
        self.live = bool(live)
        self.entries_enabled = bool(entries_enabled)
        self.account_suffix = account_suffix
        self.now = now
        self.sleep = sleep or _time.sleep
        self.alert_fn = alert or (lambda title, text: None)
        self.snap = None
        self._cache = {}

    # ============================================================ basics
    def _log(self, text):
        self.s["log"] = (self.s["log"] + [f"{_iso(self.now())} {text}"])[-500:]

    def _alert(self, title, text):
        self.s["alerts"].append(dict(at=_iso(self.now()), title=title, text=text))
        self._log(f"ALERT {title}: {text}")
        self.alert_fn(title, text)

    def _block(self, reason):
        if self.s["blocked"] != reason:
            self.s["blocked"] = reason
            self._alert("Pilot: new entries blocked", reason)

    def _persist(self):
        self.save(copy.deepcopy(self.s))

    def refresh(self):
        self.snap = self.b.snapshot()
        self._cache = {}

    def _own(self, oid):
        """The pilot's own orders are always read directly by id: a GTC stop older than the
        snapshot's order window is still live, and absence from a list never means cancelled."""
        if oid not in self._cache:
            self._cache[oid] = self.b.get_order(oid)
        return self._cache[oid]

    def held(self, ticker):
        return float((self.snap["positions"].get(ticker) or {}).get("qty", 0))

    def own_ids(self):
        ids = {str(i["order_id"]) for i in self.s["intents"] if i.get("order_id")}
        for p in self.s["positions"] + self.s["closed"]:
            ids.update(p.get("order_ids", []))
        return ids

    def _order(self, oid):
        """Fresh read of one order (the snapshot may be seconds old)."""
        return self.b.get_order(oid)

    def pending(self, kind, pos_id=None):
        return [i for i in self.s["intents"] if i["kind"] == kind and i["status"] in UNRESOLVED
                and (pos_id is None or i.get("position") == pos_id)]

    def committed_usd(self):
        c = sum(p["qty"] * p["entry"] for p in self.s["positions"] if p["qty"] > 0)
        c += sum((i["qty"] - i.get("filled", 0)) * i["limit"] for i in self.s["intents"]
                 if i["kind"] == "BUY" and i["status"] in UNRESOLVED + ("working",))
        return c

    # ============================================================ send path (all orders)
    def _intent(self, kind, ticker, qty, order, **extra):
        i = dict(id=uuid.uuid4().hex[:12], kind=kind, ticker=ticker, qty=int(qty), order=order,
                 status="submitting", created=_iso(self.now()), sent=None, order_id=None,
                 filled=0, **extra)
        self.s["intents"].append(i)
        self._persist()                                   # saved BEFORE the order leaves
        return i

    def _send(self, i):
        i["sent"] = _iso(self.now())
        try:
            oid = self.b.place(i["order"])
        except OrderRejected as e:
            i["status"], i["error"] = "rejected", str(e)
            self._log(f"{i['kind']} {i['ticker']} rejected: {e}")
            self._persist()
            return None
        except SendUnknown as e:
            i["status"], i["error"] = "unknown", str(e)
            self._log(f"{i['kind']} {i['ticker']} result unknown: {e}")
            self._persist()
            return None
        except BrokerUnavailable as e:
            i["status"], i["error"] = "not_sent", str(e)
            self._persist()
            return None
        i["order_id"], i["status"] = str(oid), "working"
        self._attach(i)
        self._persist()
        return str(oid)

    def _attach(self, i):
        if i.get("position"):
            p = self._pos(i["position"])
            if p is not None:
                p.setdefault("order_ids", []).append(i["order_id"])

    def _matches(self, i, o):
        leg = i["order"]["orderLegCollection"][0]
        if not (o["symbol"] == i["ticker"] and o["instruction"] == leg["instruction"]
                and o["type"] == i["order"]["orderType"] and int(o["qty"]) == int(i["qty"])
                and o["parent"] is None):
            return False
        if i["order"].get("stopPrice") is not None and _px(o["stop_price"]) != _px(
                i["order"]["stopPrice"]):
            return False
        if i["order"].get("price") is not None and _px(o.get("price")) != _px(i["order"]["price"]):
            return False
        t0 = _ts(i["created"]) - timedelta(seconds=MATCH_SLACK_SEC)
        return (_ts(o["entered"]) or t0) >= t0

    def resolve_unknown(self, out):
        own = self.own_ids()
        for i in [i for i in self.s["intents"] if i["status"] in ("submitting", "unknown")]:
            cands = [o for o in self.snap["orders"] if o["id"] not in own and self._matches(i, o)]
            if len(cands) == 1:
                i["order_id"], i["status"] = cands[0]["id"], "working"
                own.add(i["order_id"])
                self._attach(i)
                self._log(f"unknown {i['kind']} {i['ticker']} matched broker order {i['order_id']}")
                out["actions"].append(f"matched unknown {i['kind']} {i['ticker']} -> {i['order_id']}")
            elif len(cands) > 1:
                i["status"] = "ambiguous"
                self._block(f"{len(cands)} broker orders could be the unknown {i['kind']} "
                            f"{i['ticker']}: owner must check (never re-sent)")
            elif self.now() - _ts(i["created"]) > timedelta(minutes=UNKNOWN_WINDOW_MIN):
                i["status"] = "not_found"
                self._block(f"{i['kind']} {i['ticker']} result unknown and not found at the "
                            f"broker after {UNKNOWN_WINDOW_MIN} min: never re-sent, owner must check")
            else:
                i["status"] = "unknown"

    # ============================================================ the cycle
    def cycle(self, approval=None) -> dict:
        out = dict(at=_iso(self.now()), actions=[], entry=None)
        try:
            self.refresh()
        except BrokerUnavailable as e:
            out["broker"] = f"unavailable: {e}"
            self._alert("Pilot: broker unavailable", f"{e}. Nothing sent; stops at Schwab stay.")
            self._persist()
            return out
        if self.account_suffix and not str(self.snap["account_number"]).endswith(
                self.account_suffix):
            self._block("connected account does not match the pilot account")
            self._persist()
            return out
        try:
            self.step(out)
        except BrokerUnavailable as e:                    # lost mid-pass: stop, keep state
            out["broker"] = f"lost during the pass: {e}"
            self._alert("Pilot: broker lost during a pass", f"{e}. Re-run reconciles.")
            self._persist()
            return out
        if approval is not None:
            out["entry"] = self.enter(approval, out)
        self._persist()
        return out

    def step(self, out):
        """One reconciliation pass on fresh broker state (no new entry)."""
        self.resolve_unknown(out)
        self.poll_entries(out)
        for p in list(self.s["positions"]):
            if p["status"] == "closing":
                self.progress_exit(p, out)
            else:
                self.protect(p, out)
        unprotected = [p for p in self.s["positions"] if p["status"] == "open" and p["qty"] > 0
                       and not p.get("protected")]
        if unprotected and not self.s["blocked"]:
            self._block("an open pilot position is not protected yet")
        if not unprotected and self.s["blocked"] == "an open pilot position is not protected yet":
            self.s["blocked"] = None

    # ============================================================ entry fills
    def _pos(self, pid):
        return next((p for p in self.s["positions"] if p["id"] == pid), None)

    def poll_entries(self, out):
        for i in [i for i in self.s["intents"] if i["kind"] == "BUY" and i["status"] == "working"]:
            o = self._order(i["order_id"])
            filled = int(o["filled"])
            p = self._pos(i["position"])
            if filled > i["filled"]:
                if p is None:
                    p = dict(id=i["position"], ticker=i["ticker"], qty=0, entry=None,
                             stop_price=i["stop_price"], order_ids=[i["order_id"]],
                             fills={}, opened=_iso(self.now()), status="open",
                             approval_id=i["approval_id"], stop_rejects=0, exits=[])
                    self.s["positions"].append(p)
                new = filled - i["filled"]
                p["qty"] += new
                p["entry"] = o["avg_price"] or i["limit"]
                i["filled"] = filled
                p["protected"] = False
                out["actions"].append(f"{i['ticker']}: {filled}/{i['qty']} filled @ {p['entry']}")
                self._persist()
            if o["status"] in ("FILLED", "CANCELED", "EXPIRED", "REJECTED"):
                i["status"] = "filled" if o["status"] == "FILLED" else (
                    "partial_final" if filled else o["status"].lower())
                if not filled:
                    out["actions"].append(f"entry {i['ticker']} {o['status']}")

    # ============================================================ protection
    def _sync_outside(self, p, out):
        """Stop fills and shares sold outside the pilot reduce the pilot's shares."""
        for oid in p.get("order_ids", []):
            o = self._own(oid)
            if o["instruction"] != "SELL":
                continue
            done = p["fills"].get(oid, 0)
            if o["filled"] > done:
                q = int(o["filled"] - done)
                p["fills"][oid] = o["filled"]
                p["qty"] -= q
                reason = "stop" if o["type"] == "STOP" else p.get("exit_reason", "owner")
                p["exits"].append(dict(qty=q, px=o["avg_price"], reason=reason, order=oid))
                out["actions"].append(f"{p['ticker']}: {q} sold ({reason}) @ {o['avg_price']}")
        held = int(self.held(p["ticker"]))
        if held < p["qty"]:                               # sold outside the pilot
            gone = p["qty"] - held
            p["exits"].append(dict(qty=gone, px=None, reason="outside", order=None))
            p["qty"] = held
            self._alert("Pilot: shares sold outside the pilot",
                        f"{p['ticker']}: broker holds {held}, pilot had {held + gone}; the "
                        "pilot's stop is cut to the shares still held")

    def _own_stops(self, p, statuses=LIVE_STATUSES):
        out = []
        for oid in dict.fromkeys(p.get("order_ids", [])):
            o = self._own(oid)
            if o["type"] == "STOP" and o["status"] in statuses:
                out.append(o)
        return out

    def _good(self, o, p):
        return (o["status"] in PROTECTING and o["instruction"] == "SELL" and o["type"] == "STOP"
                and o["duration"] == "GOOD_TILL_CANCEL" and _px(o["stop_price"]) == _px(
                    p["stop_price"]) and int(o["qty"] - o["filled"]) == int(p["qty"]))

    def _cancel_confirmed(self, orders, out) -> bool:
        """Request cancellation of the pilot's own orders; True only when every one is
        confirmed CANCELED (or FILLED) by a fresh read. Never assumes."""
        ok = True
        for o in orders:
            if o["status"] not in ("PENDING_CANCEL",):
                try:
                    self.b.cancel(o["id"])
                    out["actions"].append(f"cancel {o['type']} {o['id']}")
                except (OrderRejected, SendUnknown) as e:
                    self._log(f"cancel {o['id']}: {e}")
            f = self._order(o["id"])
            self._cache[o["id"]] = f
            if f["status"] not in ("CANCELED", "FILLED", "EXPIRED", "REJECTED", "REPLACED"):
                ok = False
        return ok

    def protect(self, p, out) -> bool:
        for _ in range(3):
            self._sync_outside(p, out)
            live = self._own_stops(p)
            if p["qty"] <= 0:                             # nothing left to protect
                if live and not self._cancel_confirmed(live, out):
                    p["protected"] = False
                    return False                          # retry the cancel next pass
                self._close(p, out)
                return True
            if self.pending("STOP", p["id"]):             # unknown stop: never send another
                p["protected"] = False
                return False
            good = [o for o in live if self._good(o, p)]
            if len(good) == 1 and len(live) == 1:
                p["protected"] = True
                return True
            p["protected"] = False
            keep = good[:1]
            extra = [o for o in live if o not in keep]
            if not extra:
                break                                     # no live stop: place one below
            if not self._cancel_confirmed(extra, out):
                return False                              # old stop not confirmed cancelled yet
            # a cancelled stop may have (partly) filled first: re-read positions and orders
            # and recount the pilot's shares before deciding what still needs protection
            self.refresh()
        else:
            return False
        if p["stop_rejects"] >= STOP_ATTEMPTS:
            self._block(f"PROTECTION FAILED: {p['ticker']} {p['qty']} sh without a broker stop "
                        f"after {STOP_ATTEMPTS} rejections — set a stop manually at Schwab")
            return False
        i = self._intent("STOP", p["ticker"], p["qty"],
                         stop_sell(p["ticker"], p["qty"], p["stop_price"]), position=p["id"])
        oid = self._send(i)
        if oid is None:
            if i["status"] == "rejected":
                p["stop_rejects"] += 1
                self._alert("Pilot: stop rejected", f"{p['ticker']} ({p['stop_rejects']}/"
                            f"{STOP_ATTEMPTS}): {i.get('error')}")
            return False
        st = self._order(oid)
        if self._good(st, p):
            p["protected"], p["stop_rejects"] = True, 0
            out["actions"].append(f"{p['ticker']}: stop {p['stop_price']} x {p['qty']} GTC ({oid})")
            return True
        return False

    # ============================================================ exits
    def request_exit(self, ticker, reason="owner"):
        for p in self.s["positions"]:
            if p["ticker"] == ticker and p["status"] == "open":
                p["status"], p["exit_reason"] = "closing", reason
                self._persist()
                return True
        return False

    def progress_exit(self, p, out):
        self._sync_outside(p, out)
        if p["qty"] <= 0:
            self.protect(p, out)                          # cancels leftover stops, closes
            return
        if self.pending("SELL", p["id"]):
            return                                        # sell result unknown: never resend
        sells = [i for i in self.s["intents"] if i["kind"] == "SELL" and i.get("position") == p["id"]
                 and i["status"] == "working"]
        if sells:
            o = self._order(sells[-1]["order_id"])
            if o["status"] in ("FILLED", "CANCELED", "EXPIRED", "REJECTED"):
                sells[-1]["status"] = o["status"].lower()
                if p["qty"] > 0 and o["status"] != "FILLED":
                    p["status"] = "open"                  # rest goes back under protection
                    self._alert("Pilot: exit incomplete", f"{p['ticker']}: {o['status']}, "
                                f"{p['qty']} sh left — protected again")
                    self.protect(p, out)
            return
        live = self._own_stops(p)
        if live and not self._cancel_confirmed(live, out):
            return                                        # confirm the cancel before selling
        self.refresh()                                    # a stop may have filled meanwhile
        self._sync_outside(p, out)
        if p["qty"] <= 0:
            self._close(p, out)
            return
        qty = min(int(p["qty"]), int(self.held(p["ticker"])))
        i = self._intent("SELL", p["ticker"], qty, market_sell(p["ticker"], qty), position=p["id"])
        if self._send(i) is None and i["status"] == "rejected":
            p["status"] = "open"
            self._alert("Pilot: exit rejected", f"{p['ticker']}: {i.get('error')} — protected again")
            self.protect(p, out)

    def _close(self, p, out):
        sold = [e for e in p["exits"] if e["px"] is not None]
        q = sum(e["qty"] for e in sold)
        pnl = sum(e["qty"] * (e["px"] - p["entry"]) for e in sold) if p["entry"] else None
        p.update(status="closed", qty=0, closed=_iso(self.now()), realized_pnl=pnl,
                 exit_reason=p["exits"][-1]["reason"] if p["exits"] else p.get("exit_reason"),
                 exit=(sum(e["qty"] * e["px"] for e in sold) / q) if q else None,
                 protected=None)
        self.s["positions"].remove(p)
        self.s["closed"].append(p)
        out["actions"].append(f"{p['ticker']}: closed ({p['exit_reason']})")
        if any(e["reason"] == "outside" for e in p["exits"]):
            self._block(f"{p['ticker']} was closed outside the pilot: owner must confirm")
        self._log(f"closed {p['ticker']} {p['exit_reason']}")

    # ============================================================ new entry
    def entry_blockers(self, a) -> list:
        why = []
        if not self.live:
            why.append("live mode is off")
        if not self.entries_enabled:
            why.append("new entries are switched off")
        if self.s["blocked"]:
            why.append(f"blocked: {self.s['blocked']}")
        if any(i["status"] in UNRESOLVED + ("working",) for i in self.s["intents"]):
            why.append("an earlier order is unresolved")
        if a.get("approval_id") in self.s["used_approvals"]:
            why.append("approval already used")
        if a.get("side", "BUY") != "BUY" or a.get("asset", "EQUITY") != "EQUITY":
            why.append("long equity only")
        exp = _ts(a.get("expires_at"))
        if exp is None or self.now() > exp:
            why.append("approval expired")
        if a.get("account_last4") and not str(self.snap["account_number"]).endswith(
                a["account_last4"]):
            why.append("approval is for another account")
        qty, limit, stop = a.get("qty", 0), float(a.get("max_price", 0)), float(a.get("stop_price", 0))
        if not isinstance(qty, int) or qty < 1:
            why.append("whole shares >= 1 only")
        if not (0 < stop < limit):
            why.append("need 0 < stop < max price")
        if self.s["positions"]:
            why.append(f"max {MAX_POSITIONS} pilot position")
        held = self.held(a["ticker"])
        own = self.own_ids()
        manual = [o for o in self.snap["orders"] if o["symbol"] == a["ticker"]
                  and o["status"] in LIVE_STATUSES and o["id"] not in own]
        if held:
            why.append(f"{a['ticker']}: a position already exists at the broker (manual)")
        if manual:
            why.append(f"{a['ticker']}: {len(manual)} open order(s) not from the pilot")
        cost = qty * limit if isinstance(qty, int) else 0       # the LIMIT is the hard cap
        first = not self.s["closed"]
        if first and cost > FIRST_TRADE_MAX_USD:
            why.append(f"first trade max ${cost:.2f} > ${FIRST_TRADE_MAX_USD:.0f}")
        if self.committed_usd() + cost > BUDGET_USD:
            why.append(f"budget: ${self.committed_usd() + cost:.2f} > ${BUDGET_USD:.0f}")
        cash = self.snap["balances"].get("cash_no_margin")
        if cash is None:
            why.append("own cash unknown (no leverage allowed): refused")
        elif cost > float(cash):
            why.append(f"own cash ${float(cash):.2f} < ${cost:.2f} (no margin)")
        return why

    def enter(self, a: dict, out=None) -> dict:
        out = out if out is not None else dict(actions=[])
        why = self.entry_blockers(a)
        if why:
            return dict(sent=False, why=why)
        self.s["used_approvals"].append(a["approval_id"])
        pid = uuid.uuid4().hex[:12]
        i = self._intent("BUY", a["ticker"], a["qty"],
                         limit_buy(a["ticker"], a["qty"], a["max_price"]), position=pid,
                         limit=float(a["max_price"]), stop_price=float(a["stop_price"]),
                         approval_id=a["approval_id"])
        oid = self._send(i)
        res = dict(sent=True, order_id=oid, status=i["status"], max_cost=a["qty"] * a["max_price"])
        res["monitor"] = self.monitor_entry(i, out)
        return res

    def monitor_entry(self, i, out) -> str:
        """Right after the buy: poll, protect every filled share at once, cancel the unfilled
        rest at the end. A fill that is still unprotected at the end -> EMERGENCY."""
        if i["status"] in ("rejected", "not_sent"):
            return i["status"]
        deadline = self.now() + timedelta(seconds=MONITOR_SEC)
        while True:
            try:
                self.refresh()
                self.step(out)
            except BrokerUnavailable as e:
                self._alert("Pilot: broker lost during entry", str(e))
                self._persist()
                if self.now() >= deadline:
                    break
                self.sleep(POLL_SEC)
                continue
            p = self._pos(i["position"])
            done = i["status"] not in UNRESOLVED + ("working",)
            if done and (p is None or p.get("protected") or p["status"] == "closed"):
                return "done"
            if self.now() >= deadline:
                break
            self.sleep(POLL_SEC)
        if i["status"] == "working":                     # unfilled remainder: cancel (own order)
            try:
                o = self._order(i["order_id"])
                if self._cancel_confirmed([o], out):
                    self.refresh()
                    self.step(out)
            except BrokerUnavailable as e:
                self._alert("Pilot: cannot cancel the entry remainder", str(e))
        p = self._pos(i["position"])
        if ((p is not None and p["qty"] > 0 and not p.get("protected"))
                or i["status"] in UNRESOLVED + ("working",)):
            self._block(f"EMERGENCY: {i['ticker']} entry not confirmed protected within "
                        f"{MONITOR_SEC}s ({'order not confirmed' if i['status'] != 'filled' and p is None else 'no stop'})"
                        " — owner: check Schwab now and place a stop for the pilot's shares")
            return "emergency"
        return "done"
