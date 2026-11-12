# E (event + first base) — closure

**Status: INSUFFICIENT_DATA / VALIDATION_FAILED.** The owner decided on 2026-10-26 to stop E in
its current implementation.
- No v4 and no E backtest.
- No return of any E case was ever computed or opened.
- C and S stay the closed negative results of v1 (RESULTS.md).
- PR #25 stays Draft and is not merged.

## 1. What is kept (all committed on `research/event-base-v1`)
| Item | Files |
|---|---|
| Protocol | PLAN.md; REVIEW_PLAN.md §1–7 (the §6 and §7 addenda were committed before their data) |
| Pilot, 80 cases: manual review | `manual_labels_v1.py`; `review_labels/2026-10-26T020330Z/`; REVIEW_RESULTS.md |
| Validation sample, seed 20261026, 80 cases | `validation/sample_seed20261026.csv`; packets `validation/packets/2026-10-26T024909Z/`; labels `manual_labels_val.py` |
| Extractor v2 test | `extract_v2.py` (frozen 02c4d1d); `validation/v2/2026-10-26T030021Z/`; VALIDATION_RESULTS.md |
| Third sample, seed 20261027, 79 cases | `validation/sample_seed20261027.csv`; packets `validation/packets_test/2026-10-26T031212Z/`; labels `manual_labels_test.py` |
| Extractor v3 test | `extract_v3.py` and `eval_v3.py` (frozen 3a75b75); `validation/v3_test/2026-10-26T032209Z/`; V3_RESULTS.md |
| Development labels under the §7.1 convention | `manual_labels_r2.py` (originals unchanged) |
| Source documents | Actions artifacts `event-docs-*` (90-day retention) and the SHA256 of every document in the packets |

## 2. The three checks
### Check 1 — pilot (80): can the event be established by hand?
- **Automated v1:** 0–20 % coverage. Its two "raises" for Cadence came from quarterly ranges.
- **Manual review:** 7 raises, 15 no raise, 53 no suitable guidance, 5 unknown. Coverage was
  80–100 % in every year.
- **Verdict:** by hand, yes; automatically, no.

### Check 2 — extractor v2 on the validation sample (80)
Agreement 71 / 80 = 88.8 % against the required ≥ 95 %. **Failed.**
- False raises: 0.
- Missed raises: 0 (one real raise).

| manual \ v2 | raise | no_raise | no_suitable | unknown |
|---|---:|---:|---:|---:|
| raise | 1 | 0 | 0 | 0 |
| no_raise | 0 | 8 | 2 | 0 |
| no_suitable | 0 | 5 | 61 | 2 |
| unknown | 0 | 0 | 0 | 1 |

### Check 3 — extractor v3 on the third sample (79)
Agreement 74 / 79 = 93.7 % against the required ≥ 76 cases. **Failed.**
- False raises: 0.
- Recall: 2 / 2. Precision: 2 / 2. Both have a Wilson 95 % interval of 34–100 %.
- No look-ahead.
- Manual coverage ≥ 90 % in every year.

| manual \ v3 | raise | no_raise | no_suitable | unknown |
|---|---:|---:|---:|---:|
| raise | 2 | 0 | 0 | 0 |
| no_raise | 0 | 14 | 2 | 0 |
| no_suitable | 0 | 1 | 55 | 2 |
| unknown | 0 | 0 | 0 | 3 |

## 3. Critical risk: Eli Lilly, "Prior" read instead of "Revised"
**Where:** third sample, case 7, LLY.
- Base start 2018-07-30, signal 2018-09-07.
- Evidence 8-K 0000059478-18-000186, accepted 2018-07-24.

**The filing's guidance table** reads, in document order:

> 2018 Guidance **Prior** Revised Revenue **$23.7 to $24.2 billion** $24.0 to $24.5 billion

v3 takes the **first** full-year revenue range of a filing. In a "Prior | Revised" table that is
the **old** column. The full-year 2018 range that v3 stored for each LLY release:

| Release | v3 read | Actually stated | v3 effect |
|---|---|---|---|
| 2018-01-31 | 23.0–23.5 | 23.0–23.5 (unchanged) | correct, only because nothing changed |
| 2018-04-24 | 23.0–23.5 | **raised to 23.7–24.2** | raise **missed** |
| 2018-07-24 | 23.7–24.2 | **raised to 24.0–24.5** | the April raise is reported in July |

v3 called the case `confirmed_raise` with the right accession and the right timing. That result
was luck: the July release really was a raise, and the lagged Prior column also rose.

**Why it is critical for trading signals.** The error shifts every update **one release later**.
That produces false E signals in the most common pattern:
1. **Raise followed by reaffirmation.** Raise in Q1, reaffirm in Q2. In the Q2 release, Prior =
   the Q1 range, so v3 compares Q1's range with the stale Q4 range, sees a "raise" and **dates
   it at the Q2 acceptance**.
   - The false raise is fresh: young enough for the 60-session limit and early enough for the
     `base_start` check.
   - It becomes a buy signal, although no raise happened in the 60 sessions before the base.
2. **Lowering after a raise.** Raise in Q1, cut in Q2. The Q2 Prior column is the higher Q1
   range, so v3 again reports a raise, against the real direction.
3. **Real recent raises are missed or reported a quarter late.** Their timing then fails the
   60-session rule, so true events are lost.

**Why no check caught it:**
- The comparison is between columns of the same type, so the status was often right.
- The manual labels test the status, not the stored numbers.
- Only 10 raises exist in 239 labelled cases.

**Requirement for any future attempt** (not built now):
- Read table **column headers** ("Prior / Revised", "Previous / Updated", "Current / Prior"),
  never document order.
- Cross-check every table range against the narrative sentence of the same release ("now
  anticipates … between …").
- If the column role cannot be established, the case is `unknown`, never a raise.
- Test against labelled **numbers** (old and new ranges), not only against status.

## 4. Other limitations found
1. **Table layouts vary by issuer.** Every new sample showed a format not seen before:
   - millions columns;
   - `~` values without `$`;
   - GAAP / non-GAAP reconciliation columns read as a range;
   - ranges behind column headers.
2. **Item coverage.** Some issuers furnish earnings under Item 7.01 (Exelon 2022), so the
   "Item 2.02 within 120 days" rule fails.
3. **Labelling conventions.** Labels from one reviewer (Claude). Five development labels were
   re-stated in a dated file under §7.1, and two more after a v3 development run (BAC, FANG,
   disclosed in the file). One test label (Gartner) is arguably inconsistent with the pilot
   convention. No second independent review exists.
4. **Filed record only.** Guidance given only on calls is not in the record.
5. **Identity.** Four issuers in the samples had no unique filer CIK from Forms 3/4/5: PG&E
   (validation) and Agilent, Alphabet, Lennar (third sample).
6. **Sample size of the event.** 9 unique raises in 239 cases (3.8 %): 7 / 120 in 2017–2021 and
   2 / 119 in 2022–2026. A one-time manual collection of all 1,075 candidates would give about
   37 closed E trades, of which about 8 in 2022–2026. The PLAN §7 minimum is 50 and 20 in each
   half. The chance of reaching it is ≤ ~5 %, so E is not feasible as specified, independent of
   extraction quality.
7. **Repeated signals.** The same LLY raise appears in a pilot and a test case (2018-10-03 and
   2018-09-07). With "one signal per event", only the first can trade.
