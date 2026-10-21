# Weekly Schwab renewal (one button, automatic return)

Schwab's limit is unchanged: a login lasts **7 days** and cannot be extended. This change only
makes the weekly renewal easier and monitors it. It enables no live trading and sends no
order. The paper books are not touched.

## How it works
1. Unlock the Trading tab, open "Schwab connection" and press **«Продлить подключение
   Schwab»**. The app creates a one-time `state`: random, only its hash is kept, valid 10
   minutes, single use. It then shows the link to Schwab's login with that state and the app's
   own HTTPS address as the callback.
2. Log in at Schwab and allow access. Schwab sends you back to the scanner with
   `?code=…&state=…`.
3. On that first page load, before any password prompt (the code lives about 30 seconds),
   the app does the following in order:
   - removes `code`/`state` from the address bar;
   - checks and consumes the state; an unknown, reused or expired state is rejected and
     Schwab is never called;
   - exchanges the code;
   - saves the token **encrypted** into `state/trader.enc` on `main` through the GitHub API.
     This is the same file the bot and Actions read. If the bot saved in between, the app
     reloads and retries.
   - shows **success only after the save**. A failure says which step failed.
4. The token, code and keys are never shown, logged or put into notifications.
5. After a new login the bot **first reconciles positions and orders** with Schwab before any
   new order (`reconcile_after_reconnect`, recorded as `schwab_reconnected_at` /
   `schwab_reconciled_at`).

The old way (paste the `https://127.0.0.1/?code=…` address) stays available under «Запасной
способ». It is shown open as long as `SCHWAB_CALLBACK_URL` is not set.

## Expiry and early refusal (`schwab-monitor.yml`, every 30 min)
Each run calls only Schwab's token endpoint and places, changes and cancels no order. Each
notice is sent at most once per login:

| Notice | When |
|---|---|
| 24 h left | ≤ 24 h before the 7 days end |
| 2 h left | ≤ 2 h before |
| expired | the 7 days are over |
| refused early | Schwab rejects the login although the 7 days are not over (revoked or changed at Schwab) |

- **Expired or refused:** the bot's new entries are blocked (`schwab_or_none` returns no
  broker). Nothing is cancelled, so stops already at Schwab stay.
- **Saving:** the monitor writes only its two keys, `schwab_auth` and `schwab_notices`, on top
  of whatever is saved. A bot save keeps them too (notices are merged as a union), so the two
  never conflict.
- **The app** shows the expiry date and time (New York) and the hours left, and separately
  the "expired" and "refused early" states.

## One-time setup (owner)
**1. Schwab Developer Portal.** developer.schwab.com → Dashboard → your app (Trader API –
Individual) → Modify → Callback URL. Add the scanner's address **exactly**:

    https://dmitry-screener.streamlit.app

Use HTTPS, with no trailing slash and no path; it must match character for character. If this
is not the address your browser shows for the scanner, use the address it does show. Keep
`https://127.0.0.1` in the same field if the portal accepts several URLs (comma-separated), so
the old path keeps working.

Caveats (the official portal was not reachable from here):
- Third-party guides agree that the callback must be HTTPS and match exactly.
- Whether several URLs are accepted is not confirmed.
- Changing the app can put it into review ("Approved – Pending") for 1–3 business days.
  **Change it right after a fresh login** (you just logged in on 2026-10-21), and keep the
  current connection until the new path is tested.

**2. Streamlit → Manage app → Settings → Secrets.** Add:

    SCHWAB_CALLBACK_URL = "https://dmitry-screener.streamlit.app"

It must be exactly the string you registered. The existing secrets stay.

**3. First test.** Open the scanner (wake it first if it was asleep) → Trading → Schwab →
«Продлить подключение Schwab» → log in. Expected result: "✅ Подключение Schwab продлено и
сохранено", the address bar has no `code`, and the read-only check in Actions sees the new
login age (≈ 0 days).

## Tests
`test_schwab_auth.py` covers:
- one-time states: valid, foreign, reused, expired;
- a successful return only after the save;
- a wrong or replayed state never reaching Schwab;
- an expired code; a failed save;
- the 24 h / 2 h / expired / early-refusal notices without duplicates;
- the monitor writing nothing when nothing changed, and its state-file round trip (what
  Actions read);
- merges between the app, the bot and the monitor;
- the bot blocking without cancelling, notifying once, and reconciling first after a
  reconnect;
- the app's save retry.

`test_trade_tab.py` (AppTest) covers a foreign state: rejected, the address cleaned, the code
never displayed.
