# Audit of PR #20 identifiers and 13F timing: result

- Plan: `AUDIT_PLAN.md`, committed before the run.
- Run: GitHub Actions 40194202338.
- Outputs: `research/results/institutional/audit/40194202338/`.

## Verdict: **failed (A and B)**. The PR #20 BR result is not valid as it stands.

Under the plan no shadow paper book is started. The mapping must be rebuilt, PR #20 re-run
as a data correction, and the audit repeated.

## What passed
| Check | Result |
|---|---|
| A0: own implementation reproduces the build's 13F holder counts | **27,790 / 27,790 rows identical**; `usable_from` = period + 46 days everywhere |
| B3: F2 recomputed point-in-time for every PR #20 candidate | 0 differences (40,537 rows); 0 quarters used before they were usable |
| B2: Form 4 acceptance time (EDGAR index), 276 used purchases | 0 filing-date mismatches; 0 accepted on or after the signal day |
| B1: 13F filing date and period vs EDGAR, 320 filings | 0 mismatches |

## What failed
### A. Identifier mapping has real errors
The build's mapping has **no dates**, and three things put CUSIPs on the wrong ticker:
1. It uses **today's** `company_tickers.json` CIK for a historical ticker.
2. It adds **every symbol ever typed** under that CIK in Forms 3/4/5.
3. It maps CUSIPs via fails-to-deliver symbols, again with no dates.

Confirmed examples. Each was an S&P 500 member during the affected quarters, and each
picked up another company's 13F holders:

| Ticker | Wrongly counted security | Cause |
|---|---|---|
| TT (Trane) | Ingersoll Rand Inc. (IR, 45687V106) | Trane's CIK used the symbol IR until 2020 |
| HWM (Howmet) | Alcoa Corp. (AA, 013872106) | Howmet = old Alcoa Inc. CIK |
| TFC / BBT (Truist / BB&T) | Berkshire Hills / Beacon Financial (084680107) | the symbol BBT was reused in 2025 |
| CPAY (Corpay) | Fidelity National Financial (FNF, 31620R303) | a symbol typo in a Form 4 |
| DASH (DoorDash) | Fabrinet (FN, G3323L100) | the same kind of typo |
| BAC | an Invesco municipal fund (VKI) | the same kind of typo |
| BNY / BK | the BNY symbol was a BlackRock municipal fund until 2026 | symbol reuse |

**Counts**
- **22 tickers** have proven conflicts in quarters when they were S&P members.
- The audit lists **66 CUSIPs** with several issuers.
- It lists **49 tickers** whose issuer CIK changed. **18** of them are reuse by a different
  company: APC, BBT, LB, STI, TE, SE, PX, HCP, FI, COR, WTW, DOC, AXON, MRNA, Q and others.
- **1.3 %** of Form 4 purchases (201 / 15,454) are attributed to an issuer other than the
  ticker's dated issuer.

**Impact**
- The automatic correction (strict: verified CUSIPs only) changes the BR same-day order on
  **471 of 1,588** Breakout days, and the top 3 on **101** days.
- The lenient variant (proven conflicts removed only) changes it on 349 and 85 days.

**The audit's own automatic correction is also not reliable enough to use as the corrected
data:**
- It judges each quarter separately, so a ticker can lose its CUSIP in Q−1 and regain it in
  Q. Example: BNY on 2026-06-30, where F2 becomes +200 %.
- "Dominant Form 4 issuer per symbol" fails where a symbol is shared, as with BNY.
- Legacy CUSIPs of the same company (GE before its reverse split, FleetCor's CUSIP for CPAY,
  predecessor DuPont, Dow, Chubb) are marked "unverified".

### B. One 13F filing was accepted after its filing date
- Accession 0000033250-19-000002 has a filing date of 2019-05-15, the deadline day, but
  EDGAR accepted it on **2019-05-16 09:22**. Its filing date was backdated (EDGAR can grant
  filing-date adjustments).
- Under the plan's criterion (accepted before 00:00 of `usable_from`) this is a violation.
- Against the real decision time it was public: the signal is taken at the 16:00 close of
  2019-05-16, and the filing was accepted at 09:22.
- Still, a filing-date rule cannot exclude such cases in general. The data sets carry no
  acceptance time, so every counted filing must be checked.

## Required before any shadow book
1. **Mapping v2**, dated and consistent:
   - CUSIPs keyed by the **symbol trading at the time** (fails-to-deliver records), anchored
     to the PIT member;
   - the **same CUSIP set for Q and Q−1** of each breadth row;
   - no symbols collected from Form 4 typing;
   - a reviewed list for the ambiguous tickers.
2. **Acceptance time for every counted 13F filing** (EDGAR submissions API). A filing
   accepted after its filing date is dropped.
3. **Re-run PR #20 unchanged** on the corrected tables (a data correction), then **repeat
   this audit**.
