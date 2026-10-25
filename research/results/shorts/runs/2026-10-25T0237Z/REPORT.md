# Short strategies, 10 years — results

**Verdict: no short setup confirmed: short strategies v1 rejected (no re-parametrisation)**

## Audit

```json
{
 "eligible_primary": {
  "rows": 463882,
  "stored": 65096,
  "recomputed": 65096,
  "mismatches": 0
 },
 "eligible_off": {
  "rows": 463882,
  "stored": 146905,
  "recomputed": 146905,
  "mismatches": 0
 },
 "eligible_pit_primary": {
  "rows": 463882,
  "stored": 60422,
  "recomputed": 60422,
  "mismatches": 0
 },
 "eligible_rs1500_primary": {
  "rows": 463882,
  "stored": 46344,
  "recomputed": 46344,
  "mismatches": 0
 },
 "primary_requires_spy_below_ma50": {
  "eligible": 65096,
  "with_spy_above50": 0
 },
 "off_includes_spy_above_ma50": 81809,
 "cost_recompute_max_abs_diff_r": {
  "gross_r": 3.552713678800501e-15,
  "net_r_base_gc": 0.0,
  "net_r_base_warm": 0.0,
  "net_r_base_hot": 0.0,
  "net_r_base_htb": 0.0,
  "net_r_wide_gc": 0.0,
  "net_r_wide_warm": 0.0,
  "net_r_wide_hot": 0.0,
  "net_r_wide_htb": 0.0,
  "net_r_stress_gc": 0.0,
  "net_r_stress_warm": 0.0,
  "net_r_stress_hot": 0.0,
  "net_r_stress_htb": 0.0
 },
 "dividends": {
  "closed_trades": 459348,
  "trades_paying_dividends": 72858
 },
 "nonoverlap_engine_vs_simulate_rule": {
  "rows": 37543,
  "engine": 13702,
  "reference": 13702,
  "mismatches": 0
 },
 "coverage": {
  "first_session": "2016-10-24",
  "last_session": "2026-10-23",
  "sessions_per_year": {
   "2016": 48,
   "2017": 251,
   "2018": 251,
   "2019": 252,
   "2020": 253,
   "2021": 252,
   "2022": 251,
   "2023": 250,
   "2024": 252,
   "2025": 250,
   "2026": 204
  }
 },
 "short_detections_per_year": {
  "breakdown": {
   "2017": 1851,
   "2018": 24168,
   "2019": 14320,
   "2020": 21763,
   "2021": 16809,
   "2022": 28489,
   "2023": 24056,
   "2024": 21386,
   "2025": 22640,
   "2026": 20055
  },
  "breakdown_retest": {
   "2017": 1003,
   "2018": 15315,
   "2019": 9672,
   "2020": 10398,
   "2021": 10472,
   "2022": 18569,
   "2023": 14786,
   "2024": 11104,
   "2025": 14419,
   "2026": 12864
  },
  "failed_breakout": {
   "2017": 2176,
   "2018": 13716,
   "2019": 16183,
   "2020": 18598,
   "2021": 17084,
   "2022": 16718,
   "2023": 17302,
   "2024": 18100,
   "2025": 15949,
   "2026": 13917
  }
 },
 "eligible_pit500_primary_per_year": {
  "breakdown": {
   "2018": 1544,
   "2019": 713,
   "2020": 1098,
   "2021": 397,
   "2022": 2333,
   "2023": 1469,
   "2024": 603,
   "2025": 714,
   "2026": 652
  },
  "breakdown_retest": {
   "2018": 1110,
   "2019": 574,
   "2020": 372,
   "2021": 210,
   "2022": 1631,
   "2023": 803,
   "2024": 287,
   "2025": 471,
   "2026": 423
  },
  "failed_breakout": {
   "2018": 146,
   "2019": 31,
   "2020": 142,
   "2021": 21,
   "2022": 201,
   "2023": 71,
   "2024": 73,
   "2025": 77,
   "2026": 108
  }
 },
 "groups": {
  "sp600": 158668,
  "sp500": 142395,
  "sp400": 109509,
  "sp600_removed": 40523,
  "sp400_removed": 9477,
  "sp500_removed": 3310
 }
}
```

## Decision (PIT S&P 500)

```json
{
 "primary": {
  "breakdown": {
   "development": {
    "trades": 1310,
    "win_rate": 35.49618320610687,
    "profit_factor": 0.784251068973381,
    "expectancy_r": -0.1052087655122994,
    "median_r": -0.321217546504696
   },
   "development_ci90": [
    -0.42931584103457415,
    0.32826719163942164
   ],
   "advances": false,
   "holdout": {
    "trades": 2112,
    "win_rate": 38.92045454545455,
    "profit_factor": 0.7000251839681094,
    "expectancy_r": -0.13644988566363897,
    "median_r": -0.267154439059075
   },
   "holdout_ci90": [
    -0.2576342873488863,
    -0.020175722362814466
   ],
   "H1": true,
   "H2": false,
   "H3": false,
   "H4": false,
   "holdout_bear_2022": {
    "trades": 677,
    "win_rate": 45.79025110782865,
    "profit_factor": 0.8967410621196156,
    "expectancy_r": -0.040652128529744806,
    "median_r": -0.08751006163963404
   },
   "holdout_wide_warm": {
    "trades": 2112,
    "win_rate": 37.452651515151516,
    "profit_factor": 0.6472808316241219,
    "expectancy_r": -0.16729110152021917,
    "median_r": -0.2858661831072751
   },
   "H5": false,
   "confirmed": false
  },
  "breakdown_retest": {
   "development": {
    "trades": 852,
    "win_rate": 30.399061032863848,
    "profit_factor": 0.9765724256621063,
    "expectancy_r": -0.015034077288103267,
    "median_r": -0.8738115858354043
   },
   "development_ci90": [
    -0.4939463727595663,
    0.6120877193198652
   ],
   "advances": false,
   "holdout": {
    "trades": 1386,
    "win_rate": 30.663780663780667,
    "profit_factor": 0.5790388054112457,
    "expectancy_r": -0.28051377797746274,
    "median_r": -1.0272392149278833
   },
   "holdout_ci90": [
    -0.4412333570836381,
    -0.12731741139828182
   ],
   "H1": true,
   "H2": false,
   "H3": false,
   "H4": false,
   "holdout_bear_2022": {
    "trades": 492,
    "win_rate": 30.691056910569102,
    "profit_factor": 0.6675452539002613,
    "expectancy_r": -0.2177645124270177,
    "median_r": -1.0271697933076172
   },
   "holdout_wide_warm": {
    "trades": 1386,
    "win_rate": 30.158730158730158,
    "profit_factor": 0.5315111121461016,
    "expectancy_r": -0.3284575862672003,
    "median_r": -1.0583156111341756
   },
   "H5": false,
   "confirmed": false
  },
  "failed_breakout": {
   "development": {
    "trades": 186,
    "win_rate": 38.70967741935484,
    "profit_factor": 0.6263142015976503,
    "expectancy_r": -0.18345430280652933,
    "median_r": -0.23375753628962254
   },
   "development_ci90": [
    -0.40937751559962976,
    0.06813488886351764
   ],
   "advances": false,
   "holdout": {
    "trades": 349,
    "win_rate": 36.10315186246418,
    "profit_factor": 0.5846864920306141,
    "expectancy_r": -0.22029245351976098,
    "median_r": -0.41382863543079224
   },
   "holdout_ci90": [
    -0.44315570689709743,
    0.02547487459745376
   ],
   "H1": true,
   "H2": false,
   "H3": false,
   "H4": false,
   "holdout_bear_2022": {
    "trades": 95,
    "win_rate": 36.84210526315789,
    "profit_factor": 0.6749073396058028,
    "expectancy_r": -0.1759323000860153,
    "median_r": -0.3377420602892842
   },
   "holdout_wide_warm": {
    "trades": 349,
    "win_rate": 35.24355300859599,
    "profit_factor": 0.5400832426083243,
    "expectancy_r": -0.2543690930603621,
    "median_r": -0.43806467200247656
   },
   "H5": false,
   "confirmed": false
  }
 },
 "off": {
  "breakdown": {
   "development": {
    "trades": 2641,
    "win_rate": 37.86444528587656,
    "profit_factor": 0.7059020723924304,
    "expectancy_r": -0.1377383134838734,
    "median_r": -0.26614488381882334
   },
   "development_ci90": [
    -0.3027379826589579,
    0.06026339033605331
   ],
   "advances": false,
   "holdout": {
    "trades": 3800,
    "win_rate": 42.28947368421053,
    "profit_factor": 0.7878441358036257,
    "expectancy_r": -0.08998356401586549,
    "median_r": -0.16457721218261473
   },
   "holdout_ci90": [
    -0.16918472565123674,
    -0.008799620451389517
   ],
   "H1": true,
   "H2": false,
   "H3": false,
   "H4": true,
   "holdout_bear_2022": {
    "trades": 728,
    "win_rate": 49.175824175824175,
    "profit_factor": 1.0566597836269422,
    "expectancy_r": 0.02061795682570187,
    "median_r": -0.013038902837494173
   },
   "holdout_wide_warm": {
    "trades": 3800,
    "win_rate": 40.921052631578945,
    "profit_factor": 0.7245552548244464,
    "expectancy_r": -0.12205583484275137,
    "median_r": -0.18874833062843044
   },
   "H5": false,
   "confirmed": false
  },
  "breakdown_retest": {
   "development": {
    "trades": 1606,
    "win_rate": 33.18804483188045,
    "profit_factor": 0.8192964309617634,
    "expectancy_r": -0.11213106823870511,
    "median_r": -0.7908516659499297
   },
   "development_ci90": [
    -0.36696282228813604,
    0.19419109293203704
   ],
   "advances": false,
   "holdout": {
    "trades": 2392,
    "win_rate": 32.56688963210702,
    "profit_factor": 0.6561961624377681,
    "expectancy_r": -0.22137491921168742,
    "median_r": -1.0254875892517812
   },
   "holdout_ci90": [
    -0.3215793613380794,
    -0.11486712005762997
   ],
   "H1": true,
   "H2": false,
   "H3": false,
   "H4": false,
   "holdout_bear_2022": {
    "trades": 510,
    "win_rate": 31.960784313725487,
    "profit_factor": 0.7629262311773816,
    "expectancy_r": -0.15285279638037727,
    "median_r": -1.0260085934811882
   },
   "holdout_wide_warm": {
    "trades": 2392,
    "win_rate": 31.8561872909699,
    "profit_factor": 0.599511768635904,
    "expectancy_r": -0.27201625407208013,
    "median_r": -1.0544167264087883
   },
   "H5": false,
   "confirmed": false
  },
  "failed_breakout": {
   "development": {
    "trades": 1495,
    "win_rate": 38.72909698996656,
    "profit_factor": 0.6877537304041847,
    "expectancy_r": -0.15921948527784555,
    "median_r": -0.3471314176864091
   },
   "development_ci90": [
    -0.3049934171847412,
    -0.005505212259502656
   ],
   "advances": false,
   "holdout": {
    "trades": 1709,
    "win_rate": 42.53949678174371,
    "profit_factor": 0.7832977010784283,
    "expectancy_r": -0.10908803817314432,
    "median_r": -0.2629949662272578
   },
   "holdout_ci90": [
    -0.22210400210053208,
    0.010209825408156903
   ],
   "H1": true,
   "H2": false,
   "H3": false,
   "H4": true,
   "holdout_bear_2022": {
    "trades": 228,
    "win_rate": 53.94736842105263,
    "profit_factor": 1.3953180982350253,
    "expectancy_r": 0.16835502319916684,
    "median_r": 0.157772623672767
   },
   "holdout_wide_warm": {
    "trades": 1709,
    "win_rate": 41.31070801638385,
    "profit_factor": 0.7177610593459371,
    "expectancy_r": -0.14898453097536488,
    "median_r": -0.29357478402129766
   },
   "H5": false,
   "confirmed": false
  }
 }
}
```

