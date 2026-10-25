# Long Breakout / Retest 10Y: diagnostic findings (exploratory)

- **Plan:** `PLAN.md` (the owner's, committed before any run).
- **Run:** `research/results/long_diagnostic/runs/2026-10-25T201301Z/` (GitHub Actions
  40229678717). An identical earlier run is kept unchanged: `2026-10-25T200940Z`, run
  40229384563. Its baseline results are identical; it lacks the R table and has the
  pre-fix 2017 regime row.
- **Full report with charts:** `REPORT.md` in the run folder.
- **Status:** diagnosis, not optimisation. No holding period, stop, RS or MA was changed.
  The ten years were already examined in PR #19, so nothing here is independent validation.
- **Research Breakout** enters at the next open. It is **not** the bot's pre-close
  breakout.

## A. Verified accounting (exact)
| Book | Return | Max DD | Executed | Reproduces PR #19 | Money reconciliation |
|---|---:|---:|---:|---|---|
| Breakout, 10 bps | −6.51 % | −47.66 % | 750 | yes (≤ 1e-6) | residual $0.0000, cash identity OK |
| Breakout, 25 bps | −43.07 % | −56.30 % | 752 | yes | OK |
| Retest, 10 bps | +1.26 % | −48.05 % | 592 | yes | OK |
| Retest, 25 bps | −20.06 % | −53.82 % | 597 | yes | OK |

- **Duplicates:** none among candidates or executions.
- **No look-ahead:** detection on data cut at 2021-12-31 gives identical candidates (entry,
  stop, RS) for every entry up to 2021-11-30: 12,140 Breakout and 5,919 Retest candidates.

**Exact decomposition of the 10-year result, 10 bps ($):**

| Component | Breakout | Retest |
|---|---:|---:|
| gross price P&L, time exits | +31,545 | +20,925 |
| gross price P&L, stops at the planned stop | −28,342 | −18,745 |
| extra loss: gaps through the stop | −2,050 | −739 |
| costs on closed trades | −2,077 | −1,240 |
| open positions at the end | +273 | −75 |
| **total** | **−651** | **+126** |

**The same, as R per closed trade:**

| Component | Breakout | Retest |
|---|---:|---:|
| time exits, gross | +0.705 | +0.551 |
| stops at the planned stop | −0.632 | −0.464 |
| gaps through the stop | −0.044 | −0.020 |
| costs | −0.052 | −0.032 |
| **net** | **−0.023** | **+0.035** |

## B. What quantitatively explains the low ten-year return
1. **The gross edge is about zero, and costs are larger than it (Breakout).**
   - Before costs Breakout earns **+0.029 R** a trade. The 10 bps costs alone take
     **0.052 R**. Gaps through the stop take another 0.044 R.
   - Retest: gross +0.067 R, costs 0.032 R.
   - The cost in R is high because stops are close: mean planned risk is 4.8 % (Breakout)
     and 7.3 % (Retest) of the entry price. A 20 bps round trip on a 4 % risk is 0.05 R.
   - Independent full replays confirm it: 10 → 25 bps moves Breakout from −6.5 % to −43.1 %
     and Retest from +1.3 % to −20.1 %.
2. **The win rate sits on the break-even line.**
   - Breakout: 31.7 % wins against a break-even 32.4 % (avg win +2.23 R, avg loss −1.07 R).
   - Retest: 42.0 % against 40.5 % (+1.37 / −0.93 R).
   - 63 % of Breakout and 46 % of Retest trades end at the stop.
3. **2018 and 2022 produced most of the loss**, by exit year:

   | | 2018 + 2022 | Other years |
   |---|---|---|
   | Breakout | 136 trades, mean −0.62 R, about −$4.6k | 609 trades, +0.11 R, about +$3.7k |
   | Retest | 123 trades, −0.25 R, about −$2.7k | 465 trades, +0.11 R, about +$2.9k |

   - In 2022 Breakout lost on 87.5 % of exits via the stop. January 2022: 10 of 10 exits
     were stops. November 2022: 11 of 11.
   - 2018 losses came in the February–April and October sell-offs, mostly stops.
   - Both books then took years to recover: the max drawdown runs from January 2018 to a
     trough in April 2023 (Breakout) and November 2023 (Retest). New highs came only in 2026.
4. **Bull years were also weak.**
   - 2019: Breakout −9.4 % while SPY was +28.8 % (price).
   - 2021: Breakout −4.3 % and Retest −9.3 % while SPY was +27.0 %.
   - Over 2017–2021 both books lose: Breakout −$2.1k, Retest −$3.4k. Over 2022–2026 both
     gain: +$1.2k and +$3.6k.
5. **Profit comes from a few large winners.** Without them the rest loses (arithmetic, not a
   re-simulated portfolio).

   | | Top 10 winners | Rest | Trades ≥ 3 R |
   |---|---|---|---|
   | Breakout | +$5.3k | −$6.2k (mean −0.13 R) | 59 trades, +$17.6k |
   | Retest | +$4.0k | −$3.8k | 23 trades, +$6.9k |

   - Every ≥ 3 R trade ended by the 20-day time exit; by construction a stop ends below
     entry.
6. **About half the capital is idle.**
   - Invested on average 62.6 % (Breakout) and 51.7 % (Retest) of equity.
   - Fully in cash on 15.7 % and 12.8 % of sessions.
   - Even with 5 slots full, 1 % risk with a 4–7 % stop gives about 15–25 % of equity per
     position.
   - Because the edge is negative or flat, more exposure would not by itself have helped
     here.
7. **Not material:**
   - dividends not credited: +$549 Breakout, +$415 Retest over ten years;
   - cash-limited entries: 8 and 0.

## C. Stops, 20-day exits and what happened after
- **Breakout stops (471):**
  - 62 stopped on the entry day;
  - 108 had been ≥ +1 R above entry before the exit day, 222 ≥ +0.5 R;
  - 68 gapped through the stop, losing an extra $2,050 (mean −0.48 R each).
- **Retest stops (273):** 13 on the entry day, 41 had been ≥ +1 R, 33 gaps (−$739).
- **20 sessions after a stop**, the close was back above the entry price in 38 %
  (Breakout) and 29 % (Retest) of cases. Most stops were "right" on that horizon.
- **Time exits:**
  - Breakout: mean intraday high during the hold +3.06 R, kept +1.87 R (gave back 1.19 R).
  - Retest: +1.80 R, kept +1.00 R.
- **After a time exit (hindsight, close to close):**

  | Book | +20 sessions, mean | % positive |
  |---|---|---|
  | Breakout | +2.3 % | 56.9 % |
  | Retest | +1.5 % | 55.3 % |

  - For the top-decile winners: −1.1 % at +5 and +3.4 % at +20 (Breakout).
  - These are hindsight labels with no market baseline. They do **not** show that a longer
    hold would be better: it would change slots, capital and later choices, and needs its
    own pre-registered full replay.

## D. Historical correlations (descriptive, already-seen data, not rules)
- **Breakout, tight stops:** stops < 2 % or 2–4 % of the price (340 trades) average
  −0.54 R and −0.10 R. Behind this:
  - more stop-outs: 93 % and 69 %;
  - more entry-day stops: 46 % and 11 %;
  - higher cost in R: 0.17 and 0.06.
  
  Stops above 6 % average +0.09 to +0.29 R.
- **Breakout, SPY below MA200 at the signal:** 92 trades, −0.31 R vs +0.02 R above. Retest
  shows no such difference.
- **Breakout skips (hypothetical R of skipped candidates):**
  - over the 3-a-day limit: 745 candidates, +0.19 R;
  - ticker already held: +0.11 R;
  - all slots full: −0.04 R;
  - trades actually entered: −0.02 R.
  
  These skipped trades overlap the entered ones and were not tradable with this capital.
  The pattern is not evidence that a different rule would earn more.
- **Selection funnel:** all candidates average −0.025 R (Breakout) and −0.009 R (Retest).
  Portfolio entrants average −0.023 R and +0.035 R. RS-first selection adds little.

## E. Data limitations (flagged, not corrected)
- **117 of 726 former index members have no price history** in the dataset. Delisted or
  acquired names cannot be traded, so the universe has survivorship bias. Its sign for
  these books is unknown.
- **Prices** are split-adjusted, not dividend-adjusted. No dividends and no cash interest are
  credited. SPY comparisons are price only.
- **Same-bar ordering:** the exit-day high/low order is unknown, so MFE including the exit
  bar is an upper bound. Entry-day stops are filled at the stop price.
- **Post-exit windows missing** at the data end: 2 / 7 / 15 trades (Breakout) and
  2 / 5 / 8 (Retest) at +5 / +10 / +20 sessions.

## Confidence
- **High:** reproduction; the $ and R accounting; cost sensitivity; counts.
- **Medium:** year and regime attribution. The equity curve compounds, and calendar-year
  equity return is not the same as exit-year P&L; both are shown.
- **Low:** every correlation in D and every post-exit observation in C. They are hypotheses
  for a separately pre-registered and forward-tested study, not changes to make.
