# Institutional Intelligence v2: data correction (rules fixed before the corrected data)

**Approved by the owner on 2026-10-25.** Written before any v2 table is built.

**Why.** The first audit (`research/institutional/AUDIT_RESULT.md`) found that the PR #20
mapping attributed other companies' securities to S&P 500 tickers.

**Scope.** This is a **data correction only**. These stay exactly as in
`research/institutional/PREREG_INSTITUTIONAL.md`:
- the ratings (RS, INS, BR, IR, RND);
- the signals and strategy;
- the portfolio limits and costs;
- the windows;
- the decision rule.

**Not touched:** PR #20, its branch and every earlier result.

Research only. No paper book, schedule or real trade is enabled before the v2 audit passes.
Production, Retest Paper, Trading, positions, stops and `TRADING=dry` are not changed.
Nothing is merged into `main`.

## 1. Point-in-time security identification (F2, 13F)
No modern identifier (today's `company_tickers.json`, today's CIK) is used to attribute a
historical security.

**Symbol records.** The SEC fails-to-deliver files give dated (settlement date, CUSIP,
trading symbol). Symbols are normalised as before (`.` and `/` become `-`).

**Breadth row (ticker T, report quarter Q, previous quarter Q−1)**
- **Window:** W = [end of Q−1 − 30 days, end of Q + 166 days]. It runs from the Q−1
  holdings date to the last day the row can be used (usable_from + 120 days).
- **Security set S:** every 9-character CUSIP recorded under symbol T in W.
- **The same set S is used for both quarters.** holders_Q and holders_Q−1 count the filers,
  among those present in both quarters, that hold any CUSIP of S.

**Row status**

| Status | Condition | Row |
|---|---|---|
| `ok` | S is not empty; one issuer; no CUSIP of S is new after Q−1 | computed |
| `no_symbol_record` | S is empty | none (F2 missing → 0, as pre-registered) |
| `several_issuers` | S contains CUSIPs with different 6-character issuer prefixes. Their names (Official 13(f) List, nearest to Q, else the FTD description) are kept as evidence but **cannot merge them** (see change log) | **registry**, none |
| `new_cusip` | some CUSIP of S first appears (FTD under any symbol, or 13F holdings) after the end of Q−1, so at Q−1 the security had another identifier (renaming, merger, spin-off, CUSIP change) | **registry**, none |

Cases in the registry are **never assigned automatically**. They stay excluded until a
reviewed entry is added with its sources. No such entry is made in this run.

## 2. Point-in-time issuer identification (F1, Form 4)
For ticker T and calendar quarter k:
- **Candidates:** the issuer CIKs of Forms 3/4/5 filed under trading symbol T in quarters
  k−2 … k+2.
- **Security name:** the Official 13(f) List names of the CUSIPs recorded under T in FTD
  within [start of k − 90 days, end of k + 90 days].
- **Confirmed:** a candidate whose names valid around k match the security name. Names
  valid around k are the EDGAR name and former names with their dates, plus the Form 4
  issuer names in k−1 … k+1.
- **Assignment:** CIK(T, k) is the **unique** confirmed candidate. None, or several →
  **registry**, and no attribution for that quarter.

A purchase filing (issuer CIK c, filing date fd) belongs to T only if
c = CIK(T, quarter of fd). The same rule applies to the Form 4 coverage counts. The typed
trading symbol alone never attributes a filing.

## 3. Public-availability rule (unchanged, now enforced with acceptance times)
The rule of PREREG §3 / AUDIT_PLAN B is applied as fixed, not changed:
- **13F:** a filing counts for quarter Q only if all of these hold:
  - it is an original 13F-HR with period Q;
  - its data-set filing date is ≤ Q + 45 days;
  - its **EDGAR acceptance timestamp is before 00:00 ET of usable_from (Q + 46 days)**.
  
  The acceptance timestamp is checked for **every** such filing, through the EDGAR
  submissions data of each filer. A filing without a retrievable timestamp is excluded.
  The filers present in both quarters are counted from the same accepted filings.
  Timestamps are calibrated against EDGAR filing index pages on a random sample of 200,
  which must agree 100 %.
- **Form 4:** a purchase can be used on signal day d only if:
  - its filing date is before d; and
  - its EDGAR acceptance timestamp is before 00:00 ET of d.
  
  This is checked for every purchase used in any F1 value. An unverifiable purchase is
  excluded from that value.

## 4. Re-run and comparison
- `research/institutional/run.py` is used unchanged in logic. It only additionally writes
  its trade lists.
- **First,** the PR #20 tables are re-run. The result must reproduce PR #20's
  `results.json` **exactly**.
- **Then** the v2 tables are run. The decision is the pre-registered rule, unchanged.

**Side by side, old vs v2, per strategy and order:**
- Return, CAGR, max DD, profit factor, trades;
- the days on which the same-day rating changes, and the top-3 changes;
- portfolio composition: trades common to the old and v2 books.

**Separately:**
- coverage by year (v2 vs old);
- the candidates whose F2/F1 is missing because of a registry exclusion;
- a **sensitivity** book in which excluded rows keep their old value. This only measures
  dependence on the excluded identifiers and is never a decision input.

## 5. v2 audit: pass criteria (all required)
| # | Criterion |
|---|---|
| R1 | Regression: no (ticker, CUSIP) conflict found by the first audit appears in v2. Tests name TT, HWM, BBT/TFC, CPAY, DASH, BAC, BNY/BK and the other conflicts, and each must pass on the real v2 tables |
| R2 | Every `ok` breadth row satisfies §1. Every CUSIP has an FTD record under T in W, and each row's evidence is listed |
| R3 | Every counted 13F filing has an acceptance timestamp before usable_from 00:00 ET; the calibration sample agrees 100 % |
| R4 | Every used Form 4 purchase: issuer = CIK(T, k), accepted before 00:00 ET of the signal day |
| R5 | The PR #20 re-run with the old tables reproduces PR #20 exactly |
| R6 | `verify_v2.py` re-derives a random sample of 300 decisions directly from SEC/EDGAR files (FTD lines, 13(f) list lines, EDGAR index pages): 0 discrepancies |

**If any criterion fails, the work stops with an exact report of the blockers. No parameter
is adjusted.**

`verify_v2.py` and its instructions are the package for Muse's independent re-check.

## Change log
- **2026-10-25**, before any v2 data was seen (the sources download was still running; no
  v2 table existed):
  - **Change:** `several_issuers` is now decided by the CUSIP issuer prefix alone.
  - **Before:** different prefixes were accepted as one issuer when the names matched.
  - **Why:** writing the regression cases showed that name matching would merge different
    companies with similar names:
    - Ingersoll-Rand plc (later Trane) and Ingersoll Rand Inc. (formerly Gardner Denver),
      both under the symbol IR;
    - Arconic Inc. (now Howmet) and Arconic Corp., both under ARNC.
  - **Effect:** stricter. A genuine re-incorporation with a new issuer prefix now also goes to
    the registry and is not assigned automatically, as the owner required for disputed cases.
  - **Unchanged:** names are still used to confirm issuer CIKs (§2).
