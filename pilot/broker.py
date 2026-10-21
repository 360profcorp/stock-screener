"""Schwab adapter for the real-money pilot (no order is sent by this module on its own).

Normalises Schwab order JSON and classifies every outcome of an order submission into one of
three cases, because the pilot must never send a second buy after an unknown result:

  OrderRejected  Schwab answered 4xx: the order was NOT accepted (safe, nothing to reconcile)
  SendUnknown    timeout / connection drop / 5xx / 2xx without an order id: the order MAY
                 exist. The engine reconciles against the broker's order list; it never resends.
  BrokerUnavailable  the request could not even start (login expired, refresh failed):
                 nothing was sent.

ReadOnlyHTTP wraps `requests` so that only GET calls and the OAuth token refresh can pass:
the read-only check uses it, so it cannot place, replace or cancel anything even by mistake.
"""
import time

import requests

from schwab_api import BASE, Schwab, SchwabError, from_schwab, to_schwab

LIVE_STATUSES = {"WORKING", "PENDING_ACTIVATION", "QUEUED", "ACCEPTED", "AWAITING_PARENT_ORDER",
                 "AWAITING_CONDITION", "AWAITING_STOP_CONDITION", "AWAITING_MANUAL_REVIEW",
                 "AWAITING_RELEASE_TIME", "PENDING_ACKNOWLEDGEMENT", "NEW", "PENDING_REPLACE",
                 "PENDING_CANCEL", "PENDING_RECALL", "AWAITING_UR_OUT"}
TERMINAL = {"FILLED", "CANCELED", "REJECTED", "EXPIRED", "REPLACED"}


class BrokerUnavailable(Exception):
    pass


class SendUnknown(Exception):
    pass


class OrderRejected(Exception):
    def __init__(self, msg, retryable=False):
        super().__init__(msg)
        self.retryable = retryable


class ReadOnlyViolation(RuntimeError):
    pass


class ReadOnlyHTTP:
    """`requests`-compatible object that refuses anything but GET (and the token refresh)."""
    def __init__(self, http=requests):
        self.http = http
        self.calls = []

    def request(self, method, url, **kw):
        if method.upper() != "GET":
            raise ReadOnlyViolation(f"read-only: {method} {url.split('?')[0]} refused")
        self.calls.append(("GET", url.replace(BASE, "")))
        return self.http.request(method, url, **kw)

    def post(self, url, **kw):
        if not url.endswith("/v1/oauth/token"):
            raise ReadOnlyViolation(f"read-only: POST {url} refused")
        self.calls.append(("POST", "/v1/oauth/token"))
        return self.http.post(url, **kw)


# ---------------------------------------------------------------- normalisation
def norm_order(o: dict, parent=None) -> list:
    """Flatten one Schwab order (with child strategies) into normalised dicts."""
    legs = o.get("orderLegCollection") or [{}]
    leg = legs[0]
    ex = [e for a in o.get("orderActivityCollection", []) or []
          for e in a.get("executionLegs", []) or []]
    q = sum(float(e.get("quantity", 0)) for e in ex)
    avg = sum(float(e.get("quantity", 0)) * float(e.get("price", 0)) for e in ex) / q if q else None
    out = [dict(id=str(o.get("orderId", "")), parent=parent, status=o.get("status", "UNKNOWN"),
                symbol=from_schwab(leg.get("instrument", {}).get("symbol", "")),
                instruction=leg.get("instruction"), type=o.get("orderType"),
                duration=o.get("duration"), qty=float(o.get("quantity", leg.get("quantity", 0))),
                filled=float(o.get("filledQuantity", q) or 0),
                remaining=float(o.get("remainingQuantity", 0) or 0),
                stop_price=o.get("stopPrice"), entered=o.get("enteredTime"),
                closed=o.get("closeTime"), avg_price=avg,
                legs=len(o.get("orderLegCollection") or []),
                strategy=o.get("orderStrategyType"))]
    for ch in o.get("childOrderStrategies", []) or []:
        out += norm_order(ch, parent=out[0]["id"])
    return out


def market_buy(ticker, qty):
    return {"orderType": "MARKET", "session": "NORMAL", "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [{"instruction": "BUY", "quantity": int(qty),
                                    "instrument": {"symbol": to_schwab(ticker),
                                                   "assetType": "EQUITY"}}]}


def market_sell(ticker, qty):
    o = market_buy(ticker, qty)
    o["orderLegCollection"][0]["instruction"] = "SELL"
    return o