## Signal level, primary universe, non-overlapping

| universe | market | strategy | scenario | trades | win_rate | profit_factor | expectancy_r | median_r |
|---|---|---|---|---|---|---|---|---|
| pit500 | primary | breakdown | gross_r | 3422 | 40.30 | 0.84 | -0.07 | -0.23 |
| pit500 | primary | breakdown | net_r_base_gc | 3422 | 38.34 | 0.77 | -0.11 | -0.26 |
| pit500 | primary | breakdown | net_r_base_warm | 3422 | 37.58 | 0.73 | -0.13 | -0.28 |
| pit500 | primary | breakdown | net_r_base_hot | 3422 | 35.53 | 0.65 | -0.17 | -0.34 |
| pit500 | primary | breakdown | net_r_base_htb | 3422 | 29.66 | 0.47 | -0.30 | -0.48 |
| pit500 | primary | breakdown | net_r_wide_gc | 3422 | 37.23 | 0.71 | -0.14 | -0.29 |
| pit500 | primary | breakdown | net_r_wide_warm | 3422 | 36.24 | 0.68 | -0.16 | -0.31 |
| pit500 | primary | breakdown | net_r_wide_hot | 3422 | 34.42 | 0.61 | -0.20 | -0.37 |
| pit500 | primary | breakdown | net_r_wide_htb | 3422 | 28.90 | 0.44 | -0.34 | -0.51 |
| pit500 | primary | breakdown | net_r_stress_gc | 3422 | 35.48 | 0.63 | -0.19 | -0.34 |
| pit500 | primary | breakdown | net_r_stress_warm | 3422 | 34.69 | 0.60 | -0.21 | -0.36 |
| pit500 | primary | breakdown | net_r_stress_hot | 3422 | 32.38 | 0.54 | -0.25 | -0.41 |
| pit500 | primary | breakdown | net_r_stress_htb | 3422 | 27.41 | 0.39 | -0.39 | -0.56 |
| pit500 | primary | breakdown_retest | gross_r | 2238 | 32.22 | 0.83 | -0.10 | -1.00 |
| pit500 | primary | breakdown_retest | net_r_base_gc | 2238 | 31.28 | 0.76 | -0.16 | -1.02 |
| pit500 | primary | breakdown_retest | net_r_base_warm | 2238 | 30.56 | 0.73 | -0.18 | -1.02 |
| pit500 | primary | breakdown_retest | net_r_base_hot | 2238 | 29.49 | 0.66 | -0.24 | -1.03 |
| pit500 | primary | breakdown_retest | net_r_base_htb | 2238 | 24.84 | 0.50 | -0.40 | -1.06 |
| pit500 | primary | breakdown_retest | net_r_wide_gc | 2238 | 30.43 | 0.70 | -0.21 | -1.04 |
| pit500 | primary | breakdown_retest | net_r_wide_warm | 2238 | 30.03 | 0.67 | -0.23 | -1.05 |
| pit500 | primary | breakdown_retest | net_r_wide_hot | 2238 | 28.51 | 0.61 | -0.28 | -1.07 |
| pit500 | primary | breakdown_retest | net_r_wide_htb | 2238 | 24.17 | 0.46 | -0.44 | -1.10 |
| pit500 | primary | breakdown_retest | net_r_stress_gc | 2238 | 29.45 | 0.61 | -0.29 | -1.09 |
| pit500 | primary | breakdown_retest | net_r_stress_warm | 2238 | 28.60 | 0.59 | -0.31 | -1.09 |
| pit500 | primary | breakdown_retest | net_r_stress_hot | 2238 | 27.08 | 0.53 | -0.37 | -1.11 |
| pit500 | primary | breakdown_retest | net_r_stress_htb | 2238 | 23.32 | 0.41 | -0.53 | -1.17 |
| pit500 | primary | failed_breakout | gross_r | 535 | 38.88 | 0.70 | -0.15 | -0.26 |
| pit500 | primary | failed_breakout | net_r_base_gc | 535 | 37.76 | 0.63 | -0.19 | -0.32 |
| pit500 | primary | failed_breakout | net_r_base_warm | 535 | 37.01 | 0.60 | -0.21 | -0.34 |
| pit500 | primary | failed_breakout | net_r_base_hot | 535 | 34.77 | 0.53 | -0.25 | -0.38 |
| pit500 | primary | failed_breakout | net_r_base_htb | 535 | 30.28 | 0.38 | -0.38 | -0.53 |
| pit500 | primary | failed_breakout | net_r_wide_gc | 535 | 37.01 | 0.58 | -0.22 | -0.34 |
| pit500 | primary | failed_breakout | net_r_wide_warm | 535 | 36.07 | 0.55 | -0.24 | -0.36 |
| pit500 | primary | failed_breakout | net_r_wide_hot | 535 | 34.39 | 0.49 | -0.29 | -0.41 |
| pit500 | primary | failed_breakout | net_r_wide_htb | 535 | 28.41 | 0.35 | -0.42 | -0.57 |
| pit500 | primary | failed_breakout | net_r_stress_gc | 535 | 34.77 | 0.51 | -0.28 | -0.39 |
| pit500 | primary | failed_breakout | net_r_stress_warm | 535 | 34.58 | 0.48 | -0.30 | -0.41 |
| pit500 | primary | failed_breakout | net_r_stress_hot | 535 | 32.34 | 0.43 | -0.34 | -0.45 |
| pit500 | primary | failed_breakout | net_r_stress_htb | 535 | 26.54 | 0.31 | -0.47 | -0.61 |
| pit500 | off | breakdown | gross_r | 6441 | 43.29 | 0.88 | -0.05 | -0.15 |
| pit500 | off | breakdown | net_r_base_gc | 6441 | 41.45 | 0.79 | -0.09 | -0.19 |
| pit500 | off | breakdown | net_r_base_warm | 6441 | 40.44 | 0.75 | -0.11 | -0.20 |
| pit500 | off | breakdown | net_r_base_hot | 6441 | 38.21 | 0.66 | -0.16 | -0.25 |
| pit500 | off | breakdown | net_r_base_htb | 6441 | 31.42 | 0.45 | -0.30 | -0.41 |
| pit500 | off | breakdown | net_r_wide_gc | 6441 | 40.16 | 0.73 | -0.12 | -0.21 |
| pit500 | off | breakdown | net_r_wide_warm | 6441 | 39.09 | 0.69 | -0.14 | -0.23 |
| pit500 | off | breakdown | net_r_wide_hot | 6441 | 36.95 | 0.61 | -0.19 | -0.28 |
| pit500 | off | breakdown | net_r_wide_htb | 6441 | 30.35 | 0.42 | -0.34 | -0.44 |
| pit500 | off | breakdown | net_r_stress_gc | 6441 | 38.18 | 0.63 | -0.18 | -0.26 |
| pit500 | off | breakdown | net_r_stress_warm | 6441 | 37.26 | 0.60 | -0.20 | -0.27 |
| pit500 | off | breakdown | net_r_stress_hot | 6441 | 34.81 | 0.53 | -0.25 | -0.33 |
| pit500 | off | breakdown | net_r_stress_htb | 6441 | 28.57 | 0.37 | -0.39 | -0.49 |
| pit500 | off | breakdown_retest | gross_r | 3998 | 35.04 | 0.84 | -0.09 | -1.00 |
| pit500 | off | breakdown_retest | net_r_base_gc | 3998 | 33.49 | 0.75 | -0.15 | -1.01 |
| pit500 | off | breakdown_retest | net_r_base_warm | 3998 | 32.82 | 0.72 | -0.18 | -1.02 |
| pit500 | off | breakdown_retest | net_r_base_hot | 3998 | 31.14 | 0.64 | -0.24 | -1.03 |
| pit500 | off | breakdown_retest | net_r_base_htb | 3998 | 25.89 | 0.46 | -0.42 | -1.05 |
| pit500 | off | breakdown_retest | net_r_wide_gc | 3998 | 32.57 | 0.69 | -0.21 | -1.04 |
| pit500 | off | breakdown_retest | net_r_wide_warm | 3998 | 31.97 | 0.66 | -0.23 | -1.04 |
| pit500 | off | breakdown_retest | net_r_wide_hot | 3998 | 29.96 | 0.59 | -0.29 | -1.05 |
| pit500 | off | breakdown_retest | net_r_wide_htb | 3998 | 25.06 | 0.42 | -0.47 | -1.10 |
| pit500 | off | breakdown_retest | net_r_stress_gc | 3998 | 31.17 | 0.59 | -0.29 | -1.07 |
| pit500 | off | breakdown_retest | net_r_stress_warm | 3998 | 30.12 | 0.57 | -0.32 | -1.08 |
| pit500 | off | breakdown_retest | net_r_stress_hot | 3998 | 28.41 | 0.51 | -0.38 | -1.10 |
| pit500 | off | breakdown_retest | net_r_stress_htb | 3998 | 23.76 | 0.36 | -0.56 | -1.16 |
| pit500 | off | failed_breakout | gross_r | 3202 | 43.04 | 0.87 | -0.06 | -0.21 |
| pit500 | off | failed_breakout | net_r_base_gc | 3202 | 41.51 | 0.78 | -0.11 | -0.27 |
| pit500 | off | failed_breakout | net_r_base_warm | 3202 | 40.72 | 0.74 | -0.13 | -0.29 |
| pit500 | off | failed_breakout | net_r_base_hot | 3202 | 38.38 | 0.65 | -0.19 | -0.37 |
| pit500 | off | failed_breakout | net_r_base_htb | 3202 | 32.70 | 0.44 | -0.35 | -0.57 |
| pit500 | off | failed_breakout | net_r_wide_gc | 3202 | 40.57 | 0.71 | -0.15 | -0.30 |
| pit500 | off | failed_breakout | net_r_wide_warm | 3202 | 39.60 | 0.67 | -0.17 | -0.33 |
| pit500 | off | failed_breakout | net_r_wide_hot | 3202 | 37.51 | 0.59 | -0.23 | -0.41 |
| pit500 | off | failed_breakout | net_r_wide_htb | 3202 | 31.29 | 0.40 | -0.39 | -0.61 |
| pit500 | off | failed_breakout | net_r_stress_gc | 3202 | 38.29 | 0.61 | -0.22 | -0.37 |
| pit500 | off | failed_breakout | net_r_stress_warm | 3202 | 37.63 | 0.58 | -0.24 | -0.40 |
| pit500 | off | failed_breakout | net_r_stress_hot | 3202 | 35.45 | 0.51 | -0.30 | -0.47 |
| pit500 | off | failed_breakout | net_r_stress_htb | 3202 | 29.54 | 0.35 | -0.46 | -0.67 |


