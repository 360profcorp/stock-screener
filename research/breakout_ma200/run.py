"""Breakout + MA200 — Quality & Exit Study v1 (PREREG_MA200_QE.md). Exploratory, research only.

    python -m research.breakout_ma200.run --dataset DIR [--workers 4] [--n-random 200]

Stage 1: diagnostic of control M (PR #19 variant M) from its own trades.
Stage 2: A (quality filter: (open - stop)/open >= 4 %) and B (runner exit) as independent
full portfolio replays. Stage 3: 10/25/50 bps, full window and both halves, SPY, random-removal
benchmark for A. Checks: reproduction of PR #19 (fail closed), next-open execution, no
look-ahead, missing history of former members.
"""
import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import portfolio_bt as pf
from research.breakout_ma200 import tools as T
from research.crisis import run as CR
from research.long_diagnostic import run as LD
from research.sp1500 import universe as U

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / "research/results/crisis/runs/2026-10-25T0255Z/results.json"
COSTS = (10, 25, 50)
A_MIN_RISK = 0.04
B_MIN_R, B_ATR_K, B_MAX_BARS, BASE_BARS = 2.0, 2.0, 40, 20
WIN_NAMES = {"full": "full", "y2017_2021": "development", "y2022_2026": "holdout"}


# =====================================================================
# hypotheses
# =====================================================================
def quality_filter(tr, min_risk=A_MIN_RISK):
    """A: keep a candidate only if (actual entry - original stop) / entry >= min_risk."""
    risk = (tr["entry"] - tr["stop"]) / tr["entry"]
    return tr[risk >= min_risk].reset_index(drop=True)


def runner_exit(row, x, min_r=B_MIN_R, k_atr=B_ATR_K, max_bars=B_MAX_BARS, base=BASE_BARS):
    """B for one control trade (PREREG §3 B). Returns updated fields, or {} if unchanged."""
    if row["reason"] != "time" or row["status"] != "closed":
        return {}
    e, d = T.idx_of(x, row["date"])
    j20 = e + base
    if pd.Timestamp(d[j20]) != pd.Timestamp(row["exit_date"]).normalize():
        raise ValueError("time exit is not at bar e+20")
    O, L, C = (np.asarray(x[k], dtype=float) for k in ("O", "L", "C"))
    atr = np.asarray(x["atr14"], dtype=float)
    entry, stop = float(row["entry"]), float(row["stop"])
    R = entry - stop
    if (C[j20] - entry) / R < min_r:
        return {}
    level, hc = stop, float(np.max(C[e:j20 + 1]))          # hc = max close(e .. j-1) for j = e+21
    last = len(C) - 1
    for j in range(j20 + 1, min(e + max_bars, last) + 1):
        a = atr[j - 1]
        if np.isfinite(a):
            level = max(level, stop, hc - k_atr * a)
        if L[j] <= level:
            px = min(O[j], level)
            return dict(exit_date=d[j], exit=float(px), reason="runner_stop", status="closed", days=j - e,
                        ret_pct=(px / entry - 1) * 100, r=(px - entry) / R, runner=True)
        hc = max(hc, float(C[j]))
        if j == e + max_bars:
            return dict(exit_date=d[j], exit=float(C[j]), reason="runner_time40", status="closed", days=j - e,
                        ret_pct=(C[j] / entry - 1) * 100, r=(C[j] - entry) / R, runner=True)
    mark = float(C[last])
    return dict(exit_date=pd.NaT, exit=np.nan, reason="open", status="open", days=last - e, ret_pct=np.nan,
                r=np.nan, mark_date=d[last], mark=mark, mark_r=(mark - entry) / R, runner=True)


def runner_book(tr, data):
    out = tr.copy()
    out["runner"] = False
    out["r_at_day20"] = np.nan
    for k, row in out.iterrows():
        upd = runner_exit(row, data[row["ticker"]])
        if upd:
            out.at[k, "r_at_day20"] = (row["exit"] - row["entry"]) / (row["entry"] - row["stop"])
        for c, v in upd.items():
            out.at[k, c] = v
    return out


