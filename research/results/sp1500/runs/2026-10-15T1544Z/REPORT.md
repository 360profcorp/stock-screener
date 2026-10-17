# S&P 1500 / shorts / AI dataset — research run `2026-10-15T1544Z`

Rules `sp1500-research/1.0` (pre-registered in `research/sp1500/RULES.md`, not tuned). Code `3e12942d66cd7ecb35b00509130e93189f3a2802`. Data end **2026-10-14** (first session 2021-10-15, Yahoo `period=5y`, `auto_adjust=False` + dividends).

**Research only.** Nothing here changes the Retest RS-first paper bot, its data or schedules. Short results are *preliminary, not executable* (borrow, locate and recall are not observable). Signal-level statistics are hypothetical one-trade-per-signal outcomes and are **not** portfolio returns.

## 1. Universe and sources

| group | source | as_of | count | has_change_table |
|---|---|---|---|---|
| sp500 | wikipedia | None | 503 | False |
| sp400 | wikipedia | None | 400 | True |
| sp600 | wikipedia | None | 603 | True |

Retrieved 2026-10-15T15:44:22+00:00. Survivorship bias (current membership only, no dated change table): sp500: YES, sp400: no, sp600: no. Point-in-time S&P 500: unavailable; removed members requested 0, with Yahoo data 0 (delisted names are mostly missing — the PIT test still carries survivorship in that part).

Overlaps (ticker listed in two indices):

| ticker | groups_listed | group | resolution | evidence |
|---|---|---|---|---|
| CORT | sp400|sp600 | sp400 | change_table | [["2026-09-21", "sp400", "added"]] |
| EAT | sp400|sp600 | sp400 | change_table | [["2020-06-25", "sp400", "removed"], ["2020-06-25", "sp600", "added"], ["2026-09-21", "sp400", "added"]] |
| FORM | sp400|sp600 | ambiguous | unresolved |  |

## 2. Price coverage

| group | tickers | with_data | missing | coverage_pct | invalid_bars | median_rows | calendar_sessions |
|---|---|---|---|---|---|---|---|
| ambiguous | 1 | 1 | 0 | 100.0 | 0 | 1255.0 | 1254 |
| sp400 | 399 | 399 | 0 | 100.0 | 50 | 1255.0 | 1254 |
| sp500 | 503 | 503 | 0 | 100.0 | 30 | 1255.0 | 1254 |
| sp600 | 600 | 599 | 1 | 99.8 | 63 | 1255.0 | 1254 |

Tickers with missing sessions inside their own data span: 1 (total 1 ticker-sessions). Missing bars are never filled; labels on them stay empty (`missing_bar`).

## 3. Signal counts (all detections incl. rejected)

| group | strategy | detected | eligible_primary | eligible_off | closed | open | px20_mature |
|---|---|---|---|---|---|---|---|
| ambiguous | breakdown | 37 | 12 | 18 | 37 | 0 | 37 |
| ambiguous | breakdown_retest | 15 | 5 | 10 | 15 | 0 | 15 |
| ambiguous | breakout | 196 | 76 | 91 | 190 | 3 | 189 |
| ambiguous | dbottom | 1 | 0 | 0 | 1 | 0 | 1 |
| ambiguous | failed_breakout | 64 | 1 | 10 | 64 | 0 | 64 |
| ambiguous | retest | 114 | 48 | 54 | 110 | 3 | 108 |
| ambiguous | vcp | 8 | 1 | 1 | 8 | 0 | 8 |
| sp400 | breakdown | 20714 | 3334 | 8037 | 19914 | 741 | 19918 |
| sp400 | breakdown_retest | 12804 | 2154 | 5306 | 12092 | 649 | 12046 |
| sp400 | breakout | 65025 | 11938 | 14377 | 64000 | 489 | 64144 |
| sp400 | dbottom | 226 | 24 | 30 | 224 | 1 | 224 |
| sp400 | failed_breakout | 16978 | 305 | 2306 | 16832 | 113 | 16840 |
| sp400 | retest | 36891 | 7041 | 8519 | 36493 | 279 | 36456 |
| sp400 | vcp | 8775 | 3718 | 4165 | 8693 | 52 | 8702 |
| sp500 | breakdown | 25930 | 3614 | 9465 | 25038 | 829 | 24957 |
| sp500 | breakdown_retest | 14771 | 2155 | 5601 | 14019 | 684 | 13937 |
| sp500 | breakout | 87162 | 13824 | 16843 | 85503 | 978 | 85627 |
| sp500 | dbottom | 220 | 24 | 37 | 217 | 3 | 217 |
| sp500 | failed_breakout | 22907 | 352 | 2785 | 22641 | 209 | 22663 |
| sp500 | retest | 43214 | 7508 | 9060 | 42698 | 367 | 42660 |
| sp500 | vcp | 13944 | 5280 | 5752 | 13824 | 81 | 13819 |
| sp600 | breakdown | 31786 | 5607 | 14059 | 30648 | 1014 | 30616 |
| sp600 | breakdown_retest | 19920 | 3808 | 9226 | 18993 | 824 | 18895 |
| sp600 | breakout | 90998 | 16665 | 20111 | 89605 | 671 | 89731 |
| sp600 | dbottom | 383 | 39 | 52 | 381 | 2 | 381 |
| sp600 | failed_breakout | 22877 | 581 | 4120 | 22634 | 184 | 22658 |
| sp600 | retest | 55923 | 10758 | 12867 | 55347 | 409 | 55316 |
| sp600 | vcp | 9752 | 4518 | 5087 | 9635 | 84 | 9640 |