## Periods (PIT S&P 500, SPY < MA50, primary net)

| strategy | period | gross_trades | gross_win_rate | gross_profit_factor | gross_expectancy_r | gross_median_r | net_trades | net_win_rate | net_profit_factor | net_expectancy_r | net_median_r |
|---|---|---|---|---|---|---|---|---|---|---|---|
| breakdown | covid_crash | 137 | 85.40 | 20.88 | 2.13 | 2.04 | 137 | 85.40 | 20.02 | 2.08 | 2.00 |
| breakdown | covid_recovery | 156 | 12.18 | 0.07 | -0.79 | -1.00 | 156 | 9.62 | 0.06 | -0.84 | -1.03 |
| breakdown | bear_2022 | 677 | 48.30 | 1.00 | -0.00 | -0.06 | 677 | 45.64 | 0.88 | -0.05 | -0.09 |
| breakdown | rebound_2022 | 276 | 28.99 | 0.47 | -0.29 | -0.53 | 276 | 27.90 | 0.40 | -0.34 | -0.58 |
| breakdown | other_2023_2026 | 1159 | 39.95 | 0.80 | -0.09 | -0.22 | 1159 | 37.53 | 0.69 | -0.14 | -0.28 |
| breakdown | 2018 | 519 | 40.85 | 0.68 | -0.12 | -0.14 | 519 | 36.80 | 0.56 | -0.18 | -0.21 |
| breakdown | 2019 | 240 | 42.92 | 0.62 | -0.16 | -0.21 | 240 | 37.50 | 0.50 | -0.23 | -0.30 |
| breakdown | 2020 | 293 | 46.42 | 2.15 | 0.58 | -0.15 | 293 | 45.05 | 2.01 | 0.53 | -0.24 |
| breakdown | 2021 | 258 | 22.48 | 0.16 | -0.50 | -0.77 | 258 | 20.16 | 0.12 | -0.56 | -0.84 |
| breakdown | 2022 | 789 | 43.09 | 0.79 | -0.09 | -0.18 | 789 | 40.68 | 0.70 | -0.13 | -0.22 |
| breakdown | 2023 | 454 | 46.92 | 1.27 | 0.10 | -0.07 | 454 | 44.71 | 1.06 | 0.03 | -0.14 |
| breakdown | 2024 | 303 | 23.43 | 0.27 | -0.41 | -0.61 | 303 | 21.45 | 0.23 | -0.47 | -0.66 |
| breakdown | 2025 | 265 | 40.00 | 0.73 | -0.11 | -0.24 | 265 | 37.36 | 0.64 | -0.15 | -0.27 |
| breakdown | 2026 | 301 | 46.51 | 1.00 | 0.00 | -0.10 | 301 | 44.19 | 0.89 | -0.05 | -0.14 |
| breakdown_retest | covid_crash | 98 | 78.57 | 22.64 | 3.42 | 3.44 | 98 | 78.57 | 21.34 | 3.33 | 3.31 |
| breakdown_retest | covid_recovery | 76 | 23.68 | 0.27 | -0.64 | -1.00 | 76 | 22.37 | 0.24 | -0.71 | -1.03 |
| breakdown_retest | bear_2022 | 492 | 32.32 | 0.75 | -0.15 | -1.00 | 492 | 30.69 | 0.67 | -0.22 | -1.03 |
| breakdown_retest | rebound_2022 | 202 | 19.80 | 0.22 | -0.59 | -1.00 | 202 | 17.33 | 0.19 | -0.66 | -1.04 |
| breakdown_retest | other_2023_2026 | 692 | 36.42 | 0.76 | -0.14 | -1.00 | 692 | 34.54 | 0.66 | -0.21 | -1.02 |
| breakdown_retest | 2018 | 383 | 30.29 | 0.63 | -0.21 | -0.64 | 383 | 28.72 | 0.53 | -0.30 | -0.74 |
| breakdown_retest | 2019 | 185 | 22.70 | 0.33 | -0.45 | -1.00 | 185 | 21.08 | 0.26 | -0.54 | -1.04 |
| breakdown_retest | 2020 | 174 | 54.60 | 4.46 | 1.64 | 0.60 | 174 | 54.02 | 4.16 | 1.57 | 0.55 |
| breakdown_retest | 2021 | 110 | 15.45 | 0.17 | -0.59 | -1.00 | 110 | 14.55 | 0.15 | -0.65 | -1.03 |
| breakdown_retest | 2022 | 586 | 28.16 | 0.60 | -0.27 | -1.00 | 586 | 26.62 | 0.53 | -0.34 | -1.03 |
| breakdown_retest | 2023 | 283 | 42.76 | 0.99 | -0.00 | -0.36 | 283 | 39.58 | 0.85 | -0.08 | -0.44 |
| breakdown_retest | 2024 | 144 | 24.31 | 0.39 | -0.44 | -1.00 | 144 | 22.92 | 0.33 | -0.51 | -1.04 |
| breakdown_retest | 2025 | 193 | 29.02 | 0.64 | -0.24 | -1.00 | 193 | 28.50 | 0.57 | -0.30 | -1.02 |
| breakdown_retest | 2026 | 180 | 41.11 | 0.76 | -0.14 | -0.56 | 180 | 38.33 | 0.66 | -0.21 | -0.65 |
| failed_breakout | covid_crash | 5 | 100.00 |  | 2.03 | 2.23 | 5 | 100.00 |  | 1.98 | 2.19 |
| failed_breakout | covid_recovery | 58 | 25.86 | 0.29 | -0.46 | -1.00 | 58 | 25.86 | 0.25 | -0.51 | -1.02 |
| failed_breakout | bear_2022 | 95 | 36.84 | 0.76 | -0.13 | -0.27 | 95 | 36.84 | 0.67 | -0.18 | -0.34 |
| failed_breakout | rebound_2022 | 57 | 14.04 | 0.07 | -0.66 | -1.00 | 57 | 14.04 | 0.06 | -0.70 | -1.02 |
| failed_breakout | other_2023_2026 | 197 | 44.67 | 0.92 | -0.04 | -0.13 | 197 | 42.13 | 0.78 | -0.10 | -0.16 |
| failed_breakout | 2018 | 81 | 50.62 | 1.21 | 0.07 | 0.01 | 81 | 44.44 | 0.98 | -0.01 | -0.12 |
| failed_breakout | 2019 | 22 | 27.27 | 0.35 | -0.42 | -1.00 | 22 | 27.27 | 0.30 | -0.49 | -1.03 |
| failed_breakout | 2020 | 63 | 31.75 | 0.56 | -0.27 | -1.00 | 63 | 31.75 | 0.50 | -0.32 | -1.01 |
| failed_breakout | 2021 | 20 | 50.00 | 0.80 | -0.07 | 0.04 | 20 | 50.00 | 0.62 | -0.14 | -0.00 |
| failed_breakout | 2022 | 126 | 28.57 | 0.52 | -0.27 | -0.58 | 126 | 28.57 | 0.46 | -0.32 | -0.61 |
| failed_breakout | 2023 | 50 | 46.00 | 0.76 | -0.11 | -0.41 | 50 | 42.00 | 0.64 | -0.18 | -0.45 |
| failed_breakout | 2024 | 53 | 35.85 | 0.41 | -0.27 | -0.26 | 53 | 33.96 | 0.34 | -0.32 | -0.39 |
| failed_breakout | 2025 | 46 | 45.65 | 0.89 | -0.05 | -0.06 | 46 | 43.48 | 0.72 | -0.13 | -0.11 |
| failed_breakout | 2026 | 74 | 43.24 | 0.99 | -0.01 | -0.27 | 74 | 41.89 | 0.88 | -0.06 | -0.30 |


## Portfolio

