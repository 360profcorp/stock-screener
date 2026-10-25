# Short strategies v1, 10 years — findings

Pre-registration: `PREREG_SHORTS.md`, committed before the 10-year data was loaded.
- Dataset: run 40152515701 (`research.sp1500.run --period 10y --shorts-only`, rules
  `sp1500-research/1.0`, unchanged).
- Analysis: `research/results/shorts/runs/2026-10-25T0229Z/` (`REPORT.md`, `results.json`,
  tables, equity curves, fills).

## Verdict
**No short setup is confirmed. Short strategies v1 are rejected; no re-parametrisation.**

None of the 6 combinations (3 setups × market filter on/off, point-in-time S&P 500) even
advanced from the development period (2017–2021): every one had a negative mean net R.

**Holdout 2022–2026:** all six are negative. For four of them the upper end of the 90 %
interval is below zero; for failed breakout it only just reaches zero (+0.025 with the filter,
+0.010 without). Every portfolio lost money on the holdout. The setups are negative already
**before costs**: gross R < 0 in every universe and filter variant.

## Data and audit (Muse's six points)
| # | Check | Result |
|---|---|---|
| 1 | Engine eligibility vs an independent recomputation | `eligible_primary` 65,096 = 65,096, `eligible_off` 146,905 = 146,905, `eligible_pit_primary` 60,422 = 60,422, `eligible_rs1500_primary` 46,344 = 46,344, **0 mismatches**. No eligible primary short had SPY above MA50; 81,809 of the `off` shorts did (no filter, as intended) |
| 2 | WR / PF / expectancy | separately for gross and each of the 12 net scenarios (`signal_stats.csv`) |
| 3 | Costs recomputed from entry, exit, risk, days and dividends | max difference vs the engine: 0 R in all 12 net scenarios (gross 4e-15). 72,858 of 459,348 closed trades paid dividends |
| 4 | Non-overlap rule | engine = an independent re-implementation of `backtest.simulate(one_per_ticker=True)`: 13,702 = 13,702, 0 mismatches |
| 5 | `ambiguous` | this run's membership snapshot has **0** tickers in both the S&P 400 and 600, so the S&P 1500 with and without `ambiguous` are identical (both reported) |
| 6 | Coverage | sessions 2016-10-24 → 2026-10-23 (251–253 per full year). Eligible PIT S&P 500 shorts with SPY < MA50: breakdown 1,098 in 2020 and 2,333 in 2022; retest 372 and 1,631; failed breakout 142 and 201 |

**Survivorship.** 670 former index members were requested; only 219 have Yahoo data. The
point-in-time universe therefore misses most failed or removed companies. This most likely
**understates** short results; the size of that bias is unknown.

**Borrow.** There is no locate or borrow-rate history. Every short was assumed borrowable;
fees are scenarios only (0.25 / 3 / 10 / 30 % APR).

## Signal level (PIT S&P 500, SPY < MA50, non-overlapping)
| Setup | Trades | Gross R | Net R (10 bps, 3 % borrow) | Win rate (net) | PF (net) | Net at 50 bps + 30 % |
|---|---|---|---|---|---|---|
| Breakdown | 3,422 | −0.070 | −0.126 | 37.6 % | 0.73 | −0.387 |
| Breakdown retest | 2,238 | −0.104 | −0.179 | 30.6 % | 0.73 | −0.526 |
| Failed breakout | 535 | −0.147 | −0.207 | 37.0 % | 0.60 | −0.472 |

Without the market filter and on the other universes (today's S&P 500, S&P 1500) the picture
is the same: gross between −0.05 and −0.27 R, net worse.

## Crashes vs recoveries (same population, primary net)
| Setup | COVID crash 02-20 → 03-23 | COVID recovery | 2022 bear | 2022 rebound | 2023–2026 |
|---|---|---|---|---|---|
| Breakdown | **+2.08 R** (137) | −0.84 (156) | −0.05 (677) | −0.34 (276) | −0.14 (1,159) |
| Breakdown retest | **+3.33 R** (98) | −0.71 (76) | −0.22 (492) | −0.66 (202) | −0.21 (692) |
| Failed breakout | +1.98 R (5) | −0.51 (58) | −0.18 (95) | −0.70 (57) | −0.10 (197) |

- **The edge exists only in the one sharp crash**, about 23 sessions in this decade.
  Signals keep firing after the turn, and the recovery takes back more than the crash gave.
- **The long 2022 bear was flat to negative** for all three setups. The only positive cell
  without the market filter was failed breakout in the 2022 bear, +0.16 R over 226 trades.
  It was selected by nothing and is not evidence.

## Portfolio (short-only books, $10k, 1 % risk, 5 positions, primary net costs)
| Book (PIT S&P 500, SPY < MA50) | Full 2017–2026 | Max DD | Trades | COVID crash | COVID recovery | 2022 bear | Holdout 2022→ (fresh book) |
|---|---|---|---|---|---|---|---|
| Breakdown | −26.2 % | −38.3 % | 273 | **+22.3 %** | −15.6 % | −2.5 % | −13.8 % |
| Breakdown retest | −25.5 % | −44.1 % | 288 | **+17.7 %** | −12.2 % | −0.1 % | −24.1 % |
| Failed breakout | −21.4 % | −27.7 % | 208 | +12.2 % | −8.7 % | +6.1 % | −15.3 % |

- **Without the market filter:** −40 / −70 / −59 % over the full period.
- **S&P 1500:** −38 / −42 / −32 %.
- Yearly returns, equity curves and fills are in the run folder.

## Development vs holdout (PIT S&P 500, primary net, non-overlapping)
| Market × setup | Development 2017–2021: trades, mean R, PF | Advances | Holdout 2022→: trades, mean R [90 % CI] |
|---|---|---|---|
| SPY < MA50 · breakdown | 1,310, −0.105, 0.78 | no | 2,112, −0.136 [−0.258, −0.020] |
| SPY < MA50 · retest | 852, −0.015, 0.98 | no | 1,386, −0.281 [−0.441, −0.127] |
| SPY < MA50 · failed breakout | 186, −0.183, 0.63 | no | 349, −0.220 [−0.443, +0.025] |
| off · breakdown | 2,641, −0.138, 0.71 | no | 3,800, −0.090 [−0.169, −0.009] |
| off · retest | 1,606, −0.112, 0.82 | no | 2,392, −0.221 [−0.322, −0.115] |
| off · failed breakout | 1,495, −0.159, 0.69 | no | 1,709, −0.109 [−0.222, +0.010] |

## What this does and does not say
- These three entry rules, with a 20-session hold and a stop 3 % above, do not work as
  stand-alone short strategies on this decade. Costs make them worse, but they are negative
  before costs too.
- The crash-only edge suggests that any future short idea would need **an exit or regime rule
  that stops shorting after the turn**. That would be a **new hypothesis (v2)** with its own
  pre-registration. Because this decade has now been seen, its result on 2016–2026 could only
  be exploratory, and confirmation would have to come from future data. Nothing is proposed
  here for paper or live trading.
