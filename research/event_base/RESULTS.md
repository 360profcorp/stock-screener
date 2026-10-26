# Event & First-Base Breakout v1 — results (exploratory)

**Status: exploratory.** The 2017–2026 period was already examined, so neither half is an
independent holdout. Nothing here authorises a paper test, and the historical drawdown is not a
guarantee of future losses.

**Not changed:** Production, Paper, Trading, orders, positions, stops and `TRADING=dry`.

**Plan:** `PLAN.md`, committed in bbd8961 before any result existed.
- One technical addition came before any S result: windows with zero true range are not
  bases. The first run crashed on stale bars, so nothing had been computed yet.

**Run of the books:** GitHub Actions 40253326020 at git 9ba1aa5. Output:
`research/results/event_base/runs/2026-10-26T011603Z/`, with `REPORT.md`, `results.json`,
trades, orders, equity curves and `manifest.json`.

**Event pilot:** GitHub Actions 40253859449. Output:
`research/results/event_base/events/2026-10-26T012220Z/`. The original documents are in artifact
`event-docs-40253859449`.

## Verdicts

| Variant | Verdict | Why |
|---|---|---|
| **C** (3-session breakout, new execution) | **NOT_A_CANDIDATE** | max DD −27.5 % at 25 bps; full return −11.8 % at 25 bps; 2017–2021 negative; dominated by 50/50 SPY and SPY timing |
| **S** (first exit from a contracting base) | **NOT_A_CANDIDATE** | worse than C at both costs; fails drawdown, result, benefit vs C, vs 50/50 SPY/BIL, dominated by simpler benchmarks |
| **E** (S + raised full-year revenue guidance) | **INSUFFICIENT_DATA** | confirmed event coverage in the pilot was 0–20 % by year (needs ≥ 80 % in every year); no E return computed |

None of the variants meets the owner's objective of a useful return after costs with max DD
≤ 20 %. **50 % SPY / 50 % BIL** reaches it on this history: CAGR 8.7 %, max DD −16.9 %.

## Data and checks
**Data**
- Dataset `shorts10y-dataset-40152515701`:
  - `bars.pkl.gz` sha256 `98a68ab7…4650ab`;
  - PIT list sha256 `36326709…0d54`.
- **Windows:** full 2017-11-03 – 2026-10-23; separate books for 2017-11-03 – 2021-12-31 and
  2022-01-03 – 2026-10-23.
- **Universe:** 726 tickers ever in the PIT S&P 500; 609 have prices.

**PIT member-days without a price** (survivorship bias, strongest in the first half):

| 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 20.6 % | 18.8 % | 16.1 % | 12.9 % | 11.0 % | 8.4 % | 5.8 % | 4.3 % | 3.0 % | 1.1 % |

**Checks**
- **Reproduction of old M:** exact against PR #23 in all 9 cases (3 windows × 10 / 25 / 50 bps).
  Full window at 10 bps: +47.84 %, max DD −32.69 %, 690 trades. M uses the old model (1 % risk,
  20 % cap, unlimited open fill) and is **not** compared with C, S or E.
- **RS recomputed for S** equals `detect()`'s RS on all C signals.
- **Money:**
  - every book reconciles to the cent;
  - cash is never negative;
  - reservations never exceed cash.
- **Constraints:**
  - planned risk ≤ 0.500 % and position ≤ 10.0 % of equity at the signal close;
  - no fill above the limit;
  - every time exit is at bar e+20;
  - no stop exit above the stop.
- **Tests:** 60 pass, 17 of them new (`test_event_base.py`, PLAN §8).
- **Production code** is identical to main f0c784d (CI check).

## C versus S (new execution model)
**Execution and risk model:**
- 0.5 % planned risk from the limit; 10 % position cap; 5 positions; 3 entries a day;
- limit = close × 1.01, decided after the close, filled at the next open only if open ≤ limit;
- dividends credited; idle cash at 0 %.

