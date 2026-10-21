"""Schwab login monitor (GitHub Actions, every 30 min). Places, changes and cancels NO order.

Reads state/trader.enc (the same store the bot and the app use), and:
  - if the login is inside its 7 days and the app key/secret are set, calls ONLY the OAuth
    token endpoint to see whether Schwab still accepts the login (early revocation);
  - sends each notice at most once per login: 24 h left, 2 h left, expired, revoked early;
  - records state["schwab_auth"] (login key, revoked flag) so the bot blocks new
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
    now = time.time() if now is None else now
    tok = state.get("token")
    s = A.status(tok, now)
    rep = dict(status=s["state"], hours_left=None if s["seconds_left"] is None
               else round(s["seconds_left"] / 3600, 1), refresh=None, sent=[])
    if s["state"] == "none":
        return rep
    login = str(int(float(tok["refresh_created"])))
    if s["state"] != "expired":
        if app_key and secret:
            rep["refresh"] = A.check_refresh(app_key, secret, tok, http)
        else:
            rep["refresh"] = "skipped: app key/secret not set"
    auth = state.get("schwab_auth") or {}
    if auth.get("login") != login:
        auth = dict(login=login, revoked=False)
    if rep["refresh"] == "revoked":
        auth["revoked"] = True
    elif rep["refresh"] == "ok":
        auth["revoked"] = False
    state["schwab_auth"] = auth
    sent = state.setdefault("schwab_notices", {})
    for name in A.notices(tok, sent, now, rep["refresh"]):
        title, text = A.TEXT[name]
        push(title, text)
        rep["sent"].append(name)
    return rep


def main():
    pw = os.environ["STATE_PASSWORD"]
    path = vault.STATE_PATH
    if not Path(path).exists():
        print("no state file")
        return 0
    state = vault.load_file(path, pw)
    before = repr(sorted((k, repr(state.get(k))) for k in ("schwab_auth", "schwab_notices")))

    topic = os.getenv("NTFY_TOPIC", "").strip()

    def push(title, text):
        print(f"[push] {title}")
        if topic:
            try:
                requests.post(f"https://ntfy.sh/{topic}", data=text.encode(),
                              headers={"Title": title.encode(), "Tags": "warning"}, timeout=20)
            except Exception as e:
                print("push failed:", type(e).__name__)
    rep = run(state, os.getenv("SCHWAB_APP_KEY", ""), os.getenv("SCHWAB_APP_SECRET", ""), push)
    print({k: v for k, v in rep.items()})
    after = repr(sorted((k, repr(state.get(k))) for k in ("schwab_auth", "schwab_notices")))
    if after != before:
        vault.save_file(path, state, pw)
        print("state updated (notices / auth flag)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
