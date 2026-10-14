"""
Minimal Charles Schwab Trader API client (Trader API – Individual).

Auth (OAuth 2.0):
  • auth_url()       → you open it, log in to Schwab, approve; Schwab redirects to
                       https://127.0.0.1/?code=...  (the page won't load — that's normal)
  • exchange_code()  → the app turns that redirect URL into tokens (do it within ~30 s)
  • refresh token lives 7 days → log in again once a week (the bot reminds you by push)
  • access token lives 30 min → refreshed automatically on every run

Orders:
  • buy_with_stop()  → one TRIGGER order: market BUY, and once it fills Schwab itself
                       places a GTC STOP SELL. The stop sits at the broker, so it works
                       even if the bot or GitHub is down.
"""
import base64
import time
from urllib.parse import parse_qs, unquote, urlparse

import requests

BASE = "https://api.schwabapi.com"
CALLBACK = "https://127.0.0.1"
REFRESH_TTL = 7 * 24 * 3600          # Schwab refresh token lifetime
ACCESS_TTL = 30 * 60


class SchwabError(Exception):
    pass


def to_schwab(ticker: str) -> str:            # BRK-B (Yahoo) → BRK/B (Schwab)
    return ticker.replace("-", "/").upper()


def from_schwab(symbol: str) -> str:
    return symbol.replace("/", "-").upper()


def auth_url(app_key: str, callback: str = CALLBACK) -> str:
    return f"{BASE}/v1/oauth/authorize?client_id={app_key}&redirect_uri={callback}"


def _basic(app_key, secret):
    return "Basic " + base64.b64encode(f"{app_key}:{secret}".encode()).decode()


def extract_code(redirect_url_or_code: str) -> str:
    s = redirect_url_or_code.strip()
    if "code=" in s:
        q = parse_qs(urlparse(s).query)
        s = q.get("code", [s.split("code=")[1].split("&")[0]])[0]
    return unquote(s)                                       # "...%40" → "...@"


def exchange_code(app_key, secret, redirect_url_or_code, callback=CALLBACK, http=requests):
    r = http.post(f"{BASE}/v1/oauth/token",
                  headers={"Authorization": _basic(app_key, secret),
                           "Content-Type": "application/x-www-form-urlencoded"},
                  data={"grant_type": "authorization_code",
                        "code": extract_code(redirect_url_or_code),
                        "redirect_uri": callback}, timeout=20)
    if r.status_code != 200:
        raise SchwabError(f"token exchange failed ({r.status_code}): {r.text[:200]}")
    t = r.json()
    now = time.time()
    return {"access_token": t["access_token"], "refresh_token": t["refresh_token"],
            "access_expires": now + int(t.get("expires_in", ACCESS_TTL)) - 60,
            "refresh_created": now}


def refresh_age_days(token: dict | None) -> float | None:
    if not token or not token.get("refresh_created"):
        return None
    return (time.time() - token["refresh_created"]) / 86400


