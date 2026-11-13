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

## 11. Separate test L on the QuantRocket learning bundle (owner's instruction, 2026-10-26 21:56 ET)
Written before any QuantRocket data was accessed. No price of the bundle has been seen.

**Status:** test L is a separate check. It does **not** replace the 2007–2016 test U, which stays
INCONCLUSIVE.

### 11.1 Source, as published by QuantRocket (not yet verified on the data)
- **Bundle:** `usstock-learn-1d`, from the free "Learning and Evaluation" tier (no credit card).
- **Contents:** daily prices for all US stocks, 2007–2011, described as survivorship-bias-free
  (it includes stocks that later delisted).
- **Identifiers:** QuantRocket Sids, with symbol history.
- **Terms of use:** data for internal use only; no redistribution of the data or of anything it
  could be rebuilt from.

**Access requirements:**
- a QuantRocket account and its license key, which the owner creates;
- the QuantRocket Docker deployment. It cannot be reached from this session, but GitHub Actions
  runners can.

### 11.2 Checks before any return (each failure → INCONCLUSIVE, no backtest)
1. **License and ingestion.** The bundle ingests with the free license. Its calendar starts on
   2007-01-03 and ends on 2011-12-30.
2. **Identifiers.** Every fja05680 PIT S&P 500 ticker on a given day maps to exactly one Sid via
   the symbol as of that day.
   - Ambiguous or unmapped tickers count as missing.
   - Ticker reuse is resolved by the as-of date, never by today's symbol.
3. **Price basis compatible with the engine.**
   - Our engine uses split-adjusted OHLC that is **not** dividend-adjusted (Yahoo
     `auto_adjust=False`), with dividends kept separately.
   - Bundle prices are converted to exactly that basis: raw prices with split adjustments only.
   - Check: on the overlap with surviving tickers that Yahoo still serves (e.g. AAPL, MSFT, SPY),
     the converted closes must match Yahoo `auto_adjust=False` within 0.5 % on ≥ 99 % of
     sessions. Otherwise the basis is not compatible.
4. **SPY and BIL** are present for the whole window (BIL from 2007-05-30).
5. **Coverage ≥ 85 % in every year 2007–2011**, with the §10.6 definition. The survivorship split
   (stayed vs removed members) is reported.

### 11.3 Window, fixed now
- **T = bundle calendar session index 260 → 2011-12-30.** Index 260 is the first session after the
  engine's 260-bar warm-up (`bt.WARMUP`); that warm-up also covers SPY's SMA200 and the 252-day
  RS look-back.
- For a bundle starting on 2007-01-03 this session is **2008-01-15**. The run asserts it.
- One $10,000 book. No sub-periods: the window is about 4 years, like U1.

### 11.4 Strategy and engine
M exactly as in §10.1, through the same PR #19 code path. Nothing changes:
- detection, RS, filters;
- `trades_for`, `portfolio_bt.replay`, `CFG`;
- costs of 10, 25 and 50 bps;
- benchmarks `etf_book_v2` (SPY, 50/50 SPY/BIL, 50/50 SPY/cash), the same regimes, the named
  windows that fall inside T, and the same bootstrap.

### 11.5 Verdict for L (thresholds unchanged)
**PASS** only if all hold:
1. CAGR > 0 and profit factor > 1 at 10 **and** 25 bps.
2. Max DD ≥ −20.00 % at 10 bps.
3. CAGR ≥ that of 50/50 SPY/BIL and max DD no deeper, at 10 and 25 bps.
4. ≥ 30 closed trades (the sub-period threshold, since T has about the length of U1).
5. Every check of §11.2 passes.

**Outcomes:**
- **FAIL** if any of 1–3 fails while 4 and 5 hold.
- **INCONCLUSIVE** otherwise.

### 11.6 Handling of the licensed data in this public repository
The repository is public, so its Actions artifacts and logs are public too.
- No bars, bundle files or per-session prices are uploaded, committed or printed.
- Only aggregates are committed: coverage counts, mapping counts, basis-check statistics, book
  metrics, and trade counts / R statistics without prices.
- The license key is read only from a repository secret (`QUANTROCKET_LICENSE_KEY`), which the
  owner adds. It is never printed.

### 11.7 Owner's clarification and implementation details (2026-10-26 22:03 ET, before any data access)
**BIL.** BIL started trading on 2007-05-25 (first Yahoo bar 2007-05-30). It is needed only on
the trading window T, which begins 2008-01-15. No price before its launch is required, and its
absence before then never stops the study. §11.2.4 is to be read this way.

**Implementation, fixed before any data is seen:**
- **SPY and BIL from Yahoo** (`auto_adjust=False`, dividends as amounts). Both are survivors, so
  Yahoo has them in full.
  - They serve the market regime and the benchmarks.
  - SPY is restricted to the bundle's sessions. The run asserts that its calendar equals the
    bundle calendar.
- **Stock prices from the bundle**, exported inside the QuantRocket zipline container:
  - unadjusted daily bars, the `splits` table (zipline ratios) and `dividend_payouts`;
  - converted to split-only adjusted OHLC (volume divided by the same factor);
  - dividends kept as amounts and not used by the trading book (unchanged engine rule).
- **Universe keyed by Sid:**
  - each fja05680 snapshot's tickers are mapped to Sids by symbol history as of the snapshot date
    (at the earliest the first bundle session);
  - unmapped or ambiguous tickers stay as placeholders, so they count as missing in coverage;
  - RS is ranked among the members that have data, as before.
- **Basis check (§11.2.3):** AAPL, MSFT, XOM, JNJ, PG, KO, WMT, IBM against Yahoo
  `auto_adjust=False` closes. At most one of the eight may fail the ≥ 99 % within 0.5 % test.
- **Outputs committed:** only the aggregates listed in §11.6, plus the 10 bps equity curve
  (account values only, no prices).
