"""Real-money pilot engine (Schwab). LIVE IS OFF BY DEFAULT and nothing in this repository
switches it on. One long position at most, $1,000 pilot budget, first trade <= $100, every
buy only after the owner approved its exact parameters.

Order path (one cycle = `cycle()`, safe to re-run at any time):

  0. broker snapshot FIRST (positions, orders, balances). Unreachable broker / expired login:
     nothing is sent, new entries are blocked; the broker-side stop keeps protecting.
  1. unknown submissions (timeout / 5xx / no id) are resolved against the broker's order list
     (same ticker, side, quantity, entered after the intent). Never re-sent.
  2. entry order: poll -> filled quantity; partial fills: the stop covers the shares actually
     bought; a remainder still working past ENTRY_TIMEOUT is cancelled (pilot's own order).
  3. protection: every open pilot position must have a live GTC STOP SELL at the broker for
     exactly the pilot's shares. Missing / wrong quantity -> re-placed (the old one cancelled
     first); after STOP_ATTEMPTS failures -> PROTECTION FAILED: entries blocked, owner alerted.
  4. exit (owner request or time exit): cancel the pilot's stop, confirm it is cancelled, then
     market-sell the pilot's shares only; a stop that filled meanwhile means already closed.
  5. new entry (only with an approval, live on, entries on, nothing unresolved).

The pilot only ever touches order ids recorded in its own state. Manual positions and orders
are never sold, cancelled or modified; a ticker with any manual position or order is refused.
Every intent is saved BEFORE it is sent (save callback), so a crash between "send" and
"record" is caught by step 1 on the next run.
"""
import copy
import uuid
from datetime import datetime, timedelta, timezone

from pilot.broker import (LIVE_STATUSES, BrokerUnavailable, OrderRejected, SendUnknown,
                          market_buy, market_sell, stop_sell)

BUDGET_USD = 1000.0
FIRST_TRADE_MAX_USD = 100.0
MAX_POSITIONS = 1
PRICE_BUFFER = 0.02            # budget check uses quote * (1 + 2 %) for a market buy
ENTRY_TIMEOUT_MIN = 15          # a partially filled entry still working after this: cancel rest
UNKNOWN_WINDOW_MIN = 10         # how long an unknown submission may stay unmatched
STOP_ATTEMPTS = 3
MATCH_SLACK_SEC = 120           # broker clock vs ours when matching an unknown submission


class PilotBlocked(RuntimeError):
    pass


def new_state():
    return dict(version=1, intents=[], positions=[], closed=[], used_approvals=[],
                blocked=None, alerts=[], log=[])


def _now():
    return datetime.now(timezone.utc)


def _iso(t):
    return t.astimezone(timezone.utc).isoformat(timespec="seconds")


def _ts(s):
    if not s:
        return None
    return datetime.fromisoformat(str(s).replace("Z", "+00:00").replace("+0000", "+00:00"))


