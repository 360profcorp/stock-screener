# Audit of PR #20 identifiers and 13F timing: plan and pass criteria

Written **before** the audit is run (2026-10-25). The owner asked for it before any further
experiment.

The audit code (`audit_ids.py`) is a **separate implementation**. It shares only the HTTP
fetcher with the build (`sec_data.py`), not the parsing or the mapping logic. It checks the
build against sources the build did **not** use:
- the SEC **Official Lists of Section 13(f) Securities**: quarterly CUSIP → issuer name;
- **EDGAR company submissions**: CIK → name and dated former names;
- **EDGAR filing index pages**: filing date and acceptance time of each sampled filing.

## A. Identifier mapping (CUSIP ↔ CIK ↔ ticker)
The build's mapping has no dates: one ticker gets every CUSIP ever seen under its symbol, or
under any symbol of its current CIK, over 2016–2026. Possible errors:
- **Ticker reuse:** a symbol moves to a different company.
- **Renames:** the company keeps its CIK and changes its symbol.
- **Reorganisations:** a new holding company, a new CIK or a new CUSIP.
- **Mergers and spin-offs.**
- **CUSIP reuse.**
- **Symbol conflicts:** one symbol claimed by two study tickers.

**Dated identity.** For each study ticker and calendar quarter, the issuer is the CIK that
filed most Forms 3/4/5 under that trading symbol. If there are none, the nearest quarter
within ±2 is used.

**A CUSIP counts for a ticker in a quarter only if one of these holds:**
1. **FTD:** within ±183 days of that quarter, the CUSIP traded under a symbol whose dated
   issuer CIK equals the ticker's dated issuer CIK; or
2. **Name:** the Official 13(f) List name of the CUSIP for that quarter matches a name of the
   ticker's issuer CIK valid then (EDGAR name or dated former name, or the Form 4 issuer
   name).

**Otherwise the CUSIP is:**
- **conflict:** it belongs to another identified issuer; or
- **unverified.**

**Outputs:**
- every ticker whose issuer CIK changes during 2016–2026, classified as same company
  (names linked) or different company (reuse);
- every CUSIP with more than one issuer;
- every symbol conflict;
- every mapping row whose symbol differs from the ticker.

**Impact.** Holders and F2 are recomputed with the dated mapping in two variants:
- **strict:** verified CUSIPs only;
- **lenient:** conflicts removed, unverified kept.

The audit then counts:
- changed F2 values on the PR #20 candidates;
- days whose BR same-day order changes.

**Pass A** if the strict variant changes **no** BR same-day order. Otherwise PR #20's books
are re-run with the corrected tables as a data correction (same pre-registration, nothing
else changed) before any paper book.

**Reproduction check.** The audit's own 13F holder count, using the build's static mapping,
must equal the build's `f13_breadth` for every row. A mismatch is a failure to be explained.

## B. BR uses only 13F data public before the signal
- **B1:** a sample of counted 13F-HR filings is checked against EDGAR index pages. The
  sample is about 20 per filing year, plus the 100 counted filings closest to the 45-day
  deadline. Required for every sampled filing:
  - EDGAR filing date = data-set `FILING_DATE`;
  - report period equal;
  - acceptance time before 00:00 of the quarter's `usable_from` day (deadline + 1).
- **B2:** the same check for Form 4: the 150 used purchases filed closest to their signal
  day, plus 150 at random. Acceptance must be before the signal day.
- **B3:** for every PR #20 candidate row, F2 is recomputed with the audit's own
  point-in-time selection. It must equal the stored F2, and the chosen quarter must have
  `usable_from` ≤ signal day.

**Pass B** only with **zero** violations in B1–B3.

A failed or unfinished check is reported as such. No sample is replaced after the results
are seen.
