# Schwab real-money pilot: readiness (no orders sent)

Status: **not ready.** Live mode is off. Nothing in this branch sends an order, enables live
trading or runs the engine against Schwab. The paper books (`paper/`, `paper/compare/`) and the
dry-mode bot are unchanged. Engine v2 addresses the owner's review of v1 (§2).

## 1. Real API, read-only (`pilot/readonly_check.py`, workflow `pilot-readonly.yml`)
All calls go through `ReadOnlyHTTP`: only GET requests and the OAuth token refresh can leave
the process. `state/trader.enc` is compared before and after each run and was unchanged.
Details (balances, positions) are encrypted to a one-off key and are not in logs or the repo.

**2026-10-21 run 39666235303 (after the owner added the secrets and logged in again): passed.**

| Check | Result |
|---|---|
| Keys in Actions | `SCHWAB_APP_KEY` and `SCHWAB_APP_SECRET` set (values not shown) |
| Login used | the new saved login from `state/trader.enc` on main (`682c143`; login committed `e2a5e9d`), age 0.01 days, so it is in the repo for Actions, not only in the Streamlit session |
| Token refresh | ok; the refresh token did not rotate |
| Accounts | 1 linked, `…1725`, type **MARGIN**; not day-trader flagged, not closing-only |
| Balances, positions, orders | read ok: 1 equity position (manual), 0 open orders, 0 orders in the last 60 days |
| Calls | token refresh + 4 GETs; 0 order calls |

Earlier runs (04:04 and 12:36 UTC) failed with 401 invalid_client because the two secrets were
empty in that job. This does not mean the connection never worked elsewhere.

## 2. Engine v2 (`pilot/engine.py`): owner's review points
| # | Review point | v2 behaviour | Tests |
|---|---|---|---|
| 1 | Buy must be LIMIT at the approved max price | `LIMIT BUY DAY` at `max_price`. The limit caps the fill price. Budget and first-trade checks use `qty × limit`, never a quote | `LimitEntry` (3) |
| 2 | Stop needs the same no-resend protection as the buy | Every order (BUY, STOP, SELL) is an intent saved before sending. Unknown result → matched on ticker, side, type, quantity and stop/limit price. While a stop intent is unresolved, no other stop is sent; not found after 10 min → blocked, never re-sent | `StopSendPath` (4), incl. "broker accepted the stop, response lost" |
| 3 | Replace only after the old stop's cancellation is confirmed; check price and GTC; PENDING_CANCEL is not protection | A stop counts only if it is SELL STOP **GTC**, has the approved **stop price**, its remaining quantity equals the pilot's shares, and it is in a working status (not PENDING_CANCEL / PENDING_REPLACE / manual review). Wrong or extra stops are cancelled, and a fresh read must show CANCELED before anything new is sent | `ReplaceStop` (3) |
| 4 | Protect right after the fill; continuous monitoring; explicit emergency | `enter()` monitors the buy (every 2 s, up to 120 s) and places the stop on the first filled share in the same call; later fills resize it; the unfilled rest is cancelled at the end. A fill without a confirmed stop at the end, or a lost broker → **EMERGENCY**: entries blocked, alert with the owner's steps (§6) | `ImmediateProtection` (4) |
| 5 | Partial sells and manual close | Before selling: fresh broker read, stop fills and shares held are reconciled; sells `min(pilot shares, shares held)`. A partial sell or partial stop fill reduces the pilot's shares and the rest is protected again. Shares sold outside → the pilot's stop is cut to the shares still held, or cancelled (confirmed) when none are left; owner alerted and entries blocked | `Exits` (9) |

Second review (a3c9770):
| # | Review point | Fix | Tests |
|---|---|---|---|
| 6 | A GTC stop older than the 7-day order list could be duplicated | The pilot's own orders are always read **directly by id**, never looked up in a list (a missing list entry never means "cancelled"). The order list (for manual orders and matching unknown submissions) now spans 60 days, the API maximum | `ReviewTwo` (1) |
| 7 | A stop that filled during its cancellation could be replaced for shares already sold | After any confirmed cancel, positions and orders are re-read and fills recounted before deciding what still needs a stop; this applies both when replacing a stop and before an exit sale | `ReviewTwo` (3): full fill, partial fill, fill during the exit cancel |

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

## 3. Tests (`test_pilot.py`, 40 tests, scripted broker, no network)
Run `python -m unittest test_pilot -v`.

## 4. Blockers before the first real order
1. ~~Secrets~~ and ~~a fresh login~~ (done 2026-10-21; the login lasts 7 days and must be
   renewed weekly).
2. **Own cash for the pilot.** The account's own cash is below the first trade's $100 cap.
   The account is a margin account; the pilot uses own cash only (`cashAvailableForTrading`,
   else `cashBalance`) and refuses when it is unknown. Buying power, which includes leverage,
   is never used.
3. Shared account (`…1725` is the only linked account): pilot budget, trades and order ids are
   tracked separately; the existing manual position's ticker is refused.
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
