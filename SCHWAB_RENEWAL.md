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

**To verify live:** the cookie is set from the page with JavaScript and read back by
Streamlit (`st.context.cookies`). Whether Streamlit Community Cloud passes it through has to be
confirmed on the first real renewal. If it does not, the return is rejected with "this browser
did not start the renewal" and nothing is saved (fail-closed).

## Expiry and Schwab's answers (`schwab-monitor.yml`, every 30 min)
Each run calls only Schwab's token endpoint and places, changes and cancels no order. Each
notice is **recorded only after ntfy confirmed delivery (HTTP 2xx)**. A timeout or an error
answer leaves it unrecorded, so the next run sends it again.

| Schwab's answer to the refresh | Meaning | Bot | Notice to the owner |
|---|---|---|---|
| 200 | login works | normal | — |
| `invalid_grant` / `refresh_token_authentication_error` | the saved login was refused before its 7 days | new entries blocked | «Schwab отклонил вход досрочно» → log in again |
| `invalid_client` / `unauthorized_client`, or keys missing | app credentials refused. This is **not** proof of a revoked login: it also happens with wrong or missing keys, as seen on 2026-10-21 | new entries blocked | «Schwab не принял ключи приложения» → check the keys in GitHub Secrets and the app status at Schwab; if both are fine, log in again |
| 5xx / 429 / network error | temporary | previous verdict kept | none; retried next run |

Time notices: 24 h left, 2 h left, expired. Each is sent at most once per login.

- **Blocked or expired:** nothing is cancelled, so stops already at Schwab stay.
- **Saving:** the monitor writes only `schwab_auth` and `schwab_notices` on top of whatever is
  saved, and a bot save keeps them (notices are merged as a union), so the two never conflict.
- **The app** shows the expiry date and time (New York), the hours left, and each blocked
  state separately.

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
- Schwab's answers classified (refused login, credentials, temporary);
- notices without duplicates, recorded only after delivery (timeout and HTTP 500 retried);
- the monitor writing nothing when nothing changed, and its state-file round trip (what
  Actions read);
- merges between the app, the bot and the monitor;
- the bot blocking without cancelling, notifying once, and reconciling first after a
  reconnect;
- the app's save retry.

`test_trade_tab.py` (AppTest) covers a foreign state: rejected, the address cleaned, the code
never displayed.
