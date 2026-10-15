"""Daily Retest RS-first screener for the paper portfolio (Task 10).

Uses the SAME functions as the backtest (backtest.indicators, backtest.retest_at,
backtest.rs_history, core.market_regime) on data truncated at the scan day, so a live scan
reproduces exactly what backtest.find_signals + simulate filters produce for that day.

Output: one row per raw Retest detection on `day` (also those failing RS / market filters,
for ML research), with as-of features computed only from bars <= day, eligibility flags and
the RS-first rank among eligible signals.
"""
import numpy as np
import pandas as pd

import backtest as bt
import core
from paper.config import DEFAULT

FEATURES = ["ret_1d", "ret_5d", "ret_20d", "ret_63d", "dist_ma50", "dist_ma150", "dist_ma200",
            "ma200_slope20", "dist_52w_high", "dist_52w_low", "atr14_pct", "vol_ratio",
            "vol10_vs_50", "level_to_stopbase_pct", "close_to_level_pct"]


def truncate(frames: dict, day) -> dict:
    """Bars up to and including `day` (defensive: the screener must never see later bars)."""
    day = pd.Timestamp(day).normalize()
    out = {}
    for t, df in frames.items():
        idx = pd.to_datetime(df.index).normalize()
        d = df[idx <= day]
        if len(d):
            out[t] = d
    return out


def market_state(spy: pd.DataFrame, day, flt: str) -> dict:
    """SPY regime on `day` from bars <= day. Missing day -> filter passes (as simulate)."""
    day = pd.Timestamp(day).normalize()
    if spy is None or spy.empty:
        return dict(spy_close=np.nan, spy_ma50=np.nan, spy_ma200=np.nan, spy_ret_20d=np.nan,
                    spy_above50=np.nan, spy_above200=np.nan, market_ok=True)
    reg = core.market_regime(spy[pd.to_datetime(spy.index).normalize() <= day])
    if day not in reg.index:
        ok = True
        row = reg.iloc[-1] if len(reg) else None
    else:
        row = reg.loc[day]
        ok = bool(core.regime_mask(reg, flt).loc[day])
    c = reg["close"]
    return dict(spy_close=float(row["close"]) if row is not None else np.nan,
                spy_ma50=float(row["ma50"]) if row is not None else np.nan,
                spy_ma200=float(row["ma200"]) if row is not None else np.nan,
                spy_ret_20d=float(c.iloc[-1] / c.iloc[-21] - 1) if len(c) > 20 else np.nan,
                spy_above50=bool(row["above50"]) if row is not None else np.nan,
                spy_above200=bool(row["above200"]) if row is not None else np.nan,
                market_ok=ok)


def _features(x, i, level, stop_base):
    C, H, L = x["C"], x["H"], x["L"]
    r = lambda n: C[i] / C[i - n] - 1 if i >= n and C[i - n] > 0 else np.nan
    tr = np.maximum(H[i - 13:i + 1] - L[i - 13:i + 1],
                    np.maximum(np.abs(H[i - 13:i + 1] - C[i - 14:i]),
                               np.abs(L[i - 13:i + 1] - C[i - 14:i]))) if i >= 14 else np.nan
    avg = x["vol20_prev"][i]
    return dict(ret_1d=r(1), ret_5d=r(5), ret_20d=r(20), ret_63d=r(63),
                dist_ma50=C[i] / x["ma50"][i] - 1, dist_ma150=C[i] / x["ma150"][i] - 1,
                dist_ma200=C[i] / x["ma200"][i] - 1,
                ma200_slope20=x["ma200"][i] / x["ma200_20"][i] - 1,
                dist_52w_high=C[i] / x["hi252"][i] - 1, dist_52w_low=C[i] / x["lo252"][i] - 1,
                atr14_pct=float(np.mean(tr) / C[i]) if i >= 14 else np.nan,
                vol_ratio=x["V"][i] / avg if avg else np.nan,
                vol10_vs_50=x["vol10"][i] / x["vol50"][i] if x["vol50"][i] else np.nan,
                level_to_stopbase_pct=(level / stop_base - 1) * 100,
                close_to_level_pct=(C[i] / level - 1) * 100)


def rank_rs_first(df: pd.DataFrame) -> pd.DataFrame:
    """RS descending, ties by ticker — the validated research ordering."""
    return df.sort_values(["rs", "ticker"], ascending=[False, True], kind="stable")


def scan_day(frames: dict, spy: pd.DataFrame, day, cfg=DEFAULT, sectors: dict = None,
             already_truncated=False) -> pd.DataFrame:
    """All Retest detections on `day` with features, flags and RS-first rank."""
    day = pd.Timestamp(day).normalize()
    fr = frames if already_truncated else truncate(frames, day)
    rs = bt.rs_history(fr)
    rs_today = rs.loc[day] if day in rs.index else pd.Series(dtype=float)
    mkt = market_state(spy, day, cfg.market_filter)
    rows, above50, scanned = [], 0, 0
    for t, df in fr.items():
        if pd.Timestamp(df.index[-1]).normalize() != day:
            continue                                          # no bar today
        i = len(df) - 1
        if i < bt.WARMUP:
            continue
        x = bt.indicators(df)
        scanned += 1
        above50 += bool(x["C"][i] > x["ma50"][i])
        hit = bt.retest_at(x, i, cfg.lookback)
        if hit is None:
            continue
        level, stop_base = float(hit[0]), float(hit[1])
        rs_t = rs_today.get(t, np.nan)
        stop = stop_base * (1 - cfg.stop_buf_pct / 100)
        rows.append(dict(ticker=t, signal_date=day, close=float(x["C"][i]), level=level,
                         stop_base=stop_base, stop=stop,
                         risk_pct_at_close=(x["C"][i] - stop) / x["C"][i] * 100,
                         rs=rs_t, sector=(sectors or {}).get(t, ""),
                         **_features(x, i, level, stop_base)))
    out = pd.DataFrame(rows)
    breadth = 100 * above50 / scanned if scanned else np.nan
    if out.empty:
        return out
    out["passes_rs"] = out["rs"].ge(cfg.min_rs).fillna(False) if cfg.min_rs else True
    out["passes_market"] = mkt["market_ok"]
    out["eligible"] = out["passes_rs"] & out["passes_market"]
    for k, v in mkt.items():
        out[k] = v
    out["breadth_above_ma50_pct"] = breadth
    out["universe_scanned"] = scanned
    out["raw_signals_today"] = len(out)
    elig = rank_rs_first(out[out["eligible"]])
    out["rank"] = np.nan
    out.loc[elig.index, "rank"] = np.arange(1, len(elig) + 1)
    return rank_rs_first(out).sort_values("rank", na_position="last",
                                          kind="stable").reset_index(drop=True)
