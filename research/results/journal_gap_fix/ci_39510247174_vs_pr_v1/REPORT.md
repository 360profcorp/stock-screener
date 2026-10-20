# Journal gap-through-stop fix — before / after (`ci_39510247174_vs_pr_v1`)

Frozen prices: 80 tickers, last bar 2026-10-20, sha256 `9bbcddc1440b4a3c…` (`prices_frozen.csv`). Signals 99; stop days identical: **True**; changed signals: **0**.

Before = `core.evaluate_journal` at `5976fe4`; after = current code. max_up changed: **4**; insufficient-data stops: **0**.

## Per strategy

| mode | signals_before | stopped_before | gap_stops_before | avg_now_pct_before | n_5d_before | avg_5d_pct_before | n_10d_before | avg_10d_pct_before | signals_after | stopped_after | gap_stops_after | avg_now_pct_after | n_5d_after | avg_5d_pct_after | n_10d_after | avg_10d_pct_after |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| breakout | 65 | 19 | 3 | 1.48 | 41 | 1.87 | 0 |  | 65 | 19 | 3 | 1.48 | 41 | 1.87 | 0 |  |
| retest | 23 | 5 | 1 | 1.14 | 17 | 0.50 | 0 |  | 23 | 5 | 1 | 1.14 | 17 | 0.50 | 0 |  |
| vcp | 11 | 8 | 3 | -2.36 | 10 | -2.96 | 0 |  | 11 | 8 | 3 | -2.36 | 10 | -2.96 | 0 |  |

## Changed signals (returns in %)

| date | mode | ticker | close | stop | stop_day | exit_price | gap_through_stop | ret_5d_before | ret_5d_after | ret_10d_before | ret_10d_after | ret_now_before | ret_now_after |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

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
| 2026-10-12 | breakout | FAST | 51.49 | 50.41 | 2.00 | 47.51 | True | -7.73 | -7.73 |  |  | -7.73 | -7.73 |
| 2026-10-12 | retest | BAX | 24.78 | 23.27 |  |  |  | 0.85 | 0.85 |  |  | -1.09 | -1.09 |

