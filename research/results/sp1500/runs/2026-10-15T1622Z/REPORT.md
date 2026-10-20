# S&P 1500 / shorts / AI dataset — research run `2026-10-15T1622Z`

Rules `sp1500-research/1.0` (pre-registered in `research/sp1500/RULES.md`, not tuned). Code `301c65108fcbfd99ad2f2c354d26e743c8df0b15`. Data end **2026-10-14** (first session 2021-10-15, Yahoo `period=5y`, `auto_adjust=False` + dividends).

**Research only.** Nothing here changes the Retest RS-first paper bot, its data or schedules. Short results are *preliminary, not executable* (borrow, locate and recall are not observable). Signal-level statistics are hypothetical one-trade-per-signal outcomes and are **not** portfolio returns.

## 1. Universe and sources

| group | source | as_of | count | has_change_table |
|---|---|---|---|---|
| sp500 | wikipedia | None | 503 | False |
| sp400 | wikipedia | None | 400 | True |
| sp600 | wikipedia | None | 603 | True |

Retrieved 2026-10-15T16:22:17+00:00. All main comparisons use **today's** lists (survivorship bias). Point-in-time sources: sp500: fja05680/sp500 snapshots 1996-01-02..2026-08-18; sp400: wikipedia change table (best effort); sp600: wikipedia change table (best effort). Former members requested 439, with Yahoo data 186 (delisted names are mostly missing, so the PIT comparison still carries survivorship in that part). Membership counts over time: `pit_membership_sanity.csv`.

Overlaps (ticker listed in two indices):

| ticker | groups_listed | group | resolution | evidence |
|---|---|---|---|---|
| CORT | sp400|sp600 | sp400 | press_release | [["2026-09-21", "sp400", "added"], ["2026-09-21", "sp400", "added"], ["2026-09-21", "sp600", "removed"]] |
| EAT | sp400|sp600 | sp400 | press_release | [["2020-06-25", "sp400", "removed"], ["2020-06-25", "sp600", "added"], ["2026-09-21", "sp400", "added"], ["2026-09-21", "sp400", "added"], ["2026-09-21", "sp600", "removed"]] |
| FORM | sp400|sp600 | sp400 | press_release | [["2026-10-06", "sp400", "added"], ["2026-10-06", "sp600", "removed"]] |

## 2. Price coverage

| group | tickers | with_data | missing | coverage_pct | invalid_bars | median_rows | calendar_sessions |
|---|---|---|---|---|---|---|---|
| sp400 | 400 | 400 | 0 | 100.0 | 50 | 1255.0 | 1254 |
| sp400_removed | 85 | 21 | 64 | 24.7 | 2 | 1255.0 | 1254 |
| sp500 | 503 | 503 | 0 | 100.0 | 30 | 1255.0 | 1254 |
| sp500_removed | 60 | 11 | 49 | 18.3 | 0 | 505.0 | 1254 |
| sp600 | 600 | 599 | 1 | 99.8 | 63 | 1255.0 | 1254 |
| sp600_removed | 294 | 154 | 140 | 52.4 | 20 | 1255.0 | 1254 |

Tickers with missing sessions inside their own data span: 2 (total 43 ticker-sessions). Missing bars are never filled; labels on them stay empty (`missing_bar`).

## 3. Signal counts (all detections incl. rejected)

