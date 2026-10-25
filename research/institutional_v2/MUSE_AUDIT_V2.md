# Independent re-audit package for Muse: Institutional v2

Everything below can be checked against the original SEC/EDGAR files. Nothing depends on
trusting the v2 code.

## What to read first
1. `CORRECTION_V2.md`: the rules, written before any v2 table, with the change log.
2. `research/results/institutional_v2/build/<run>/`, the real outputs:

| File | Content | How to check it at the source |
|---|---|---|
| `security_sets.csv.gz` | every (ticker, quarter) security set: status, CUSIPs, 13(f) List names, FTD evidence (first and last record dates, count) | download the fails-to-deliver files named in the registry (`https://www.sec.gov/files/data/fails-deliver-data/cnsfailsYYYYMM[a|b].zip`); grep the symbol and the CUSIP |
| `registry_f2.csv` | disputed security sets (`several_issuers`, `new_cusip`): sources and the status *excluded; not assigned automatically* | same files; the Official 13(f) List PDFs (`https://www.sec.gov/files/investment/13flistYYYYqN.pdf`) |
| `cik_map.csv.gz`, `registry_cik.csv` | issuer CIK per (ticker, quarter) with its candidates; disputed ones are excluded | EDGAR company pages (`https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=...`) |
| `acceptance_13f_excluded_late.csv` | 13F-HR filings whose EDGAR acceptance is on or after usable_from (backdated filing dates); excluded | the EDGAR index page of each accession (the "Accepted" field) |
| `acceptance_13f_no_timestamp.csv.gz` | filings without a retrievable timestamp; excluded | the same |
| `f13_counted_sample.csv` | random 2,000 counted filings with acceptance time and ok flag | the same |
| `form4_acceptance.csv` | every Form 4 purchase used by an F1 value: acceptance time, first signal day using it, URL | the same |
| `regression_tests.txt` | the regression tests run on the real outputs | `research/institutional_v2/test_regression_real.py` |

3. `research/results/institutional_v2/accept/<run>/calibration.csv`: 200 acceptance
   timestamps from the EDGAR submissions API compared with the EDGAR index pages
   (Eastern time).

## Re-run the verifier yourself
`verify_v2.py` is stand-alone. It uses only pandas and requests and does not import the v2
code.

```
pip install pandas requests        # and poppler-utils for pdftotext
python research/institutional_v2/verify_v2.py \
    --build research/results/institutional_v2/build/<run> --out /tmp/v2verify --seed <any number>
```

It re-reads **all** fails-to-deliver files and re-derives a random sample:
- the CUSIP sets of 150 security-set decisions;
- the issuer-prefix rule;
- every 13(f) List name those rows cite;
- 100 counted 13F filings (acceptance vs usable_from);
- 50 used Form 4 purchases (issuer CIK on the EDGAR index page, acceptance before the
  signal day).

A different `--seed` draws a fresh sample. The exit code is 0 only with no discrepancy.

## Suggested manual spot checks
- The regression cases TT, HWM, BBT/TFC, CPAY, DASH, BAC, BNY/BK in `security_sets.csv.gz`
  and `cik_map.csv.gz`.
- Five random rows of `registry_f2.csv`: do the cited FTD files really show two issuer
  prefixes under the symbol, or a CUSIP first seen after Q−1?
- The excluded late 13F filings: is EDGAR "Accepted" really after the deadline + 1 day?
- **Known conservative losses**, reported and not fixed after seeing the data:
  - 13(f) List abbreviations ("M & T BK", "GLOBAL PMTS", "CF INDS HLDGS", "WABTEC")
    prevent automatic issuer confirmation for MTB, GPN, CF, WAB and FMC.
  - REITs whose operating partnership also files Form 4 under the same symbol (DLR) have
    two confirmed issuers.
  - All of these are excluded, so F1 is missing there. Resolving them needs reviewed
    registry entries with sources, which this run does not make.
