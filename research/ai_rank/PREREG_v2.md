# AI ranking v2: pre-registration (written BEFORE any v2 data is built or model trained)

Status: **draft for audit (Muse).** Nothing below may be changed after the audit without a
new version number and a note on why.

## 0. Ground rules
- **Research and shadow only.** No change to the live paper portfolio, the paper bot, their
  state, schedules, or any fingerprinted code (`paper/*`, `backtest.indicators/retest_at/
  rs_history`, `core.market_regime/regime_mask`, `store.is_late/session_open_utc`). CI asserts
  that the fingerprint `17454c61f631` is unchanged.
- **Base data.** PR #5 dataset (artifact run 38773034101): sessions 2021-10-15 → 2026-10-14.
- **Splits.** Purge by the label's true end: exit date, at least signal + 21 sessions
  (`engine.label_end`, `pipeline.splits_at`, commit a4ba326). Fixed boundaries:
  - validation starts 2025-03-17;
  - test starts 2025-12-30;
  - embargo 5 sessions.
- **The 2025-12-30 → 2026-10-14 window is NOT an independent test.** It was used to choose the
  strategy. It is reported once and never used for a decision.

## 1. Task
Rank the eligible **long retest** signals of the PIT S&P 500 (members on the signal day, RS
against that day's members) inside each day.

The eligible set is the production one: RS ≥ 85, SPY > MA50, valid stop. The ranker never adds or
removes signals; it only orders them.

Secondary (reported, never a decision basis): all four long setups.

## 2. Features (decision time = signal-day close; nothing later)
- **v1 set (19):** unchanged from `pipeline.MODEL_FEATURES`.
- **New information (v2):**

| Group | Feature | Definition | Look-ahead risk |
|---|---|---|---|
| Earnings | `sess_since_earn` | Sessions since the last reported earnings date ≤ signal day | none: the date is in the past |
| Earnings | `earn_within_5` | 1 if an earnings date falls within the next 5 sessions | **flagged**: we only know the date as eventually reported, not as scheduled at the time. Evaluated with and without it; the decision uses the model **without** it unless the two differ by less than the noise band |
| Sector | `sector_rs_median` | Median `rs_score` of the PIT S&P 500 members of the same sector on the signal day | sector labels are today's GICS (static): mild bias, noted |
| Sector | `sector_ret20_median` | Median 20-day return of the same members | same as above |
| Sector | `rs_minus_sector` | Own `rs_score` − `sector_rs_median` | same as above |
| Breadth | `breadth_ma50` | Share of PIT S&P 500 members with close > MA50 | none |
| Breadth | `breadth_new_high` | Share at a 252-day high | none |
| Breadth | `breadth_chg5` | 5-session change of `breadth_ma50` | none |

- **Earnings dates source:** `yfinance.Ticker.get_earnings_dates`. If fewer than 80 % of the
  signals get a past earnings date, the earnings group is dropped and the report says so.

## 3. Models (fixed now)
- **Ridge** (alpha in 1, 10, 100) and **gradient boosting** (depth 2 or 3; 100 or 300
  iterations; min leaf 200; learning rate 0.05).
- **Target:** net R after 10 bps, clipped to [−2, 6] for fitting only.
- No other model families, feature selection or tuning are allowed.

## 4. Selection and gates (fixed now)
- **Selection metric on validation:** mean daily Spearman rank correlation (days with ≥ 3
  eligible signals) between score and realised R. Portfolio return is only a tie-break, which
  avoids the v1 failure where a lucky portfolio path picked a model with correlation ≤ 0.
- **Walk-forward inside development:** train before year Y (purged), score year Y, for every year
  of 2023, 2024 and 2025 that has ≥ 500 training labels.
- **Gate to the shadow stage (all must hold):**
  1. mean daily rank correlation > 0 in **every** walk-forward year and on validation;
  2. pooled correlation ≥ 0.03 with a bootstrap 90 % interval (by day) above 0;
  3. the portfolio (same trades, capital, limits, costs) is not worse than RS-first by more than
     2 percentage points of return in any walk-forward year, and beats the median of random
     same-day orders on validation.
- **If the gate fails:** v2 is reported as failed and RS-first stays.

## 5. Shadow stage (only if the gate passes)
- **Freeze:** the model file and its sha256 are frozen.
- **Separate workflow**, run after the paper run. It reads `paper/data/snapshots/*.json` (read
  only), scores the eligible signals and keeps three books under `research/shadow/`:
  - the model order;
  - RS-first (it must reproduce the paper portfolio exactly, otherwise the run is invalid);
  - a fixed random order.
- **Evaluation:**
  - The first indicator is the forward rank correlation on all eligible signals, including those
    not traded (labels from `paper/data/labels.csv` once observable).
  - Portfolio comparison only after at least 6 months **and** at least 30 days on which ranking
    changed the entered set.
  - The test is evaluated exactly once, at the pre-agreed date.

## 6. Roles
- **Claude:** builds the dataset and features, and **stops before training** for the audit.
- **Muse:** audits the features and splits before training, then gives an independent evaluation
  against RS-first and the random baseline.
- **Owner:** decisions.