Rejection reasons (primary variant, a signal can have several):

| direction | r | n |
|---|---|---|
| long | eligible | 81462 |
| long | market | 68283 |
| long | rs | 315786 |
| short | eligible | 21928 |
| short | liquidity | 5789 |
| short | market | 122292 |
| short | rs | 125124 |

## 4. Long strategies — signal level, RS vs S&P 500 reference (production meaning)

Net R after 10 bps/side, next-open entry, stop or 20 sessions. Mature (closed) trades only.

| group | strategy | detected | mature_trades | win_rate | mean_r | median_r | mean_r_ex_top5 | profit_factor | se_mean_r |
|---|---|---|---|---|---|---|---|---|---|
| sp500 | breakout | 13824 | 13523 | 35.89 | 0.16 | -1.04 | 0.15 | 1.24 | 0.02 |
| sp500 | dbottom | 24 | 22 | 54.55 | 0.10 | 0.24 | -0.26 | 1.30 | 0.19 |
| sp500 | retest | 7508 | 7355 | 42.54 | 0.12 | -0.43 | 0.10 | 1.21 | 0.02 |
| sp500 | vcp | 5280 | 5207 | 47.24 | 0.20 | -0.11 | 0.19 | 1.42 | 0.02 |
| sp400 | breakout | 11938 | 11715 | 30.74 | -0.04 | -1.04 | -0.04 | 0.95 | 0.02 |
| sp400 | dbottom | 24 | 22 | 63.64 | 0.16 | 0.38 | -0.24 | 1.46 | 0.24 |
| sp400 | retest | 7041 | 6940 | 38.76 | -0.00 | -0.94 | -0.02 | 0.99 | 0.02 |
| sp400 | vcp | 3718 | 3684 | 41.45 | 0.08 | -0.34 | 0.06 | 1.15 | 0.03 |
| sp600 | breakout | 16665 | 16342 | 27.90 | -0.05 | -1.04 | -0.07 | 0.94 | 0.02 |
| sp600 | dbottom | 39 | 37 | 37.84 | -0.31 | -0.50 | -0.62 | 0.52 | 0.21 |
| sp600 | retest | 10758 | 10588 | 36.77 | -0.04 | -1.02 | -0.04 | 0.94 | 0.02 |
| sp600 | vcp | 4518 | 4448 | 34.58 | -0.13 | -1.01 | -0.15 | 0.80 | 0.03 |
| combined | breakout | 42503 | 41650 | 31.28 | 0.02 | -1.04 | 0.01 | 1.03 | 0.01 |
| combined | dbottom | 87 | 81 | 49.38 | -0.07 | -0.12 | -0.24 | 0.85 | 0.13 |
| combined | retest | 25355 | 24928 | 39.00 | 0.02 | -1.01 | 0.01 | 1.03 | 0.01 |
| combined | vcp | 13517 | 13340 | 41.42 | 0.06 | -0.37 | 0.05 | 1.11 | 0.02 |

### RS base change: percentile vs the full 1500

