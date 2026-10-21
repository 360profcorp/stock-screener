"""Weekly Schwab re-login without copying the redirect address (pure logic, no Streamlit).

Flow
  1. The owner, in an UNLOCKED app session, presses "Renew Schwab connection". The browser
     gets a random browser secret in a short-lived cookie (BROWSER_COOKIE), and
     PendingStates.issue() creates a one-time `state` bound to that browser: only
     SHA-256(state) -> SHA-256(browser secret) is kept, valid STATE_TTL, single use.
  2. Schwab redirects back with ?code=...&state=... in a NEW app session of the same browser;
     the cookie comes with it (SameSite=Lax allows a top-level GET navigation).
  3. handle_callback() consumes the state ATOMICALLY and checks that the returning browser
     presents the same secret. Unknown, used, expired or foreign-browser states are rejected
     before Schwab is called; a state is burnt on the first attempt, whatever the outcome.
  4. The code is exchanged (it lives ~30 s), the token is saved encrypted into
     state/trader.enc through the GitHub API (the store Actions read) and success is reported
     ONLY after the save. The caller removes code/state from the address bar.

Nothing here logs or returns a key, code or token: results carry only short reasons.

Expiry: Schwab's refresh token lives 7 days from the login. due_notices() lists what should be
sent; a notice is recorded with mark_sent() ONLY after the notification service confirmed it,
so a failed delivery is retried by the next run.
"""
import hashlib
import hmac
import secrets as _secrets
import threading
import time
from urllib.parse import urlencode

from schwab_api import BASE, SchwabError, _basic

REFRESH_TTL = 7 * 24 * 3600
STATE_TTL = 600                     # seconds a pending login may take
BROWSER_COOKIE = "visar_sch_b"
WARN_AT = (("24h", 24 * 3600), ("2h", 2 * 3600))


def _h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def new_browser_secret() -> str:
    return _secrets.token_urlsafe(32)


class PendingStates:
    """One-time login states bound to the initiating browser. Shared by all sessions of the
    app process (st.cache_resource); a lock makes check-and-consume atomic."""

    def __init__(self):
        self._p = {}
        self._lock = threading.Lock()

    def issue(self, browser_secret: str, now=None) -> str:
        if not browser_secret:
            raise ValueError("a browser secret is required")
        now = time.time() if now is None else now
        s = _secrets.token_urlsafe(32)
        with self._lock:
            self._p = {k: v for k, v in self._p.items() if now - v["created"] < 2 * STATE_TTL}
            self._p[_h(s)] = dict(created=now, used=False, browser=_h(browser_secret))
        return s

    def consume(self, state: str, browser_secret: str, now=None) -> str:
        """'ok' | 'missing' | 'unknown' | 'used' | 'expired' | 'other_browser'. The state is
        burnt by the first attempt that names it, so a failed or foreign attempt cannot be
        followed by a retry with the same state."""
        now = time.time() if now is None else now
        if not state:
            return "missing"
        with self._lock:
            rec = self._p.get(_h(state))
            if rec is None:
                return "unknown"
            if rec["used"]:
                return "used"
            rec["used"] = True
            if now - rec["created"] > STATE_TTL:
                return "expired"
            if not browser_secret or not hmac.compare_digest(rec["browser"], _h(browser_secret)):
                return "other_browser"
            return "ok"


def login_url(app_key: str, callback: str, state: str) -> str:
    return f"{BASE}/v1/oauth/authorize?" + urlencode(
        {"client_id": app_key, "redirect_uri": callback, "state": state})


# ---------------------------------------------------------------- Schwab error classes
TOKEN_REFUSED = {"invalid_grant", "refresh_token_authentication_error", "expired_token"}
CLIENT_ERRORS = {"invalid_client", "unauthorized_client"}


