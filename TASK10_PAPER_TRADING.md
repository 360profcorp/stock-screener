# Task 10 — Retest RS-first daily screener and paper trading

Branch `feature/task10-paper-retest` (base: `fix/portfolio-engine-task6`, PR #2). **Not merged,
not deployed.** No broker connection, no live orders. The daily workflow is manual-only (cron
commented out). Task 9 sector limits stay off (`max_per_sector=None`). The trading bot,
`daily_scan.py`, RS calculation and Retest detection are unchanged.

## Dependencies
* **PR #2 (required):** `simulate(one_per_ticker=False, include_open=True, entry_at="open")`,
  pre-open sizing and `open_at_end="mark"` in `portfolio_bt.replay` are the reference the paper
  portfolio must match. This branch adds an opt-in `record_decisions` audit log to `replay`
  (default off → output unchanged; verified identical in 8 comparison runs).
* **PR #3 (not required):** no code used. Sector is only recorded as an ML feature.

## Components
| File | Purpose |
|---|---|
| `paper/config.py` | Frozen validated parameters (Retest, RS ≥ 85, stop −3 %, SPY > MA50, next-open entry, hold 20, $10k, 1 % risk, 20 % max position, 5 positions, 3/day, 10 bps) |
| `paper/screener.py` | Daily scan with the backtest's own functions on data truncated at the scan day; all raw detections with flags, as-of features and RS-first rank |
| `paper/portfolio.py` | Persistent session-by-session paper portfolio (`forward` / `backfill` / `verification` kinds) |
| `paper/store.py` | State, write-once snapshots + manifest, append-only signal store, observable-only labels, timing (`is_late`), versioning |
| `paper/metrics.py` | Return, CAGR, drawdown, PF, expectancy ($, R), win rate, exposure, SPY comparison |
| `paper/verify.py`, `paper_run.py verify` | Equivalence checks vs history and vs the replay engine |
| `paper_run.py daily` / `backfill` | Forward run after the close / reconstructed history in a separate tree |
| `paper_tab.py` | 📒 Paper dashboard tab (forward only; backfill in a separate, labelled expander) |

## Acceptance requirements
1. **Historical backtests, backfill and forward trading are separate.**
   Forward state lives in `paper/state` + `paper/data`, backfill in `paper/backfill/...`, and
   historical research in `research/results`. A state's `kind` is checked on load, so kinds can't
   be mixed. In a forward portfolio, a signal recorded at or after its execution session's
   09:30 ET open (`store.is_late`) is stored and logged as `not_traded_late`, never traded.
   When the runner catches up missed sessions, it processes exits and marks for positions that
   were already entered, and flags `processed_late`. Every ledger row carries `origin`. The
   dashboard computes forward metrics from forward state only.
2. **Immutable decision-time snapshots.** `paper/data/snapshots/<signal_date>.json` is write-once:
   identical rewrite = no-op, different content = `ImmutableError`, and the file is read-only on
   disk. Its sha256 goes into `MANIFEST.csv`, and `verify_snapshots()` detects tampering. Contents:
   * strategy id/version, all parameters and code fingerprints (sha256 of backtest, core,
     portfolio_bt and the paper modules);
   * source data timestamps: download time, bar date, yfinance version, tickers with a bar,
     latest bar, SPY last bar, universe hash;
   * every raw detection with decision-time features, flags and rank.

   `signals.csv` is append-only (first write wins).
3. **Next-open sizing and fill timing equal the Task 6 replay engine, without look-ahead.**
   Verification compares, session by session:
   * the exact candidate order;
   * the decision and reason per candidate (entered / ticker_open / positions / daily_entries /
     invalid / capital_or_risk);
   * share counts and fills/exits;
   * cash and holdings at every close;
   * equity and open positions at the end.

   A no-look-ahead test multiplies all later bars ×3 and requires an identical past.
4. **Rejected signals are stored; labels appear only when observable.**
   * Every raw detection is stored, including RS/market rejections and portfolio rejections
     (`orders_log`, and `decision` in `labels.csv`).
   * `labels.csv` is filled only from bars ≤ the processed session.
   * Each label records its observation date, and a written label is never changed (also not
     when data are revised).
   * The screener and the portfolio never read labels.

## Tests
`python -m unittest test_paper test_task6_engine test_portfolio_bt` → **52 tests, all pass.**
`test_paper.py` (23) covers:
* equivalence (3 markets incl. missing bars × 3 configs);
* scanner vs history;
* the live scan path;
* no look-ahead;
* fills, stops and time exits;
* gap below the stop;
* order waiting for a bar;
* persistence;
* catch-up and idempotency;
* the unfinished-bar guard;
* all four acceptance requirements;
* metrics and labels.

Real-data verification runs in CI on this branch only (`paper-verify.yml`). Its output is
`research/results/task10/VERIFY.md`.

## Operation (after approval only)
Enable the commented cron in `.github/workflows/paper-daily.yml` (≈ 16:45–17:45 ET). The first
run starts the forward portfolio on that day. `python paper_run.py backfill 2025-01-02` builds a
reconstructed history in `paper/backfill/` for comparison. It is always labelled backfill.

## Known limitations
* Today's S&P 500 constituents and today's GICS sectors (survivorship / not point-in-time).
* Yahoo data may be revised; snapshots preserve what was seen at decision time.
* Fills are simulated at the official open with 10 bps per side. No partial fills, no auction
  slippage.
* Orders for a ticker without a bar expire after 10 sessions. The replay engine waits
  indefinitely, so this only matters for halted or delisted names.