| group | strategy | detected | eligible_primary | eligible_off | closed | open | px20_mature |
|---|---|---|---|---|---|---|---|
| sp400 | breakdown | 20751 | 3346 | 8055 | 19951 | 741 | 19955 |
| sp400 | breakdown_retest | 12819 | 2159 | 5316 | 12107 | 649 | 12061 |
| sp400 | breakout | 65221 | 12014 | 14468 | 64190 | 492 | 64333 |
| sp400 | dbottom | 227 | 24 | 30 | 225 | 1 | 225 |
| sp400 | failed_breakout | 17042 | 306 | 2316 | 16896 | 113 | 16904 |
| sp400 | retest | 37005 | 7089 | 8573 | 36603 | 282 | 36564 |
| sp400 | vcp | 8783 | 3719 | 4166 | 8701 | 52 | 8710 |
| sp400_removed | breakdown | 1452 | 359 | 897 | 1413 | 30 | 1408 |
| sp400_removed | breakdown_retest | 782 | 217 | 490 | 753 | 23 | 749 |
| sp400_removed | breakout | 2392 | 445 | 530 | 2342 | 17 | 2356 |
| sp400_removed | dbottom | 4 | 1 | 1 | 4 | 0 | 4 |
| sp400_removed | failed_breakout | 602 | 28 | 243 | 595 | 6 | 595 |
| sp400_removed | retest | 1236 | 228 | 265 | 1216 | 10 | 1216 |
| sp400_removed | vcp | 100 | 60 | 60 | 100 | 0 | 100 |
| sp500 | breakdown | 25930 | 3614 | 9465 | 25038 | 829 | 24957 |
| sp500 | breakdown_retest | 14771 | 2155 | 5601 | 14019 | 684 | 13937 |
| sp500 | breakout | 87162 | 13824 | 16843 | 85503 | 978 | 85627 |
| sp500 | dbottom | 220 | 24 | 37 | 217 | 3 | 217 |
| sp500 | failed_breakout | 22907 | 352 | 2785 | 22641 | 209 | 22663 |
| sp500 | retest | 43214 | 7508 | 9060 | 42698 | 367 | 42660 |
| sp500 | vcp | 13944 | 5280 | 5752 | 13824 | 81 | 13819 |
| sp500_removed | breakdown | 343 | 54 | 168 | 329 | 12 | 325 |
| sp500_removed | breakdown_retest | 186 | 33 | 94 | 170 | 14 | 167 |
| sp500_removed | breakout | 669 | 123 | 146 | 639 | 15 | 651 |
| sp500_removed | failed_breakout | 170 | 6 | 34 | 162 | 7 | 163 |
| sp500_removed | retest | 283 | 78 | 87 | 280 | 2 | 280 |
| sp500_removed | vcp | 57 | 44 | 45 | 56 | 1 | 56 |
| sp600 | breakdown | 31786 | 5607 | 14059 | 30648 | 1014 | 30616 |
| sp600 | breakdown_retest | 19920 | 3808 | 9226 | 18993 | 824 | 18895 |
| sp600 | breakout | 90998 | 16665 | 20111 | 89605 | 671 | 89731 |
| sp600 | dbottom | 383 | 39 | 52 | 381 | 2 | 381 |
| sp600 | failed_breakout | 22877 | 581 | 4120 | 22634 | 184 | 22658 |
| sp600 | retest | 55923 | 10758 | 12867 | 55347 | 409 | 55316 |
| sp600 | vcp | 9752 | 4518 | 5087 | 9635 | 84 | 9640 |
| sp600_removed | breakdown | 9151 | 1057 | 2655 | 8846 | 262 | 8840 |
| sp600_removed | breakdown_retest | 5517 | 640 | 1703 | 5303 | 187 | 5282 |
| sp600_removed | breakout | 19674 | 3013 | 3633 | 19291 | 146 | 19355 |
| sp600_removed | dbottom | 74 | 8 | 8 | 72 | 0 | 74 |
| sp600_removed | failed_breakout | 4726 | 122 | 768 | 4663 | 51 | 4663 |
| sp600_removed | retest | 11435 | 1774 | 2124 | 11266 | 120 | 11270 |
| sp600_removed | vcp | 981 | 500 | 559 | 963 | 13 | 963 |

Rejection reasons (primary variant, a signal can have several):

| direction | r | n |
|---|---|---|
| long | eligible | 87736 |
| long | market | 74285 |
| long | rs | 345233 |
| short | eligible | 24444 |
| short | liquidity | 17414 |
| short | market | 137358 |
| short | rs | 133171 |

## 4. Long strategies — signal level, RS vs S&P 500 reference (production meaning)

Net R after 10 bps/side, next-open entry, stop or 20 sessions. Mature (closed) trades only. `mean_r` etc. use every eligible signal (consecutive-day repeats of one setup included, so they overlap); `nonoverlap_*` follows the production signal-level convention (one model trade per ticker and strategy at a time).

