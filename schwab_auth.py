"""Weekly Schwab re-login without copying the redirect address (pure logic, no Streamlit).

Flow
  1. The owner, in an UNLOCKED app session, presses "Renew Schwab connection".
     PendingStates.issue() creates a one-time random `state` (only its SHA-256 is kept, with a
     10-minute expiry) and the button opens Schwab's login with that state and our HTTPS
     callback (the app's own address, registered in the Schwab Developer Portal).
  2. Schwab redirects back to the app with ?code=...&state=... (a new browser session).
     handle_callback() checks and CONSUMES the state before anything else: unknown, used or
     expired states are rejected, so a replayed or foreign callback never reaches Schwab.
  3. The code is exchanged (it lives ~30 s, so this happens on the first page load, before
     any password prompt), the token is saved encrypted into state/trader.enc through the
     GitHub API (the store Actions read) and success is reported ONLY after the save.
  4. The caller removes code/state from the address bar.

Nothing here logs or returns a key, code or token: results carry only short reasons.

Expiry: Schwab's refresh token lives 7 days from the login (cannot be extended). notices()
decides the 24 h / 2 h warnings, the expiry notice and an early-revocation notice, each at most
once per login (keyed by the login time).
"""
import hashlib
import secrets as _secrets
import time
from urllib.parse import urlencode

from schwab_api import BASE, SchwabError, _basic

REFRESH_TTL = 7 * 24 * 3600
STATE_TTL = 600                     # seconds a pending login may take
WARN_AT = (("24h", 24 * 3600), ("2h", 2 * 3600))


def _h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


class PendingStates:
    """One-time login states. Only hashes are stored. Shared by all sessions of the app
    process (st.cache_resource), because Schwab's redirect opens a new browser session."""

    def __init__(self):
        self._p = {}

    def issue(self, now=None) -> str:
        now = time.time() if now is None else now
        self._p = {k: v for k, v in self._p.items() if now - v["created"] < 2 * STATE_TTL}
        s = _secrets.token_urlsafe(32)
        self._p[_h(s)] = dict(created=now, used=False)
        return s

    def consume(self, state: str, now=None) -> str:
        """'ok' (and marks it used) | 'missing' | 'unknown' | 'used' | 'expired'."""
        now = time.time() if now is None else now
        if not state:
            return "missing"
        rec = self._p.get(_h(state))
        if rec is None:
            return "unknown"
        if rec["used"]:
            return "used"
        rec["used"] = True                       # single use, even if it then fails
        if now - rec["created"] > STATE_TTL:
            return "expired"
        return "ok"


def login_url(app_key: str, callback: str, state: str) -> str:
    return f"{BASE}/v1/oauth/authorize?" + urlencode(
        {"client_id": app_key, "redirect_uri": callback, "state": state})


def exchange(app_key, secret, code, callback, http, now=None) -> dict:
    """Authorization code -> token dict. Raises SchwabError with a reason, never the code."""
    now = time.time() if now is None else now
    try:
        r = http.post(f"{BASE}/v1/oauth/token",
                      headers={"Authorization": _basic(app_key, secret),
                               "Content-Type": "application/x-www-form-urlencoded"},
                      data={"grant_type": "authorization_code", "code": code,
                            "redirect_uri": callback}, timeout=20)
    except Exception as e:                       # network: no response details
        raise SchwabError(f"network error during the exchange ({type(e).__name__})")
    if r.status_code != 200:
        err = ""
        try:
            err = str(r.json().get("error", ""))[:40]
        except Exception:
            pass
        if r.status_code in (400, 401) and err in ("invalid_grant", "invalid_request", ""):
            raise SchwabError(f"the login code was rejected or expired ({r.status_code} {err})")
        raise SchwabError(f"token exchange failed ({r.status_code} {err})")
    t = r.json()
    return {"access_token": t["access_token"], "refresh_token": t["refresh_token"],
            "access_expires": now + int(t.get("expires_in", 1800)) - 60,
            "refresh_created": now}


def handle_callback(params: dict, pending: PendingStates, exchange_fn, save_fn,
                    now=None) -> dict:
    """params: the page's query parameters. exchange_fn(code) -> token; save_fn(token) ->
    raises on failure. Returns dict(ok, reason, step) — never a secret."""
    code, state = params.get("code"), params.get("state")
    if not code and not state:
        return dict(ok=None, reason="no callback", step="none")
    if not code:
        err = params.get("error", "")
        return dict(ok=False, reason=f"Schwab returned no code {str(err)[:40]}".strip(),
                    step="params")
    v = pending.consume(state, now)
    if v != "ok":
        return dict(ok=False, reason=f"login state {v}: start the renewal again from the app",
                    step="state")
    try:
        token = exchange_fn(code)
    except SchwabError as e:
        return dict(ok=False, reason=str(e)[:160], step="exchange")
    try:
        save_fn(token)
    except Exception as e:
        return dict(ok=False, reason=f"the new login was NOT saved ({type(e).__name__}: "
                                     f"{str(e)[:80]}) — renew again", step="save")
    return dict(ok=True, reason="saved", step="done",
                expires_at=token["refresh_created"] + REFRESH_TTL)


# ---------------------------------------------------------------- expiry
def status(token: dict | None, now=None) -> dict:
    now = time.time() if now is None else now
    if not token or not token.get("refresh_created"):
        return dict(state="none", seconds_left=None, expires_at=None)
    exp = float(token["refresh_created"]) + REFRESH_TTL
    left = exp - now
    st = "expired" if left <= 0 else "expiring" if left <= WARN_AT[0][1] else "ok"
    return dict(state=st, seconds_left=left, expires_at=exp)


def check_refresh(app_key, secret, token, http) -> str:
    """'ok' | 'revoked' (refused although inside the 7 days) | 'error: ...'. Does not change
    the token; only the token endpoint is called."""
    try:
        r = http.post(f"{BASE}/v1/oauth/token",
                      headers={"Authorization": _basic(app_key, secret),
                               "Content-Type": "application/x-www-form-urlencoded"},
                      data={"grant_type": "refresh_token",
                            "refresh_token": token["refresh_token"]}, timeout=20)
    except Exception as e:
        return f"error: network ({type(e).__name__})"
    if r.status_code == 200:
        return "ok"
    if r.status_code in (400, 401):
        return "revoked"
    return f"error: {r.status_code}"


def notices(token, sent: dict, now=None, refresh_result=None) -> list:
    """Notices due now, each at most once per login. `sent` is updated in place:
    {login_key: [names...]}. refresh_result: result of check_refresh() if it ran."""
    s = status(token, now)
    if s["state"] == "none":
        return []
    key = str(int(float(token["refresh_created"])))
    done = sent.setdefault(key, [])
    for k in [k for k in sent if k != key]:      # keep only the current login
        sent.pop(k)
    out = []
    if s["state"] == "expired":
        names = ["expired"]
    else:
        names = [n for n, sec in WARN_AT if s["seconds_left"] <= sec]
        if refresh_result == "revoked":
            names.append("revoked")
    for n in names:
        if n not in done:
            done.append(n)
            out.append(n)
    if "expired" in out:                         # the warnings would be stale now
        for n, _ in WARN_AT:
            if n not in done:
                done.append(n)
    return out


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
                "Schwab отказал в обновлении доступа раньше 7 дней (вход отозван или изменён "
                "в Schwab). Новые входы заблокированы, стопы у Schwab остаются. Войди заново."),
}
