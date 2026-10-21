# Schwab real-money pilot: readiness (no orders sent)

Status: **not ready.** Live mode is off. Nothing in this branch sends an order, enables live
trading or runs the engine against Schwab. The paper books (`paper/`, `paper/compare/`) and the
dry-mode bot are unchanged. Engine v2 addresses the owner's review of v1 (§2).

## 1. Real API, read-only (`pilot/readonly_check.py`, workflow `pilot-readonly.yml`)
All calls go through `ReadOnlyHTTP`: only GET requests and the OAuth token refresh can leave
the process. `state/trader.enc` is compared before and after each run and was unchanged.

| Check | Result (2026-10-21 04:04 UTC) |
|---|---|
| Saved Schwab login in the bot state | present; refresh token created 5.49 days earlier, so it expires around **2026-10-22 16:20 UTC** |
| `SCHWAB_APP_KEY` / `SCHWAB_APP_SECRET` as seen by this Actions job | empty |
| Token refresh | 401 invalid_client (consistent with empty client credentials in this job) |
| Account, balances, positions, open orders | not reached yet |
| Calls other than GET + token | 0 |

What this shows: in this job the two secrets were empty. It does **not** prove that the
connection never worked. They may be stored elsewhere, for example in the app only or in a
GitHub environment this job does not use. The owner adds them directly in GitHub Secrets
(never in the chat); then the read-only check is repeated.

## 2. Engine v2 (`pilot/engine.py`): owner's review points
| # | Review point | v2 behaviour | Tests |
|---|---|---|---|
| 1 | Buy must be LIMIT at the approved max price | `LIMIT BUY DAY` at `max_price`. The limit caps the fill price. Budget and first-trade checks use `qty × limit`, never a quote | `LimitEntry` (3) |
| 2 | Stop needs the same no-resend protection as the buy | Every order (BUY, STOP, SELL) is an intent saved before sending. Unknown result → matched on ticker, side, type, quantity and stop/limit price. While a stop intent is unresolved, no other stop is sent; not found after 10 min → blocked, never re-sent | `StopSendPath` (4), incl. "broker accepted the stop, response lost" |
| 3 | Replace only after the old stop's cancellation is confirmed; check price and GTC; PENDING_CANCEL is not protection | A stop counts only if it is SELL STOP **GTC**, has the approved **stop price**, its remaining quantity equals the pilot's shares, and it is in a working status (not PENDING_CANCEL / PENDING_REPLACE / manual review). Wrong or extra stops are cancelled, and a fresh read must show CANCELED before anything new is sent | `ReplaceStop` (3) |
| 4 | Protect right after the fill; continuous monitoring; explicit emergency | `enter()` monitors the buy (every 2 s, up to 120 s) and places the stop on the first filled share in the same call; later fills resize it; the unfilled rest is cancelled at the end. A fill without a confirmed stop at the end, or a lost broker → **EMERGENCY**: entries blocked, alert with the owner's steps (§6) | `ImmediateProtection` (4) |
| 5 | Partial sells and manual close | Before selling: fresh broker read, stop fills and shares held are reconciled; sells `min(pilot shares, shares held)`. A partial sell or partial stop fill reduces the pilot's shares and the rest is protected again. Shares sold outside → the pilot's stop is cut to the shares still held, or cancelled (confirmed) when none are left; owner alerted and entries blocked | `Exits` (9) |

Unchanged rules: owner approval of exact ticker, quantity, max price, stop, expiry and account
(used once); first trade ≤ $100; pilot total ≤ $1,000 including open positions and working buys;
one position; long whole shares; cash available checked; manual positions and orders never
touched and their tickers refused; kill switch keeps protection; a lost broker mid-pass stops
the pass without sending anything.

The existing live path in `trader.py` is not used for the pilot. Its known issues:
- whole-account positions;
- cancelling every sell order in the ticker on a time exit;
- the OTO child stop sized to the ordered quantity;
- no handling of unknown send results.

## 3. Tests (`test_pilot.py`, 35 tests, scripted broker, no network)
Run `python -m unittest test_pilot -v`.

## 4. Blockers before the first real order
1. Owner adds `SCHWAB_APP_KEY` and `SCHWAB_APP_SECRET` in GitHub Secrets.
2. Owner logs in to Schwab again from the app (the current login expires around
   2026-10-22 16:20 UTC).
3. The read-only check is repeated and shows the account (last 4 digits), type, balances,
   positions and open orders.
4. Separate or shared account: owner's decision.
5. Runner with encrypted pilot state and alerts: a separate PR, not merged without approval.
6. Review by the owner and Muse, then the owner confirms one concrete order.

## 5. First trade sequence (after the blockers)
1. Snapshot → guards → intent saved → `LIMIT BUY 1 DAY @ max_price`.
2. Monitor: fill read from the order → intent saved → `STOP SELL 1 GTC @ stop`; read back,
   working, price, GTC, quantity 1.
3. Every run: the stop is verified the same way; wrong → cancel, confirm, replace.
4. Close: fresh read and reconciliation → cancel the pilot stop → confirm `CANCELED` →
   intent saved → `MARKET SELL min(pilot, held)` → fill read. A stop that filled first means
   there is nothing to sell.

## 6. Switching off and emergencies
- **No new entries, protection kept:** `entries_enabled=False`. Stops are still verified and
  repaired, and exits are processed.
- **Lost connection / bot down:** the GTC stop at Schwab works without the bot; the next run
  reconciles from the broker.
- **EMERGENCY alert** (a filled buy without a confirmed stop, or the broker lost during entry):
  1. In Schwab, check the position and open orders for the ticker.
  2. If there is no working stop for the pilot's shares, place one at the approved stop price
     (or sell).
  3. Then clear the block. Entries stay blocked until then.
- **Emergency stop:** disable the pilot workflow and leave the stop in place. Selling manually
  at Schwab is handled: the pilot cancels its own stop and blocks for review.
