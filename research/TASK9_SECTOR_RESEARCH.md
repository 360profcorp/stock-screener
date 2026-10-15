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

## 7. Results (real data, CI run on GitHub Actions)

Reproducibility: two independent CI runs (commits 7e1425d and 1c9acaa) gave identical results.

Window: signals 2024-10-28 → 2026-10-14, 503 tickers (all with a GICS sector, 11 sectors),
3,760 Retest candidates (next-open entry) / 3,790 (close entry) after the frozen filters.
Single-path numbers are deterministic (RS-first, ties by ticker); Monte Carlo (MC) = 100 runs with
random order among equal-RS candidates. Full tables: `research/results/task9/REPORT.md`.

### 7.1 Baseline concentration (no sector limit) is high
| Max positions | Most positions in one sector | Days with ≥2 in one sector | Avg top-sector weight | Avg HHI | Largest sector share of position-days |
|---|---|---|---|---|---|
| 5 | 5 (all positions) | 73 % | 52 % | 0.44 | Information Technology 37 %, Industrials 20 % |
| 10 | 10 | 86 % | 47 % | 0.36 | Information Technology 41 % |
| 20 | 13 | 87 % | 44 % | 0.32 | Information Technology 38 % |

RS-first naturally clusters in the leading sector — at times the whole portfolio was one sector.

### 7.2 Next-open entry (the bot's Retest entry) — MC medians [5th–95th percentile]
| Max pos | Sector limit | Return % | Max drawdown % | Max same sector | Executed (single path) | Avg net R (single path) | Sector rejections |
|---|---|---|---|---|---|---|---|
| 5 | none | 80.8 [60.7–104.9] | −12.1 [−12.4…−12.0] | 5 | 140 | 0.61 | 0 |
| 5 | 1 | 49.3 [37.3–60.4] | −8.8 [−13.8…−7.8] | 1 | 146 | 0.37 | 333 |
| 5 | 2 | 72.3 [54.7–92.2] | −12.3 [−14.2…−12.2] | 2 | 143 | 0.48 | 75 |
| 5 | 3 | 76.1 [59.4–103.7] | −12.9 [−16.2…−12.0] | 3 | 144 | 0.50 | 20 |
| 10 | none | 124.7 [99.7–148.0] | −19.7 [−21.0…−17.0] | 9 | 285 | 0.36 | 0 |
| 10 | 1 | 56.3 [45.8–67.2] | −14.6 [−17.9…−13.1] | 1 | 219 | 0.23 | 2,878 |
| 10 | 2 | 57.6 [43.6–76.6] | −16.9 [−20.4…−14.2] | 2 | 278 | 0.19 | 641 |
| 10 | 3 | 95.9 [70.7–130.9] | −15.9 [−20.0…−14.9] | 3 | 276 | 0.47 | 227 |
| 20 | none | 116.8 [85.1–149.8] | −19.2 [−21.6…−16.8] | 12 | 416 | 0.21 | 0 |
| 20 | 1 | 55.2 [41.0–66.5] | −14.6 [−17.9…−12.9] | 1 | 219 | 0.23 | 2,884 |
| 20 | 2 | 44.5 [35.0–59.3] | −17.4 [−22.6…−14.1] | 2 | 327 | 0.10 | 2,057 |
| 20 | 3 | 69.0 [51.1–101.4] | −16.3 [−20.8…−14.6] | 3 | 370 | 0.12 | 1,202 |

(With 11 GICS sectors, limit 1 caps the portfolio at 11 positions, so 10 and 20 positions coincide.)

Close entry (single path, no MC) shows the same pattern but noisier — e.g. 5 positions:
none +63.7 % / DD −18.4 %, limit 1 +65.8 % / −9.3 %, limit 2 +41.4 % / −14.9 %, limit 3 +60.2 % / −14.6 %.

### 7.3 Findings
1. **Sector limits do what they are meant to do for concentration.** Max same-sector positions
   fall to the limit, HHI falls (5 pos: 0.44 → 0.28 at limit 1, 10 pos: 0.36 → 0.24).
2. **Downside reduction is real only for a strict limit.** Limit 1 lowers max drawdown and the
   worst 20-day loss consistently (5 pos MC median DD −12.1 → −8.8 %; 10 pos −19.7 → −14.6 %;
   worst 20-day −9.1 → −7.1 % and −14.6 → −8.7 %). Limits 2–3 barely change drawdown at
   5 positions; at 10 positions they reduce it by ~3–4 pp.
3. **The cost is large and systematic, not noise.** In every configuration return falls
   proportionally more than drawdown (least for limit 3 at 10 positions: −23 % vs −19 %), and
   per-trade quality falls: avg net R
   0.61 → 0.37 (5 pos, limit 1), win rate 50 → 43 %. The MC ranges of limit 1 and the baseline
   do not overlap at 5 and 10 positions. Interpretation: the Retest edge is concentrated in
   leading sectors (sector momentum); a sector cap pushes the portfolio into lower-ranked
   signals from weaker sectors.
4. **Return / drawdown (MC medians):** 5 pos — none 6.7, limit 1 5.6, limit 2 5.9, limit 3 5.9;
   10 pos — none 6.3, limit 1 3.9, limit 2 3.4, limit 3 6.0. No limit improves the
   risk-adjusted result; limit 3 at 10 positions is the only one that keeps it while cutting
   max drawdown by ~4 pp.
5. **Non-monotonic results** (limit 2 often below both 1 and 3; close vs open entry disagree on
   limit 1 at 5 positions) show strong path dependence — another reason not to pick a limit by
   the highest number.

### 7.4 Conclusion (no limit selected or deployed)
* Concentration risk is real: unrestricted, the portfolio is regularly 50 %+ in one sector and
  occasionally 100 %.
* Count-based sector limits reduce concentration, but only the strict limit (1) reliably reduces
  drawdown, and it costs roughly 40–55 % of the return (MC medians) and 0.1–0.25R per trade
  over this window.
* Evidence is insufficient to adopt any limit: one 2-year window dominated by one leading
  sector (Information Technology), current-snapshot sectors, today's constituents.
* Candidates for out-of-sample validation (not a recommendation to deploy): limit 3 with
  10 positions (similar return/drawdown ratio, lower drawdown), and risk-based alternatives
  that keep the leading-sector edge — e.g. cap a sector's share of total open risk (e.g. 40 %)
  instead of a position count, or cap only when sector breadth/momentum weakens.

### 7.5 Caveats
Sector map is today's GICS snapshot; universe is today's S&P 500; one window (late 2024–2026);
next-open MC covers order ties only, not parameter uncertainty; costs 10 bps per side;
no taxes/borrow; RS-first ordering is research-only and may differ from Muse's RS work.