| group | strategy | detected | mature_trades | win_rate | mean_r | median_r | mean_r_ex_top5 | profit_factor | se_mean_r | nonoverlap_trades | nonoverlap_mean_r | nonoverlap_pf | nonoverlap_se |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| sp500 | breakout | 13824 | 13523 | 35.89 | 0.16 | -1.04 | 0.15 | 1.24 | 0.02 | 3970 | 0.11 | 1.17 | 0.03 |
| sp500 | dbottom | 24 | 22 | 54.55 | 0.10 | 0.24 | -0.26 | 1.30 | 0.19 | 15 | -0.00 | 1.00 | 0.25 |
| sp500 | retest | 7508 | 7355 | 42.54 | 0.12 | -0.43 | 0.10 | 1.21 | 0.02 | 2296 | 0.15 | 1.28 | 0.04 |
| sp500 | vcp | 5280 | 5207 | 47.24 | 0.20 | -0.11 | 0.19 | 1.42 | 0.02 | 859 | 0.12 | 1.24 | 0.06 |
| sp400 | breakout | 12014 | 11785 | 30.69 | -0.04 | -1.04 | -0.05 | 0.95 | 0.02 | 3732 | -0.03 | 0.96 | 0.03 |
| sp400 | dbottom | 24 | 22 | 63.64 | 0.16 | 0.38 | -0.24 | 1.46 | 0.24 | 16 | 0.20 | 1.59 | 0.31 |
| sp400 | retest | 7089 | 6985 | 38.67 | -0.01 | -1.01 | -0.02 | 0.99 | 0.02 | 2265 | -0.02 | 0.96 | 0.03 |
| sp400 | vcp | 3719 | 3685 | 41.44 | 0.08 | -0.34 | 0.06 | 1.15 | 0.03 | 678 | 0.03 | 1.05 | 0.06 |
| sp600 | breakout | 16665 | 16342 | 27.90 | -0.05 | -1.04 | -0.07 | 0.94 | 0.02 | 5544 | -0.05 | 0.94 | 0.03 |
| sp600 | dbottom | 39 | 37 | 37.84 | -0.31 | -0.50 | -0.62 | 0.52 | 0.21 | 30 | -0.27 | 0.59 | 0.25 |
| sp600 | retest | 10758 | 10588 | 36.77 | -0.04 | -1.02 | -0.04 | 0.94 | 0.02 | 3317 | -0.06 | 0.91 | 0.03 |
| sp600 | vcp | 4518 | 4448 | 34.58 | -0.13 | -1.01 | -0.15 | 0.80 | 0.03 | 889 | -0.05 | 0.92 | 0.07 |
| combined | breakout | 42503 | 41650 | 31.28 | 0.02 | -1.04 | 0.01 | 1.03 | 0.01 | 13246 | 0.01 | 1.01 | 0.02 |
| combined | dbottom | 87 | 81 | 49.38 | -0.07 | -0.12 | -0.24 | 0.85 | 0.13 | 61 | -0.08 | 0.85 | 0.16 |
| combined | retest | 25355 | 24928 | 39.00 | 0.02 | -1.01 | 0.01 | 1.03 | 0.01 | 7878 | 0.01 | 1.02 | 0.02 |
| combined | vcp | 13517 | 13340 | 41.42 | 0.06 | -0.37 | 0.05 | 1.11 | 0.02 | 2426 | 0.03 | 1.06 | 0.04 |

### RS base change: percentile vs the full 1500

| group | strategy | detected | mature_trades | win_rate | mean_r | median_r | mean_r_ex_top5 | profit_factor | se_mean_r | nonoverlap_trades | nonoverlap_mean_r | nonoverlap_pf | nonoverlap_se |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| sp500 | breakout | 12413 | 12147 | 36.30 | 0.19 | -1.04 | 0.18 | 1.28 | 0.02 | 3544 | 0.15 | 1.22 | 0.04 |
| sp500 | dbottom | 22 | 20 | 60.00 | 0.17 | 0.25 | -0.22 | 1.55 | 0.20 | 14 | 0.03 | 1.08 | 0.26 |
| sp500 | retest | 6740 | 6610 | 43.19 | 0.15 | -0.38 | 0.13 | 1.27 | 0.02 | 2061 | 0.19 | 1.36 | 0.04 |
| sp500 | vcp | 4769 | 4704 | 47.83 | 0.22 | -0.08 | 0.20 | 1.47 | 0.03 | 783 | 0.14 | 1.28 | 0.06 |
| sp400 | breakout | 10933 | 10733 | 31.28 | 0.00 | -1.04 | -0.01 | 1.00 | 0.02 | 3384 | -0.00 | 0.99 | 0.04 |
| sp400 | dbottom | 22 | 20 | 60.00 | 0.12 | 0.29 | -0.34 | 1.32 | 0.27 | 16 | 0.20 | 1.59 | 0.31 |
| sp400 | retest | 6424 | 6329 | 40.13 | 0.05 | -0.69 | 0.03 | 1.08 | 0.02 | 2031 | 0.02 | 1.04 | 0.04 |
| sp400 | vcp | 3394 | 3368 | 42.37 | 0.11 | -0.30 | 0.09 | 1.21 | 0.03 | 625 | 0.07 | 1.14 | 0.07 |
| sp600 | breakout | 15101 | 14808 | 28.32 | -0.03 | -1.04 | -0.05 | 0.96 | 0.02 | 5015 | -0.02 | 0.97 | 0.03 |
| sp600 | dbottom | 33 | 33 | 39.39 | -0.20 | -0.45 | -0.51 | 0.62 | 0.18 | 26 | -0.11 | 0.77 | 0.22 |
| sp600 | retest | 9782 | 9628 | 37.69 | -0.01 | -1.02 | -0.02 | 0.98 | 0.02 | 2974 | -0.03 | 0.96 | 0.03 |
| sp600 | vcp | 4091 | 4031 | 34.73 | -0.12 | -1.02 | -0.15 | 0.81 | 0.03 | 819 | -0.06 | 0.92 | 0.08 |
| combined | breakout | 38447 | 37688 | 31.73 | 0.05 | -1.04 | 0.04 | 1.07 | 0.01 | 11943 | 0.03 | 1.05 | 0.02 |
| combined | dbottom | 77 | 73 | 50.68 | -0.01 | 0.01 | -0.19 | 0.98 | 0.12 | 56 | 0.01 | 1.03 | 0.15 |
| combined | retest | 22946 | 22567 | 39.99 | 0.05 | -0.76 | 0.04 | 1.09 | 0.01 | 7066 | 0.05 | 1.09 | 0.02 |
| combined | vcp | 12254 | 12103 | 41.95 | 0.08 | -0.34 | 0.07 | 1.14 | 0.02 | 2227 | 0.05 | 1.09 | 0.04 |

