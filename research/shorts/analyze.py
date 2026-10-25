"""Short strategies, 10-year analysis (PREREG_SHORTS.md). Research only.

    python -m research.shorts.analyze --dataset DIR

DIR: the 10-year dataset artifact of research.sp1500.run (signals.csv.gz, bars.pkl.gz).
Writes a new write-once directory research/results/shorts/runs/<run_id>/.
"""
import argparse
import gzip
import hashlib
import io
import json
import pickle
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from research.shorts import portfolio as PF
from research.sp1500 import engine as E
from research.sp1500 import rules as R
from research.sp1500 import run as RUN

ROOT = Path(__file__).resolve().parents[2]
SHORTS = list(R.SHORT_RULES)
SLIPS = list(R.SLIPPAGE_SCENARIOS_BPS)                          # base, wide, stress
BORROWS = [b for b, v in R.BORROW_SCENARIOS_APR.items() if v is not None]   # gc warm hot htb
SCEN = ["gross_r"] + [f"net_r_{s}_{b}" for s in SLIPS for b in BORROWS]
PRIMARY = "net_r_base_warm"
SEED, N_BOOT = 20261024, 5000
HOLDOUT_START = pd.Timestamp("2022-01-01")
PERIODS = {"covid_crash": ("2020-02-20", "2020-03-23"),
           "covid_recovery": ("2020-03-24", "2020-12-31"),
           "bear_2022": ("2022-01-03", "2022-10-12"),
           "rebound_2022": ("2022-10-13", "2023-07-31"),
           "other_2023_2026": ("2023-08-01", "2100-01-01")}
POPS = {"pit500": ("rs_pit500", None), "sp500": ("rs_ref500", ["sp500"]),
        "sp1500": ("rs_1500", ["sp500", "sp400", "sp600"]),
        "sp1500_with_ambiguous": ("rs_1500", ["sp500", "sp400", "sp600", "ambiguous"])}


def tb(s):
    return s.map(lambda v: v if isinstance(v, bool) else str(v).lower() == "true")


def load(d):
    d = Path(d)
    sig, bars = next(d.rglob("signals.csv.gz")), next(d.rglob("bars.pkl.gz"))
    sha = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (sig, bars)}
    lab = pd.read_csv(sig, low_memory=False)
    for c in ("signal_date", "entry_date", "exit_date"):
        lab[c] = pd.to_datetime(lab[c], errors="coerce")
    b = pickle.load(io.BytesIO(gzip.decompress(bars.read_bytes())))
    return lab, b["frames"], b["spy"], sha


# ---------------------------------------------------------------- eligibility (independent)
def eligible(s: pd.DataFrame, rs_col: str, market: str) -> pd.Series:
    """Written out from PREREG §3, NOT via the engine, so it can audit the engine's columns."""
    ok = (s[rs_col] <= R.MAX_RS_SHORT) & (s["close"] >= R.MIN_PRICE) & \
        (s["adv20_usd"] >= R.MIN_ADV_USD) & (s["risk_at_close_pct"] > 0)
    if market == "primary":
        ok &= tb(s["spy_above50"].astype(str)) == False                      # noqa: E712
        ok &= s["spy_above50"].notna()
    return ok.fillna(False)


def population(lab, pop, market):
    s = lab[lab["direction"] == "short"]
    rs, groups = POPS[pop]
    m = tb(s["pit_member_sp500"].astype(str)) if groups is None else s["group"].isin(groups)
    s = s[m]
    return s[eligible(s, rs, market)].copy()


