# Extractor v3 — independent test on the third sample (REVIEW_PLAN.md §7)

## Sequence, as pre-registered
| Step | Commit |
|---|---|
| Protocol §7 and the convention-normalised dev labels, before any v3 code | 82314e3 |
| v3 and the gate script frozen (`extract_v3.py` sha256 `7dbfade8…6b0b`, `eval_v3.py` `66646ca4…9306`), before any third-sample packet | 3a75b75 |
| Third sample drawn: seed 20261027, 79 cases (2022 has only 9 candidates left) | 1b0e2b5 |
| Packets fetched | `validation/packets_test/2026-10-26T031212Z` |
| Manual labels `manual_labels_test.py`, from filing text only, **before** v3 was run | eb96480 |
| v3 run with the frozen hash | `validation/v3_test/` (`summary.json`, `comparison.csv`) |

## Result: **v3 does not pass. Development stops (§7.5). No v4 is started.**

| Condition (§7.4) | Required | Result | |
|---|---|---|---|
| 1. Status agreement | ≥ 76 of 79 | **74 / 79 = 93.7 %** | **fail** |
| 2. False `confirmed_raise` | 0 | 0 | pass |
| 3. Recall of real E events | ≥ 80 % (0 missed when < 5) | 2 / 2 = 100 % (Wilson 95 %: 34–100 %) | pass |
| 4. No look-ahead | 0 violations | re-run on filings before the signal day is identical; both raises accepted before `base_start` (32 and 55 sessions old) | pass |
| 5. Manual coverage by year | ≥ 80 % | 100 % in 2018, 2020, 2022, 2023, 2025; 90 % in 2019, 2021, 2024 | pass |

**Precision of `confirmed_raise`:** 2 / 2 = 100 % (Wilson 95 %: 34–100 %).

**Real E events in the third sample:** 2, Eli Lilly 2018 and Quanta Services 2023. Both were
found by v3.

**Recall on the development sets** (development data, not evidence): pilot 7 / 7, validation
1 / 1.

### Confusion matrix (rows = manual, columns = v3)
| manual \ v3 | raise | no_raise | no_suitable | unknown |
|---|---:|---:|---:|---:|
| confirmed_raise | **2** | 0 | 0 | 0 |
| confirmed_no_raise | 0 | **14** | 2 | 0 |
| confirmed_no_suitable_guidance | 0 | 1 | **55** | 2 |
| unknown | 0 | 0 | 0 | **3** |

**Manual label counts:** 2 raise, 16 no raise, 58 no suitable guidance, 3 unknown. All 3 unknowns
are issuers without a unique filer CIK: Agilent, Alphabet, Lennar.

## The 5 disagreements
| Case | Manual | v3 | Cause | Type |
|---|---|---|---|---|
| AVGO 2019 | no_suitable (point $24.5 B) | no_raise | The GAAP / reconciling / non-GAAP columns `$24,500M — $24,500M` were read as a range | false range |
| NOC 2022 | no_raise (initial sales ~36,200 – ~36,600, $ M) | no_suitable | Table values with `~` and an em dash, without `$`, were not parsed | missed range |
| TTWO FY26 | no_raise (range set on the `base_start` day) | no_suitable | Revenue in a GAAP reconciliation table, "Total net revenue $6,100 to $6,200" behind column headers, was not parsed | missed range |
| EXC 2022 | no_suitable (EPS only) | unknown | The year-end results were furnished under Item 7.01, not 2.02, so v3's rule "a 2.02 release within 120 days" fails | rule design |
| IT 2022 | no_suitable | unknown | "Raising our 2022 outlook for Revenue …" with no numbers in the packet; v3 abstains | label convention |

**Note on IT:** in the pilot, the same situation was labelled `unknown` (LKQ), so v3's answer may
be the better one. Labels are not edited after the run. Even counting IT as agreement, the score
is 75 / 79, still below 76.

## Further defect found while checking the 2 correct raises
**Eli Lilly 2018: the status and timing are right, but for the wrong numbers.**
- v3 read the release's "Prior | Revised" table and took the **Prior** column ($23.7–24.2 B) as
  the new range.
- It compared that with the April release's Prior column ($23.0–23.5 B).
- The real update is $23.7–24.2 B → $24.0–24.5 B.
- The result is right only because two lagged columns happened to rise together. A company that
  raised in April and only reaffirmed in July would be marked a raise. This is a **false-raise
  path that this sample did not trigger.**

## Why the gate failed (analysis, §7.5)
1. **Table layouts are the main weak point.** 3 of 5 errors, plus the Lilly defect, come from
   tables:
   - reconciliation columns read as a range (AVGO);
   - values without `$` or with `~` (NOC);
   - ranges behind column headers (TTWO);
   - "Prior | Revised" columns in the wrong order (LLY).
   Rules tuned on two development samples do not cover the next issuer's layout. Every new sample
   so far has shown a layout the earlier ones did not have.
2. **The two errors in v2 that the owner asked about are fixed:**
   - the "Revenue was $A and $B" actuals (META);
   - product-revenue phrasing and millions tables (VRTX and GILD in development).
   Zero false raises held on all three samples.
3. **Small event count.** The test has only 2 real E events. So recall (100 %) and precision
   (100 %) have 95 % intervals starting at 34 %. Even a passing gate would say little about the
   accuracy of raises.
4. **Rule edges:**
   - non-2.02 earnings filings (EXC);
   - stated raises without numbers in the packet (IT), where the pilot and test labels differ.

## Status
- E stays **INSUFFICIENT_DATA**.
- No full collection and no E backtest were run.
- Rules, criteria and the 20 % drawdown target are unchanged.
- Production, Paper, `TRADING=dry` and `main` are untouched. PR #25 stays Draft.
