"""Breakout + MA200: Turnover & Selection Audit (PREREG_TURNOVER_SELECTION.md). Exploratory.

    python -m research.turnover_selection.run --dataset DIR [--workers 4] [--n 200]

M and B are exactly PR #23's (research.breakout_ma200.run). Every book is a full sequential
portfolio replay; no trade is removed from an already computed P&L.
"""
import argparse
import hashlib
import json
import subprocess
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import portfolio_bt as pf
from research.breakout_ma200 import run as R
from research.crisis import run as CR

ROOT = Path(__file__).resolve().parents[2]
PR23 = ROOT / "research/results/breakout_ma200/runs/2026-10-25T205752Z/results.json"
COSTS = (10, 25)
CAL_SEEDS = range(1001, 1021)
CTX = "research/results/breakout_causes/runs/2026-10-25T204323Z (branch research/breakout-causes)"


# =====================================================================
# books
# =====================================================================
def metrics(curve, ex, m, spy):
    met = CR.metrics(curve, ex, m, spy)
    eq = curve["equity"]
    years = (curve["date"].iloc[-1] - curve["date"].iloc[0]).days / 365.25
    notional = float((ex["shares"] * (ex["entry"] + ex["exit"])).sum()) if len(ex) else 0.0
    notional += sum(p["shares"] * p["entry"] for p in m["open_positions"])
    met.update(turnover_per_year=float(notional / eq.mean() / years),
               invested_pct=float(100 * ((curve["equity"] - curve["cash"]) / curve["equity"]).mean()))
    return met


def replay(tr, data, s0, s1, bps, decisions=False):
    return pf.replay(tr, data, start=s0, end=s1, open_at_end="mark", cost_bps=float(bps),
                     record_decisions=decisions, **CR.CFG)


def b0_book(M, B):
    """B0: B's exit dates (slot occupancy), but every closed runner gets M's day-20 price."""
    out = B.copy()
    m = out["runner"].astype(bool) & (out["status"] == "closed")
    out.loc[m, "exit"] = M.loc[m, "exit"].values
    return out


def extend_all(M, data):
    """Every M time exit with B's trailing exit and no +2 R condition (R2's pool)."""
    ext = {}
    for k, row in M.iterrows():
        upd = R.runner_exit(row, data[row["ticker"]], min_r=-1e9)
        if upd:
            ext[k] = upd
    return ext


def apply_ext(M, ext, keys):
    out = M.copy()
    for k in keys:
        for c, v in ext[k].items():
            out.at[k, c] = v
    return out


def shuffle_day(M, seed):
    rng = np.random.default_rng(seed)
    t = M.assign(_k=rng.random(len(M)))
    return t.sort_values(["date", "_k"], kind="stable").drop(columns="_k").reset_index(drop=True)


# =====================================================================
# parallel random controls
# =====================================================================
G = {}
KEEP = ("return_pct", "cagr_pct", "max_dd_pct", "profit_factor", "trades", "expectancy_r", "turnover_per_year",
        "invested_pct")


def _task(t):
    kind, seed, w, bps, q = t
    M, data, spy = G["M"], G["data"], G["spy"]
    s0, s1 = G["windows"][w]
    if kind == "R1":
        rng = np.random.default_rng(seed)
        tr = M[rng.random(len(M)) >= q]
    elif kind == "R2":
        rng = np.random.default_rng(seed)
        keys = list(G["ext"])
        pick = rng.choice(len(keys), size=G["n_runners"], replace=False)
        tr = apply_ext(M, G["ext"], [keys[i] for i in pick])
    else:
        tr = shuffle_day(M, seed)
    curve, ex, m = replay(tr, data, s0, s1, bps)
    met = metrics(curve, ex, m, spy)
    return dict(kind=kind, seed=seed, window=w, bps=bps, **{k: met[k] for k in KEEP})


def run_tasks(tasks, workers):
    if workers > 1:
        with ProcessPoolExecutor(workers) as p:
            return list(p.map(_task, tasks, chunksize=2))
    return [_task(t) for t in tasks]


def calibrate_q(target, workers, lo=0.0, hi=0.99, tol=0.001):
    log = []
    while hi - lo > tol:
        mid = round((lo + hi) / 2, 6)
        r = run_tasks([("R1", s, "full", 10, mid) for s in CAL_SEEDS], workers)
        mt = float(np.mean([x["trades"] for x in r]))
        log.append(dict(q=mid, mean_trades=mt))
        if mt > target:
            lo = mid
        else:
            hi = mid
    q = round((lo + hi) / 2, 4)
    return q, log


