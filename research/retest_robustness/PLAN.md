# Retest RS-first — independent robustness check (plan, for approval)

**Draft written 2026-10-26, before any data download or run for this study.** It follows the
owner's instruction of 2026-10-26.

**Unchanged:**
- The strategy is not modified and nothing is optimised: no parameter, filter, stop, holding
  period, sizing or ranking change, and no variant search.
- Production, Paper, Trading, positions, stops, secrets and `TRADING=dry` are not touched. There
  are no real trades and no schedules. Nothing is merged into `main`; the PR stays Draft.
- **Nothing in this plan is run until the owner approves it.** After approval the plan is
  committed unchanged; later changes go into dated addenda written before the data they affect.

## 0. Which strategy ("M (Retest)") — owner to confirm
In earlier PRs "M" meant the **SPY > MA200 variant** (PR #19: "Retest M" and "Breakout M"). The
only Retest strategy that exists as running rules, in Paper, is **Retest RS-first** (Task 10,
`paper/config.py`, `strategy_id retest-rs-first/1.0+cfg.d4b20dc660ae`). This plan tests that
strategy, frozen exactly as below.
- If the owner meant **Retest + SPY > MA200**, the plan is the same with that one extra filter
  (PR #19 rule M).

| Rule | Value (frozen) |
|---|---|
| Detector | `backtest.retest_at(lookback=3, max_days=10, tol=0.02, min_pull=0.03)` |
| Signal filters | RS ≥ 85 (RS against the point-in-time S&P 500 members of that day); SPY close > SMA50 on the signal day |
| Stop | stop base × (1 − 3 %); entry bar: exit at the stop; later bars: exit at min(open, stop) |
| Entry | next session's open; pre-open sizing |
| Exit | stop, or the close of the 20th bar |
| Portfolio | $10,000; 1 % risk per trade; 20 % position cap; 5 positions; 3 new a day; RS-first, ties by ticker |
| Engine | `backtest.simulate(entry_at="open", one_per_ticker=False, include_open=True)` + `portfolio_bt.replay`, unchanged (the PR #19 / #22 path) |

## 1. What is already known (not independent)
**2016-10 → 2026-10 has been fully examined** (PR #13, #19, #22): it is development data.

| Book (10 bps) | Return | Max DD | Trades |
|---|---:|---:|---:|
| full 10 years | +1.3 % | −48.1 % | 592 |
| 2017–2021 | −30.4 % | −36 % | — |
| 2022 → | +70.7 % | −22.9 % | — |

- At 25 bps the full 10-year return is −20.1 %.
- On the PR #5 five-year dataset: +68.35 %, DD −19.20 %, 265 trades.
- The live Paper book has 8 sessions of genuine forward history: too short to count.

**So the question is:** does the 2022–2026 result reflect a durable edge, or one favourable
period? Only data the strategy has never been run on can answer that.

## 2. Data and periods
### 2.1 Independent period (the evidence)
**U = 2007-06-01 → 2016-10-21.**
- The strategy was never run on these years.
- The window ends one session before the start of the existing 10-year dataset, so there is no
  overlap.
- It starts after BIL's inception (2007-05-30), so the 50/50 SPY/BIL control exists for the
  whole window.

**Sub-periods**, each as its own $10,000 book:

| Sub-period | Dates | Contents |
|---|---|---|
| U1 | 2007-06-01 → 2011-12-30 | 2007–09 bear and GFC, recovery, the 2010 and 2011 corrections |
| U2 | 2012-01-03 → 2016-10-21 | low-volatility bull, 2015–16 correction |

**Data sources:**
- **Bars:** Yahoo daily OHLCV, `auto_adjust=False` as before. Downloaded once in GitHub Actions
  (free, no paid API) from 2006-01-03, which gives 260 warm-up sessions. Every file is hashed and
  the hashes are written down before the first run.
- **Universe:** point-in-time S&P 500 from the `fja05680/sp500` snapshots (they go back to 1996),
  the same source and code as PR #19.

### 2.2 Survivorship gate
Yahoo lacks many removed companies, and their absence flatters long results.
- **Coverage** = member-days with a usable bar ÷ PIT member-days, by year. It is reported with
  the list of members without data.
- **If coverage is < 85 % in any year of U, the verdict can be at most INCONCLUSIVE**, whatever
  the returns.

### 2.3 Reference only (not evidence)
- The 2017–2026 books are re-run with the identical code: same windows, 10 / 25 / 50 bps, the
  same benchmarks with the corrected dividend logic.
- The Paper forward record is reported as is.

## 3. Reproduction gate (first step after approval)
On the existing dataset (run 40152515701) the code must reproduce the PR #19 / #22 Retest
control:
- 10 bps: +1.26 %, −48.05 %, 592 trades;
- 25 bps: −20.06 %, −53.82 %, 597 trades;
- to ≤ 1e-6, with money reconciled to the cent.

**If it does not reproduce, the study stops** before any new period is opened.

## 4. Costs
- **10 bps** a side (base), **25 bps** (realistic stress), **50 bps** (extreme stress).
- ETF benchmarks at 2 bps.
- Dividends are not credited in the trading book (unchanged engine rule). The omitted dividends
  are reported separately.

## 5. Market regimes (descriptive, decided from SPY data up to the day before)
- **Trend:** SPY close > SMA200 versus below.
- **Volatility:** 20-day realised SPY volatility, annualised, with fixed bands:
  - < 12 % low;
  - 12–20 % normal;
  - > 20 % high.
- **Named windows** (book % vs SPY %, recovery time):

  | Window | Dates |
  |---|---|
  | 2007–09 bear | 2007-10-09 → 2009-03-09 |
  | Recovery | 2009-03-10 → 2010-04-23 |
  | 2010 correction | 2010-04-23 → 2010-07-02 |
  | 2011 correction | 2011-04-29 → 2011-10-03 |
  | 2015–16 correction | 2015-05-21 → 2016-02-11 |

**For each regime:** trades, mean R, profit factor, win rate, exposure, and the book's
contribution to return.
- The SPY > SMA50 entry filter means few trades in bear regimes; the cost of being out of the
  market in recoveries is also shown.

## 6. Reported for U, U1, U2 (and the reference books)
- **Performance:** final equity, total return, CAGR, max drawdown and its dates, time to
  recover, Calmar (CAGR / |max DD|), profit factor, mean R per trade, win rate.
- **Activity:** closed trades and open positions at the end, exposure, yearly returns,
  worst month.
- **Robustness:**
  - **Start-date sensitivity:** books of 4 years started on each January of 2007 … 2013 (7
    books); the spread of CAGR and DD.
  - **Concentration:** the share of net P&L from the best 5 trades and from the best year.
  - **Block bootstrap** by calendar month: 2,000 resamples, fixed seed, of the daily return
    difference against 50/50 SPY/BIL; the 95 % interval of the annualised difference.
- **Benchmarks, same windows:**
  - SPY total return (dividends reinvested, v2 logic);
  - SPY price only;
  - 50 % SPY / 50 % BIL, monthly rebalance;
  - 50 % SPY / 50 % cash (0 %).

## 7. Decision rule (proposed; fixed once approved)
**ROBUST** only if **all** hold:
1. **Profitable after costs:** on U at 10 **and** 25 bps, CAGR > 0 and profit factor > 1. Both
   sub-period books have return > 0 at 25 bps.
2. **Drawdown:** max DD ≥ −20.00 % on U, U1 and U2 at 10 bps (the owner's 20 % limit).
3. **Versus 50 % SPY / 50 % BIL** (U, at 10 and at 25 bps): CAGR ≥ the benchmark's **and** max DD
   no deeper than the benchmark's.
4. **Trades:** ≥ 100 closed trades on U and ≥ 30 in each sub-period.
5. **Data:** coverage ≥ 85 % in every year of U.

**Outcomes:**
- **NOT ROBUST** if any of 1–3 fails while 4 and 5 hold.
- **INCONCLUSIVE** if 4 or 5 fails.

**SPY:**
- Reported side by side (excess CAGR, DD difference), not a pass condition, because the
  strategy does not aim to beat SPY in bull years.
- A loss of more than half of SPY's return together with a DD no smaller than SPY's is reported
  as a finding.

**Expected difficulty, stated in advance:** on the seen 10 years the strategy had a −48 % DD, so
condition 2 is a hard test.

## 8. What is not done
- No parameter, filter or exit change.
- No new variants and no MA200 / breaker tests (PR #19 is closed).
- No use of the U results to tune anything.

**After the result:**
- **NOT ROBUST:** the owner decides about the Paper book. Nothing is changed automatically.
- **ROBUST:** it supports keeping the Paper book running unchanged. It is not a reason to trade
  real money without a separate decision.

## 9. Deliverables
- **Code:** `research/retest_robustness/run.py`, reusing the PR #19 path unchanged, plus tests:
  - reproduction;
  - no look-ahead (detection on data cut at a date gives identical earlier candidates);
  - cash identity.
- **Runner:** an Actions workflow triggered by a file, on this branch only.
- **Results:** `research/results/retest_robustness/runs/<UTC>/`, write-once. Contents: books,
  trades, equity curves, coverage per year, regime tables, `results.json` and `REPORT.md` with
  charts.
- **PR:** Draft, do not merge.

**Open points for the owner:**
- (a) confirm the strategy of §0;
- (b) approve or change the window U and the sub-periods;
- (c) approve or change the thresholds of §7, in particular −20 % and 85 % coverage.

## 10. Owner's approval and decisions (2026-10-26 09:49 ET), before any data or run
The plan is approved with these binding conditions.

1. **Object of study: the historical strategy M = Retest + SPY > MA200.** This is the PR #19
   variant M (`research/crisis/PREREG_CRISIS.md` §4): all rules of §0 plus SPY close > SMA200 on
   the signal day, both computed from bars up to the signal day. Nothing else changes.
2. **Reproduction gate (§3 replaced).** The exact PR #19 code path
   (`research/crisis/run.py` at `research/long-crisis-v1`), run on dataset 40152515701, must
   reproduce `research/results/crisis/runs/2026-10-25T0255Z/results.json` for
   `retest|M|{full,development,holdout}|{10,25}bps`, to ≤ 1e-6 in return and max DD and with
   equal trade counts. Reference values:

   | Window | Costs | Return | Max DD | Trades |
   |---|---|---:|---:|---:|
   | full | 10 bps | −4.3995 % | −45.3443 % | 557 |
   | full | 25 bps | −33.8579 % | −53.7683 % | 559 |
   | development | 10 bps | −24.2689 % | −30.8500 % | 283 |
   | development | 25 bps | −34.1337 % | −39.4539 % | 283 |
   | holdout | 10 bps | +49.6964 % | −22.0521 % | 276 |
   | holdout | 25 bps | +31.0048 % | −24.3969 % | 276 |

   The Retest control C is reproduced as well, as an extra check of the engine.
   **If the gate fails, the study stops: INCONCLUSIVE.**
3. **Independent period** U = 2007-06-01 → 2016-10-21, with sub-period books U1 2007-06-01 →
   2011-12-30 and U2 2012-01-03 → 2016-10-21. Each book starts with $10,000.
4. **Costs:** 10, 25 and 50 bps a side.
5. **Max drawdown −20.00 %.** Not to be changed.
6. **Coverage ≥ 85 % in every year of U.**
   - Coverage = PIT S&P 500 member-days with a usable Yahoo bar ÷ PIT member-days.
   - **Separate survivorship assessment**, reported:
     - coverage of members later removed versus members that stayed;
     - the removed members without data, with their membership spans;
     - members whose bars end before their membership ends;
     - a sensitivity book restricted to tickers that were still members at the end of U (the
       direction and size of the bias).
   - **If coverage < 85 % in any year, the study stops before the backtest: INCONCLUSIVE.**
7. **The other criteria of §7 stay:** CAGR, profit factor, trade counts (≥ 100 closed on U and
   ≥ 30 in each sub-period), and the comparison with 50 % SPY / 50 % BIL.
   - The benchmarks use the corrected dividend logic: `etf_book_v2` of PR #25, copied
     unchanged.
8. **If the gates pass, the research backtest is run without any parameter change.**
9. **Verdict names:**
   - **PASS** = all of §7 1–5 hold (= "ROBUST").
   - **FAIL** = any of §7 1–3 fails while 4 and 5 hold.
   - **INCONCLUSIVE** = the reproduction gate fails, the coverage gate fails, or §7 4 fails.
10. **No optimisation.** Nothing is tuned to results.
11. **Unchanged:** Production, Paper, `TRADING=dry` and `main`. PR #26 stays Draft.

### 10.12 Addendum (2026-10-26, after the first data run, before any backtest or return)
- The first download run (coverage 59–76 % a year) reported 308 tickers as "no valid bars". 112
  of them were still members at the end of U, many still trading today (EA, BK, EQR, IPG, …).
- So this is a download fault (empty frames from Yahoo in 100-ticker chunks), not missing
  history.
- **Fix:** empty tickers are retried one by one, in 2 rounds of one retry each (the first version, with 3 rounds of 4 back-off retries, would have exceeded the job's time limit and was cancelled). Nothing else changes: same
  tickers, dates, cleaning and coverage definition.
- The first run's files are kept.
- The gate stays at 85 %. If coverage is still below it, the verdict is INCONCLUSIVE.
- Renamed tickers (the old symbol is no longer on Yahoo) are **not** remapped by hand. They count
  as missing.