# =====================================================================
# metrics
# =====================================================================
def book(tr, data, s0, s1, bps, spy, decisions=False):
    curve, ex, m = pf.replay(tr, data, start=s0, end=s1, open_at_end="mark", cost_bps=float(bps),
                             record_decisions=decisions, **CR.CFG)
    met = CR.metrics(curve, ex, m, spy)
    eq = curve["equity"]
    years = (curve["date"].iloc[-1] - curve["date"].iloc[0]).days / 365.25
    notional = float((ex["shares"] * (ex["entry"] + ex["exit"])).sum()) if len(ex) else 0.0
    notional += sum(p["shares"] * p["entry"] for p in m["open_positions"])
    met.update(win_rate_pct=float(100 * (ex["net_pnl"] > 0).mean()) if len(ex) else None,
               turnover_per_year=float(notional / eq.mean() / years) if years > 0 else None,
               invested_pct=float(100 * ((curve["equity"] - curve["cash"]) / curve["equity"]).mean()),
               skipped=m["skipped"], open_end=len(m["open_positions"]))
    return met, curve, ex, m


def spy_stats(spy, s0, s1):
    c = spy["Close"].astype(float).copy()
    c.index = pd.DatetimeIndex(c.index).normalize()
    prev = c[c.index < s0]
    w = c[(c.index >= s0) & (c.index <= s1)]
    base = prev.iloc[-1] if len(prev) else w.iloc[0]
    path = pd.concat([pd.Series([base]), w.reset_index(drop=True)])
    years = (w.index[-1] - s0).days / 365.25
    ret = w.iloc[-1] / base - 1
    return dict(return_pct=float(100 * ret), cagr_pct=float(100 * ((1 + ret) ** (1 / years) - 1)),
                max_dd_pct=float(100 * (path / path.cummax() - 1).min()), invested_pct=100.0)


# =====================================================================
# checks
# =====================================================================
def next_open_check(tr, data):
    bad = []
    for r in tr.itertuples(index=False):
        x = data[r.ticker]
        i, d = T.idx_of(x, r.signal_date)
        if i + 1 >= len(d) or pd.Timestamp(d[i + 1]) != pd.Timestamp(r.date) or \
                not np.isclose(float(np.asarray(x["O"])[i + 1]), float(r.entry)):
            bad.append((r.ticker, str(r.signal_date)[:10], str(r.date)[:10]))
    return dict(candidates=int(len(tr)), violations=len(bad), examples=bad[:10])


def no_lookahead(frames, spy, pit_text, full, cut="2021-12-31", until="2021-11-30"):
    c = pd.Timestamp(cut)
    sig, data, _, _ = CR.build({t: f[f.index <= c] for t, f in frames.items()}, spy[spy.index <= c], pit_text)
    a = CR.trades_for(CR.eligible(sig, True), data, "breakout")
    k = ["ticker", "date"]
    x = a[a["date"] <= until].set_index(k).sort_index()
    y = full[full["date"] <= until].set_index(k).sort_index()
    same = x.index.equals(y.index) and np.allclose(x["entry"], y["entry"]) and np.allclose(x["stop"], y["stop"]) \
        and np.allclose(x["rs"].fillna(-1), y["rs"].fillna(-1))
    return dict(candidates_truncated=int(len(x)), candidates_full=int(len(y)), identical=bool(same))


def missing_history(frames, spy, pit_text):
    uni = pd.read_csv(CR.UNIVERSE_CSV)
    cal = pd.DatetimeIndex(spy.index)
    cur500 = set(uni.loc[uni["group"] == "sp500", "ticker"])
    tl = U.pit_from_snapshots(U.parse_pit500(pit_text), cur500, cal[-1])
    have = {t: set(pd.DatetimeIndex(f.index).normalize()) for t, f in frames.items()}
    rows = []
    for d in cal[cal >= "2017-01-01"][::21]:
        mem = U.member_on(tl, d)
        miss = [t for t in mem if d not in have.get(t, ())]
        rows.append(dict(date=d, members=len(mem), without_price=len(miss)))
    D = pd.DataFrame(rows)
    D["year"] = D["date"].dt.year
    by = D.groupby("year").agg(members=("members", "mean"), without_price=("without_price", "mean"))
    by["share_pct"] = 100 * by["without_price"] / by["members"]
    ever = set().union(*[U.member_on(tl, d) for d in cal[::5]]) | cur500
    return dict(by_year={int(k): {a: round(float(b), 2) for a, b in v.items()} for k, v in by.to_dict("index").items()},
                ever_members=len(ever), ever_members_without_any_price=len([t for t in ever if t not in frames]))