### Slippage sensitivity (combined universe, RS vs 500)

| slippage | strategy | mature_trades | mean_r | profit_factor | nonoverlap_mean_r |
|---|---|---|---|---|---|
| base | breakout | 41650 | 0.02 | 1.03 | 0.01 |
| base | dbottom | 81 | -0.07 | 0.85 | -0.08 |
| base | retest | 24928 | 0.02 | 1.03 | 0.01 |
| base | vcp | 13340 | 0.06 | 1.11 | 0.03 |
| wide | breakout | 41650 | -0.06 | 0.92 | -0.07 |
| wide | dbottom | 81 | -0.10 | 0.80 | -0.10 |
| wide | retest | 24928 | -0.03 | 0.95 | -0.04 |
| wide | vcp | 13340 | 0.01 | 1.01 | -0.02 |
| stress | breakout | 41650 | -0.21 | 0.77 | -0.20 |
| stress | dbottom | 81 | -0.14 | 0.73 | -0.14 |
| stress | retest | 24928 | -0.11 | 0.83 | -0.12 |
| stress | vcp | 13340 | -0.09 | 0.87 | -0.11 |

### Point-in-time vs current membership (per index)

| universe | strategy | detected | mature_trades | mean_r | profit_factor | se_mean_r | nonoverlap_trades | nonoverlap_mean_r |
|---|---|---|---|---|---|---|---|---|
| current_sp500 | breakout | 13824 | 13523 | 0.16 | 1.24 | 0.02 | 3970 | 0.11 |
| current_sp500 | dbottom | 24 | 22 | 0.10 | 1.30 | 0.19 | 15 | -0.00 |
| current_sp500 | retest | 7508 | 7355 | 0.12 | 1.21 | 0.02 | 2296 | 0.15 |
| current_sp500 | vcp | 5280 | 5207 | 0.20 | 1.42 | 0.02 | 859 | 0.12 |
| pit_sp500 | breakout | 13380 | 13099 | 0.04 | 1.06 | 0.02 | 3844 | 0.01 |
| pit_sp500 | dbottom | 18 | 16 | 0.26 | 1.87 | 0.25 | 11 | 0.35 |
| pit_sp500 | retest | 7060 | 6909 | 0.05 | 1.09 | 0.02 | 2183 | 0.08 |
| pit_sp500 | vcp | 5343 | 5272 | 0.11 | 1.22 | 0.02 | 843 | 0.07 |
| current_sp400 | breakout | 12014 | 11785 | -0.04 | 0.95 | 0.02 | 3732 | -0.03 |
| current_sp400 | dbottom | 24 | 22 | 0.16 | 1.46 | 0.24 | 16 | 0.20 |
| current_sp400 | retest | 7089 | 6985 | -0.01 | 0.99 | 0.02 | 2265 | -0.02 |
| current_sp400 | vcp | 3719 | 3685 | 0.08 | 1.15 | 0.03 | 678 | 0.03 |
| pit_sp400 | breakout | 11451 | 11222 | -0.02 | 0.97 | 0.02 | 3514 | -0.06 |
| pit_sp400 | dbottom | 27 | 25 | 0.11 | 1.31 | 0.22 | 19 | 0.12 |
| pit_sp400 | retest | 6724 | 6620 | -0.05 | 0.91 | 0.02 | 2117 | -0.03 |
| pit_sp400 | vcp | 3774 | 3742 | 0.04 | 1.07 | 0.03 | 669 | 0.03 |
| current_sp600 | breakout | 16665 | 16342 | -0.05 | 0.94 | 0.02 | 5544 | -0.05 |
| current_sp600 | dbottom | 39 | 37 | -0.31 | 0.52 | 0.21 | 30 | -0.27 |
| current_sp600 | retest | 10758 | 10588 | -0.04 | 0.94 | 0.02 | 3317 | -0.06 |
| current_sp600 | vcp | 4518 | 4448 | -0.13 | 0.80 | 0.03 | 889 | -0.05 |
| pit_sp600 | breakout | 16915 | 16589 | -0.06 | 0.92 | 0.02 | 5581 | -0.07 |
| pit_sp600 | dbottom | 39 | 37 | -0.29 | 0.52 | 0.20 | 30 | -0.25 |
| pit_sp600 | retest | 10829 | 10661 | -0.05 | 0.92 | 0.02 | 3336 | -0.05 |
| pit_sp600 | vcp | 4568 | 4500 | -0.13 | 0.80 | 0.02 | 883 | -0.09 |

