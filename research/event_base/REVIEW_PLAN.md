# E pilot — manual source review and benchmark dividend fix (plan)

Written on 2026-10-25, before any review label or corrected benchmark number exists. It follows
the owner's task of 2026-10-25 21:47.

**Unchanged:**
- C and S are closed negative results of v1. Their rules and parameters are not touched.
- The E signal rule, the success criteria (PLAN.md §7), the 80 % coverage requirement and the
  20 % drawdown target are as in PLAN.md.
- Production, Paper, Trading, positions and `TRADING=dry`. No paid APIs. The PR stays Draft.

## 1. Fixed sample
The same 80 pilot cases: `research/results/event_base/events/2026-10-26T012220Z/sample.csv`.
- No case is added, dropped or replaced.
- No price, return or chart of any case is opened during the review. The review packets contain
  only filing text, filing times and the case dates (base start, signal date).

## 2. Sources
**Saved primary documents:** artifact `event-docs-40253859449`, the EX-99 exhibits of every
Item 2.02 8-K, identified by SHA256 in `source_registry.csv`.

**Added for this review**, fetched from SEC EDGAR with the same identified User-Agent:
1. **Item 2.02 8-Ks without an EX-99 exhibit** (the 4 `release_not_retrieved` cases): their
   filing index and every document in the filing.
2. **Possible intermediate updates:** 8-Ks with Item 7.01 or 8.01 from `base_start − 400 days` to
   the signal date, and their EX-99 exhibits. These can carry an update that cancels an older
   raise.

Earnings-call statements that were never filed are outside the record. If guidance exists only
there, the case can be at most "no suitable guidance in the filed record". This limit is
reported, not hidden.

**Review packet per case:** every relevant filing (accession, form, items, acceptance time ET,
URL, SHA256) with the text windows around revenue and outlook words. Each document also carries
a count of its outlook / guidance words, so a document with no guidance language is visible as
such.

## 3. Status per case (manual, from the quoted primary text)
| Status | Meaning |
|---|---|
| `confirmed_raise` | Same issuer, **full fiscal year** (not a quarter), USD, same units. The new range has `low >= old low`, `high >= old high` and a higher midpoint than the most recent earlier full-year range for the same year. The raise was accepted before `base_start` (calendar day, never the same day), is ≤ 60 sessions old on the signal date, and its fiscal year is not finished. No later filed update before the signal (neutral, lower, withdrawn or not comparable) cancels it. |
| `confirmed_no_raise` | A full-year USD revenue range for the current fiscal year is in force on the signal date, and the facts show the rule is not met: initial guidance, a reaffirmation, a cut, a narrowing with a lower top end, a raise made after `base_start`, a raise older than 60 sessions, or a raise cancelled by a later update. |
| `confirmed_no_suitable_guidance` | The filed record for the window (`base_start − 400 days` … signal) was fully retrieved and contains **no full-year USD revenue range** for the current fiscal year. For example: the company gives only EPS, growth-percentage or point guidance, only quarterly ranges, or no outlook at all. The sub-type is recorded, e.g. `growth_pct_only`, `eps_only`, `quarterly_only`, `point_only`, `none`. |
| `unknown` | Anything that cannot be settled from the record: a missing document, the period or units unclear, the issuer unclear, or a conflicting text. |

**Recorded for every case:**
- the quoted excerpts with the accession and URL of the documents used;
- old and new ranges, fiscal-year label and acceptance times;
- the reason, and for `unknown` the cause: `extraction` (the text is there but unclear),
  `incomplete_history` (documents missing) or `other`.

**Regression example.** Cadence (CDNS) 2020 must come out as quarterly ranges, not a full-year
raise. The automated status `raise` was wrong. The case is judged on its full-year range, if any.

**Coverage** = (`confirmed_raise` + `confirmed_no_raise` + `confirmed_no_suitable_guidance`) /
80, by year 2018–2025. This is the "known event status" of PLAN.md §4.
`confirmed_no_suitable_guidance` belongs to S-covered as a known "no event".

**Labelling discipline.** The labels are written once into
`research/results/event_base/review/<UTC>/labels.csv` and are not edited after any extractor
comparison. A corrected label goes in a new dated file that keeps the old one.

## 4. What happens next (gates, fixed now)
**A. Reason for missing coverage.** If manual coverage is below 80 % in any year, the report
states the dominant cause per year: extraction error, incomplete publication history, or
genuinely absent guidance. No expansion follows.

