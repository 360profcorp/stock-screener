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
def find_pending(frames: dict, data: dict, lookback=3, near_pct=2.0) -> pd.DataFrame:
    """Every historical day a buy-stop order would have been placed (setup not broken yet)."""
    rs = rs_history(frames)
    rows = []
    for t, x in data.items():
        rs_t = rs[t].reindex(x["dates"]).values if t in rs else np.full(len(x["C"]), np.nan)
        for i in range(WARMUP, len(x["C"]) - 1):
            v = vcp_at(x, i)
            if v and x["C"][i] < v[0]:
                rows.append((t, "vcp", i, x["dates"][i], x["C"][i], v[0], v[1], rs_t[i]))
                continue
            b = core.breakout_pending_at(x["H"], x["C"], i, lookback, near_pct / 100)
            if b:
                rows.append((t, "breakout", i, x["dates"][i], x["C"][i], b[0], b[1], rs_t[i]))
    return pd.DataFrame(rows, columns=["ticker", "mode", "i", "date", "close", "pivot",
                                       "stop_base", "rs"])


LEGACY_COLS = ["ticker", "date", "exit_date", "days", "rs", "vol_ratio", "entry", "stop",
               "exit", "risk_pct", "ret_pct", "r", "reason", "max_up_pct"]
FULL_COLS = LEGACY_COLS + ["signal_date", "entry_at", "status", "window_complete",
                           "mark_date", "mark", "mark_r"]


def _trade(x, ticker, rs, vol_ratio, sig_i, e, entry, stop, risk, hold, first, entry_at,
           same_day_stop=None, up_from=None):
    """
    One trade outcome, independent of any other trade (no position ownership here).
    e = entry bar, first = first bar the stop can trigger on.
    status "closed": exited by stop or after `hold` bars.
    status "open":   neither happened before the last bar — no exit price is invented;
                     the position is described by its last close (mark) instead.
    """
    last = len(x["C"]) - 1
    up_from = first if up_from is None else up_from      # first bar of the max-up window
    exit_i = exit_px = reason = None
    if same_day_stop is not None:                         # buy-stop: stop on the entry bar
        exit_i, exit_px, reason = e, same_day_stop, "stop"
    else:
        for j in range(first, min(e + hold, last) + 1):
            if x["L"][j] <= stop:                         # gap below the stop → open price
                exit_i, exit_px, reason = j, (stop if j == e else min(x["O"][j], stop)), "stop"
                break
    if exit_i is None and e + hold <= last:
        exit_i, exit_px, reason = e + hold, x["C"][e + hold], "time"
    row = {"ticker": ticker, "date": x["dates"][e], "rs": rs, "vol_ratio": vol_ratio,
           "entry": entry, "stop": stop, "risk_pct": risk * 100,
           "signal_date": x["dates"][sig_i], "entry_at": entry_at,
           "window_complete": e + hold <= last,
           "_sig_i": sig_i, "_e": e}
    if exit_i is None:                                    # still open at the end of the data
        mark = float(x["C"][last])
        row.update({"exit_date": pd.NaT, "days": last - e, "exit": np.nan, "ret_pct": np.nan,
                    "r": np.nan, "reason": "open", "status": "open",
                    "mark_date": x["dates"][last], "mark": mark,
                    "mark_r": (mark / entry - 1) / risk,
                    "max_up_pct": (x["H"][up_from:last + 1].max() / entry - 1) * 100
                    if last >= up_from else np.nan, "_x": last})
    else:
        ret = exit_px / entry - 1
        row.update({"exit_date": x["dates"][exit_i], "days": exit_i - e, "exit": exit_px,
                    "ret_pct": ret * 100, "r": ret / risk, "reason": reason, "status": "closed",
                    "mark_date": pd.NaT, "mark": np.nan, "mark_r": np.nan,
                    "max_up_pct": (x["H"][up_from:exit_i + 1].max() / entry - 1) * 100
                    if exit_i >= up_from else (x["H"][e] / entry - 1) * 100, "_x": exit_i})
    return row


def _finish(rows, chk_key, one_per_ticker, include_open):
    """
    Position ownership (optional) + output shape.
    one_per_ticker=True reproduces the original signal-level rule: while a hypothetical trade
    on a ticker is open, later signals on that ticker are ignored (checked on `chk_key`).
    Portfolio replays should use one_per_ticker=False: the portfolio decides ownership, so a
    trade it rejects can never hide a later valid signal.
    """
    out = []
    if one_per_ticker:
        busy = {}
        for r in rows:                                    # rows are in (ticker, signal) order
            if r[chk_key] <= busy.get(r["ticker"], -1):
                continue
            busy[r["ticker"]] = r["_x"]
            out.append(r)
    else:
        out = list(rows)
    if not include_open:
        out = [r for r in out if r["status"] == "closed"]
    full = include_open or not one_per_ticker
    df = pd.DataFrame(out, columns=FULL_COLS if full else LEGACY_COLS)
    if full and len(df):
        df["window_complete"] = df["window_complete"].astype(bool)
    return df


