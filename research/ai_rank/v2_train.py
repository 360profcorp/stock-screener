"""AI ranking v2 — training and gate evaluation exactly as PREREG v2.1 (§3, §4, §5a).

    python -m research.ai_rank.v2_train --pr5 DIR --v2 DIR [--out ...]

Order enforced in code:
  1. grid (§3) fit on train, chosen on validation by mean daily rank correlation (§4),
     portfolio return only as a tie-break;
  2. walk-forward 2023-2025 inside development with the chosen config;
  3. gate (§4) evaluated and WRITTEN to gate.json;
  4. only then the historical window (§5a, NOT independent) is computed once.
Deciding run: retest, 26 features (no earn_within_5). Sensitivity run (+earn_within_5) and the
secondary all-long-setups run (rank_rs_all) are reported but can never pass the gate.
Nothing is frozen and nothing touches the bot.
"""
import argparse
import gzip
import hashlib
import json
import pickle
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from research.ai_rank import pipeline as P
from research.ai_rank import v2_build as B
from research.sp1500 import engine as E
from research.sp1500 import run as RUN

ROOT = Path(__file__).resolve().parents[2]
KEY = ["ticker", "signal_date", "strategy"]
WF_YEARS = (2023, 2024, 2025)
N_RANDOM = 50
N_BOOT = 2000
SEED = 20261020


# ---------------------------------------------------------------- metrics
def daily_ic(df, score, target=P.TARGET, min_n=3):
    """Per-day Spearman correlation between score and realised R (rows with a label;
    each (ticker, day, strategy) once; days with >= min_n labelled signals)."""
    d = df.assign(_s=np.asarray(score, dtype=float)).dropna(subset=[target, "_s"])
    out = {}
    for day, g in d.groupby("signal_date"):
        if len(g) >= min_n and g["_s"].nunique() > 1 and g[target].nunique() > 1:
            out[day] = g["_s"].rank().corr(g[target].rank())
    return pd.Series(out, dtype=float)


def boot_ci(ics, n=N_BOOT, seed=SEED, q=(0.05, 0.95)):
    v = ics.dropna().to_numpy()
    if len(v) < 2:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    means = rng.choice(v, size=(n, len(v)), replace=True).mean(axis=1)
    return tuple(float(x) for x in np.quantile(means, q))


# ---------------------------------------------------------------- data
def load_inputs(pr5_dir, v2_dir):
    lab, frames, spy, src = P.load(pr5_dir)
    v2 = pd.read_csv(next(Path(v2_dir).rglob("dataset_v2.csv.gz")), low_memory=False)
    v2_sha = hashlib.sha256(next(Path(v2_dir).rglob("dataset_v2.csv.gz")).read_bytes()).hexdigest()
    for c in ("signal_date", "label_end", "exit_date", "entry_date"):
        v2[c] = pd.to_datetime(v2[c], errors="coerce")
    base = P.long_pool(lab, "pit500", tuple(P.LONGS))[KEY + ["close", "level", "stop_base",
                                                            "bars_held"]]
    pool = v2.merge(base, on=KEY, how="left", validate="one_to_one")
    assert pool["stop_base"].notna().all(), "v2 rows not found in the PR #5 pool"
    tick = sorted(set(lab.loc[lab["group"] == "sp500", "ticker"]) | set(pool["ticker"]))
    data = {t: E.arrays(frames[t]) for t in tick if t in frames and len(frames[t]) > 262}
    cal = pd.DatetimeIndex(spy.index)
    return pool, data, cal, dict(pr5=src, v2_sha256=v2_sha)


def features_for(kind, deciding):
    if kind == "deciding":
        return list(deciding)
    if kind == "sensitivity":
        return list(deciding) + B.SENSITIVITY_ONLY
    f = [("rank_rs_all" if c == "rank_rs" else c) for c in deciding]
    return f + [f"is_{m}" for m in P.LONGS]


