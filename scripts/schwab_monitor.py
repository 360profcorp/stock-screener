"""Schwab login monitor (GitHub Actions, every 30 min). Calls NO Schwab endpoint and places,
changes or cancels no order: it never uses the refresh token, so it cannot rotate or
invalidate the saved login.

From state/trader.enc (the store the bot and the app use) it sends, once per login, the
"24 h left", "2 h left" and "expired" notices. A notice is recorded only after ntfy confirmed
delivery; otherwise the next run retries. Early refusals by Schwab are detected and notified
by the bot itself, when it really uses the login (trader.schwab_or_none).
Writes state/trader.enc only when the notice record changed; the workflow saves it with the
monitor merge (only schwab_notices). Prints no key, code or token.
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests  # noqa: E402

import schwab_auth as A  # noqa: E402
import vault  # noqa: E402


def run(state: dict, push, now=None) -> dict:
    """push(title, text) -> True only when the notification service confirmed delivery."""
    now = time.time() if now is None else now
    tok = state.get("token")
    s = A.status(tok, now)
    rep = dict(status=s["state"], hours_left=None if s["seconds_left"] is None
               else round(s["seconds_left"] / 3600, 1), sent=[], failed=[])
    if s["state"] == "none":
        return rep
    sent = state.setdefault("schwab_notices", {})
    for name in A.due_notices(tok, sent, now):
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
    before = repr(state.get("schwab_notices") or {})
    topic = os.getenv("NTFY_TOPIC", "").strip()

    def push(title, text):
        ok = A.send_ntfy(topic, title, text, http)
        print(f"[push] {title}: {'delivered' if ok else 'NOT delivered, retried next run'}")
        return ok
    rep = run(state, push)
    print({k: v for k, v in rep.items()})
    after = repr(state.get("schwab_notices") or {})
    if after != before:
        vault.save_file(path, state, pw)
        print("state updated (notice record)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
