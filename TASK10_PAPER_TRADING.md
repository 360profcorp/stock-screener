# Task 10 / 10B — Retest RS-first daily screener and paper trading

Branch `feature/task10-paper-retest` (base `fix/portfolio-engine-task6`, PR #2). **Not merged,
not deployed.** No broker connection, no live orders. The daily workflow is manual-only (cron
commented out). Task 9 sector limits stay off. The trading bot, `daily_scan.py`, RS, Retest
detection, sizing/execution rules and the Task 6 engine logic are unchanged. The only engine
addition is an opt-in audit log (`record_decisions`, default off).

## Dependencies
* **PR #2 (required):** the paper portfolio must reproduce
  `simulate(one_per_ticker=False, include_open=True, entry_at="open")` + `replay` (pre-open
  sizing, `open_at_end="mark"`).
* **PR #3:** not used. Sector is only stored as an ML feature.

## How a forward run works (`paper_run.py daily`, after the US close)
1. Download data and determine the last **closed** session (a bar of today is ignored before
   16:15 New York).
2. Process **every** session since the last run, in order. For each session D:
   * **pre-open entries:** orders queued after the previous close fill at D's open, sized
     from cash before D's exits and positions at the previous close;
   * stop and 20-day exits, then mark-to-market at D's close;
   * scan D, write the immutable snapshot and signal rows, and queue eligible signals for
     the next session.
3. Update labels (only observable outcomes), save state (revision + 1), write `summary.json`.

### Catch-up after a missed run — retrospective (reconstructed) executions
D is processed **on time** only if the run starts **before the 09:30 New York open of the
session after D** (`store.is_late`). Otherwise D is processed retrospectively (`processed_late`),
and the following happens:
* **entry fills** on D of orders that were queued on time are computed from D's bars after the
  fact → the entry is flagged `entry_processed_late`;
* **stop / time exits** on D are computed after the fact → `exit_processed_late`;
* **marks** for D are computed after the fact (no execution);
* **signals** found on D are recorded (snapshot + signal store, `late=True`) but **never
  traded** → `not_traded_late`.

### Reporting categories (`metrics.forward_report`, `summary.json → forward`, Paper tab)
| Category | Definition | Where |
|---|---|---|
| **A — timely** | entry and exit (if any) processed in their own session's run | `forward.timely` |
| **B — reconstructed** | entry **or** exit processed late | `forward.reconstructed` (+ events list) |
| **C — late signals** | recorded at/after their execution session's open; never traded | `forward.late_not_traded` |

**Genuine-forward portfolio metrics** (return, CAGR, max drawdown, SPY-relative) are
calculated **only up to the session before the first reconstructed execution**
(`genuine_through`). Equity is path-dependent, so the curve is **not** "cleaned" by
removing B trades. After contamination, `genuine_forward.available = false`, a `reason` is
given, and the last valid values stay frozen at `genuine_through`. A run with only
late-processed **marks** (no execution) does not contaminate.

The observed portfolio (including reconstructed executions) is shown only in a separate,
labelled section (`observed_portfolio.contains_reconstructed`). A/B trade statistics are
trade-level (R, $, PF, win rate) and are **not** a counterfactual portfolio return. After
contamination, A trade sizes also depend on contaminated equity, which is stated in
`timely.note`.

**SPY is price-only** (dividends excluded). It understates SPY total return by about the
dividend yield. Keys: `spy_price_return_pct`, `excess_vs_spy_price_pct`.

## Strategy fingerprint guard
At creation, the portfolio stores its `strategy_id` (version + parameter hash) and a
**function-level code fingerprint**. The fingerprint is a sha256 of the source of
`backtest.indicators / retest_at / rs_history`, `WARMUP`, `core.market_regime / regime_mask`,
the paper `screener / portfolio / config / nyse` modules, and `store.is_late /
session_open_utc`.

If parameters or any fingerprinted code change, `daily` raises `StrategyChanged` and does
nothing. Continuing requires `--new-experiment <label>`: the old experiment is moved to
`paper/archive/<label>/` (never deleted) and a new forward portfolio starts. Versions are
never mixed. Snapshots and signal rows carry experiment, strategy id and code version.

## State persistence
* `scripts/persist_state.sh`: commit, then `pull --rebase`, then push, with 5 attempts.
  * On a conflicting remote change it aborts the rebase, **fails the job (exit 2)** and writes
    an error to the job summary. Nothing is overwritten, and conflicts are never auto-resolved.
  * If all 5 attempts fail it exits 1 with a loud error.
* Every run uploads `paper/state` + `paper/data` as an artifact (`paper-state-<run_id>`,
  90 days), even on failure.
* `paper_run.py restore <dir>` restores a backup **only if it strictly extends** the current
  state: same experiment, later `processed_through`, higher `revision`, and the current equity
  history is an exact prefix of the backup's. Otherwise it is refused. A stale backup can't
  overwrite later valid state.
* Workflow `concurrency` (no cancel) prevents two state updates at once.

## Snapshots and signal store
* `paper/data/snapshots/<signal_date>.json` is write-once:
  * an identical rewrite is a no-op; different content raises `ImmutableError`;
  * the file is chmod read-only, and its sha256 goes into `MANIFEST.csv` (`verify_snapshots`).
* Contents: strategy id/version, parameters, code fingerprint, experiment, source data
  timestamps (download time, bar date, yfinance version, tickers with a bar, latest bar, SPY
  last bar, universe hash), and all raw detections with decision-time features, flags and rank.
* **Tamper-evident, not tamper-proof:** the manifest lives in the same repository. Anyone with
  write access can change a snapshot **and** its manifest line together. Git history and the
  run artifacts are the external record. Use signed commits / an external timestamping
  service if tamper-proofing is required.
* `signals.csv` is append-only; the first write wins.
* `labels.csv` is filled only from bars ≤ the processed session. Each label has an
  `_observed` date and is never rewritten (also not on data revisions). Labels include
  portfolio decisions and trade results once they exist. The screener and the portfolio never
  read labels.

## Calendar
`paper/nyse.py` computes NYSE full-day holidays from rules (Saturday New Year's Day not
observed, so **2027-12-31 is a trading day**) plus listed special closures (2025-01-09). It is
tested against NYSE's published calendars for 2025–2028. `trader.py` (live bot, out of scope)
still has its own list.

## Equivalence checker
Every portfolio outcome is mapped explicitly (`verify.OUTCOME_MAP`):
* **`replay`** (1:1 with the reference decision log): `entered`, `ticker_open`, `positions`,
  `daily_entries`, `invalid`, `capital_or_risk`.
* **`simulate_excluded`** (no trade exists in the reference): `no_trade_open_below_stop`,
  `no_trade_max_risk`. They must be absent from the replay decisions and their condition must
  hold on the logged open.
* **`forward_only`**: `not_traded_late` — not allowed in verification.
* **`divergent`**: `expired_no_bar` — not allowed in verification.

Unknown outcomes fail the check.

## Tests
`python -m unittest test_paper test_task6_engine test_portfolio_bt` → **67 tests**.
`test_paper.py` (38) covers:
* equivalence (3 markets incl. missing bars × 3 configs; live scan path);
* no look-ahead; mechanics; persistence and timestamps; acceptance 1–4;
* six deterministic **outage scenarios** end-to-end through `daily()`;
* the fingerprint and parameter guards; stale-backup refusal and newer-backup restore;
* `persist_state.sh` conflict handling on real git repositories;
* the NYSE calendar vs official dates;
* outcome-mapping coverage, including simulate-excluded outcomes on synthetic data;
* metrics and labels.

Outage outputs: `research/results/task10/OUTAGE_SCENARIOS.md`
(`python research/task10b_outage_report.py`). Real-data equivalence:
`research/results/task10/VERIFY.md` (CI on this branch).

## Operation (after approval only)
Uncomment the cron in `.github/workflows/paper-daily.yml`. The first run starts the forward
experiment on that day. `python paper_run.py backfill 2025-01-02` writes a clearly labelled
reconstructed history to `paper/backfill/`, which is never merged with forward results.

## Known limitations
* Today's S&P 500 constituents and today's GICS sectors (survivorship / not point-in-time).
* Yahoo data can be revised; snapshots keep what was seen at decision time.
* Fills are simulated at the official open with 10 bps per side. No partial fills, no auction
  slippage.
* Orders for a ticker without a bar expire after 10 sessions (`expired_no_bar`). The replay
  engine would wait, which is why this outcome is flagged as divergent in verification.