# ---------------------------------------------------------------- one experiment
def experiment(kind, pool, data, cal, deciding, v0, t0, log):
    strategies = ("retest",) if kind in ("deciding", "sensitivity") else tuple(P.LONGS)
    d = pool[pool["strategy"].isin(strategies)].copy()
    for m in P.LONGS:
        d[f"is_{m}"] = (d["strategy"] == m).astype(float)
    fc = features_for(kind, deciding)
    trades = P.trades_for(d, data)
    tk = d.rename(columns={"strategy": "mode"})[["ticker", "signal_date", "mode"] + fc]
    trades = trades.drop(columns=[c for c in fc if c in trades]).merge(
        tk, on=["ticker", "signal_date", "mode"], how="left", validate="many_to_one")
    labelled = d[(d["trade_status"] == "closed") & d[P.TARGET].notna()]
    train = labelled[labelled["split"] == "train"]
    val = labelled[labelled["split"] == "validation"]
    dev = labelled[labelled["split"].isin(["train", "validation"])]
    v_end = cal[cal < t0][-1]
    in_val = (trades["date"] >= v0) & (trades["date"] < t0)
    res = dict(kind=kind, strategies=list(strategies), features=fc,
               counts=dict(signals=len(d), labelled=len(labelled), train=len(train),
                           validation=len(val), dev=len(dev),
                           nonoverlap_train=int(E.non_overlapping(d[d["split"] == "train"]).sum()),
                           nonoverlap_validation=int(E.non_overlapping(
                               d[d["split"] == "validation"]).sum()),
                           trades_validation=int(in_val.sum())))
    # 1) grid on validation (selection by mean daily IC; portfolio as tie-break)
    rs_v = P.summary(*P.replay(trades[in_val], data, v0, v_end))
    rnd_v = [P.summary(*P.replay(trades[in_val], data, v0, v_end, seed=SEED + k))["return_pct"]
             for k in range(N_RANDOM)]
    grid = []
    for mk, params in P.GRID:
        p_val, _ = P.fit_predict(mk, params, train[fc], train[P.TARGET], val[fc])
        ic = daily_ic(val, p_val)
        p_tr, _ = P.fit_predict(mk, params, train[fc], train[P.TARGET], trades.loc[in_val, fc])
        S = P.summary(*P.replay(trades[in_val], data, v0, v_end, score=p_tr))
        grid.append(dict(model=mk, params=params, val_ic_mean=float(ic.mean()) if len(ic) else np.nan,
                         val_ic_days=int(len(ic)), val_return_pct=S["return_pct"],
                         val_max_dd_pct=S["max_dd_pct"]))
    best = max(grid, key=lambda g: (np.nan_to_num(g["val_ic_mean"], nan=-9), g["val_return_pct"]))
    log(f"{kind}: chosen {best['model']} {best['params']} val IC {best['val_ic_mean']:.4f}")
    res["validation"] = dict(rs_first=rs_v, random_return_pct=dict(
        median=float(np.median(rnd_v)), p10=float(np.percentile(rnd_v, 10)),
        p90=float(np.percentile(rnd_v, 90))), grid=grid, chosen=best)
    # 2) walk-forward inside development with the chosen config
    wf, wf_ics = [], []
    for y in WF_YEARS:
        ys = pd.Timestamp(f"{y}-01-01")
        ye = min(pd.Timestamp(f"{y}-12-31"), v_end)
        trn = labelled[(labelled["signal_date"] < ys) & (labelled["label_end"] < ys)]
        scr = labelled[(labelled["signal_date"] >= ys) & (labelled["signal_date"] <= ye)]
        win = (trades["date"] >= ys) & (trades["date"] <= ye)
        if len(trn) < 500 or not len(scr):
            wf.append(dict(year=y, skipped=True, train_labels=len(trn)))
            continue
        p_s, _ = P.fit_predict(best["model"], best["params"], trn[fc], trn[P.TARGET], scr[fc])
        ic = daily_ic(scr, p_s)
        wf_ics.append(ic)
        p_t, _ = P.fit_predict(best["model"], best["params"], trn[fc], trn[P.TARGET],
                               trades.loc[win, fc])
        a = P.summary(*P.replay(trades[win], data, ys, ye))
        b = P.summary(*P.replay(trades[win], data, ys, ye, score=p_t))
        wf.append(dict(year=y, skipped=False, train_labels=len(trn), scored=len(scr),
                       nonoverlap_scored=int(E.non_overlapping(
                           d[(d["signal_date"] >= ys) & (d["signal_date"] <= ye)]).sum()),
                       ic_mean=float(ic.mean()) if len(ic) else np.nan, ic_days=int(len(ic)),
                       rs_first_return_pct=a["return_pct"], model_return_pct=b["return_pct"],
                       rs_first_dd=a["max_dd_pct"], model_dd=b["max_dd_pct"]))
    pooled = pd.concat(wf_ics) if wf_ics else pd.Series(dtype=float)
    res["walk_forward"] = wf
    res["pooled_wf_ic"] = dict(mean=float(pooled.mean()) if len(pooled) else np.nan,
                               days=int(len(pooled)), ci90=boot_ci(pooled),
                               definition="daily ICs of the out-of-sample walk-forward years "
                                          "2023-2025, each day once; bootstrap by day")
    # 3) gate (PREREG §4) — only the deciding run is eligible
    yrs = [w for w in wf if not w.get("skipped")]
    g1 = bool(yrs) and all(w["ic_mean"] > 0 for w in yrs) and best["val_ic_mean"] > 0
    lo, _ = res["pooled_wf_ic"]["ci90"]
    g2 = bool(res["pooled_wf_ic"]["mean"] >= 0.03 and lo > 0)
    worst = min((w["model_return_pct"] - w["rs_first_return_pct"] for w in yrs), default=-np.inf)
    g3 = bool(worst >= -2.0 and best["val_return_pct"] > res["validation"]["random_return_pct"]["median"])
    res["gate"] = dict(eligible=kind == "deciding",
                       g1_ic_positive_every_wf_year_and_validation=g1,
                       g2_pooled_ic_ge_0_03_and_ci_above_0=g2,
                       g3_portfolio_vs_rs_first_and_random=g3,
                       worst_wf_return_gap_pp=float(worst),
                       passed=bool(kind == "deciding" and g1 and g2 and g3))
    res["_trades"], res["_dev"], res["_fc"], res["_d"] = trades, dev, fc, d
    return res