# =====================================================================
# analyses
# =====================================================================
def split_b_vs_m(exM, mM, exB, mB, curveM, curveB, bps, initial=10000.):
    f = bps / 1e4
    k = ["ticker", "entry_date"]
    a = exM.assign(entry_date=pd.to_datetime(exM["entry_date"]), exit_date=pd.to_datetime(exM["exit_date"]))
    b = exB.assign(entry_date=pd.to_datetime(exB["entry_date"]), exit_date=pd.to_datetime(exB["exit_date"]))
    j = b.merge(a, on=k, how="outer", suffixes=("_b", "_m"), indicator=True)
    both = j[j["_merge"] == "both"]
    same = both[both["exit_date_b"] == both["exit_date_m"]]
    diff = both[both["exit_date_b"] != both["exit_date_m"]]
    ob, om = j[j["_merge"] == "left_only"], j[j["_merge"] == "right_only"]
    openv = lambda m: sum(p["shares"] * (p["mark"] - p["entry"] * (1 + f)) for p in m["open_positions"])  # noqa: E731
    rows = {"identical trades (sizing only)": (float((same["net_pnl_b"] - same["net_pnl_m"]).sum()),
                                               float((same["net_r_b"] - same["net_r_m"]).sum()), len(same)),
            "same entry, different exit (runners)": (float((diff["net_pnl_b"] - diff["net_pnl_m"]).sum()),
                                                     float((diff["net_r_b"] - diff["net_r_m"]).sum()), len(diff)),
            "trades only in B": (float(ob["net_pnl_b"].sum()), float(ob["net_r_b"].sum()), len(ob)),
            "trades only in M (subtracted)": (-float(om["net_pnl_m"].sum()), -float(om["net_r_m"].sum()), len(om)),
            "open positions at the end": (float(openv(mB) - openv(mM)), None, None)}
    tot = float(curveB["equity"].iloc[-1] - curveM["equity"].iloc[-1])
    res = sum(v[0] for v in rows.values()) - tot
    if abs(res) > 0.01:
        raise RuntimeError(f"B-M split residual {res}")
    out = {k2: dict(usd=v[0], r_sum=v[1], n=v[2]) for k2, v in rows.items()}
    out["total (profit B - profit M)"] = dict(usd=tot, r_sum=None, n=None)
    return out


def selection_chain(M, exM, decisions, spy, bps=10):
    f = bps / 1e4
    c = M[M["status"] == "closed"].copy()
    c["R"] = (c["exit"] * (1 - f) - c["entry"] * (1 + f)) / (c["entry"] - c["stop"])
    c["date"] = pd.to_datetime(c["date"]).dt.normalize()
    sc = spy["Close"].astype(float).copy()
    sc.index = pd.DatetimeIndex(sc.index).normalize()
    r20 = (sc / sc.shift(20) - 1).to_dict()
    day = c.groupby("date").agg(n=("R", "size"), mean=("R", "mean"))
    c["spy_r20"] = pd.to_datetime(c["signal_date"]).dt.normalize().map(r20)
    dfeat = c.groupby("date").agg(spy_r20=("spy_r20", "first"))
    day = day.join(dfeat)
    top3 = c.groupby("date", sort=False).head(3)                     # M is sorted date, RS desc, ticker
    ent = exM.copy()
    ent["entry_date"] = pd.to_datetime(ent["entry_date"]).dt.normalize()

    def chain(cc, dd, tt, ee):
        w = np.minimum(dd["n"], 3)
        return dict(candidates=int(len(cc)), days=int(len(dd)), mu_all=float(cc["R"].mean()),
                    mu_day=float(dd["mean"].mean()), mu_rand3=float((dd["mean"] * w).sum() / w.sum()),
                    mu_top3=float(tt["R"].mean()), entered=int(len(ee)),
                    mu_entered=float(ee["net_r"].mean()) if len(ee) else None)
    out = dict(all=chain(c, day, top3, ent))
    dec = pd.DataFrame(decisions)
    dec["day"] = pd.to_datetime(dec["day"]).dt.normalize()
    t3 = top3.merge(dec[["ticker", "day", "outcome"]], left_on=["ticker", "date"], right_on=["ticker", "day"], how="left")
    out["top3_by_portfolio_outcome"] = {str(k): dict(n=int(len(g)), mean_r=float(g["R"].mean()))
                                        for k, g in t3.groupby(t3["outcome"].fillna("not offered"))}
    nt = c.merge(dec[["ticker", "day", "outcome"]], left_on=["ticker", "date"], right_on=["ticker", "day"], how="left")
    out["all_by_portfolio_outcome"] = {str(k): dict(n=int(len(g)), mean_r=float(g["R"].mean()))
                                       for k, g in nt.groupby(nt["outcome"].fillna("not offered"))}
    for feat, lab in (("n", "breadth (candidates that day)"), ("spy_r20", "SPY 20-session return")):
        cuts = day[feat].quantile([1 / 3, 2 / 3]).values
        out[f"terciles_{feat}"] = {"cuts": [float(x) for x in cuts], "label": lab}
        for i, (a, b) in enumerate(((-np.inf, cuts[0]), (cuts[0], cuts[1]), (cuts[1], np.inf))):
            dsel = day[(day[feat] > a) & (day[feat] <= b)] if i else day[day[feat] <= b]
            ds = set(dsel.index)
            out[f"terciles_{feat}"][f"T{i + 1}"] = chain(c[c["date"].isin(ds)], dsel, top3[top3["date"].isin(ds)],
                                                       ent[ent["entry_date"].isin(ds)])
    return out


