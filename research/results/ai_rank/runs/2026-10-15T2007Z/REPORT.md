# AI ranking research v1 — run `2026-10-15T2007Z`

Dataset: PR #5 run (rules `sp1500-research/1.0`), data end 2026-10-14. Validation from 2025-03-17, test from 2025-12-30. Research only — no model is connected to the bot.

## 1. Dataset audit

```json
{
 "features_recomputed_on_truncated_bars": {
  "checked": 400,
  "mismatches": 0,
  "examples": []
 },
 "rs_recomputed_on_truncated_closes": {
  "checked": 1866,
  "mismatches": 0
 },
 "labels": {
  "closed": 648319,
  "closed_after_data_end": 0,
  "exit_before_entry": 0,
  "entry_not_after_signal": 0,
  "open_or_immature": 13150
 },
 "purge_v1_leaks": {
  "train_rows_label_after_validation_start": 716,
  "validation_rows_label_after_test_start": 483,
  "fixed": "purge by label end (exit date, >= signal + 21 sessions)"
 },
 "overlap": {
  "eligible_long": 87736,
  "non_overlapping": 26157,
  "repeats_share": 0.702
 }
}
```

## 2. Portfolio (RS-first, frozen paper config) by universe and strategy

| universe | strategy | signals | return_pct | cagr_pct | max_dd_pct | trades | closed | expectancy_r | expectancy_usd | win_rate |
|---|---|---|---|---|---|---|---|---|---|---|
| sp500 | breakout | 13824 | 212.31 | 33.28 | -27.46 | 369 | 366 | 0.37 | 56.54 | 30.87 |
| sp500 | retest | 7508 | 78.38 | 15.72 | -16.50 | 276 | 272 | 0.26 | 29.16 | 44.85 |
| sp500 | vcp | 5280 | 34.89 | 7.84 | -19.16 | 274 | 269 | 0.14 | 13.05 | 41.64 |
| sp500 | dbottom | 24 | 0.01 | 0.00 | -3.32 | 16 | 15 | -0.00 | -0.66 | 46.67 |
| sp400 | breakout | 12014 | 50.67 | 10.89 | -21.90 | 349 | 344 | 0.16 | 14.30 | 32.27 |
| sp400 | retest | 7089 | 35.72 | 8.01 | -21.96 | 284 | 280 | 0.12 | 12.35 | 40.71 |
| sp400 | vcp | 3719 | 11.77 | 2.85 | -20.52 | 270 | 266 | 0.04 | 3.97 | 41.73 |
| sp400 | dbottom | 24 | 2.80 | 0.70 | -3.07 | 17 | 16 | 0.20 | 17.76 | 62.50 |
| sp600 | breakout | 16665 | 27.79 | 6.38 | -29.80 | 402 | 399 | 0.05 | 7.26 | 23.06 |
| sp600 | retest | 10758 | -6.50 | -1.68 | -20.09 | 303 | 298 | -0.02 | -2.40 | 35.23 |
| sp600 | vcp | 4518 | -33.52 | -9.78 | -41.99 | 287 | 283 | -0.10 | -11.91 | 33.92 |
| sp600 | dbottom | 39 | -8.06 | -2.10 | -10.64 | 31 | 30 | -0.27 | -25.35 | 40.00 |
| combined | breakout | 42503 | 275.07 | 39.58 | -19.56 | 385 | 380 | 0.42 | 68.66 | 28.95 |
| combined | retest | 25355 | 9.42 | 2.30 | -26.05 | 307 | 303 | 0.04 | 2.91 | 35.31 |
| combined | vcp | 13517 | 37.76 | 8.42 | -22.32 | 286 | 282 | 0.18 | 12.61 | 41.13 |
| combined | dbottom | 87 | -5.74 | -1.48 | -12.76 | 59 | 56 | -0.09 | -9.51 | 46.43 |
| pit500 | breakout | 13380 | 56.08 | 11.89 | -18.87 | 353 | 350 | 0.18 | 15.29 | 33.14 |
| pit500 | retest | 7060 | 68.35 | 14.04 | -19.20 | 265 | 261 | 0.23 | 24.95 | 47.51 |
| pit500 | vcp | 5343 | -8.87 | -2.32 | -21.54 | 273 | 268 | -0.04 | -3.30 | 39.93 |
| pit500 | dbottom | 18 | 3.03 | 0.76 | -1.85 | 12 | 11 | 0.35 | 26.55 | 54.55 |