| group | strategy | detected | mature_trades | win_rate | mean_r | median_r | mean_r_ex_top5 | profit_factor | se_mean_r |
|---|---|---|---|---|---|---|---|---|---|
| sp500 | breakout | 12280 | 12009 | 35.94 | 0.19 | -1.04 | 0.17 | 1.27 | 0.02 |
| sp500 | dbottom | 20 | 18 | 66.67 | 0.29 | 0.29 | -0.11 | 2.21 | 0.21 |
| sp500 | retest | 6692 | 6561 | 43.12 | 0.15 | -0.38 | 0.13 | 1.28 | 0.02 |
| sp500 | vcp | 4715 | 4649 | 47.71 | 0.22 | -0.09 | 0.20 | 1.47 | 0.03 |
| sp400 | breakout | 10719 | 10517 | 31.19 | -0.00 | -1.04 | -0.01 | 1.00 | 0.02 |
| sp400 | dbottom | 22 | 20 | 60.00 | 0.12 | 0.29 | -0.34 | 1.32 | 0.27 |
| sp400 | retest | 6292 | 6198 | 39.98 | 0.04 | -0.70 | 0.03 | 1.07 | 0.02 |
| sp400 | vcp | 3362 | 3336 | 42.60 | 0.12 | -0.28 | 0.09 | 1.22 | 0.03 |
| sp600 | breakout | 15023 | 14726 | 28.31 | -0.03 | -1.04 | -0.05 | 0.96 | 0.02 |
| sp600 | dbottom | 33 | 33 | 36.36 | -0.27 | -0.50 | -0.58 | 0.51 | 0.18 |
| sp600 | retest | 9720 | 9565 | 37.64 | -0.01 | -1.02 | -0.02 | 0.98 | 0.02 |
| sp600 | vcp | 4052 | 3991 | 34.50 | -0.13 | -1.02 | -0.15 | 0.80 | 0.03 |
| combined | breakout | 38096 | 37320 | 31.57 | 0.05 | -1.04 | 0.04 | 1.07 | 0.01 |
| combined | dbottom | 75 | 71 | 50.70 | -0.02 | 0.01 | -0.20 | 0.96 | 0.12 |
| combined | retest | 22751 | 22368 | 39.87 | 0.05 | -0.78 | 0.04 | 1.08 | 0.01 |
| combined | vcp | 12130 | 11977 | 41.88 | 0.08 | -0.34 | 0.07 | 1.14 | 0.02 |

### Slippage sensitivity (combined universe, RS vs 500)

| slippage | strategy | mature_trades | mean_r | profit_factor |
|---|---|---|---|---|
| base | breakout | 41650 | 0.02 | 1.03 |
| base | dbottom | 81 | -0.07 | 0.85 |
| base | retest | 24928 | 0.02 | 1.03 |
| base | vcp | 13340 | 0.06 | 1.11 |
| wide | breakout | 41650 | -0.06 | 0.92 |
| wide | dbottom | 81 | -0.10 | 0.80 |
| wide | retest | 24928 | -0.03 | 0.95 |
| wide | vcp | 13340 | 0.01 | 1.01 |
| stress | breakout | 41650 | -0.21 | 0.77 |
| stress | dbottom | 81 | -0.14 | 0.73 |
| stress | retest | 24928 | -0.11 | 0.83 |
| stress | vcp | 13340 | -0.09 | 0.87 |

### Point-in-time S&P 500 vs current S&P 500

_PIT unavailable_

## 5. Long portfolio backtests (production engine, separate from signal stats)

`backtest.simulate(entry_at='open')` + RS-first order + `portfolio_bt.replay` with the frozen paper config ($10k, 1 % risk, 5 positions, 3 new/day, 20 % cap, 10 bps).

