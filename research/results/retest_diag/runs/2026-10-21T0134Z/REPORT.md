# Retest RS-first v1 — diagnostic (historical backtest, PIT S&P 500)

Exploratory cuts, not evidence for new rules. Live paper trading is not included.

Reproduction of the saved result: **OK**. Reconciliation to the cent: **True**.

## Skipped orders

| outcome | orders | closed | mean_r_if_taken | median_r_if_taken |
|---|---|---|---|---|
| capital_or_risk | 6 | 5 | 0.34 | -0.13 |
| daily_entries | 62 | 62 | 0.46 | 0.10 |
| positions | 6078 | 5977 | 0.01 | -0.47 |
| ticker_open | 613 | 604 | 0.31 | -0.02 |

## Cut: year

Executed portfolio trades:

| year | trades | mean_r | median_r | profit_factor | win_rate | small_sample | pnl_usd | pnl_share_pct |
|---|---|---|---|---|---|---|---|---|
| 2022 | 16 | -0.43 | -1.03 | 0.43 | 18.75 | True | -618.40 | -9.50 |
| 2023 | 62 | -0.06 | -0.25 | 0.86 | 43.55 | False | -410.46 | -6.30 |
| 2024 | 71 | 0.26 | -0.12 | 1.50 | 47.89 | False | 1693.15 | 26.00 |
| 2025 | 63 | 0.56 | 0.11 | 2.26 | 50.79 | False | 3780.36 | 58.05 |
| 2026 | 49 | 0.34 | 0.42 | 1.71 | 57.14 | False | 2067.16 | 31.74 |

Signals (non-overlapping model trades, 10 bps):

| year | trades | mean_r | median_r | profit_factor | win_rate | small_sample |
|---|---|---|---|---|---|---|
| 2022 | 109 | -0.25 | -0.80 | 0.56 | 33.94 | False |
| 2023 | 475 | 0.12 | -0.14 | 1.25 | 46.32 | False |
| 2024 | 577 | 0.12 | -0.18 | 1.26 | 44.37 | False |
| 2025 | 538 | 0.07 | -0.30 | 1.13 | 44.24 | False |
| 2026 | 484 | 0.08 | -1.02 | 1.13 | 33.47 | False |

## Cut: quarter

Executed portfolio trades:

| quarter | trades | mean_r | median_r | profit_factor | win_rate | small_sample | pnl_usd | pnl_share_pct |
|---|---|---|---|---|---|---|---|---|
| 2022Q4 | 16 | -0.43 | -1.03 | 0.43 | 18.75 | True | -618.40 | -9.50 |
| 2023Q1 | 18 | -0.23 | -0.68 | 0.58 | 38.89 | True | -347.82 | -5.34 |
| 2023Q2 | 17 | 0.01 | -0.41 | 1.03 | 47.06 | True | -29.58 | -0.45 |
| 2023Q3 | 17 | -0.54 | -1.02 | 0.18 | 23.53 | True | -711.04 | -10.92 |
| 2023Q4 | 10 | 0.91 | 0.58 | 18.41 | 80.00 | True | 677.98 | 10.41 |
| 2024Q1 | 19 | 0.21 | -0.11 | 1.32 | 47.37 | True | 367.48 | 5.64 |
| 2024Q2 | 13 | 0.33 | 0.68 | 2.20 | 53.85 | True | 370.53 | 5.69 |
| 2024Q3 | 20 | 0.05 | -0.33 | 1.08 | 45.00 | True | 34.95 | 0.54 |
| 2024Q4 | 19 | 0.49 | -0.35 | 1.96 | 47.37 | True | 920.20 | 14.13 |
| 2025Q1 | 12 | -0.62 | -1.03 | 0.23 | 8.33 | True | -697.98 | -10.72 |
| 2025Q2 | 12 | 0.71 | 0.99 | 5.09 | 83.33 | True | 803.89 | 12.35 |
| 2025Q3 | 21 | 0.73 | -0.32 | 2.44 | 47.62 | True | 1602.67 | 24.61 |
| 2025Q4 | 18 | 1.04 | 0.42 | 4.42 | 61.11 | True | 2071.77 | 31.82 |
| 2026Q1 | 9 | 0.24 | 0.42 | 1.43 | 55.56 | True | 144.75 | 2.22 |
| 2026Q2 | 19 | 0.58 | 0.46 | 2.75 | 68.42 | True | 1411.44 | 21.68 |
| 2026Q3 | 18 | 0.36 | 0.06 | 1.73 | 55.56 | True | 895.20 | 13.75 |
| 2026Q4 | 3 | -1.03 | -1.04 | 0.00 | 0.00 | True | -384.24 | -5.90 |