Yearly portfolio returns, %:

| book | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|
| sp500/breakout | 2.67 | 24.89 | 42.26 | 35.20 | 26.65 |
| sp500/retest | -9.62 | 4.07 | 12.96 | 37.72 | 21.91 |
| sp500/vcp | -6.72 | 14.90 | 30.34 | 0.87 | -4.28 |
| sp500/dbottom | 0.00 | 2.35 | -1.59 | 0.59 | -1.28 |
| sp400/breakout | -2.01 | 25.91 | 7.59 | 10.15 | 3.05 |
| sp400/retest | -1.25 | 18.25 | 5.58 | 17.10 | -5.99 |
| sp400/vcp | -2.95 | 5.35 | 19.17 | 1.64 | -9.74 |
| sp400/dbottom | -0.98 | 1.55 | -1.08 | 0.33 | 2.99 |
| sp600/breakout | -9.12 | 9.40 | -2.14 | 47.12 | -10.72 |
| sp600/retest | -12.43 | 3.99 | 0.70 | 2.95 | -0.97 |
| sp600/vcp | -12.99 | -23.43 | -3.83 | 15.61 | -10.25 |
| sp600/dbottom | -0.60 | 1.08 | -3.05 | -5.95 | 0.34 |
| combined/breakout | 7.87 | 26.35 | 44.93 | 55.39 | 22.19 |
| combined/retest | -11.72 | 16.70 | 29.83 | 3.14 | -20.68 |
| combined/vcp | -6.54 | 16.48 | 25.73 | 18.27 | -14.89 |
| combined/dbottom | -1.57 | 3.98 | -4.74 | -5.15 | 1.93 |
| pit500/breakout | -12.46 | 17.00 | 18.55 | 2.16 | 25.83 |
| pit500/retest | -10.11 | 2.60 | 15.43 | 20.71 | 31.00 |
| pit500/vcp | -6.47 | 4.06 | 12.38 | -13.67 | -3.49 |
| pit500/dbottom | 0.00 | 1.08 | 0.00 | 0.59 | 1.34 |


## 3. Signal-level stability by year (non-overlapping, NOT portfolio)

