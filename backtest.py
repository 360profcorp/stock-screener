"""
VISAR backtest — runs the same three setups (breakout, retest, VCP) over history.

How it works
  1. For every S&P 500 stock and every past day, the setup rules are checked using only
     data up to that day (no look-ahead). The rules are identical to the live scanner
     (core.py); the functions below are array versions of them, evaluated at bar i.
  2. RS is recomputed for every past day (percentile across the S&P 500 on that day).
  3. Each signal becomes a trade: entry at that day's close, stop under the level
     (same stop rules as the live scanner), exit at the stop or after N trading days.
     One open trade per stock per setup at a time.

Limitations: today's S&P 500 list (survivorship bias), no commissions or slippage,
entry at the signal close.
"""
import numpy as np
import pandas as pd

import core

WARMUP = 260          # bars needed before a day can be tested (MA200 + 52 weeks + RS)


# =====================================================================
# Indicators for one stock (computed once, then read at any bar i)
# =====================================================================
def indicators(df: pd.DataFrame) -> dict:
    C, H, L, V = df["Close"], df["High"], df["Low"], df["Volume"]
    ma200 = C.rolling(200).mean()
    return {
        "O": df["Open"].values.astype(float), "H": H.values.astype(float),
        "L": L.values.astype(float), "C": C.values.astype(float),
        "V": V.values.astype(float),
        "ma50": C.rolling(50).mean().values, "ma150": C.rolling(150).mean().values,
        "ma200": ma200.values, "ma200_20": ma200.shift(20).values,
        "hi252": H.rolling(252).max().values, "lo252": L.rolling(252).min().values,
        "vol10": V.rolling(10, min_periods=1).mean().values,
        "vol50": V.rolling(50, min_periods=1).mean().values,
        "vol20_prev": V.shift(1).rolling(20, min_periods=1).mean().values,
        "dates": df.index,
    }


# =====================================================================
# Setup rules at bar i — same logic as core.detect_* on df.iloc[:i+1]
# Return (level, stop_base) or None.
# =====================================================================
def breakout_at(x, i, lookback=3):
    if i < lookback:
        return None
    level = x["H"][i - lookback:i].max()
    return (level, level) if x["C"][i] > level else None


def retest_at(x, i, lookback=3, max_days=10, tol=0.02, min_pull=0.03):
    H, L, C = x["H"], x["L"], x["C"]
    if i + 1 < lookback + max_days + 2 or not C[i] > C[i - 1]:
        return None
    for b in range(i - 2, i - max_days - 1, -1):
        level = H[b - lookback:b].max()
        if C[b] <= level:
            continue
        peak_idx = b + int(np.argmax(H[b:i]))
        peak = H[peak_idx]
        pull_lows = L[peak_idx + 1:i + 1]
        if len(pull_lows) == 0:
            continue
        pull_low = pull_lows.min()
        touched = level * (1 - tol) <= pull_low <= level * (1 + tol)
        deep_enough = pull_low <= peak * (1 - min_pull)
        held = C[b + 1:i + 1].min() >= level * (1 - tol)
        if touched and deep_enough and held and C[i] > level:
            return level, min(level, pull_low)
    return None


def vcp_at(x, i, base_len=65, max_last=0.12, max_first=0.35, near_pivot=0.05):
    if i + 1 < 260:
        return None
    c = x["C"][i]
    ma50, ma150, ma200 = x["ma50"][i], x["ma150"][i], x["ma200"][i]
    if not (c > ma50 > ma150 > ma200 and ma200 > x["ma200_20"][i]
            and c >= x["lo252"][i] * 1.25 and c >= x["hi252"][i] * 0.75):
        return None
    H = x["H"][i + 1 - base_len:i + 1]
    L = x["L"][i + 1 - base_len:i + 1]
    highs = core.swing_highs(H)
    if len(highs) < 2:
        return None
    waves = []
    for k, h in enumerate(highs):
        end = highs[k + 1] if k + 1 < len(highs) else len(H)
        low = L[h:end].min()
        waves.append(((H[h] - low) / H[h], low))
    waves = [w for w in waves if w[0] >= 0.02][-4:]
    if len(waves) < 2:
        return None
    depths = [w[0] for w in waves]
    if not (all(depths[k + 1] < depths[k] for k in range(len(depths) - 1))
            and depths[0] <= max_first and depths[-1] <= max_last):
        return None
    if not x["vol10"][i] < x["vol50"][i]:
        return None
    pivot = H[highs[-1]]
    if c < pivot * (1 - near_pivot):
        return None
    return pivot, waves[-1][1]