# =====================================================================
# stage 1 helpers
# =====================================================================
def monthly(curve, ex, years, initial=10000.):
    eq = curve.set_index("date")["equity"]
    out = {}
    for y in years:
        m_ = eq[eq.index.year == y]
        prev = eq[eq.index < f"{y}-01-01"]
        base = prev.iloc[-1] if len(prev) else initial
        me = m_.groupby(m_.index.month).last()
        mp = me.shift(1).fillna(base)
        e = ex[pd.to_datetime(ex["exit_date"]).dt.year == y]
        mo = pd.to_datetime(e["exit_date"]).dt.month
        cv = curve[curve["date"].dt.year == y]
        inv = ((cv["equity"] - cv["cash"]) / cv["equity"]).groupby(cv["date"].dt.month).mean() * 100
        out[str(y)] = {int(k): dict(book_pct=round(float((me[k] / mp[k] - 1) * 100), 2), exits=int((mo == k).sum()),
                                    stops=int(((mo == k) & (e["reason"] == "stop")).sum()),
                                    pnl_usd=round(float(e.loc[mo == k, "net_pnl"].sum()), 2),
                                    invested_pct=round(float(inv.get(k, np.nan)), 1)) for k in me.index}
    return out


def removed_by_ma200(C, M, bps=10):
    k = ["ticker", "date"]
    r = C.merge(M[k].assign(_m=1), on=k, how="left")
    r = r[r["_m"].isna() & (r["status"] == "closed")].copy()
    f = bps / 1e4
    r["hypo_net_r"] = (r["exit"] * (1 - f) - r["entry"] * (1 + f)) / (r["entry"] - r["stop"])
    r["year"] = pd.to_datetime(r["signal_date"]).dt.year
    return {int(y): dict(n=int(len(g)), mean_r=round(float(g["hypo_net_r"].mean()), 3),
                         win_pct=round(float(100 * (g["hypo_net_r"] > 0).mean()), 1)) for y, g in r.groupby("year")}


# =====================================================================
# decision
# =====================================================================
def decide(B, rnd_a):
    m = lambda w, b: B[f"M|{w}|{b}"]                                         # noqa: E731
    out = {}
    for h in ("A", "B"):
        x = lambda w, b: B[f"{h}|{w}|{b}"]                                  # noqa: E731
        crit = {"CAGR > M full at 10 and 25": all(x("full", b)["cagr_pct"] > m("full", b)["cagr_pct"] for b in (10, 25)),
                "PF > M full at 10 and 25": all((x("full", b)["profit_factor"] or 0) > (m("full", b)["profit_factor"] or 0)
                                                for b in (10, 25)),
                "max DD not > 3 pt deeper (full 10)": x("full", 10)["max_dd_pct"] >= m("full", 10)["max_dd_pct"] - 3,
                "CAGR > M in 2017-2021 and 2022-2026 (10)": all(x(w, 10)["cagr_pct"] > m(w, 10)["cagr_pct"]
                                                               for w in ("y2017_2021", "y2022_2026"))}
        if h == "A":
            crit["return > random-removal p80 (full 10)"] = x("full", 10)["return_pct"] > rnd_a["p80"]
        out[h] = dict(passed={k: bool(v) for k, v in crit.items()},
                      verdict="supported (exploratory)" if all(crit.values()) else "not supported")
    return out


