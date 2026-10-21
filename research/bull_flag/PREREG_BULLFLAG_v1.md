# Bull flag v1.1: pre-registration (written BEFORE any real-data detection or return calculation)

Status: **v1.1. ChatGPT's review applied** (two separated experiments, an exact S4 calculation,
an unambiguous combined portfolio, breakouts kept for forward checks). Waiting for Muse's
review. (ChatGPT: rules vs code; Muse: protocol and statistics). No
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

## 4. Two separate experiments (identical filters, costs and limits)
**Experiment A — filter value (decides S4).**
- Population: every eligible production **breakout** (lookback 3; RS ≥ 85; SPY > MA50; PIT
  S&P 500). Each one is labelled **flag** (`flag_at` fires on that ticker and day) or
  **non-flag**.
- **Both groups use the breakout's own stop and exit:** `stop = breakout level × 0.97`, where
  the level is the high of the previous 3 bars. Entry at the next open, stop or 20 sessions,
  10 bps per side. So the only difference between the groups is the pattern filter.

**Experiment B — full strategy.**
- The flag with its **structural stop** (`flag low × 0.97`, R9) and the same entry, exit and
  costs. S1, S2, S3 and S5 are evaluated here; the portfolio test S6 uses this version.

## 4.1 Overlap with other setups (reported, no criterion)
For each eligible flag signal, report counts and %:
- **same day:** breakout / retest / VCP / double bottom eligible on the same ticker and day (breakout
  must be 100 %);
- **near:** any of them in sessions `i−5 … i`;
- **new relative to retest + VCP:** none of those eligible on that ticker in `i−5 … i`.

## 4.2 S4 calculation (Experiment A, fixed now)
1. **Overlapping trades.** Within each ticker, all eligible breakouts form one sequence: a
   breakout is skipped while that ticker's previous kept breakout trade is still open,
   whatever its group (production `one_per_ticker` rule, `engine.non_overlapping`). The kept
   trades are then split into flag and non-flag.
2. **Matched days.** Only signal days with at least one kept flag trade **and** at least one
   kept non-flag trade count. Trades still open at the data end are excluded.
3. **Day weighting.** Per matched day `t`: `d_t = mean net R(flag trades of t) − mean net
   R(non-flag trades of t)`. Each matched day weighs the same. The statistic is `S4 = mean_t(d_t)`.
4. **Bootstrap.** Resample the **calendar months** that contain matched days, with
   replacement, 5,000 draws, seed 20261020. Each draw takes **the same months for both groups**
   (the paired `d_t` of those days) and recomputes `mean(d_t)`. The 90 % interval is that of
   the **difference**.
5. **S4 holds** if `S4 > 0` and the lower bound of the 90 % interval > 0 (base 10 bps). The
   25 bps value is also reported.
6. **Sensitivity (reported, no criterion):** S4 without the overlap rule, i.e. all eligible
   breakouts.

## 4.3 Portfolio books (still 5 slots, `portfolio_bt.replay`, frozen paper config)
- **(a) control:** retest only.
- **(b) retest + flag** (Experiment B stop).
- **(c) retest + all breakouts** (reference).

Candidate rules for (b) and (c), fixed now:
1. **One order per ticker and day.** If a ticker has a retest and a flag (or breakout) on the
   same day, there is a single candidate: the **retest**, with the retest's stop and entry.
   The control book's decision for that ticker is therefore never changed.
2. **Same-day order:** RS descending. On equal RS, retest before flag/breakout. Then ticker
   alphabetically.
3. **Filling the 5 slots:** in that order, with the existing replay rules. A held ticker is
   skipped (`ticker_open`); at most 3 new entries per day; sizing at 1 % risk from the pre-open
   equity; 20 % cap per position; no trade if the open is at or below the stop.

## 5. Statistics
- **Experiment B, signal level:** net R per non-overlapping model trade (same overlap rule,
  within the flag group). Report mean, median, win rate, profit factor and the count.
- **Uncertainty:** 90 % bootstrap interval resampling calendar months, 5,000 draws, seed
  20261020.
- **Years:** 2023, 2024, 2025 and 2026 to Oct 14 reported separately. Q4 2022 is shown, not used in
  S5.

## 6. Success criteria for the exploratory history (fixed now)
**All** of S1–S5 must hold to justify a forward test:
- **S1 (B):** at least 100 non-overlapping eligible flag trades.
- **S2 (B):** mean net R (10 bps) > 0, with the lower bound of the 90 % interval > 0.
- **S3 (B):** mean net R at 25 bps per side > 0.
- **S4 (A):** as defined in 4.2.
- **S5 (B):** mean net R > 0 in at least 2 of the 3 full years 2023–2025.

**S6 (portfolio):** book (b) return ≥ book (a), and (b)'s max drawdown no deeper than (a)'s by
more than 3 percentage points. It decides whether a forward test adds the flag to the retest
book.

If S1–S5 fail, flag v1 is reported as failed. No re-parametrisation in v1.

## 7. Independent confirmation (future data only)
- **If S1–S5 pass**, the owner may approve a **shadow paper book**: flag-only, plus retest +
  flag if S6 also passed. It runs from the freeze date on live daily data, without touching the
  live paper portfolio.
- **Evaluation date T:** the first session on or after freeze + 6 months with at least 30
  closed flag trades; otherwise freeze + 12 months.
- **At T,** the same S2–S4 criteria apply to the forward trades. Until T only counts are
  published.
- **The shadow run records every eligible breakout** (flag and non-flag) with its label, the
  breakout-stop trade and the structural-stop trade. Experiment A / S4 can then be re-checked
  independently on future data, not only the flag book.

## 8. First deliverable (this step)
This document, the detector `research/bull_flag/rules.py`, and synthetic tests (including
invariance to future bars and the breakout implication). **No real-data detection, counts or
returns** until ChatGPT and Muse have reviewed this pre-registration.

## Change log
- 2026-10-20, before any real data: R2 was widened from "no flag bar above the top" to "the top
  is the highest high of bars T−15 … i−1". A synthetic test showed that a 13-session flag could
  otherwise pass as a 12-session flag starting at its first bar. This was found from synthetic
  data only.
- v1.1 (2026-10-20, ChatGPT's review, before any real data):
  - Experiments A (filter value, breakout stop for both groups) and B (full strategy,
    structural stop) are separated.
  - The S4 calculation is fixed: combined overlap rule, matched days, equal day weights,
    paired month bootstrap of the difference.
  - The combined-portfolio candidate rules are fixed: one order per ticker and day, retest
    first; RS order with retest winning ties; 5-slot filling.
  - Forward runs record all breakouts.
