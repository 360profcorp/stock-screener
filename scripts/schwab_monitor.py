"""Schwab login monitor (GitHub Actions, every 30 min). Places, changes and cancels NO order.

Reads state/trader.enc (the same store the bot and the app use), and:
  - if the login is inside its 7 days and the app key/secret are set, calls ONLY the OAuth
    token endpoint to see whether Schwab still accepts the login (early revocation);
  - sends each notice once per login (24 h / 2 h left, expired, login refused early, app
    credentials refused); recorded only after ntfy confirmed delivery, otherwise retried;
  - records state["schwab_auth"] (login key, blocked reason) so the bot blocks new
    entries; nothing is cancelled, stops already at Schwab stay.
Writes state/trader.enc only when a flag or notice changed (not on every run); the workflow saves it with the usual
3-way merge (scripts/save_trader_state.py). Prints no key, code or token.
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests  # noqa: E402

import schwab_auth as A  # noqa: E402
import vault  # noqa: E402


def run(state: dict, app_key: str, secret: str, push, http=requests, now=None) -> dict:
    """push(title, text) -> True only when the notification service confirmed delivery.
    A notice is recorded only after that, so a failed delivery is retried next run."""
    now = time.time() if now is None else now
    tok = state.get("token")
    s = A.status(tok, now)
    rep = dict(status=s["state"], hours_left=None if s["seconds_left"] is None
               else round(s["seconds_left"] / 3600, 1), refresh=None, sent=[], failed=[])
    if s["state"] == "none":
        return rep
    login = A.login_key(tok)
    if s["state"] != "expired":
        rep["refresh"] = (A.check_refresh(app_key, secret, tok, http) if app_key and secret
                          else "client_or_token")          # keys missing: a config problem
    auth = state.get("schwab_auth") or {}
    if auth.get("login") != login:
        auth = dict(login=login, blocked=None)
    if rep["refresh"] in ("token_refused", "client_or_token"):
        auth["blocked"] = rep["refresh"]
    elif rep["refresh"] == "ok":
        auth["blocked"] = None
    # 'temporary' / 'other': keep the previous verdict, try again next run
    auth.pop("revoked", None)
    state["schwab_auth"] = auth
    sent = state.setdefault("schwab_notices", {})
    for name in A.due_notices(tok, sent, now, rep["refresh"]):
        title, text = A.TEXT[name]
        if push(title, text):
            A.mark_sent(tok, sent, name)
            rep["sent"].append(name)
        else:
            rep["failed"].append(name)
    return rep


def main(http=requests):
    pw = os.environ["STATE_PASSWORD"]
    path = vault.STATE_PATH
    if not Path(path).exists():
        print("no state file")
        return 0
    state = vault.load_file(path, pw)
    before = repr(sorted((k, repr(state.get(k))) for k in ("schwab_auth", "schwab_notices")))
    topic = os.getenv("NTFY_TOPIC", "").strip()

    def push(title, text):
        ok = A.send_ntfy(topic, title, text, http)
        print(f"[push] {title}: {'delivered' if ok else 'NOT delivered, retried next run'}")
        return ok
    rep = run(state, os.getenv("SCHWAB_APP_KEY", ""), os.getenv("SCHWAB_APP_SECRET", ""), push,
              http)
    print({k: v for k, v in rep.items()})
    after = repr(sorted((k, repr(state.get(k))) for k in ("schwab_auth", "schwab_notices")))
    if after != before:
        vault.save_file(path, state, pw)
        print("state updated (notices / auth flag)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