| rs | strategy | group | candidates | executed | closed | open_end | final_equity | return_pct | cagr_pct | max_dd_pct | first | last |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| rs_ref500 | breakout | sp500 | 13689 | 369 | 366 | 3 | 31230.76 | 212.31 | 33.28 | -27.46 | 2022-10-27 | 2026-10-14 |
| rs_ref500 | breakout | sp400 | 11826 | 354 | 349 | 5 | 14843.78 | 48.44 | 10.48 | -19.62 | 2022-10-27 | 2026-10-14 |
| rs_ref500 | breakout | sp600 | 16518 | 402 | 399 | 3 | 12779.03 | 27.79 | 6.38 | -29.80 | 2022-10-27 | 2026-10-14 |
| rs_ref500 | breakout | combined | 42106 | 385 | 380 | 5 | 37506.73 | 275.07 | 39.58 | -19.56 | 2022-10-27 | 2026-10-14 |
| rs_ref500 | retest | sp500 | 7470 | 276 | 272 | 4 | 17838.14 | 78.38 | 15.72 | -16.50 | 2022-10-27 | 2026-10-14 |
| rs_ref500 | retest | sp400 | 7017 | 284 | 280 | 4 | 12999.66 | 30.00 | 6.84 | -21.79 | 2022-10-27 | 2026-10-14 |
| rs_ref500 | retest | sp600 | 10716 | 303 | 298 | 5 | 9349.64 | -6.50 | -1.68 | -20.09 | 2022-10-27 | 2026-10-14 |
| rs_ref500 | retest | combined | 25250 | 307 | 303 | 4 | 10941.53 | 9.42 | 2.30 | -26.05 | 2022-10-27 | 2026-10-14 |
| rs_ref500 | vcp | sp500 | 5256 | 274 | 269 | 5 | 13489.35 | 34.89 | 7.84 | -19.16 | 2022-10-27 | 2026-10-14 |
| rs_ref500 | vcp | sp400 | 3703 | 270 | 266 | 4 | 11176.97 | 11.77 | 2.85 | -20.52 | 2022-10-27 | 2026-10-14 |
| rs_ref500 | vcp | sp600 | 4505 | 287 | 283 | 4 | 6648.30 | -33.52 | -9.78 | -41.99 | 2022-10-27 | 2026-10-14 |
| rs_ref500 | vcp | combined | 13465 | 286 | 282 | 4 | 13776.50 | 37.76 | 8.42 | -22.32 | 2022-10-27 | 2026-10-14 |
| rs_ref500 | dbottom | sp500 | 24 | 16 | 15 | 1 | 10001.46 | 0.01 | 0.00 | -3.32 | 2022-10-27 | 2026-10-14 |
| rs_ref500 | dbottom | sp400 | 23 | 17 | 16 | 1 | 10279.56 | 2.80 | 0.70 | -3.07 | 2022-10-27 | 2026-10-14 |
| rs_ref500 | dbottom | sp600 | 39 | 31 | 30 | 1 | 9193.56 | -8.06 | -2.10 | -10.64 | 2022-10-27 | 2026-10-14 |
| rs_ref500 | dbottom | combined | 86 | 59 | 56 | 3 | 9426.29 | -5.74 | -1.48 | -12.76 | 2022-10-27 | 2026-10-14 |
| rs_1500 | breakout | sp500 | 12154 | 364 | 361 | 3 | 44552.83 | 345.53 | 45.77 | -20.70 | 2022-10-27 | 2026-10-14 |
| rs_1500 | breakout | sp400 | 10613 | 348 | 343 | 5 | 18062.53 | 80.63 | 16.08 | -21.13 | 2022-10-27 | 2026-10-14 |
| rs_1500 | breakout | sp600 | 14885 | 394 | 390 | 4 | 11127.70 | 11.28 | 2.73 | -41.88 | 2022-10-27 | 2026-10-14 |
| rs_1500 | breakout | combined | 37723 | 396 | 392 | 4 | 22010.93 | 120.11 | 22.02 | -35.66 | 2022-10-27 | 2026-10-14 |
| rs_1500 | retest | sp500 | 6659 | 270 | 266 | 4 | 20232.37 | 102.32 | 19.45 | -17.48 | 2022-10-27 | 2026-10-14 |
| rs_1500 | retest | sp400 | 6269 | 275 | 271 | 4 | 14399.32 | 43.99 | 9.63 | -19.46 | 2022-10-27 | 2026-10-14 |
| rs_1500 | retest | sp600 | 9683 | 297 | 292 | 5 | 8293.98 | -17.06 | -4.61 | -27.14 | 2022-10-27 | 2026-10-14 |
| rs_1500 | retest | combined | 22657 | 308 | 304 | 4 | 14426.72 | 44.27 | 9.69 | -23.58 | 2022-10-27 | 2026-10-14 |
| rs_1500 | vcp | sp500 | 4694 | 265 | 261 | 4 | 13560.58 | 35.61 | 7.99 | -17.23 | 2022-10-27 | 2026-10-14 |
| rs_1500 | vcp | sp400 | 3349 | 268 | 264 | 4 | 11715.08 | 17.15 | 4.07 | -24.94 | 2022-10-27 | 2026-10-14 |
| rs_1500 | vcp | sp600 | 4041 | 291 | 287 | 4 | 7263.73 | -27.36 | -7.75 | -39.61 | 2022-10-27 | 2026-10-14 |
| rs_1500 | vcp | combined | 12085 | 302 | 298 | 4 | 8882.63 | -11.17 | -2.94 | -31.63 | 2022-10-27 | 2026-10-14 |
| rs_1500 | dbottom | sp500 | 20 | 13 | 12 | 1 | 10232.06 | 2.32 | 0.58 | -2.30 | 2022-10-27 | 2026-10-14 |
| rs_1500 | dbottom | sp400 | 21 | 17 | 16 | 1 | 10275.42 | 2.75 | 0.69 | -3.51 | 2022-10-27 | 2026-10-14 |
| rs_1500 | dbottom | sp600 | 33 | 27 | 27 | 0 | 9536.86 | -4.63 | -1.19 | -5.96 | 2022-10-27 | 2026-10-14 |
| rs_1500 | dbottom | combined | 74 | 52 | 50 | 2 | 9921.51 | -0.78 | -0.20 | -8.78 | 2022-10-27 | 2026-10-14 |