# ---------------------------------------------------------------- audits
def audit(lab, spy):
    s = lab[lab["direction"] == "short"].copy()
    out = {}
    for col, rs, mk in (("eligible_primary", "rs_ref500", "primary"),
                        ("eligible_off", "rs_ref500", "off"),
                        ("eligible_pit_primary", "rs_pit500", "primary"),
                        ("eligible_rs1500_primary", "rs_1500", "primary")):
        stored = tb(s[col].astype(str))
        mine = eligible(s, rs, mk)
        out[col] = dict(rows=int(len(s)), stored=int(stored.sum()), recomputed=int(mine.sum()),
                        mismatches=int((stored != mine).sum()))
    ep = tb(s["eligible_primary"].astype(str))
    out["primary_requires_spy_below_ma50"] = dict(
        eligible=int(ep.sum()),
        with_spy_above50=int((ep & (tb(s["spy_above50"].astype(str)) == True)).sum()))  # noqa: E712
    eo = tb(s["eligible_off"].astype(str))
    out["off_includes_spy_above_ma50"] = int((eo & (tb(s["spy_above50"].astype(str)) == True)).sum())  # noqa: E712
    # costs recomputed from the trade's own fields
    c = s[s["trade_status"] == "closed"]
    risk = c["risk_pct"] / 100
    gross_ret = -(c["exit"] / c["entry"] - 1)
    worst = {"gross_r": float((gross_ret / risk - c["gross_r"]).abs().max())}
    div = c["dividends_ps"].fillna(0) / c["entry"]
    for sl, bps in R.SLIPPAGE_SCENARIOS_BPS.items():
        cost = bps / 1e4 * (c["entry"] + c["exit"]) / c["entry"]
        for b in BORROWS:
            apr = R.BORROW_SCENARIOS_APR[b]
            net = (gross_ret - cost - apr * np.maximum(1, c["calendar_days"]) / 365 - div) / risk
            worst[f"net_r_{sl}_{b}"] = float((net - c[f"net_r_{sl}_{b}"]).abs().max())
    out["cost_recompute_max_abs_diff_r"] = worst
    out["dividends"] = dict(closed_trades=int(len(c)),
                            trades_paying_dividends=int((c["dividends_ps"].fillna(0) > 0).sum()))
    # non-overlap: engine vs an independent re-implementation of backtest._finish
    s2 = population(lab, "pit500", "off")
    eng = E.non_overlapping(s2)
    ref = nonoverlap_ref(s2)
    out["nonoverlap_engine_vs_simulate_rule"] = dict(rows=int(len(s2)), engine=int(eng.sum()),
                                                      reference=int(ref.sum()),
                                                      mismatches=int((eng != ref).sum()))
    # coverage
    cal = pd.DatetimeIndex(spy.index)
    out["coverage"] = dict(first_session=str(cal[0].date()), last_session=str(cal[-1].date()),
                           sessions_per_year={int(y): int(n) for y, n in
                                              pd.Series(cal.year).value_counts().sort_index().items()})
    sd = pd.to_datetime(s["signal_date"])
    out["short_detections_per_year"] = {
        st: {int(y): int(n) for y, n in sd[s["strategy"] == st].dt.year.value_counts().sort_index().items()}
        for st in SHORTS}
    pe = population(lab, "pit500", "primary")
    out["eligible_pit500_primary_per_year"] = {
        st: {int(y): int(n) for y, n in pd.to_datetime(pe.loc[pe["strategy"] == st, "signal_date"])
             .dt.year.value_counts().sort_index().items()} for st in SHORTS}
    out["groups"] = lab["group"].value_counts().to_dict()
    return out


def nonoverlap_ref(df):
    """backtest._finish(one_per_ticker=True): a signal at bar i is skipped while i <= the exit
    bar of the ticker's last kept trade (exit bar = entry bar i+1 + bars held); an open trade
    blocks the rest of the history."""
    keep = pd.Series(False, index=df.index)
    for _, g in df.sort_values(["ticker", "strategy", "i"]).groupby(["ticker", "strategy"]):
        busy = -1
        for idx, r in g.iterrows():
            if r["i"] <= busy:
                continue
            if r["trade_status"] == "closed":
                keep[idx] = True
                busy = r["i"] + 1 + int(r["bars_held"])
            elif r["trade_status"] == "open":
                keep[idx] = True
                busy = float("inf")
    return keep


# ---------------------------------------------------------------- statistics
def stats(df, col):
    d = df[(df["trade_status"] == "closed") & df[col].notna()]
    r = d[col].astype(float)
    if not len(r):
        return dict(trades=0)
    w, l = r[r > 0].sum(), -r[r <= 0].sum()
    return dict(trades=int(len(r)), win_rate=float((r > 0).mean() * 100),
                profit_factor=float(w / l) if l > 0 else None,
                expectancy_r=float(r.mean()), median_r=float(r.median()))


def month_ci(df, col):
    d = df[(df["trade_status"] == "closed") & df[col].notna()]
    if len(d) < 2:
        return [None, None]
    v = d[col].astype(float).values
    m = pd.to_datetime(d["signal_date"]).dt.to_period("M").values
    groups = [v[m == k] for k in sorted(set(m))]
    rng = np.random.default_rng(SEED)
    st = np.array([np.concatenate([groups[k] for k in rng.integers(0, len(groups), len(groups))])
                   .mean() for _ in range(N_BOOT)])
    return [float(np.quantile(st, .05)), float(np.quantile(st, .95))]


