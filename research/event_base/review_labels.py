"""Corrected registry of the 80 E pilot cases from the manual labels (REVIEW_PLAN.md §3).

    python -m research.event_base.review_labels --packets DIR --out DIR

Timing of every confirmed_raise is re-checked mechanically from EDGAR acceptance times:
accepted calendar day < base_start, and <= 60 SPY sessions from the usable day (acceptance
day + 1) to the signal. A raise failing either check becomes confirmed_no_raise.
No prices or returns are read (the SPY session calendar comes from a dates-only column).
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from research.event_base.manual_labels_v1 import LABELS
from research.sp1500 import run as RUN

ROOT = Path(__file__).resolve().parents[2]
CAL_CSV = ROOT / "research/results/event_base/runs/2026-10-26T011603Z/equity_C_full_10bps.csv"
KNOWN = ("confirmed_raise", "confirmed_no_raise", "confirmed_no_suitable_guidance")


def build(packets, labels, sessions):
    lab = {l[0]: l for l in labels}
    cal = pd.DatetimeIndex(sessions)
    rows = []
    for p in packets:
        case, status, sub, fy, old, new, acc, reason, ev = lab[p["case"]]
        acc_t = next((pd.Timestamp(f["accepted_et"]) for f in p["filings"] if f["accession"] == acc), None)
        url = next((d.get("url") for f in p["filings"] if f["accession"] == acc for d in f["documents"]), None)
        r = dict(case=case, ticker=p["ticker"], issuer=p.get("issuer"), cik=p["cik"], base_start=p["base_start"],
                 signal_date=p["signal_date"], status=status, subtype=sub, fiscal_year=fy,
                 old_low_bn=old[0] if old else None, old_high_bn=old[1] if old else None,
                 new_low_bn=new[0] if new else None, new_high_bn=new[1] if new else None,
                 evidence_accession=acc, evidence_accepted_et=str(acc_t) if acc_t is not None else None,
                 evidence_url=url, reason=reason, evidence=ev, automated_status=p["auto_status"],
                 automated_reason=p["auto_reason"], filings_in_packet=len(p["filings"]),
                 filings_with_error=sum(1 for f in p["filings"] if f.get("error") or any(d.get("error") for d in f["documents"])))
        if status == "confirmed_raise":
            if acc_t is None:
                raise ValueError(f"case {case}: evidence accession not in packet")
            usable = acc_t.normalize() + pd.Timedelta(days=1)
            age = int(((cal >= usable) & (cal <= pd.Timestamp(p["signal_date"]))).sum())
            before = acc_t.normalize() < pd.Timestamp(p["base_start"])
            r.update(age_sessions=age, accepted_before_base_start=bool(before))
            if not (before and age <= 60):
                r.update(status="confirmed_no_raise", subtype="raise_timing_failed",
                         reason=r["reason"] + f" | timing: before_base_start={before}, age={age}")
        rows.append(r)
    return pd.DataFrame(rows)


def coverage(df):
    df = df.copy()
    df["year"] = pd.to_datetime(df["signal_date"]).dt.year
    by = {}
    for y, g in df.groupby("year"):
        k = int(g["status"].isin(KNOWN).sum())
        by[int(y)] = dict(cases=int(len(g)), known=k, coverage_pct=round(100 * k / len(g), 1),
                          raise_=int((g["status"] == "confirmed_raise").sum()),
                          no_raise=int((g["status"] == "confirmed_no_raise").sum()),
                          no_suitable_guidance=int((g["status"] == "confirmed_no_suitable_guidance").sum()),
                          unknown=int((g["status"] == "unknown").sum()))
    return by


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--packets", required=True)
    ap.add_argument("--out", default=str(ROOT / "research/results/event_base/review_labels"))
    a = ap.parse_args(argv)
    packets = json.loads((Path(a.packets) / "packets.json").read_text())
    if any(l[1] is None for l in LABELS):
        raise SystemExit("labels incomplete")
    sessions = pd.to_datetime(pd.read_csv(CAL_CSV, usecols=["date"])["date"])
    df = build(packets, LABELS, sessions)
    by = coverage(df)
    out = Path(a.out).resolve() / datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    root = ROOT if ROOT in out.parents else Path(a.out).resolve()
    man = {}
    W = lambda n, b: RUN.write_once(out / n, b, man, root)                      # noqa: E731
    auto_known = df["automated_status"].isin(["raise", "known_no_raise"])
    res = dict(packets=str(a.packets), labels="research/event_base/manual_labels_v1.py", git=RUN._git_rev(),
               status_counts=df["status"].value_counts().to_dict(),
               subtype_counts_no_suitable=df.loc[df["status"] == "confirmed_no_suitable_guidance", "subtype"].value_counts().to_dict(),
               coverage_by_year=by, all_years_ge_80=all(v["coverage_pct"] >= 80 for v in by.values()),
               automated_vs_manual=pd.crosstab(df["automated_status"], df["status"]).to_dict(),
               automated_raise_correct_for_right_reason=0,
               automated_known=int(auto_known.sum()))
    W("labels.csv", RUN.csv_bytes(df))
    W("summary.json", json.dumps(res, indent=1, default=str))
    W("manifest.json", json.dumps(dict(files=dict(man)), indent=1))
    print(json.dumps(res, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
