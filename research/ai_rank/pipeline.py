"""AI ranking research v1: dataset audit, yearly stability, first long-signal ranker.

Research only. Uses the PR #5 dataset (signals.csv.gz + bars.pkl.gz from the
`sp1500-dataset-<run>` artifact); nothing is connected to the bot or the paper portfolios.

Comparison protocol (same for both rankers):
  same eligible signals -> backtest.simulate(entry next open, stop 3 %, 20 sessions,
  one_per_ticker=False) -> SAME trade list; only the same-day ORDER differs
  (RS-first: RS desc, ticker; model: score desc, ticker) -> portfolio_bt.replay with the
  frozen paper config ($10k, 1 % risk, 5 positions, 3 new/day, 20 % cap, 10 bps/side).
"""
import gzip
import io
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

import backtest as bt
import portfolio_bt as pf
from research.sp1500 import engine as E
from research.sp1500 import rules as R

LONGS = list(R.LONG_RULES)
CFG = dict(initial_cash=10000., risk_fraction=.01, max_positions=5, max_new_per_day=3,
           max_position_fraction=.20, cost_bps=10.)
MODEL_FEATURES = ["rs_score", "rank_rs", "log_adv", "atr14_pct", "vol_ratio", "vol10_vs_50",
                  "ret_1d", "ret_5d", "ret_20d", "ret_63d", "dist_ma50", "dist_ma150",
                  "dist_ma200", "dist_52w_high", "dist_52w_low", "dist_level_pct",
                  "risk_at_close_pct", "spy_above200", "spy_ret_20d"]
TARGET = "net_r_base"
CLIP = (-2.0, 6.0)                      # winsorise the R target for fitting only


# =====================================================================
# loading
# =====================================================================
def load(dataset_dir):
    d = Path(dataset_dir)
    sig = next(d.rglob("signals.csv.gz"))
    bars = next(d.rglob("bars.pkl.gz"))
    lab = pd.read_csv(sig, low_memory=False)
    for c in ("signal_date", "entry_date", "exit_date", "observable_trade"):
        if c in lab:
            lab[c] = pd.to_datetime(lab[c], errors="coerce")
    b = pickle.load(io.BytesIO(gzip.decompress(bars.read_bytes())))
    return lab, b["frames"], b["spy"], {"signals": str(sig), "bars": str(bars)}


def to_bool(s):
    return s.map(lambda v: v if isinstance(v, bool) else str(v).lower() == "true")