# =====================================================================
# charts / report
# =====================================================================
def charts(out, res, curves, spy, rnd, runners):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fs = []

    def save(fig, n):
        fig.tight_layout()
        fig.savefig(out / n, dpi=110)
        plt.close(fig)
        fs.append(n)
    fig, ax = plt.subplots(3, 1, figsize=(10, 11))
    for i, w in enumerate(("full", "y2017_2021", "y2022_2026")):
        for k in ("M", "A", "B"):
            c = curves[(k, w)]
            ax[i].plot(c["date"], c["equity"], label=k, lw=1.6 if k == "M" else 1)
        s = spy["Close"].copy()
        s.index = pd.DatetimeIndex(s.index).normalize()
        c0 = curves[("M", w)]
        s = s[(s.index >= c0["date"].iloc[0]) & (s.index <= c0["date"].iloc[-1])]
        ax[i].plot(s.index, 10000 * s / s.iloc[0], color="grey", alpha=.6, label="SPY price")
        ax[i].set_title(f"{w}, 10 bps (fresh $10,000)")
        ax[i].legend()
    save(fig, "books.png")
    fig, ax = plt.subplots(figsize=(8, 4))
    xi = np.arange(len(COSTS))
    for j, k in enumerate(("M", "A", "B")):
        ax.bar(xi + (j - 1) * .27, [res["books"][f"{k}|full|{b}"]["cagr_pct"] for b in COSTS], .27, label=k)
    ax.set_xticks(xi, [f"{b} bps" for b in COSTS])
    ax.axhline(0, color="k", lw=.5)
    ax.set_ylabel("CAGR %")
    ax.legend()
    ax.set_title("Full window: CAGR by cost per side")
    save(fig, "costs.png")
    fig, ax = plt.subplots(figsize=(10, 4))
    yrs = sorted(res["books"]["M|full|10"]["yearly_return_pct"])
    for j, k in enumerate(("M", "A", "B")):
        y = res["books"][f"{k}|full|10"]["yearly_return_pct"]
        ax.bar(np.arange(len(yrs)) + (j - 1) * .27, [y[t] for t in yrs], .27, label=k)
    ax.set_xticks(np.arange(len(yrs)), yrs)
    ax.axhline(0, color="k", lw=.5)
    ax.legend()
    ax.set_title("Calendar-year return, full window, 10 bps")
    save(fig, "years.png")
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(rnd["returns"], bins=30, alpha=.6, label=f"random removal of {rnd['removed']} candidates")
    ax.axvline(res["books"]["A|full|10"]["return_pct"], color="k", ls="--", label="A")
    ax.axvline(res["books"]["M|full|10"]["return_pct"], color="grey", label="M")
    ax.legend()
    ax.set_title("A vs random removal (full, 10 bps)")
    save(fig, "random_removal.png")
    if len(runners):
        fig, ax = plt.subplots(figsize=(7, 5))
        ax.scatter(runners["r_at_day20"], runners["r"], s=10, alpha=.6)
        lim = [0, max(runners["r_at_day20"].max(), runners["r"].max()) + 1]
        ax.plot(lim, lim, color="k", lw=.5)
        ax.set_xlabel("R at the close of day 20 (M's exit)")
        ax.set_ylabel("R at the runner exit (B)")
        ax.set_title("B runners: candidate-level outcome vs M's day-20 exit")
        save(fig, "runners.png")
    s = res["stage1"]["execution_split_10bps"]
    keys = ["signal_quality", "entry_gap", "stop_gap", "costs"]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(keys + ["net"], [s[k + "_usd"] for k in keys] + [s["net_usd"]],
           color=["tab:blue", "tab:orange", "tab:red", "tab:grey", "k"])
    ax.axhline(0, color="k", lw=.5)
    ax.set_title("Control M, 10 bps: signal quality vs execution ($)")
    save(fig, "M_execution_split.png")
    return fs


def f(v, s="{:+.1f}"):
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else s.format(v)