| direction | group | strategy | year | signals | nonoverlap_trades | mean_net_r | win_rate | mean_gross_r | mean_net_r_warm |
|---|---|---|---|---|---|---|---|---|---|
| long | sp400 | breakout | 2022 | 400 | 190 | -0.60 | 18.95 |  |  |
| long | sp400 | breakout | 2023 | 3250 | 1006 | -0.05 | 31.61 |  |  |
| long | sp400 | breakout | 2024 | 3302 | 1018 | 0.07 | 35.07 |  |  |
| long | sp400 | breakout | 2025 | 2530 | 795 | 0.11 | 36.23 |  |  |
| long | sp400 | breakout | 2026 | 2532 | 771 | -0.09 | 25.81 |  |  |
| long | sp400 | dbottom | 2022 | 1 | 1 | -1.02 | 0.00 |  |  |
| long | sp400 | dbottom | 2023 | 7 | 5 | 0.32 | 80.00 |  |  |
| long | sp400 | dbottom | 2024 | 7 | 3 | -0.32 | 33.33 |  |  |
| long | sp400 | dbottom | 2025 | 1 | 1 | 0.36 | 100.00 |  |  |
| long | sp400 | dbottom | 2026 | 8 | 6 | 0.55 | 66.67 |  |  |
| long | sp400 | retest | 2022 | 284 | 107 | -0.48 | 19.63 |  |  |
| long | sp400 | retest | 2023 | 1966 | 609 | 0.07 | 43.51 |  |  |
| long | sp400 | retest | 2024 | 1922 | 620 | -0.08 | 36.61 |  |  |
| long | sp400 | retest | 2025 | 1492 | 483 | 0.15 | 42.24 |  |  |
| long | sp400 | retest | 2026 | 1425 | 463 | -0.14 | 31.53 |  |  |
| long | sp400 | vcp | 2022 | 155 | 39 | -0.45 | 33.33 |  |  |
| long | sp400 | vcp | 2023 | 959 | 172 | 0.15 | 41.86 |  |  |
| long | sp400 | vcp | 2024 | 1218 | 220 | 0.01 | 41.36 |  |  |
| long | sp400 | vcp | 2025 | 712 | 127 | 0.14 | 48.82 |  |  |
| long | sp400 | vcp | 2026 | 675 | 134 | -0.04 | 33.58 |  |  |
| long | sp500 | breakout | 2022 | 435 | 169 | -0.36 | 30.77 |  |  |
| long | sp500 | breakout | 2023 | 3238 | 930 | 0.09 | 39.14 |  |  |
| long | sp500 | breakout | 2024 | 3996 | 1135 | 0.22 | 40.18 |  |  |
| long | sp500 | breakout | 2025 | 3388 | 978 | 0.19 | 36.50 |  |  |
| long | sp500 | breakout | 2026 | 2767 | 824 | 0.01 | 28.40 |  |  |
| long | sp500 | dbottom | 2023 | 4 | 4 | 0.62 | 75.00 |  |  |
| long | sp500 | dbottom | 2024 | 3 | 3 | -0.57 | 33.33 |  |  |
| long | sp500 | dbottom | 2025 | 9 | 5 | 0.24 | 60.00 |  |  |
| long | sp500 | dbottom | 2026 | 8 | 3 | -0.65 | 0.00 |  |  |
| long | sp500 | retest | 2022 | 314 | 112 | -0.30 | 33.04 |  |  |
| long | sp500 | retest | 2023 | 1728 | 514 | 0.18 | 47.08 |  |  |
| long | sp500 | retest | 2024 | 2062 | 633 | 0.23 | 46.45 |  |  |
| long | sp500 | retest | 2025 | 1825 | 566 | 0.16 | 45.23 |  |  |
| long | sp500 | retest | 2026 | 1579 | 491 | 0.09 | 33.60 |  |  |
| long | sp500 | vcp | 2022 | 221 | 44 | -0.43 | 29.55 |  |  |
| long | sp500 | vcp | 2023 | 1254 | 207 | 0.05 | 39.61 |  |  |
| long | sp500 | vcp | 2024 | 1718 | 275 | 0.30 | 46.91 |  |  |
| long | sp500 | vcp | 2025 | 1256 | 198 | 0.22 | 51.01 |  |  |
| long | sp500 | vcp | 2026 | 831 | 160 | 0.09 | 38.75 |  |  |
| long | sp600 | breakout | 2022 | 490 | 233 | -0.60 | 19.74 |  |  |
| long | sp600 | breakout | 2023 | 4101 | 1339 | -0.03 | 31.29 |  |  |
| long | sp600 | breakout | 2024 | 4661 | 1498 | 0.07 | 31.71 |  |  |
| long | sp600 | breakout | 2025 | 3431 | 1167 | -0.06 | 28.02 |  |  |
| long | sp600 | breakout | 2026 | 3982 | 1344 | -0.05 | 26.26 |  |  |
| long | sp600 | dbottom | 2022 | 4 | 3 | -0.21 | 33.33 |  |  |
| long | sp600 | dbottom | 2023 | 10 | 9 | 0.20 | 77.78 |  |  |
| long | sp600 | dbottom | 2024 | 8 | 7 | -0.53 | 28.57 |  |  |
| long | sp600 | dbottom | 2025 | 8 | 6 | -1.16 | 0.00 |  |  |
| long | sp600 | dbottom | 2026 | 9 | 5 | 0.30 | 40.00 |  |  |
| long | sp600 | retest | 2022 | 351 | 137 | -0.53 | 20.44 |  |  |
| long | sp600 | retest | 2023 | 2602 | 805 | -0.05 | 37.76 |  |  |
| long | sp600 | retest | 2024 | 3092 | 938 | -0.04 | 34.54 |  |  |
| long | sp600 | retest | 2025 | 2251 | 699 | 0.04 | 36.62 |  |  |
| long | sp600 | retest | 2026 | 2462 | 765 | -0.09 | 33.86 |  |  |
| long | sp600 | vcp | 2022 | 149 | 45 | -0.64 | 13.33 |  |  |
| long | sp600 | vcp | 2023 | 906 | 180 | -0.11 | 33.89 |  |  |
| long | sp600 | vcp | 2024 | 1584 | 309 | -0.11 | 38.51 |  |  |
| long | sp600 | vcp | 2025 | 896 | 165 | 0.43 | 37.58 |  |  |
| long | sp600 | vcp | 2026 | 983 | 203 | -0.17 | 33.00 |  |  |
| short | sp400 | breakdown | 2022 | 107 | 70 |  | 5.71 | -0.85 | -0.90 |
| short | sp400 | breakdown | 2023 | 1221 | 375 |  | 50.93 | 0.12 | 0.05 |
| short | sp400 | breakdown | 2024 | 596 | 298 |  | 22.48 | -0.47 | -0.53 |
| short | sp400 | breakdown | 2025 | 804 | 348 |  | 35.63 | -0.22 | -0.27 |
| short | sp400 | breakdown | 2026 | 618 | 256 |  | 50.78 | 0.06 | 0.01 |
| short | sp400 | breakdown_retest | 2022 | 78 | 39 |  | 2.56 | -0.96 | -1.03 |
| short | sp400 | breakdown_retest | 2023 | 784 | 275 |  | 44.00 | 0.04 | -0.04 |
| short | sp400 | breakdown_retest | 2024 | 279 | 143 |  | 23.08 | -0.52 | -0.59 |
| short | sp400 | breakdown_retest | 2025 | 597 | 263 |  | 28.14 | -0.29 | -0.35 |
| short | sp400 | breakdown_retest | 2026 | 421 | 167 |  | 43.11 | 0.05 | -0.02 |
| short | sp400 | failed_breakout | 2022 | 34 | 25 |  | 16.00 | -0.64 | -0.67 |
| short | sp400 | failed_breakout | 2023 | 70 | 44 |  | 38.64 | -0.28 | -0.33 |
| short | sp400 | failed_breakout | 2024 | 70 | 46 |  | 23.91 | -0.37 | -0.42 |
| short | sp400 | failed_breakout | 2025 | 61 | 35 |  | 42.86 | -0.10 | -0.17 |
| short | sp400 | failed_breakout | 2026 | 71 | 57 |  | 47.37 | -0.07 | -0.11 |
| short | sp500 | breakdown | 2022 | 222 | 116 |  | 14.66 | -0.56 | -0.60 |
| short | sp500 | breakdown | 2023 | 1425 | 455 |  | 43.74 | 0.01 | -0.06 |
| short | sp500 | breakdown | 2024 | 619 | 313 |  | 23.32 | -0.44 | -0.49 |
| short | sp500 | breakdown | 2025 | 733 | 300 |  | 37.67 | -0.17 | -0.22 |
| short | sp500 | breakdown | 2026 | 615 | 292 |  | 43.84 | -0.05 | -0.10 |
| short | sp500 | breakdown_retest | 2022 | 148 | 78 |  | 6.41 | -0.91 | -0.98 |
| short | sp500 | breakdown_retest | 2023 | 813 | 314 |  | 34.71 | -0.21 | -0.29 |
| short | sp500 | breakdown_retest | 2024 | 305 | 157 |  | 22.93 | -0.45 | -0.52 |
| short | sp500 | breakdown_retest | 2025 | 481 | 215 |  | 29.30 | -0.22 | -0.29 |
| short | sp500 | breakdown_retest | 2026 | 408 | 172 |  | 37.21 | -0.20 | -0.27 |
| short | sp500 | failed_breakout | 2022 | 35 | 24 |  | 8.33 | -0.65 | -0.69 |
| short | sp500 | failed_breakout | 2023 | 69 | 49 |  | 40.82 | -0.24 | -0.31 |
| short | sp500 | failed_breakout | 2024 | 72 | 49 |  | 32.65 | -0.32 | -0.38 |
| short | sp500 | failed_breakout | 2025 | 79 | 48 |  | 45.83 | -0.12 | -0.20 |
| short | sp500 | failed_breakout | 2026 | 97 | 67 |  | 40.30 | -0.07 | -0.13 |
| short | sp600 | breakdown | 2022 | 272 | 153 |  | 8.50 | -0.70 | -0.74 |
| short | sp600 | breakdown | 2023 | 2092 | 649 |  | 53.62 | 0.22 | 0.16 |
| short | sp600 | breakdown | 2024 | 944 | 470 |  | 29.79 | -0.36 | -0.41 |
| short | sp600 | breakdown | 2025 | 1514 | 612 |  | 41.99 | -0.08 | -0.12 |
| short | sp600 | breakdown | 2026 | 785 | 335 |  | 52.84 | 0.11 | 0.05 |
| short | sp600 | breakdown_retest | 2022 | 156 | 79 |  | 1.27 | -0.99 | -1.07 |
| short | sp600 | breakdown_retest | 2023 | 1448 | 512 |  | 47.66 | 0.13 | 0.06 |
| short | sp600 | breakdown_retest | 2024 | 481 | 233 |  | 26.18 | -0.41 | -0.47 |
| short | sp600 | breakdown_retest | 2025 | 1152 | 452 |  | 32.08 | -0.10 | -0.16 |
| short | sp600 | breakdown_retest | 2026 | 571 | 217 |  | 41.01 | -0.04 | -0.12 |
| short | sp600 | failed_breakout | 2022 | 77 | 56 |  | 7.14 | -0.65 | -0.68 |
| short | sp600 | failed_breakout | 2023 | 140 | 91 |  | 31.87 | -0.23 | -0.28 |
| short | sp600 | failed_breakout | 2024 | 159 | 99 |  | 32.32 | -0.20 | -0.24 |
| short | sp600 | failed_breakout | 2025 | 88 | 57 |  | 47.37 | -0.01 | -0.06 |
| short | sp600 | failed_breakout | 2026 | 117 | 90 |  | 37.78 | -0.10 | -0.14 |