def dbottom_at(x, i, lookback=None):
    hit = core.double_bottom_at(x["H"], x["L"], x["C"], x["V"], x["ma200"], i)
    return None if hit is None else (hit[0], hit[1])


RULES = {"breakout": breakout_at, "retest": retest_at, "vcp": vcp_at, "dbottom": dbottom_at}


# =====================================================================
# Historical RS: percentile 1–99 across the S&P 500 for every day
# =====================================================================
def rs_history(frames: dict) -> pd.DataFrame:
    closes = pd.DataFrame({t: df["Close"] for t, df in frames.items()}).sort_index()
    r = lambda n: closes / closes.shift(n) - 1
    score = 0.4 * r(63) + 0.2 * r(126) + 0.2 * r(189) + 0.2 * r(252)
    return (score.rank(axis=1, pct=True) * 98 + 1).round()


# =====================================================================
# 1) Raw signals over history (no filters yet — filters are applied in simulate)
# =====================================================================
def find_signals(frames: dict, lookback=3, modes=core.MODES, progress=None) -> tuple:
    rs = rs_history(frames)
    data, rows = {}, []
    for n, (t, df) in enumerate(frames.items()):
        if progress and n % 25 == 0:
            progress(n / max(len(frames), 1))
        if len(df) < WARMUP + 2:
            continue
        x = indicators(df)
        data[t] = x
        rs_t = rs[t].reindex(df.index).values if t in rs else np.full(len(df), np.nan)
        for i in range(WARMUP, len(df)):
            for mode in modes:
                hit = (vcp_at(x, i) if mode == "vcp" else RULES[mode](x, i, lookback))
                if hit is None:
                    continue
                avg = x["vol20_prev"][i]
                rows.append((t, mode, i, x["dates"][i], x["C"][i], hit[0], hit[1],
                             rs_t[i], x["V"][i] / avg if avg else np.nan))
    if progress:
        progress(1.0)
    sig = pd.DataFrame(rows, columns=["ticker", "mode", "i", "date", "close", "level",
                                      "stop_base", "rs", "vol_ratio"])
    return sig, data


