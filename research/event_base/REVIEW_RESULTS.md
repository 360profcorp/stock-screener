# E pilot — corrected registry of the 80 cases and the index dividend fix

**Plan:** `REVIEW_PLAN.md`, committed before any label or corrected number.
- C and S stay closed negative results of v1.
- The E rules, the success criteria and the 20 % drawdown target are unchanged.
- No returns or prices of any case were opened during the review.

**Sources**
- **Review packets:** `research/results/event_base/review/2026-10-26T015919Z/`. They hold the
  text windows of every 8-K with Items 2.02, 7.01, 8.01 or blank item codes, from
  `base_start − 520 days` to the signal date. Each document is identified by SHA256.
- **Original documents:** in artifacts `event-docs-40253859449` and the review run's
  `event-docs-*`.
- **Labels:** `manual_labels_v1.py`. The registry built from them is
  `research/results/event_base/review_labels/2026-10-26T020330Z/labels.csv`, with
  `summary.json`.
  - Every label quotes the filing (accession and URL) it rests on.
  - The timing of each raise is re-checked by code from EDGAR acceptance times.

## 1. Result of the manual review
| Status | Cases |
|---|---:|
| confirmed raise of a full-year revenue range | **7** |
| confirmed no raise | **15** |
| confirmed no suitable guidance | **53** |
| unknown | **5** |

**Coverage by year** (known status out of 10 cases):

| 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 80 % | 100 % | 100 % | 90 % | 100 % | 100 % | 80 % | 100 % |

**Manual coverage meets the ≥ 80 % requirement in every year of the pilot.** The automated
extractor v1 reached 0–20 % on the same cases.

**The 7 confirmed raises**
- All were accepted before `base_start`, are 24–50 sessions old at the signal, and their fiscal
  year was still open.
- Dollar Tree FY2017 (Nov 2017), Boeing 2018 (Jul 2018), Eli Lilly 2018 (Jul 2018), Cintas FY2020
  (Dec 2019), Cadence 2020 twice (Jul and Oct 2020), Intuit FY2025 (May 2025).

**Cadence regression example**
- Automated v1 called both Cadence cases raises using the **quarterly** ranges ($580–600 M →
  $630–650 M → $720–740 M).
- The **full-year** ranges were also raised in those releases: $2.545–2.585 B → $2.585–2.615 B →
  $2.643–2.663 B.
- So the status is right, but v1 got there through the wrong period. On other issuers the same
  mistake would produce false raises.

**The 15 confirmed non-raises:**

| Reason | Cases |
|---|---|
| initial guidance | 4 |
| reaffirmed | 3, two of them with the fiscal year already over |
| lowered, narrowed with a lower top end, or widened with a lower low end | 4 |
| raise whose fiscal year ended before the signal | 1 (PayPal 2017) |
| update not comparable | 3: new metric (Martin Marietta); acquisitions included and fiscal year over (TransDigm); point estimate replacing a range (Tractor Supply) |

**The 53 cases with no suitable guidance**
- None of these issuers publishes a full-year USD revenue **range** in its filed releases.
- 19 give no outlook at all, mostly banks, asset managers, insurers, Costco, AutoZone, Monster
  and NVR.
- 9 give growth percentages only, 4 organic or core growth only, 5 quarterly ranges only, 3 a
  point estimate, 2 EPS only; the rest are mixed.
- The automated extractor's hits on these issuers were checked: they are all quarterly or
  segment ranges.

**Why 5 cases stay unknown:**

| Case | Cause | Detail |
|---|---|---|
| T. Rowe Price 2018 | incomplete publication history | no earnings 8-K in EDGAR after 2017-01-26 up to the signal |
| Bank of America 2024 | tool retrieval gap | an Item 2.02 8-K without EX-99 whose main document the tool did not fetch |
| Diamondback 2024 | tool retrieval gap | same as Bank of America |
| Salesforce 2018 | extraction / comparability | the raise is stated, but the prior range and the business composition (MuleSoft) are not readable in the packet |
| LKQ 2021 | extraction | "outlook raised" is stated, but the outlook table was not captured |

**Limits**
- The labels are one reviewer's reading (Claude) of the primary text. They have not yet been
  checked by a second independent review.
- Guidance given only on earnings calls, never filed, is outside the record, so "no suitable
  guidance" means "none in the filed record".
- Only Item 2.02, 7.01 and 8.01 8-Ks are searched.

## 2. Answer to "can we recognise the event before the price move?"
- **By hand, from SEC filings: yes.**
  - On this pilot the status is established for 75 of 80 cases.
  - The event, when it exists, is dated by EDGAR acceptance before the base starts.
- **Automatically: not yet.**
  - Extractor v1 got 5 of 80 statuses, and its two raises came from the wrong (quarterly)
    ranges.
  - Before any expansion, the following gate of `REVIEW_PLAN.md` §4 B applies, unchanged.

**What the gate requires**
1. Build extractor v2, aware of quarter vs full year, tables, "versus prior", point estimates,
   acquisitions and metric names.
2. Draw a **new validation sample**: 80 S candidates, 10 a year 2018–2025, seed 20261026,
   excluding these 80.
3. Label that sample manually **before** opening v2's output on it.
4. Accept v2 only with status agreement ≥ 95 %, **zero false raises**, and the validation
   sample's manual coverage ≥ 80 % in every year.

**Only then:**
- collect events for all S candidates;
- run the first E versus S-covered versus the index alternatives.

**Expected size of E:** the pilot rate of 7 / 80 ≈ 9 % applied to about 1,075 S candidates
gives roughly 90 E signals. That is close to the minimum sample (50 in total, 20 in each half),
which is itself a risk to the test.

## 3. Index benchmark dividend fix (v2)
**The v1 faults**
- Shares bought at the open of an ex-date were paid the distribution; shares sold at that open
  were not.
- Distributions became cash and were reinvested on the ex-date.
- **Each distribution was reinvested only in whole shares bought with that one payment.** For
  SPY 100 % every quarterly payment was smaller than one share, so in v1 the distributions just
  sat as idle cash.

**v2:**
- entitlement from the shares held at the previous close;
- accrual on the ex-date;
- cash on the pay date (SPY: the end of the next month; BIL: 5 sessions);
- the whole accumulated balance reinvested at the next open.

**Results:**
- The v1 numbers were reproduced exactly before the fix.
- C and S were not re-simulated.

| Full window, ETF 2 bps | CAGR v1 | CAGR v2 | Max DD v1 | Max DD v2 | v2, pay on ex-date | Price only |
|---|---:|---:|---:|---:|---:|---:|
| SPY 100 % | 13.54 % | **14.33 %** | −32.0 % | −33.4 % | 14.33 % | 12.64 % |
| 50 % SPY / 50 % cash | 7.25 % | 7.25 % | −17.1 % | −17.1 % | 7.25 % | 6.41 % |
| 50 % SPY / 50 % BIL | 8.70 % | **8.67 %** | −16.9 % | −16.9 % | 8.69 % | 6.45 % |
| SPY timing 50 % | 3.76 % | 3.70 % | −7.7 % | −7.7 % | 3.70 % | 3.25 % |

- **50/50 SPY/BIL halves:** 2017–2021 9.62 % / −16.9 %; 2022–2026 7.56 % / −11.7 %.
- Only SPY 100 % moves materially, and it is above the 20 % drawdown limit anyway.
- **Decisions on C and S with v2 benchmarks:** both remain **NOT_A_CANDIDATE**, failing the same
  criteria.
- **Not changed:** the trading books still credit dividends as cash on the ex-date. That is a
  small effect, about $280 over the full C book.
