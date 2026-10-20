# Journal gap-through-stop fix — before / after (`ci_39510247174_vs_main`)

Frozen prices: 80 tickers, last bar 2026-10-20, sha256 `9bbcddc1440b4a3c…` (`prices_frozen.csv`). Signals 99; stop days identical: **True**; changed signals: **7**.

Before = `core.evaluate_journal` at `2895b9b`; after = current code. max_up changed: **4**; insufficient-data stops: **0**.

## Per strategy

| mode | signals_before | stopped_before | gap_stops_before | avg_now_pct_before | n_5d_before | avg_5d_pct_before | n_10d_before | avg_10d_pct_before | signals_after | stopped_after | gap_stops_after | avg_now_pct_after | n_5d_after | avg_5d_pct_after | n_10d_after | avg_10d_pct_after |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| breakout | 65 | 19 | 0 | 1.60 | 41 | 2.07 | 0 |  | 65 | 19 | 3 | 1.48 | 41 | 1.87 | 0 |  |
| retest | 23 | 5 | 0 | 1.17 | 17 | 0.54 | 0 |  | 23 | 5 | 1 | 1.14 | 17 | 0.50 | 0 |  |
| vcp | 11 | 8 | 0 | -2.05 | 10 | -2.63 | 0 |  | 11 | 8 | 3 | -2.36 | 10 | -2.96 | 0 |  |

## Changed signals (returns in %)

| date | mode | ticker | close | stop | stop_day | exit_price | gap_through_stop | ret_5d_before | ret_5d_after | ret_10d_before | ret_10d_after | ret_now_before | ret_now_after |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-10-12 | breakout | JNJ | 263.73 | 258.99 | 1.00 | 254.56 | True | -1.80 | -3.48 |  |  | -1.80 | -3.48 |
| 2026-10-12 | breakout | FAST | 51.49 | 50.41 | 2.00 | 47.51 | True | -2.10 | -7.73 |  |  | -2.10 | -7.73 |
| 2026-10-12 | breakout | META | 742.96 | 730.91 | 3.00 | 726.56 | True | -1.62 | -2.21 |  |  | -1.62 | -2.21 |
| 2026-10-12 | retest | ZBRA | 388.12 | 374.30 | 3.00 | 371.31 | True | -3.56 | -4.33 |  |  | -3.56 | -4.33 |
| 2026-10-12 | vcp | HPE | 70.33 | 68.81 | 1.00 | 67.56 | True | -2.16 | -3.94 |  |  | -2.16 | -3.94 |
| 2026-10-12 | vcp | ANET | 210.88 | 208.08 | 1.00 | 204.98 | True | -1.33 | -2.80 |  |  | -1.33 | -2.80 |
| 2026-10-12 | vcp | JCI | 155.41 | 149.85 | 3.00 | 149.69 | True | -3.58 | -3.68 |  |  | -3.58 | -3.68 |

## max_up changes (%)

| date | mode | ticker | max_up_before | max_up_after | insufficient_data |
|---|---|---|---|---|---|
| 2026-10-12 | breakout | JNJ | -2.86 | -3.48 | False |
| 2026-10-12 | breakout | FAST | 1.83 | 0.99 | False |
| 2026-10-12 | vcp | HPE | 1.21 | -3.94 | False |
| 2026-10-12 | vcp | ANET | -2.69 | -2.80 | False |

## FAST and BAX (returns in %)

| date | mode | ticker | close | stop | stop_day | exit_price | gap_through_stop | ret_5d_before | ret_5d_after | ret_10d_before | ret_10d_after | ret_now_before | ret_now_after |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-10-12 | breakout | BAX | 24.78 | 24.35 | 6.00 | 24.35 | False | 0.85 | 0.85 |  |  | -1.74 | -1.74 |
| 2026-10-12 | breakout | FAST | 51.49 | 50.41 | 2.00 | 47.51 | True | -2.10 | -7.73 |  |  | -2.10 | -7.73 |
| 2026-10-12 | retest | BAX | 24.78 | 23.27 |  |  |  | 0.85 | 0.85 |  |  | -1.09 | -1.09 |

