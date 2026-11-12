"""Gate of REVIEW_PLAN.md §7.4 for extractor v3 on a labelled packet set.

    python -m research.event_base.eval_v3 --packets DIR --labels MODULE[:ATTR] --out DIR

Reports: confusion matrix (manual x v3), agreement, false raises, precision and recall of
confirmed_raise (Wilson 95 %), manual coverage by year, and a mechanical look-ahead audit:
  (a) v3 re-run on packets truncated to filings accepted before the signal day gives identical output;
  (b) every v3 raise: evidence accepted on a calendar day < base_start and <= 60 sessions old at the signal.
No prices or returns are read (the session calendar is a dates-only column).
"""
import argparse
import copy
import hashlib
import importlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from research.event_base import extract_v3 as X

ROOT = Path(__file__).resolve().parents[2]
CAL_CSV = ROOT / "research/results/event_base/runs/2026-10-26T011603Z/equity_C_full_10bps.csv"
RAISE = "confirmed_raise"
KNOWN = ("confirmed_raise", "confirmed_no_raise", "confirmed_no_suitable_guidance")
STATUSES = KNOWN + ("unknown",)


def wilson(k, n, z=1.96):
    if n == 0:
        return (None, None)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(c - h, 3), round(c + h, 3))


def load_labels(spec):
    mod, _, attr = spec.partition(":")
    return getattr(importlib.import_module(mod), attr or "LABELS")


def evaluate(packets, labels, sessions):
    v3 = X.run(packets, sessions)
    lab = pd.DataFrame([dict(case=l[0], manual=l[1], manual_subtype=l[2]) for l in labels])
    m = v3.merge(lab, on="case", how="outer", validate="one_to_one")
    if m["manual"].isna().any() or m["status"].isna().any():
        raise SystemExit("labels and packets do not cover the same cases")
    conf = pd.crosstab(m["manual"], m["status"]).reindex(index=list(STATUSES), columns=list(STATUSES), fill_value=0)
    agree = int((m["status"] == m["manual"]).sum())
    tp = int(((m["status"] == RAISE) & (m["manual"] == RAISE)).sum())
    fp = int(((m["status"] == RAISE) & (m["manual"] != RAISE)).sum())
    fn = int(((m["status"] != RAISE) & (m["manual"] == RAISE)).sum())
    n_real = tp + fn
    allowed_missed = math.floor(0.2 * n_real)
    # look-ahead (a): truncate packets to filings accepted before the signal day
    trunc = copy.deepcopy(packets)
    for p in trunc:
        p["filings"] = [f for f in p["filings"] if pd.Timestamp(f["accepted_et"]).normalize() < pd.Timestamp(p["signal_date"])]
    v3t = X.run(trunc, sessions)
    cols = [c for c in v3.columns]
    same = v3[cols].astype(str).equals(v3t[cols].astype(str))
    # look-ahead (b): raises re-timed independently
    cal = pd.DatetimeIndex(sessions)
    bad_raise = []
    for _, r in m[m["status"] == RAISE].iterrows():
        p = next(q for q in packets if q["case"] == r["case"])
        f = next((f for f in p["filings"] if f["accession"] == r["accession"]), None)
        if f is None:
            bad_raise.append((int(r["case"]), "evidence not in packet"))
            continue
        acc = pd.Timestamp(f["accepted_et"])
        age = int(((cal >= acc.normalize() + pd.Timedelta(days=1)) & (cal <= pd.Timestamp(p["signal_date"]))).sum())
        if not (acc.normalize() < pd.Timestamp(p["base_start"]) and age <= 60):
            bad_raise.append((int(r["case"]), f"accepted {acc}, base_start {p['base_start']}, age {age}"))
    # manual coverage by year
    m["year"] = pd.to_datetime(m["signal_date"]).dt.year
    cov = {}
    for y, g in m.groupby("year"):
        k = int(g["manual"].isin(KNOWN).sum())
        cov[int(y)] = dict(cases=int(len(g)), known=k, coverage_pct=round(100 * k / len(g), 1))
    gate = dict(
        agreement_ge_76=agree >= 76 if len(m) == 80 else agree / len(m) >= 0.95,
        zero_false_raise=fp == 0,
        recall_ok=(fn <= allowed_missed),
        no_lookahead=bool(same) and not bad_raise,
        coverage_ge_80_every_year=all(v["coverage_pct"] >= 80 for v in cov.values()),
    )
    res = dict(version=X.VERSION, cases=int(len(m)), agree=agree, agree_pct=round(100 * agree / len(m), 1),
               confusion_manual_rows_v3_cols={i: {c: int(conf.loc[i, c]) for c in conf.columns} for i in conf.index},
               real_E_events_manual=n_real, v3_raises=tp + fp, true_raises=tp, false_raises=fp, missed_raises=fn,
               precision=(round(tp / (tp + fp), 3) if tp + fp else None), precision_ci95=wilson(tp, tp + fp),
               recall=(round(tp / n_real, 3) if n_real else None), recall_ci95=wilson(tp, n_real),
               recall_allowed_missed=allowed_missed,
               lookahead=dict(truncated_rerun_identical=bool(same), raise_timing_violations=bad_raise),
               manual_coverage_by_year=cov, gate=gate, passed=all(gate.values()))
    return m, res


def main(argv=None):
    from research.sp1500 import run as RUN
    ap = argparse.ArgumentParser()
    ap.add_argument("--packets", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    packets = json.loads((Path(a.packets) / "packets.json").read_text())
    sessions = pd.to_datetime(pd.read_csv(CAL_CSV, usecols=["date"])["date"])
    m, res = evaluate(packets, load_labels(a.labels), sessions)
    res.update(packets=str(a.packets), labels=a.labels, git=RUN._git_rev(),
               extract_v3_sha256=hashlib.sha256((ROOT / "research/event_base/extract_v3.py").read_bytes()).hexdigest())
    out = Path(a.out).resolve() / datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    root = ROOT if ROOT in out.parents else Path(a.out).resolve()
    man = {}
    W = lambda n, b: RUN.write_once(out / n, b, man, root)                      # noqa: E731
    W("comparison.csv", RUN.csv_bytes(m))
    W("summary.json", json.dumps(res, indent=1, default=str))
    W("manifest.json", json.dumps(dict(files=dict(man)), indent=1))
    print(json.dumps(res, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