def stop_sell(ticker, qty, stop):
    return {"orderType": "STOP", "session": "NORMAL", "duration": "GOOD_TILL_CANCEL",
            "stopPrice": round(float(stop), 2), "orderStrategyType": "SINGLE",
            "orderLegCollection": [{"instruction": "SELL", "quantity": int(qty),
                                    "instrument": {"symbol": to_schwab(ticker),
                                                   "assetType": "EQUITY"}}]}


# ---------------------------------------------------------------- adapter
class SchwabPilotBroker:
    """Thin layer over schwab_api.Schwab. Every call is classified (see module doc)."""

    def __init__(self, client: Schwab):
        self.c = client

    def _get(self, path, **kw):
        try:
            return self.c._req("GET", path, **kw).json()
        except SchwabError as e:
            raise BrokerUnavailable(str(e)[:200])
        except (requests.Timeout, requests.ConnectionError) as e:
            raise BrokerUnavailable(f"network: {type(e).__name__}")

    def account_numbers(self):
        return self._get("/trader/v1/accounts/accountNumbers")

    def snapshot(self, days=7) -> dict:
        h = self._account_hash()
        acct = self._get(f"/trader/v1/accounts/{h}", params={"fields": "positions"})
        a = acct.get("securitiesAccount", acct)
        pos = {}
        for p in a.get("positions", []) or []:
            ins = p.get("instrument", {})
            q = float(p.get("longQuantity", 0)) - float(p.get("shortQuantity", 0))
            if q:
                pos[from_schwab(ins.get("symbol", ""))] = dict(
                    qty=q, asset=ins.get("assetType"), avg=p.get("averagePrice"))
        frm = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(time.time() - days * 86400))
        to = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(time.time() + 60))
        raw = self._get(f"/trader/v1/accounts/{h}/orders",
                        params={"fromEnteredTime": frm, "toEnteredTime": to})
        orders = [n for o in raw for n in norm_order(o)]
        cb = a.get("currentBalances", {}) or {}
        return dict(account_number=str(a.get("accountNumber", "")), type=a.get("type"),
                    positions=pos, orders=orders,
                    balances=dict(cash=cb.get("cashBalance"),
                                  cash_available=cb.get("cashAvailableForTrading"),
                                  buying_power=cb.get("buyingPower"),
                                  liquidation_value=cb.get("liquidationValue")),
                    flags=dict(is_day_trader=a.get("isDayTrader"),
                               closing_only=a.get("isClosingOnlyRestricted"),
                               round_trips=a.get("roundTrips"), pfcb=a.get("pfcbFlag")))

    def _account_hash(self):
        try:
            return self.c.account_hash()
        except SchwabError as e:
            raise BrokerUnavailable(str(e)[:200])
        except (requests.Timeout, requests.ConnectionError) as e:
            raise BrokerUnavailable(f"network: {type(e).__name__}")

    def get_order(self, order_id) -> dict:
        h = self._account_hash()
        return norm_order(self._get(f"/trader/v1/accounts/{h}/orders/{order_id}"))[0]

    def quote(self, ticker) -> float:
        try:
            return self.c.quotes([ticker]).get(ticker)
        except SchwabError as e:
            raise BrokerUnavailable(str(e)[:200])

    def place(self, order: dict) -> str:
        h = self._account_hash()
        try:
            tok = self.c._access()
        except SchwabError as e:
            raise BrokerUnavailable(str(e)[:200])
        try:
            r = self.c.http.request("POST", f"{BASE}/trader/v1/accounts/{h}/orders", timeout=20,
                                    headers={"Authorization": f"Bearer {tok}",
                                             "Accept": "application/json"}, json=order)
        except (requests.Timeout, requests.ConnectionError) as e:
            raise SendUnknown(f"{type(e).__name__} after sending")
        if r.status_code == 429:
            raise OrderRejected("rate limited (429)", retryable=True)
        if 400 <= r.status_code < 500:
            raise OrderRejected(f"{r.status_code}: {r.text[:200]}")
        if r.status_code >= 500:
            raise SendUnknown(f"server error {r.status_code}")
        loc = r.headers.get("Location", "")
        oid = loc.rstrip("/").split("/")[-1] if loc else ""
        if not oid:
            raise SendUnknown(f"{r.status_code} without an order id")
        return oid

    def cancel(self, order_id):
        h = self._account_hash()
        try:
            self.c._req("DELETE", f"/trader/v1/accounts/{h}/orders/{order_id}")
        except SchwabError as e:
            raise OrderRejected(str(e)[:200])
        except (requests.Timeout, requests.ConnectionError) as e:
            raise SendUnknown(f"cancel: {type(e).__name__}")