## 4. Ranker E1_retest_pit500

```json
{
 "strategies": [
  "retest"
 ],
 "signals": 7060,
 "split_counts": {
  "train": 3914,
  "test": 1549,
  "validation": 1300,
  "purged": 248,
  "embargo": 49
 },
 "train_labels": 3904,
 "dev_labels": 5199,
 "trades_validation": 1494,
 "trades_test": 1579,
 "validation": {
  "rs_first": {
   "return_pct": 31.078861843750126,
   "cagr_pct": 41.116474096729185,
   "max_dd_pct": -5.879497833331904,
   "trades": 50,
   "closed": 45,
   "expectancy_r": 0.6321608785069196,
   "expectancy_usd": 66.6976502204727,
   "win_rate": 57.77777777777777,
   "yearly_return_pct": {
    "2025": 31.08
   }
  },
  "random_return_pct": {
   "median": 19.723625667431342,
   "p10": 12.768655073757516,
   "p90": 30.835830605798115
  },
  "grid": [
   {
    "kind": "ridge",
    "params": {
     "alpha": 1.0
    },
    "val_return_pct": 10.099646794162464,
    "val_max_dd_pct": -7.270426698264753,
    "val_daily_ic": -0.013508061011185053,
    "ic_days": 144
   },
   {
    "kind": "ridge",
    "params": {
     "alpha": 10.0
    },
    "val_return_pct": 10.099646794162464,
    "val_max_dd_pct": -7.270426698264732,
    "val_daily_ic": -0.01520168994327713,
    "ic_days": 144
   },
   {
    "kind": "ridge",
    "params": {
     "alpha": 100.0
    },
    "val_return_pct": 7.671776090498428,
    "val_max_dd_pct": -5.1261269311061675,
    "val_daily_ic": -0.0001342034777768206,
    "ic_days": 144
   },
   {
    "kind": "hgb",
    "params": {
     "depth": 2,
     "iter": 100
    },
    "val_return_pct": 34.07755332848057,
    "val_max_dd_pct": -6.1238605277991525,
    "val_daily_ic": -0.014875640240328792,
    "ic_days": 144
   },
   {
    "kind": "hgb",
    "params": {
     "depth": 2,
     "iter": 300
    },
    "val_return_pct": 14.590189661680641,
    "val_max_dd_pct": -5.909943621805169,
    "val_daily_ic": -0.055635138522618734,
    "ic_days": 144
   },
   {
    "kind": "hgb",
    "params": {
     "depth": 3,
     "iter": 100
    },
    "val_return_pct": 9.883824485998982,
    "val_max_dd_pct": -8.002774028921944,
    "val_daily_ic": -0.04203410897410165,
    "ic_days": 144
   },
   {
    "kind": "hgb",
    "params": {
     "depth": 3,
     "iter": 300
    },
    "val_return_pct": 29.505786800985767,
    "val_max_dd_pct": -5.164499953832347,
    "val_daily_ic": -0.05603885363201525,
    "ic_days": 144
   }
  ],
  "chosen": {
   "kind": "hgb",
   "params": {
    "depth": 2,
    "iter": 100
   },
   "val_return_pct": 34.07755332848057,
   "val_max_dd_pct": -6.1238605277991525,
   "val_daily_ic": -0.014875640240328792,
   "ic_days": 144
  }
 },
 "test": {
  "rs_first": {
   "return_pct": 27.500511583492717,
   "cagr_pct": 36.08595447419687,
   "max_dd_pct": -7.716921121764598,
   "trades": 57,
   "closed": 53,
   "expectancy_r": 0.4685045391266353,
   "expectancy_usd": 46.58896049976795,
   "win_rate": 54.71698113207547,
   "yearly_return_pct": {
    "2025": -0.47,
    "2026": 28.1
   }
  },
  "model": {
   "return_pct": 13.742570613603288,
   "cagr_pct": 17.739782553726393,
   "max_dd_pct": -19.53203706347898,
   "trades": 63,
   "closed": 59,
   "expectancy_r": 0.2347340778032008,
   "expectancy_usd": 24.70488524441749,
   "win_rate": 33.89830508474576,
   "yearly_return_pct": {
    "2025": -0.47,
    "2026": 14.28
   }
  },
  "model_daily_ic": -0.05702623143980294,
  "ic_days": 135,
  "random_return_pct": {
   "median": 7.577472246121097,
   "p10": -6.046310720137339,
   "p90": 18.05323591534555
  },
  "model_rank_among_random": 0.84
 },
 "walk_forward_dev": [
  {
   "year": 2024,
   "train_labels": 1704,
   "rs_first_return_pct": 22.70628985092533,
   "model_return_pct": 12.352220798529734,
   "rs_first_dd": -9.903454671600842,
   "model_dd": -12.760767252778948
  },
  {
   "year": 2025,
   "train_labels": 3603,
   "rs_first_return_pct": 23.866966258373722,
   "model_return_pct": 20.250823960919284,
   "rs_first_dd": -8.163883328476407,
   "model_dd": -6.446337574140015
  }
 ]
}
```