## 6. Short hypotheses — preliminary, cost scenarios

R per trade: gross, then net of 10 bps/side slippage+commission, dividends paid and borrow at GC 0.25 % / warm 3 % / hot 10 % / HTB 30 % APR; `net_stress_hot` = 50 bps/side + 10 %. Unknown borrow → no net figure. `gap_no_trade`: opened at/above the stop (skipped).

| market | group | strategy | detected | mature_trades | gross_mean_r | gross_win | net_base_gc | net_base_warm | net_base_hot | net_base_htb | net_stress_hot | gap_no_trade | ambiguous_bar | div_paid_trades |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| primary | sp500 | breakdown | 3614 | 3562 | -0.18 | 36.58 | -0.22 | -0.24 | -0.29 | -0.42 | -0.37 | 5 | 0 | 597 |
| primary | sp500 | breakdown_retest | 2155 | 2117 | -0.28 | 30.18 | -0.33 | -0.35 | -0.41 | -0.56 | -0.53 | 8 | 0 | 283 |
| primary | sp500 | failed_breakout | 352 | 349 | -0.12 | 41.26 | -0.16 | -0.18 | -0.22 | -0.35 | -0.31 | 2 | 1 | 66 |
| primary | sp400 | breakdown | 3334 | 3287 | -0.21 | 36.96 | -0.24 | -0.26 | -0.30 | -0.42 | -0.39 | 4 | 1 | 528 |
| primary | sp400 | breakdown_retest | 2154 | 2118 | -0.20 | 33.33 | -0.25 | -0.27 | -0.32 | -0.46 | -0.44 | 9 | 0 | 267 |
| primary | sp400 | failed_breakout | 305 | 305 | -0.20 | 38.03 | -0.23 | -0.25 | -0.29 | -0.40 | -0.36 | 0 | 0 | 56 |
| primary | sp600 | breakdown | 5607 | 5548 | -0.09 | 41.01 | -0.13 | -0.14 | -0.18 | -0.29 | -0.26 | 4 | 2 | 810 |
| primary | sp600 | breakdown_retest | 3808 | 3759 | -0.07 | 37.38 | -0.12 | -0.14 | -0.19 | -0.32 | -0.30 | 11 | 4 | 424 |
| primary | sp600 | failed_breakout | 581 | 579 | -0.20 | 34.20 | -0.23 | -0.25 | -0.28 | -0.38 | -0.36 | 1 | 0 | 72 |
| primary | combined | breakdown | 12567 | 12409 | -0.15 | 38.67 | -0.18 | -0.20 | -0.24 | -0.37 | -0.32 | 13 | 3 | 1935 |
| primary | combined | breakdown_retest | 8122 | 7999 | -0.16 | 34.38 | -0.21 | -0.23 | -0.28 | -0.42 | -0.40 | 28 | 4 | 974 |
| primary | combined | failed_breakout | 1239 | 1234 | -0.18 | 37.12 | -0.21 | -0.23 | -0.27 | -0.38 | -0.35 | 3 | 1 | 194 |
| off | sp500 | breakdown | 9465 | 9138 | -0.12 | 40.47 | -0.16 | -0.18 | -0.23 | -0.38 | -0.32 | 7 | 0 | 1710 |
| off | sp500 | breakdown_retest | 5601 | 5309 | -0.18 | 34.53 | -24.48 | -25.41 | -27.79 | -34.59 | -124.59 | 15 | 4 | 812 |
| off | sp500 | failed_breakout | 2785 | 2775 | -0.11 | 43.78 | -0.15 | -0.18 | -0.23 | -0.38 | -0.33 | 7 | 1 | 531 |
| off | sp400 | breakdown | 8037 | 7750 | -0.15 | 40.04 | -0.18 | -0.20 | -0.24 | -0.37 | -0.33 | 13 | 1 | 1253 |
| off | sp400 | breakdown_retest | 5306 | 5039 | -0.15 | 35.58 | -0.20 | -0.22 | -0.28 | -0.44 | -0.42 | 14 | 3 | 732 |
| off | sp400 | failed_breakout | 2306 | 2293 | -0.16 | 39.82 | -0.20 | -0.22 | -0.27 | -0.40 | -0.36 | 2 | 1 | 343 |
| off | sp600 | breakdown | 14059 | 13590 | -0.08 | 42.20 | -0.12 | -0.13 | -0.17 | -0.29 | -0.25 | 18 | 2 | 1964 |
| off | sp600 | breakdown_retest | 9226 | 8799 | -0.08 | 37.10 | -0.13 | -0.15 | -0.20 | -0.35 | -0.33 | 30 | 8 | 1061 |
| off | sp600 | failed_breakout | 4120 | 4099 | -0.05 | 42.42 | -0.09 | -0.11 | -0.15 | -0.28 | -0.24 | 9 | 2 | 558 |
| off | combined | breakdown | 31579 | 30496 | -0.11 | 41.13 | -0.15 | -0.16 | -0.21 | -0.34 | -0.29 | 38 | 3 | 4927 |
| off | combined | breakdown_retest | 20143 | 19157 | -0.12 | 35.98 | -6.90 | -7.17 | -7.87 | -9.86 | -34.79 | 59 | 15 | 2605 |
| off | combined | failed_breakout | 9221 | 9177 | -0.10 | 42.16 | -0.14 | -0.16 | -0.21 | -0.34 | -0.30 | 18 | 4 | 1432 |

