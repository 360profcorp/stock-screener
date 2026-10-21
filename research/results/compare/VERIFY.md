# Paper comparison: real-data equivalence (2026-10-21T01:48:39+00:00)

Tickers 503; comparison fingerprint `d74e0327e1d0`; Task 10 fingerprint `17454c61f631`.

**All checks passed: True**

## breakout
- raw signals 41539, window 2024-11-05 → 2026-10-20
- A) scanner vs history: 25/25 days identical
- B) book vs replay, full period: fills 201/201, decisions True (6734/6734), cash True, holdings True, equity True (490 days), open True, final 15481.16 vs 15481.16, violations 0
- C) live path (daily scan), last 30 sessions: fills 10/10, decisions True, cash True, holdings True, equity True, open True

## retest
- raw signals 21536, window 2024-11-05 → 2026-10-20
- A) scanner vs history: 25/25 days identical
- B) book vs replay, full period: fills 134/134, decisions True (3736/3736), cash True, holdings True, equity True (490 days), open True, final 17378.03 vs 17378.03, violations 0
- C) live path (daily scan), last 30 sessions: fills 14/14, decisions True, cash True, holdings True, equity True, open True
- control scanner identical to Task 10 `scan_day`: 25/25 days

