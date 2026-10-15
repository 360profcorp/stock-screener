# Task 9 — Sector concentration risk research

Branch `research/task9-sector-concentration`, based on `fix/portfolio-engine-task6` (PR #2).
Research only: no change to RS ranking, Retest detection, the trading bot, the live scanner
or PR #2. Full auto-generated tables: `research/results/task9/REPORT.md`.

## 1. Sector data: sources and point-in-time limits

| Source | Classification | Point-in-time? | Cost / reliability | Use here |
|---|---|---|---|---|
| Wikipedia "List of S&P 500 companies" (already used by `core.get_sp500`) | GICS Sector + Sub-Industry | **No** — current snapshot only; page history can be scraped by date but is unreliable | free; changes when editors update | **primary** (snapshot saved with as-of date) |
| `datasets/s-and-p-500-companies` CSV on GitHub (current fallback) | GICS Sector | No | free; refreshed periodically | fallback |
| yfinance `Ticker.info['sector']` | Yahoo/Morningstar sectors (e.g. "Consumer Cyclical", "Financial Services") — **not GICS** | No | free; slow (1 request per ticker), rate-limited, fields sometimes missing | not used (inconsistent taxonomy) |
| SEC EDGAR submissions API (`sic`) | SIC codes | Partly (filings carry the SIC at filing time) | free; SIC ≠ GICS, coarse for tech/internet | possible cross-check |
| S&P Capital IQ / Compustat GICS history, MSCI GICS Direct, Sharadar, Norgate | GICS with effective dates | **Yes** | paid | needed for strict PIT research |

Known limits of the current approach:
* **Look-ahead in classification:** a stock's sector is assumed equal to today's for the whole
  window. The last broad GICS reshuffle (announced Dec 2022, effective March 2023: e.g. Visa and
  Mastercard IT → Financials, Target Consumer Discretionary → Consumer Staples) happened
  *before* the backtest signal window (late 2024 → 2026), so the residual error comes from
  individual reclassifications after corporate events. A GICS consultation (AI/semiconductor
  sub-industries, application software) runs July 17 – Oct 30, 2026; any resulting change would
  be announced by November 2026 and is not reflected here.
* **Survivorship:** universe = today's S&P 500 members (same limitation as all other backtests).
* **Missing sectors** fall into one `Unknown` bucket, which the sector cap treats as one sector
  (conservative). The count is reported in `meta.json`.
* Reproducibility: every run saves `sector_map.csv` (ticker, sector, as_of).

## 2. Module

* `sector_exposure.py` — `sector_map_from_universe`, `save/load_sector_snapshot`,
  `daily_exposure` (positions held at each close, by sector; exit day excluded),
  `concentration_metrics`, `sector_breakdown`, `downside_metrics`.
* `portfolio_bt.replay(..., sector_map=None, max_per_sector=None)` — optional cap on
  concurrent positions per sector; rejected candidates counted as `sector_limit` and per sector
  (`metrics['sector_limit_rejections']`). For pre-open entries, positions that exit later the
  same day still count (consistent with the Task 6 no-look-ahead rule). Default off is
  bit-identical to the Task 6 engine (16 synthetic comparison runs).
* Tests: `test_sector_exposure.py` (15). All 44 tests pass locally and in CI.

## 3–6. Study design (frozen parameters)

Retest, RS ≥ 85, stop buffer 3 %, hold 20, SPY > MA50, lookback 3; $10k, 1 % risk, 20 % max
position, 3 new entries/day, 10 bps per side, open positions marked at the end.
RS-first = same-day candidates by RS descending (ties by ticker), research-only.
Varied only: sector limit none / 1 / 2 / 3 × max positions 5 / 10 / 20 × entry next-open / close.
Robustness: 100 Monte Carlo runs with random order among equal-RS candidates (next-open entry).

Results and interpretation: see section 7 (filled from the CI run).
