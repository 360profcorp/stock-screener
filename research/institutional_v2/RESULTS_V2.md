# Institutional Intelligence v2: corrected data, results

- **Rules:** `CORRECTION_V2.md`, fixed before any v2 table. Its change log has two stricter
  changes, both made before v2 tables existed.
- **Ratings, strategy, limits, costs and decision rule:** unchanged from
  `research/institutional/PREREG_INSTITUTIONAL.md`.
- **PR #20** and every earlier result are untouched.
- **Research only.** No shadow book, schedule or real trade is enabled.

## Runs
| Step | GitHub run | Output |
|---|---|---|
| SEC sources | 40196473096 | `research/results/institutional_v2/sources/40196473096/` |
| EDGAR acceptance times (236,450 13F-HR filings) | 40197339936 | `.../accept/40197339936/` |
| PIT mapping, registry, tables, regression tests | 40201750843 | `.../build/40201750843/` |
| Re-run: reproduction, v2, sensitivity | 40202217650 | `.../runs/{repro,v2,sens}/`, `.../comparison/40202217650/COMPARISON_V2.md` |
| v2 audit (R1–R6) | 40220841134 | `.../audit/40220841134/AUDIT_V2.md` |

## v2 audit: **passed** (R1–R6)
- **R1/R2:** the regression tests pass on the real tables. They cover:
  - every member-quarter conflict found by the first audit;
  - TT, HWM, BBT/TFC, CPAY, DASH, BAC and BNY/BK, by CUSIP, 13(f) List name and issuer CIK;
  - one issuer prefix and FTD evidence for every CUSIP of every `ok` set.
- **R3:** acceptance times
  - **236,430** filings carry an EDGAR acceptance time. The calibration sample matched the
    EDGAR index pages **200 / 200**.
  - **23** filings with a backdated filing date (accepted after usable_from) are excluded.
  - **20** filings without a retrievable timestamp are excluded.
- **R4:** all **1,102** Form 4 purchases used by F1 were checked: 0 accepted on or after
  their signal day, 0 unverifiable.
- **R5:** PR #20 re-run on the old tables reproduces books, RND, decisions, coverage and the
  PIT check **exactly**. Only the IC differs, in the 16th decimal (floating-point summation
  order), so it is compared to 1e-12.
- **R6:** `verify_v2.py`, which does not import the v2 code, re-derived from the raw SEC/EDGAR
  files:
  - 150 security-set decisions;
  - 171 13(f) List names;
  - 100 13F acceptance checks;
  - 50 Form 4 checks.
  
  It found **0 discrepancies**. The first audit run (40220530239) failed on 50 Form 4 checks
  because of a **bug in the verifier**: it read the issuer CIK on EDGAR index pages as empty.
  After the parsing fix (commit "robust issuer parsing") the re-run found 0.

## Result
| Strategy | INS | BR | IR |
|---|---|---|---|
| Research Breakout (next-open entry, **not** the bot) | not improved (unchanged) | **improves → not improved** | not improved (unchanged) |
| Retest | not improved | not improved | not improved |

**Breakout BR, old → v2 (10 bps unless stated):**

| Window | Return | Max DD | PF |
|---|---|---|---|
| full | +85.8 → +65.7 % | −29.3 → −40.5 % | 1.22 → 1.19 |
| development | +13.2 → +9.2 % | | |
| holdout | +73.8 → +63.8 % | | |
| holdout, 25 bps | **+2.5 → −8.6 %**, vs RS −7.3 % | | |

The rule now fails on the 25 bps holdout condition. It still beats RS and the RND 80th
percentile at 10 bps in both windows.

**Sensitivity:** with the excluded identifiers given back their PR #20 values, BR
"improves" again. The PR #20 pass therefore depended partly on ambiguous identifiers. The
sensitivity is not a decision input.

**How much the data changed**
- **Same-day order:** the BR order changed on 43 % of Breakout days, and the top 3 on 162
  days.
- **Composition:** 86 % of the old BR trades are still in the v2 book (621 of 720).
- **Coverage:**
  - the 13F row is usable for 95–100 % of candidates in every year, so the result is not
    "undetermined";
  - Form 4 data covers 92–98 %, against 97–100 % before. The issuer-name rule is
    conservative; see the registry.

## Registry (disputed cases, excluded and not assigned)
- `registry_f2.csv`: **450** security sets, **247** of them in index-member windows across
  94 tickers. Statuses:
  - `new_cusip`: renamings, spin-offs and CUSIP changes such as HWM 2020, TFC 2019, CPAY 2024
    and GE 2021;
  - `several_issuers`: reused symbols such as IR 2020, ARNC 2020 and BNY 2025–26.
- `registry_cik.csv`: **852** issuer quarters. Known conservative losses:
  - 13(f) List abbreviations: MTB, GPN, CF, WAB, FMC;
  - REITs with an operating partnership: DLR.
- Resolving any of them needs a reviewed entry with sources. None was made.

## Next
- **Independent re-audit by Muse:** see `MUSE_AUDIT_V2.md`.
- **Shadow books:** stay off. Under the pre-registered rule, the corrected BR no longer
  qualifies. Whether to run a forward shadow comparison anyway is the owner's decision.