def historical_window(res, data, cal, t0):
    """PREREG §5a: computed ONCE, after gate.json has been written. Not independent."""
    trades, dev, fc, d = res["_trades"], res["_dev"], res["_fc"], res["_d"]
    best = res["validation"]["chosen"]
    end = cal[-1]
    tw = trades["date"] >= t0
    lab_t = d[(d["split"].isin(["test", "embargo"])) & (d["trade_status"] == "closed") &
              d[P.TARGET].notna()]
    p_t, _ = P.fit_predict(best["model"], best["params"], dev[fc], dev[P.TARGET], trades.loc[tw, fc])
    p_l, _ = P.fit_predict(best["model"], best["params"], dev[fc], dev[P.TARGET], lab_t[fc])
    ic = daily_ic(lab_t, p_l)
    a = P.summary(*P.replay(trades[tw], data, t0, end))
    b = P.summary(*P.replay(trades[tw], data, t0, end, score=p_t))
    rnd = [P.summary(*P.replay(trades[tw], data, t0, end, seed=SEED + k))["return_pct"]
           for k in range(N_RANDOM)]
    return dict(note="NOT an independent test (window used for strategy choice); "
                     "computed once after the gate decision; cannot change it",
                rs_first=a, model=b, ic_mean=float(ic.mean()) if len(ic) else np.nan,
                ic_days=int(len(ic)), ic_ci90=boot_ci(ic),
                random_return_pct=dict(median=float(np.median(rnd)),
                                       p10=float(np.percentile(rnd, 10)),
                                       p90=float(np.percentile(rnd, 90))))


def clean(r):
    return {k: v for k, v in r.items() if not k.startswith("_")}