| Book | bps | Return | CAGR | Max DD | Vol | PF | Closed trades | Turnover / yr | Costs | Dividends | Invested |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| C full | 10 | +6.2 % | +0.67 % | −19.6 % | 7.7 % | 1.04 | 718 | 13.1× | $1,091 | $279 | 26.6 % |
| C full | 25 | −11.8 % | −1.39 % | −27.5 % | 7.7 % | 0.92 | 719 | 13.0× | $2,465 | $248 | 26.2 % |
| C full | 50 | −33.9 % | −4.52 % | −37.6 % | 7.7 % | 0.76 | 713 | 12.6× | $4,187 | $213 | 26.2 % |
| S full | 10 | −12.0 % | −1.42 % | −19.5 % | 4.5 % | 0.84 | 421 | 8.1× | $661 | $186 | 20.0 % |
| S full | 25 | −20.0 % | −2.45 % | −24.1 % | 4.5 % | 0.75 | 421 | 8.1× | $1,563 | $179 | 19.9 % |
| S full | 50 | −34.2 % | −4.56 % | −36.5 % | 4.6 % | 0.60 | 420 | 8.1× | $2,852 | $164 | 19.7 % |
| C 2017–21 | 10 / 25 | −10.5 / −18.9 % | −2.62 / −4.90 % | −19.1 / −21.9 % | | 0.84 / 0.74 | 339 | | | | |
| C 2022–26 | 10 / 25 | +23.0 / +9.6 % | +4.40 / +1.93 % | −9.4 / −10.0 % | | 1.25 / 1.10 | 370 / 374 | | | | |
| S 2017–21 | 10 / 25 | −11.0 / −15.4 % | −2.75 / −3.95 % | −14.5 / −18.4 % | | 0.73 / 0.65 | 213 | | | | |
| S 2022–26 | 10 / 25 | +2.0 / −2.7 % | +0.41 / −0.57 % | −10.2 / −12.6 % | | 1.02 / 0.92 | 205 | | | | |

**Bad years (full book, 10 bps)**
- C: 2017 (partial), 2018 −12.7 %, 2019, 2021 −5.7 %, 2022 −6.2 %.
- S: 2018 −6.2 %, 2019 −4.8 %, 2021 −5.8 %, 2022 −4.1 %, 2025, 2026.

**Orders (full, 10 bps)**

| | Placed | Filled | Expired above the limit | Entered at or below the stop | No bar |
|---|---:|---:|---:|---:|---:|
| C | 849 | 707 | 129 (15 %) | 13 | 0 |
| S | 453 | 424 | 28 (6 %) | 1 | 0 |

- Candidates were mostly skipped because all 5 slots were full: C 21,903 times, S 578.

**Signals**
- **S candidates:** 1,075 first exits passed the filters on the full window. Of all bases, 7,762
  expired, 5,274 were cancelled and 7,439 first exits were consumed by a filter. The filters were
  RS 5,889, membership 1,234 and market 316.
- **C candidates:** 24,973 filtered signals.
- **Trade quality (10 bps):**

  | | Win rate | Expectancy | Time exits | Stops |
  |---|---:|---:|---|---|
  | S | 37 % | −0.07 R | +1.01 R (178) | −0.86 R (242) |
  | C | 30 % | +0.02 R | +1.57 R (248) | −0.82 R (457) |

  S stops less often, but its winners are much smaller.

**Paired bootstrap** (daily return differences, monthly blocks, 2,000 resamples, seed 20261025;
exploratory, 4 comparisons, no multiplicity correction):

| Comparison | bps | Mean | 90 % CI | P(> 0) |
|---|---:|---:|---|---:|
| S − C | 10 | −2.3 % a year | −6.4 … +1.4 | 0.14 |
| S − C | 25 | −1.3 % a year | −5.6 … +2.4 | 0.28 |
| S − 50/50 SPY/BIL | 10 | −10.1 % a year | −14.1 … −6.2 | 0.00 |
| S − 50/50 SPY/BIL | 25 | −11.2 % a year | −15.2 … −7.3 | 0.00 |

**Sensitivity** (full window, 10 / 25 bps CAGR; not a decision criterion):

| | Base | Stop −0.5 % | Stop at Low | Limit = close | 20 % non-fill |
|---|---|---|---|---|---|
| C | +0.67 / −1.39 | −1.44 / −4.01 | −5.39 / −6.83 | +1.85 / +0.02 | +0.85 / −0.96 |
| S | −1.42 / −2.45 | −2.38 / −3.65 | −4.05 / −5.18 | +0.73 / −0.29 | +0.09 / −1.06 |

- The results are very sensitive to stop fills: the "stop at Low" column is the worst case on
  daily bars.
- A stricter limit (open ≤ close) helps both books, but even then neither becomes positive at
  25 bps with a useful CAGR. This was observed after the fact and is not a rule.

## Index alternatives (same dates)
SPY and BIL with distributions, ETF costs 2 bps a side. With 5 bps CAGR changes by ≤ 0.2 pt.