def classify(status_code: int, body) -> str:
    """'token_refused' | 'client_or_token' | 'temporary' | 'other'.
    invalid_client is NOT proof of a revoked login: it is also what Schwab answers when the
    app key/secret are wrong or missing (seen on 2026-10-21), so it is its own class."""
    err = ""
    try:
        err = str((body or {}).get("error", "")).strip().lower()
    except Exception:
        pass
    if status_code >= 500 or status_code == 429:
        return "temporary"
    if err in TOKEN_REFUSED:
        return "token_refused"
    if err in CLIENT_ERRORS:
        return "client_or_token"
    return "other"


def _body(r):
    try:
        return r.json()
    except Exception:
        return {}


def exchange(app_key, secret, code, callback, http, now=None) -> dict:
    """Authorization code -> token dict. Raises SchwabError with a reason, never the code."""
    now = time.time() if now is None else now
    try:
        r = http.post(f"{BASE}/v1/oauth/token",
                      headers={"Authorization": _basic(app_key, secret),
                               "Content-Type": "application/x-www-form-urlencoded"},
                      data={"grant_type": "authorization_code", "code": code,
                            "redirect_uri": callback}, timeout=20)
    except Exception as e:
        raise SchwabError(f"network error during the exchange ({type(e).__name__}) — retry")
    if r.status_code != 200:
        b = _body(r)
        c = classify(r.status_code, b)
        err = str(b.get("error", ""))[:40] if isinstance(b, dict) else ""
        if c == "client_or_token":
            raise SchwabError(f"Schwab refused the app credentials or the callback "
                              f"({r.status_code} {err}): check SCHWAB_APP_KEY / SECRET and that "
                              "the callback URL matches the Developer Portal exactly")
        if c == "temporary":
            raise SchwabError(f"Schwab is temporarily unavailable ({r.status_code}) — retry")
        raise SchwabError(f"the login code was rejected or expired ({r.status_code} {err}) — "
                          "press the renew button again")
    t = r.json()
    return {"access_token": t["access_token"], "refresh_token": t["refresh_token"],
            "access_expires": now + int(t.get("expires_in", 1800)) - 60,
            "refresh_created": now}


def handle_callback(params: dict, browser_secret: str, pending: PendingStates, exchange_fn,
                    save_fn, now=None) -> dict:
    """params: the page's query parameters; browser_secret: the returning browser's cookie.
    exchange_fn(code) -> token; save_fn(token) raises on failure. Returns dict(ok, reason,
    step) — never a secret."""
    code, state = params.get("code"), params.get("state")
    if not code and not state:
        return dict(ok=None, reason="no callback", step="none")
    if not code:
        err = params.get("error", "")
        if state:
            pending.consume(state, browser_secret, now)        # burn it
        return dict(ok=False, reason=f"Schwab returned no code {str(err)[:40]}".strip(),
                    step="params")
    v = pending.consume(state, browser_secret, now)
    if v != "ok":
        why = {"other_browser": "this browser did not start the renewal",
               "used": "this login link was already used",
               "expired": "the login link expired (10 min)",
               "unknown": "unknown login link (or the app restarted)",
               "missing": "no login state"}.get(v, v)
        return dict(ok=False, reason=f"{why}: start the renewal again from the app",
                    step="state", state_check=v)
    try:
        token = exchange_fn(code)
    except SchwabError as e:
        return dict(ok=False, reason=str(e)[:200], step="exchange")
    try:
        save_fn(token)
    except Exception as e:
        return dict(ok=False, reason=f"the new login was NOT saved ({type(e).__name__}: "
                                     f"{str(e)[:80]}) — renew again", step="save")
    return dict(ok=True, reason="saved", step="done",
                expires_at=token["refresh_created"] + REFRESH_TTL)


