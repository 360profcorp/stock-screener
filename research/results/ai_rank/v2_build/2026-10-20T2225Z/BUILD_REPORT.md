# AI ranking v2 — data build (PREREG v2.1)

**Build only. No model was trained.** Next: Muse's data/feature/split audit.

```json
{
 "prereg": "v2.1",
 "data_end": "2026-10-14",
 "validation_start": "2025-03-17",
 "test_start": "2025-12-30",
 "dataset": {
  "signals": "dataset/2026-10-15T1656Z/signals.csv.gz",
  "bars": "dataset/2026-10-15T1656Z/bars.pkl.gz"
 },
 "pit_source_sha256": "36326709d46d6cd25834de5df457b16f5f96fad3a06b9beac28f7b88aa0b0d54",
 "rows_all_long": 25801,
 "rows_retest": 7060,
 "splits_retest": {
  "train": 3914,
  "test": 1549,
  "validation": 1300,
  "purged": 248,
  "embargo": 49
 },
 "nonoverlap_retest": 2220,
 "earnings": {
  "tickers": 440,
  "with_dates": 440,
  "failed": 0,
  "coverage_retest_dev": 0.9996,
  "coverage_rule": ">= 80% of eligible retest signals (train + validation) with sess_since_earn defined",
  "group_kept": true
 },
 "sectors": {
  "signals_without_sector": 45,
  "n_sectors": 11
 },
 "breadth": {
  "min_members": 452,
  "median_members": 480.0
 },
 "missing_share": {
  "rs_score": 0.0,
  "rank_rs": 0.0,
  "log_adv": 0.0,
  "atr14_pct": 0.0,
  "vol_ratio": 0.0,
  "vol10_vs_50": 0.0,
  "ret_1d": 0.0,
  "ret_5d": 0.0,
  "ret_20d": 0.0,
  "ret_63d": 0.0,
  "dist_ma50": 0.0,
  "dist_ma150": 0.0,
  "dist_ma200": 0.0,
  "dist_52w_high": 0.0,
  "dist_52w_low": 0.0,
  "dist_level_pct": 0.0,
  "risk_at_close_pct": 0.0,
  "spy_above200": 0.0,
  "spy_ret_20d": 0.0,
  "sess_since_earn": 0.0002,
  "sector_rs_median": 0.0017,
  "sector_ret20_median": 0.0017,
  "rs_minus_sector": 0.0017,
  "breadth_ma50": 0.0,
  "breadth_new_high": 0.0,
  "breadth_chg5": 0.0,
  "earn_within_5": 0.0
 },
 "deciding_features": [
  "rs_score",
  "rank_rs",
  "log_adv",
  "atr14_pct",
  "vol_ratio",
  "vol10_vs_50",
  "ret_1d",
  "ret_5d",
  "ret_20d",
  "ret_63d",
  "dist_ma50",
  "dist_ma150",
  "dist_ma200",
  "dist_52w_high",
  "dist_52w_low",
  "dist_level_pct",
  "risk_at_close_pct",
  "spy_above200",
  "spy_ret_20d",
  "sess_since_earn",
  "sector_rs_median",
  "sector_ret20_median",
  "rs_minus_sector",
  "breadth_ma50",
  "breadth_new_high",
  "breadth_chg5"
 ],
 "sensitivity_only": [
  "earn_within_5"
 ],
 "self_checks": {
  "cut_at_signal_day_recompute": {
   "days": [
    "2023-08-02",
    "2024-10-22",
    "2026-10-01"
   ],
   "mismatches": 0
  },
  "pit_membership_vs_pr5": {
   "rows": 25801,
   "mismatches": 0
  },
  "earnings_last_date_after_signal": 0
 },
 "stop_before_training": "BUILD ONLY \u2014 no model trained (PREREG v2.1: Muse's data audit first)",
 "files_sha256": {
  "2026-10-20T2225Z/dataset_v2.csv.gz": "48077f8f6b998c5bad80536ac27a95e63b47e37f8dbf0b7d5a55890cf0efe982",
  "2026-10-20T2225Z/earnings_raw.json": "6124ef832241d30e69e2f8d40f1bb4b6b1469a3c915db27c884afbf42c04d68b"
 },
 "git": "7d4e20158f8d5c3b65bd04701f0eb12667e211bd"
}
```