def report(res, out):
    B, S1 = res["books"], res["stage1"]
    d = S1["diag"]
    L = ["# Breakout + MA200 — Quality & Exit Study v1 (exploratory)", "",
         "Pre-registration: `research/breakout_ma200/PREREG_MA200_QE.md` (committed before any calculation). The ten years "
         "were already examined (PR #19, #22): **nothing here confirms a strategy**; only a future independent forward test "
         "can. Research Breakout buys at the **next session's open** — this is **not** a test of `trader.py`'s pre-close "
         "purchases. No paper book is started.", "",
         "## Checks", "",
         f"- Reproduction of PR #19 variant M (tolerance 1e-6, trade count equal): {res['reproduction']}",
         f"- Next-open execution: {res['checks']['next_open']['violations']} violations in "
         f"{res['checks']['next_open']['candidates']} M candidates (entry = the stock's next session open after the signal).",
         f"- No look-ahead (detection cut at 2021-12-31, entries to 2021-11-30): {res['checks']['no_lookahead']}.",
         f"- Money reconciliation M 10 bps: {S1['reconciliation']}.",
         f"- Former members without any price history: {res['checks']['missing_history']['ever_members_without_any_price']} of "
         f"{res['checks']['missing_history']['ever_members']}; PIT member-days without a price by year (mean share): "
         + ", ".join(f"{y}: {v['share_pct']:.1f} %" for y, v in res['checks']['missing_history']['by_year'].items())
         + ". Their effect on returns cannot be measured (survivorship); it is a limitation of every number below.", "",
         "## Stage 1 — diagnostic of control M (from M's own trades)", "", "![M equity](M_equity.png)", "",
         "| Component | $ |", "|---|---:|"]
    L += [f"| {k} | {v:,.2f} |" for k, v in d["decomposition_usd"].items()]
    xr = d["expectancy_r"] if "expectancy_r" in d else None
    c = d["closed"]
    L += ["", f"Closed trades {c['trades']}: win rate {c['win_rate_pct']:.1f} %, mean {c['mean_r']:+.3f} R (avg win "
          f"{c['avg_win_r']:+.2f} R, avg loss {c['avg_loss_r']:+.2f} R), PF {c['profit_factor']:.2f}; gross {d['costs']['mean_gross_r']:+.3f} R, "
          f"costs {d['costs']['mean_cost_r']:.3f} R per trade.", "", "![split](M_execution_split.png)", "",
          "| Exact split (risk at the signal close) | Signal quality | Entry gap | Stop gap | Costs | Net |", "|---|---:|---:|---:|---:|---:|"]
    for bps in (10, 25):
        s = S1[f"execution_split_{bps}bps"]
        L.append(f"| executed, {bps} bps ($) | {s['signal_quality_usd']:,.0f} | {s['entry_gap_usd']:,.0f} | {s['stop_gap_usd']:,.0f} | "
                 f"{s['costs_usd']:,.0f} | {s['net_usd']:,.0f} |")
        L.append(f"| executed, {bps} bps (R/trade) | {s['signal_quality_r_per_trade']:+.3f} | {s['entry_gap_r_per_trade']:+.3f} | "
                 f"{s['stop_gap_r_per_trade']:+.3f} | {s['costs_r_per_trade']:+.3f} | {s['net_r_sig_per_trade']:+.3f} |")
    e = d["exits"]
    L += ["", "### Exits", "", "![exits](M_exits.png)", "", "| Reason | Trades | Net P&L | Mean R | Win % | MFE R |", "|---|---:|---:|---:|---:|---:|"]
    for r_, v in e["by_reason"].items():
        L.append(f"| {r_} | {v['trades']} | ${v['total_pnl_usd']:,.0f} | {v['mean_r']:+.3f} | {v['win_rate_pct']:.1f} | {f(v.get('mfe_r_mean'), '{:.2f}')} |")
    g = d["gap_through_stop"]
    L += ["", f"- Entry-day stops {e['entry_day_stops']}; stops that had been ≥ +1 R before the exit day "
          f"{e['stops_that_were_up_1r_before_the_exit_day']}; gaps through the stop {g['trades']} (extra ${g['total_extra_loss_usd']:,.0f}).",
          f"- Time exits: mean MFE {e['time_exit_mfe_r_mean']:.2f} R, kept {e['time_exit_final_r_mean']:+.2f} R.", "",
          "![mfe](M_mfe.png)", "", "| After the exit vs SPY (hindsight) | Horizon | n | Stock % | SPY % | Excess mean | Excess > 0 | 90 % CI |",
          "|---|---|---:|---:|---:|---:|---:|---|"]
    for grp, v in S1["post_exit_vs_spy"].items():
        for h in T.HORIZONS:
            x = v[f"+{h}"]
            L.append(f"| {grp} | +{h} | {x['n']} | {x['stock_mean_pct']:+.2f} | {x['spy_mean_pct']:+.2f} | {x['excess_mean_pct']:+.2f} | "
                     f"{x['excess_positive_pct']:.0f} % | [{x['excess_ci90'][0]:+.2f}, {x['excess_ci90'][1]:+.2f}] |")
    k = d["concentration"]
    L += ["", "### Entry quality, RS, concentration", "", "| Group | Value | Trades | Mean R | Win % | P&L |", "|---|---|---:|---:|---:|---:|"]
    for gname in ("by_rs_bucket", "by_risk_bucket", "by_cohort"):
        for kk, v in d[gname].items():
            L.append(f"| {gname[3:]} | {kk} | {v['trades']} | {v['mean_r']:+.3f} | {v['win_rate_pct']:.1f} | ${v['total_pnl_usd']:,.0f} |")
    L += ["", f"Top 10 winners ${k['top10_pnl_usd']:,.0f}; without them ${k['remainder_without_top10_usd']:,.0f} (arithmetic). "
          f"Trades ≥ 3 R: {k['trades_r_ge_3']} (${k['pnl_of_r_ge_3_usd']:,.0f}).", "", "![conc](M_concentration.png)", "",
          "| Funnel | Count | Mean R | Win % |", "|---|---:|---:|---:|"]
    for kk, v in d["funnel"].items():
        if isinstance(v, dict):
            L.append(f"| {kk} | {v['count']} | {v.get('mean_r', 0):+.3f} | {v.get('win_rate_pct', 0):.1f} |")
    L += ["", "| Portfolio decision | Count | Hypothetical mean R |", "|---|---:|---:|"]
    for kk, v in d["candidate_decisions"].items():
        L.append(f"| {kk} | {v['count']} | {f(v.get('hypothetical_mean_r'), '{:+.3f}')} |")
    x = d["exposure"]
    L += ["", f"Capital: invested {x['average_invested_pct']:.1f} % on average, {x['avg_open_positions']:.2f} positions, fully in cash "
          f"{x['fully_cash_pct']:.1f} % of sessions, all slots full {x['full_five_slots_pct']:.1f} %.", "", "![exposure](M_exposure.png)", "",
          "### Years, and 2018 / 2019 / 2021 in detail", "", "![years](M_years.png)", "",
          "| Year | M | SPY price | Exits | Win % | Mean R |", "|---|---:|---:|---:|---:|---:|"]
    for y, v in d["calendar_years"].items():
        xx = v["exits"]
        L.append(f"| {y} | {v['book_return_pct']:+.1f} % | {v['spy_price_return_pct']:+.1f} % | {xx.get('trades', 0)} | "
                 f"{xx.get('win_rate_pct', 0):.1f} | {xx.get('mean_r', 0):+.3f} |")
    for y, mm in S1["monthly"].items():
        L += ["", f"**{y} by month** (book %, stops/exits, P&L, invested %): " + "; ".join(
            f"{kk}: {v['book_pct']:+.1f} % ({v['stops']}/{v['exits']}, ${v['pnl_usd']:,.0f}, {v['invested_pct']:.0f} %)" for kk, v in mm.items())]
    L += ["", "Control-C candidates removed by the MA200 filter (hypothetical net R at 10 bps, by signal year): "
          + "; ".join(f"{y}: n={v['n']}, {v['mean_r']:+.3f} R, {v['win_pct']:.0f} % wins" for y, v in S1["removed_by_ma200"].items()), "",
          "## Stages 2–3 — hypotheses A and B (independent full replays)", "", "![books](books.png)", "",
          "| Book | Window | bps | Return | CAGR | Max DD | PF | Exp. R | Win % | Trades | Turnover/yr | Invested % |",
          "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for kk, m in B.items():
        b, w, cc = kk.split("|")
        L.append(f"| {b} | {w} | {cc} | {m['return_pct']:+.1f} % | {f(m['cagr_pct'])} % | {m['max_dd_pct']:.1f} % | "
                 f"{f(m['profit_factor'], '{:.2f}')} | {f(m['expectancy_r'], '{:+.3f}')} | {f(m['win_rate_pct'], '{:.1f}')} | "
                 f"{m['trades']} | {f(m['turnover_per_year'], '{:.1f}')}× | {m['invested_pct']:.0f} |")
    L += ["", "| SPY price only | Window | Return | CAGR | Max DD | Invested |", "|---|---|---:|---:|---:|---:|"]
    for w, v in res["spy"].items():
        L.append(f"| SPY | {w} | {v['return_pct']:+.1f} % | {v['cagr_pct']:+.1f} % | {v['max_dd_pct']:.1f} % | 100 % |")
    L += ["", "The books risk 1 % per trade with at most 5 positions and are invested only part of the time (see Invested %), so "
          "their return and drawdown are not comparable one-to-one with a fully invested SPY; SPY is price only (no "
          "dividends), and the books earn no cash interest.", "", "![costs](costs.png)", "", "![years](years.png)", "",
          "![rnd](random_removal.png)", "", f"A removed {res['random_removal_A']['removed']} of {res['candidates']['M']} candidates. Random "
          f"removal of the same number (200 seeds, full 10 bps): p20 / p50 / p80 / p95 = {res['random_removal_A']['p20']:+.1f} / "
          f"{res['random_removal_A']['p50']:+.1f} / {res['random_removal_A']['p80']:+.1f} / {res['random_removal_A']['p95']:+.1f} %.", ""]
    rb = res["runners"]
    L += [f"B: {rb['runners']} of {rb['time_exits']} time exits had ≥ +2 R at day 20 and became runners; exits {rb['by_reason']}; "
          f"candidate-level mean R at the runner exit {f(rb['mean_r_runner_exit'], '{:+.2f}')} vs {f(rb['mean_r_day20'], '{:+.2f}')} at day 20 "
          f"(candidate level, not portfolio). Skips 'positions' full 10 bps: M {B['M|full|10']['skipped'].get('positions')}, "
          f"B {B['B|full|10']['skipped'].get('positions')}.", "", "![runners](runners.png)", "",
          "## Decision (pre-registered, applied unchanged)", "", "| Hypothesis | Criteria | Verdict |", "|---|---|---|"]
    for h, v in res["decision"].items():
        L.append(f"| {h} | " + "; ".join(f"{kk}: {'yes' if vv else 'no'}" for kk, vv in v["passed"].items()) + f" | **{v['verdict']}** |")
    L += ["", "Even a 'supported' verdict is only a candidate for a separately approved forward test. A+B was not tested.", ""]
    (out / "REPORT.md").write_text("\n".join(L) + "\n")


# =====================================================================
# main
# =====================================================================
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--out", default=str(ROOT / "research/results/breakout_ma200/runs"))
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--n-random", type=int, default=200)
    ap.add_argument("--skip-lookahead", action="store_true")
    a = ap.parse_args(argv)
    out = Path(a.out) / datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    out.mkdir(parents=True, exist_ok=False)
    frames, spy, pit_text, dsha = CR.load(a.dataset)
    sig, data, cal, info = CR.build(frames, spy, pit_text)
    start, end = cal[min(260, len(cal) - 1)], cal[-1]
    windows = dict(full=(start, end), y2017_2021=(start, pd.Timestamp("2021-12-31")),
                   y2022_2026=(cal[cal >= CR.HOLDOUT][0], end))
    M = CR.trades_for(CR.eligible(sig, True), data, "breakout")
    Cc = CR.trades_for(CR.eligible(sig, False), data, "breakout")
    Bt = runner_book(M, data)
    sets = dict(M=M, A=quality_filter(M), B=Bt)
    ref = json.loads(REF.read_text())["books"]
    res = dict(prereg="research/breakout_ma200/PREREG_MA200_QE.md", dataset_sha256=dsha, data=info,
               windows={k: [str(v[0].date()), str(v[1].date())] for k, v in windows.items()},
               candidates={k: int(len(v)) for k, v in sets.items()}, reproduction={}, books={}, spy={})
    curves = {}
    for name, tr in sets.items():
        for w, (s0, s1) in windows.items():
            for bps in COSTS:
                met, curve, ex, m = book(tr, data, s0, s1, bps, spy, decisions=(name == "M" and w == "full" and bps == 10))
                res["books"][f"{name}|{w}|{bps}"] = met
                if name == "M" and bps in (10, 25):
                    anc = ref[f"breakout|M|{WIN_NAMES[w]}|{bps}bps"]
                    diff = (met["return_pct"] - anc["return_pct"], met["max_dd_pct"] - anc["max_dd_pct"], met["trades"] - anc["trades"])
                    if abs(diff[0]) > 1e-6 or abs(diff[1]) > 1e-6 or diff[2]:
                        raise RuntimeError(f"STOP: M does not reproduce PR #19 ({w}, {bps} bps): {diff}")
                    res["reproduction"][f"{w} {bps} bps"] = "exact"
                if bps == 10:
                    curves[(name, w)] = curve
                    if w == "full":
                        ex.to_csv(out / f"trades_{name}.csv", index=False)
                        curve[["date", "equity", "cash", "open_positions"]].to_csv(out / f"equity_{name}.csv", index=False)
                if name == "M" and w == "full" and bps in (10, 25):
                    if bps == 10:
                        m10, c10, e10 = m, curve, ex
                    else:
                        c25, e25 = curve, ex
        for w, (s0, s1) in windows.items():
            res["spy"][w] = spy_stats(spy, s0, s1)
    # ---- stage 1: diagnostic of M
    obs, diag = LD.make_diagnostics(M, e10, c10, m10, data, spy, 10)
    obs.to_csv(out / "M_closed_diagnostic.csv", index=False)
    S1 = dict(reconciliation={kk: (round(v, 4) if isinstance(v, float) else v) for kk, v in
                              LD.reconcile(c10, e10, m10["open_positions"], CR.CFG["initial_cash"], 10).items()})
    for bps, ex in ((10, e10), (25, e25)):
        e = T.with_shares(ex, M)
        dsp = T.split_execution(e, data, bps)
        S1[f"execution_split_{bps}bps"] = T.split_summary(dsp)
        if bps == 10:
            dsp.to_csv(out / "M_execution_split.csv", index=False)
            P = T.post_exit_vs_spy(dsp, data, spy)
            P.to_csv(out / "M_post_exit_vs_spy.csv", index=False)
            S1["post_exit_vs_spy"] = T.post_summary(P)
    diag["cost_sensitivity"] = dict(return_10bps_pct=res["books"]["M|full|10"]["return_pct"],
                                    return_25bps_pct=res["books"]["M|full|25"]["return_pct"])
    S1["monthly"] = monthly(c10, obs, (2018, 2019, 2021))
    S1["removed_by_ma200"] = removed_by_ma200(Cc, M)
    S1["diag"] = diag
    S1["charts"] = LD.charts(out, "M", {10: c10, 25: c25}, obs, spy, diag)
    res["stage1"] = S1
    # ---- runners (candidate level)
    rn = Bt[Bt["runner"]]
    res["runners"] = dict(time_exits=int((M["reason"] == "time").sum()), runners=int(len(rn)),
                          by_reason=rn["reason"].value_counts().to_dict(),
                          mean_r_day20=float(rn["r_at_day20"].mean()) if len(rn) else None,
                          mean_r_runner_exit=float(rn["r"].dropna().mean()) if len(rn) else None)
    # ---- benchmark and checks
    s0, s1 = windows["full"]
    rnd = T.random_removal(M, data, s0, s1, len(M) - len(sets["A"]), a.n_random, a.workers)
    res["random_removal_A"] = rnd
    res["checks"] = dict(next_open=next_open_check(M, data), missing_history=missing_history(frames, spy, pit_text))
    res["checks"]["no_lookahead"] = (dict(skipped=True) if a.skip_lookahead
                                     else no_lookahead(frames, spy, pit_text, M))
    if res["checks"]["next_open"]["violations"] or not res["checks"]["no_lookahead"].get("identical", True):
        raise RuntimeError(f"STOP: check failed {res['checks']}")
    res["decision"] = decide(res["books"], rnd)
    res["charts"] = charts(out, res, curves, spy, rnd, rn.dropna(subset=["r"]))
    res["provenance"] = dict(commit=subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip(),
                             prereg_sha256=hashlib.sha256((ROOT / res["prereg"]).read_bytes()).hexdigest(),
                             reference_sha256=hashlib.sha256(REF.read_bytes()).hexdigest(),
                             production_diff_vs_main=subprocess.run(["git", "diff", "--stat", "origin/main", "--", "paper", "state",
                                                                     "trader.py", "core.py"], capture_output=True, text=True,
                                                                    cwd=ROOT).stdout.strip())
    (out / "results.json").write_text(json.dumps(res, indent=1, default=str))
    report(res, out)
    print(json.dumps(dict(out=str(out), reproduction=res["reproduction"], decision={k: v["verdict"] for k, v in res["decision"].items()}),
                     indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