Signals (non-overlapping model trades, 10 bps):

| quarter | trades | mean_r | median_r | profit_factor | win_rate | small_sample |
|---|---|---|---|---|---|---|
| 2022Q4 | 109 | -0.25 | -0.80 | 0.56 | 33.94 | False |
| 2023Q1 | 133 | -0.18 | -0.33 | 0.63 | 37.59 | False |
| 2023Q2 | 143 | 0.46 | 0.37 | 2.25 | 57.34 | False |
| 2023Q3 | 99 | -0.52 | -1.03 | 0.30 | 24.24 | False |
| 2023Q4 | 100 | 0.66 | 0.47 | 3.15 | 64.00 | False |
| 2024Q1 | 150 | 0.45 | 0.29 | 2.21 | 53.33 | False |
| 2024Q2 | 144 | -0.07 | -0.45 | 0.88 | 38.89 | False |
| 2024Q3 | 150 | -0.08 | -0.33 | 0.86 | 42.67 | False |
| 2024Q4 | 133 | 0.19 | -0.34 | 1.38 | 42.11 | False |
| 2025Q1 | 78 | -0.63 | -1.03 | 0.23 | 21.79 | False |
| 2025Q2 | 118 | 0.48 | 0.31 | 2.34 | 58.47 | False |
| 2025Q3 | 174 | 0.12 | -0.20 | 1.24 | 44.83 | False |
| 2025Q4 | 168 | 0.05 | -0.39 | 1.10 | 44.05 | False |
| 2026Q1 | 115 | 0.10 | -1.02 | 1.17 | 36.52 | False |
| 2026Q2 | 196 | 0.33 | -0.83 | 1.59 | 41.84 | False |
| 2026Q3 | 165 | -0.17 | -1.02 | 0.77 | 23.03 | False |
| 2026Q4 | 8 | -1.03 | -1.03 | 0.00 | 0.00 | True |

## Cut: sector

Executed portfolio trades:

| sector | trades | mean_r | median_r | profit_factor | win_rate | small_sample | pnl_usd | pnl_share_pct |
|---|---|---|---|---|---|---|---|---|
| Communication Services | 12 | -0.24 | -1.03 | 0.64 | 25.00 | True | -289.09 | -4.44 |
| Consumer Discretionary | 36 | 0.12 | -0.34 | 1.23 | 41.67 | False | 443.86 | 6.82 |
| Consumer Staples | 6 | 0.72 | 0.53 | 3.09 | 66.67 | True | 365.49 | 5.61 |
| Energy | 18 | -0.30 | -1.02 | 0.57 | 27.78 | True | -539.96 | -8.29 |
| Financials | 12 | -0.23 | -0.00 | 0.57 | 50.00 | True | -337.74 | -5.19 |
| Health Care | 27 | -0.25 | -1.03 | 0.62 | 37.04 | True | -280.83 | -4.31 |
| Industrials | 41 | 0.15 | -0.11 | 1.36 | 48.78 | False | 661.04 | 10.15 |
| Information Technology | 86 | 0.50 | 0.40 | 2.12 | 55.81 | False | 4470.81 | 68.66 |
| Materials | 8 | 1.73 | 1.50 | 7.51 | 75.00 | True | 1645.55 | 25.27 |
| Real Estate | 3 | 0.72 | 0.92 | 3.08 | 66.67 | True | 179.87 | 2.76 |
| Utilities | 11 | 0.17 | -1.02 | 1.30 | 36.36 | True | 72.21 | 1.11 |
| unknown | 1 | 1.40 | 1.40 |  | 100.00 | True | 120.57 | 1.85 |

Signals (non-overlapping model trades, 10 bps):

| sector | trades | mean_r | median_r | profit_factor | win_rate | small_sample |
|---|---|---|---|---|---|---|
| Communication Services | 128 | -0.02 | -0.22 | 0.96 | 44.53 | False |
| Consumer Discretionary | 285 | 0.19 | -0.16 | 1.38 | 45.96 | False |
| Consumer Staples | 64 | -0.21 | -1.03 | 0.66 | 32.81 | False |
| Energy | 113 | -0.19 | -1.02 | 0.69 | 33.63 | False |
| Financials | 222 | -0.17 | -0.43 | 0.68 | 37.84 | False |
| Health Care | 212 | -0.01 | -0.53 | 0.98 | 36.32 | False |
| Industrials | 393 | 0.12 | -0.23 | 1.24 | 44.78 | False |
| Information Technology | 578 | 0.24 | -0.53 | 1.45 | 42.21 | False |
| Materials | 84 | 0.08 | -0.13 | 1.16 | 46.43 | False |
| Real Estate | 38 | 0.09 | -0.28 | 1.19 | 47.37 | False |
| Utilities | 59 | 0.07 | -0.45 | 1.13 | 44.07 | False |
| unknown | 7 | -0.32 | -1.04 | 0.61 | 28.57 | True |