## 5. Long portfolio backtests (production engine, separate from signal stats)

`backtest.simulate(entry_at='open')` + RS-first order + `portfolio_bt.replay` with the frozen paper config ($10k, 1 % risk, 5 positions, 3 new/day, 20 % cap, 10 bps).

| rs | strategy | group | candidates | executed | closed | open_end | final_equity | return_pct | cagr_pct | max_dd_pct | first | last |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| rs_ref500 | breakout | sp500 | 13689 | 369 | 366 | 3 | 31230.76 | 212.31 | 33.28 | -27.46 | 2022-10-27 | 2026-10-14 |
| rs_ref500 | breakout | sp400 | 11899 | 349 | 344 | 5 | 15067.28 | 50.67 | 10.89 | -21.90 | 2022-10-27 | 2026-10-14 |
| rs_ref500 | breakout | sp600 | 16518 | 402 | 399 | 3 | 12779.03 | 27.79 | 6.38 | -29.80 | 2022-10-27 | 2026-10-14 |
| rs_ref500 | breakout | combined | 42106 | 385 | 380 | 5 | 37506.73 | 275.07 | 39.58 | -19.56 | 2022-10-27 | 2026-10-14 |
| rs_ref500 | retest | sp500 | 7470 | 276 | 272 | 4 | 17838.14 | 78.38 | 15.72 | -16.50 | 2022-10-27 | 2026-10-14 |
| rs_ref500 | retest | sp400 | 7064 | 284 | 280 | 4 | 13572.42 | 35.72 | 8.01 | -21.96 | 2022-10-27 | 2026-10-14 |
| rs_ref500 | retest | sp600 | 10716 | 303 | 298 | 5 | 9349.64 | -6.50 | -1.68 | -20.09 | 2022-10-27 | 2026-10-14 |
| rs_ref500 | retest | combined | 25250 | 307 | 303 | 4 | 10941.53 | 9.42 | 2.30 | -26.05 | 2022-10-27 | 2026-10-14 |
| rs_ref500 | vcp | sp500 | 5256 | 274 | 269 | 5 | 13489.35 | 34.89 | 7.84 | -19.16 | 2022-10-27 | 2026-10-14 |
| rs_ref500 | vcp | sp400 | 3704 | 270 | 266 | 4 | 11176.97 | 11.77 | 2.85 | -20.52 | 2022-10-27 | 2026-10-14 |
| rs_ref500 | vcp | sp600 | 4505 | 287 | 283 | 4 | 6648.30 | -33.52 | -9.78 | -41.99 | 2022-10-27 | 2026-10-14 |
| rs_ref500 | vcp | combined | 13465 | 286 | 282 | 4 | 13776.50 | 37.76 | 8.42 | -22.32 | 2022-10-27 | 2026-10-14 |
| rs_ref500 | dbottom | sp500 | 24 | 16 | 15 | 1 | 10001.46 | 0.01 | 0.00 | -3.32 | 2022-10-27 | 2026-10-14 |
| rs_ref500 | dbottom | sp400 | 23 | 17 | 16 | 1 | 10279.56 | 2.80 | 0.70 | -3.07 | 2022-10-27 | 2026-10-14 |
| rs_ref500 | dbottom | sp600 | 39 | 31 | 30 | 1 | 9193.56 | -8.06 | -2.10 | -10.64 | 2022-10-27 | 2026-10-14 |
| rs_ref500 | dbottom | combined | 86 | 59 | 56 | 3 | 9426.29 | -5.74 | -1.48 | -12.76 | 2022-10-27 | 2026-10-14 |
| rs_1500 | breakout | sp500 | 12287 | 351 | 348 | 3 | 44852.75 | 348.53 | 46.02 | -26.51 | 2022-10-27 | 2026-10-14 |
| rs_1500 | breakout | sp400 | 10824 | 346 | 341 | 5 | 16903.34 | 69.03 | 14.16 | -21.76 | 2022-10-27 | 2026-10-14 |
| rs_1500 | breakout | sp600 | 14964 | 395 | 391 | 4 | 9087.85 | -9.12 | -2.38 | -35.02 | 2022-10-27 | 2026-10-14 |
| rs_1500 | breakout | combined | 38075 | 383 | 380 | 3 | 27679.60 | 176.80 | 29.28 | -24.99 | 2022-10-27 | 2026-10-14 |
| rs_1500 | retest | sp500 | 6708 | 270 | 266 | 4 | 19559.50 | 95.60 | 18.44 | -16.23 | 2022-10-27 | 2026-10-14 |
| rs_1500 | retest | sp400 | 6401 | 278 | 274 | 4 | 14220.98 | 42.21 | 9.29 | -21.11 | 2022-10-27 | 2026-10-14 |
| rs_1500 | retest | sp600 | 9745 | 307 | 302 | 5 | 8044.69 | -19.55 | -5.34 | -27.54 | 2022-10-27 | 2026-10-14 |
| rs_1500 | retest | combined | 22854 | 309 | 305 | 4 | 10913.69 | 9.14 | 2.23 | -25.75 | 2022-10-27 | 2026-10-14 |
| rs_1500 | vcp | sp500 | 4749 | 266 | 262 | 4 | 12760.67 | 27.61 | 6.34 | -18.45 | 2022-10-27 | 2026-10-14 |
| rs_1500 | vcp | sp400 | 3381 | 273 | 269 | 4 | 10392.29 | 3.92 | 0.98 | -27.26 | 2022-10-27 | 2026-10-14 |
| rs_1500 | vcp | sp600 | 4080 | 287 | 283 | 4 | 6729.77 | -32.70 | -9.51 | -36.62 | 2022-10-27 | 2026-10-14 |
| rs_1500 | vcp | combined | 12210 | 294 | 290 | 4 | 11321.52 | 13.22 | 3.18 | -28.05 | 2022-10-27 | 2026-10-14 |
| rs_1500 | dbottom | sp500 | 22 | 15 | 14 | 1 | 10044.20 | 0.44 | 0.11 | -2.91 | 2022-10-27 | 2026-10-14 |
| rs_1500 | dbottom | sp400 | 21 | 17 | 16 | 1 | 10275.42 | 2.75 | 0.69 | -3.51 | 2022-10-27 | 2026-10-14 |
| rs_1500 | dbottom | sp600 | 33 | 26 | 26 | 0 | 9729.75 | -2.70 | -0.69 | -5.76 | 2022-10-27 | 2026-10-14 |
| rs_1500 | dbottom | combined | 76 | 53 | 51 | 2 | 9973.84 | -0.26 | -0.07 | -9.38 | 2022-10-27 | 2026-10-14 |

