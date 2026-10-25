"""Old (PR #20) vs v2 side by side (CORRECTION_V2.md §4).

    python -m research.institutional_v2.compare --pr20 PR20_RUN --repro REPRO_RUN --v2 V2_RUN \
        --sens SENS_RUN --build BUILD_COMMIT_DIR --out OUT_DIR
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

KEYS = ("return_pct", "cagr_pct", "max_dd_pct", "profit_factor", "trades")
ORD = {"RS": ["rs"], "INS": ["F1", "rs"], "BR": ["F2", "rs"]}


def J(d):
    return json.loads((Path(d) / "results.json").read_text())


def same(x, y, tol):
    if isinstance(x, dict):
        return isinstance(y, dict) and x.keys() == y.keys() and all(same(x[k], y[k], tol) for k in x)
    if isinstance(x, (list, tuple)):
        return isinstance(y, (list, tuple)) and len(x) == len(y) and all(same(a, b, tol) for a, b in zip(x, y))
    if isinstance(x, float) and isinstance(y, (int, float)):
        return abs(x - y) <= tol
    return x == y


def reproduction(a, b):
    """Every number of PR #20 that depends on data and code must be reproduced: books, RND,
    decisions, coverage and PIT check exactly; the IC (a mean of daily rank correlations) is
    compared to 1e-12 because floating-point summation order changes its last digits."""
    diffs, notes = [], []
    for st in a["strategies"]:
        x, y = a["strategies"][st], b["strategies"][st]
        for part in ("books", "random", "decision", "coverage", "pit_check", "undetermined_by_coverage"):
            if json.dumps(x[part], sort_keys=True, default=str) != json.dumps(y[part], sort_keys=True, default=str):
                diffs.append(f"{st}.{part}")
        if not same(x["ic"], y["ic"], 1e-12):
            diffs.append(f"{st}.ic")
        elif json.dumps(x["ic"], sort_keys=True) != json.dumps(y["ic"], sort_keys=True):
            notes.append(f"{st}.ic equal to 1e-12 (last floating-point digits differ)")
    return diffs, notes


def day_orders(F, how):
    d = F.copy()
    if how == "IR":
        d["r1"] = d.groupby("signal_date")["F1"].rank(pct=True)
        d["r2"] = d.groupby("signal_date")["F2"].rank(pct=True)
        d["k"] = (d["r1"] + d["r2"]) / 2
        cols = ["k", "rs"]
    else:
        cols = ORD[how]
    d = d.sort_values(["signal_date"] + cols + ["ticker"], ascending=[True] + [False] * len(cols) + [True],
                      kind="stable")
    return {k: list(g["ticker"]) for k, g in d.groupby("signal_date")}


def rank_changes(Fo, Fn, how):
    a, b = day_orders(Fo, how), day_orders(Fn, how)
    days = sorted(set(a) & set(b))
    ch = sum(a[d] != b[d] for d in days)
    top = sum(a[d][:3] != b[d][:3] for d in days)
    return dict(days=len(days), order_changed=int(ch), top3_changed=int(top),
                order_changed_pct=round(100 * ch / len(days), 1) if days else None)


def composition(do, dn, st, how):
    po, pn = Path(do) / f"trades_{st}_{how}.csv", Path(dn) / f"trades_{st}_{how}.csv"
    if not (po.exists() and pn.exists()):
        return None
    k = lambda f: set(zip(f["ticker"], f["entry_date"].astype(str)))       # noqa: E731
    a, b = k(pd.read_csv(po)), k(pd.read_csv(pn))
    return dict(old=len(a), v2=len(b), common=len(a & b), only_old=len(a - b), only_v2=len(b - a),
                common_pct_of_old=round(100 * len(a & b) / len(a), 1) if a else None)


def main(argv=None):
    ap = argparse.ArgumentParser()
    for k in ("--pr20", "--repro", "--v2", "--sens", "--build", "--out"):
        ap.add_argument(k, required=True)
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    P, R, V, Sn = J(a.pr20), J(a.repro), J(a.v2), J(a.sens)
    d_, n_ = reproduction(P, R)
    res = dict(reproduction_diffs=d_, reproduction_notes=n_, strategies={})
    SS = pd.read_csv(Path(a.build) / "security_sets.csv.gz", dtype=str)
    md = ["# Institutional v2 vs PR #20 (old)", "",
          f"Reproduction of PR #20 with the old tables: "
          f"{'**exact**' if not res['reproduction_diffs'] else '**DIFFERS: ' + ', '.join(res['reproduction_diffs']) + '**'}"
          + (f" ({'; '.join(n_)})" if n_ else ""), ""]
    for st in ("breakout", "retest"):
        o, n, s = P["strategies"][st], V["strategies"][st], Sn["strategies"][st]
        rows = []
        for key in o["books"]:
            how, w, bps = key.split("|")
            rows.append(dict(order=how, window=w, bps=bps, **{f"old_{k}": o["books"][key][k] for k in KEYS},
                             **{f"v2_{k}": n["books"][key][k] for k in KEYS},
                             **{f"sens_{k}": s["books"][key][k] for k in KEYS}))
        Bk = pd.DataFrame(rows)
        Bk.to_csv(out / f"books_{st}.csv", index=False)
        Fo = pd.read_csv(Path(a.pr20) / f"features_{st}.csv", parse_dates=["signal_date"])
        Fn = pd.read_csv(Path(a.v2) / f"features_{st}.csv", parse_dates=["signal_date"])
        rc = {h: rank_changes(Fo, Fn, h) for h in ("RS", "INS", "BR", "IR")}
        comp = {h: composition(a.repro, a.v2, st, h) for h in ("RS", "INS", "BR", "IR")}
        # excluded identifiers: candidates whose F2 is missing in v2 but present in PR #20
        m = Fo[["ticker", "signal_date", "has_13f", "F2", "F1"]].merge(
            Fn[["ticker", "signal_date", "has_13f", "F2", "F1"]], on=["ticker", "signal_date"], suffixes=("_old", "_v2"))
        m["year"] = m["signal_date"].dt.year
        lost = m[m["has_13f_old"] & ~m["has_13f_v2"]]
        exc = dict(candidates=int(len(m)), f2_lost=int(len(lost)),
                   f2_lost_by_year=lost.groupby("year").size().astype(int).to_dict(),
                   f2_changed=int((np.abs(m["F2_old"] - m["F2_v2"]) > 1e-12).sum()),
                   f1_changed=int((m["F1_old"] != m["F1_v2"]).sum()))
        res["strategies"][st] = dict(decision_old=o["decision"], decision_v2=n["decision"],
                                     decision_sensitivity=s["decision"],
                                     undetermined_v2=n["undetermined_by_coverage"],
                                     random_old=o["random"], random_v2=n["random"], random_sens=s["random"],
                                     ic_old=o["ic"], ic_v2=n["ic"], coverage_old=o["coverage"], coverage_v2=n["coverage"],
                                     rank_changes=rc, composition=comp, excluded=exc, pit_v2=n["pit_check"])
        md += [f"## {st.capitalize()}{' (research Breakout: next-open entry, not the bot)' if st == 'breakout' else ''}", "",
               f"Decision: old {o['decision']} → **v2 {n['decision']}** (sensitivity, excluded rows at old values: {s['decision']})", "",
               "| Order | Window | bps | Return old → v2 | CAGR old → v2 | Max DD old → v2 | PF old → v2 | Trades old → v2 |",
               "|---|---|---|---|---|---|---|---|"]
        for r in Bk.itertuples():
            md.append(f"| {r.order} | {r.window} | {r.bps} | {r.old_return_pct:+.1f} → {r.v2_return_pct:+.1f} | "
                      f"{r.old_cagr_pct:+.1f} → {r.v2_cagr_pct:+.1f} | {r.old_max_dd_pct:.1f} → {r.v2_max_dd_pct:.1f} | "
                      f"{r.old_profit_factor:.2f} → {r.v2_profit_factor:.2f} | {r.old_trades} → {r.v2_trades} |")
        md += ["", "RND (200 random orders, 10 bps) p50 / p80 / p95:"]
        for w in ("development", "holdout"):
            x, y = o["random"][w], n["random"][w]
            md.append(f"- {w}: old {x['p50']:.1f} / {x['p80']:.1f} / {x['p95']:.1f}; v2 {y['p50']:.1f} / {y['p80']:.1f} / {y['p95']:.1f}")
        md += ["", "| Order | Days with a changed same-day order | Top-3 changed | Trades common old/v2 (full, 10 bps) |",
               "|---|---|---|---|"]
        for h in ("RS", "INS", "BR", "IR"):
            c = comp[h] or {}
            md.append(f"| {h} | {rc[h]['order_changed']} of {rc[h]['days']} ({rc[h]['order_changed_pct']} %) | "
                      f"{rc[h]['top3_changed']} | {c.get('common', '—')} of {c.get('old', '—')} old / {c.get('v2', '—')} v2 |")
        md += ["", f"Excluded identifiers: F2 lost for {exc['f2_lost']} of {exc['candidates']} candidates "
               f"(by year {exc['f2_lost_by_year']}); F2 changed for {exc['f2_changed']}, F1 for {exc['f1_changed']}.", "",
               "| Year | 13F usable old → v2 | F1 > 0 old → v2 | Form 4 data old → v2 |", "|---|---|---|---|"]
        for y in sorted(o["coverage"], key=int):
            co, cn = o["coverage"][y], n["coverage"].get(y, {})
            md.append(f"| {y} | {co['f13_usable']} → {cn.get('f13_usable')} | {co['f1_positive']} → {cn.get('f1_positive')} | "
                      f"{co['form4_any_12m']} → {cn.get('form4_any_12m')} |")
        md += ["", f"IC (F1 / F2 / RS) old: {o['ic']['F1'].get('mean_ic', 0):+.3f} / {o['ic']['F2'].get('mean_ic', 0):+.3f} / "
               f"{o['ic']['rs'].get('mean_ic', 0):+.3f}; v2: {n['ic']['F1'].get('mean_ic', 0):+.3f} / "
               f"{n['ic']['F2'].get('mean_ic', 0):+.3f} / {n['ic']['rs'].get('mean_ic', 0):+.3f}", ""]
    md += ["## Security sets by status (all study tickers × quarters)", "",
           json.dumps(SS["status"].value_counts().to_dict()),
           "", "Member rows only: " + json.dumps(SS[SS["member_in_use_window"] == "True"]["status"].value_counts().to_dict())]
    (out / "comparison.json").write_text(json.dumps(res, indent=1, default=str))
    (out / "COMPARISON_V2.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    return 0 if not res["reproduction_diffs"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