## Cut: market

Executed portfolio trades:

| market | trades | mean_r | median_r | profit_factor | win_rate | small_sample | pnl_usd | pnl_share_pct |
|---|---|---|---|---|---|---|---|---|
| SPY<=MA200 | 23 | -0.08 | -1.02 | 0.86 | 34.78 | True | -162.52 | -2.50 |
| SPY>MA200 | 238 | 0.26 | -0.12 | 1.53 | 48.74 | False | 6674.33 | 102.50 |

Signals (non-overlapping model trades, 10 bps):

| market | trades | mean_r | median_r | profit_factor | win_rate | small_sample |
|---|---|---|---|---|---|---|
| SPY<=MA200 | 180 | -0.08 | -0.30 | 0.84 | 40.56 | False |
| SPY>MA200 | 2003 | 0.10 | -0.39 | 1.18 | 41.94 | False |

## Cut: stop_dist

Executed portfolio trades:

| stop_dist | trades | mean_r | median_r | profit_factor | win_rate | small_sample | pnl_usd | pnl_share_pct |
|---|---|---|---|---|---|---|---|---|
| 3-5% | 44 | 0.31 | -0.39 | 1.49 | 36.36 | False | 1436.82 | 22.06 |
| 5-8% | 128 | 0.18 | -0.37 | 1.35 | 44.53 | False | 2665.58 | 40.93 |
| <=3% | 1 | 0.30 | 0.30 |  | 100.00 | True | 17.13 | 0.26 |
| >8% | 88 | 0.25 | 0.29 | 1.63 | 56.82 | False | 2392.28 | 36.74 |

Signals (non-overlapping model trades, 10 bps):

| stop_dist | trades | mean_r | median_r | profit_factor | win_rate | small_sample |
|---|---|---|---|---|---|---|
| 3-5% | 583 | 0.13 | -1.04 | 1.21 | 38.94 | False |
| 5-8% | 1111 | 0.05 | -0.41 | 1.09 | 41.49 | False |
| <=3% | 32 | -0.05 | -1.08 | 0.94 | 28.12 | False |
| >8% | 457 | 0.11 | -0.07 | 1.28 | 47.26 | False |

## All numbers