class Schwab:
    def __init__(self, app_key, secret, token: dict, account_suffix: str = "", http=requests):
        if not token or not token.get("refresh_token"):
            raise SchwabError("Schwab is not connected — log in from the app (Trading tab)")
        self.app_key, self.secret, self.token = app_key, secret, token
        self.account_suffix = (account_suffix or "").strip()
        self.http = http
        self._hash = None

    # ---------- auth ----------
    def _access(self):
        if time.time() < self.token.get("access_expires", 0):
            return self.token["access_token"]
        if (refresh_age_days(self.token) or 99) >= 7:
            raise SchwabError("Schwab login expired (7 days) — log in again from the app")
        r = self.http.post(f"{BASE}/v1/oauth/token",
                           headers={"Authorization": _basic(self.app_key, self.secret),
                                    "Content-Type": "application/x-www-form-urlencoded"},
                           data={"grant_type": "refresh_token",
                                 "refresh_token": self.token["refresh_token"]}, timeout=20)
        if r.status_code != 200:
            raise SchwabError(f"token refresh failed ({r.status_code}): {r.text[:200]}")
        t = r.json()
        self.token["access_token"] = t["access_token"]
        self.token["access_expires"] = time.time() + int(t.get("expires_in", ACCESS_TTL)) - 60
        if t.get("refresh_token") and t["refresh_token"] != self.token["refresh_token"]:
            self.token["refresh_token"] = t["refresh_token"]       # keep the creation time
        return self.token["access_token"]

    def _req(self, method, path, **kw):
        r = self.http.request(method, BASE + path, timeout=20,
                              headers={"Authorization": f"Bearer {self._access()}",
                                       "Accept": "application/json"}, **kw)
        if r.status_code >= 400:
            raise SchwabError(f"{method} {path} → {r.status_code}: {r.text[:300]}")
        return r

    # ---------- account ----------
    def account_hash(self):
        if self._hash:
            return self._hash
        accts = self._req("GET", "/trader/v1/accounts/accountNumbers").json()
        if self.account_suffix:
            accts = [a for a in accts if str(a["accountNumber"]).endswith(self.account_suffix)]
        if len(accts) != 1:
            raise SchwabError(f"found {len(accts)} matching accounts — set SCHWAB_ACCOUNT "
                              "to the last digits of the bot's account")
        self._hash = accts[0]["hashValue"]
        return self._hash

    def account(self):
        j = self._req("GET", f"/trader/v1/accounts/{self.account_hash()}",
                      params={"fields": "positions"}).json()
        return j.get("securitiesAccount", j)

    def positions(self) -> dict:
        out = {}
        for p in self.account().get("positions", []) or []:
            ins = p.get("instrument", {})
            if ins.get("assetType") == "EQUITY":
                q = float(p.get("longQuantity", 0)) - float(p.get("shortQuantity", 0))
                if q:
                    out[from_schwab(ins["symbol"])] = q
        return out

    def quotes(self, tickers) -> dict:
        if not tickers:
            return {}
        j = self._req("GET", "/marketdata/v1/quotes",
                      params={"symbols": ",".join(to_schwab(t) for t in tickers),
                              "fields": "quote"}).json()
        out = {}
        for sym, v in j.items():
            q = v.get("quote", {})
            px = q.get("lastPrice") or q.get("mark") or q.get("closePrice")
            if px:
                out[from_schwab(sym)] = float(px)
        return out

    # ---------- orders ----------
    @staticmethod
    def _leg(instruction, ticker, qty):
        return [{"instruction": instruction, "quantity": int(qty),
                 "instrument": {"symbol": to_schwab(ticker), "assetType": "EQUITY"}}]

    def _place(self, order) -> str:
        r = self._req("POST", f"/trader/v1/accounts/{self.account_hash()}/orders", json=order)
        loc = r.headers.get("Location", "")
        return loc.rstrip("/").split("/")[-1] if loc else ""

    def buy_with_stop(self, ticker, qty, stop) -> str:
        order = {
            "orderType": "MARKET", "session": "NORMAL", "duration": "DAY",
            "orderStrategyType": "TRIGGER",
            "orderLegCollection": self._leg("BUY", ticker, qty),
            "childOrderStrategies": [{
                "orderType": "STOP", "session": "NORMAL", "duration": "GOOD_TILL_CANCEL",
                "stopPrice": round(float(stop), 2), "orderStrategyType": "SINGLE",
                "orderLegCollection": self._leg("SELL", ticker, qty)}],
        }
        return self._place(order)

    def sell_market(self, ticker, qty) -> str:
        return self._place({"orderType": "MARKET", "session": "NORMAL", "duration": "DAY",
                            "orderStrategyType": "SINGLE",
                            "orderLegCollection": self._leg("SELL", ticker, qty)})

    def orders(self, days=60):
        now = time.gmtime()
        frm = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(time.time() - days * 86400))
        to = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", now)
        return self._req("GET", f"/trader/v1/accounts/{self.account_hash()}/orders",
                         params={"fromEnteredTime": frm, "toEnteredTime": to}).json()

    def open_sell_orders(self, ticker):
        sym, ids = to_schwab(ticker), []
        live = {"WORKING", "PENDING_ACTIVATION", "QUEUED", "ACCEPTED", "AWAITING_PARENT_ORDER",
                "AWAITING_CONDITION", "AWAITING_STOP_CONDITION", "NEW"}

        def walk(o):
            for leg in o.get("orderLegCollection", []):
                if (leg.get("instruction") == "SELL" and leg["instrument"]["symbol"] == sym
                        and o.get("status") in live):
                    ids.append(str(o["orderId"]))
            for ch in o.get("childOrderStrategies", []) or []:
                walk(ch)
        for o in self.orders():
            walk(o)
        return ids

    def cancel(self, order_id):
        self._req("DELETE", f"/trader/v1/accounts/{self.account_hash()}/orders/{order_id}")

    def last_fill(self, ticker, instruction="SELL", since_ts=0.0):
        """Average fill price of the latest filled order for ticker (best effort)."""
        sym, best = to_schwab(ticker), None

        def walk(o):
            nonlocal best
            legs = o.get("orderLegCollection", [])
            if (o.get("status") == "FILLED" and legs and legs[0].get("instruction") == instruction
                    and legs[0]["instrument"]["symbol"] == sym):
                px = [e["price"] for a in o.get("orderActivityCollection", []) or []
                      for e in a.get("executionLegs", []) or [] if "price" in e]
                if px:
                    best = (o.get("closeTime", ""), sum(px) / len(px))
            for ch in o.get("childOrderStrategies", []) or []:
                walk(ch)
        for o in self.orders():
            walk(o)
        return best[1] if best else None