| Benchmark | Full CAGR | Full max DD | 2017–21 CAGR / DD | 2022–26 CAGR / DD | Invested |
|---|---:|---:|---|---|---:|
| SPY 100 % | 13.54 % | −32.0 % | 16.90 % / −32.0 % | 10.75 % / −23.3 % | 94 % |
| 50 % SPY / 50 % cash (0 %) | 7.25 % | −17.1 % | 8.92 % / −17.1 % | 5.71 % / −12.0 % | 48 % |
| **50 % SPY / 50 % BIL**, monthly | **8.70 %** | **−16.9 %** | 9.62 % / −16.9 % | 7.80 % / −11.8 % | 98 % |
| SPY timing (50 % when SPY > SMA50 & SMA200) | 3.76 % | −7.7 % | 4.62 % / −7.5 % | 3.00 % / −7.2 % | 32 % |

- Price only, without distributions: SPY 12.64 %, 50/50 SPY/BIL 6.45 %.
- Distributions come from the dataset for SPY and from Yahoo for BIL (sha256 `dba1ec9e…`). The
  economic comparison is complete.
- **Criterion 5:**
  - 50/50 SPY/cash, 50/50 SPY/BIL and SPY timing all stay within the 20 % limit;
  - each of them has both a higher CAGR and a smaller drawdown than C and S at 10 and 25 bps.

## E — source check (pilot)
**Pilot sample:** 80 S candidates, 10 a year for 2018–2025, drawn with seed 20261025 before any
SEC data was fetched and without returns.

**What was fetched:**
- 1,342 SEC requests, 0 failed; 69 issuers; 481 Item 2.02 8-K filings; 593 EX-99 exhibits.
- Each exhibit's URL, accession, CIK, acceptance time and SHA256 are in
  `source_registry.csv`.

**Identity:** all 80 tickers mapped to exactly one CIK through issuer symbols in Forms 3/4/5
within ±365 days. No current ticker file was used.

**Status of the 80 candidates:** 2 `raise`, 3 `known_no_raise`, 75 `unknown`.

| Reason for unknown | Candidates |
|---|---:|
| latest release has no parsed full-year USD revenue range | 64 |
| fiscal year ends Jan–Mar, so its label is ambiguous | 7 |
| a release exhibit could not be retrieved | 4 |

**Coverage by year:**

| 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 % | 0 % | 20 % | 20 % | 0 % | 10 % | 0 % | 0 % |

**Manual check of the extracted ranges.** The excerpts are verbatim text from the filings, in
`extractions.csv`.
- **Both "raises" are false positives.** They are Cadence 2020 ranges of $580–600 M →
  $630–650 M → $720–740 M, which are **quarterly** revenue guidance. The document also gives a
  full-year range, but the extractor took the first range in a sentence labelled "fiscal year".
- Of the 51 extracted ranges, 31 have quarter wording in the excerpt (F5, NetApp, Cadence among
  them). The deterministic extractor does not separate quarterly from full-year guidance
  reliably.
- The 3 `known_no_raise` cases are real full-year ranges, and their status is correct:
  - Albemarle net sales $3.2–3.3 B;
  - Dentsply Sirona $3.85–3.95 B;
  - Howmet $5.05–5.20 B. The tool's reason ("initial guidance") is wrong: the text says
    "versus prior $5.05–$5.25 billion", which the extractor had missed in the earlier release. It
    is an update with a lower top end, so it is still not a raise.
- **Verified coverage is therefore about 3 / 80 (4 %).** That is far below the 80 % required in
  every year, so **E = INSUFFICIENT_DATA**.
- No full collection was run and no E or S-covered return was computed.

**What E would need:**
1. A full-year/quarter-aware parser (table structure, "fourth quarter", "Q1"), validated by hand
   on a fixed sample before any return is looked at.
2. A way to establish that an issuer gives no revenue guidance at all; today that is
   indistinguishable from a parse failure.
3. Handling of 52/53-week fiscal years and three-digit `fiscalYearEnd` values.
4. Other 8-K items (7.01 / 8.01 investor-day updates). Today only Item 2.02 is searched, a known
   gap.

Even then, many S&P 500 issuers (banks, insurers) do not give revenue ranges. Coverage of 80 % of
S candidates is probably out of reach for this definition of the event.

## Conclusion
1. **The first-base definition S does not improve on the simple breakout C** under the same
   execution model. Its CAGR is lower at both cost levels, and its trades average a negative R.
   Do not pursue S as defined.
2. **C itself is not a candidate.**
   - With 0.5 % risk and a 10 % cap it is invested only about 26 %.
   - Its edge is about +0.02 R at 10 bps and turns negative at 25 bps.
   - Its drawdown exceeds 20 % at 25 bps.
   - Its 2017–2021 book is negative.
3. **E cannot be tested with the data that can be established reliably now.** That is not a
   rejection of the economic idea.
4. **On this history, the owner's objective is met by 50 % SPY / 50 % BIL** (8.7 % CAGR, −16.9 %
   max DD), not by any of the tested signals. It is the reference any future strategy has to
   beat.
