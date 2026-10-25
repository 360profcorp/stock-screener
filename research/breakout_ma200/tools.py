"""Shared helpers for the MA200 study (copied unchanged from research/breakout_causes/run.py:
index lookup, random-removal benchmark, exact execution split, post-exit vs SPY)."""
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

import portfolio_bt as pf
from research.crisis import run as CR

HORIZONS = (5, 10, 20)
SEED = 20261025


def idx_of(x, day):
    d = pd.DatetimeIndex(pd.to_datetime(x["dates"])).normalize()
    k = np.flatnonzero(d == pd.Timestamp(day).normalize())
    if len(k) != 1:
        raise ValueError(f"date {day} not unique/present")
    return int(k[0]), d


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
