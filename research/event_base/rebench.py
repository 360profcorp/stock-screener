"""Corrected index benchmarks (REVIEW_PLAN.md §5) and criteria 4-5 for the unchanged C / S books.

    python -m research.event_base.rebench --dataset DIR --run RUN_DIR

Reads SPY from the dataset and BIL from RUN_DIR/bil_prices.csv (the series used in v1). Writes
research/results/event_base/benchmarks_v2/<UTC>/ (write-once). C and S are not re-simulated.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from research.crisis import run as CR
from research.event_base import benchmarks as BM
from research.event_base import run as R
from research.sp1500 import run as RUN

ROOT = Path(__file__).resolve().parents[2]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--run", required=True)
    ap.add_argument("--out", default=str(ROOT / "research/results/event_base/benchmarks_v2"))
    a = ap.parse_args(argv)
    run_dir = Path(a.run)
    old = json.loads((run_dir / "results.json").read_text())
    frames, spy, _, sha = CR.load(a.dataset)
    spy.index = pd.to_datetime(spy.index).normalize()
    bil = pd.read_csv(run_dir / "bil_prices.csv")
    bil = bil.set_index(pd.to_datetime(bil[bil.columns[0]]).dt.normalize())
    cal = pd.DatetimeIndex(spy.index)
    windows = {k: (pd.Timestamp(v[0]), pd.Timestamp(v[1])) for k, v in old["windows"].items()}
    out = Path(a.out).resolve() / datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    root = ROOT if ROOT in out.parents else Path(a.out).resolve()
    man = {}
    W = lambda n, b: RUN.write_once(out / n, b, man, root)                      # noqa: E731
    res = dict(plan="research/event_base/REVIEW_PLAN.md §5", git=RUN._git_rev(), dataset_sha256=sha,
               books_from=str(run_dir), v1_recheck={}, v2={}, v2_pay_on_exdate={}, v2_price_only={}, diff_v2_minus_v1={})
    for w, (s0, s1) in windows.items():
        days = [d for d in cal if s0 <= d <= s1]
        for name in BM.rules(spy, days):
            px = {s: (spy if s == "SPY" else bil) for s in (("SPY", "BIL") if name == "SPY50_BIL50" else ("SPY",))}
            for ec in (2, 5):
                key = f"{name}|{w}|{ec}"
                v1 = R.etf_metrics(BM.etf_book(px, days, BM.rules(spy, days)[name], cost_bps=float(ec)))
                res["v1_recheck"][key] = abs(v1["cagr_pct"] - old["benchmarks"][key]["cagr_pct"]) < 1e-9
                b = BM.etf_book_v2(px, days, BM.rules(spy, days)[name], cost_bps=float(ec), full_cal=cal,
                                   sweep_all=(name == "SPY100"))
                m = R.etf_metrics(b)
                m["distributions_accrued_usd"] = b["totals"]["distributions"]
                m["receivable_end_usd"] = b["totals"]["receivable_end"]
                res["v2"][key] = m
                res["diff_v2_minus_v1"][key] = dict(cagr_pt=m["cagr_pct"] - old["benchmarks"][key]["cagr_pct"],
                                                    max_dd_pt=m["max_dd_pct"] - old["benchmarks"][key]["max_dd_pct"],
                                                    distributions_usd=m["distributions_accrued_usd"] -
                                                    old["benchmarks"][key]["distributions_usd"])
                if ec == 2:
                    b = BM.etf_book_v2(px, days, BM.rules(spy, days)[name], cost_bps=2.0, full_cal=cal,
                                       pay_mode="exdate", sweep_all=(name == "SPY100"))
                    res["v2_pay_on_exdate"][key] = R.etf_metrics(b)
                    b = BM.etf_book_v2(px, days, BM.rules(spy, days)[name], cost_bps=2.0, full_cal=cal,
                                       with_dist=False, sweep_all=(name == "SPY100"))
                    res["v2_price_only"][key] = R.etf_metrics(b)
                    if w == "full":
                        W(f"equity_bench_v2_{name}.csv", RUN.csv_bytes(b["curve"]))
    res["v1_recheck_all"] = all(res["v1_recheck"].values())
    res["decision_v2"] = {v: R.decide(old["books"], res["v2"], v, ref=("C" if v == "S" else None)) for v in ("C", "S")}
    res["decision_v1"] = {v: old["decision"][v]["verdict"] for v in ("C", "S")}
    W("results.json", json.dumps(res, indent=1, default=str))
    L = ["# Index benchmarks v2 (dividend fix) — report", "", f"git `{res['git']}`; books unchanged from `{run_dir}`.",
         f"v1 numbers reproduced before the fix: **{res['v1_recheck_all']}**.", "",
         "| benchmark | window | ETF bps | CAGR v1 % | CAGR v2 % | Δ pt | max DD v1 % | max DD v2 % | distributions v2 $ |",
         "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for k, m in res["v2"].items():
        n, w, ec = k.split("|")
        o = old["benchmarks"][k]
        L.append(f"| {n} | {w} | {ec} | {o['cagr_pct']:.2f} | {m['cagr_pct']:.2f} | {m['cagr_pct'] - o['cagr_pct']:+.2f} | "
                 f"{o['max_dd_pct']:.2f} | {m['max_dd_pct']:.2f} | {m['distributions_accrued_usd']:.0f} |")
    L += ["", "## Criteria 4–5 with v2 benchmarks (C and S books unchanged)", ""]
    for v, d in res["decision_v2"].items():
        L.append(f"- **{v}: {d['verdict']}** (v1: {res['decision_v1'][v]}) — {json.dumps(d['checks'])}; dominated by: {d['dominated_by']}")
    W("REPORT.md", "\n".join(L) + "\n")
    W("manifest.json", json.dumps(dict(files=dict(man)), indent=1))
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