## 6. Short hypotheses — preliminary, cost scenarios

R per trade: gross, then net of 10 bps/side slippage+commission, dividends paid and borrow at GC 0.25 % / warm 3 % / hot 10 % / HTB 30 % APR; `net_stress_hot` = 50 bps/side + 10 %. Unknown borrow → no net figure. `gap_no_trade`: opened at/above the stop (skipped).

| market | group | strategy | detected | mature_trades | gross_mean_r | gross_win | net_base_gc | net_base_warm | net_base_hot | net_base_htb | net_stress_hot | nonoverlap_trades | nonoverlap_gross | nonoverlap_net_base_warm | nonoverlap_net_base_hot | gap_no_trade | ambiguous_bar | div_paid_trades |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| primary | sp500 | breakdown | 3614 | 3562 | -0.18 | 36.58 | -0.22 | -0.24 | -0.29 | -0.42 | -0.37 | 1428 | -0.17 | -0.23 | -0.27 | 5 | 0 | 597 |
| primary | sp500 | breakdown_retest | 2155 | 2117 | -0.28 | 30.18 | -0.33 | -0.35 | -0.41 | -0.56 | -0.53 | 890 | -0.29 | -0.36 | -0.42 | 8 | 0 | 283 |
| primary | sp500 | failed_breakout | 352 | 349 | -0.12 | 41.26 | -0.16 | -0.18 | -0.22 | -0.35 | -0.31 | 237 | -0.22 | -0.29 | -0.33 | 2 | 1 | 66 |
| primary | sp400 | breakdown | 3346 | 3299 | -0.21 | 36.98 | -0.24 | -0.26 | -0.30 | -0.42 | -0.39 | 1315 | -0.15 | -0.21 | -0.25 | 4 | 1 | 528 |
| primary | sp400 | breakdown_retest | 2159 | 2123 | -0.20 | 33.25 | -0.25 | -0.27 | -0.32 | -0.46 | -0.44 | 851 | -0.17 | -0.24 | -0.29 | 9 | 0 | 267 |
| primary | sp400 | failed_breakout | 306 | 306 | -0.20 | 37.91 | -0.24 | -0.25 | -0.29 | -0.40 | -0.36 | 207 | -0.25 | -0.30 | -0.34 | 0 | 0 | 56 |
| primary | sp600 | breakdown | 5607 | 5548 | -0.09 | 41.01 | -0.13 | -0.14 | -0.18 | -0.29 | -0.26 | 2160 | -0.05 | -0.10 | -0.14 | 4 | 2 | 810 |
| primary | sp600 | breakdown_retest | 3808 | 3759 | -0.07 | 37.38 | -0.12 | -0.14 | -0.19 | -0.32 | -0.30 | 1447 | -0.09 | -0.16 | -0.21 | 11 | 4 | 424 |
| primary | sp600 | failed_breakout | 581 | 579 | -0.20 | 34.20 | -0.23 | -0.25 | -0.28 | -0.38 | -0.36 | 391 | -0.22 | -0.27 | -0.30 | 1 | 0 | 72 |
| primary | combined | breakdown | 12567 | 12409 | -0.15 | 38.67 | -0.18 | -0.20 | -0.24 | -0.37 | -0.32 | 4903 | -0.11 | -0.17 | -0.21 | 13 | 3 | 1935 |
| primary | combined | breakdown_retest | 8122 | 7999 | -0.16 | 34.38 | -0.21 | -0.23 | -0.28 | -0.42 | -0.40 | 3188 | -0.17 | -0.24 | -0.29 | 28 | 4 | 974 |
| primary | combined | failed_breakout | 1239 | 1234 | -0.18 | 37.12 | -0.21 | -0.23 | -0.27 | -0.38 | -0.35 | 835 | -0.23 | -0.28 | -0.32 | 3 | 1 | 194 |
| off | sp500 | breakdown | 9465 | 9138 | -0.12 | 40.47 | -0.16 | -0.18 | -0.23 | -0.38 | -0.32 | 3077 | -0.09 | -0.15 | -0.20 | 7 | 0 | 1710 |
| off | sp500 | breakdown_retest | 5601 | 5309 | -0.18 | 34.53 | -24.48 | -25.41 | -27.79 | -34.59 | -124.59 | 1851 | -0.16 | -0.25 | -0.31 | 15 | 4 | 812 |
| off | sp500 | failed_breakout | 2785 | 2775 | -0.11 | 43.78 | -0.15 | -0.18 | -0.23 | -0.38 | -0.33 | 1539 | -0.13 | -0.20 | -0.25 | 7 | 1 | 531 |
| off | sp400 | breakdown | 8055 | 7768 | -0.15 | 40.04 | -0.18 | -0.20 | -0.24 | -0.37 | -0.33 | 2680 | -0.14 | -0.19 | -0.24 | 13 | 1 | 1253 |
| off | sp400 | breakdown_retest | 5316 | 5049 | -0.15 | 35.55 | -0.20 | -0.22 | -0.28 | -0.44 | -0.42 | 1668 | -0.14 | -0.22 | -0.28 | 14 | 3 | 732 |
| off | sp400 | failed_breakout | 2316 | 2303 | -0.16 | 39.73 | -0.20 | -0.22 | -0.27 | -0.40 | -0.36 | 1291 | -0.15 | -0.21 | -0.26 | 2 | 1 | 343 |
| off | sp600 | breakdown | 14059 | 13590 | -0.08 | 42.20 | -0.12 | -0.13 | -0.17 | -0.29 | -0.25 | 4611 | -0.08 | -0.13 | -0.17 | 18 | 2 | 1964 |
| off | sp600 | breakdown_retest | 9226 | 8799 | -0.08 | 37.10 | -0.13 | -0.15 | -0.20 | -0.35 | -0.33 | 2926 | -0.10 | -0.17 | -0.22 | 30 | 8 | 1061 |
| off | sp600 | failed_breakout | 4120 | 4099 | -0.05 | 42.42 | -0.09 | -0.11 | -0.15 | -0.28 | -0.24 | 2232 | -0.05 | -0.11 | -0.16 | 9 | 2 | 558 |
| off | combined | breakdown | 31579 | 30496 | -0.11 | 41.13 | -0.15 | -0.16 | -0.21 | -0.34 | -0.29 | 10368 | -0.10 | -0.15 | -0.20 | 38 | 3 | 4927 |
| off | combined | breakdown_retest | 20143 | 19157 | -0.12 | 35.98 | -6.90 | -7.17 | -7.87 | -9.86 | -34.79 | 6445 | -0.13 | -0.20 | -0.26 | 59 | 15 | 2605 |
| off | combined | failed_breakout | 9221 | 9177 | -0.10 | 42.16 | -0.14 | -0.16 | -0.21 | -0.34 | -0.30 | 5062 | -0.10 | -0.16 | -0.21 | 18 | 4 | 1432 |