def table(pop_df, keys=("strategy",)):
    rows = []
    for k, g in pop_df.groupby(list(keys)):
        k = k if isinstance(k, tuple) else (k,)
        n = g[E.non_overlapping(g)]
        for col in SCEN:
            for label, d in (("nonoverlap", n), ("all_signals", g)):
                rows.append(dict(zip(keys, k), scenario=col, sample=label, **stats(d, col)))
    return pd.DataFrame(rows)


def periods_table(df):
    rows = []
    for st in SHORTS:
        d = df[df["strategy"] == st]
        n = d[E.non_overlapping(d)]
        sd = pd.to_datetime(n["signal_date"])
        for name, (a, b) in PERIODS.items():
            x = n[(sd >= a) & (sd <= b)]
            rows.append(dict(strategy=st, period=name, **{f"gross_{k}": v for k, v in
                                                          stats(x, "gross_r").items()},
                             **{f"net_{k}": v for k, v in stats(x, PRIMARY).items()}))
        for y in sorted(sd.dt.year.unique()):
            x = n[sd.dt.year == y]
            rows.append(dict(strategy=st, period=str(y), **{f"gross_{k}": v for k, v in
                                                            stats(x, "gross_r").items()},
                             **{f"net_{k}": v for k, v in stats(x, PRIMARY).items()}))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- portfolio
def books(df, frames, cal, start, end, rs_col):
    closes = {t: f["Close"].astype(float) for t, f in frames.items()}
    for s in closes.values():
        s.index = pd.to_datetime(s.index).normalize()
    out = {}
    for st in SHORTS:
        c = df[(df["strategy"] == st) & df["entry_date"].notna() &
               df["trade_status"].isin(["closed", "open"])]
        c = c.assign(rs=c[rs_col])[["ticker", "rs", "signal_date", "entry_date", "entry", "stop",
                                    "exit_date", "exit", "dividends_ps"]]
        used = {t: closes[t] for t in set(c["ticker"]) if t in closes}
        used["SPY_CAL"] = pd.Series(1.0, index=pd.DatetimeIndex([d for d in cal
                                                                   if start <= d <= end]))
        cv, fl, m = PF.replay(c, used, start, end)
        eq = cv.set_index("date")["equity"]
        m["periods"] = {}
        for name, (a, b) in PERIODS.items():
            w = eq[(eq.index >= a) & (eq.index <= b)]
            prev = eq[eq.index < a]
            if len(w):
                base = prev.iloc[-1] if len(prev) else 10000.0
                m["periods"][name] = round(float((w.iloc[-1] / base - 1) * 100), 2)
        out[st] = (cv, fl, m)
    return out