```json
{
 "pit500_primary": {
  "breakdown": {
   "full": {
    "first": "2017-11-03",
    "last": "2026-10-23",
    "final_equity": 7382.4452121461945,
    "return_pct": -26.17554787853805,
    "cagr_pct": -3.3269787472193446,
    "max_dd_pct": -38.34742235455744,
    "yearly_return_pct": {
     "2017": 0.0,
     "2018": -3.26,
     "2019": -0.18,
     "2020": 3.15,
     "2021": -11.52,
     "2022": -5.32,
     "2023": 2.52,
     "2024": -11.72,
     "2025": 8.77,
     "2026": -10.13
    },
    "trades": 273,
    "exposure_pct": 50.22182786157941,
    "win_rate": 37.362637362637365,
    "expectancy_r": -0.09300741210635237,
    "profit_factor": 0.7740939161015069,
    "borrow_paid": 383.0784604925914,
    "dividends_paid": 307.5627,
    "open_at_end": 5,
    "skipped": {
     "daily_entries": 794,
     "positions": 7898,
     "ticker_open": 533,
     "size": 2
    },
    "candidates": 9505,
    "periods": {
     "covid_crash": 22.28,
     "covid_recovery": -15.64,
     "bear_2022": -2.48,
     "rebound_2022": -10.06,
     "other_2023_2026": -4.5
    }
   },
   "holdout": {
    "first": "2022-01-03",
    "last": "2026-10-23",
    "final_equity": 8624.389101810215,
    "return_pct": -13.756108981897853,
    "cagr_pct": -3.0347372932012284,
    "max_dd_pct": -16.26397120512586,
    "yearly_return_pct": {
     "2022": -3.52,
     "2023": 2.93,
     "2024": -11.5,
     "2025": 9.68,
     "2026": -10.54
    },
    "trades": 172,
    "exposure_pct": 58.16072908036454,
    "win_rate": 39.53488372093023,
    "expectancy_r": -0.07830968058318338,
    "profit_factor": 0.8247324629405207,
    "borrow_paid": 245.5042885432701,
    "dividends_paid": 134.157647,
    "open_at_end": 5,
    "skipped": {
     "size": 2,
     "daily_entries": 374,
     "ticker_open": 322,
     "positions": 4878
    },
    "candidates": 5753,
    "periods": {
     "bear_2022": -0.41,
     "rebound_2022": -9.94,
     "other_2023_2026": -3.85
    }
   }
  },
  "breakdown_retest": {
   "full": {
    "first": "2017-11-03",
    "last": "2026-10-23",
    "final_equity": 7452.006491598599,
    "return_pct": -25.479935084014016,
    "cagr_pct": -3.2258422429292555,
    "max_dd_pct": -44.09272842961357,
    "yearly_return_pct": {
     "2017": 0.0,
     "2018": 4.28,
     "2019": -1.45,
     "2020": 3.4,
     "2021": -8.52,
     "2022": -16.25,
     "2023": -3.07,
     "2024": 0.36,
     "2025": -2.51,
     "2026": -3.49
    },
    "trades": 288,
    "exposure_pct": 46.983141082519964,
    "win_rate": 38.19444444444444,
    "expectancy_r": -0.11486641614008031,
    "profit_factor": 0.8160148552586916,
    "borrow_paid": 529.2065080575943,
    "dividends_paid": 389.24840700000004,
    "open_at_end": 5,
    "skipped": {
     "daily_entries": 132,
     "positions": 4951,
     "ticker_open": 482,
     "size": 1
    },
    "candidates": 5859,
    "periods": {
     "covid_crash": 17.72,
     "covid_recovery": -12.17,
     "bear_2022": -0.09,
     "rebound_2022": -21.08,
     "other_2023_2026": -2.77
    }
   },
   "holdout": {
    "first": "2022-01-03",
    "last": "2026-10-23",
    "final_equity": 7592.868601980359,
    "return_pct": -24.071313980196408,
    "cagr_pct": -5.57305847764783,
    "max_dd_pct": -35.66900039803015,
    "yearly_return_pct": {
     "2022": -16.13,
     "2023": -3.61,
     "2024": 0.17,
     "2025": -2.7,
     "2026": -3.64
    },
    "trades": 179,
    "exposure_pct": 53.68682684341343,
    "win_rate": 37.43016759776536,
    "expectancy_r": -0.15559575233129863,
    "profit_factor": 0.7321091230514218,
    "borrow_paid": 290.8060274982191,
    "dividends_paid": 180.751426,
    "open_at_end": 5,
    "skipped": {
     "ticker_open": 290,
     "positions": 3063,
     "daily_entries": 60,
     "size": 1
    },
    "candidates": 3598,
    "periods": {
     "bear_2022": -0.03,
     "rebound_2022": -21.21,
     "other_2023_2026": -3.6
    }
   }
  },
  "failed_breakout": {
   "full": {
    "first": "2017-11-03",
    "last": "2026-10-23",
    "final_equity": 7860.789833271945,
    "return_pct": -21.39210166728055,
    "cagr_pct": -2.647917652516696,
    "max_dd_pct": -27.709336844680386,
    "yearly_return_pct": {
     "2017": 0.0,
     "2018": 4.45,
     "2019": -9.64,
     "2020": 2.49,
     "2021": -4.56,
     "2022": -2.82,
     "2023": 4.57,
     "2024": -3.88,
     "2025": -5.65,
     "2026": -7.59
    },
    "trades": 208,
    "exposure_pct": 45.87400177462289,
    "win_rate": 40.38461538461539,
    "expectancy_r": -0.11521648346379457,
    "profit_factor": 0.7557555941220019,
    "borrow_paid": 352.3262262610606,
    "dividends_paid": 355.01148,
    "open_at_end": 2,
    "skipped": {
     "ticker_open": 127,
     "positions": 448,
     "daily_entries": 81
    },
    "candidates": 866,
    "periods": {
     "covid_crash": 12.24,
     "covid_recovery": -8.69,
     "bear_2022": 6.14,
     "rebound_2022": -10.04,
     "other_2023_2026": -10.82
    }
   },
   "holdout": {
    "first": "2022-01-03",
    "last": "2026-10-23",
    "final_equity": 8468.071392248505,
    "return_pct": -15.319286077514949,
    "cagr_pct": -3.403371535082389,
    "max_dd_pct": -27.591556949631713,
    "yearly_return_pct": {
     "2022": -3.22,
     "2023": 4.81,
     "2024": -4.23,
     "2025": -5.81,
     "2026": -7.44
    },
    "trades": 124,
    "exposure_pct": 50.538525269262635,
    "win_rate": 38.70967741935484,
    "expectancy_r": -0.131737626176743,
    "profit_factor": 0.7220342482453304,
    "borrow_paid": 206.68995048303472,
    "dividends_paid": 149.025,
    "open_at_end": 2,
    "skipped": {
     "daily_entries": 53,
     "ticker_open": 69,
     "positions": 278
    },
    "candidates": 526,
    "periods": {
     "bear_2022": 5.46,
     "rebound_2022": -9.81,
     "other_2023_2026": -10.97
    }
   }
  }
 },
 "pit500_off": {
  "breakdown": {
   "full": {
    "first": "2017-11-03",
    "last": "2026-10-23",
    "final_equity": 5958.152137924408,
    "return_pct": -40.41847862075593,
    "cagr_pct": -5.609868821692898,
    "max_dd_pct": -47.27169725612329,
    "yearly_return_pct": {
     "2017": -5.31,
     "2018": 1.93,
     "2019": -12.8,
     "2020": -0.71,
     "2021": -22.36,
     "2022": -2.05,
     "2023": -4.07,
     "2024": 1.31,
     "2025": -0.83,
     "2026": -2.73
    },
    "trades": 611,
    "exposure_pct": 99.33451641526176,
    "win_rate": 40.261865793780686,
    "expectancy_r": -0.0834420964193193,
    "profit_factor": 0.7778421605096697,
    "borrow_paid": 838.0335349689117,
    "dividends_paid": 679.269779,
    "open_at_end": 5,
    "skipped": {
     "daily_entries": 3,
     "ticker_open": 1359,
     "positions": 17823,
     "size": 16
    },
    "candidates": 19817,
    "periods": {
     "covid_crash": 30.54,
     "covid_recovery": -20.31,
     "bear_2022": 0.38,
     "rebound_2022": -11.61,
     "other_2023_2026": 3.49
    }
   },
   "holdout": {
    "first": "2022-01-03",
    "last": "2026-10-23",
    "final_equity": 9864.959377630516,
    "return_pct": -1.3504062236948444,
    "cagr_pct": -0.2827218822788913,
    "max_dd_pct": -13.09841698058235,
    "yearly_return_pct": {
     "2022": 1.3,
     "2023": -4.08,
     "2024": 0.57,
     "2025": 1.94,
     "2026": -0.97
    },
    "trades": 339,
    "exposure_pct": 99.83429991714996,
    "win_rate": 46.017699115044245,
    "expectancy_r": -0.006430690524859854,
    "profit_factor": 0.9715548717574156,
    "borrow_paid": 595.1414087060118,
    "dividends_paid": 411.611594,
    "open_at_end": 5,
    "skipped": {
     "ticker_open": 797,
     "daily_entries": 8,
     "positions": 10736,
     "size": 5
    },
    "candidates": 11890,
    "periods": {
     "bear_2022": 1.96,
     "rebound_2022": -10.76,
     "other_2023_2026": 8.42
    }
   }
  },
  "breakdown_retest": {
   "full": {
    "first": "2017-11-03",
    "last": "2026-10-23",
    "final_equity": 3040.7257925469476,
    "return_pct": -69.59274207453052,
    "cagr_pct": -12.429918887486647,
    "max_dd_pct": -71.52886639524185,
    "yearly_return_pct": {
     "2017": -3.88,
     "2018": -6.14,
     "2019": -26.63,
     "2020": -18.35,
     "2021": -13.49,
     "2022": -10.05,
     "2023": -5.61,
     "2024": -3.95,
     "2025": -14.58,
     "2026": -6.65
    },
    "trades": 700,
    "exposure_pct": 97.87045252883763,
    "win_rate": 33.85714285714286,
    "expectancy_r": -0.17616870625350195,
    "profit_factor": 0.6675906608426159,
    "borrow_paid": 860.9261334812477,
    "dividends_paid": 726.1229519999999,
    "open_at_end": 5,
    "skipped": {
     "daily_entries": 17,
     "ticker_open": 1346,
     "positions": 9678,
     "size": 19
    },
    "candidates": 11765,
    "periods": {
     "covid_crash": 25.58,
     "covid_recovery": -32.78,
     "bear_2022": -7.89,
     "rebound_2022": -15.77,
     "other_2023_2026": -16.18
    }
   },
   "holdout": {
    "first": "2022-01-03",
    "last": "2026-10-23",
    "final_equity": 7129.826831346609,
    "return_pct": -28.701731686533915,
    "cagr_pct": -6.8022526879922935,
    "max_dd_pct": -36.439618535754235,
    "yearly_return_pct": {
     "2022": -10.23,
     "2023": -4.91,
     "2024": 0.42,
     "2025": -9.99,
     "2026": -7.58
    },
    "trades": 383,
    "exposure_pct": 99.00579950289975,
    "win_rate": 36.55352480417754,
    "expectancy_r": -0.0827138971022161,
    "profit_factor": 0.8288192928583097,
    "borrow_paid": 723.5173817623086,
    "dividends_paid": 459.411101,
    "open_at_end": 5,
    "skipped": {
     "ticker_open": 776,
     "positions": 5967,
     "daily_entries": 3,
     "size": 3
    },
    "candidates": 7137,
    "periods": {
     "bear_2022": -7.18,
     "rebound_2022": -17.44,
     "other_2023_2026": -6.96
    }
   }
  },
  "failed_breakout": {
   "full": {
    "first": "2017-11-03",
    "last": "2026-10-23",
    "final_equity": 4115.704325892639,
    "return_pct": -58.842956741073614,
    "cagr_pct": -9.423955848555288,
    "max_dd_pct": -60.42740318686028,
    "yearly_return_pct": {
     "2017": -6.21,
     "2018": -4.56,
     "2019": -15.1,
     "2020": -13.34,
     "2021": -11.08,
     "2022": -8.14,
     "2023": -2.93,
     "2024": -12.29,
     "2025": -5.18,
     "2026": -5.23
    },
    "trades": 598,
    "exposure_pct": 98.40283939662822,
    "win_rate": 38.62876254180602,
    "expectancy_r": -0.15289266810838162,
    "profit_factor": 0.6703572876724799,
    "borrow_paid": 785.89784135761,
    "dividends_paid": 923.91671,
    "open_at_end": 3,
    "skipped": {
     "positions": 4750,
     "ticker_open": 488,
     "daily_entries": 14,
     "size": 30
    },
    "candidates": 5883,
    "periods": {
     "covid_crash": 11.32,
     "covid_recovery": -19.79,
     "bear_2022": 1.54,
     "rebound_2022": -12.64,
     "other_2023_2026": -20.78
    }
   },
   "holdout": {
    "first": "2022-01-03",
    "last": "2026-10-23",
    "final_equity": 7454.0949446474115,
    "return_pct": -25.459050553525884,
    "cagr_pct": -5.935070676836984,
    "max_dd_pct": -38.56503336839799,
    "yearly_return_pct": {
     "2022": 0.1,
     "2023": -2.37,
     "2024": -12.83,
     "2025": -5.92,
     "2026": -6.99
    },
    "trades": 319,
    "exposure_pct": 99.08864954432477,
    "win_rate": 40.43887147335423,
    "expectancy_r": -0.09779688548009942,
    "profit_factor": 0.80717491317106,
    "borrow_paid": 614.3466908469788,
    "dividends_paid": 449.287,
    "open_at_end": 4,
    "skipped": {
     "daily_entries": 13,
     "ticker_open": 268,
     "positions": 2485,
     "size": 8
    },
    "candidates": 3097,
    "periods": {
     "bear_2022": 8.46,
     "rebound_2022": -10.81,
     "other_2023_2026": -22.95
    }
   }
  }
 },
 "sp1500_primary": {
  "breakdown": {
   "full": {
    "first": "2017-11-03",
    "last": "2026-10-23",
    "final_equity": 6229.00295511583,
    "return_pct": -37.7099704488417,
    "cagr_pct": -5.140862190998741,
    "max_dd_pct": -39.05142070269256,
    "yearly_return_pct": {
     "2017": 0.0,
     "2018": -6.81,
     "2019": -7.39,
     "2020": 1.34,
     "2021": -13.83,
     "2022": -3.81,
     "2023": -1.24,
     "2024": -3.49,
     "2025": -3.55,
     "2026": -6.54
    },
    "trades": 277,
    "exposure_pct": 50.08873114463177,
    "win_rate": 37.545126353790614,
    "expectancy_r": -0.16851648642294814,
    "profit_factor": 0.6465546848933708,
    "borrow_paid": 270.298524672874,
    "dividends_paid": 174.06847599999998,
    "open_at_end": 5,
    "skipped": {
     "daily_entries": 2050,
     "positions": 20675,
     "ticker_open": 479,
     "size": 1
    },
    "candidates": 23487,
    "periods": {
     "covid_crash": 13.2,
     "covid_recovery": -10.48,
     "bear_2022": 3.86,
     "rebound_2022": -10.44,
     "other_2023_2026": -11.14
    }
   },
   "holdout": {
    "first": "2022-01-03",
    "last": "2026-10-23",
    "final_equity": 8196.574286477038,
    "return_pct": -18.034257135229616,
    "cagr_pct": -4.056633651027841,
    "max_dd_pct": -30.512455975747564,
    "yearly_return_pct": {
     "2022": -3.25,
     "2023": -1.47,
     "2024": -3.75,
     "2025": -3.42,
     "2026": -7.5
    },
    "trades": 171,
    "exposure_pct": 56.420878210439106,
    "win_rate": 41.52046783625731,
    "expectancy_r": -0.10956403601297073,
    "profit_factor": 0.7614262508615441,
    "borrow_paid": 196.47878583577562,
    "dividends_paid": 115.770506,
    "open_at_end": 5,
    "skipped": {
     "daily_entries": 1018,
     "positions": 12833,
     "ticker_open": 303,
     "size": 1
    },
    "candidates": 14331,
    "periods": {
     "bear_2022": 4.48,
     "rebound_2022": -10.66,
     "other_2023_2026": -12.19
    }
   }
  },
  "breakdown_retest": {
   "full": {
    "first": "2017-11-03",
    "last": "2026-10-23",
    "final_equity": 5772.13631395222,
    "return_pct": -42.2786368604778,
    "cagr_pct": -5.943074844684359,
    "max_dd_pct": -49.02193846030804,
    "yearly_return_pct": {
     "2017": 0.0,
     "2018": 4.55,
     "2019": -13.67,
     "2020": -0.05,
     "2021": -12.14,
     "2022": -6.28,
     "2023": -5.26,
     "2024": -5.34,
     "2025": 0.73,
     "2026": -13.98
    },
    "trades": 308,
    "exposure_pct": 48.1810115350488,
    "win_rate": 35.064935064935064,
    "expectancy_r": -0.1764444688721042,
    "profit_factor": 0.7319117561253505,
    "borrow_paid": 442.6363049809181,
    "dividends_paid": 230.141168,
    "open_at_end": 5,
    "skipped": {
     "daily_entries": 610,
     "ticker_open": 498,
     "positions": 13444
    },
    "candidates": 14865,
    "periods": {
     "covid_crash": 24.25,
     "covid_recovery": -19.56,
     "bear_2022": 7.01,
     "rebound_2022": -14.91,
     "other_2023_2026": -20.02
    }
   },
   "holdout": {
    "first": "2022-01-03",
    "last": "2026-10-23",
    "final_equity": 6908.055128394613,
    "return_pct": -30.919448716053864,
    "cagr_pct": -7.413488318671768,
    "max_dd_pct": -38.27577946480572,
    "yearly_return_pct": {
     "2022": -11.17,
     "2023": -5.2,
     "2024": -5.46,
     "2025": 0.75,
     "2026": -13.86
    },
    "trades": 196,
    "exposure_pct": 55.343827671913836,
    "win_rate": 36.734693877551024,
    "expectancy_r": -0.1784977004661378,
    "profit_factor": 0.7184708242137682,
    "borrow_paid": 287.1583660835108,
    "dividends_paid": 155.16199999999998,
    "open_at_end": 5,
    "skipped": {
     "daily_entries": 342,
     "positions": 8453,
     "ticker_open": 311
    },
    "candidates": 9307,
    "periods": {
     "bear_2022": 1.69,
     "rebound_2022": -15.19,
     "other_2023_2026": -19.9
    }
   }
  },
  "failed_breakout": {
   "full": {
    "first": "2017-11-03",
    "last": "2026-10-23",
    "final_equity": 6769.597715342852,
    "return_pct": -32.30402284657148,
    "cagr_pct": -4.256565952532821,
    "max_dd_pct": -39.84471389539339,
    "yearly_return_pct": {
     "2017": 0.0,
     "2018": 0.28,
     "2019": -13.6,
     "2020": -9.89,
     "2021": -10.27,
     "2022": -6.81,
     "2023": 7.04,
     "2024": -0.51,
     "2025": -6.26,
     "2026": 3.87
    },
    "trades": 244,
    "exposure_pct": 48.58030168589175,
    "win_rate": 38.52459016393443,
    "expectancy_r": -0.14974627518352385,
    "profit_factor": 0.6649179810351288,
    "borrow_paid": 291.3172224653584,
    "dividends_paid": 211.721,
    "open_at_end": 5,
    "skipped": {
     "positions": 1270,
     "ticker_open": 149,
     "daily_entries": 189,
     "size": 3
    },
    "candidates": 1860,
    "periods": {
     "covid_crash": 7.01,
     "covid_recovery": -15.8,
     "bear_2022": 3.03,
     "rebound_2022": -13.96,
     "other_2023_2026": 9.01
    }
   },
   "holdout": {
    "first": "2022-01-03",
    "last": "2026-10-23",
    "final_equity": 9814.235365743105,
    "return_pct": -1.8576463425689527,
    "cagr_pct": -0.38970991361314544,
    "max_dd_pct": -20.810043441291526,
    "yearly_return_pct": {
     "2022": -4.41,
     "2023": 7.33,
     "2024": -0.72,
     "2025": -6.34,
     "2026": 2.88
    },
    "trades": 148,
    "exposure_pct": 54.18392709196355,
    "win_rate": 43.91891891891892,
    "expectancy_r": -0.0062357887262124885,
    "profit_factor": 0.9793251111989028,
    "borrow_paid": 220.3130451395087,
    "dividends_paid": 100.979,
    "open_at_end": 5,
    "skipped": {
     "daily_entries": 90,
     "positions": 842,
     "ticker_open": 92
    },
    "candidates": 1177,
    "periods": {
     "bear_2022": 5.65,
     "rebound_2022": -14.01,
     "other_2023_2026": 8.02
    }
   }
  }
 }
}
```