def pctile(v, arr):
    arr = np.asarray(arr, float)
    return float(100 * (arr < v).mean())


def dist(rows, kind, w, bps):
    d = pd.DataFrame([r for r in rows if r["kind"] == kind and r["window"] == w and r["bps"] == bps])
    return d


def summarize(d, b):
    out = {}
    for k in KEEP:
        s = d[k].astype(float)
        out[k] = dict(p10=float(s.quantile(.1)), p50=float(s.median()), p80=float(s.quantile(.8)),
                      p90=float(s.quantile(.9)), mean=float(s.mean()), B=b[k], B_percentile=pctile(b[k], s))
    return out


def decide(res):
    b = res["books"]
    R1 = res["controls"]["R1"]
    crit = {
        "B CAGR > R1 p90 at 10 and 25 (full)": all(b[f"B|full|{c}"]["cagr_pct"] > R1[f"full|{c}"]["cagr_pct"]["p90"] for c in COSTS),
        "B PF > R1 p80 at 10 and 25 (full)": all((b[f"B|full|{c}"]["profit_factor"] or 0) > R1[f"full|{c}"]["profit_factor"]["p80"]
                                                for c in COSTS),
        "B max DD not > 3 pt deeper than R1 median (full 10)": b["B|full|10"]["max_dd_pct"] >= R1["full|10"]["max_dd_pct"]["p50"] - 3,
        "extension effect B - B0 > 0 at 10 and 25 (full)": all(res["b_minus_b0"][f"full|{c}"] > 0 for c in COSTS),
    }
    ok = all(crit.values())
    return dict(passed={k: bool(v) for k, v in crit.items()},
                verdict="B shows an advantage beyond turnover reduction (exploratory)" if ok
                else "B does NOT show a convincing advantage beyond turnover reduction: do not implement B")


