# Breakout + MA200: Turnover & Selection Audit (pre-registration)

Written **before** any new calculation, on 2026-10-25, following the owner's task.

**Unchanged:**
- **Control M** and **variant B** are exactly as in PR #23 (`research/breakout_ma200/run.py`:
  `CR.eligible(sig, True)`, `runner_exit`). Neither is changed.
- Production, Paper, Trading, risks and `TRADING=dry` are not touched.
- Earlier results are kept; nothing is merged into `main`.

**Status: exploratory.** The ten years were already examined. The 2017–2021 history misses
many former index members: 20.6 % of PIT member-days in 2017 have no price. Nothing here is
independent confirmation. Research Breakout buys at the next open; this is not a test of
`trader.py`'s pre-close purchases.

**Common settings.** Data: run 40152515701. Portfolio: `portfolio_bt.replay` unchanged
($10,000, 1 % risk, 5 positions, 3 a day, 20 % cap, RS-first). Every book is a full
sequential replay from the start; no trade is ever removed from an already computed P&L.

**Windows:** full, 2017–2021, 2022–2026. **Costs:** 10 and 25 bps per side.

**Reproduction gate.** M and B must reproduce PR #23
(`research/results/breakout_ma200/runs/2026-10-25T205752Z/results.json`) exactly. The check
is ≤ 1e-6 on return and max DD, with equal trade counts, for full, 2017–2021 and 2022–2026
at 10 and 25 bps. If the gate fails, the run stops.

## 1. Where B's advantage comes from
**(a) Exact accounting split of profit_B − profit_M**, in $ and in R, for each window and
cost:
- identical trades (same ticker, entry and exit), where only the sizing differs because
  equity differs;
- trades with the same entry but a different exit (runners): the extension effect at the
  trade level;
- trades only in B;
- trades only in M;
- the difference in open positions at the end.

**(b) Isolating book B0 (slot effect without extension gain).** Same candidates and exit
dates as B. Every runner, however, is closed at M's day-20 close price, on B's later exit
date: it keeps its slot for as long as in B but earns exactly M's day-20 result. Between
day 20 and the exit it is marked at actual closes.

Then:
- `B0 − M` = the slot / turnover / composition effect;
- `B − B0` = the price effect of extending the runners.

## 2. Random controls (full sequential replays, seeds fixed in advance)
**R1 — random entry reduction to B's turnover.**
- **Rule:** every M candidate is dropped independently with probability q, then M is
  replayed unchanged.
- **Calibration:** q is set **before** the evaluation, on calibration seeds 1001–1020, by
  bisection to 0.001. The target is the mean number of executed trades of the full 10 bps
  book equal to B's.
- **Evaluation:** seeds 1–200 with that q, at 10 and 25 bps, on the full window and both
  halves.

**R2 — random runners (selection of the extended positions).**
- Every M time exit is first given the B trailing exit (2 × ATR14, never below the stop,
  hard exit at session 40) **without** the +2 R condition.
- Each seed then extends a random set of these time-exit candidates, the same number as B's
  candidate-level runners (2,934). All others exit at day 20.
- Seeds 1–200; 10 and 25 bps; full window and both halves.
- **Purpose:** to test whether choosing the strong (+2 R) positions matters, or whether any
  extension (and its slot occupancy) gives the same.

**Per control book:** return, CAGR, max DD, PF, trades, turnover (traded notional per year /
mean equity) and mean invested share. B is placed in each distribution as a percentile.

## 3. Why candidates average < 0 R while the trades M takes average > 0 R
**Candidate-level chain** (net R at 10 bps, closed candidates; no sizing):

| Step | Set |
|---|---|
| μ_all | every M candidate |
| μ_day | each day weighted equally (mean of daily means). μ_day − μ_all = **crowding**: days with many signals |
| μ_rand3 | at most 3 random candidates a day; analytic expectation = the mean over days of the daily mean, weighted by min(n, 3). μ_rand3 − μ_all = the **daily-limit / crowding** effect |
| μ_top3 | the 3 highest-RS candidates a day (RS-first, ties by ticker). μ_top3 − μ_rand3 = the **RS-first** effect |
| μ_entered | the trades M's portfolio actually took. μ_entered − μ_top3 = the **slot / ticker-held / capital / sequence** effect |

**Market regime:** every step is repeated within regime terciles, cut by the day's SPY
20-session return and by the day's number of candidates (signal breadth). The terciles are
fixed on all candidate days of the full window.

**Portfolio-level RS-first check:** M with a **random same-day order** instead of RS-first,
200 seeds, full 10 bps. RS-first's percentile in that distribution is reported.

## 4. Decision on B (applied unchanged)
**B shows a convincing advantage beyond turnover reduction only if all of these hold:**
1. B's full-window **CAGR is above the 90th percentile of R1** at **both** 10 and 25 bps;
2. B's full-window **PF is above the 80th percentile of R1** at both costs;
3. B's max DD at 10 bps is not more than 3 points deeper than R1's median;
4. the extension price effect **B − B0 is positive** at both costs on the full window.

**If any condition fails,** the report says plainly: **do not implement B.**

Beating R2 is reported as information on runner selection.

## 5. Context only
The completed `research/breakout-causes` run uses control C (no MA200), a different base
strategy. Its numbers are quoted only as context in a separate section and are never mixed
with M / B results.

## 6. Outputs
`research/results/turnover_selection/runs/<UTC>/` (write-once):
- `REPORT.md` with charts;
- `results.json`;
- the control distributions (CSV);
- the split tables;
- `provenance.json`.