## Other universes, non-overlapping

| universe | market | strategy | scenario | trades | win_rate | profit_factor | expectancy_r | median_r |
|---|---|---|---|---|---|---|---|---|
| sp500 | primary | breakdown | gross_r | 3580 | 38.66 | 0.74 | -0.12 | -0.26 |
| sp500 | primary | breakdown | net_r_base_gc | 3580 | 36.96 | 0.67 | -0.15 | -0.30 |
| sp500 | primary | breakdown | net_r_base_warm | 3580 | 36.20 | 0.64 | -0.17 | -0.32 |
| sp500 | primary | breakdown | net_r_base_hot | 3580 | 34.13 | 0.57 | -0.22 | -0.37 |
| sp500 | primary | breakdown | net_r_base_htb | 3580 | 28.77 | 0.41 | -0.35 | -0.52 |
| sp500 | primary | breakdown | net_r_wide_gc | 3580 | 35.78 | 0.63 | -0.19 | -0.33 |
| sp500 | primary | breakdown | net_r_wide_warm | 3580 | 34.80 | 0.60 | -0.20 | -0.35 |
| sp500 | primary | breakdown | net_r_wide_hot | 3580 | 33.07 | 0.53 | -0.25 | -0.40 |
| sp500 | primary | breakdown | net_r_wide_htb | 3580 | 27.88 | 0.38 | -0.38 | -0.54 |
| sp500 | primary | breakdown | net_r_stress_gc | 3580 | 34.11 | 0.55 | -0.24 | -0.37 |
| sp500 | primary | breakdown | net_r_stress_warm | 3580 | 33.32 | 0.53 | -0.26 | -0.39 |
| sp500 | primary | breakdown | net_r_stress_hot | 3580 | 31.12 | 0.47 | -0.30 | -0.44 |
| sp500 | primary | breakdown | net_r_stress_htb | 3580 | 26.34 | 0.34 | -0.43 | -0.59 |
| sp500 | primary | breakdown_retest | gross_r | 2343 | 30.30 | 0.70 | -0.19 | -1.00 |
| sp500 | primary | breakdown_retest | net_r_base_gc | 2343 | 29.28 | 0.64 | -0.24 | -1.02 |
| sp500 | primary | breakdown_retest | net_r_base_warm | 2343 | 28.72 | 0.61 | -0.26 | -1.03 |
| sp500 | primary | breakdown_retest | net_r_base_hot | 2343 | 27.66 | 0.55 | -0.32 | -1.04 |
| sp500 | primary | breakdown_retest | net_r_base_htb | 2343 | 23.43 | 0.41 | -0.48 | -1.07 |
| sp500 | primary | breakdown_retest | net_r_wide_gc | 2343 | 28.55 | 0.58 | -0.29 | -1.05 |
| sp500 | primary | breakdown_retest | net_r_wide_warm | 2343 | 28.04 | 0.56 | -0.31 | -1.06 |
| sp500 | primary | breakdown_retest | net_r_wide_hot | 2343 | 26.76 | 0.51 | -0.37 | -1.07 |
| sp500 | primary | breakdown_retest | net_r_wide_htb | 2343 | 22.79 | 0.38 | -0.53 | -1.11 |
| sp500 | primary | breakdown_retest | net_r_stress_gc | 2343 | 27.61 | 0.51 | -0.37 | -1.10 |
| sp500 | primary | breakdown_retest | net_r_stress_warm | 2343 | 26.85 | 0.49 | -0.39 | -1.11 |
| sp500 | primary | breakdown_retest | net_r_stress_hot | 2343 | 25.52 | 0.44 | -0.45 | -1.13 |
| sp500 | primary | breakdown_retest | net_r_stress_htb | 2343 | 21.77 | 0.33 | -0.61 | -1.18 |
| sp500 | primary | failed_breakout | gross_r | 556 | 36.51 | 0.63 | -0.19 | -0.41 |
| sp500 | primary | failed_breakout | net_r_base_gc | 556 | 35.25 | 0.57 | -0.23 | -0.44 |
| sp500 | primary | failed_breakout | net_r_base_warm | 556 | 34.71 | 0.54 | -0.25 | -0.47 |
| sp500 | primary | failed_breakout | net_r_base_hot | 556 | 32.73 | 0.48 | -0.30 | -0.51 |
| sp500 | primary | failed_breakout | net_r_base_htb | 556 | 28.60 | 0.34 | -0.43 | -0.70 |
| sp500 | primary | failed_breakout | net_r_wide_gc | 556 | 34.53 | 0.52 | -0.27 | -0.48 |
| sp500 | primary | failed_breakout | net_r_wide_warm | 556 | 33.63 | 0.50 | -0.29 | -0.50 |
| sp500 | primary | failed_breakout | net_r_wide_hot | 556 | 32.19 | 0.44 | -0.34 | -0.55 |
| sp500 | primary | failed_breakout | net_r_wide_htb | 556 | 26.98 | 0.31 | -0.47 | -0.72 |
| sp500 | primary | failed_breakout | net_r_stress_gc | 556 | 32.73 | 0.46 | -0.33 | -0.52 |
| sp500 | primary | failed_breakout | net_r_stress_warm | 556 | 32.37 | 0.44 | -0.35 | -0.55 |
| sp500 | primary | failed_breakout | net_r_stress_hot | 556 | 30.40 | 0.39 | -0.40 | -0.61 |
| sp500 | primary | failed_breakout | net_r_stress_htb | 556 | 24.64 | 0.27 | -0.53 | -0.77 |
| sp500 | off | breakdown | gross_r | 6787 | 41.70 | 0.79 | -0.09 | -0.18 |
| sp500 | off | breakdown | net_r_base_gc | 6787 | 39.97 | 0.71 | -0.13 | -0.22 |
| sp500 | off | breakdown | net_r_base_warm | 6787 | 39.15 | 0.68 | -0.15 | -0.24 |
| sp500 | off | breakdown | net_r_base_hot | 6787 | 36.84 | 0.59 | -0.20 | -0.30 |
| sp500 | off | breakdown | net_r_base_htb | 6787 | 30.53 | 0.40 | -0.34 | -0.45 |
| sp500 | off | breakdown | net_r_wide_gc | 6787 | 38.78 | 0.65 | -0.16 | -0.25 |
| sp500 | off | breakdown | net_r_wide_warm | 6787 | 37.84 | 0.62 | -0.18 | -0.27 |
| sp500 | off | breakdown | net_r_wide_hot | 6787 | 35.67 | 0.54 | -0.23 | -0.32 |
| sp500 | off | breakdown | net_r_wide_htb | 6787 | 29.20 | 0.37 | -0.37 | -0.48 |
| sp500 | off | breakdown | net_r_stress_gc | 6787 | 36.85 | 0.57 | -0.22 | -0.30 |
| sp500 | off | breakdown | net_r_stress_warm | 6787 | 35.92 | 0.54 | -0.24 | -0.32 |
| sp500 | off | breakdown | net_r_stress_hot | 6787 | 33.62 | 0.47 | -0.29 | -0.37 |
| sp500 | off | breakdown | net_r_stress_htb | 6787 | 27.33 | 0.32 | -0.43 | -0.54 |
| sp500 | off | breakdown_retest | gross_r | 4197 | 34.55 | 0.77 | -0.13 | -1.00 |
| sp500 | off | breakdown_retest | net_r_base_gc | 4197 | 33.10 | 0.69 | -0.19 | -1.02 |
| sp500 | off | breakdown_retest | net_r_base_warm | 4197 | 32.48 | 0.66 | -0.22 | -1.02 |
| sp500 | off | breakdown_retest | net_r_base_hot | 4197 | 30.66 | 0.58 | -0.28 | -1.03 |
| sp500 | off | breakdown_retest | net_r_base_htb | 4197 | 25.26 | 0.41 | -0.46 | -1.06 |
| sp500 | off | breakdown_retest | net_r_wide_gc | 4197 | 32.19 | 0.63 | -0.25 | -1.04 |
| sp500 | off | breakdown_retest | net_r_wide_warm | 4197 | 31.52 | 0.60 | -0.27 | -1.05 |
| sp500 | off | breakdown_retest | net_r_wide_hot | 4197 | 29.52 | 0.53 | -0.33 | -1.06 |
| sp500 | off | breakdown_retest | net_r_wide_htb | 4197 | 24.35 | 0.37 | -0.52 | -1.10 |
| sp500 | off | breakdown_retest | net_r_stress_gc | 4197 | 30.66 | 0.54 | -0.34 | -1.08 |
| sp500 | off | breakdown_retest | net_r_stress_warm | 4197 | 29.64 | 0.51 | -0.36 | -1.09 |
| sp500 | off | breakdown_retest | net_r_stress_hot | 4197 | 27.78 | 0.45 | -0.42 | -1.11 |
| sp500 | off | breakdown_retest | net_r_stress_htb | 4197 | 23.14 | 0.32 | -0.60 | -1.17 |
| sp500 | off | failed_breakout | gross_r | 3460 | 41.94 | 0.80 | -0.10 | -0.27 |
| sp500 | off | failed_breakout | net_r_base_gc | 3460 | 40.23 | 0.71 | -0.15 | -0.33 |
| sp500 | off | failed_breakout | net_r_base_warm | 3460 | 39.34 | 0.68 | -0.17 | -0.36 |
| sp500 | off | failed_breakout | net_r_base_hot | 3460 | 37.08 | 0.59 | -0.23 | -0.43 |
| sp500 | off | failed_breakout | net_r_base_htb | 3460 | 31.50 | 0.40 | -0.39 | -0.64 |
| sp500 | off | failed_breakout | net_r_wide_gc | 3460 | 39.08 | 0.65 | -0.19 | -0.37 |
| sp500 | off | failed_breakout | net_r_wide_warm | 3460 | 38.15 | 0.61 | -0.21 | -0.40 |
| sp500 | off | failed_breakout | net_r_wide_hot | 3460 | 36.24 | 0.54 | -0.27 | -0.47 |
| sp500 | off | failed_breakout | net_r_wide_htb | 3460 | 30.26 | 0.36 | -0.43 | -0.68 |
| sp500 | off | failed_breakout | net_r_stress_gc | 3460 | 37.08 | 0.55 | -0.26 | -0.44 |
| sp500 | off | failed_breakout | net_r_stress_warm | 3460 | 36.39 | 0.53 | -0.29 | -0.47 |
| sp500 | off | failed_breakout | net_r_stress_hot | 3460 | 34.36 | 0.46 | -0.34 | -0.54 |
| sp500 | off | failed_breakout | net_r_stress_htb | 3460 | 28.12 | 0.31 | -0.50 | -0.74 |
| sp1500 | primary | breakdown | gross_r | 8693 | 39.13 | 0.80 | -0.09 | -0.26 |
| sp1500 | primary | breakdown | net_r_base_gc | 8693 | 37.86 | 0.74 | -0.12 | -0.29 |
| sp1500 | primary | breakdown | net_r_base_warm | 8693 | 37.26 | 0.71 | -0.14 | -0.31 |
| sp1500 | primary | breakdown | net_r_base_hot | 8693 | 35.76 | 0.65 | -0.18 | -0.36 |
| sp1500 | primary | breakdown | net_r_base_htb | 8693 | 31.24 | 0.49 | -0.29 | -0.48 |
| sp1500 | primary | breakdown | net_r_wide_gc | 8693 | 37.01 | 0.70 | -0.15 | -0.31 |
| sp1500 | primary | breakdown | net_r_wide_warm | 8693 | 36.50 | 0.67 | -0.16 | -0.33 |
| sp1500 | primary | breakdown | net_r_wide_hot | 8693 | 34.84 | 0.61 | -0.21 | -0.38 |
| sp1500 | primary | breakdown | net_r_wide_htb | 8693 | 30.52 | 0.46 | -0.32 | -0.51 |
| sp1500 | primary | breakdown | net_r_stress_gc | 8693 | 35.76 | 0.63 | -0.20 | -0.36 |
| sp1500 | primary | breakdown | net_r_stress_warm | 8693 | 35.09 | 0.60 | -0.21 | -0.38 |
| sp1500 | primary | breakdown | net_r_stress_hot | 8693 | 33.27 | 0.55 | -0.25 | -0.42 |
| sp1500 | primary | breakdown | net_r_stress_htb | 8693 | 29.16 | 0.41 | -0.37 | -0.55 |
| sp1500 | primary | breakdown_retest | gross_r | 5747 | 32.35 | 0.79 | -0.13 | -1.00 |
| sp1500 | primary | breakdown_retest | net_r_base_gc | 5747 | 31.55 | 0.73 | -0.17 | -1.02 |
| sp1500 | primary | breakdown_retest | net_r_base_warm | 5747 | 30.99 | 0.71 | -0.19 | -1.03 |
| sp1500 | primary | breakdown_retest | net_r_base_hot | 5747 | 29.95 | 0.65 | -0.24 | -1.04 |
| sp1500 | primary | breakdown_retest | net_r_base_htb | 5747 | 26.26 | 0.50 | -0.38 | -1.06 |
| sp1500 | primary | breakdown_retest | net_r_wide_gc | 5747 | 30.85 | 0.68 | -0.22 | -1.05 |
| sp1500 | primary | breakdown_retest | net_r_wide_warm | 5747 | 30.42 | 0.66 | -0.24 | -1.06 |
| sp1500 | primary | breakdown_retest | net_r_wide_hot | 5747 | 29.20 | 0.60 | -0.29 | -1.07 |
| sp1500 | primary | breakdown_retest | net_r_wide_htb | 5747 | 25.60 | 0.47 | -0.43 | -1.10 |
| sp1500 | primary | breakdown_retest | net_r_stress_gc | 5747 | 29.88 | 0.60 | -0.30 | -1.10 |
| sp1500 | primary | breakdown_retest | net_r_stress_warm | 5747 | 29.28 | 0.58 | -0.31 | -1.10 |
| sp1500 | primary | breakdown_retest | net_r_stress_hot | 5747 | 28.05 | 0.53 | -0.36 | -1.12 |
| sp1500 | primary | breakdown_retest | net_r_stress_htb | 5747 | 24.71 | 0.42 | -0.51 | -1.16 |
| sp1500 | primary | failed_breakout | gross_r | 1229 | 32.87 | 0.50 | -0.27 | -0.51 |
| sp1500 | primary | failed_breakout | net_r_base_gc | 1229 | 32.22 | 0.46 | -0.31 | -0.54 |
| sp1500 | primary | failed_breakout | net_r_base_warm | 1229 | 31.90 | 0.44 | -0.32 | -0.56 |
| sp1500 | primary | failed_breakout | net_r_base_hot | 1229 | 30.02 | 0.40 | -0.36 | -0.61 |
| sp1500 | primary | failed_breakout | net_r_base_htb | 1229 | 25.87 | 0.30 | -0.47 | -0.75 |
| sp1500 | primary | failed_breakout | net_r_wide_gc | 1229 | 31.57 | 0.43 | -0.34 | -0.57 |
| sp1500 | primary | failed_breakout | net_r_wide_warm | 1229 | 30.92 | 0.41 | -0.35 | -0.59 |
| sp1500 | primary | failed_breakout | net_r_wide_hot | 1229 | 29.21 | 0.37 | -0.39 | -0.63 |
| sp1500 | primary | failed_breakout | net_r_wide_htb | 1229 | 25.06 | 0.28 | -0.50 | -0.79 |
| sp1500 | primary | failed_breakout | net_r_stress_gc | 1229 | 29.94 | 0.38 | -0.39 | -0.62 |
| sp1500 | primary | failed_breakout | net_r_stress_warm | 1229 | 29.37 | 0.37 | -0.40 | -0.63 |
| sp1500 | primary | failed_breakout | net_r_stress_hot | 1229 | 27.50 | 0.33 | -0.44 | -0.69 |
| sp1500 | primary | failed_breakout | net_r_stress_htb | 1229 | 23.60 | 0.25 | -0.55 | -0.84 |
| sp1500 | off | breakdown | gross_r | 16699 | 42.45 | 0.85 | -0.06 | -0.17 |
| sp1500 | off | breakdown | net_r_base_gc | 16699 | 40.86 | 0.78 | -0.10 | -0.20 |
| sp1500 | off | breakdown | net_r_base_warm | 16699 | 40.19 | 0.74 | -0.12 | -0.22 |
| sp1500 | off | breakdown | net_r_base_hot | 16699 | 38.49 | 0.66 | -0.16 | -0.26 |
| sp1500 | off | breakdown | net_r_base_htb | 16699 | 32.99 | 0.48 | -0.28 | -0.40 |
| sp1500 | off | breakdown | net_r_wide_gc | 16699 | 39.97 | 0.72 | -0.13 | -0.23 |
| sp1500 | off | breakdown | net_r_wide_warm | 16699 | 39.33 | 0.69 | -0.14 | -0.24 |
| sp1500 | off | breakdown | net_r_wide_hot | 16699 | 37.35 | 0.62 | -0.19 | -0.29 |
| sp1500 | off | breakdown | net_r_wide_htb | 16699 | 31.98 | 0.45 | -0.31 | -0.43 |
| sp1500 | off | breakdown | net_r_stress_gc | 16699 | 38.46 | 0.64 | -0.18 | -0.27 |
| sp1500 | off | breakdown | net_r_stress_warm | 16699 | 37.62 | 0.61 | -0.19 | -0.29 |
| sp1500 | off | breakdown | net_r_stress_hot | 16699 | 35.58 | 0.55 | -0.24 | -0.33 |
| sp1500 | off | breakdown | net_r_stress_htb | 16699 | 30.28 | 0.40 | -0.36 | -0.47 |
| sp1500 | off | breakdown_retest | gross_r | 10633 | 35.16 | 0.86 | -0.08 | -1.00 |
| sp1500 | off | breakdown_retest | net_r_base_gc | 10633 | 33.90 | 0.78 | -0.14 | -1.02 |
| sp1500 | off | breakdown_retest | net_r_base_warm | 10633 | 33.32 | 0.75 | -0.16 | -1.02 |
| sp1500 | off | breakdown_retest | net_r_base_hot | 10633 | 31.98 | 0.68 | -0.22 | -1.03 |
| sp1500 | off | breakdown_retest | net_r_base_htb | 10633 | 27.60 | 0.50 | -0.38 | -1.05 |
| sp1500 | off | breakdown_retest | net_r_wide_gc | 10633 | 33.10 | 0.72 | -0.19 | -1.05 |
| sp1500 | off | breakdown_retest | net_r_wide_warm | 10633 | 32.58 | 0.69 | -0.21 | -1.05 |
| sp1500 | off | breakdown_retest | net_r_wide_hot | 10633 | 31.10 | 0.62 | -0.27 | -1.07 |
| sp1500 | off | breakdown_retest | net_r_wide_htb | 10633 | 26.78 | 0.46 | -0.43 | -1.10 |
| sp1500 | off | breakdown_retest | net_r_stress_gc | 10633 | 31.96 | 0.62 | -0.28 | -1.09 |
| sp1500 | off | breakdown_retest | net_r_stress_warm | 10633 | 31.21 | 0.60 | -0.30 | -1.10 |
| sp1500 | off | breakdown_retest | net_r_stress_hot | 10633 | 29.79 | 0.54 | -0.36 | -1.12 |
| sp1500 | off | breakdown_retest | net_r_stress_htb | 10633 | 25.52 | 0.40 | -0.52 | -1.16 |
| sp1500 | off | failed_breakout | gross_r | 7657 | 42.54 | 0.86 | -0.07 | -0.24 |
| sp1500 | off | failed_breakout | net_r_base_gc | 7657 | 41.40 | 0.78 | -0.11 | -0.29 |
| sp1500 | off | failed_breakout | net_r_base_warm | 7657 | 40.72 | 0.75 | -0.13 | -0.32 |
| sp1500 | off | failed_breakout | net_r_base_hot | 7657 | 38.67 | 0.67 | -0.18 | -0.38 |
| sp1500 | off | failed_breakout | net_r_base_htb | 7657 | 33.96 | 0.48 | -0.32 | -0.56 |
| sp1500 | off | failed_breakout | net_r_wide_gc | 7657 | 40.49 | 0.72 | -0.15 | -0.33 |
| sp1500 | off | failed_breakout | net_r_wide_warm | 7657 | 39.70 | 0.69 | -0.17 | -0.35 |
| sp1500 | off | failed_breakout | net_r_wide_hot | 7657 | 37.82 | 0.62 | -0.22 | -0.42 |
| sp1500 | off | failed_breakout | net_r_wide_htb | 7657 | 32.91 | 0.44 | -0.36 | -0.60 |
| sp1500 | off | failed_breakout | net_r_stress_gc | 7657 | 38.67 | 0.63 | -0.21 | -0.38 |
| sp1500 | off | failed_breakout | net_r_stress_warm | 7657 | 37.93 | 0.61 | -0.23 | -0.41 |
| sp1500 | off | failed_breakout | net_r_stress_hot | 7657 | 36.29 | 0.54 | -0.28 | -0.48 |
| sp1500 | off | failed_breakout | net_r_stress_htb | 7657 | 31.49 | 0.39 | -0.42 | -0.66 |
| sp1500_with_ambiguous | primary | breakdown | gross_r | 8693 | 39.13 | 0.80 | -0.09 | -0.26 |
| sp1500_with_ambiguous | primary | breakdown | net_r_base_gc | 8693 | 37.86 | 0.74 | -0.12 | -0.29 |
| sp1500_with_ambiguous | primary | breakdown | net_r_base_warm | 8693 | 37.26 | 0.71 | -0.14 | -0.31 |
| sp1500_with_ambiguous | primary | breakdown | net_r_base_hot | 8693 | 35.76 | 0.65 | -0.18 | -0.36 |
| sp1500_with_ambiguous | primary | breakdown | net_r_base_htb | 8693 | 31.24 | 0.49 | -0.29 | -0.48 |
| sp1500_with_ambiguous | primary | breakdown | net_r_wide_gc | 8693 | 37.01 | 0.70 | -0.15 | -0.31 |
| sp1500_with_ambiguous | primary | breakdown | net_r_wide_warm | 8693 | 36.50 | 0.67 | -0.16 | -0.33 |
| sp1500_with_ambiguous | primary | breakdown | net_r_wide_hot | 8693 | 34.84 | 0.61 | -0.21 | -0.38 |
| sp1500_with_ambiguous | primary | breakdown | net_r_wide_htb | 8693 | 30.52 | 0.46 | -0.32 | -0.51 |
| sp1500_with_ambiguous | primary | breakdown | net_r_stress_gc | 8693 | 35.76 | 0.63 | -0.20 | -0.36 |
| sp1500_with_ambiguous | primary | breakdown | net_r_stress_warm | 8693 | 35.09 | 0.60 | -0.21 | -0.38 |
| sp1500_with_ambiguous | primary | breakdown | net_r_stress_hot | 8693 | 33.27 | 0.55 | -0.25 | -0.42 |
| sp1500_with_ambiguous | primary | breakdown | net_r_stress_htb | 8693 | 29.16 | 0.41 | -0.37 | -0.55 |
| sp1500_with_ambiguous | primary | breakdown_retest | gross_r | 5747 | 32.35 | 0.79 | -0.13 | -1.00 |
| sp1500_with_ambiguous | primary | breakdown_retest | net_r_base_gc | 5747 | 31.55 | 0.73 | -0.17 | -1.02 |
| sp1500_with_ambiguous | primary | breakdown_retest | net_r_base_warm | 5747 | 30.99 | 0.71 | -0.19 | -1.03 |
| sp1500_with_ambiguous | primary | breakdown_retest | net_r_base_hot | 5747 | 29.95 | 0.65 | -0.24 | -1.04 |
| sp1500_with_ambiguous | primary | breakdown_retest | net_r_base_htb | 5747 | 26.26 | 0.50 | -0.38 | -1.06 |
| sp1500_with_ambiguous | primary | breakdown_retest | net_r_wide_gc | 5747 | 30.85 | 0.68 | -0.22 | -1.05 |
| sp1500_with_ambiguous | primary | breakdown_retest | net_r_wide_warm | 5747 | 30.42 | 0.66 | -0.24 | -1.06 |
| sp1500_with_ambiguous | primary | breakdown_retest | net_r_wide_hot | 5747 | 29.20 | 0.60 | -0.29 | -1.07 |
| sp1500_with_ambiguous | primary | breakdown_retest | net_r_wide_htb | 5747 | 25.60 | 0.47 | -0.43 | -1.10 |
| sp1500_with_ambiguous | primary | breakdown_retest | net_r_stress_gc | 5747 | 29.88 | 0.60 | -0.30 | -1.10 |
| sp1500_with_ambiguous | primary | breakdown_retest | net_r_stress_warm | 5747 | 29.28 | 0.58 | -0.31 | -1.10 |
| sp1500_with_ambiguous | primary | breakdown_retest | net_r_stress_hot | 5747 | 28.05 | 0.53 | -0.36 | -1.12 |
| sp1500_with_ambiguous | primary | breakdown_retest | net_r_stress_htb | 5747 | 24.71 | 0.42 | -0.51 | -1.16 |
| sp1500_with_ambiguous | primary | failed_breakout | gross_r | 1229 | 32.87 | 0.50 | -0.27 | -0.51 |
| sp1500_with_ambiguous | primary | failed_breakout | net_r_base_gc | 1229 | 32.22 | 0.46 | -0.31 | -0.54 |
| sp1500_with_ambiguous | primary | failed_breakout | net_r_base_warm | 1229 | 31.90 | 0.44 | -0.32 | -0.56 |
| sp1500_with_ambiguous | primary | failed_breakout | net_r_base_hot | 1229 | 30.02 | 0.40 | -0.36 | -0.61 |
| sp1500_with_ambiguous | primary | failed_breakout | net_r_base_htb | 1229 | 25.87 | 0.30 | -0.47 | -0.75 |
| sp1500_with_ambiguous | primary | failed_breakout | net_r_wide_gc | 1229 | 31.57 | 0.43 | -0.34 | -0.57 |
| sp1500_with_ambiguous | primary | failed_breakout | net_r_wide_warm | 1229 | 30.92 | 0.41 | -0.35 | -0.59 |
| sp1500_with_ambiguous | primary | failed_breakout | net_r_wide_hot | 1229 | 29.21 | 0.37 | -0.39 | -0.63 |
| sp1500_with_ambiguous | primary | failed_breakout | net_r_wide_htb | 1229 | 25.06 | 0.28 | -0.50 | -0.79 |
| sp1500_with_ambiguous | primary | failed_breakout | net_r_stress_gc | 1229 | 29.94 | 0.38 | -0.39 | -0.62 |
| sp1500_with_ambiguous | primary | failed_breakout | net_r_stress_warm | 1229 | 29.37 | 0.37 | -0.40 | -0.63 |
| sp1500_with_ambiguous | primary | failed_breakout | net_r_stress_hot | 1229 | 27.50 | 0.33 | -0.44 | -0.69 |
| sp1500_with_ambiguous | primary | failed_breakout | net_r_stress_htb | 1229 | 23.60 | 0.25 | -0.55 | -0.84 |
| sp1500_with_ambiguous | off | breakdown | gross_r | 16699 | 42.45 | 0.85 | -0.06 | -0.17 |
| sp1500_with_ambiguous | off | breakdown | net_r_base_gc | 16699 | 40.86 | 0.78 | -0.10 | -0.20 |
| sp1500_with_ambiguous | off | breakdown | net_r_base_warm | 16699 | 40.19 | 0.74 | -0.12 | -0.22 |
| sp1500_with_ambiguous | off | breakdown | net_r_base_hot | 16699 | 38.49 | 0.66 | -0.16 | -0.26 |
| sp1500_with_ambiguous | off | breakdown | net_r_base_htb | 16699 | 32.99 | 0.48 | -0.28 | -0.40 |
| sp1500_with_ambiguous | off | breakdown | net_r_wide_gc | 16699 | 39.97 | 0.72 | -0.13 | -0.23 |
| sp1500_with_ambiguous | off | breakdown | net_r_wide_warm | 16699 | 39.33 | 0.69 | -0.14 | -0.24 |
| sp1500_with_ambiguous | off | breakdown | net_r_wide_hot | 16699 | 37.35 | 0.62 | -0.19 | -0.29 |
| sp1500_with_ambiguous | off | breakdown | net_r_wide_htb | 16699 | 31.98 | 0.45 | -0.31 | -0.43 |
| sp1500_with_ambiguous | off | breakdown | net_r_stress_gc | 16699 | 38.46 | 0.64 | -0.18 | -0.27 |
| sp1500_with_ambiguous | off | breakdown | net_r_stress_warm | 16699 | 37.62 | 0.61 | -0.19 | -0.29 |
| sp1500_with_ambiguous | off | breakdown | net_r_stress_hot | 16699 | 35.58 | 0.55 | -0.24 | -0.33 |
| sp1500_with_ambiguous | off | breakdown | net_r_stress_htb | 16699 | 30.28 | 0.40 | -0.36 | -0.47 |
| sp1500_with_ambiguous | off | breakdown_retest | gross_r | 10633 | 35.16 | 0.86 | -0.08 | -1.00 |
| sp1500_with_ambiguous | off | breakdown_retest | net_r_base_gc | 10633 | 33.90 | 0.78 | -0.14 | -1.02 |
| sp1500_with_ambiguous | off | breakdown_retest | net_r_base_warm | 10633 | 33.32 | 0.75 | -0.16 | -1.02 |
| sp1500_with_ambiguous | off | breakdown_retest | net_r_base_hot | 10633 | 31.98 | 0.68 | -0.22 | -1.03 |
| sp1500_with_ambiguous | off | breakdown_retest | net_r_base_htb | 10633 | 27.60 | 0.50 | -0.38 | -1.05 |
| sp1500_with_ambiguous | off | breakdown_retest | net_r_wide_gc | 10633 | 33.10 | 0.72 | -0.19 | -1.05 |
| sp1500_with_ambiguous | off | breakdown_retest | net_r_wide_warm | 10633 | 32.58 | 0.69 | -0.21 | -1.05 |
| sp1500_with_ambiguous | off | breakdown_retest | net_r_wide_hot | 10633 | 31.10 | 0.62 | -0.27 | -1.07 |
| sp1500_with_ambiguous | off | breakdown_retest | net_r_wide_htb | 10633 | 26.78 | 0.46 | -0.43 | -1.10 |
| sp1500_with_ambiguous | off | breakdown_retest | net_r_stress_gc | 10633 | 31.96 | 0.62 | -0.28 | -1.09 |
| sp1500_with_ambiguous | off | breakdown_retest | net_r_stress_warm | 10633 | 31.21 | 0.60 | -0.30 | -1.10 |
| sp1500_with_ambiguous | off | breakdown_retest | net_r_stress_hot | 10633 | 29.79 | 0.54 | -0.36 | -1.12 |
| sp1500_with_ambiguous | off | breakdown_retest | net_r_stress_htb | 10633 | 25.52 | 0.40 | -0.52 | -1.16 |
| sp1500_with_ambiguous | off | failed_breakout | gross_r | 7657 | 42.54 | 0.86 | -0.07 | -0.24 |
| sp1500_with_ambiguous | off | failed_breakout | net_r_base_gc | 7657 | 41.40 | 0.78 | -0.11 | -0.29 |
| sp1500_with_ambiguous | off | failed_breakout | net_r_base_warm | 7657 | 40.72 | 0.75 | -0.13 | -0.32 |
| sp1500_with_ambiguous | off | failed_breakout | net_r_base_hot | 7657 | 38.67 | 0.67 | -0.18 | -0.38 |
| sp1500_with_ambiguous | off | failed_breakout | net_r_base_htb | 7657 | 33.96 | 0.48 | -0.32 | -0.56 |
| sp1500_with_ambiguous | off | failed_breakout | net_r_wide_gc | 7657 | 40.49 | 0.72 | -0.15 | -0.33 |
| sp1500_with_ambiguous | off | failed_breakout | net_r_wide_warm | 7657 | 39.70 | 0.69 | -0.17 | -0.35 |
| sp1500_with_ambiguous | off | failed_breakout | net_r_wide_hot | 7657 | 37.82 | 0.62 | -0.22 | -0.42 |
| sp1500_with_ambiguous | off | failed_breakout | net_r_wide_htb | 7657 | 32.91 | 0.44 | -0.36 | -0.60 |
| sp1500_with_ambiguous | off | failed_breakout | net_r_stress_gc | 7657 | 38.67 | 0.63 | -0.21 | -0.38 |
| sp1500_with_ambiguous | off | failed_breakout | net_r_stress_warm | 7657 | 37.93 | 0.61 | -0.23 | -0.41 |
| sp1500_with_ambiguous | off | failed_breakout | net_r_stress_hot | 7657 | 36.29 | 0.54 | -0.28 | -0.48 |
| sp1500_with_ambiguous | off | failed_breakout | net_r_stress_htb | 7657 | 31.49 | 0.39 | -0.42 | -0.66 |