## 4. Ranker E2_all_longs_pit500

```json
{
 "strategies": [
  "breakout",
  "retest",
  "vcp",
  "dbottom"
 ],
 "signals": 25801,
 "split_counts": {
  "train": 14881,
  "test": 5014,
  "validation": 4818,
  "purged": 851,
  "embargo": 237
 },
 "train_labels": 14836,
 "dev_labels": 19628,
 "trades_validation": 5406,
 "trades_test": 5167,
 "validation": {
  "rs_first": {
   "return_pct": 4.472070042250165,
   "cagr_pct": 5.725699735728607,
   "max_dd_pct": -11.89566931924092,
   "trades": 66,
   "closed": 61,
   "expectancy_r": 0.16483619783372183,
   "expectancy_usd": 6.364694546781639,
   "win_rate": 36.0655737704918,
   "yearly_return_pct": {
    "2025": 4.47
   }
  },
  "random_return_pct": {
   "median": 16.184816508389076,
   "p10": 1.6032463585683359,
   "p90": 27.656950133631483
  },
  "grid": [
   {
    "kind": "ridge",
    "params": {
     "alpha": 1.0
    },
    "val_return_pct": -5.221698389405372,
    "val_max_dd_pct": -13.66169519786995,
    "val_daily_ic": -0.022161151626595068,
    "ic_days": 159
   },
   {
    "kind": "ridge",
    "params": {
     "alpha": 10.0
    },
    "val_return_pct": -5.221698389405372,
    "val_max_dd_pct": -13.66169519786995,
    "val_daily_ic": -0.02250699624618826,
    "ic_days": 159
   },
   {
    "kind": "ridge",
    "params": {
     "alpha": 100.0
    },
    "val_return_pct": 4.555518199794317,
    "val_max_dd_pct": -12.779091523475273,
    "val_daily_ic": -0.01831606613931115,
    "ic_days": 159
   },
   {
    "kind": "hgb",
    "params": {
     "depth": 2,
     "iter": 100
    },
    "val_return_pct": 11.935848826389982,
    "val_max_dd_pct": -7.057710522234862,
    "val_daily_ic": -0.04672053433910814,
    "ic_days": 159
   },
   {
    "kind": "hgb",
    "params": {
     "depth": 2,
     "iter": 300
    },
    "val_return_pct": 24.98264912666408,
    "val_max_dd_pct": -7.042981367378598,
    "val_daily_ic": -0.03414866416203586,
    "ic_days": 159
   },
   {
    "kind": "hgb",
    "params": {
     "depth": 3,
     "iter": 100
    },
    "val_return_pct": 1.0625047186651804,
    "val_max_dd_pct": -8.62026002754982,
    "val_daily_ic": -0.024392075834481337,
    "ic_days": 159
   },
   {
    "kind": "hgb",
    "params": {
     "depth": 3,
     "iter": 300
    },
    "val_return_pct": -4.14192571508627,
    "val_max_dd_pct": -13.548500661110086,
    "val_daily_ic": -0.0200617897241008,
    "ic_days": 159
   }
  ],
  "chosen": {
   "kind": "hgb",
   "params": {
    "depth": 2,
    "iter": 300
   },
   "val_return_pct": 24.98264912666408,
   "val_max_dd_pct": -7.042981367378598,
   "val_daily_ic": -0.03414866416203586,
   "ic_days": 159
  }
 },
 "test": {
  "rs_first": {
   "return_pct": 11.517505408510376,
   "cagr_pct": 14.826421808229195,
   "max_dd_pct": -16.86347106194167,
   "trades": 86,
   "closed": 83,
   "expectancy_r": 0.22980758450494415,
   "expectancy_usd": 12.904990955070312,
   "win_rate": 27.710843373493976,
   "yearly_return_pct": {
    "2025": -2.01,
    "2026": 13.81
   }
  },
  "model": {
   "return_pct": -11.267374406256037,
   "cagr_pct": -14.067436433848346,
   "max_dd_pct": -26.939640578953473,
   "trades": 69,
   "closed": 64,
   "expectancy_r": -0.25952542466470124,
   "expectancy_usd": -17.847907820901685,
   "win_rate": 23.4375,
   "yearly_return_pct": {
    "2025": -0.7,
    "2026": -10.64
   }
  },
  "model_daily_ic": -0.016444458629821062,
  "ic_days": 149,
  "random_return_pct": {
   "median": 10.368887761040202,
   "p10": -8.298127668826318,
   "p90": 27.04495382876216
  },
  "model_rank_among_random": 0.1
 },
 "walk_forward_dev": [
  {
   "year": 2023,
   "train_labels": 607,
   "rs_first_return_pct": 8.38355889282083,
   "model_return_pct": -1.1776371661156193,
   "rs_first_dd": -13.6250761663684,
   "model_dd": -9.893605671083272
  },
  {
   "year": 2024,
   "train_labels": 5907,
   "rs_first_return_pct": 25.335728805719747,
   "model_return_pct": 8.641653768683199,
   "rs_first_dd": -18.83704427048104,
   "model_dd": -10.808311287118855
  },
  {
   "year": 2025,
   "train_labels": 13814,
   "rs_first_return_pct": 6.5168735598806204,
   "model_return_pct": -1.072461720545148,
   "rs_first_dd": -11.873705641294341,
   "model_dd": -9.213098665491493
  }
 ]
}
```
