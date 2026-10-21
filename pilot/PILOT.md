# Schwab real-money pilot: readiness check (no orders sent)

Status: **not ready, blocked.** Live mode is off. Nothing in this branch sends an order or
enables live trading. The paper books (`paper/`, `paper/compare/`) and the dry-mode bot are
unchanged.

## 1. Real API, read-only (`pilot/readonly_check.py`, workflow `pilot-readonly.yml`)
All calls go through `ReadOnlyHTTP`: only GET requests and the OAuth token refresh can leave
the process. `state/trader.enc` is compared before and after each run and was unchanged.

| Check | Result (2026-10-21 04:04 UTC) |
|---|---|
| Saved Schwab login in the bot state | present; refresh token created 5.49 days earlier, so it **expires around 2026-10-22 16:20 UTC** (7-day limit) |
| `SCHWAB_APP_KEY` / `SCHWAB_APP_SECRET` in GitHub secrets | **not set** (empty in Actions) |
| Token refresh | **failed: 401 invalid_client**, the expected result without the app key and secret |
| Account, balances, positions, open orders | not reached (the refresh is needed first) |
| Calls other than GET + token | 0 |

As a result, the bot's live modes could never have worked from GitHub Actions. The login made
in the app is stored, but the job that would use it has no client credentials.

## 2. Code path signal → closed position (`pilot/engine.py`)
The existing live path in `trader.py` is **not used** for the pilot. The review found:
- `Schwab.positions()` counts the whole account, so manual shares in a ticker would be
  adopted as the bot's fills.
- `open_sell_orders()` + `cancel()` on a time exit cancel **every** live sell order in that
  ticker, including manual ones.
- `buy_with_stop()` is a TRIGGER (OTO) order whose child stop has the **ordered** quantity,
  not the filled one.
- A timeout after sending (a `requests` exception, not `SchwabError`) crashes the run before
  the order is recorded. A forced re-run could then send the buy again.

The pilot engine handles these:

| Step | Rule |
|---|---|
| Before anything | Broker snapshot first (positions, orders, balances). Unreachable or expired login: nothing is sent, alert, the broker stop keeps protecting |
| Size | Owner approval with exact ticker, quantity, max price, stop, expiry and account last 4 digits; used once. Quote ≤ max price. First trade ≤ $100; total pilot ≤ $1,000 including open positions and pending buys (quote + 2 %); one position; whole shares; long equity only; cash available checked |
| Send | The intent is saved **before** the request. 4xx → rejected (safe). Timeout, connection drop, 5xx or 2xx without an id → **unknown** |
| Unknown result | Matched against the broker's orders (same ticker, side, quantity, type, entered after the intent). One match → adopted. Several → blocked, owner checks. None after 10 min → `not_found`, blocked. **Never re-sent** |
| Broker id / status | Order id from the `Location` header; status and filled quantity from `GET /orders/{id}` |
| Partial fill | The stop covers the shares actually bought. It is replaced when more shares fill. A remainder still working after 15 min is cancelled (the pilot's own order only) |
| Protective stop | Separate `STOP SELL GTC` for exactly the pilot's shares, placed after the fill and verified by reading it back (live status, quantity, type) on every run. Wrong quantity → cancel and replace. Missing → re-placed. After 3 failures → **PROTECTION FAILED**: new entries blocked, explicit alert to the owner |
| Close | Cancel the pilot's stop, confirm it is cancelled (if it filled meanwhile, the position is already closed), then market-sell the pilot's shares only. Sell result unknown → reconciled, never re-sent. Sell rejected → stop re-placed |
| Isolation | Only order ids recorded by the pilot are ever touched. A ticker with any broker position or open order not from the pilot is refused. Manual shares added later are never sold |

**Why a separate stop and not the TRIGGER child.** The TRIGGER child carries a fixed quantity.
After a partial fill it would protect (and sell) more shares than the pilot owns, and in a
margin account that could open a short. The cost of the separate stop is a gap of one poll
between the fill and the stop. For a 1-share market order that fills at once, this is
seconds.

**Order preview.** Third-party clients list a `previewOrder` endpoint. The official Schwab
developer portal could not be reached from here to confirm it is supported, so per the task it
is **not used**. The read-only check refuses it too, since it is a POST.

## 3. Tests on scripted broker answers (`test_pilot.py`, 25 tests, no network)
Covered:
- the happy path buy → fill → stop → re-runs → close;
- the intent saved before sending; a duplicate run with the same approval;
- the first-trade limit, the $1,000 budget and the one-position limit; a quote above the
  approved price; an expired approval; an account mismatch;
- a manual position or manual order in the ticker; manual shares and stops untouched on exit;
- an expired token;
- a timeout with the order created (matched, not re-sent) and with the order lost (blocked);
- a crash between save and send; a rejected buy;
- partial fills (stop follows the bought shares; remainder cancelled after the timeout);
- the stop rejected 3× (protection failed, entries blocked); a stop cancelled outside
  (restored); stopped out while an exit was requested (no sell);
- a sell timeout (matched, sold once); a manual sale (no stop placed without shares, blocked); the kill switch (no entries, protection kept);
- the read-only guard.

## 4. Blockers before the first real order
1. Add `SCHWAB_APP_KEY` and `SCHWAB_APP_SECRET` (the same ones the app uses) to the GitHub repo
   secrets.
2. Log in to Schwab again from the app (the current login expires around 2026-10-22 16:20 UTC).
3. Re-run the read-only check. It must show the account (last 4 digits), type, balances,
   positions and open orders.
4. Decide whether the pilot uses a separate account or the shared one, and set its last 4
   digits.
5. Wire the engine to a runner with encrypted pilot state and alerts. This is a separate PR
   that is not merged until approved; nothing here runs the engine against Schwab.
6. ChatGPT and Muse review, then the owner confirms one concrete order.

## 5. Exact order of the first trade (after the blockers)
1. Read-only check is green; the owner confirms: ticker, 1 share (cost ≤ $100), max price,
   stop price, expiry, account last 4 digits.
2. Run (during market hours): snapshot → guards → quote ≤ max price → intent saved →
   `MARKET BUY 1 DAY`.
3. Same run and following runs: `GET` the order → filled quantity → `STOP SELL 1 GTC` at the
   confirmed stop → read it back (live, quantity 1).
4. Every run: the stop is live with the right quantity, otherwise it is fixed or the run
   alerts.
5. Close (owner's request or the time rule): cancel the pilot stop → confirm `CANCELED` →
   `MARKET SELL 1 DAY` → filled → closed. If the stop fills first, the trade closed at the
   stop and nothing is sold.

## 6. Switching off and emergencies
- **No new entries, protection kept:** `entries_enabled=False` (pilot switch). Runs still
  verify and repair the stop and process exits; no buy is sent. Tested.
- **Lost connection / GitHub down / bot stopped:** the GTC stop is at Schwab and keeps working
  without the bot. The next run starts from the broker's state.
- **Emergency stop:** disable the pilot workflow (or set live off). Do **not** cancel the stop.
  To leave the position, sell it manually at Schwab; the next pilot run sees the stop
  `CANCELED`/position gone and blocks for owner review rather than acting.
- **Protection failed alert:** place a stop manually at Schwab for the pilot's shares. Entries
  stay blocked until the owner clears the block.
