# Extractor v2 — validation result (REVIEW_PLAN.md §6)

## Sequence, as pre-registered
1. **Sample:** `validation/sample_seed20261026.csv` — 80 S candidates, 10 per year 2018–2025, pilot
   cases excluded.
2. **Packets:** `validation/packets/2026-10-26T024909Z/`.
3. **Extractor v2:** `extract_v2.py`, frozen in commit 02c4d1d (sha256 `ccda094a…8d98`).
   - Developed only on the 80 pilot cases.
   - The file was unchanged at run time (same hash).
4. **Manual labels:** `manual_labels_val.py`, committed in ff25b6a **before** v2 was run on this
   sample.
   - Filing text only; no prices or returns were opened.
5. **v2 run:** `validation/v2/2026-10-26T030021Z/` (`comparison.csv`, `event_status_v2.csv`,
   `summary.json`).

## Gate
| Condition | Required | Result | |
|---|---|---|---|
| status agreement | ≥ 95 % (≥ 76 / 80) | **71 / 80 = 88.8 %** | **fail** |
| false `confirmed_raise` | 0 | 0 | pass |
| manual coverage per year 2018–2025 | ≥ 80 % | 100 % in every year except 2022, which is 90 % | pass |

**v2 is not accepted.**
- E stays **INSUFFICIENT_DATA**.
- The full collection and the E vs S-covered vs index backtest were **not run**.
- No rule or criterion was changed, and v2 was not re-tuned on this sample.

**Manual labels:** 1 confirmed raise (HCA 2018, also found by v2), 10 confirmed no raise,
68 no suitable guidance, 1 unknown (PG&E, two filer CIKs).

## The 9 disagreements
| Case | Manual | v2 | Cause |
|---|---|---|---|
| VRTX 2022 | no_raise (initial FY2022 product revenues $8.4–8.6 B) | no_suitable | v2 classed the "full year 2022 product revenue guidance" sentence as quarterly. **A range was missed.** |
| GILD 2025 | no_raise (product sales $28,200–28,600 M, unchanged) | no_suitable | Table in millions with "Low End / High End" headers was not parsed. **A range was missed.** |
| META 2023 | no_suitable (quarterly revenue only) | no_raise "initial" | A spurious range of 32.17–116.61 was assembled from unrelated numbers. **A false range**, which can also yield a false raise. |
| META 2024 | no_suitable | no_raise "initial" | Same fault, spurious range 40.11–134.9. |
| TXT 2021 | no_suitable (point only) | unknown | A stated guidance change with no range: v2 abstains. |
| KR 2022 | no_suitable (identical-sales % only) | unknown | Same as TXT. |
| AMAT 2019 | no_suitable | no_raise "latest guided FY completed" | Labelling convention, see below. |
| LMT 2020 | no_suitable (2020 point ~$62.0 B) | no_raise "latest guided FY completed" | Labelling convention. |
| MSI 2024 | no_suitable (2024 growth % only) | no_raise "latest guided FY completed" | Labelling convention. |

**Labelling-convention note (reported, labels not edited)**
- In the pilot labels, a case whose most recent range was for a fiscal year already over was
  labelled `confirmed_no_raise`. Examples: PayPal 2017 and Boeing 2017.
- v2 was built on that convention.
- In the validation labels, AMAT, LMT and MSI follow the literal REVIEW_PLAN §3 definition instead:
  no current-FY range, so `no_suitable`.
- Both statuses are "known non-events": the choice does not change E or S-covered.
- **Even if these 3 were counted as agreements, the score would be 74 / 80 = 92.5 %, still below
  95 %.**

## Why it matters beyond the score
| Error | Cases | Effect on the strategy |
|---|---|---|
| Missed ranges | VRTX, GILD | Real ranges in a format v2 does not read. On the full ~1,075 candidates the same blind spot would hide raises, and E is already close to its minimum sample. |
| Spurious ranges | META ×2 | The direct route to a false `confirmed_raise`. Zero false raises appeared here only because the junk ranges were not followed by a higher one. |

## Possible next step (needs the owner's approval; not started)
**Extractor v3 must fix:**
- millions-unit tables with Low/High headers;
- "full year … guidance of $A to $B" phrases with a product-revenue metric;
- the stray-number range assembly;
- an explicit `no_suitable` vs `no_raise` rule for a completed guided fiscal year.

**Testing v3:**
- This validation sample is now used up as a test of v2. Its errors would inform v3, so it can
  no longer act as an independent test.
- v3 would need a **third, newly drawn sample** (a new seed, excluding both earlier samples),
  labelled before v3 is run, with the same gate.
