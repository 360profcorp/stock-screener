# Long Breakout / Retest: 10-year failure diagnosis — frozen plan

**Research only; no strategy optimization.** Parent research branch `research/long-crisis-v1`; never modify or merge the live bot, paper portfolios, pending orders, their state, or `TRADING=dry`. This study uses historic data already examined in PR #19. All cuts and findings are therefore **exploratory** and cannot confirm an improved trading rule. No new parameter will be recommended as validated based on this decade.

## Exact baseline and inputs

- Freeze current (pre-study) `research/crisis/PREREG_CRISIS.md` and `research/results/crisis/runs/2026-10-25T0255Z/results.json` from PR #19. Cite SHA256 of these and both 10-year dataset inputs.
- 10-year dataset GitHub Actions run `40152515701`, session dates 2016-10-24 .. 2026-10-23, use existing `research.crisis.run.load`/`build` PIT S&P 500 membership. No new fetch or changes in data provider, universe, RS or detection.
- Exactly baseline **C** for Breakout and Retest, independent long-only books. Eligibility: PIT S&P 500, RS≥85, SPY close>MA50; research Breakout/Retest entered **at next open**, stop at stop_base × .97, exit by stop/gap or time close of 20th bar; 10/25 bps **per side**; 1% risk, max 5 positions, max 3/day, max 20% notional per name, $10k, RS-first. NOTE: `trader.py` Breakout pre-close entry is a *different* execution and not covered by this study.
- Rerun baseline with `record_decisions=True` for diagnostics and fail closed if for each strategy and each bps scenario total return, max DD and trade count differ from PR #19 by >1e-6; verify net P&L reconciliation and no duplicated ticker-entry keys. Write outputs to timestamped `research/results/long_diagnostic/runs/<UTC>`, never overwrite historic files.

## Questions, in analysis order (descriptive, NOT candidate trading changes)

1. **Entry edge / portfolio selection.** Separate *all eligible signals*, *non-overlap model trades*, *portfolio entrants*, *skips by reason*; show counts, expectancy in R, profit factor, average wins/losses and which constraints select winners. Never add R of hypothetical skipped overlapping trades to actual realized portfolio P&L. Estimate concentration in top 5 / 10 winners; compare 2017–2021 vs 2022–2026 without refitting.
2. **Exits and slippage.** Stop/time counts, median R, expectancy, P&L dollars, win rates, the stop-gap component (realized gap fills below planned stop). Study MFE/MAE *during held window* (high/low data may not resolve same-bar order; high/low on exit bar are optimistic bounds). Classify exits by reason and observed market regime and year. Count stop day / time exit / open outcomes separately.
3. **Time limit diagnostic, not a hypothetical equity curve.** For trades actually closed at day 20, report subsequent **close-to-close** +5/+10/+20-session returns and % positive. These are after-exit hindsight and cannot be interpreted as realizable incremental portfolio alpha; adding longer holding periods would change slots, capital and future choices. Do not claim a longer hold is better until a separately pre-registered and forward tested full portfolio replay.
4. **Market regimes.** 2018, COVID crash/recovery, 2022 bear/rebound, 2023–26; win rate, expectancy, drawdown, exposure per actual historical return. Do not confuse calendar-year equity-return breakdown with net P&L by exit-year. Compare full books with SPY **price-only** comparison; state dividend and cash-yield treatment.
5. **Capital deployment and cost drag.** Measured daily invested share `(equity−cash)/equity`, mean open positions, share fully cash, time all slots full, cash-limited vs slots-limited skips; distinguish book exposure and signal availability. Compare independent full replays at 10/25bps, never infer cost drag solely by subtracting per-trade R.
6. **Data issues.** Point-in-time member completeness; missing former/delisted prices, corp actions and prices `auto_adjust=False`; dividend handling for longs, SPY price-only comparison; absent dividends/cash yield, no intraday stops or accurate after-hours fills, entry-day OHLC ambiguity. Flag errors/unknowns, do not invent corrections in the baseline study.

## Outputs / acceptance

- `REPORT.md` with baseline reproduced, exact window, control exposures, trade-level exits and net P&L, by-year and 2017–21 vs 2022–26, MFE/MAE and post-exit close returns, cost sensitivity, top-10 winners, broker execution mismatch note, limitations and explicit confidence levels.
- CSVs for closed fills, missing-data/coverage statistics, and daily curve. JSON `reconciliation.json` (baseline identity verified), `provenance.json` (checksums, commit, no production differences).
- The study must differentiate **verified accounting observations**, **historical correlations**, and **unproven hypotheses**. No strategy changes, no new live/paper orders, no edits to main; open Draft PR and request review.

**Prior independent diagnostic (shorter period):** PR #13 used 2022-10-27..2026-10-14 and found Retest 109 stops/152 time exits; 16 gap-through-stop trades with ~$813 excess below planned stop; almost all the mean R from the top 10 winners. These are *not 10-year* results and must not be extrapolated.