## 7. Price-move labels (signal-close origin, eligible, %, signed by direction)

| strategy | group | eligible | n_1 | mean_1_pct | n_5 | mean_5_pct | n_10 | mean_10_pct | n_20 | mean_20_pct |
|---|---|---|---|---|---|---|---|---|---|---|
| breakdown | sp400 | 3346 | 3346 | -0.18 | 3346 | -0.67 | 3346 | -1.63 | 3320 | -3.03 |
| breakdown | sp500 | 3614 | 3614 | -0.11 | 3614 | -0.64 | 3614 | -1.44 | 3590 | -2.95 |
| breakdown | sp600 | 5607 | 5607 | -0.13 | 5607 | -0.34 | 5607 | -1.04 | 5572 | -1.89 |
| breakdown_retest | sp400 | 2159 | 2159 | -0.47 | 2159 | -1.06 | 2159 | -2.00 | 2139 | -2.53 |
| breakdown_retest | sp500 | 2155 | 2155 | -0.64 | 2155 | -1.26 | 2155 | -2.67 | 2139 | -3.46 |
| breakdown_retest | sp600 | 3808 | 3808 | -0.45 | 3808 | -0.85 | 3808 | -1.48 | 3783 | -1.37 |
| breakout | sp400 | 12014 | 12008 | 0.03 | 11960 | -0.00 | 11875 | 0.42 | 11776 | 0.92 |
| breakout | sp500 | 13824 | 13805 | 0.04 | 13752 | 0.30 | 13640 | 1.16 | 13473 | 2.32 |
| breakout | sp600 | 16665 | 16652 | 0.02 | 16559 | 0.11 | 16419 | 0.47 | 16263 | 1.00 |
| dbottom | sp400 | 24 | 23 | -0.00 | 23 | 0.83 | 22 | 0.86 | 22 | 4.55 |
| dbottom | sp500 | 24 | 24 | 0.28 | 24 | 2.12 | 23 | 1.29 | 22 | 1.41 |
| dbottom | sp600 | 39 | 39 | -0.23 | 38 | -2.04 | 37 | -2.91 | 37 | -3.39 |
| failed_breakout | sp400 | 306 | 306 | -0.11 | 306 | -0.39 | 306 | -2.08 | 305 | -3.76 |
| failed_breakout | sp500 | 352 | 352 | -0.32 | 352 | -1.21 | 352 | -3.30 | 352 | -2.83 |
| failed_breakout | sp600 | 581 | 581 | -0.10 | 581 | -1.48 | 581 | -2.59 | 580 | -3.36 |
| retest | sp400 | 7089 | 7087 | 0.07 | 7053 | 0.19 | 7011 | 0.42 | 6938 | 1.05 |
| retest | sp500 | 7508 | 7502 | 0.12 | 7456 | 0.57 | 7402 | 1.11 | 7310 | 2.35 |
| retest | sp600 | 10758 | 10748 | 0.02 | 10672 | 0.26 | 10618 | 0.46 | 10544 | 0.86 |
| vcp | sp400 | 3719 | 3717 | 0.01 | 3709 | 0.26 | 3692 | 0.77 | 3686 | 1.51 |
| vcp | sp500 | 5280 | 5277 | 0.03 | 5252 | 0.37 | 5219 | 0.95 | 5197 | 2.46 |
| vcp | sp600 | 4518 | 4516 | -0.04 | 4501 | -0.13 | 4471 | -0.08 | 4439 | -0.07 |