# =====================================================================
# charts / report
# =====================================================================
def charts(out, res, rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fs = []

    def save(fig, n):
        fig.tight_layout()
        fig.savefig(out / n, dpi=110)
        plt.close(fig)
        fs.append(n)
    fig, ax = plt.subplots(2, 2, figsize=(11, 7))
    for i, kind in enumerate(("R1", "R2")):
        for j, c in enumerate(COSTS):
            d = dist(rows, kind, "full", c)
            ax[i, j].hist(d["cagr_pct"], bins=30, alpha=.7)
            ax[i, j].axvline(res["books"][f"B|full|{c}"]["cagr_pct"], color="k", ls="--", label="B")
            ax[i, j].axvline(res["books"][f"M|full|{c}"]["cagr_pct"], color="grey", label="M")
            ax[i, j].axvline(res["books"][f"B0|full|{c}"]["cagr_pct"], color="tab:orange", label="B0")
            ax[i, j].set_title(f"{kind}, full window, {c} bps: CAGR %")
            ax[i, j].legend(fontsize=8)
    save(fig, "controls_cagr.png")
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    d = dist(rows, "R1", "full", 10)
    ax[0].scatter(d["trades"], d["cagr_pct"], s=10, alpha=.5, label="R1 seeds")
    for k, col in (("M", "grey"), ("B", "k"), ("B0", "tab:orange")):
        x = res["books"][f"{k}|full|10"]
        ax[0].scatter([x["trades"]], [x["cagr_pct"]], color=col, s=60, label=k)
    ax[0].set_xlabel("trades")
    ax[0].set_ylabel("CAGR % (10 bps)")
    ax[0].legend()
    ax[1].scatter(d["invested_pct"], d["cagr_pct"], s=10, alpha=.5)
    for k, col in (("M", "grey"), ("B", "k"), ("B0", "tab:orange")):
        x = res["books"][f"{k}|full|10"]
        ax[1].scatter([x["invested_pct"]], [x["cagr_pct"]], color=col, s=60)
    ax[1].set_xlabel("mean invested %")
    save(fig, "controls_trades_exposure.png")
    s = res["selection"]["all"]
    fig, ax = plt.subplots(figsize=(8, 4))
    lab = ["all candidates", "day-weighted", "≤3/day random", "top-3 RS", "entered"]
    ax.bar(lab, [s["mu_all"], s["mu_day"], s["mu_rand3"], s["mu_top3"], s["mu_entered"]],
           color=["grey", "tab:blue", "tab:blue", "tab:green", "k"])
    ax.axhline(0, color="k", lw=.5)
    ax.set_ylabel("mean net R (10 bps)")
    ax.set_title("M: from all candidates to the trades the portfolio took")
    save(fig, "selection_chain.png")
    return fs


def report(res, out):
    b = res["books"]
    L = ["# Breakout + MA200 — Turnover & Selection Audit (exploratory)", "",
         "Pre-registration: `research/turnover_selection/PREREG_TURNOVER_SELECTION.md` (committed before the run). M and B are "
         "exactly PR #23's. The 2017–2021 history misses many former index members (20.6 % of PIT member-days in 2017 without a "
         "price): **nothing here is independent confirmation**. Research Breakout buys at the next open, not like `trader.py`.", "",
         f"Reproduction of PR #23 (M and B, 3 windows × 2 costs): {res['reproduction']}", "",
         "## Verdict", "", f"**{res['decision']['verdict']}**", "", "| Criterion | Result |", "|---|---|"]
    L += [f"| {k} | {'yes' if v else 'no'} |" for k, v in res["decision"]["passed"].items()]
    L += ["", "## 1. Where B's advantage comes from", "", "| Book | Window | bps | Return | CAGR | Max DD | PF | Trades | Turnover/yr | Invested % |",
          "|---|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for k, m in b.items():
        bk, w, c = k.split("|")
        L.append(f"| {bk} | {w} | {c} | {m['return_pct']:+.1f} % | {m['cagr_pct']:+.2f} % | {m['max_dd_pct']:.1f} % | "
                 f"{(m['profit_factor'] or 0):.3f} | {m['trades']} | {m['turnover_per_year']:.1f}× | {m['invested_pct']:.1f} |")
    L += ["", "B0 = B's exit dates (slots held as long as in B) with M's day-20 price for every runner. "
          "`B0 − M` = slot / turnover / composition effect; `B − B0` = price effect of extending runners.", "",
          "| Window | bps | B − M ($) | B0 − M ($) | B − B0 ($) |", "|---|---|---:|---:|---:|"]
    for k, v in res["b_minus_b0"].items():
        w, c = k.split("|")
        L.append(f"| {w} | {c} | {res['b_minus_m'][k]:,.0f} | {res['b0_minus_m'][k]:,.0f} | {v:,.0f} |")
    for k, sp in res["split"].items():
        L += ["", f"Exact split of profit_B − profit_M, {k}:", "", "| Part | $ | Σ R | n |", "|---|---:|---:|---:|"]
        L += [f"| {p} | {v['usd']:,.0f} | {'—' if v['r_sum'] is None else f'{v['r_sum']:+.1f}'} | {'—' if v['n'] is None else v['n']} |"
              for p, v in sp.items()]
    L += ["", "## 2. B against random controls (200 seeds each, full sequential replays)", "",
          f"R1: each M candidate dropped with probability q = {res['q']} (calibrated on seeds 1001–1020 to B's {b['B|full|10']['trades']} "
          f"trades). R2: {res['n_runners']} random time exits extended with B's trailing exit (no +2 R condition).", "",
          "![controls](controls_cagr.png)", "", "![trades](controls_trades_exposure.png)", "",
          "| Control | Window | bps | Metric | p10 | p50 | p80 | p90 | B | B percentile |", "|---|---|---|---|---:|---:|---:|---:|---:|---:|"]
    for kind in ("R1", "R2"):
        for key, s in res["controls"][kind].items():
            w, c = key.split("|")
            for met in ("cagr_pct", "max_dd_pct", "profit_factor", "return_pct", "trades", "turnover_per_year", "invested_pct"):
                x = s[met]
                L.append(f"| {kind} | {w} | {c} | {met} | {x['p10']:.2f} | {x['p50']:.2f} | {x['p80']:.2f} | {x['p90']:.2f} | "
                         f"{x['B']:.2f} | {x['B_percentile']:.0f} |")
    o = res["order"]
    L += ["", f"RS-first vs random same-day order (M, full 10 bps, 200 seeds): random p10 / p50 / p90 return = "
          f"{o['p10']:+.1f} / {o['p50']:+.1f} / {o['p90']:+.1f} %; RS-first M = {b['M|full|10']['return_pct']:+.1f} % "
          f"(percentile {o['M_percentile']:.0f}).", "",
          "## 3. Why candidates average < 0 R and M's trades > 0 R", "", "![chain](selection_chain.png)", ""]
    s = res["selection"]
    a = s["all"]
    L += ["| Step | Mean net R (10 bps) | Effect |", "|---|---:|---:|",
          f"| all candidates ({a['candidates']}) | {a['mu_all']:+.3f} | |",
          f"| each day weighted equally ({a['days']} days) | {a['mu_day']:+.3f} | crowding {a['mu_day'] - a['mu_all']:+.3f} |",
          f"| ≤ 3 random per day | {a['mu_rand3']:+.3f} | daily limit / crowding {a['mu_rand3'] - a['mu_all']:+.3f} |",
          f"| top 3 by RS per day | {a['mu_top3']:+.3f} | RS-first {a['mu_top3'] - a['mu_rand3']:+.3f} |",
          f"| entered by the portfolio ({a['entered']}) | {a['mu_entered']:+.3f} | slots / held / sequence {a['mu_entered'] - a['mu_top3']:+.3f} |",
          "", "Top-3-by-RS candidates by portfolio outcome: " + "; ".join(f"{k}: n={v['n']}, {v['mean_r']:+.3f} R"
                                                                        for k, v in s["top3_by_portfolio_outcome"].items()),
          "", "All candidates by portfolio outcome: " + "; ".join(f"{k}: n={v['n']}, {v['mean_r']:+.3f} R"
                                                               for k, v in s["all_by_portfolio_outcome"].items())]
    for feat in ("n", "spy_r20"):
        t = s[f"terciles_{feat}"]
        L += ["", f"By {t['label']} terciles (cuts {', '.join(f'{x:.3g}' for x in t['cuts'])}):", "",
              "| Tercile | Candidates | Days | All | Day-weighted | ≤3 random | Top-3 RS | Entered (n) |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for k in ("T1", "T2", "T3"):
            v = t[k]
            L.append(f"| {k} | {v['candidates']} | {v['days']} | {v['mu_all']:+.3f} | {v['mu_day']:+.3f} | {v['mu_rand3']:+.3f} | "
                     f"{v['mu_top3']:+.3f} | {(v['mu_entered'] if v['mu_entered'] is not None else float('nan')):+.3f} ({v['entered']}) |")
    L += ["", "## Context only: the completed research/breakout-causes run (base C, no MA200 — not mixed with M/B)", "",
          f"Source: {CTX}. On C (10 bps): exact split signal quality +0.145 R / entry gap −0.037 / stop gap −0.045 / costs −0.048 = "
          "+0.014 R per executed trade (on the signal-close risk); after a time exit the stock beat SPY by +1.66 % at +20 sessions "
          "(90 % CI +0.59…+2.65) — on M the same figure is +0.60 % with a CI including 0 (PR #23). H2 there is identical to M "
          "and beat random removal of the same number of candidates (p95 +31.4 % vs +47.8 %); H3 (hold ≥ +1 R, 1 R trail, bar 60) "
          "on C was not supported (deeper drawdown).", ""]
    (out / "REPORT.md").write_text("\n".join(L) + "\n")


# =====================================================================
# main
# =====================================================================
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--out", default=str(ROOT / "research/results/turnover_selection/runs"))
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--n", type=int, default=200)
    a = ap.parse_args(argv)
    out = Path(a.out) / datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    out.mkdir(parents=True, exist_ok=False)
    frames, spy, pit_text, dsha = CR.load(a.dataset)
    sig, data, cal, info = CR.build(frames, spy, pit_text)
    start, end = cal[min(260, len(cal) - 1)], cal[-1]
    windows = dict(full=(start, end), y2017_2021=(start, pd.Timestamp("2021-12-31")), y2022_2026=(cal[cal >= CR.HOLDOUT][0], end))
    M = CR.trades_for(CR.eligible(sig, True), data, "breakout")
    B = R.runner_book(M, data)
    B0 = b0_book(M, B)
    ref = json.loads(PR23.read_text())["books"]
    res = dict(prereg="research/turnover_selection/PREREG_TURNOVER_SELECTION.md", dataset_sha256=dsha,
               windows={k: [str(v[0].date()), str(v[1].date())] for k, v in windows.items()}, reproduction={}, books={},
               split={}, b_minus_m={}, b0_minus_m={}, b_minus_b0={})
    keep = {}
    for name, tr in (("M", M), ("B", B), ("B0", B0)):
        for w, (s0, s1) in windows.items():
            for bps in COSTS:
                curve, ex, m = replay(tr, data, s0, s1, bps, decisions=(name == "M" and w == "full" and bps == 10))
                met = metrics(curve, ex, m, spy)
                res["books"][f"{name}|{w}|{bps}"] = {k: met[k] for k in KEEP}
                keep[(name, w, bps)] = (curve, ex, m)
                if name in ("M", "B"):
                    anc = ref[f"{name}|{w}|{bps}"]
                    d = (met["return_pct"] - anc["return_pct"], met["max_dd_pct"] - anc["max_dd_pct"], met["trades"] - anc["trades"])
                    if abs(d[0]) > 1e-6 or abs(d[1]) > 1e-6 or d[2]:
                        raise RuntimeError(f"STOP: {name} does not reproduce PR #23 ({w}, {bps}): {d}")
                    res["reproduction"][f"{name} {w} {bps}"] = "exact"
    for w in windows:
        for bps in COSTS:
            cm, em, mm = keep[("M", w, bps)]
            cb, eb, mb = keep[("B", w, bps)]
            c0 = keep[("B0", w, bps)][0]
            k = f"{w}|{bps}"
            res["split"][k] = split_b_vs_m(em, mm, eb, mb, cm, cb, bps)
            res["b_minus_m"][k] = float(cb["equity"].iloc[-1] - cm["equity"].iloc[-1])
            res["b0_minus_m"][k] = float(c0["equity"].iloc[-1] - cm["equity"].iloc[-1])
            res["b_minus_b0"][k] = float(cb["equity"].iloc[-1] - c0["equity"].iloc[-1])
    # ---- random controls
    ext = extend_all(M, data)
    n_runners = int(B["runner"].sum())
    G.update(M=M, data=data, spy=spy, windows=windows, ext=ext, n_runners=n_runners)
    target = res["books"]["B|full|10"]["trades"]
    q, cal_log = calibrate_q(target, a.workers)
    res.update(q=q, calibration=cal_log, n_runners=n_runners, extension_pool=len(ext))
    tasks = [(kind, s, w, bps, q) for kind in ("R1", "R2") for s in range(1, a.n + 1) for w in windows for bps in COSTS]
    tasks += [("ORDER", s, "full", 10, q) for s in range(1, a.n + 1)]
    rows = run_tasks(tasks, a.workers)
    pd.DataFrame(rows).to_csv(out / "controls.csv", index=False)
    res["controls"] = {kind: {f"{w}|{bps}": summarize(dist(rows, kind, w, bps), res["books"][f"B|{w}|{bps}"])
                              for w in windows for bps in COSTS} for kind in ("R1", "R2")}
    od = dist(rows, "ORDER", "full", 10)["return_pct"]
    res["order"] = dict(p10=float(od.quantile(.1)), p50=float(od.median()), p90=float(od.quantile(.9)),
                        M_percentile=pctile(res["books"]["M|full|10"]["return_pct"], od))
    # ---- selection chain
    cm, em, mm = keep[("M", "full", 10)]
    res["selection"] = selection_chain(M, em, mm["decisions"], spy)
    res["decision"] = decide(res)
    res["charts"] = charts(out, res, rows)
    res["provenance"] = dict(commit=subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip(),
                             prereg_sha256=hashlib.sha256((ROOT / res["prereg"]).read_bytes()).hexdigest(),
                             pr23_sha256=hashlib.sha256(PR23.read_bytes()).hexdigest())
    (out / "results.json").write_text(json.dumps(res, indent=1, default=str))
    report(res, out)
    print(json.dumps(dict(out=str(out), q=q, verdict=res["decision"]["verdict"]), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
