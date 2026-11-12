# Index benchmarks v2 (dividend fix) — report

git `3eb51549c2cede685054df538c931b8f8a33d2ee`; books unchanged from `research/results/event_base/runs/2026-10-26T011603Z`.
v1 numbers reproduced before the fix: **True**.

| benchmark | window | ETF bps | CAGR v1 % | CAGR v2 % | Δ pt | max DD v1 % | max DD v2 % | distributions v2 $ |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| SPY100 | full | 2 | 13.54 | 14.33 | +0.79 | -32.04 | -33.39 | 2319 |
| SPY100 | full | 5 | 13.53 | 14.33 | +0.79 | -32.05 | -33.40 | 2319 |
| SPY50_CASH50 | full | 2 | 7.25 | 7.25 | -0.00 | -17.07 | -17.07 | 866 |
| SPY50_CASH50 | full | 5 | 7.26 | 7.24 | -0.02 | -17.07 | -17.07 | 866 |
| SPY50_BIL50 | full | 2 | 8.70 | 8.67 | -0.03 | -16.92 | -16.92 | 2632 |
| SPY50_BIL50 | full | 5 | 8.64 | 8.60 | -0.04 | -16.93 | -16.93 | 2618 |
| SPY_TIMING50 | full | 2 | 3.76 | 3.70 | -0.06 | -7.74 | -7.74 | 479 |
| SPY_TIMING50 | full | 5 | 3.59 | 3.55 | -0.04 | -7.93 | -7.90 | 476 |
| SPY100 | y2017_2021 | 2 | 16.90 | 17.58 | +0.68 | -32.04 | -33.39 | 931 |
| SPY100 | y2017_2021 | 5 | 16.90 | 17.58 | +0.68 | -32.05 | -33.40 | 931 |
| SPY50_CASH50 | y2017_2021 | 2 | 8.92 | 8.92 | +0.00 | -17.07 | -17.07 | 407 |
| SPY50_CASH50 | y2017_2021 | 5 | 8.91 | 8.91 | +0.00 | -17.07 | -17.07 | 407 |
| SPY50_BIL50 | y2017_2021 | 2 | 9.62 | 9.62 | -0.00 | -16.92 | -16.92 | 636 |
| SPY50_BIL50 | y2017_2021 | 5 | 9.61 | 9.50 | -0.11 | -16.93 | -16.93 | 634 |
| SPY_TIMING50 | y2017_2021 | 2 | 4.62 | 4.62 | -0.00 | -7.46 | -7.47 | 324 |
| SPY_TIMING50 | y2017_2021 | 5 | 4.39 | 4.35 | -0.04 | -7.87 | -7.90 | 321 |
| SPY100 | y2022_2026 | 2 | 10.75 | 11.21 | +0.46 | -23.26 | -24.33 | 691 |
| SPY100 | y2022_2026 | 5 | 10.75 | 11.20 | +0.46 | -23.27 | -24.34 | 691 |
| SPY50_CASH50 | y2022_2026 | 2 | 5.71 | 5.71 | +0.00 | -12.02 | -12.02 | 320 |
| SPY50_CASH50 | y2022_2026 | 5 | 5.68 | 5.68 | -0.01 | -12.03 | -12.03 | 318 |
| SPY50_BIL50 | y2022_2026 | 2 | 7.80 | 7.56 | -0.24 | -11.75 | -11.74 | 1346 |
| SPY50_BIL50 | y2022_2026 | 5 | 7.57 | 7.55 | -0.02 | -11.76 | -11.76 | 1346 |
| SPY_TIMING50 | y2022_2026 | 2 | 3.00 | 2.91 | -0.08 | -7.21 | -7.21 | 128 |
| SPY_TIMING50 | y2022_2026 | 5 | 2.73 | 2.68 | -0.05 | -7.52 | -7.52 | 127 |

## Criteria 4–5 with v2 benchmarks (C and S books unchanged)

- **C: NOT_A_CANDIDATE** (v1: NOT_A_CANDIDATE) — {"1_drawdown": false, "2_result": false, "4_vs_5050_bil": false, "5_no_simpler_dominates": false, "6_sample": true}; dominated by: ['SPY50_CASH50 dominates at 10 bps', 'SPY50_CASH50 dominates at 25 bps', 'SPY50_BIL50 dominates at 10 bps', 'SPY50_BIL50 dominates at 25 bps', 'SPY_TIMING50 dominates at 10 bps', 'SPY_TIMING50 dominates at 25 bps']
- **S: NOT_A_CANDIDATE** (v1: NOT_A_CANDIDATE) — {"1_drawdown": false, "2_result": false, "3_signal_benefit": false, "4_vs_5050_bil": false, "5_no_simpler_dominates": false, "6_sample": true}; dominated by: ['SPY50_CASH50 dominates at 10 bps', 'SPY50_CASH50 dominates at 25 bps', 'SPY50_BIL50 dominates at 10 bps', 'SPY50_BIL50 dominates at 25 bps', 'SPY_TIMING50 dominates at 10 bps', 'SPY_TIMING50 dominates at 25 bps']
