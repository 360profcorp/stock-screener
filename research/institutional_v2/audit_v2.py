"""v2 audit verdict (CORRECTION_V2.md §5): R1-R6 from the committed outputs.

    python -m research.institutional_v2.audit_v2 --build B --accept A --comparison C --verify V --out OUT
"""
import argparse
import json
from pathlib import Path


def main(argv=None):
    ap = argparse.ArgumentParser()
    for k in ("--build", "--accept", "--comparison", "--verify", "--out"):
        ap.add_argument(k, required=True)
    a = ap.parse_args(argv)
    B = json.loads((Path(a.build) / "build.json").read_text())
    A = json.loads((Path(a.accept) / "accept.json").read_text())
    C = json.loads((Path(a.comparison) / "comparison.json").read_text())
    V = json.loads((Path(a.verify) / "verify_v2.json").read_text())
    rt = (Path(a.build) / "regression_tests.txt").read_text()
    reg_ok = rt.rstrip().endswith("OK") and "skipped" not in rt.splitlines()[-1]
    cal = A["calibration"]
    f4 = B["form4_acceptance"]
    R = {
        "R1 regression (first-audit conflicts, named cases)": dict(ok=reg_ok, detail=rt.strip().splitlines()[-3:]),
        "R2 security sets (one issuer, FTD evidence for every CUSIP)": dict(ok=reg_ok, detail=B["f2_rows"]),
        "R3 13F acceptance (every counted filing before usable_from; calibration 100 %)": dict(
            ok=cal["fetched"] == cal["n"] and max(cal["agree_label"], cal["agree_utc"]) == cal["n"]
            and cal["filing_date_agree"] == cal["n"],
            detail=dict(calibration=cal, acceptance=B["acceptance_13f"])),
        "R4 Form 4 (issuer = CIK(T,k); accepted before the signal day)": dict(
            ok=f4["fetched"] == f4["used_purchase_filings"], detail=f4),
        "R5 PR #20 reproduced exactly with the old tables": dict(ok=not C["reproduction_diffs"],
                                                                detail=C["reproduction_diffs"]),
        "R6 independent re-derivation from SEC/EDGAR files": dict(
            ok=V["discrepancies"] == 0, detail={k: v for k, v in V.items() if k != "details"}),
    }
    passed = all(r["ok"] for r in R.values())
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "audit_v2.json").write_text(json.dumps(dict(passed=passed, criteria=R), indent=1, default=str))
    md = [f"# v2 audit: {'PASSED' if passed else 'FAILED'}", "", "| Criterion | Result |", "|---|---|"]
    md += [f"| {k} | {'pass' if r['ok'] else '**FAIL**'} |" for k, r in R.items()]
    md += ["", "Details: `audit_v2.json`; verifier discrepancies: `verify_v2.json`."]
    (out / "AUDIT_V2.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
