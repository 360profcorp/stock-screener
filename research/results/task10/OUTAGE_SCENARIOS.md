# Task 10B — outage scenarios (actual outputs)

Deterministic: flat 100 bars, scripted signals (rs 90, stop 95), hold 3 bars, 0 bps; runs at 18:00 New York unless noted. Days: d0=2026-03-02, d1=2026-03-03, d2=2026-03-04, d3=2026-03-05, d4=2026-03-06, d5=2026-03-09, d6=2026-03-10, d7=2026-03-11

## S1_timely

AAA signal d0 (on time) -> fill d1 -> time exit d4; runner every evening

| field | value |
|---|---|
| sessions in last run | [{"day": "2026-03-09", "raw": 0, "queued": 0, "late": false, "processed_late": false}] |
| A timely: closed / open | 1 / 0 |
| B reconstructed: closed / open | 0 / 0 |
| B events | [] |
| C late, never traded | 0 [] |
| genuine_forward.available | True |
| contaminated_since / genuine_through | None / 2026-03-09 |
| genuine return % / final equity | 0.8121 / 10081.21 |
| genuine reason | None |
| observed contains reconstructed | False |
| late-processed sessions | [] |
| ledger | [{"ticker": "AAA", "entry_date": "2026-03-03", "exit_date": "2026-03-06", "reason": "time", "entry_processed_late": false, "exit_processed_late": false}] |
| open positions | [] |

## S2_late_entry

AAA queued on time d0; runner DOWN d1; d2 run processes d1 late

| field | value |
|---|---|
| sessions in last run | [{"day": "2026-03-05", "raw": 0, "queued": 0, "late": false, "processed_late": false}] |
| A timely: closed / open | 0 / 0 |
| B reconstructed: closed / open | 0 / 1 |
| B events | [{"date": "2026-03-03", "kind": "entry", "ticker": "AAA"}] |
| C late, never traded | 0 [] |
| genuine_forward.available | False |
| contaminated_since / genuine_through | 2026-03-03 / 2026-03-02 |
| genuine return % / final equity | 0.0 / 10000.0 |
| genuine reason | reconstructed execution(s) from 2026-03-03: portfolio-level genuine-forward return, drawdown, CAGR and SPY-relative performance are unavailable after 2026-03-02 |
| observed contains reconstructed | True |
| late-processed sessions | ['2026-03-03'] |
| ledger | [] |
| open positions | [{"ticker": "AAA", "entry_date": "2026-03-03", "entry_processed_late": true}] |

## S3_late_exit

AAA filled d1 on time; runner DOWN on exit day d4; d5 run processes d4

| field | value |
|---|---|
| sessions in last run | [{"day": "2026-03-06", "raw": 0, "queued": 0, "late": true, "processed_late": true}, {"day": "2026-03-09", "raw": 0, "queued": 0, "late": false, "processed_late": false}] |
| A timely: closed / open | 0 / 0 |
| B reconstructed: closed / open | 1 / 0 |
| B events | [{"date": "2026-03-06", "kind": "exit", "ticker": "AAA"}] |
| C late, never traded | 0 [] |
| genuine_forward.available | False |
| contaminated_since / genuine_through | 2026-03-06 / 2026-03-05 |
| genuine return % / final equity | 0.606 / 10060.6 |
| genuine reason | reconstructed execution(s) from 2026-03-06: portfolio-level genuine-forward return, drawdown, CAGR and SPY-relative performance are unavailable after 2026-03-05 |
| observed contains reconstructed | True |
| late-processed sessions | ['2026-03-06'] |
| ledger | [{"ticker": "AAA", "entry_date": "2026-03-03", "exit_date": "2026-03-06", "reason": "time", "entry_processed_late": false, "exit_processed_late": true}] |
| open positions | [] |

## S4_late_signal

d0 processed only at 10:00 NY on d1 (after the open): BBB late

| field | value |
|---|---|
| sessions in last run | [{"day": "2026-03-04", "raw": 0, "queued": 0, "late": false, "processed_late": false}] |
| A timely: closed / open | 0 / 0 |
| B reconstructed: closed / open | 0 / 0 |
| B events | [] |
| C late, never traded | 1 ["BBB"] |
| genuine_forward.available | True |
| contaminated_since / genuine_through | None / 2026-03-04 |
| genuine return % / final equity | 0.0 / 10000.0 |
| genuine reason | None |
| observed contains reconstructed | False |
| late-processed sessions | ['2026-03-02'] |
| ledger | [] |
| open positions | [] |

## S5_mixed

AAA timely round trip; BBB queued d4 on time, filled d5 while DOWN; CCC found during the d5 catch-up

| field | value |
|---|---|
| sessions in last run | [{"day": "2026-03-11", "raw": 0, "queued": 0, "late": false, "processed_late": false}] |
| A timely: closed / open | 1 / 0 |
| B reconstructed: closed / open | 0 / 1 |
| B events | [{"date": "2026-03-09", "kind": "entry", "ticker": "BBB"}] |
| C late, never traded | 1 ["CCC"] |
| genuine_forward.available | False |
| contaminated_since / genuine_through | 2026-03-09 / 2026-03-06 |
| genuine return % / final equity | 0.8121 / 10081.21 |
| genuine reason | reconstructed execution(s) from 2026-03-09: portfolio-level genuine-forward return, drawdown, CAGR and SPY-relative performance are unavailable after 2026-03-06 |
| observed contains reconstructed | True |
| late-processed sessions | ['2026-03-09'] |
| ledger | [{"ticker": "AAA", "entry_date": "2026-03-03", "exit_date": "2026-03-06", "reason": "time", "entry_processed_late": false, "exit_processed_late": false}] |
| open positions | [{"ticker": "BBB", "entry_date": "2026-03-09", "entry_processed_late": true}] |

## S6_late_entry_and_stop

AAA queued d0; runner DOWN d1-d2; d3 run: late entry d1 + late stop exit d2

| field | value |
|---|---|
| sessions in last run | [{"day": "2026-03-06", "raw": 0, "queued": 0, "late": false, "processed_late": false}] |
| A timely: closed / open | 0 / 0 |
| B reconstructed: closed / open | 1 / 0 |
| B events | [{"date": "2026-03-03", "kind": "entry", "ticker": "AAA"}, {"date": "2026-03-04", "kind": "exit", "ticker": "AAA"}] |
| C late, never traded | 0 [] |
| genuine_forward.available | False |
| contaminated_since / genuine_through | 2026-03-03 / 2026-03-02 |
| genuine return % / final equity | 0.0 / 10000.0 |
| genuine reason | reconstructed execution(s) from 2026-03-03: portfolio-level genuine-forward return, drawdown, CAGR and SPY-relative performance are unavailable after 2026-03-02 |
| observed contains reconstructed | True |
| late-processed sessions | ['2026-03-03', '2026-03-04'] |
| ledger | [{"ticker": "AAA", "entry_date": "2026-03-03", "exit_date": "2026-03-04", "reason": "stop", "entry_processed_late": true, "exit_processed_late": true}] |
| open positions | [] |
