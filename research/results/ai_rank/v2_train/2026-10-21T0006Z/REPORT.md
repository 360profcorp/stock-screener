# AI ranking v2.1 — training and gate (PREREG v2.1)

**Gate verdict: FAILED — v2 is reported as failed and RS-first stays** (written to gate.json at 2026-10-21T00:16:13+00:00, before the historical window was computed).

## deciding

Features (26): rs_score, rank_rs, log_adv, atr14_pct, vol_ratio, vol10_vs_50, ret_1d, ret_5d, ret_20d, ret_63d, dist_ma50, dist_ma150, dist_ma200, dist_52w_high, dist_52w_low, dist_level_pct, risk_at_close_pct, spy_above200, spy_ret_20d, sess_since_earn, sector_rs_median, sector_ret20_median, rs_minus_sector, breadth_ma50, breadth_new_high, breadth_chg5

Counts: {'signals': 7060, 'labelled': 6909, 'train': 3904, 'validation': 1295, 'dev': 5199, 'nonoverlap_train': 1228, 'nonoverlap_validation': 389, 'trades_validation': 1494}

Validation grid (selection = mean daily IC):

| model | val_ic_mean | val_ic_days | val_return_pct | val_max_dd_pct | params |
|---|---|---|---|---|---|
| ridge | 0.0127 | 126 | 17.4637 | -5.5143 | {"alpha": 1.0} |
| ridge | 0.0106 | 126 | 7.2582 | -7.8203 | {"alpha": 10.0} |
| ridge | 0.0151 | 126 | 12.5932 | -6.0339 | {"alpha": 100.0} |
| hgb | 0.0003 | 126 | 42.5122 | -7.0107 | {"depth": 2, "iter": 100} |
| hgb | 0.0114 | 126 | 31.9469 | -4.5877 | {"depth": 2, "iter": 300} |
| hgb | -0.0128 | 126 | 29.6074 | -7.0511 | {"depth": 3, "iter": 100} |
| hgb | 0.0088 | 126 | 34.9876 | -5.6062 | {"depth": 3, "iter": 300} |

Chosen: ridge {'alpha': 100.0}
Validation RS-first return 31.08 %, random median 17.70 %

Walk-forward:

| year | skipped | train_labels | scored | nonoverlap_scored | ic_mean | ic_days | rs_first_return_pct | model_return_pct | rs_first_dd | model_dd |
|---|---|---|---|---|---|---|---|---|---|---|
| 2023 | True | 203 |  |  |  |  |  |  |  |  |
| 2024 | False | 1704 | 1830.0000 | 583.0000 | 0.0249 | 185.0000 | 22.7063 | 19.8152 | -9.9035 | -11.7730 |
| 2025 | False | 3603 | 1721.0000 | 539.0000 | -0.0449 | 168.0000 | 23.8670 | 13.1557 | -8.1639 | -9.3054 |

Pooled walk-forward IC: {'mean': -0.008318581581558356, 'days': 353, 'ci90': (-0.048056187247915313, 0.02864241679410196), 'definition': 'daily ICs of the out-of-sample walk-forward years 2023-2025, each day once; bootstrap by day'}

Gate: {'eligible': True, 'g1_ic_positive_every_wf_year_and_validation': False, 'g2_pooled_ic_ge_0_03_and_ci_above_0': False, 'g3_portfolio_vs_rs_first_and_random': False, 'worst_wf_return_gap_pp': -10.711297516386374, 'passed': False}

## sensitivity

Features (27): rs_score, rank_rs, log_adv, atr14_pct, vol_ratio, vol10_vs_50, ret_1d, ret_5d, ret_20d, ret_63d, dist_ma50, dist_ma150, dist_ma200, dist_52w_high, dist_52w_low, dist_level_pct, risk_at_close_pct, spy_above200, spy_ret_20d, sess_since_earn, sector_rs_median, sector_ret20_median, rs_minus_sector, breadth_ma50, breadth_new_high, breadth_chg5, earn_within_5

Counts: {'signals': 7060, 'labelled': 6909, 'train': 3904, 'validation': 1295, 'dev': 5199, 'nonoverlap_train': 1228, 'nonoverlap_validation': 389, 'trades_validation': 1494}

Validation grid (selection = mean daily IC):

| model | val_ic_mean | val_ic_days | val_return_pct | val_max_dd_pct | params |
|---|---|---|---|---|---|
| ridge | 0.0192 | 126 | 17.8181 | -4.4382 | {"alpha": 1.0} |
| ridge | 0.0242 | 126 | 17.8181 | -4.4382 | {"alpha": 10.0} |
| ridge | 0.0320 | 126 | 26.0865 | -3.8178 | {"alpha": 100.0} |
| hgb | 0.0003 | 126 | 42.5122 | -7.0107 | {"depth": 2, "iter": 100} |
| hgb | 0.0208 | 126 | 35.7720 | -5.2883 | {"depth": 2, "iter": 300} |
| hgb | -0.0158 | 126 | 28.1990 | -7.0511 | {"depth": 3, "iter": 100} |
| hgb | -0.0026 | 126 | 39.6064 | -5.6986 | {"depth": 3, "iter": 300} |

Chosen: ridge {'alpha': 100.0}
Validation RS-first return 31.08 %, random median 17.70 %

Walk-forward:

| year | skipped | train_labels | scored | nonoverlap_scored | ic_mean | ic_days | rs_first_return_pct | model_return_pct | rs_first_dd | model_dd |
|---|---|---|---|---|---|---|---|---|---|---|
| 2023 | True | 203 |  |  |  |  |  |  |  |  |
| 2024 | False | 1704 | 1830.0000 | 583.0000 | 0.0543 | 185.0000 | 22.7063 | 11.8054 | -9.9035 | -10.4965 |
| 2025 | False | 3603 | 1721.0000 | 539.0000 | -0.0473 | 168.0000 | 23.8670 | 9.4379 | -8.1639 | -6.4185 |

Pooled walk-forward IC: {'mean': 0.005992658186959454, 'days': 353, 'ci90': (-0.034263736673653636, 0.04434281612422651), 'definition': 'daily ICs of the out-of-sample walk-forward years 2023-2025, each day once; bootstrap by day'}

Gate: {'eligible': False, 'g1_ic_positive_every_wf_year_and_validation': False, 'g2_pooled_ic_ge_0_03_and_ci_above_0': False, 'g3_portfolio_vs_rs_first_and_random': False, 'worst_wf_return_gap_pp': -14.4290949201481, 'passed': False}

## secondary_all_longs

Features (30): rs_score, rank_rs_all, log_adv, atr14_pct, vol_ratio, vol10_vs_50, ret_1d, ret_5d, ret_20d, ret_63d, dist_ma50, dist_ma150, dist_ma200, dist_52w_high, dist_52w_low, dist_level_pct, risk_at_close_pct, spy_above200, spy_ret_20d, sess_since_earn, sector_rs_median, sector_ret20_median, rs_minus_sector, breadth_ma50, breadth_new_high, breadth_chg5, is_breakout, is_retest, is_vcp, is_dbottom

Counts: {'signals': 25801, 'labelled': 25296, 'train': 14836, 'validation': 4792, 'dev': 19628, 'nonoverlap_train': 3973, 'nonoverlap_validation': 1273, 'trades_validation': 5406}

Validation grid (selection = mean daily IC):

| model | val_ic_mean | val_ic_days | val_return_pct | val_max_dd_pct | params |
|---|---|---|---|---|---|
| ridge | 0.0081 | 140 | -10.0278 | -13.3282 | {"alpha": 1.0} |
| ridge | 0.0079 | 140 | -5.6874 | -9.4925 | {"alpha": 10.0} |
| ridge | 0.0069 | 140 | -8.1172 | -11.4397 | {"alpha": 100.0} |
| hgb | 0.0009 | 140 | 1.7545 | -6.8787 | {"depth": 2, "iter": 100} |
| hgb | 0.0318 | 140 | 4.0236 | -9.0171 | {"depth": 2, "iter": 300} |
| hgb | 0.0344 | 140 | 8.9688 | -9.7351 | {"depth": 3, "iter": 100} |
| hgb | 0.0494 | 140 | 20.1771 | -5.3231 | {"depth": 3, "iter": 300} |

Chosen: hgb {'depth': 3, 'iter': 300}
Validation RS-first return 4.47 %, random median 12.49 %

Walk-forward:

| year | skipped | train_labels | scored | nonoverlap_scored | ic_mean | ic_days | rs_first_return_pct | model_return_pct | rs_first_dd | model_dd |
|---|---|---|---|---|---|---|---|---|---|---|
| 2023 | False | 607 | 5875 | 1588 | 0.0459 | 175 | 8.3836 | -1.7032 | -13.6251 | -10.8145 |
| 2024 | False | 5907 | 7427 | 1903 | 0.0515 | 215 | 25.3357 | 33.1223 | -18.8370 | -6.4014 |
| 2025 | False | 13814 | 6282 | 1711 | 0.0247 | 185 | 6.5169 | 17.7340 | -11.8737 | -14.1186 |

Pooled walk-forward IC: {'mean': 0.04119798750043812, 'days': 575, 'ci90': (0.025629960301435155, 0.05620563424335087), 'definition': 'daily ICs of the out-of-sample walk-forward years 2023-2025, each day once; bootstrap by day'}

Gate: {'eligible': False, 'g1_ic_positive_every_wf_year_and_validation': True, 'g2_pooled_ic_ge_0_03_and_ci_above_0': True, 'g3_portfolio_vs_rs_first_and_random': False, 'worst_wf_return_gap_pp': -10.086713422684067, 'passed': False}

## Historical window 2025-12-30 → 2026-10-14 (NOT independent, computed once after the gate)

```json
{
 "note": "NOT an independent test (window used for strategy choice); computed once after the gate decision; cannot change it",
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
  "return_pct": 13.969394623437204,
  "cagr_pct": 18.03763627520807,
  "max_dd_pct": -14.049585242403651,
  "trades": 62,
  "closed": 57,
  "expectancy_r": 0.2441879563029271,
  "expectancy_usd": 22.676625706765183,
  "win_rate": 38.59649122807017,
  "yearly_return_pct": {
   "2025": -0.47,
   "2026": 14.51
  }
 },
 "ic_mean": 0.053460122504451285,
 "ic_days": 135,
 "ic_ci90": [
  -0.004660899589620024,
  0.10967576038227751
 ],
 "random_return_pct": {
  "median": 7.611490049062885,
  "p10": -3.533121280417751,
  "p90": 22.66221385566347
 }
}
```