## 7. Price-move labels (signal-close origin, eligible, %, signed by direction)

| strategy | group | eligible | n_1 | mean_1_pct | n_5 | mean_5_pct | n_10 | mean_10_pct | n_20 | mean_20_pct |
|---|---|---|---|---|---|---|---|---|---|---|
| breakdown | ambiguous | 12 | 12 | 0.68 | 12 | 0.53 | 12 | -3.54 | 12 | -7.52 |
| breakdown | sp400 | 3334 | 3334 | -0.18 | 3334 | -0.67 | 3334 | -1.63 | 3308 | -3.02 |
| breakdown | sp500 | 3614 | 3614 | -0.11 | 3614 | -0.64 | 3614 | -1.44 | 3590 | -2.95 |
| breakdown | sp600 | 5607 | 5607 | -0.13 | 5607 | -0.34 | 5607 | -1.04 | 5572 | -1.89 |
| breakdown_retest | ambiguous | 5 | 5 | -5.21 | 5 | -2.61 | 5 | -8.39 | 5 | -13.12 |
| breakdown_retest | sp400 | 2154 | 2154 | -0.46 | 2154 | -1.06 | 2154 | -1.98 | 2134 | -2.51 |
| breakdown_retest | sp500 | 2155 | 2155 | -0.64 | 2155 | -1.26 | 2155 | -2.67 | 2139 | -3.46 |
| breakdown_retest | sp600 | 3808 | 3808 | -0.45 | 3808 | -0.85 | 3808 | -1.48 | 3783 | -1.37 |
| breakout | ambiguous | 76 | 76 | 0.26 | 76 | -0.36 | 76 | 0.65 | 70 | 2.40 |
| breakout | sp400 | 11938 | 11932 | 0.03 | 11884 | 0.00 | 11799 | 0.42 | 11706 | 0.91 |
| breakout | sp500 | 13824 | 13805 | 0.04 | 13752 | 0.30 | 13640 | 1.16 | 13473 | 2.32 |
| breakout | sp600 | 16665 | 16652 | 0.02 | 16559 | 0.11 | 16419 | 0.47 | 16263 | 1.00 |
| dbottom | sp400 | 24 | 23 | -0.00 | 23 | 0.83 | 22 | 0.86 | 22 | 4.55 |
| dbottom | sp500 | 24 | 24 | 0.28 | 24 | 2.12 | 23 | 1.29 | 22 | 1.41 |
| dbottom | sp600 | 39 | 39 | -0.23 | 38 | -2.04 | 37 | -2.91 | 37 | -3.39 |
| failed_breakout | ambiguous | 1 | 1 | -0.35 | 1 | 2.39 | 1 | 0.89 | 1 | -10.42 |
| failed_breakout | sp400 | 305 | 305 | -0.11 | 305 | -0.40 | 305 | -2.09 | 304 | -3.74 |
| failed_breakout | sp500 | 352 | 352 | -0.32 | 352 | -1.21 | 352 | -3.30 | 352 | -2.83 |
| failed_breakout | sp600 | 581 | 581 | -0.10 | 581 | -1.48 | 581 | -2.59 | 580 | -3.36 |
| retest | ambiguous | 48 | 48 | 0.94 | 47 | 1.98 | 47 | 0.49 | 42 | 2.10 |
| retest | sp400 | 7041 | 7039 | 0.07 | 7006 | 0.18 | 6964 | 0.42 | 6896 | 1.04 |
| retest | sp500 | 7508 | 7502 | 0.12 | 7456 | 0.57 | 7402 | 1.11 | 7310 | 2.35 |
| retest | sp600 | 10758 | 10748 | 0.02 | 10672 | 0.26 | 10618 | 0.46 | 10544 | 0.86 |
| vcp | ambiguous | 1 | 1 | -3.59 | 1 | -3.92 | 1 | -3.15 | 1 | -3.92 |
| vcp | sp400 | 3718 | 3716 | 0.01 | 3708 | 0.26 | 3691 | 0.77 | 3685 | 1.51 |
| vcp | sp500 | 5280 | 5277 | 0.03 | 5252 | 0.37 | 5219 | 0.95 | 5197 | 2.46 |
| vcp | sp600 | 4518 | 4516 | -0.04 | 4501 | -0.13 | 4471 | -0.08 | 4439 | -0.07 |

