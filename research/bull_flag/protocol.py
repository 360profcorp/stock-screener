"""Bull flag v1.1 protocol helpers (PREREG_BULLFLAG_v1 §4, §4.2, §4.3). No data access.

flag_filter_at    Experiment A: a flag day evaluated with the BREAKOUT's own stop/exit
s4_statistic      S4: matched days, equal day weights, paired month bootstrap of the difference
merge_candidates  combined books: one order per ticker/day (retest first), RS-first order
"""
import numpy as np
import pandas as pd

import backtest as bt
from research.bull_flag import rules as F

SEED = 20261020
N_BOOT = 5000
PRIORITY = {"retest": 0, "flag": 1, "breakout": 1}


def flag_filter_at(x, i):
    """Experiment A: only the pattern filter changes; level/stop are the breakout's."""
    if F.flag_at(x, i) is None:
        return None
    return bt.breakout_at(x, i, 3)          # (level, level) -> stop = level * 0.97


def s4_statistic(trades: pd.DataFrame, col="net_r", n_boot=N_BOOT, seed=SEED):
    """trades: kept (non-overlapping) closed breakout trades with columns signal_date, group
    ('flag' | 'nonflag'), col. Returns dict(S4, ci90, matched_days, months, n_flag, n_nonflag)."""
    t = trades.dropna(subset=[col]).copy()
    t["signal_date"] = pd.to_datetime(t["signal_date"])
    g = t.groupby(["signal_date", "group"])[col].mean().unstack()
    for k in ("flag", "nonflag"):
        if k not in g:
            g[k] = np.nan
    m = g.dropna(subset=["flag", "nonflag"])                     # matched days only
    d = (m["flag"] - m["nonflag"]).rename("d")
    out = dict(matched_days=int(len(d)),
               n_flag=int(t[t["signal_date"].isin(d.index) & (t["group"] == "flag")].shape[0]),
               n_nonflag=int(t[t["signal_date"].isin(d.index) & (t["group"] == "nonflag")].shape[0]))
    if not len(d):
        return dict(out, S4=np.nan, ci90=(np.nan, np.nan), months=0)
    month = d.index.to_period("M")
    months = sorted(set(month))
    by_m = [d.values[month == mm] for mm in months]
    rng = np.random.default_rng(seed)
    stats = np.empty(n_boot)
    for b in range(n_boot):
        pick = rng.integers(0, len(months), len(months))           # same months for both groups
        vals = np.concatenate([by_m[k] for k in pick])
        stats[b] = vals.mean()
    return dict(out, S4=float(d.mean()), months=len(months),
                ci90=(float(np.quantile(stats, 0.05)), float(np.quantile(stats, 0.95))))


def merge_candidates(retest: pd.DataFrame, other: pd.DataFrame, other_kind="flag"):
    """Combined book candidates. Both frames: simulate()-style trades with ticker, date
    (entry), signal_date, rs, entry, stop, exit... One candidate per (ticker, signal_date):
    the retest wins (its stop and entry). Order: date, RS desc, retest first, ticker."""
    r = retest.assign(kind="retest")
    o = other.assign(kind=other_kind)
    both = pd.concat([r, o], ignore_index=True)
    both["_prio"] = both["kind"].map(PRIORITY)
    both = both.sort_values(["signal_date", "ticker", "_prio"], kind="stable") \
        .drop_duplicates(["ticker", "signal_date"], keep="first")
    both = both.sort_values(["date", "rs", "_prio", "ticker"], ascending=[True, False, True, True],
                            kind="stable").reset_index(drop=True)
    return both.drop(columns="_prio")