# ---------------------------------------------------------------- expiry and refresh check
def status(token: dict | None, now=None) -> dict:
    now = time.time() if now is None else now
    if not token or not token.get("refresh_created"):
        return dict(state="none", seconds_left=None, expires_at=None)
    exp = float(token["refresh_created"]) + REFRESH_TTL
    left = exp - now
    st = "expired" if left <= 0 else "expiring" if left <= WARN_AT[0][1] else "ok"
    return dict(state=st, seconds_left=left, expires_at=exp)


def check_refresh(app_key, secret, token, http) -> str:
    """'ok' | 'token_refused' | 'client_or_token' | 'temporary' | 'other'.
    Only the token endpoint is called; the saved token is not changed."""
    try:
        r = http.post(f"{BASE}/v1/oauth/token",
                      headers={"Authorization": _basic(app_key, secret),
                               "Content-Type": "application/x-www-form-urlencoded"},
                      data={"grant_type": "refresh_token",
                            "refresh_token": token["refresh_token"]}, timeout=20)
    except Exception:
        return "temporary"
    if r.status_code == 200:
        return "ok"
    return classify(r.status_code, _body(r))


# refresh result -> notice name; 'temporary' / 'other' send nothing (retried next run)
REFRESH_NOTICE = {"token_refused": "revoked", "client_or_token": "client"}


def login_key(token) -> str:
    return str(int(float(token["refresh_created"])))


def due_notices(token, sent: dict, now=None, refresh_result=None) -> list:
    """Notices due now and not yet DELIVERED for this login (does not mark anything)."""
    s = status(token, now)
    if s["state"] == "none":
        return []
    done = set((sent or {}).get(login_key(token), []))
    if s["state"] == "expired":
        names = ["expired"]
    else:
        names = [n for n, sec in WARN_AT if s["seconds_left"] <= sec]
        if refresh_result in REFRESH_NOTICE:
            names.append(REFRESH_NOTICE[refresh_result])
    return [n for n in names if n not in done]


def mark_sent(token, sent: dict, name: str):
    """Record a DELIVERED notice; only the current login is kept. After the expiry notice the
    warnings are recorded too (they would be stale)."""
    k = login_key(token)
    for old in [x for x in sent if x != k]:
        sent.pop(old)
    done = sent.setdefault(k, [])
    for n in [name] + ([w for w, _ in WARN_AT] if name == "expired" else []):
        if n not in done:
            done.append(n)


def send_ntfy(topic, title, text, http, timeout=20) -> bool:
    """True only if ntfy confirmed the notification (2xx)."""
    if not topic:
        return False
    try:
        r = http.post(f"https://ntfy.sh/{topic}", data=text.encode("utf-8"),
                      headers={"Title": title.encode("utf-8"), "Tags": "warning"},
                      timeout=timeout)
    except Exception:
        return False
    return 200 <= int(getattr(r, "status_code", 0)) < 300


TEXT = {
    "24h": ("VISAR: вход в Schwab истекает через 24 ч",
            "Открой сканер → «Торговля» → «Продлить подключение Schwab»."),
    "2h": ("VISAR: вход в Schwab истекает через 2 ч",
           "Продли сейчас: сканер → «Торговля» → «Продлить подключение Schwab». После "
           "истечения новые входы блокируются."),
    "expired": ("VISAR: вход в Schwab истёк",
                "Новые входы заблокированы. Защитные стопы у Schwab не отменяются и работают. "
                "Продли подключение; после входа бот сначала сверит позиции и заявки."),
    "revoked": ("VISAR: Schwab отклонил вход досрочно",
                "Schwab не принял сохранённый вход раньше 7 дней (вход отозван или изменён в "
                "Schwab). Новые входы заблокированы, стопы у Schwab остаются. Войди заново."),
    "client": ("VISAR: Schwab не принял ключи приложения",
               "Ответ invalid_client: проверь SCHWAB_APP_KEY / SCHWAB_APP_SECRET в GitHub "
               "Secrets и статус приложения в Schwab Developer Portal; если ключи верны — войди "
               "заново. Новые входы заблокированы, стопы у Schwab остаются."),
}