# =====================================================================
# 2) Trades: entry at the signal close, exit at the stop or after `hold` days
# =====================================================================
def simulate(sig: pd.DataFrame, data: dict, mode: str, hold=10, stop_buf=1.0,
             min_rs=70, min_vol=0.0, max_risk=0.0, market_ok=None) -> pd.DataFrame:
    """market_ok: optional pd.Series(date → bool); signals on 'bad market' days are skipped."""
    s = sig[sig["mode"] == mode]
    if market_ok is not None:
        days = pd.to_datetime(s["date"]).dt.normalize()
        s = s[days.map(market_ok).fillna(True).astype(bool).values]
    if min_rs:
        s = s[s["rs"] >= min_rs]
    if min_vol:
        s = s[s["vol_ratio"] >= min_vol]
    s = s.sort_values(["ticker", "i"])
    trades, busy_until = [], {}
    for r in s.itertuples(index=False):
        if r.i <= busy_until.get(r.ticker, -1):        # already in a trade on this stock
            continue
        x = data[r.ticker]
        entry = r.close
        stop = r.stop_base * (1 - stop_buf / 100)
        if stop >= entry:
            continue
        risk = (entry - stop) / entry
        if max_risk and risk * 100 > max_risk:
            continue
        last = len(x["C"]) - 1
        exit_i, exit_px, reason = None, None, None
        for j in range(r.i + 1, min(r.i + hold, last) + 1):
            if x["L"][j] <= stop:                        # stopped; a gap below → open price
                exit_i, exit_px, reason = j, min(x["O"][j], stop), "stop"
                break
        if exit_i is None:
            if r.i + hold > last:                        # not finished yet → leave out
                busy_until[r.ticker] = last
                continue
            exit_i, exit_px, reason = r.i + hold, x["C"][r.i + hold], "time"
        busy_until[r.ticker] = exit_i
        ret = exit_px / entry - 1
        trades.append({
            "ticker": r.ticker, "date": r.date, "exit_date": x["dates"][exit_i],
            "days": exit_i - r.i, "rs": r.rs, "vol_ratio": r.vol_ratio,
            "entry": entry, "stop": stop, "exit": exit_px, "risk_pct": risk * 100,
            "ret_pct": ret * 100, "r": ret / risk, "reason": reason,
            "max_up_pct": (x["H"][r.i + 1:exit_i + 1].max() / entry - 1) * 100,
        })
    cols = ["ticker", "date", "exit_date", "days", "rs", "vol_ratio", "entry", "stop",
            "exit", "risk_pct", "ret_pct", "r", "reason", "max_up_pct"]
    return pd.DataFrame(trades, columns=cols)


# =====================================================================
# 3) Statistics
# =====================================================================
def stats(tr: pd.DataFrame) -> dict:
    if tr.empty:
        return {"trades": 0}
    win, loss = tr[tr["ret_pct"] > 0], tr[tr["ret_pct"] <= 0]
    gross_loss = -loss["ret_pct"].sum()
    streak = best = 0
    for v in tr.sort_values("exit_date")["ret_pct"]:
        streak = streak + 1 if v <= 0 else 0
        best = max(best, streak)
    return {
        "trades": len(tr),
        "win_rate": len(win) / len(tr) * 100,
        "avg_win": win["ret_pct"].mean() if len(win) else 0.0,
        "avg_loss": loss["ret_pct"].mean() if len(loss) else 0.0,
        "expectancy": tr["ret_pct"].mean(),
        "expectancy_r": tr["r"].mean(),
        "profit_factor": win["ret_pct"].sum() / gross_loss if gross_loss > 0 else np.inf,
        "stopped": (tr["reason"] == "stop").mean() * 100,
        "max_losing_streak": best,
        "total_r": tr["r"].sum(),
        "avg_days": tr["days"].mean(),
        # robustness: is the edge broad, or carried by a few lucky trades?
        "median_r": tr["r"].median(),
        "exp_r_ex5": tr["r"].nsmallest(max(len(tr) - 5, 0)).mean() if len(tr) > 5 else np.nan,
    }


def equity_r(tr: pd.DataFrame) -> pd.Series:
    """Cumulative result in R (each trade risks 1R), by exit date."""
    if tr.empty:
        return pd.Series(dtype=float)
    s = tr.sort_values("exit_date")
    return pd.Series(s["r"].cumsum().values, index=pd.to_datetime(s["exit_date"]))


def by_bucket(tr: pd.DataFrame, col: str, bins: list, labels: list) -> pd.DataFrame:
    """Stats per RS / volume bucket."""
    if tr.empty:
        return pd.DataFrame()
    b = pd.cut(tr[col], bins=bins, labels=labels, right=False)
    rows = []
    for lab in labels:
        st_ = stats(tr[b == lab])
        if st_["trades"]:
            rows.append({"bucket": lab, "trades": st_["trades"], "win_rate": st_["win_rate"],
                         "expectancy": st_["expectancy"], "expectancy_r": st_["expectancy_r"],
                         "profit_factor": st_["profit_factor"]})
    return pd.DataFrame(rows)
