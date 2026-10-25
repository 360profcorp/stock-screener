# Breakout + MA200 — Quality & Exit Study v1 (pre-registration)

Written **before** any calculation of this study, on 2026-10-25, following the owner's task.

**Question.** Can Breakout + MA50 + MA200 be improved without more risk and without fitting
parameters to historical returns?

**Research only:**
- Production, Paper, Trading, risk, the stops of existing books and `TRADING=dry` are
  unchanged;
- nothing is merged into `main`;
- earlier results are kept unchanged.

**Status: exploratory.** The 2017–2026 data were already examined (PR #19, #22). No result
here confirms a strategy; only a future independent forward test can.

**Execution model.** The research Breakout buys at the **next session's open**. It does
**not** test `trader.py`'s actual pre-close purchases. A dedicated check (§5) verifies that
every entry is the next session's open.

## 1. Data and control M
- **Data:** dataset run 40152515701 (sessions 2016-10-24 → 2026-10-23), loaded with
  `research.crisis.run.load` / `build`. Universe: PIT S&P 500 membership. No new download.
- **Control M (PR #19 variant M):**
  - eligible if PIT member, RS ≥ 85 (`rs_pit500`), **SPY > MA50 and SPY > MA200** on the
    signal day;
  - Breakout with lookback 3, entry at the next open, stop = base × 0.97;
  - exit by stop (a gap fills at the open; on the entry bar at the stop) or at the close of
    the 20th bar.
- **Portfolio:** `portfolio_bt.replay` unchanged: $10,000, 1 % risk, 5 positions, 3 new a
  day, 20 % notional cap, RS-first, open positions marked at the end.
- **Reproduction gate:** M must equal PR #19
  (`research/results/crisis/runs/2026-10-25T0255Z/results.json`). Tolerance is 1e-6 on
  return and max DD, with an equal trade count, for:
  - full window at 10 and 25 bps;
  - development and holdout at 10 and 25 bps.

  Reference: full window at 10 bps is +47.84 %, CAGR 4.46 %, max DD −32.69 %, 690 trades.
  **If the gate fails, the run stops.**

## 2. Stage 1 — diagnostic of M itself
The PR #22 diagnostic is repeated on M, recomputed from M's own trades. Nothing is carried
over from the Breakout book without MA200. It covers:
- **Exits:** stops and time exits, MFE/MAE, gaps through the stop, entry-day stops, the
  20-day exit and what happened after it.
- **Selection:** entry quality (RS, risk at the open), the candidate funnel and skips by
  reason.
- **Results:** P&L by year, capital deployment, concentration.
- **Exact P&L split** into signal quality / entry gap / stop gap / costs, with the risk at
  the signal close as the R unit. The parts add up to net P&L.
- **Post-exit return vs SPY** on the same dates.
- **2018, 2019 and 2021:**
  - monthly book returns, exits and stops;
  - exposure;
  - the trades of control C that the MA200 filter removed, with their hypothetical outcome
    (diagnostic only).

## 3. Stage 2 — hypotheses (one fixed variant each; A+B is not tested)
### A. Quality filter
- **Rule:** exclude a candidate when the distance from the **actual entry price** (the next
  session's open) to the **original technical stop** is below 4 % of the entry price, i.e.
  `(open − stop) / open < 0.04`.
- **Fixed:** the stop is never widened and the risk per trade stays 1 %. Everything else is
  M.

### B. Runner exit
1. **Decision point.** At the close of the 20th session after entry (bar e + 20, where the
   control exits by time), compute the unrealised R:
   `(close_{e+20} − entry) / (entry − stop)`.
2. **Runners.**
   - If the unrealised R is **≥ +2.0**, the position becomes a runner. Every other position
     exits at that close exactly as in M.
   - A position stopped before bar 20 is unchanged.
3. **ATR(14).** The engine's `atr14`: the simple 14-session mean of the true range,
   max(H − L, |H − C_prev|, |L − C_prev|), from bars up to and including the session it is
   dated.
4. **Trailing stop for session j ≥ e + 21.** It is set from information up to the close of
   session j − 1:
   - `level_j = max(level_{j−1}, original stop, max close(e … j−1) − 2 × ATR14_{j−1})`;
   - `level_{e+20}` = original stop.
   
   The level never moves down.
5. **Stop execution** works like the original stop:
   - if the session low `L_j ≤ level_j`, exit at `min(O_j, level_j)` (a gap below the level
     fills at the open);
   - checked from session e + 21.
6. **Hard exit** at the close of session **e + 40**. If the data end first, the position is
   marked at the last close, as the engine does.
7. **Slots.** A runner keeps its slot. The portfolio replay accounts for the slots it
   blocks.

## 4. Stage 3 — robustness (reported for M, A, B)
- **Costs:** 10, 25 and 50 bps per side; independent full replays.
- **Windows:** full (2017-11-03 → 2026-10-23); 2017–2021 (→ 2021-12-31); 2022–2026
  (2022-01-03 → end). Each window is a fresh $10,000 book.
- **Metrics:**
  - CAGR, max DD, profit factor, expectancy (R), win rate, trades;
  - turnover: traded notional per year / mean equity;
  - mean invested share of equity.
- **SPY:** price-only buy-and-hold, with return, CAGR and max DD on the same windows. Its
  risk and exposure differences are explained.
- **Random-removal benchmark for A:** 200 books (seeds 1–200) remove the same number of
  candidates at random. Full window, 10 bps.

## 5. Checks
- **Next-open execution:** for every M candidate, the entry date is the stock's next session
  after the signal day, and the entry price equals that session's open.
- **No look-ahead:**
  - detection on data cut at 2021-12-31 gives identical M candidates (entry, stop, RS) for
    entries up to 2021-11-30;
  - B's trailing level uses data up to j − 1 only (tested).
- **Gaps and slots:** gaps fill at the open (engine rule); slots are owned by the portfolio
  replay.
- **Missing history of former members:** per year, the PIT member-days without price
  history and the members never tradable. Their effect on returns cannot be measured and is
  reported as a limitation.

## 6. Decision (applied unchanged)
**A hypothesis is "supported (exploratory)" only if all of these hold:**
1. full window, **CAGR > M at 10 and at 25 bps**;
2. full window, **PF > M at 10 and at 25 bps**;
3. max DD at 10 bps not more than 3 points deeper than M's;
4. **CAGR > M in both 2017–2021 and 2022–2026** at 10 bps;
5. for A only: full 10 bps return above the **80th percentile** of the random-removal books.

**Otherwise "not supported".** The 50 bps results are a stress test and are reported, not
used in the decision. Even "supported" means only a candidate for a separately approved
forward test. No paper book is started.

## 7. Outputs
`research/results/breakout_ma200/runs/<UTC>/` (write-once):
- `REPORT.md` with tables and charts;
- `results.json`;
- trade lists and equity curves per book;
- the diagnostic CSV and JSON;
- `provenance.json`.
