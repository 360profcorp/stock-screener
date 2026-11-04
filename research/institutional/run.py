"""Institutional v1 backtest (PREREG_INSTITUTIONAL.md): RS-first vs SEC-based same-day orders.

    python -m research.institutional.run --dataset DS_DIR --sec SEC_DIR

DS_DIR: 10-year dataset artifact (run 40152515701); SEC_DIR: research.institutional.sec_data
output. Writes research/results/institutional/runs/<run_id>/ (write-once).
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import portfolio_bt as pf
from research.crisis import run as CR
from research.sp1500 import run as RUN

ROOT = Path(__file__).resolve().parents[2]
ORDERS = ("RS", "INS", "BR", "IR")
N_RND = 200
SEED = 20261025
F1_DAYS = 90
FEE = 10 / 1e4


# ---------------------------------------------------------------- point-in-time features
def features(tr, sec):
    """F1, F2 and coverage flags per trade row (ticker, signal_date), from filings dated
    strictly before the signal day. Also returns the latest filing date used per row."""
    buys = pd.read_csv(sec / "form4_buys.csv.gz", parse_dates=["filing_date"])
    fil = pd.read_csv(sec / "form4_filings.csv.gz", parse_dates=["filing_date"])
    br = pd.read_csv(sec / "f13_breadth.csv.gz", parse_dates=["period", "usable_from"])
    out = tr[["ticker", "signal_date"]].drop_duplicates().copy()
    out["signal_date"] = pd.to_datetime(out["signal_date"]).dt.normalize()
    f1, used1, has4, f2, used2, has13 = [], [], [], [], [], []
    bt_ = {t: g.sort_values("filing_date") for t, g in buys.groupby("ticker")}
    ft_ = {t: g["filing_date"].sort_values().values for t, g in fil.groupby("ticker")}
    brt = {t: g.sort_values("usable_from") for t, g in br.groupby("ticker")}
    for t, d in zip(out["ticker"], out["signal_date"]):
        g = bt_.get(t)
        if g is not None:
            w = g[(g["filing_date"] < d) & (g["filing_date"] >= d - pd.Timedelta(days=F1_DAYS))]
            f1.append(int(w["owner_cik"].nunique()))
            used1.append(w["filing_date"].max() if len(w) else pd.NaT)
        else:
            f1.append(0)
            used1.append(pd.NaT)
        fd = ft_.get(t)
        has4.append(bool(fd is not None and ((fd < np.datetime64(d)) &
                                             (fd >= np.datetime64(d - pd.Timedelta(days=365)))).any()))
        b = brt.get(t)
        row = None
        if b is not None:
            u = b[b["usable_from"] <= d]
            if len(u) and (d - u["usable_from"].iloc[-1]).days <= 120:
                row = u.iloc[-1]
        f2.append(float(row["breadth_change"]) if row is not None and pd.notna(row["breadth_change"])
                  else 0.0)
        used2.append(row["usable_from"] - pd.Timedelta(days=1) if row is not None else pd.NaT)
        has13.append(row is not None)
    out["F1"], out["F2"] = f1, f2
    out["used_form4_max"], out["used_13f_deadline"] = used1, used2
    out["has_form4"], out["has_13f"] = has4, has13
    return out


def pit_check(feat):
    bad4 = int((feat["used_form4_max"] >= feat["signal_date"]).sum())
    bad13 = int((feat["used_13f_deadline"] >= feat["signal_date"]).sum())
    return dict(form4_filings_on_or_after_signal_day=bad4,
                f13_quarters_not_yet_public=bad13, rows=int(len(feat)))


# ---------------------------------------------------------------- orders and books
def order(tr, how, seed=None):
    t = tr.copy()
    if how == "RS":
        key = [-t["rs"]]
    elif how == "INS":
        key = [-t["F1"], -t["rs"]]
    elif how == "BR":
        key = [-t["F2"], -t["rs"]]
    elif how == "IR":
        r1 = t.groupby("date")["F1"].rank(pct=True)
        r2 = t.groupby("date")["F2"].rank(pct=True)
        key = [-(r1 + r2) / 2, -t["rs"]]
    else:
        key = [pd.Series(np.random.default_rng(seed).random(len(t)), index=t.index)]
    for k, s in enumerate(key):
        t[f"_k{k}"] = s.values
    cols = ["date"] + [f"_k{k}" for k in range(len(key))] + ["ticker"]
    t = t.sort_values(cols, kind="stable").reset_index(drop=True)
    return t.drop(columns=[c for c in t.columns if c.startswith("_k")])


def book(t, data, s0, s1, bps, spy):
    curve, ex, m = pf.replay(t, data, start=s0, end=s1, open_at_end="mark", cost_bps=bps,
                             **CR.CFG)
    return CR.metrics(curve, ex, m, spy), curve


# ---------------------------------------------------------------- information content
def nonoverlap(tr):
    keep, last = [], {}
    for idx, r in tr.sort_values(["ticker", "signal_date"]).iterrows():
        e = last.get(r["ticker"])
        if e is not None and (pd.isna(e) or r["signal_date"] <= e):
            continue
        keep.append(idx)
        last[r["ticker"]] = r["exit_date"]
    return tr.loc[keep]


def ic(tr, col):
    d = tr[tr["status"] == "closed"].copy()
    d["net_r"] = (d["exit"] * (1 - FEE) - d["entry"] * (1 + FEE)) / (d["entry"] - d["stop"])
    vals, months = [], []
    for day, g in d.groupby("signal_date"):
        if len(g) >= 3 and g[col].nunique() > 1:
            vals.append(g[col].rank().corr(g["net_r"].rank()))
            months.append(pd.Timestamp(day).to_period("M"))
    if not vals:
        return dict(days=0)
    v, m = np.array(vals), np.array(months)
    groups = [v[m == k] for k in sorted(set(m))]
    rng = np.random.default_rng(SEED)
    bs = [np.concatenate([groups[k] for k in rng.integers(0, len(groups), len(groups))]).mean()
          for _ in range(2000)]
    return dict(days=len(v), mean_ic=float(v.mean()),
                ci90=[float(np.quantile(bs, .05)), float(np.quantile(bs, .95))])


def coverage(tr):
    y = pd.to_datetime(tr["signal_date"]).dt.year
    g = tr.assign(year=y).groupby("year")
    return {int(k): dict(candidates=int(len(x)), form4_any_12m=round(float(x["has_form4"].mean() * 100), 1),
                         f1_positive=round(float((x["F1"] > 0).mean() * 100), 1),
                         f13_usable=round(float(x["has_13f"].mean() * 100), 1))
            for k, x in g}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--sec", required=True)
    ap.add_argument("--out", default=str(ROOT / "research/results/institutional/runs"))
    a = ap.parse_args(argv)
    root, sec = Path(a.out), Path(a.sec)
    out = root / datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%MZ")
    man = {}
    frames, spy, pit_text, sha = CR.load(a.dataset)
    sig, data, cal, info = CR.build(frames, spy, pit_text)
    elig = CR.eligible(sig, False)
    start = cal[min(260, len(cal) - 1)]
    windows = dict(full=(start, cal[-1]), development=(start, pd.Timestamp("2021-12-31")),
                   holdout=(cal[cal >= pd.Timestamp("2022-01-03")][0], cal[-1]))
    res = dict(prereg="research/institutional/PREREG_INSTITUTIONAL.md", dataset_sha256=sha,
               sec_summary=json.loads((sec / "sources.json").read_text())["info"],
               lags=json.loads((sec / "lags.json").read_text()), git=RUN._git_rev(), data=info,
               note="Research Breakout = next-open entry (backtest.simulate). It is NOT the bot's "
                    "pre-close breakout purchase; results must not be mixed.",
               strategies={})
    W = lambda n, b: RUN.write_once(out / n, b, man, root)                  # noqa: E731
    for st in CR.STRATS:
        tr = CR.trades_for(elig, data, st)
        tr["signal_date"] = pd.to_datetime(tr["signal_date"]).dt.normalize()
        feat = features(tr, sec)
        tr = tr.merge(feat[["ticker", "signal_date", "F1", "F2", "has_form4", "has_13f"]],
                      on=["ticker", "signal_date"], how="left")
        r = dict(pit_check=pit_check(feat), coverage=coverage(tr), books={}, random={})
        no = nonoverlap(tr)
        r["ic"] = {c: ic(no, c) for c in ("F1", "F2", "rs")}
        for how in ORDERS:
            t = order(tr, how)
            for w, (s0, s1) in windows.items():
                for bps in (10., 25.):
                    m, curve = book(t, data, s0, s1, bps, spy)
                    r["books"][f"{how}|{w}|{int(bps)}"] = m
                    if w == "full" and bps == 10.:
                        W(f"equity_{st}_{how}.csv", RUN.csv_bytes(curve[["date", "equity"]]))
        for w in ("development", "holdout"):
            s0, s1 = windows[w]
            rets = []
            for k in range(1, N_RND + 1):
                c, _, mm = pf.replay(order(tr, "RND", seed=k), data, start=s0, end=s1,
                                     open_at_end="mark", cost_bps=10., **CR.CFG)
                rets.append(mm["return_pct"])
            r["random"][w] = dict(n=N_RND, p50=float(np.median(rets)),
                                  p80=float(np.quantile(rets, .8)), p95=float(np.quantile(rets, .95)))
        dec = {}
        cov = r["coverage"]
        full_years = [y for y in cov if 2018 <= y <= 2025]
        undetermined = (any(cov[y]["f13_usable"] < 70 for y in full_years) or
                        float((tr["F1"] > 0).mean()) < 0.05)
        for how in ("INS", "BR", "IR"):
            ok = True
            for w in ("development", "holdout"):
                x, c = r["books"][f"{how}|{w}|10"], r["books"][f"RS|{w}|10"]
                ok &= (x["return_pct"] > c["return_pct"] and
                       x["return_pct"] > r["random"][w]["p80"] and
                       x["max_dd_pct"] >= c["max_dd_pct"] - 3)
            xs, cs = r["books"][f"{how}|holdout|25"], r["books"]["RS|holdout|25"]
            ok &= xs["return_pct"] > cs["return_pct"]
            dec[how] = "improves" if ok else ("undetermined" if undetermined else "not improved")
        r["decision"], r["undetermined_by_coverage"] = dec, bool(undetermined)
        res["strategies"][st] = r
        W(f"features_{st}.csv", RUN.csv_bytes(tr[["ticker", "signal_date", "rs", "F1", "F2",
                                                  "has_form4", "has_13f", "status", "entry",
                                                  "exit", "stop"]]))
    W("results.json", json.dumps(res, indent=1, default=str))
    rows = [dict(strategy=st, order=k.split("|")[0], window=k.split("|")[1],
                 costs_bps=k.split("|")[2], **{c: v[c] for c in ("return_pct", "cagr_pct", "max_dd_pct",
                                                                  "profit_factor", "trades")})
            for st, r in res["strategies"].items() for k, v in r["books"].items()]
    W("books.csv", RUN.csv_bytes(pd.DataFrame(rows)))
    RUN.write_once(out / "manifest.json", json.dumps(dict(files=man), indent=1), {}, root)
    print(json.dumps({st: r["decision"] for st, r in res["strategies"].items()}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