## 8. Equivalence with production

`backtest.find_signals` (retest, S&P 500 frames) vs research engine: `{'production_rows': 43214, 'research_rows': 43214, 'same_keys': True, 'level_equal': True, 'stop_base_equal': True, 'rs_equal': True, 'ok': True}`

## 9. AI dataset readiness

Rows 601635 (every detection, rejected ones with reasons for 4 variants). Columns: id, ticker, group, sector, strategy, direction, dates, rules/data version, generation time, decision-time features, price-move labels (with observable date and status), model trade (net R by scenario, MFE/MAE, barrier), split. Historical kind only; forward paper data is not mixed in.

| split | rows |
|---|---|
| embargo | 5738 |
| purged | 23231 |
| test | 119105 |
| train | 352453 |
| validation | 101108 |

Split: chronological 60/20/20 by signal date, 20-session purge before each boundary and 5-session embargo after it. No model was trained.

## 10. Limitations

- Membership is today's (except reconstructed PIT S&P 500); delisted stocks are largely absent from Yahoo → survivorship bias, likely optimistic for longs and pessimistic for shorts.
- Yahoo daily bars, split-adjusted; vendor revisions possible (bars + checksums saved in the artifact).
- Daily candles: intrabar order unknown; shared stop/target bars resolved as stop.
- Shorts: no borrow availability / fee / recall data; uptick rules and halts not modelled; not executable.
- Overlapping signals in signal-level stats are not independent; standard errors are understated.
- Immature signals (last ~20 sessions) are excluded from outcome statistics.
- Artifact retention is limited (90 days) — download the dataset if it must be kept.