def main(argv=None):
    frozen = ROOT / "research/results/ai_rank/v2_train/FREEZE/FREEZE.json"
    if frozen.exists():
        raise SystemExit("AI ranking v2 is FROZEN (see FREEZE.json): no further training")
    ap = argparse.ArgumentParser()
    ap.add_argument("--pr5", required=True)
    ap.add_argument("--v2", required=True)
    ap.add_argument("--out", default=str(ROOT / "research/results/ai_rank/v2_train"))
    a = ap.parse_args(argv)
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%MZ")
    out = Path(a.out) / run_id
    man = {}
    pool, data, cal, src = load_inputs(a.pr5, a.v2)
    rep = json.loads((ROOT / "research/results/ai_rank/v2_build/2026-10-20T2346Z/"
                            "build_report.json").read_text())
    assert rep["files_sha256"]["2026-10-20T2346Z/dataset_v2.csv.gz"] == src["v2_sha256"], \
        "v2 dataset is not the audited rebuild (sha256 mismatch)"
    deciding = P.MODEL_FEATURES + [f for f in B.V2_FEATURES
                                   if f != "sess_since_earn" or rep.get("earnings", {}).get(
                                       "group_kept", True)]
    v0, t0 = B.V0, B.T0
    log = print
    runs = {k: experiment(k, pool, data, cal, deciding, v0, t0, log)
            for k in ("deciding", "sensitivity", "secondary_all_longs")}
    gate = dict(prereg="v2.1", decided_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                inputs=src, deciding_features=deciding,
                deciding=clean(runs["deciding"])["gate"],
                deciding_chosen=runs["deciding"]["validation"]["chosen"],
                verdict=("PASSED — candidate for the shadow stage (owner decides; ChatGPT "
                         "review before any freeze)") if runs["deciding"]["gate"]["passed"]
                else "FAILED — v2 is reported as failed and RS-first stays",
                sensitivity_note="sensitivity and secondary runs can never pass the gate")
    RUN.write_once(out / "gate.json", json.dumps(gate, indent=2, default=str), man, Path(a.out))
    log(f"GATE WRITTEN: {gate['verdict']}")
    hist = historical_window(runs["deciding"], data, cal, t0)        # §5a, after the gate
    results = {k: clean(v) for k, v in runs.items()}
    RUN.write_once(out / "results.json", json.dumps(results, indent=2, default=str), man,
                   Path(a.out))
    RUN.write_once(out / "historical_window.json", json.dumps(hist, indent=2, default=str), man,
                   Path(a.out))
    RUN.write_once(out / "REPORT.md", report(gate, results, hist), man, Path(a.out))
    RUN.write_once(out / "manifest.json", json.dumps(dict(run_id=run_id, git=RUN._git_rev(),
                                                          files=man, inputs=src), indent=2),
                   {}, Path(a.out))
    return 0


def report(gate, results, hist):
    L = ["# AI ranking v2.1 — training and gate (PREREG v2.1)", "",
         f"**Gate verdict: {gate['verdict']}** (written to gate.json at {gate['decided_at']}, "
         "before the historical window was computed).", ""]
    for k, r in results.items():
        L += [f"## {k}", "", f"Features ({len(r['features'])}): {', '.join(r['features'])}", "",
              f"Counts: {r['counts']}", "", "Validation grid (selection = mean daily IC):", ""]
        L += [RUN.md_table(pd.DataFrame([{**{kk: vv for kk, vv in g.items() if kk != 'params'},
                                          "params": json.dumps(g["params"])} for g in r["validation"]["grid"]]), "{:.4f}")]
        L += [f"Chosen: {r['validation']['chosen']['model']} {r['validation']['chosen']['params']}",
              f"Validation RS-first return {r['validation']['rs_first']['return_pct']:.2f} %, "
              f"random median {r['validation']['random_return_pct']['median']:.2f} %", "",
              "Walk-forward:", "", RUN.md_table(pd.DataFrame(r["walk_forward"]), "{:.4f}"),
              f"Pooled walk-forward IC: {r['pooled_wf_ic']}", "", f"Gate: {r['gate']}", ""]
    L += ["## Historical window 2025-12-30 → 2026-10-14 (NOT independent, computed once after the gate)",
          "", "```json", json.dumps(hist, indent=1, default=str), "```", ""]
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
