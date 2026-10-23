# Weekly Schwab renewal (one button, automatic return)

Schwab's limit is unchanged: a login lasts **7 days** and cannot be extended. This change only
makes the weekly renewal easier and monitors it. It enables no live trading and sends no
order. The paper books are not touched.

## How it works
1. Unlock the Trading tab, open "Schwab connection" and press **«Продлить подключение
   Schwab»**. The app does two things:
   - it gives **this browser** a random secret in a short-lived cookie
     (`visar_sch_b`: HTTPS only, SameSite=Lax, 10 minutes);
   - it creates a one-time `state` bound to that secret (only hashes are kept, valid 10
     minutes, single use) and shows the link to Schwab's login with that state and the app's
     HTTPS address as the callback.
2. Log in at Schwab and allow access. Schwab sends the browser back to the scanner with
   `?code=…&state=…`. The cookie comes along, because it is the same browser and the return is
   a top-level navigation.
3. On that first page load, before any password prompt (the code lives about 30 seconds), the
   app does the following in order:
   - removes `code`/`state` from the address bar;
   - **atomically** consumes the state and checks that the returning browser holds the same
     secret. A valid state brought by another browser, an unknown, reused or expired state,
     or a missing cookie is rejected, and Schwab is never called. The state is burnt by its
     first use either way, and the cookie is cleared;
   - exchanges the code;
   - saves the token **encrypted** into `state/trader.enc` on `main` through the GitHub API
     (the same file the bot and Actions read), reloading and retrying if the bot saved in
     between;
   - shows **success only after the save**. A failure names the step.
4. The token, code, keys and browser secret are never shown, logged or put into
   notifications.
5. After a new login the bot **first reconciles positions and orders** with Schwab before any
   new order.

**To verify live:** the cookie is set from the page with JavaScript and read back by Streamlit
(`st.context.cookies`). The integration test below proves this with a real browser and a real
Streamlit server. Behind Streamlit Community Cloud it still has to be confirmed by the first
real renewal; if the cookie does not come through, the return is rejected with "this browser
did not start the renewal" and nothing is saved (fail-closed).

## Expiry, Schwab's answers and the refresh token
**No check uses the refresh token.** The monitor (`schwab-monitor.yml`, every 30 min) calls no
Schwab endpoint. It only reads the saved login time and sends, once per login, the "24 h left",
"2 h left" and "expired" notices. The refresh token is used only by the bot's normal
access-token refresh (`schwab_api.Schwab._access`, in `trader.schwab_or_none`), and only when
the bot really works with Schwab.
- **Rotation:** if Schwab answers a refresh with a new refresh token, it is written into
  `state["token"]` (the same dict) and saved with the run.
- **Merges:** a bot save keeps it; a newer login saved by the app meanwhile wins; the monitor
  never writes the token.

Each notice is **recorded only after ntfy confirmed delivery (HTTP 2xx)**. A timeout or an error
answer leaves it unrecorded, so the next run sends it again.

| Answer to the bot's refresh | Meaning | Bot | Notice to the owner |
|---|---|---|---|
| 200 | login works | normal | — |
| `invalid_grant` / `refresh_token_authentication_error` | the saved login was refused before its 7 days | new entries blocked | «Schwab отклонил вход досрочно» → log in again |
| `invalid_client` / `unauthorized_client`, or keys missing | app credentials refused. This is **not** proof of a revoked login; it also happens with wrong or missing keys (seen on 2026-10-21) | new entries blocked | «Schwab не принял ключи приложения» → check the keys in GitHub Secrets and the app status at Schwab; if both are fine, log in again |
| 5xx / 429 / network error | temporary | no broker for this run, nothing recorded | none |

Nothing is cancelled in any of these cases, so stops already at Schwab stay.

## Live safety check (every live run, first after a new login)
`trader.live_safety_check` runs before any new order in every live run (`execute`,
`preclose`). After a new login it is therefore the first thing the bot does.
1. It reconciles positions and fills with Schwab (`reconcile_live`).
2. Each bot position must have a **working STOP SELL at Schwab** for its quantity at its stop
   price. Child stops of TRIGGER orders count. The stop is read from Schwab's order list (60
   days), never assumed because the bot once sent it. PENDING_CANCEL, CANCELED or a wrong
   quantity or price counts as missing or mismatched.
3. The bot's own submitted orders are looked up by id, and REJECTED / CANCELED / EXPIRED ones
   are reported.

