# v2 audit: PASSED

| Criterion | Result |
|---|---|
| R1 regression (first-audit conflicts, named cases) | pass |
| R2 security sets (one issuer, FTD evidence for every CUSIP) | pass |
| R3 13F acceptance (every counted filing before usable_from; calibration 100 %) | pass |
| R4 Form 4 (issuer = CIK(T,k); accepted before the signal day) | pass |
| R5 PR #20 reproduced exactly with the old tables | pass |
| R6 independent re-derivation from SEC/EDGAR files | pass |

Details: `audit_v2.json`; verifier discrepancies: `verify_v2.json`.