# =====================================================================
# audit
# =====================================================================
def audit(lab, frames, spy, n_sample=400, seed=0):
    cal = pd.DatetimeIndex(spy.index)
    end = cal[-1]
    out = {}
    # 1) per-ticker features recomputed from bars truncated at the decision bar
    rng = np.random.default_rng(seed)
    rows = lab.iloc[rng.choice(len(lab), size=min(n_sample, len(lab)), replace=False)]
    bad, checked = [], 0
    keys = ["close", "adv20_usd", "atr14_pct", "vol_ratio", "ret_1d", "ret_5d", "ret_20d",
            "ret_63d", "dist_ma50", "dist_ma200", "dist_52w_high"]
    for r in rows.itertuples():
        f = frames.get(r.ticker)
        if f is None:
            continue
        tr = f.loc[:r.signal_date]
        if not len(tr) or tr.index[-1] != r.signal_date:
            continue
        x = E.arrays(tr)
        i = len(tr) - 1
        if i != r.i:
            bad.append((r.ticker, str(r.signal_date.date()), "index"))
            continue
        feat = E._features(x, i)
        rule = R.LONG_RULES.get(r.strategy) or R.SHORT_RULES[r.strategy]
        hit = rule(x, i)
        checked += 1
        ok = hit is not None and np.isclose(hit[0], r.level) and np.isclose(hit[1], r.stop_base)
        for k in keys:
            a, b = feat[k], getattr(r, k)
            ok &= (np.isnan(a) and pd.isna(b)) or np.isclose(a, b, rtol=1e-6, equal_nan=True)
        if not ok:
            bad.append((r.ticker, str(r.signal_date.date()), r.strategy))
    out["features_recomputed_on_truncated_bars"] = dict(checked=checked, mismatches=len(bad),
                                                        examples=bad[:5])
    # 2) RS at 3 dates recomputed from closes up to that date only
    rs_bad, rs_checked = 0, 0
    ref = sorted(set(lab.loc[lab["group"] == "sp500", "ticker"]) & set(frames))
    for day in pd.DatetimeIndex(sorted(lab["signal_date"].unique()))[[100, len(cal) // 2, -30]]:
        tr = {t: f.loc[:day] for t, f in frames.items() if len(f.loc[:day])}
        pct = E.rs_percentile(E.rs_scores(tr), ref).loc[day]
        sub = lab[lab["signal_date"] == day]
        for r in sub.itertuples():
            rs_checked += 1
            if not (pd.isna(r.rs_ref500) and pd.isna(pct.get(r.ticker))) and \
                    not np.isclose(r.rs_ref500, pct.get(r.ticker, np.nan)):
                rs_bad += 1
    out["rs_recomputed_on_truncated_closes"] = dict(checked=rs_checked, mismatches=rs_bad)
    # 3) labels only when observable
    closed = lab[lab["trade_status"] == "closed"]
    out["labels"] = dict(
        closed=len(closed),
        closed_after_data_end=int((closed["observable_trade"] > end).sum()),
        exit_before_entry=int((closed["exit_date"] < closed["entry_date"]).sum()),
        entry_not_after_signal=int((closed["entry_date"] <= closed["signal_date"]).sum()),
        open_or_immature=int((lab["trade_status"] != "closed").sum()))
    # 4) purge: v1.0 dataset split vs the corrected label-end purge
    le = E.label_end(lab, cal)
    v0 = pd.Timestamp(lab["split_validation_start"].iloc[0])
    t0 = pd.Timestamp(lab["split_test_start"].iloc[0])
    leak_v = (lab["split"] == "train") & (le >= v0)
    leak_t = (lab["split"] == "validation") & (le >= t0)
    out["purge_v1_leaks"] = dict(train_rows_label_after_validation_start=int(leak_v.sum()),
                                 validation_rows_label_after_test_start=int(leak_t.sum()),
                                 fixed="purge by label end (exit date, >= signal + 21 sessions)")
    # 5) overlap of consecutive-day repeats
    el = lab[(lab["direction"] == "long") & to_bool(lab["eligible_primary"])]
    no = E.non_overlapping(el)
    out["overlap"] = dict(eligible_long=len(el), non_overlapping=int(no.sum()),
                          repeats_share=round(1 - no.mean(), 3))
    return out


# =====================================================================
# universe for the ranker
# =====================================================================
def long_pool(lab, universe="pit500", strategies=("retest",)):
    """Eligible long signals. pit500: S&P 500 members ON the signal day, RS vs that day's
    members (closest to what the forward screener sees); sp500/sp400/sp600/combined: today's
    lists (survivorship), RS vs the S&P 500 reference (production meaning)."""
    d = lab[(lab["direction"] == "long") & lab["strategy"].isin(strategies)].copy()
    if universe == "pit500":
        d = d[to_bool(d["pit_member_sp500"]) & to_bool(d["eligible_pit_primary"])]
        d["rs"] = d["rs_pit500"]
    else:
        groups = ["sp500", "sp400", "sp600"] if universe == "combined" else [universe]
        d = d[d["group"].isin(groups) & to_bool(d["eligible_primary"])]
        d["rs"] = d["rs_ref500"]
    d["log_adv"] = np.log(d["adv20_usd"].clip(lower=1))
    d["rank_rs"] = d.groupby("signal_date")["rs"].rank(pct=True)
    d["spy_above200"] = to_bool(d["spy_above200"]).astype(float)
    return d.reset_index(drop=True)


def splits_at(df, calendar, v0, t0, embargo=5):
    """Fixed dataset-wide boundaries; purge by the label's true end (see engine.label_end)."""
    cal = pd.DatetimeIndex(calendar)
    pos = {d: k for k, d in enumerate(cal)}
    sd = pd.to_datetime(df["signal_date"])
    le = E.label_end(df, cal)
    shift = lambda d, n: cal[min(pos[d] + n, len(cal) - 1)]          # noqa: E731
    sp = np.where(sd < v0, "train", np.where(sd < t0, "validation", "test")).astype(object)
    sp[(sp == "train") & (le >= v0)] = "purged"
    sp[(sp == "validation") & (le >= t0)] = "purged"
    sp[(sp == "validation") & (sd < shift(v0, embargo))] = "embargo"
    sp[(sp == "test") & (sd < shift(t0, embargo))] = "embargo"
    return pd.Series(sp, index=df.index), le


# =====================================================================
# portfolio replay with a given same-day order
# =====================================================================
def trades_for(pool, data):
    parts = []
    for mode, s in pool.groupby("strategy"):
        raw = pd.DataFrame(dict(ticker=s["ticker"], mode=mode, i=s["i"], date=s["signal_date"],
                                close=s["close"], level=s["level"], stop_base=s["stop_base"],
                                rs=s["rs"], vol_ratio=s["vol_ratio"]))
        tr = bt.simulate(raw, data, mode, hold=R.HOLD, stop_buf=R.LONG_STOP_BUF_PCT,
                         min_rs=0, min_vol=0.0, max_risk=0.0, market_ok=None,
                         entry_at="open", one_per_ticker=False, include_open=True)
        if len(tr):
            parts.append(tr.assign(mode=mode))
    tr = pd.concat(parts, ignore_index=True)
    tr["signal_date"] = pd.to_datetime(tr["signal_date"])
    return tr


def replay(trades, data, start, end, score=None, seed=None):
    """score: None -> RS-first (rs desc, ticker); Series aligned to trades -> score desc;
    seed -> random same-day order."""
    t = trades.copy()
    if seed is not None:
        t["_k"] = np.random.default_rng(seed).random(len(t))
    elif score is not None:
        t["_k"] = -np.asarray(score, dtype=float)
    else:
        t["_k"] = -t["rs"].astype(float)
    t = t.sort_values(["date", "_k", "ticker"], kind="stable").reset_index(drop=True)
    # `data` is the whole universe (common price calendar), not only traded tickers
    curve, ex, m = pf.replay(t.drop(columns="_k"), data, start=start, end=end,
                             open_at_end="mark", **CFG)
    return curve, ex, m


def summary(curve, ex, m):
    eq = curve.set_index("date")["equity"]
    yr = eq.groupby(eq.index.year).agg(["first", "last"])
    prev = eq.groupby(eq.index.year).last().shift(1)
    yr_ret = ((yr["last"] / prev.fillna(CFG["initial_cash"])) - 1) * 100
    closed = ex[ex["status"] == "closed"] if len(ex) else ex
    return dict(return_pct=m["return_pct"], cagr_pct=m["cagr_pct"],
                max_dd_pct=m["max_drawdown_pct"], trades=m["executed_trades"],
                closed=len(closed),
                expectancy_r=float(closed["net_r"].mean()) if len(closed) else np.nan,
                expectancy_usd=float(closed["net_pnl"].mean()) if len(closed) else np.nan,
                win_rate=float((closed["net_pnl"] > 0).mean() * 100) if len(closed) else np.nan,
                yearly_return_pct={int(k): round(float(v), 2) for k, v in yr_ret.items()})


# =====================================================================
# models
# =====================================================================
def fit_predict(kind, params, Xtr, ytr, Xte):
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    if kind == "ridge":
        m = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                          Ridge(alpha=params["alpha"]))
    else:
        m = HistGradientBoostingRegressor(max_depth=params["depth"], learning_rate=0.05,
                                          max_iter=params["iter"], min_samples_leaf=200,
                                          l2_regularization=1.0, random_state=0)
    m.fit(Xtr, np.clip(ytr, *CLIP))
    return m.predict(Xte), m


GRID = [("ridge", dict(alpha=a)) for a in (1., 10., 100.)] + \
       [("hgb", dict(depth=d, iter=it)) for d in (2, 3) for it in (100, 300)]


def daily_ic(df, score, target=TARGET):
    """Mean same-day Spearman correlation between score and realised net R (days with >= 3)."""
    d = df.assign(_s=score)
    vals = []
    for _, g in d.groupby("signal_date"):
        g = g.dropna(subset=[target])
        if len(g) >= 3 and g["_s"].nunique() > 1:
            vals.append(g["_s"].rank().corr(g[target].rank()))
    return (float(np.nanmean(vals)) if vals else np.nan, len(vals))