## 8. Equivalence with production

`backtest.find_signals` (retest, S&P 500 frames) vs research engine: `{'production_rows': 43214, 'research_rows': 43214, 'same_keys': True, 'level_equal': True, 'stop_base_equal': True, 'rs_equal': True, 'ok': True}`

## 9. AI dataset readiness

Rows 661469 (every detection, rejected ones with reasons for 4 variants). Columns: id, ticker, group, sector, strategy, direction, dates, rules/data version, generation time, decision-time features, price-move labels (with observable date and status), model trade (net R by scenario, MFE/MAE, barrier), split. Historical kind only; forward paper data is not mixed in.

| split | rows |
|---|---|
| embargo | 6297 |
| purged | 25615 |
| test | 130837 |
| train | 387357 |
| validation | 111363 |

Split: chronological 60/20/20 by signal date, 20-session purge before each boundary and 5-session embargo after it. No model was trained.

## 10. Limitations

- Main comparisons use today's membership. PIT membership is reconstructed only for the PIT section: S&P 500 from a community snapshot dataset (not S&P), 400/600 from Wikipedia change tables (best effort). Delisted stocks are largely absent from Yahoo → survivorship bias, likely optimistic for longs and pessimistic for shorts.
- iShares holdings files (dated) were requested but return an HTML page from the runner, so membership dates are retrieval dates; overlaps were resolved with dated S&P DJI press releases (`membership_evidence.csv`).
- Yahoo daily bars, split-adjusted; vendor revisions possible (bars + checksums saved in the artifact).
- Daily candles: intrabar order unknown; shared stop/target bars resolved as stop.
- Shorts: no borrow availability / fee / recall data; uptick rules and halts not modelled; not executable.
- Overlapping signals in signal-level stats are not independent; standard errors are understated.
- Immature signals (last ~20 sessions) are excluded from outcome statistics.
- Artifact retention is limited (90 days) — download the dataset if it must be kept.