class Pilot:
    def __init__(self, broker, state=None, save=None, live=False, entries_enabled=True,
                 account_suffix="", now=_now, alert=None):
        self.b = broker
        self.s = state if state is not None else new_state()
        self.save = save or (lambda s: None)
        self.live = bool(live)
        self.entries_enabled = bool(entries_enabled)
        self.account_suffix = account_suffix
        self.now = now
        self.alert_fn = alert or (lambda title, text: None)
        self.snap = None

    # ------------------------------------------------------------ helpers
    def _log(self, text):
        self.s["log"].append(f"{_iso(self.now())} {text}")
        self.s["log"] = self.s["log"][-500:]

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

    def own_ids(self):
        ids = set()
        for i in self.s["intents"]:
            if i.get("order_id"):
                ids.add(str(i["order_id"]))
        for p in self.s["positions"] + self.s["closed"]:
            for k in ("entry_order_id", "stop_order_id", "exit_order_id"):
                if p.get(k):
                    ids.add(str(p[k]))
            ids.update(map(str, p.get("old_stop_ids", [])))
        return ids

    def _order(self, oid):
        for o in self.snap["orders"]:
            if o["id"] == str(oid):
                return o
        return self.b.get_order(oid)

    def pilot_qty(self, ticker):
        return sum(p["qty"] for p in self.s["positions"] if p["ticker"] == ticker)

    def manual_activity(self, ticker):
        """Broker shares / live orders in `ticker` that are not the pilot's."""
        held = float((self.snap["positions"].get(ticker) or {}).get("qty", 0))
        manual_qty = held - self.pilot_qty(ticker)
        own = self.own_ids()
        manual_orders = [o for o in self.snap["orders"] if o["symbol"] == ticker
                         and o["status"] in LIVE_STATUSES and o["id"] not in own]
        return manual_qty, manual_orders

    def committed_usd(self):
        c = sum(p["qty"] * p["entry"] for p in self.s["positions"])
        c += sum(i["qty"] * i["est_price"] * (1 + PRICE_BUFFER) for i in self.s["intents"]
                 if i["side"] == "BUY" and i["status"] in ("submitting", "unknown", "working"))
        return c

    # ------------------------------------------------------------ the cycle
    def cycle(self, approval=None) -> dict:
        out = dict(at=_iso(self.now()), actions=[], entry=None)
        try:
            self.snap = self.b.snapshot()
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
        self.resolve_unknown(out)
        self.poll_entries(out)
        self.check_positions(out)
        self.ensure_protection(out)
        self.progress_exits(out)
        if approval is not None:
            out["entry"] = self.enter(approval)
        self._persist()
        return out

    # ------------------------------------------------------------ 1) unknown submissions
    def resolve_unknown(self, out):
        own = self.own_ids()
        for i in [i for i in self.s["intents"] if i["status"] in ("submitting", "unknown")]:
            t0 = _ts(i["created"]) - timedelta(seconds=MATCH_SLACK_SEC)
            cands = [o for o in self.snap["orders"] if o["symbol"] == i["ticker"]
                     and o["instruction"] == i["side"] and int(o["qty"]) == int(i["qty"])
                     and o["id"] not in own and o["parent"] is None
                     and (_ts(o["entered"]) or t0) >= t0
                     and o["type"] == i["order"]["orderType"]]
            if len(cands) == 1:
                i["order_id"], i["status"] = cands[0]["id"], "working"
                self._log(f"unknown {i['side']} {i['ticker']} matched broker order {i['order_id']}")
                out["actions"].append(f"matched unknown {i['side']} {i['ticker']} -> {i['order_id']}")
                own.add(i["order_id"])
            elif len(cands) > 1:
                i["status"] = "ambiguous"
                self._block(f"{len(cands)} broker orders could be the unknown {i['side']} "
                            f"{i['ticker']}: owner must check")
            elif self.now() - _ts(i["created"]) > timedelta(minutes=UNKNOWN_WINDOW_MIN):
                i["status"] = "not_found"
                self._block(f"{i['side']} {i['ticker']} result unknown and not found at the broker "
                            f"after {UNKNOWN_WINDOW_MIN} min: never re-sent, owner must check")
            else:
                i["status"] = "unknown"
                self._block(f"{i['side']} {i['ticker']} result still unknown")

    # ------------------------------------------------------------ 2) entry orders
    def poll_entries(self, out):
        for i in [i for i in self.s["intents"] if i["side"] == "BUY" and i["status"] == "working"]:
            o = self._order(i["order_id"])
            filled = int(o["filled"])
            if o["status"] == "REJECTED" or (o["status"] in ("CANCELED", "EXPIRED") and not filled):
                i["status"] = o["status"].lower()
                self._log(f"entry {i['ticker']} {o['status']}")
                out["actions"].append(f"entry {i['ticker']} {o['status']}")
                if self.s["blocked"] and "still unknown" in self.s["blocked"]:
                    self.s["blocked"] = None
                continue
            if filled <= 0:
                continue
            pos = next((p for p in self.s["positions"] if p["entry_order_id"] == i["order_id"]),
                       None)
            if pos is None:
                pos = dict(id=i["id"], ticker=i["ticker"], qty=0, entry=None,
                           entry_order_id=i["order_id"], stop_price=i["stop_price"],
                           stop_order_id=None, old_stop_ids=[], stop_attempts=0,
                           opened=_iso(self.now()), status="open", approval_id=i["approval_id"])
                self.s["positions"].append(pos)
            if filled != pos["qty"]:
                pos["qty"], pos["entry"] = filled, o["avg_price"] or i["est_price"]
                out["actions"].append(f"{i['ticker']}: {filled} filled @ {pos['entry']}")
            if o["status"] in ("FILLED", "CANCELED", "EXPIRED"):
                i["status"] = "filled" if o["status"] == "FILLED" else "partial_final"
            elif self.now() - _ts(i["sent"]) > timedelta(minutes=ENTRY_TIMEOUT_MIN):
                try:
                    self.b.cancel(i["order_id"])          # the pilot's own entry, remainder only
                    out["actions"].append(f"{i['ticker']}: cancel unfilled remainder")
                except (OrderRejected, SendUnknown) as e:
                    self._alert("Pilot: cannot cancel entry remainder", f"{i['ticker']}: {e}")

    # ------------------------------------------------------------ 3) positions vs broker
    def check_positions(self, out):
        for p in list(self.s["positions"]):
            if p["status"] != "open" or not p["stop_order_id"]:
                continue
            st = self._order(p["stop_order_id"])
            if st["status"] == "FILLED":
                self._close(p, st["avg_price"] or p["stop_price"], "stop", st["id"])
                out["actions"].append(f"{p['ticker']}: stopped out")
                continue
            held = float((self.snap["positions"].get(p["ticker"]) or {}).get("qty", 0))
            if held < p["qty"]:
                self._block(f"{p['ticker']}: broker holds {held:g} < pilot {p['qty']} "
                            "(sold outside the pilot?) — owner must check")

    # ------------------------------------------------------------ 4) protection
    def ensure_protection(self, out):
        for p in self.s["positions"]:
            if p["status"] != "open" or p["qty"] <= 0:
                continue
            st = self._order(p["stop_order_id"]) if p["stop_order_id"] else None
            ok = (st is not None and st["status"] in LIVE_STATUSES and st["instruction"] == "SELL"
                  and int(st["qty"]) == int(p["qty"]) and st["type"] == "STOP")
            if ok:
                p["protected"] = True
                continue
            p["protected"] = False
            held = float((self.snap["positions"].get(p["ticker"]) or {}).get("qty", 0))
            if held < p["qty"]:          # shares gone outside the pilot: never place a stop that
                self._block(f"{p['ticker']}: broker holds {held:g} < pilot {p['qty']} and no "
                            "live stop — owner must check (no stop placed)")   # could go short
                continue
            if st is not None and st["status"] in LIVE_STATUSES:   # wrong quantity: replace
                try:
                    self.b.cancel(st["id"])
                    p["old_stop_ids"].append(st["id"])
                except (OrderRejected, SendUnknown) as e:
                    self._alert("Pilot: cannot replace stop", f"{p['ticker']}: {e}")
                    continue
            if p["stop_attempts"] >= STOP_ATTEMPTS:
                self._block(f"PROTECTION FAILED: {p['ticker']} {p['qty']} sh without a broker "
                            f"stop after {STOP_ATTEMPTS} attempts — set a stop manually")
                continue
            p["stop_attempts"] += 1
            try:
                oid = self.b.place(stop_sell(p["ticker"], p["qty"], p["stop_price"]))
                if p["stop_order_id"]:
                    p["old_stop_ids"].append(p["stop_order_id"])
                p["stop_order_id"] = oid
                self._persist()
                st = self.b.get_order(oid)
                if st["status"] in LIVE_STATUSES and int(st["qty"]) == int(p["qty"]):
                    p["protected"], p["stop_attempts"] = True, 0
                    out["actions"].append(f"{p['ticker']}: stop {p['stop_price']} x {p['qty']} "
                                          f"at broker ({oid})")
                else:
                    self._alert("Pilot: stop not active", f"{p['ticker']}: {st['status']}")
            except (OrderRejected, SendUnknown, BrokerUnavailable) as e:
                self._alert("Pilot: stop placement failed",
                            f"{p['ticker']} attempt {p['stop_attempts']}: {e}")
                if p["stop_attempts"] >= STOP_ATTEMPTS:
                    self._block(f"PROTECTION FAILED: {p['ticker']} {p['qty']} sh without a broker "
                                "stop — set a stop manually")
        if any(not p.get("protected") for p in self.s["positions"] if p["status"] == "open"
               and p["qty"] > 0):
            self._block(self.s["blocked"] or "an open pilot position is not protected yet")
        elif self.s["blocked"] == "an open pilot position is not protected yet":
            self.s["blocked"] = None

    # ------------------------------------------------------------ 5) exits
    def request_exit(self, ticker, reason="owner"):
        for p in self.s["positions"]:
            if p["ticker"] == ticker and p["status"] == "open":
                p["status"], p["exit_reason"] = "closing", reason
                self._persist()
                return True
        return False

    def progress_exits(self, out):
        for p in [p for p in self.s["positions"] if p["status"] == "closing"]:
            if not p.get("exit_order_id"):          # a sell matched after an unknown result
                sold = [i for i in self.s["intents"] if i["side"] == "SELL"
                        and i.get("position") == p["id"] and i.get("order_id")
                        and i["status"] == "working"]
                if sold:
                    p["exit_order_id"] = sold[-1]["order_id"]
            if p.get("exit_order_id"):
                o = self._order(p["exit_order_id"])
                if o["status"] == "FILLED":
                    self._close(p, o["avg_price"], p.get("exit_reason", "owner"), o["id"])
                    out["actions"].append(f"{p['ticker']}: sold")
                elif o["status"] in ("REJECTED", "CANCELED", "EXPIRED"):
                    p["exit_order_id"], p["status"], p["stop_order_id"] = None, "open", None
                    self._alert("Pilot: exit failed", f"{p['ticker']}: {o['status']} — stop re-placed")
                    self.ensure_protection(out)
                continue
            if any(i["side"] == "SELL" and i.get("position") == p["id"] and i["status"] in
                   ("submitting", "unknown", "ambiguous", "not_found") for i in self.s["intents"]):
                continue                                       # sell result unknown: never resend
            st = self._order(p["stop_order_id"]) if p["stop_order_id"] else None
            if st is not None and st["status"] == "FILLED":
                self._close(p, st["avg_price"] or p["stop_price"], "stop", st["id"])
                continue
            if st is not None and st["status"] in LIVE_STATUSES:
                if st["status"] != "PENDING_CANCEL":
                    try:
                        self.b.cancel(st["id"])
                        out["actions"].append(f"{p['ticker']}: cancel stop {st['id']} before selling")
                    except (OrderRejected, SendUnknown) as e:
                        self._alert("Pilot: cannot cancel stop", f"{p['ticker']}: {e}")
                st = self.b.get_order(st["id"])
                if st["status"] == "FILLED":
                    self._close(p, st["avg_price"] or p["stop_price"], "stop", st["id"])
                    continue
                if st["status"] != "CANCELED":
                    continue                                   # confirm next run, never sell twice
            i = self._intent("SELL", p["ticker"], p["qty"], None, p["stop_price"],
                             market_sell(p["ticker"], p["qty"]), position=p["id"])
            oid = self._send(i)
            if oid:
                p["exit_order_id"] = oid
                o = self.b.get_order(oid)
                if o["status"] == "FILLED":
                    self._close(p, o["avg_price"], p.get("exit_reason", "owner"), oid)
                    out["actions"].append(f"{p['ticker']}: sold")
            elif i["status"] == "rejected":
                p["status"], p["stop_order_id"] = "open", None      # put protection back
                self._alert("Pilot: exit rejected", f"{p['ticker']}: stop re-placed")
                self.ensure_protection(out)

    def _close(self, p, px, reason, order_id):
        p.update(status="closed", exit=px, exit_reason=reason, closed=_iso(self.now()),
                 exit_fill_order_id=order_id,
                 pnl=(px - p["entry"]) * p["qty"] if px is not None and p["entry"] else None)
        self.s["positions"].remove(p)
        self.s["closed"].append(p)
        self._log(f"closed {p['ticker']} {reason} @ {px}")

    # ------------------------------------------------------------ 6) new entry
    def entry_blockers(self, a) -> list:
        why = []
        if not self.live:
            why.append("live mode is off")
        if not self.entries_enabled:
            why.append("new entries are switched off")
        if self.s["blocked"]:
            why.append(f"blocked: {self.s['blocked']}")
        if any(i["status"] in ("submitting", "unknown", "ambiguous", "not_found", "working")
               for i in self.s["intents"]):
            why.append("an earlier order is unresolved")
        if a.get("approval_id") in self.s["used_approvals"]:
            why.append("approval already used")
        if a.get("side", "BUY") != "BUY" or a.get("asset", "EQUITY") != "EQUITY":
            why.append("long equity only")
        exp = _ts(a.get("expires_at"))
        if exp is None or self.now() > exp:
            why.append("approval expired")
        if self.account_suffix and a.get("account_last4") and not str(
                self.snap["account_number"]).endswith(a["account_last4"]):
            why.append("approval is for another account")
        qty = int(a.get("qty", 0))
        if qty < 1 or qty != a.get("qty"):
            why.append("whole shares >= 1 only")
        if len([p for p in self.s["positions"] if p["status"] != "closed"]) >= MAX_POSITIONS:
            why.append(f"max {MAX_POSITIONS} pilot position")
        mq, mo = self.manual_activity(a["ticker"])
        if mq > 0 or a["ticker"] in self.snap["positions"]:
            why.append(f"{a['ticker']}: a position already exists at the broker (manual)")
        if mo:
            why.append(f"{a['ticker']}: {len(mo)} open order(s) not from the pilot")
        if not (float(a.get("stop_price", 0)) > 0):
            why.append("no stop price")
        return why

    def enter(self, a: dict) -> dict:
        why = self.entry_blockers(a)
        if why:
            return dict(sent=False, why=why)
        try:
            px = self.b.quote(a["ticker"])
        except BrokerUnavailable as e:
            return dict(sent=False, why=[f"no quote: {e}"])
        why = []
        if px is None or px > float(a["max_price"]):
            why.append(f"quote {px} above the approved max {a['max_price']}")
        if px is not None and not float(a["stop_price"]) < px:
            why.append("stop is not below the price")
        cost = (px or 0) * a["qty"] * (1 + PRICE_BUFFER)
        first = not self.s["closed"] and not self.s["positions"]
        if first and cost > FIRST_TRADE_MAX_USD:
            why.append(f"first trade ${cost:.2f} > ${FIRST_TRADE_MAX_USD:.0f}")
        if self.committed_usd() + cost > BUDGET_USD:
            why.append(f"budget: ${self.committed_usd() + cost:.2f} > ${BUDGET_USD:.0f}")
        cash = self.snap["balances"].get("cash_available")
        if cash is not None and cost > float(cash):
            why.append(f"cash available ${cash} < ${cost:.2f}")
        if why:
            return dict(sent=False, why=why)
        self.s["used_approvals"].append(a["approval_id"])
        i = self._intent("BUY", a["ticker"], a["qty"], px, a["stop_price"],
                         market_buy(a["ticker"], a["qty"]), approval_id=a["approval_id"])
        oid = self._send(i)
        return dict(sent=True, order_id=oid, status=i["status"], est_cost=round(cost, 2))

    # ------------------------------------------------------------ sending
    def _intent(self, side, ticker, qty, est, stop, order, **extra):
        i = dict(id=uuid.uuid4().hex[:12], side=side, ticker=ticker, qty=int(qty),
                 est_price=est or 0.0, stop_price=stop, order=order, status="submitting",
                 created=_iso(self.now()), sent=None, order_id=None, **extra)
        self.s["intents"].append(i)
        self._persist()                         # saved BEFORE the order leaves
        return i

    def _send(self, i):
        i["sent"] = _iso(self.now())
        try:
            oid = self.b.place(i["order"])
        except OrderRejected as e:
            i["status"], i["error"] = "rejected", str(e)
            self._log(f"{i['side']} {i['ticker']} rejected: {e}")
            self._persist()
            return None
        except SendUnknown as e:
            i["status"], i["error"] = "unknown", str(e)
            self._block(f"{i['side']} {i['ticker']} result unknown ({e}): reconciling, no resend")
            self._persist()
            return None
        except BrokerUnavailable as e:
            i["status"], i["error"] = "not_sent", str(e)
            self._persist()
            return None
        i["order_id"], i["status"] = str(oid), "working"
        self._persist()
        return str(oid)
