# Bull flag v1: pre-registration (written BEFORE any real-data detection or return calculation)

Status: **draft for review** (ChatGPT: rules vs code; Muse: protocol and statistics). No
real-data signal, count or return has been computed. The rules below are the single main
version; they are not tuned on history.

## 0. Ground rules
- **Research branch only.** The live bot, paper portfolio, RS-first, risk and limits do not
  change. AI v2 stays frozen.
- **The history is already seen.** Everything from 2022-10 to 2026-10-14 is **exploratory**:
  it was looked at while choosing the existing strategies. Independent confirmation can only
  come from future data (section 7).

## 1. Universe, data, filters (same as the existing studies)
- **Universe:** point-in-time S&P 500 members on the signal day, with RS measured against that
  day's members. Today's list is reported as a secondary view.
  - *Difference from production* (which scans today's list): this is justified by PR #5, where
    today's list inflated breakout results from +56 % to +212 % through survivorship.
- **Data:** the PR #5 dataset (artifact run 38773034101; bars `3df57ff9…`; PIT source
  `36326709…`). Yahoo daily bars, `auto_adjust=False`.
- **Filters:** RS ≥ 85 (production formula); SPY close > MA50 on the signal day; at least 260
  bars of history (`backtest.WARMUP`).

## 2. Pattern rules (signal at the close of bar `i`; only bars ≤ `i` are used)
All parameters are fixed here. Notation: `H`, `L`, `C`, `V` are the daily high, low, close and
volume.

| # | Element | Exact rule |
|---|---|---|
| R1 | Flag top `T` | The **latest** bar with the highest `H` among bars `i−13 … i−4`. The flag is bars `T+1 … i−1`, so it lasts **3 to 12 sessions** |
| R2 | Top is the peak | `max(H[T−15 … i−1]) ≤ H[T]`: the top is the highest high of the pole **and** the flag. A longer flag whose real top lies outside the R1 window is therefore not re-read as a shorter flag |
| R3 | Pole (impulse) | `pole_low = min(L[T−15 … T])`, with its bar `P < T`. Pole gain `H[T] / pole_low − 1` **≥ 12 %**, so the pole lasts at most 15 sessions |
| R4 | Flag depth | `flag_low = min(L[T+1 … i−1])`. Depth `1 − flag_low / H[T]` must lie **between 3 % and 12 %** |
| R5 | Retracement | `(H[T] − flag_low) / (H[T] − pole_low)` **≤ 50 %** |
| R6 | Volume dries up | `mean(V[T+1 … i−1]) < mean(V[P … T])` |
| R7 | Upper boundary | `flag_high = max(H[T+1 … i−1])` |
| R8 | Breakout confirmation | `C[i] > flag_high` **and** `C[i−1] ≤ flag_high` **and** `V[i] > mean(V[T+1 … i−1])` |
| R9 | Level and stop base | `level = flag_high`; `stop_base = min(L[T+1 … i])` (the flag low, including the breakout bar) |

`T` is deterministic (R1), so there is at most one flag per ticker and day.

**Structural consequence, fixed before any data.** R1 and R8 imply
`C[i] > flag_high ≥ max(H[i−3 … i−1])`, which is exactly the production `breakout` rule with
lookback 3. **Every flag signal is therefore also a breakout signal on the same day.** The
flag cannot add new tickers or days beyond breakout. It can only be a **quality filter on
breakouts**. A test asserts this implication.

## 3. Execution, risk, portfolio (unchanged from production / the Task 6 engine)
- **Entry:** next session's open. No trade if the open is at or below the stop.
- **Stop:** `stop_base × (1 − 3 %)`. On the entry bar it fills at the stop; on later bars at
  `min(open, stop)` (a gap through the stop fills at the open).
- **Exit:** the stop, or the close of the 20th bar after entry. **No profit target.**
- **Costs:** 10 bps per side. **Stress scenarios:** 25 and 50 bps per side.
- **Portfolio:** `portfolio_bt.replay` with the frozen paper config: $10,000, 1 % risk per trade,
  5 positions, 3 new entries per day, 20 % cap per position, RS-first order within a day.

## 4. Comparisons (identical rules, costs and limits everywhere)
1. **Overlap**, for each eligible flag signal (ticker, day). Shares are reported as counts and %:
   - **same day:** breakout / retest / VCP / double bottom eligible on the same ticker and day
     (breakout must be 100 % by construction);
   - **near:** any of them eligible on the same ticker in sessions `i−5 … i`;
   - **new relative to retest + VCP:** no retest or VCP eligible on that ticker in `i−5 … i`.
2. **Flag vs other breakouts:** the flag subset against breakouts that are *not* flags, on the
   same days and with the same filters.
3. **Portfolio, still 5 slots:**
   - (a) retest only (the control);
   - (b) retest + flag;
   - (c) retest + all breakouts (reference);
   
   all RS-first.

## 5. Statistics
- **Signal-level metric:** net R per non-overlapping model trade. Mean, median, win rate,
  profit factor, and the count of non-overlapping trades.
- **Uncertainty:** 90 % bootstrap interval, resampling **calendar months** as blocks, 5,000
  draws, seed 20261020.
- **Years:** 2023, 2024, 2025 and 2026 to Oct 14 reported separately. Q4 2022 is shown but not
  used in criterion S5.

## 6. Success criteria for the exploratory history (fixed now)
To justify a forward test, **all** of S1–S5 must hold:
- **S1:** at least 100 non-overlapping eligible flag trades.
- **S2:** mean net R (10 bps) > 0, with the lower bound of the 90 % interval > 0.
- **S3:** mean net R at 25 bps per side > 0.
- **S4:** flag mean net R − non-flag breakout mean net R > 0, with the lower bound of the 90 %
  interval > 0 (the flag must be a better breakout).
- **S5:** mean net R > 0 in at least 2 of the 3 full years 2023–2025.

**S6 (portfolio, decides whether a forward test adds the flag to the retest book):**
book (b) return ≥ book (a), and (b)'s max drawdown no deeper than (a)'s by more than 3
percentage points.

If S1–S5 fail, the flag v1 is reported as failed. There is no re-parametrisation in v1; any
change is a new version with a new pre-registration.

## 7. Independent confirmation (future data only)
- **If S1–S5 pass**, the owner may approve a **shadow paper book**: flag-only, plus retest +
  flag if S6 also passed. It runs from the freeze date on live daily data, without touching the
  live paper portfolio.
- **Evaluation date T:** the first session on or after freeze + 6 months with at least 30
  closed flag trades; otherwise freeze + 12 months.
- **At T,** the same S2–S4 criteria apply to the forward trades. Until T only counts are
  published.

## 8. First deliverable (this step)
This document, the detector `research/bull_flag/rules.py`, and synthetic tests (including
invariance to future bars and the breakout implication). **No real-data detection, counts or
returns** until ChatGPT and Muse have reviewed this pre-registration.

## Change log
- 2026-10-20, before any real data: R2 was widened from "no flag bar above the top" to "the top
  is the highest high of bars T−15 … i−1". A synthetic test showed that a 13-session flag could
  otherwise pass as a 12-session flag starting at its first bar. This was found from synthetic
  data only.