Any gap, or a check that could not run, sets `live_block`: new entries (morning plan and
pre-close breakouts) are blocked, while time exits and existing stops are untouched. The block
lifts when a later check passes. `schwab_reconciled_at` is set only by a passing check.

Dry mode is unchanged (the randomized equivalence test against the pre-audit bot passes).

## Concurrent writers of `state/trader.enc`
| Writer | How it saves | Conflicts |
|---|---|---|
| App (new login, approvals) | GitHub API with the file's sha; on a 409 the renewal reloads and re-applies the login (3 tries) | never overwrites a newer save |
| Bot | 3-way merge (`save_trader_state.py`) | app keys (`token`, `schwab_reconnected_at`, …) taken from the app if it changed them, otherwise the bot's (keeps a rotated refresh token); notices merged as a union; anything else changed by both → fails loudly, nothing overwritten |
| Monitor | `--monitor` merge: takes the saved state as it is and adds only its notice record | cannot conflict |

Tests cover the token cases: a bot rotation kept, a newer app login winning over it, and the
monitor never writing the token.

## Integration test (real browser, real Streamlit)
`schwab-renew-integration.yml` starts the real `trade_tab` helpers in a Streamlit server with
dummy secrets and drives Chromium (Playwright). It checks:
1. the cookie is set by the page and read back by `st.context.cookies`;
2. a valid state from browser A is rejected in browser B, and the URL is cleaned;
3. browser A passes the state check (the fake code then fails at the exchange step);
4. a replayed state is refused.

This proves the mechanism with a real browser and a real Streamlit server, but **not behind
Streamlit Community Cloud's proxy**. That still has to be confirmed by the first real renewal,
which fails closed if the cookie does not come through.

## One-time setup (owner): check before changing anything
Schwab's official documentation could not be reached from here. These points are **not
confirmed** and must be checked in the Developer Portal itself (the field's help text, or
Schwab's API support) **before** the working connection is changed:

| Question | Why it matters |
|---|---|
| Does the Callback URL field accept **several** addresses (e.g. comma-separated)? | If yes, `https://127.0.0.1` can stay and the manual fallback keeps working. If no, adding the scanner's address **replaces** it, and the manual fallback stops working |
| Does editing the app send it back to review ("Approved – Pending"), and do existing logins keep working during the review? | Third-party guides report 1–3 business days of review after creating an app. What happens on modification is not documented |

**If both answers are favourable:**
1. developer.schwab.com → your app → Modify → Callback URL: keep `https://127.0.0.1` and add
   the scanner's exact address, `https://dmitry-screener.streamlit.app` (HTTPS, no trailing
   slash or path, character for character; use the address your browser shows for the
   scanner if it differs). Do this right after a fresh login.
2. Streamlit → Manage app → Settings → Secrets: add
   `SCHWAB_CALLBACK_URL = "https://dmitry-screener.streamlit.app"`, the exact same string.
3. Test: scanner (awake) → Trading → Schwab → «Продлить подключение Schwab» → log in. Expected:
   "✅ … сохранено", no `code` in the address bar, and the Actions read-only check shows a
   login age of ≈ 0 days.

**If only one callback is allowed:** decide whether to switch. Switching means the manual
fallback (`https://127.0.0.1/?code=…`) no longer works, and the app says so (it is offered
only while `SCHWAB_CALLBACK_URL` is not set, or with a warning that it needs `127.0.0.1` to
still be registered).

## Tests
`test_schwab_auth.py` covers:
- one-time states: a valid state from browser A rejected in browser B, no cookie, foreign,
  reused, expired, and an atomic consume (16 threads, exactly one "ok");
- a successful return only after the save;
- a wrong or replayed state never reaching Schwab;
- an expired code; a failed save;
- Schwab's answers classified (refused login, credentials, temporary) from the bot's own
  refresh; a rotated refresh token lands in the state; no check calls the token endpoint;
- the live safety check: a working stop at Schwab is required, a missing, cancelled,
  pending-cancel, wrong-quantity or wrong-price stop blocks new entries, a child stop of a
  TRIGGER order counts, a failed check blocks, and the reconciled marker is set only after a
  pass;
- notices without duplicates, recorded only after delivery (timeout and HTTP 500 retried);
- the monitor writing nothing when nothing changed, and its state-file round trip (what
  Actions read);
- merges between the app, the bot and the monitor;
- the bot blocking without cancelling, notifying once, and reconciling first after a
  reconnect;
- the app's save retry.

`test_trade_tab.py` (AppTest) covers a foreign state: rejected, the address cleaned, the code
never displayed.