def simulate_stop(pend: pd.DataFrame, data: dict, mode: str, hold=20, stop_buf=3.0,
                  min_rs=85, max_risk=0.0, market_ok=None, limit_pct=1.0,
                  one_per_ticker=True, include_open=False) -> pd.DataFrame:
    """
    Buy-stop entry: order placed after the close of day i at stop_trigger(pivot) with a limit
    `limit_pct` above. Day i+1: fills only if the high reaches the trigger; a gap above the
    trigger fills at the open, a gap above the limit fills only if price comes back to the limit.
    Same-day stop: if day i+1 also trades down to the stop, the trade is stopped (worst case).
    one_per_ticker / include_open: see _finish() and simulate().
    """
    s = pend[pend["mode"] == mode]
    if min_rs:
        s = s[s["rs"] >= min_rs]
    if market_ok is not None:
        days = pd.to_datetime(s["date"]).dt.normalize()
        s = s[days.map(market_ok).fillna(True).astype(bool).values]
    s = s.sort_values(["ticker", "i"])
    rows = []
    for r in s.itertuples(index=False):
        j = r.i + 1
        x = data[r.ticker]
        if j >= len(x["C"]):
            continue
        trig = core.stop_trigger(r.pivot)
        lim = trig * (1 + limit_pct / 100)
        O, H, L = x["O"][j], x["H"][j], x["L"][j]
        if H < trig:
            continue                                    # never broke out — order expires
        if O <= lim:
            entry = max(O, trig)
        elif L <= lim:
            entry = lim                                 # gapped above the limit, came back
        else:
            continue                                    # ran away — no fill
        stop = r.stop_base * (1 - stop_buf / 100)
        if stop >= entry:
            continue
        risk = (entry - stop) / entry
        if max_risk and risk * 100 > max_risk:
            continue
        rows.append(_trade(x, r.ticker, r.rs, np.nan, r.i, j, entry, stop, risk, hold,
                           j + 1, "stop", same_day_stop=stop if L <= stop else None,
                           up_from=j))
    return _finish(rows, "_e", one_per_ticker, include_open)


def simulate(sig: pd.DataFrame, data: dict, mode: str, hold=10, stop_buf=1.0,
             min_rs=70, min_vol=0.0, max_risk=0.0, market_ok=None,
             entry_at="close", one_per_ticker=True, include_open=False) -> pd.DataFrame:
    """
    market_ok: optional pd.Series(date → bool); signals on 'bad market' days are skipped.
    entry_at: "close" — buy at the signal-day close;
              "open"  — buy at the next day's open (gap included). If it opens at/below the
                        stop the trade is skipped; the stop can be hit the same day.
    one_per_ticker: True (default, signal-level statistics) — one hypothetical trade per stock
                    at a time, exactly as before. False — every valid signal becomes a trade;
                    use this for portfolio replays, where the portfolio owns the positions.
    include_open:   False (default) — only closed trades, as before. True — trades whose stop
                    or holding period is not reached by the last bar are returned with
                    status="open" and a mark-to-market (mark, mark_r) instead of an exit.
    With either option changed, extra columns are returned: signal_date, entry_at, status,
    window_complete, mark_date, mark, mark_r.
    """
    s = sig[sig["mode"] == mode]
    if market_ok is not None:
        days = pd.to_datetime(s["date"]).dt.normalize()
        s = s[days.map(market_ok).fillna(True).astype(bool).values]
    if min_rs:
        s = s[s["rs"] >= min_rs]
    if min_vol:
        s = s[s["vol_ratio"] >= min_vol]
    s = s.sort_values(["ticker", "i"])
    rows = []
    for r in s.itertuples(index=False):
        x = data[r.ticker]
        last = len(x["C"]) - 1
        if entry_at == "open":
            e = r.i + 1                                   # entry day
            if e > last:
                continue
            entry, first = x["O"][e], e                   # stop can hit on the entry day
        else:
            e, entry, first = r.i, r.close, r.i + 1
        stop = r.stop_base * (1 - stop_buf / 100)
        if stop >= entry:
            continue
        risk = (entry - stop) / entry
        if max_risk and risk * 100 > max_risk:
            continue
        rows.append(_trade(x, r.ticker, r.rs, r.vol_ratio, r.i, e, entry, stop, risk, hold,
                           first, entry_at))
    return _finish(rows, "_sig_i", one_per_ticker, include_open)


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