# ---------------------------------------------------------------- decision
def decision(pe):
    dev = pe[pd.to_datetime(pe["signal_date"]) < HOLDOUT_START]
    hold = pe[pd.to_datetime(pe["signal_date"]) >= HOLDOUT_START]
    res = {}
    for st in SHORTS:
        d = dev[dev["strategy"] == st]
        d = d[E.non_overlapping(d)]
        h = hold[hold["strategy"] == st]
        h = h[E.non_overlapping(h)]
        ds, hs = stats(d, PRIMARY), stats(h, PRIMARY)
        adv = bool(ds.get("trades", 0) >= 30 and (ds.get("expectancy_r") or -1) > 0
                   and (ds.get("profit_factor") or 0) > 1)
        hb = h[(pd.to_datetime(h["signal_date"]) >= PERIODS["bear_2022"][0]) &
               (pd.to_datetime(h["signal_date"]) <= PERIODS["bear_2022"][1])]
        ci = month_ci(h, PRIMARY)
        wide = stats(h, "net_r_wide_warm")
        res[st] = dict(development=ds, development_ci90=month_ci(d, PRIMARY), advances=adv,
                       holdout=hs, holdout_ci90=ci,
                       H1=bool(hs.get("trades", 0) >= 30),
                       H2=bool((hs.get("expectancy_r") or -1) > 0 and ci[0] is not None and ci[0] > 0),
                       H3=bool((wide.get("expectancy_r") or -1) > 0),
                       H4=bool((stats(hb, PRIMARY).get("expectancy_r") or -1) > 0),
                       holdout_bear_2022=stats(hb, PRIMARY), holdout_wide_warm=wide)
    return res


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--out", default=str(ROOT / "research/results/shorts/runs"))
    a = ap.parse_args(argv)
    root = Path(a.out)
    out = root / datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%MZ")
    man = {}
    lab, frames, spy, sha = load(a.dataset)
    cal = pd.DatetimeIndex(spy.index).normalize()
    res = dict(prereg="research/shorts/PREREG_SHORTS.md", dataset_sha256=sha,
               git=RUN._git_rev(), audit=audit(lab, spy))
    W = lambda n, b: RUN.write_once(out / n, b, man, root)                  # noqa: E731
    # signal level, every population x market
    tabs = []
    for pop in POPS:
        for mk in ("primary", "off"):
            t = table(population(lab, pop, mk))
            tabs.append(t.assign(universe=pop, market=mk))
    sig_tbl = pd.concat(tabs, ignore_index=True)
    W("signal_stats.csv", RUN.csv_bytes(sig_tbl))
    pe = population(lab, "pit500", "primary")
    per = periods_table(pe)
    W("periods_pit500_primary.csv", RUN.csv_bytes(per))
    per_off = periods_table(population(lab, "pit500", "off"))
    W("periods_pit500_off.csv", RUN.csv_bytes(per_off))
    # decision (primary universe, both market variants)
    res["decision"] = {mk: decision(population(lab, "pit500", mk)) for mk in ("primary", "off")}
    # portfolios
    start = cal[min(260, len(cal) - 1)]
    res["portfolio"] = {}
    for pop, mk in (("pit500", "primary"), ("pit500", "off"), ("sp1500", "primary")):
        df = population(lab, pop, mk)
        full = books(df, frames, cal, start, cal[-1], POPS[pop][0])
        hold = books(df, frames, cal, cal[cal >= HOLDOUT_START][0], cal[-1], POPS[pop][0])
        key = f"{pop}_{mk}"
        res["portfolio"][key] = {st: dict(full=full[st][2], holdout=hold[st][2]) for st in SHORTS}
        for st in SHORTS:
            W(f"equity_{key}_{st}.csv", RUN.csv_bytes(full[st][0]))
            W(f"fills_{key}_{st}.csv", RUN.csv_bytes(full[st][1]))
    for mk in ("primary", "off"):
        for st in SHORTS:
            d = res["decision"][mk][st]
            d["H5"] = bool(res["portfolio"][f"pit500_{mk}"][st]["holdout"]["return_pct"] > 0) \
                if f"pit500_{mk}" in res["portfolio"] else None
            d["confirmed"] = bool(d["advances"] and all(d[k] for k in ("H1", "H2", "H3", "H4", "H5")))
    res["confirmed"] = [f"{st}/{mk}" for mk in ("primary", "off") for st in SHORTS
                        if res["decision"][mk][st]["confirmed"]]
    res["verdict"] = ("confirmed: " + ", ".join(res["confirmed"]) if res["confirmed"] else
                      "no short setup confirmed: short strategies v1 rejected "
                      "(no re-parametrisation)")
    W("results.json", json.dumps(res, indent=1, default=str))
    W("REPORT.md", report(res, sig_tbl, per))
    RUN.write_once(out / "manifest.json", json.dumps(dict(files=man, dataset=sha), indent=1),
                   {}, root)
    print(json.dumps(dict(verdict=res["verdict"]), indent=1))
    return 0


def report(res, sig, per):
    f = RUN.md_table
    keep = ["universe", "market", "strategy", "scenario", "trades", "win_rate", "profit_factor",
            "expectancy_r", "median_r"]
    s = sig[(sig["sample"] == "nonoverlap")][keep]
    L = ["# Short strategies, 10 years — results", "", f"**Verdict: {res['verdict']}**", "",
         "## Audit", "", "```json", json.dumps(res["audit"], indent=1, default=str), "```", "",
         "## Decision (PIT S&P 500)", "", "```json",
         json.dumps(res["decision"], indent=1, default=str), "```", "",
         "## Signal level, primary universe, non-overlapping", "",
         f(s[(s["universe"] == "pit500")]), "", "## Periods (PIT S&P 500, SPY < MA50, primary net)",
         "", f(per), "", "## Portfolio", "", "```json",
         json.dumps(res["portfolio"], indent=1, default=str), "```", "",
         "## Other universes, non-overlapping", "", f(s[s["universe"] != "pit500"])]
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