```json
{
 "plan": "research/retest_diag/PLAN.md",
 "dataset_sha256": {
  "signals.csv.gz": "98b6f81623ea3f20e5e5adc313891762c1a4e3ff0970f907fe7f17081a241cf3",
  "bars.pkl.gz": "3df57ff951cf7f580ffbc088be003dfcdb872fabd66000e74b508cd73f69283e"
 },
 "data_end": "2026-10-14",
 "window": [
  "2022-10-27",
  "2026-10-14"
 ],
 "git": "298169eea520809679dbdc59029043c9ba3b5a3a",
 "reproduction": {
  "ok": true,
  "checks": {
   "return_pct": {
    "saved": 68.35310415699882,
    "now": 68.35310415699882,
    "equal": true
   },
   "max_dd_pct": {
    "saved": -19.20456303303514,
    "now": -19.20456303303514,
    "equal": true
   },
   "executed": {
    "saved": 265,
    "now": 265,
    "equal": true
   },
   "closed": {
    "saved": 261,
    "now": 261,
    "equal": true
   },
   "expectancy_r": {
    "saved": 0.22771964261522995,
    "now": 0.22771964261522995,
    "equal": true
   }
  }
 },
 "portfolio": {
  "return_pct": 68.35310415699882,
  "cagr_pct": 14.041528575651107,
  "max_dd_pct": -19.20456303303514,
  "executed": 265,
  "closed": 261,
  "open_end": 4,
  "expectancy_r": 0.22771964261522995,
  "median_r": -0.17988382648186751,
  "profit_factor": 1.456699576675837,
  "win_rate": 47.509578544061306,
  "final_equity": 16835.31041569988,
  "yearly_return_pct": {
   "2022": -10.11,
   "2023": 2.6,
   "2024": 15.43,
   "2025": 20.71,
   "2026": 31.0
  }
 },
 "layers": {
  "signals_eligible": 7060,
  "signals_nonoverlap_closed": 2183,
  "signal_level": {
   "trades": 2183,
   "win_rate": 41.8231791113147,
   "mean_r": 0.08104509807960399,
   "median_r": -0.3781757619931913,
   "mean_r_ex_top5": 0.05110097135143462,
   "profit_factor": 1.1527444201763857,
   "stopped_pct": 45.0755840586349,
   "avg_bars": 14.587265231333028,
   "se_mean_r": 0.033593190702895875
  },
  "portfolio_candidates": 7024,
  "executed": 265,
  "skipped_orders": 6759,
  "skipped_by_reason": [
   {
    "outcome": "capital_or_risk",
    "orders": 6,
    "closed": 5,
    "mean_r_if_taken": 0.33859101615179515,
    "median_r_if_taken": -0.1285558021032464
   },
   {
    "outcome": "daily_entries",
    "orders": 62,
    "closed": 62,
    "mean_r_if_taken": 0.46213512115585254,
    "median_r_if_taken": 0.09629992245440935
   },
   {
    "outcome": "positions",
    "orders": 6078,
    "closed": 5977,
    "mean_r_if_taken": 0.007107252824400854,
    "median_r_if_taken": -0.46771542138064987
   },
   {
    "outcome": "ticker_open",
    "orders": 613,
    "closed": 604,
    "mean_r_if_taken": 0.3068855540031707,
    "median_r_if_taken": -0.018801201650156953
   }
  ],
  "outside_window": 0
 },
 "reconciliation": {
  "final_equity": 16835.31041569988,
  "initial": 10000.0,
  "total_pnl": 6835.310415699882,
  "closed_net_pnl": 6511.802544667164,
  "closed_trades": 261,
  "open_positions": 4,
  "open_mark_pnl_in_equity": 323.50787103271534,
  "open_exit_fee_not_charged": 6.211610000610351,
  "difference": 2.6147972675971687e-12,
  "reconciled_to_the_cent": true
 },
 "concentration": {
  "total_pnl": 6835.310415699882,
  "closed_pnl": 6511.802544667164,
  "top5_trades_usd": 3377.683233589173,
  "top10_trades_usd": 5860.941893867495,
  "top5_tickers": {
   "STX": 1504.1,
   "ALB": 808.09,
   "PLTR": 744.1,
   "TPR": 700.44,
   "GLW": 654.91
  },
  "top5_tickers_usd": 4411.640663896106,
  "worst5_tickers": {
   "HII": -239.64,
   "VST": -249.17,
   "MPC": -352.48,
   "NFLX": -367.77,
   "PANW": -452.8
  },
  "pnl_by_exit_year": {
   "2022": -1051.3,
   "2023": -212.11,
   "2024": 2089.55,
   "2025": 2219.55,
   "2026": 3466.12
  },
  "best_exit_year": 2026,
  "best_exit_year_usd": 3466.115725658501,
  "mean_r_all": 0.2277196426152301,
  "mean_r_ex_top5": 0.10420053820478481,
  "mean_r_ex_top10": 0.01998350805186635,
  "top5_trades": [
   {
    "ticker": "PLTR",
    "signal_date": "2024-10-17",
    "net_pnl": 780.3580044937137,
    "net_r": 8.060546182436212
   },
   {
    "ticker": "TER",
    "signal_date": "2025-12-26",
    "net_pnl": 693.1963871459961,
    "net_r": 7.652189510476968
   },
   {
    "ticker": "STX",
    "signal_date": "2025-09-02",
    "net_pnl": 682.496401855469,
    "net_r": 7.0182144779629985
   },
   {
    "ticker": "ALB",
    "signal_date": "2025-12-26",
    "net_pnl": 628.495209716797,
    "net_r": 4.8118356366059345
   },
   {
    "ticker": "ILMN",
    "signal_date": "2026-09-02",
    "net_pnl": 593.1372303771973,
    "net_r": 4.166810559353282
   }
  ],
  "worst5_trades": [
   {
    "ticker": "MRNA",
    "signal_date": "2026-07-09",
    "net_pnl": -165.8683183819578,
    "net_r": -1.0255648663955306
   },
   {
    "ticker": "KKR",
    "signal_date": "2024-07-18",
    "net_pnl": -178.06234362030023,
    "net_r": -1.9872472304720377
   },
   {
    "ticker": "HII",
    "signal_date": "2026-01-16",
    "net_pnl": -209.18454656982408,
    "net_r": -1.9402186346673889
   },
   {
    "ticker": "DVA",
    "signal_date": "2026-07-10",
    "net_pnl": -285.38606109619104,
    "net_r": -1.7964961820426089
   },
   {
    "ticker": "PANW",
    "signal_date": "2024-01-26",
    "net_pnl": -337.0358401489257,
    "net_r": -4.344061797282776
   }
  ],
  "winners_usd": 19151.00445732118,
  "losers_usd": -12639.201912654022,
  "top5_trades_residual_usd": 3457.6271821107084,
  "top10_trades_residual_usd": 974.3685218323863,
  "top5_tickers_residual_usd": 2423.6697518037754,
  "best_exit_year_residual_usd": 3369.1946900413805
 },
 "execution": {
  "sessions": 994,
  "share_sessions_with_position": 90.84507042253522,
  "mean_slots_used": 3.995975855130785,
  "share_sessions_all_5_used": 60.66398390342053,
  "stops": 109,
  "time_exits": 152,
  "gap_through_stop_trades": 16,
  "gap_pnl_usd": -2372.2735585174532,
  "gap_extra_loss_vs_stop_usd": -813.035123634338,
  "gap_mean_r": -1.5798115226537157,
  "gap_worst_r": -4.344061797282776,
  "signals_gap_through_stop": 144,
  "signals_gap_mean_r": -1.3499456303670794,
  "mean_bars_held": 15.080459770114942,
  "candidates": 7024,
  "entered": 265,
  "outside_window": 0,
  "skipped": {
   "daily_entries": 62,
   "positions": 6078,
   "ticker_open": 613,
   "capital_or_risk": 6
  },
  "cash_limited_entries": 0
 },
 "costs": {
  "signal_level": {
   "10bps": {
    "trades": 2183,
    "win_rate": 41.8231791113147,
    "mean_r": 0.08104509807960399,
    "median_r": -0.3781757619931913,
    "mean_r_ex_top5": 0.05110097135143462,
    "profit_factor": 1.1527444201763857,
    "stopped_pct": 45.0755840586349,
    "avg_bars": 14.587265231333028,
    "se_mean_r": 0.033593190702895875
   },
   "25bps": {
    "trades": 2183,
    "win_rate": 41.13605130554283,
    "mean_r": 0.02902550898726096,
    "median_r": -0.4176950946737268,
    "mean_r_ex_top5": -0.0008561150253293462,
    "profit_factor": 1.0517541021154484,
    "stopped_pct": 45.0755840586349,
    "avg_bars": 14.587265231333028,
    "se_mean_r": 0.03354672880896354
   },
   "50bps": {
    "trades": 2183,
    "win_rate": 39.80760421438387,
    "mean_r": -0.057673806166644116,
    "median_r": -0.4795633609951193,
    "mean_r_ex_top5": -0.08745125898660241,
    "profit_factor": 0.9057537487075821,
    "stopped_pct": 45.0755840586349,
    "avg_bars": 14.587265231333028,
    "se_mean_r": 0.033480955370469495
   }
  },
  "portfolio_recomputed": {
   "10bps": {
    "return_pct": 68.35310415699882,
    "cagr_pct": 14.041528575651107,
    "max_dd_pct": -19.20456303303514,
    "executed": 265,
    "expectancy_r": 0.22771964261522995,
    "profit_factor": 1.456699576675837,
    "yearly_return_pct": {
     "2022": -10.11,
     "2023": 2.6,
     "2024": 15.43,
     "2025": 20.71,
     "2026": 31.0
    }
   },
   "25bps": {
    "return_pct": 48.043315046056165,
    "cagr_pct": 10.40268454151876,
    "max_dd_pct": -21.63956242972863,
    "executed": 266,
    "expectancy_r": 0.17762175739636385,
    "profit_factor": 1.336334157540279,
    "yearly_return_pct": {
     "2022": -10.76,
     "2023": -0.22,
     "2024": 10.33,
     "2025": 16.85,
     "2026": 28.96
    }
   },
   "50bps": {
    "return_pct": 23.650654561403563,
    "cagr_pct": 5.500869147835208,
    "max_dd_pct": -24.826118814702625,
    "executed": 266,
    "expectancy_r": 0.10155395807327808,
    "profit_factor": 1.1781304906396084,
    "yearly_return_pct": {
     "2022": -11.86,
     "2023": -3.5,
     "2024": 4.32,
     "2025": 12.74,
     "2026": 23.62
    }
   }
  }
 },
 "live_paper_trading": "not used (historical backtest only)"
}
```