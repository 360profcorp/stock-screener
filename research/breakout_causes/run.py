"""Why research Breakout is weak (PREREG_BREAKOUT_CAUSES.md). Exploratory, research only.

    python -m research.breakout_causes.run --dataset DIR [--workers N] [--n-random 200]

1. execution audit of control C: exact split of P&L into signal quality and execution
   mechanics (entry gap, stop gap, costs), open gaps, entry-day stops, stop-width buckets;
2. post-exit stock vs SPY on the same dates (hindsight);
3. H1 (risk >= 4 % at the open), H2 (SPY > MA50 and > MA200), H3 (keep a strong position
   past bar 20 with a protective trailing stop, hard exit at bar 60) as full portfolio
   replays at 10 / 25 bps, full window and both halves, plus the random-removal benchmark.
Control C must reproduce PR #19 exactly or the run stops.
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
from research.crisis import run as CR

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / "research/results/crisis/runs/2026-10-25T0255Z/results.json"
COSTS = (10, 25)
HORIZONS = (5, 10, 20)
H1_MIN_RISK_PCT = 4.0
H3_STRONG_R, H3_TRAIL_R, H3_MAX_BARS, BASE_BARS = 1.0, 1.0, 60, 20
SEED = 20261025
HALF = pd.Timestamp("2021-12-31")
HALF2 = pd.Timestamp("2022-01-03")


# =====================================================================
# hypotheses: candidate sets (rules only, no fitting)
# =====================================================================
def h1(tr, min_risk=H1_MIN_RISK_PCT):
    """Entry quality: planned risk at the actual open (entry - stop)/entry >= min_risk %."""
    return tr[tr["risk_pct"] >= min_risk].reset_index(drop=True)


def idx_of(x, day):
    d = pd.DatetimeIndex(pd.to_datetime(x["dates"])).normalize()
    k = np.flatnonzero(d == pd.Timestamp(day).normalize())
    if len(k) != 1:
        raise ValueError(f"date {day} not unique/present")
    return int(k[0]), d


def extend_strong(row, x, strong_r=H3_STRONG_R, trail_r=H3_TRAIL_R, max_bars=H3_MAX_BARS, base=BASE_BARS):
    """H3 exit for one control trade. Only trades closed by time at bar `base` can change.
    Strong (close of bar base >= entry + strong_r R): from bar base+1 a protective stop =
    max(entry, highest close so far - trail_r R) from closes up to the previous session,
    filled at min(open, stop) when the low reaches it; hard exit at the close of bar max_bars.
    Returns a dict of updated fields (or {} if unchanged)."""
    if row["reason"] != "time" or row["status"] != "closed":
        return {}
    e, d = idx_of(x, row["date"])
    j20 = e + base
    if pd.Timestamp(d[j20]) != pd.Timestamp(row["exit_date"]).normalize():
        raise ValueError("time exit not at bar 20")
    O, L, C = (np.asarray(x[k], dtype=float) for k in ("O", "L", "C"))
    entry, stop = float(row["entry"]), float(row["stop"])
    R = entry - stop
    if C[j20] < entry + strong_r * R:
        return {}
    hc = float(np.max(C[e:j20 + 1]))
    last = len(C) - 1
    for j in range(j20 + 1, min(e + max_bars, last) + 1):
        lvl = max(entry, hc - trail_r * R)
        if L[j] <= lvl:
            px = min(O[j], lvl)
            return dict(exit_date=d[j], exit=float(px), reason="trail", status="closed", days=j - e,
                        ret_pct=(px / entry - 1) * 100, r=(px / entry - 1) / (R / entry), h3="extended")
        hc = max(hc, float(C[j]))
        if j == e + max_bars:
            return dict(exit_date=d[j], exit=float(C[j]), reason="time60", status="closed", days=j - e,
                        ret_pct=(C[j] / entry - 1) * 100, r=(C[j] / entry - 1) / (R / entry), h3="extended")
    mark = float(C[last])                           # data ends inside the extended hold
    return dict(exit_date=pd.NaT, exit=np.nan, reason="open", status="open", days=last - e, ret_pct=np.nan,
                r=np.nan, mark_date=d[last], mark=mark, mark_r=(mark / entry - 1) / (R / entry), h3="extended")


def h3(tr, data):
    out = tr.copy()
    out["h3"] = ""
    for k, row in out.iterrows():
        upd = extend_strong(row, data[row["ticker"]])
        for c, v in upd.items():
            out.at[k, c] = v
    return out


# =====================================================================
# portfolio books
# =====================================================================
def book(tr, data, s0, s1, bps, spy):
    curve, ex, m = pf.replay(tr, data, start=s0, end=s1, open_at_end="mark", cost_bps=float(bps), **CR.CFG)
    return CR.metrics(curve, ex, m, spy), curve, ex, m


def _rnd(args):
    seed, k = args
    rng = np.random.default_rng(seed)
    drop = rng.choice(len(G["tr"]), size=k, replace=False)
    t = G["tr"].drop(index=G["tr"].index[drop])
    _, _, m = pf.replay(t, G["data"], start=G["s0"], end=G["s1"], open_at_end="mark", cost_bps=10., **CR.CFG)
    return float(m["return_pct"])


G = {}


def random_removal(tr, data, s0, s1, k, n, workers):
    G.update(tr=tr, data=data, s0=s0, s1=s1)
    args = [(s, k) for s in range(1, n + 1)]
    if workers > 1:
        with ProcessPoolExecutor(workers) as p:
            rets = list(p.map(_rnd, args, chunksize=4))
    else:
        rets = [_rnd(a) for a in args]
    r = np.array(rets)
    return dict(n=n, removed=int(k), p20=float(np.quantile(r, .2)), p50=float(np.median(r)),
                p80=float(np.quantile(r, .8)), p95=float(np.quantile(r, .95)), returns=[round(v, 3) for v in r])


# =====================================================================
# 1. execution audit
# =====================================================================
def signal_close(x, day):
    i, _ = idx_of(x, day)
    return float(np.asarray(x["C"], dtype=float)[i])


def split_execution(rows, data, bps):
    """Exact split per trade, in $ (for executed trades: shares) and in R of risk_sig."""
    f = bps / 1e4
    out = []
    for r in rows.itertuples(index=False):
        cs = signal_close(data[r.ticker], r.signal_date)
        risk_sig = cs - r.stop
        ideal = r.stop if r.reason == "stop" else r.exit
        q = getattr(r, "shares", 1.0)
        parts = dict(signal_quality=ideal - cs, entry_gap=-(r.entry - cs), stop_gap=r.exit - ideal,
                     costs=-(r.entry + r.exit) * f)
        row = dict(ticker=r.ticker, signal_date=r.signal_date, entry_date=r.date, exit_date=r.exit_date,
                   reason=r.reason, close_sig=cs, entry=r.entry, stop=r.stop, exit=r.exit, shares=q,
                   risk_sig=risk_sig, risk_pct_open=r.risk_pct, gap_open_pct=100 * (r.entry / cs - 1),
                   gap_open_r=(r.entry - cs) / risk_sig,
                   entry_day_stop=bool(r.reason == "stop" and pd.Timestamp(r.exit_date) == pd.Timestamp(r.date)))
        for k, v in parts.items():
            row[k + "_usd"] = q * v
            row[k + "_r"] = v / risk_sig
        row["net_usd"] = q * (r.exit - r.entry - (r.entry + r.exit) * f)
        row["net_r_sig"] = sum(row[k + "_r"] for k in parts)
        out.append(row)
    d = pd.DataFrame(out)
    chk = d[[k + "_usd" for k in ("signal_quality", "entry_gap", "stop_gap", "costs")]].sum(axis=1)
    if not np.allclose(chk, d["net_usd"], atol=1e-6):
        raise RuntimeError("execution split does not add up")
    return d


def split_summary(d):
    keys = ("signal_quality", "entry_gap", "stop_gap", "costs")
    return dict(n=int(len(d)), **{f"{k}_usd": float(d[k + "_usd"].sum()) for k in keys},
                net_usd=float(d["net_usd"].sum()),
                **{f"{k}_r_per_trade": float(d[k + "_r"].mean()) for k in keys},
                net_r_sig_per_trade=float(d["net_r_sig"].mean()))


def bucket_table(d, col, bins, labels, value_cols):
    d = d.copy()
    d["bucket"] = pd.cut(d[col], bins, labels=labels)
    agg = {c: (c, "mean") for c in value_cols}
    t = d.groupby("bucket", observed=False).agg(n=(col, "size"), **agg,
                                                stop_rate=("reason", lambda s: float((s == "stop").mean()) if len(s) else None),
                                                entry_day_stop_rate=("entry_day_stop", "mean"))
    return {str(k): {a: (None if pd.isna(b) else float(b)) for a, b in v.items()} for k, v in t.to_dict("index").items()}


GAP_BINS = ([-100, -1, 0, 0.5, 1, 2, 4, 100], ["<-1%", "-1..0%", "0..0.5%", "0.5..1%", "1..2%", "2..4%", ">4%"])
RISK_BINS = ([0, 2, 4, 6, 10, 100], ["<2%", "2-4%", "4-6%", "6-10%", ">10%"])


def non_overlap(tr):
    keep, busy = [], {}
    for idx, r in tr.sort_values(["ticker", "date"], kind="stable").iterrows():
        b = busy.get(r["ticker"])
        if b is not None and (pd.isna(b) or r["date"] <= b):
            continue
        keep.append(idx)
        busy[r["ticker"]] = r["exit_date"]
    return tr.loc[keep]


def with_shares(ex, tr):
    t = tr[["ticker", "date", "signal_date", "stop", "reason", "risk_pct"]].copy()
    e = ex.copy()
    e["entry_date"] = pd.to_datetime(e["entry_date"]).dt.normalize()
    e = e.merge(t, left_on=["ticker", "entry_date"], right_on=["ticker", "date"], how="left", validate="one_to_one")
    if e["stop"].isna().any():
        raise RuntimeError("execution without candidate")
    return e


# =====================================================================
# 2. post-exit vs SPY
# =====================================================================
def post_exit_vs_spy(e, data, spy, horizons=HORIZONS):
    sc = spy["Close"].astype(float).copy()
    sc.index = pd.DatetimeIndex(sc.index).normalize()
    rows = []
    for r in e.itertuples(index=False):
        x = data[r.ticker]
        i1, d = idx_of(x, r.exit_date)
        C = np.asarray(x["C"], dtype=float)
        row = dict(ticker=r.ticker, exit_date=pd.Timestamp(r.exit_date), reason=r.reason)
        for h in horizons:
            if i1 + h < len(C) and d[i1] in sc.index and d[i1 + h] in sc.index:
                s = C[i1 + h] / C[i1] - 1
                m = sc[d[i1 + h]] / sc[d[i1]] - 1
                row.update({f"stock_{h}": 100 * s, f"spy_{h}": 100 * m, f"excess_{h}": 100 * (s - m)})
        rows.append(row)
    return pd.DataFrame(rows)


def boot_ci(v, months, n=2000, seed=SEED):
    v, months = np.asarray(v, float), np.asarray(months)
    ok = ~np.isnan(v)
    v, months = v[ok], months[ok]
    if not len(v):
        return [None, None]
    groups = [v[months == m] for m in np.unique(months)]
    rng = np.random.default_rng(seed)
    bs = [np.concatenate([groups[k] for k in rng.integers(0, len(groups), len(groups))]).mean() for _ in range(n)]
    return [float(np.quantile(bs, .05)), float(np.quantile(bs, .95))]


def post_summary(P):
    out = {}
    P = P.copy()
    P["month"] = P["exit_date"].dt.to_period("M").astype(str)
    for grp, g in P.groupby("reason"):
        row = dict(n=int(len(g)))
        for h in HORIZONS:
            s = g[f"excess_{h}"].dropna()
            row[f"+{h}"] = dict(n=int(len(s)), stock_mean_pct=float(g[f"stock_{h}"].mean()),
                                spy_mean_pct=float(g[f"spy_{h}"].mean()), excess_mean_pct=float(s.mean()),
                                excess_median_pct=float(s.median()), excess_positive_pct=float(100 * (s > 0).mean()),
                                excess_ci90=boot_ci(g[f"excess_{h}"], g["month"]))
        out[grp] = row
    return out


# =====================================================================
# charts and report
# =====================================================================
def charts(out, res, curves, audit, rnd):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fs = []

    def save(fig, n):
        fig.tight_layout()
        fig.savefig(out / n, dpi=110)
        plt.close(fig)
        fs.append(n)

    s = res["execution_audit"]["executed_10bps"]
    keys = ["signal_quality", "entry_gap", "stop_gap", "costs"]
    fig, ax = plt.subplots(figsize=(7, 4))
    vals = [s[k + "_usd"] for k in keys] + [s["net_usd"]]
    ax.bar(keys + ["net"], vals, color=["tab:blue", "tab:orange", "tab:red", "tab:grey", "k"])
    ax.axhline(0, color="k", lw=.5)
    ax.set_title("Control Breakout, 10 bps: signal quality vs execution ($, 10 years)")
    save(fig, "execution_split.png")

    g = res["execution_audit"]["by_open_gap"]
    fig, ax = plt.subplots(figsize=(8, 4))
    lab = list(g)
    ax.bar(lab, [g[k]["net_r_sig"] if g[k]["net_r_sig"] is not None else 0 for k in lab], label="net R (signal risk)")
    ax.plot(lab, [g[k]["signal_quality_r"] if g[k]["signal_quality_r"] is not None else 0 for k in lab], "o-",
            color="tab:orange", label="signal quality R")
    for i, k in enumerate(lab):
        ax.text(i, 0, f"n={g[k]['n']:.0f}", ha="center", va="bottom", fontsize=8)
    ax.axhline(0, color="k", lw=.5)
    ax.legend()
    ax.set_title("Executed trades by gap at the open vs the signal close")
    save(fig, "open_gap.png")

    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    for i, bps in enumerate(COSTS):
        t = res["execution_audit"][f"by_risk_{bps}bps"]
        lab = list(t)
        ax[i].bar(np.arange(len(lab)) - .2, [t[k]["gross_r"] or 0 for k in lab], .4, label="gross R")
        ax[i].bar(np.arange(len(lab)) + .2, [t[k]["net_r"] or 0 for k in lab], .4, label="net R")
        ax[i].set_xticks(np.arange(len(lab)), lab)
        ax[i].axhline(0, color="k", lw=.5)
        ax[i].set_title(f"by stop width at the open, {bps} bps")
        ax[i].legend()
    save(fig, "stop_width.png")

    ps = res["post_exit_vs_spy"]
    fig, ax = plt.subplots(figsize=(8, 4))
    for i, grp in enumerate(("time", "stop")):
        if grp not in ps:
            continue
        m = [ps[grp][f"+{h}"]["excess_mean_pct"] for h in HORIZONS]
        lo = [m[j] - ps[grp][f"+{h}"]["excess_ci90"][0] for j, h in enumerate(HORIZONS)]
        hi = [ps[grp][f"+{h}"]["excess_ci90"][1] - m[j] for j, h in enumerate(HORIZONS)]
        ax.bar(np.arange(len(HORIZONS)) * 3 + i, m, yerr=[lo, hi], capsize=4, label=f"{grp} exits")
    ax.set_xticks(np.arange(len(HORIZONS)) * 3 + .5, [f"+{h}" for h in HORIZONS])
    ax.axhline(0, color="k", lw=.5)
    ax.set_ylabel("stock minus SPY, % (mean, 90 % CI)")
    ax.legend()
    ax.set_title("After the exit: return in excess of SPY on the same dates (hindsight)")
    save(fig, "post_exit_vs_spy.png")

    fig, ax = plt.subplots(figsize=(10, 4.5))
    for k, c in curves.items():
        ax.plot(c["date"], c["equity"], label=k, lw=1.5 if k == "C" else 1)
    ax.set_title("Full window, 10 bps: control vs hypotheses")
    ax.legend()
    save(fig, "books.png")

    fig, ax = plt.subplots(figsize=(8, 4))
    for k, v in rnd.items():
        ax.hist(v["returns"], bins=30, alpha=.5, label=f"random removal of {v['removed']} ({k})")
        ax.axvline(res["books"][f"{k}|full|10"]["return_pct"], color="k" if k == "H1" else "tab:red", ls="--",
                   label=f"{k} book")
    ax.axvline(res["books"]["C|full|10"]["return_pct"], color="grey", label="C")
    ax.legend(fontsize=8)
    ax.set_title("Filters vs random removal of the same number of candidates (full, 10 bps)")
    save(fig, "random_removal.png")
    return fs


def fmt(v, f="{:+.1f}"):
    return "—" if v is None or (isinstance(v, float) and np.isnan(v)) else f.format(v)


def report(res, out):
    B = res["books"]
    L = ["# Why research Breakout is weak — execution audit and hypotheses (exploratory)", "",
         "Pre-registration: `research/breakout_causes/PREREG_BREAKOUT_CAUSES.md`. The 2017–2026 data were already "
         "examined (PR #19, #22): nothing here is independent confirmation. Research Breakout enters at the next open "
         "(not the bot's pre-close breakout). No paper book is started.", "",
         "## Reproduction gate", "",
         "Control C reproduces PR #19: " + "; ".join(f"{k}: {v}" for k, v in res["reproduction"].items()), "",
         "## 1. Execution audit (control C, Breakout)", "", "![split](execution_split.png)", "",
         "Exact split of net P&L into signal quality (exit at the planned stop or the time-exit close, measured from "
         "the signal-day close) and execution mechanics. R is per trade on the risk at the signal close.", "",
         "| Set | n | Signal quality | Entry gap | Stop gap | Costs | Net |", "|---|---:|---:|---:|---:|---:|---:|"]
    A = res["execution_audit"]
    for name in ("executed_10bps", "executed_25bps", "all_candidates_10bps", "non_overlap_10bps"):
        s = A[name]
        usd = name.startswith("executed")
        if usd:
            L.append(f"| {name} ($) | {s['n']} | {s['signal_quality_usd']:,.0f} | {s['entry_gap_usd']:,.0f} | "
                     f"{s['stop_gap_usd']:,.0f} | {s['costs_usd']:,.0f} | {s['net_usd']:,.0f} |")
        L.append(f"| {name} (R/trade) | {s['n']} | {s['signal_quality_r_per_trade']:+.3f} | {s['entry_gap_r_per_trade']:+.3f} | "
                 f"{s['stop_gap_r_per_trade']:+.3f} | {s['costs_r_per_trade']:+.3f} | {s['net_r_sig_per_trade']:+.3f} |")
    o = A["open"]
    L += ["", f"- Open gap vs the signal close (executed): median {o['gap_open_pct_median']:+.2f} %, mean "
          f"{o['gap_open_pct_mean']:+.2f} %; {o['gap_up_share_pct']:.0f} % of entries opened above the signal close; mean "
          f"gap {o['gap_open_r_mean']:+.3f} R of the signal risk.",
          f"- Candidates never traded because the open was at or below the stop: {o['not_traded_open_below_stop']} "
          f"of {o['eligible_signals']} eligible signals.",
          f"- Entry-day stops (executed): {o['entry_day_stops']} trades, ${o['entry_day_stop_usd']:,.0f}, mean "
          f"{o['entry_day_stop_r']:+.2f} R; {o['entry_day_stops_risk_lt4_share_pct']:.0f} % of them had a risk < 4 % at the open.", "",
          "![gap](open_gap.png)", "", "| Open gap | n | Signal quality R | Entry gap R | Net R | Stop rate | Entry-day stop rate |",
          "|---|---:|---:|---:|---:|---:|---:|"]
    for k, v in A["by_open_gap"].items():
        L.append(f"| {k} | {v['n']:.0f} | {fmt(v['signal_quality_r'], '{:+.3f}')} | {fmt(v['entry_gap_r'], '{:+.3f}')} | "
                 f"{fmt(v['net_r_sig'], '{:+.3f}')} | {fmt(v['stop_rate'], '{:.2f}')} | {fmt(v['entry_day_stop_rate'], '{:.2f}')} |")
    L += ["", "![width](stop_width.png)", "", "| Risk at the open | bps | n | Gross R | Cost R | Net R | Stop rate | Entry-day stop rate |",
          "|---|---|---:|---:|---:|---:|---:|---:|"]
    for bps in COSTS:
        for k, v in A[f"by_risk_{bps}bps"].items():
            L.append(f"| {k} | {bps} | {v['n']:.0f} | {fmt(v['gross_r'], '{:+.3f}')} | {fmt(v['cost_r'], '{:.3f}')} | "
                     f"{fmt(v['net_r'], '{:+.3f}')} | {fmt(v['stop_rate'], '{:.2f}')} | {fmt(v['entry_day_stop_rate'], '{:.2f}')} |")
    L += ["", "## 2. After the exit: stock vs SPY on the same dates (hindsight)", "", "![post](post_exit_vs_spy.png)", "",
          "| Exit | Horizon | n | Stock % | SPY % | Excess % (mean) | Excess median | Excess > 0 | 90 % CI of mean excess |",
          "|---|---|---:|---:|---:|---:|---:|---:|---|"]
    for grp, v in res["post_exit_vs_spy"].items():
        for h in HORIZONS:
            x = v[f"+{h}"]
            L.append(f"| {grp} | +{h} | {x['n']} | {x['stock_mean_pct']:+.2f} | {x['spy_mean_pct']:+.2f} | "
                     f"{x['excess_mean_pct']:+.2f} | {x['excess_median_pct']:+.2f} | {x['excess_positive_pct']:.0f} % | "
                     f"[{x['excess_ci90'][0]:+.2f}, {x['excess_ci90'][1]:+.2f}] |")
    L += ["", "## 3. Hypotheses: full portfolio replays", "", "![books](books.png)", "",
          "| Book | Window | bps | Return | CAGR | Max DD | PF | Trades | Exp. R |", "|---|---|---|---:|---:|---:|---:|---:|---:|"]
    for k, m in B.items():
        b, w, c = k.split("|")
        L.append(f"| {b} | {w} | {c} | {m['return_pct']:+.1f} % | {fmt(m['cagr_pct'])} % | {m['max_dd_pct']:.1f} % | "
                 f"{fmt(m['profit_factor'], '{:.2f}')} | {m['trades']} | {fmt(m['expectancy_r'], '{:+.3f}')} |")
    L += ["", "![rnd](random_removal.png)", ""]
    for k, v in res["random_removal"].items():
        L.append(f"- {k}: removing {v['removed']} random candidates (200 seeds), full 10 bps return p20 / p50 / p80 / p95 = "
                 f"{v['p20']:+.1f} / {v['p50']:+.1f} / {v['p80']:+.1f} / {v['p95']:+.1f} %; {k} = {B[k + '|full|10']['return_pct']:+.1f} %.")
    h3 = res["h3_changes"]
    L += ["", f"H3 changed {h3['extended']} of {h3['time_exits']} time exits (strong at bar 20): {h3['by_reason']}.", "",
          "## Decision (pre-registered, applied unchanged)", "", "| Hypothesis | Criteria | Verdict |", "|---|---|---|"]
    for k, v in res["decision"].items():
        L.append(f"| {k} | {v['criteria']} | **{v['verdict']}** |")
    L += ["", "Even a 'supported' verdict only makes a candidate for a separately approved forward paper test.", ""]
    (out / "REPORT.md").write_text("\n".join(L) + "\n")


# =====================================================================
# main
# =====================================================================
def decide(B, rnd):
    out = {}
    c = lambda w, b: B[f"C|{w}|{b}"]                                       # noqa: E731
    for h in ("H1", "H2", "H3"):
        x = lambda w, b: B[f"{h}|{w}|{b}"]                                  # noqa: E731
        crit = {
            "full return > C at 10 and 25": all(x("full", b)["return_pct"] > c("full", b)["return_pct"] for b in COSTS),
            "full PF > C at 10 and 25": all((x("full", b)["profit_factor"] or 0) > (c("full", b)["profit_factor"] or 0)
                                            for b in COSTS),
            "max DD not > 3 pt deeper (10)": x("full", 10)["max_dd_pct"] >= c("full", 10)["max_dd_pct"] - 3,
            "both halves return > C (10)": all(x(w, 10)["return_pct"] > c(w, 10)["return_pct"] for w in ("first_half", "second_half")),
        }
        if h in rnd:
            crit["> random-removal p80 (full 10)"] = x("full", 10)["return_pct"] > rnd[h]["p80"]
        ok = all(crit.values())
        out[h] = dict(criteria="; ".join(f"{k}: {'yes' if v else 'no'}" for k, v in crit.items()),
                      passed={k: bool(v) for k, v in crit.items()},
                      verdict="supported (exploratory)" if ok else "not supported")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--out", default=str(ROOT / "research/results/breakout_causes/runs"))
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--n-random", type=int, default=200)
    a = ap.parse_args(argv)
    out = Path(a.out) / datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    out.mkdir(parents=True, exist_ok=False)
    frames, spy, pit_text, dsha = CR.load(a.dataset)
    sig, data, cal, info = CR.build(frames, spy, pit_text)
    start, end = cal[min(260, len(cal) - 1)], cal[-1]
    windows = dict(full=(start, end), first_half=(start, HALF), second_half=(cal[cal >= HALF2][0], end))
    C = CR.trades_for(CR.eligible(sig, False), data, "breakout")
    sets = dict(C=C, H1=h1(C), H2=CR.trades_for(CR.eligible(sig, True), data, "breakout"), H3=h3(C, data))
    ref = json.loads(REF.read_text())
    res = dict(prereg="research/breakout_causes/PREREG_BREAKOUT_CAUSES.md", dataset_sha256=dsha, data=info,
               window=[str(start.date()), str(end.date())], reproduction={}, books={}, candidates={k: int(len(v)) for k, v in sets.items()})
    curves, fills = {}, {}
    for name, tr in sets.items():
        for w, (s0, s1) in windows.items():
            for bps in COSTS:
                m, curve, ex, raw = book(tr, data, s0, s1, bps, spy)
                res["books"][f"{name}|{w}|{bps}"] = m
                if name == "C" and w == "full":
                    anc = ref["books"][f"breakout|C|full|{bps}bps"]
                    diff = dict(return_pct=m["return_pct"] - anc["return_pct"], max_dd_pct=m["max_dd_pct"] - anc["max_dd_pct"],
                                trades=m["trades"] - anc["trades"])
                    if abs(diff["return_pct"]) > 1e-6 or abs(diff["max_dd_pct"]) > 1e-6 or diff["trades"]:
                        raise RuntimeError(f"STOP: control C does not reproduce PR #19 at {bps} bps: {diff}")
                    res["reproduction"][f"{bps} bps"] = "exact"
                if w == "full":
                    fills[(name, bps)] = ex
                    if bps == 10:
                        curves[name] = curve
                        ex.to_csv(out / f"trades_{name}.csv", index=False)
                        curve[["date", "equity", "cash", "open_positions"]].to_csv(out / f"equity_{name}.csv", index=False)
    # 1. execution audit
    A = {}
    for bps in COSTS:
        e = with_shares(fills[("C", bps)], C)
        e = e.rename(columns={"entry_date": "date_entry"}).assign(date=e["entry_date"])
        d = split_execution(e, data, bps)
        A[f"executed_{bps}bps"] = split_summary(d)
        e2 = e.copy()
        e2["gross_r"] = (e2["exit"] - e2["entry"]) / (e2["entry"] - e2["stop"])
        e2["cost_r"] = (e2["entry"] + e2["exit"]) * bps / 1e4 / (e2["entry"] - e2["stop"])
        e2["net_r"] = e2["gross_r"] - e2["cost_r"]
        e2["entry_day_stop"] = (e2["reason"] == "stop") & (pd.to_datetime(e2["exit_date"]) == pd.to_datetime(e2["date"]))
        A[f"by_risk_{bps}bps"] = bucket_table(e2, "risk_pct", *RISK_BINS, ["gross_r", "cost_r", "net_r"])
        if bps == 10:
            d.to_csv(out / "execution_audit.csv", index=False)
            A["by_open_gap"] = bucket_table(d, "gap_open_pct", *GAP_BINS,
                                            ["signal_quality_r", "entry_gap_r", "stop_gap_r", "net_r_sig"])
            eds = d[d["entry_day_stop"]]
            elig = CR.eligible(sig, False)
            n_sig = int((elig["strategy"] == "breakout").sum())
            A["open"] = dict(gap_open_pct_median=float(d["gap_open_pct"].median()), gap_open_pct_mean=float(d["gap_open_pct"].mean()),
                             gap_up_share_pct=float(100 * (d["gap_open_pct"] > 0).mean()), gap_open_r_mean=float(d["gap_open_r"].mean()),
                             eligible_signals=n_sig, candidates=int(len(C)), not_traded_open_below_stop=n_sig - int(len(C)),
                             entry_day_stops=int(len(eds)), entry_day_stop_usd=float(eds["net_usd"].sum()),
                             entry_day_stop_r=float(eds["net_r_sig"].mean()) if len(eds) else None,
                             entry_day_stops_risk_lt4_share_pct=float(100 * (eds["risk_pct_open"] < 4).mean()) if len(eds) else None)
            P = post_exit_vs_spy(d.assign(reason=d["reason"]), data, spy)
            P.to_csv(out / "post_exit_vs_spy.csv", index=False)
            res["post_exit_vs_spy"] = post_summary(P)
    cc = C[C["status"] == "closed"].rename(columns={})
    A["all_candidates_10bps"] = split_summary(split_execution(cc, data, 10))
    A["non_overlap_10bps"] = split_summary(split_execution(non_overlap(C).query("status == 'closed'"), data, 10))
    res["execution_audit"] = A
    # H3 bookkeeping
    h3s = sets["H3"]
    res["h3_changes"] = dict(time_exits=int((C["reason"] == "time").sum()), extended=int((h3s["h3"] == "extended").sum()),
                             by_reason=h3s.loc[h3s["h3"] == "extended", "reason"].value_counts().to_dict())
    # random removal (H1, H2)
    s0, s1 = windows["full"]
    rnd = {h: random_removal(C, data, s0, s1, len(C) - len(sets[h]), a.n_random, a.workers) for h in ("H1", "H2")}
    res["random_removal"] = rnd
    res["decision"] = decide(res["books"], rnd)
    res["charts"] = charts(out, res, curves, A, rnd)
    res["provenance"] = dict(commit=subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip(),
                             prereg_sha256=hashlib.sha256((ROOT / res["prereg"]).read_bytes()).hexdigest(),
                             reference_sha256=hashlib.sha256(REF.read_bytes()).hexdigest())
    (out / "results.json").write_text(json.dumps(res, indent=1, default=str))
    report(res, out)
    print(json.dumps(dict(out=str(out), reproduction=res["reproduction"], decision={k: v["verdict"] for k, v in res["decision"].items()}),
                     indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
