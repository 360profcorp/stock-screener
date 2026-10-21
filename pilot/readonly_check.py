"""Read-only check of the connected Schwab account (pilot readiness, step 1).

Uses the bot's saved Schwab login from state/trader.enc. Every HTTP call goes through
ReadOnlyHTTP: only GET requests and the OAuth token refresh can leave this process, so no
order can be placed, replaced or cancelled. state/trader.enc is never written.

Output:
  stdout / annotations  only non-sensitive facts: ok flags, counts, last 4 digits
  --pub KEY --out FILE  full details (balances, positions, orders) encrypted with a one-off
                        public key (RSA-OAEP + Fernet), readable only by the holder of the key
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.getcwd())

import vault                                                       # noqa: E402
from pilot.broker import (LIVE_STATUSES, BrokerUnavailable, ReadOnlyHTTP,  # noqa: E402
                          SchwabPilotBroker)
from schwab_api import Schwab, SchwabError, refresh_age_days      # noqa: E402


def last4(x):
    s = str(x or "")
    return "…" + s[-4:] if s else None


def run(state: dict, app_key, secret, account_suffix="", http=None) -> dict:
    tok = dict(state.get("token") or {})
    ro = ReadOnlyHTTP() if http is None else ReadOnlyHTTP(http)
    rep = dict(checked_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               token_present=bool(tok.get("refresh_token")),
               refresh_age_days=round(refresh_age_days(tok), 2) if tok else None,
               steps={}, accounts=[])
    if not rep["token_present"]:
        rep["steps"]["auth"] = "no saved Schwab login"
        return rep
    old_refresh = tok.get("refresh_token")
    tok["access_expires"] = 0                       # force a real refresh: proves it works
    try:
        c = Schwab(app_key, secret, tok, account_suffix, http=ro)
        c._access()
        rep["steps"]["token_refresh"] = "ok"
        rep["refresh_token_rotated"] = tok.get("refresh_token") != old_refresh
    except SchwabError as e:
        rep["steps"]["token_refresh"] = f"failed: {str(e)[:160]}"
        rep["read_only_calls"] = ro.calls
        return rep
    b = SchwabPilotBroker(c)
    try:
        nums = b.account_numbers()
        rep["steps"]["account_numbers"] = "ok"
    except BrokerUnavailable as e:
        rep["steps"]["account_numbers"] = f"failed: {e}"
        rep["read_only_calls"] = ro.calls
        return rep
    rep["account_count"] = len(nums)
    for a in nums:
        c2 = Schwab(app_key, secret, tok, str(a["accountNumber"]), http=ro)
        b2 = SchwabPilotBroker(c2)
        entry = dict(account=last4(a["accountNumber"]))
        try:
            s = b2.snapshot(days=60)
            live = [o for o in s["orders"] if o["status"] in LIVE_STATUSES]
            entry.update(type=s["type"], balances=s["balances"], flags=s["flags"],
                         positions={t: p["qty"] for t, p in s["positions"].items()},
                         position_assets=sorted({p["asset"] for p in s["positions"].values()}),
                         open_orders=[{k: o[k] for k in ("id", "status", "symbol", "instruction",
                                                         "type", "duration", "qty", "filled",
                                                         "stop_price", "entered")} for o in live],
                         orders_60d=len(s["orders"]),
                         order_statuses_60d=sorted({o["status"] for o in s["orders"]}),
                         snapshot="ok")
        except BrokerUnavailable as e:
            entry["snapshot"] = f"failed: {e}"
        rep["accounts"].append(entry)
    rep["bot_account_setting"] = account_suffix or "(not set)"
    rep["read_only_calls"] = ro.calls
    rep["non_get_calls"] = [c for c in ro.calls if c[0] != "GET" and c[1] != "/v1/oauth/token"]
    return rep


def public_summary(rep: dict) -> dict:
    return dict(token_present=rep["token_present"], refresh_age_days=rep["refresh_age_days"],
                steps=rep["steps"], refresh_token_rotated=rep.get("refresh_token_rotated"),
                accounts=[dict(account=a["account"], type=a.get("type"),
                               snapshot=a.get("snapshot"),
                               positions=len(a.get("positions", {})),
                               open_orders=len(a.get("open_orders", [])))
                          for a in rep["accounts"]],
                calls=len(rep.get("read_only_calls", [])),
                non_get_calls=rep.get("non_get_calls", []))


def encrypt(data: bytes, pub_path: str) -> bytes:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    k = Fernet.generate_key()
    pub = serialization.load_pem_public_key(open(pub_path, "rb").read())
    wk = pub.encrypt(k, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),
                                     algorithm=hashes.SHA256(), label=None))
    return len(wk).to_bytes(2, "big") + wk + Fernet(k).encrypt(data)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pub")
    ap.add_argument("--out")
    a = ap.parse_args()
    st = vault.load_file(vault.STATE_PATH, os.environ["STATE_PASSWORD"])
    rep = run(st, os.environ.get("SCHWAB_APP_KEY", ""), os.environ.get("SCHWAB_APP_SECRET", ""),
              os.environ.get("SCHWAB_ACCOUNT", ""))
    summ = public_summary(rep)
    print("::notice title=Schwab read-only::" + json.dumps(summ, default=str))
    if a.pub and a.out:
        open(a.out, "wb").write(encrypt(json.dumps(rep, default=str).encode(), a.pub))
    ok = rep["steps"].get("token_refresh") == "ok" and not summ["non_get_calls"]
    sys.exit(0 if ok else 1)