**B. Extraction workable.** Only if manual coverage is ≥ 80 % in every year can an automated
extractor be used to expand. It may be revised using these 80 manual labels. It is then accepted
only on a **new, independently drawn validation sample**:
- 80 S candidates, 10 per year 2018–2025, seed 20261026, excluding the pilot cases;
- the sample is labelled manually before the extractor's output on it is opened.

**Acceptance on that sample:**
- status agreement ≥ 95 %;
- **0 false `confirmed_raise`**;
- the validation sample's manual coverage also ≥ 80 % in every year.

**C. Only after B passes:**
- collect events for all S candidates;
- recheck coverage ≥ 80 % in every full year;
- then run the initial E vs S-covered vs the index alternatives with the unchanged rules and
  criteria.

## 5. Index benchmark dividend fix
**Faults in v1** (`benchmarks.etf_book`):
1. Entitlement used the shares held **after** that day's open trades. Shares bought at the open of
   an ex-date were wrongly paid; shares sold at that open were wrongly not paid.
2. Distributions became cash on the ex-date and were reinvested at that close, before the money
   is actually paid.
3. Each distribution was reinvested with its own whole-share floor. The remainders were left as
   idle cash and never reinvested.

**Corrected rule (v2)**
- **Entitlement** = shares held at the close **before** the ex-date.
- **On the ex-date** the distribution is **accrued**: a receivable that counts in equity.
- **On the pay date** it becomes cash. Pay dates are not in the Yahoo data, so a fixed assumption
  is used:
  - SPY: the last session of the month after the ex-date month (SPY's usual schedule);
  - BIL: 5 sessions after the ex-date.
  - A sensitivity run uses pay = ex-date.
- **Reinvestment:** received cash goes into that ETF sleeve's distribution balance. At the
  **next session's open** the whole accumulated balance buys whole shares of the same ETF. The
  remainder stays in the balance and is added to by the next payment.
  - SPY 100 %: all idle cash, including the remainder of the first purchase, is that balance.
- **Monthly rebalance and timing switches** size from cash + market value (receivables
  excluded, they are not yet money). The balances then merge into ordinary cash.
- **SPY timing:** when out of the market, received SPY distributions stay in cash.

**Recomputed:** only the benchmarks (4 rules × 3 windows × 2 and 5 bps, plus price-only) and
criteria 4 and 5 for C and S, using the unchanged book metrics of run 2026-10-26T011603Z.
- The v1 numbers are kept.
- A difference between v1 and v2 is reported per benchmark.
- C and S are not re-simulated.

**Not changed:** the trading books credit a dividend as cash on its ex-date. That is a smaller
version of fault 2: about $280 of dividends over the full C book at 10 bps.

## 6. Addendum (2026-10-25, before any validation label or extractor-v2 output)
Owner's instruction: continue with extractor v2 and the new validation sample; if accuracy and
coverage pass, run E against the controls. Sequence fixed now:

1. **Validation sample:** `research/results/event_base/validation/sample_seed20261026.csv`.
   - 80 S candidates, 10 per year 2018–2025, seed 20261026, pilot cases excluded.
   - Committed before its packets are fetched.
2. **Packets** for that sample are built with the same text-window code, plus one fix: when an
   Item 2.02 8-K has no EX-99, the first listed `.htm` document is used as the primary.
3. **Manual labels** of the validation sample are committed (`manual_labels_val.py`) **before**
   extractor v2 is run on that sample.
4. **Extractor v2** (`extract_v2.py`):
   - deterministic rules applied to the same packet text windows;
   - developed only on the 80 pilot cases;
   - frozen (committed) before it sees the validation packets.
5. **Acceptance:**
   - status agreement ≥ 95 % (≥ 76 of 80) over the four statuses;
   - 0 cases where v2 says `confirmed_raise` and the manual label does not;
   - validation manual coverage ≥ 80 % in every year 2018–2025.
6. **If accepted:**
   - packets for all S candidates of the full window, then v2 on them;
   - S-candidate coverage ≥ 80 % in every full year 2018–2025;
   - then `run.py --events` builds E (`confirmed_raise`) and S-covered (all known statuses),
     with the unchanged execution model, costs, windows and criteria of PLAN.md §7.
   - Otherwise E stays INSUFFICIENT_DATA, and the failing condition is reported.
