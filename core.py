"""
VISAR screener core — data, relative strength, signal detectors and the scan.
No Streamlit here: used by both the web app (app.py) and the daily auto-scan (daily_scan.py).
"""
import io
import math
from datetime import datetime, time
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
import yfinance as yf

NY = ZoneInfo("America/New_York")
HEADERS = {"User-Agent": "Mozilla/5.0"}
MODES = ["breakout", "retest", "vcp"]

DETAILS = {
    "ru": {"det_breakout": "закрытие выше хая {n} свечей",
           "det_retest": "пробой {d} дн. назад, откат к уровню, отскок",
           "det_vcp": "коррекции {w}"},
    "en": {"det_breakout": "close above {n}-candle high",
           "det_retest": "broke out {d}d ago, pulled back to level, bounced",
           "det_vcp": "contractions {w}"},
}

# =====================================================================
# Данные / Data
# =====================================================================
def get_sp500() -> pd.DataFrame:
    """S&P 500 list: Wikipedia, fallback — GitHub CSV."""
    rename = {"Symbol": "ticker", "Security": "name", "Name": "name",
              "GICS Sector": "sector", "Sector": "sector"}
    try:
        html = requests.get(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            headers=HEADERS, timeout=20).text
        df = pd.read_html(io.StringIO(html))[0].rename(columns=rename)
    except Exception:
        df = pd.read_csv(
            "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/"
            "main/data/constituents.csv").rename(columns=rename)
    df["ticker"] = df["ticker"].astype(str).str.replace(".", "-", regex=False)  # BRK.B -> BRK-B
    for col in ("name", "sector"):
        if col not in df:
            df[col] = ""
    return df[["ticker", "name", "sector"]].drop_duplicates("ticker").reset_index(drop=True)


def get_prices(tickers, period="2y", start=None) -> pd.DataFrame:
    """Daily candles for many tickers (2 years by default: MA200 + 12-month RS)."""
    kw = {"start": start} if start else {"period": period}
    return yf.download(list(tickers), interval="1d", group_by="ticker",
                       auto_adjust=False, threads=True, progress=False, **kw)


def market_is_open(now: datetime) -> bool:
    return now.weekday() < 5 and time(9, 30) <= now.time() < time(16, 0)


def clean_frame(prices, ticker, drop_unclosed, now):
    """One ticker's candles; during market hours drop today's unfinished candle."""
    try:
        df = prices[ticker].dropna(subset=["Close", "High", "Low"])
    except KeyError:
        return None
    if drop_unclosed and len(df) and df.index[-1].date() == now.date() and market_is_open(now):
        df = df.iloc[:-1]
    return df if len(df) else None


# =====================================================================
# Относительная сила / Relative strength (IBD / Minervini style)
# =====================================================================
def rs_score(close: pd.Series):
    """Weighted return: 40% — 3 months, 20% each — 6, 9, 12 months."""
    if len(close) < 253:
        return math.nan
    c = close.values
    r = lambda n: c[-1] / c[-1 - n] - 1
    return 0.4 * r(63) + 0.2 * r(126) + 0.2 * r(189) + 0.2 * r(252)


def rs_ratings(frames: dict) -> pd.Series:
    """Percentile 1–99 among all S&P 500 stocks."""
    s = pd.Series({t: rs_score(df["Close"]) for t, df in frames.items()}).dropna()
    return (s.rank(pct=True) * 98 + 1).round().astype(int)


# =====================================================================
# Детекторы / Detectors.
# Return dict: level, stop_base (price the stop goes under), detail (key, args) — or None.
# =====================================================================
def detect_breakout(df, lookback=3):
    """Last close above the high of the previous N candles."""
    if len(df) < lookback + 1:
        return None
    level = df["High"].iloc[-1 - lookback:-1].max()
    if df["Close"].iloc[-1] <= level:
        return None
    return {"level": level, "stop_base": level,
            "detail": ("det_breakout", {"n": lookback})}


def detect_retest(df, lookback=3, max_days=10, tol=0.02, min_pull=0.03):
    """
    N-candle breakout 2..max_days ago → price ran up, pulled back to the broken
    level (± tol), held it, and turns up today.
    """
    n = len(df)
    if n < lookback + max_days + 2:
        return None
    H, L, C = df["High"].values, df["Low"].values, df["Close"].values
    last = n - 1
    if not (C[last] > C[last - 1]):                # today turns up
        return None
    for i in range(last - 2, last - max_days - 1, -1):
        level = H[i - lookback:i].max()
        if C[i] <= level:
            continue
        peak_idx = i + int(np.argmax(H[i:last]))   # high from breakout to yesterday
        peak = H[peak_idx]
        pull_lows = L[peak_idx + 1:last + 1]       # pullback after the peak, incl. today
        if len(pull_lows) == 0:
            continue                               # no pullback — straight run-up
        pull_low = pull_lows.min()
        touched = level * (1 - tol) <= pull_low <= level * (1 + tol)
        deep_enough = pull_low <= peak * (1 - min_pull)
        held = C[i + 1:last + 1].min() >= level * (1 - tol)
        if touched and deep_enough and held and C[last] > level:
            return {"level": level, "stop_base": min(level, pull_low),
                    "detail": ("det_retest", {"d": last - i})}
    return None


def swing_highs(high: np.ndarray, w=5):
    """Indices of local highs (max within ±w bars)."""
    idx = []
    for i in range(w, len(high) - 1):
        lo, hi = max(0, i - w), min(len(high), i + w + 1)
        if high[i] == high[lo:hi].max() and (not idx or i - idx[-1] > w):
            idx.append(i)
    return idx


def detect_vcp(df, base_len=65, max_last=0.12, max_first=0.35, near_pivot=0.05):
    """
    Simplified Minervini VCP:
      • Trend Template: close > MA50 > MA150 > MA200, MA200 rising,
        price ≥ +25% above 52-wk low and within 25% of 52-wk high
      • 2–4 pullbacks in the base, each shallower, last ≤ 12%
      • volume drying up: 10-day avg < 50-day avg
      • price within 5% of the pivot (high of the last contraction)
    """
    if len(df) < 260:
        return None
    C = df["Close"]
    ma50, ma150, ma200 = (C.rolling(n).mean() for n in (50, 150, 200))
    c = C.iloc[-1]
    hi52, lo52 = df["High"].iloc[-252:].max(), df["Low"].iloc[-252:].min()
    trend_ok = (c > ma50.iloc[-1] > ma150.iloc[-1] > ma200.iloc[-1]
                and ma200.iloc[-1] > ma200.iloc[-21]
                and c >= lo52 * 1.25 and c >= hi52 * 0.75)
    if not trend_ok:
        return None

    base = df.iloc[-base_len:]
    H, L = base["High"].values, base["Low"].values
    highs = swing_highs(H)
    if len(highs) < 2:
        return None
    waves = []                                     # (depth, low of that pullback)
    for k, h in enumerate(highs):
        end = highs[k + 1] if k + 1 < len(highs) else len(H)
        low = L[h:end].min()
        waves.append(((H[h] - low) / H[h], low))
    waves = [w for w in waves if w[0] >= 0.02][-4:]     # ignore noise < 2%
    if len(waves) < 2:
        return None
    depths = [w[0] for w in waves]
    contracting = all(depths[k + 1] < depths[k] for k in range(len(depths) - 1))
    if not (contracting and depths[0] <= max_first and depths[-1] <= max_last):
        return None

    vol = df["Volume"]
    if not vol.iloc[-10:].mean() < vol.iloc[-50:].mean():
        return None

    pivot = H[highs[-1]]
    if c < pivot * (1 - near_pivot):
        return None
    return {"level": pivot, "stop_base": waves[-1][1],
            "detail": ("det_vcp", {"w": " → ".join(f"{d * 100:.0f}%" for d in depths)})}


DETECTORS = {"breakout": detect_breakout, "retest": detect_retest, "vcp": detect_vcp}


# =====================================================================
# Сканирование / Scan  (returns internal column keys; UI renames per language)
# =====================================================================
def scan(prices, universe, mode, lookback, drop_unclosed, min_vol_ratio, min_rs,
         account=10_000.0, risk_pct=1.0, stop_buf=1.0, max_risk=0.0):
    now = datetime.now(NY)
    frames = {}
    for t in universe["ticker"]:
        df = clean_frame(prices, t, drop_unclosed, now)
        if df is not None:
            frames[t] = df
    rs = rs_ratings(frames)
    info = universe.set_index("ticker")
    risk_dollars = account * risk_pct / 100

    rows = []
    for t, df in frames.items():
        if len(df) < 25:
            continue
        rating = rs.get(t, np.nan)
        if min_rs and (pd.isna(rating) or rating < min_rs):
            continue
        sig = (detect_vcp(df) if mode == "vcp"
               else DETECTORS[mode](df, lookback))
        if not sig:
            continue

        last = df.iloc[-1]
        close = float(last["Close"])
        avg_vol = df["Volume"].iloc[-21:-1].mean()
        vol_ratio = last["Volume"] / avg_vol if avg_vol else math.nan
        if min_vol_ratio and (math.isnan(vol_ratio) or vol_ratio < min_vol_ratio):
            continue

        level = float(sig["level"])
        stop = float(sig["stop_base"]) * (1 - stop_buf / 100)
        per_share = close - stop
        if per_share <= 0:
            continue
        risk = per_share / close * 100
        if max_risk and risk > max_risk:
            continue
        shares = int(min(risk_dollars // per_share, account // close))

        key, args = sig["detail"]
        rows.append({
            "ticker": t,
            "rs": None if pd.isna(rating) else int(rating),
            "name": info.at[t, "name"] if t in info.index else "",
            "sector": info.at[t, "sector"] if t in info.index else "",
            "close": round(close, 2),
            "level": round(level, 2),
            "pct_level": round((close / level - 1) * 100, 2),
            "stop": round(stop, 2),
            "risk_pct": round(risk, 2),
            "shares": shares,
            "pos_value": round(shares * close, 0),
            "vol_ratio": round(float(vol_ratio), 2),
            "signal_ru": DETAILS["ru"][key].format(**args),
            "signal_en": DETAILS["en"][key].format(**args),
            "date": df.index[-1].strftime("%Y-%m-%d"),
            "chart": f"https://www.tradingview.com/chart/?symbol={t.replace('-', '.')}",
        })
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["rs", "vol_ratio"], ascending=False,
                              na_position="last").reset_index(drop=True)
    return out



# =====================================================================
# Журнал сигналов / Signal journal
# =====================================================================
JOURNAL_COLS = ["date", "mode", "ticker", "rs", "sector", "close", "level", "stop", "risk_pct"]


def journal_rows(result: pd.DataFrame, mode: str) -> pd.DataFrame:
    """Scan result → journal rows (one line per signal)."""
    if result is None or result.empty:
        return pd.DataFrame(columns=JOURNAL_COLS)
    out = result.assign(mode=mode)[["date", "mode", "ticker", "rs", "sector",
                                     "close", "level", "stop", "risk_pct"]]
    return out.reset_index(drop=True)


def merge_journal(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """Append new signals, drop duplicates (same date + mode + ticker)."""
    frames = [f for f in (old, new) if f is not None and not f.empty]
    if not frames:
        return pd.DataFrame(columns=JOURNAL_COLS)
    j = pd.concat(frames, ignore_index=True)
    j["date"] = j["date"].astype(str)
    j = j.drop_duplicates(subset=["date", "mode", "ticker"], keep="last")
    return j.sort_values(["date", "mode", "rs"], ascending=[False, True, False]).reset_index(drop=True)


def _frame_for(prices, ticker):
    try:
        df = prices[ticker] if isinstance(prices.columns, pd.MultiIndex) else prices
        return df.dropna(subset=["Close", "High", "Low"])
    except KeyError:
        return None


def evaluate_journal(journal: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """
    For every logged signal: return after 5 and 10 trading days, return now,
    max run-up, and whether the stop was hit (low ≤ stop) after the signal day.
    """
    rows = []
    for _, s in journal.iterrows():
        df = _frame_for(prices, s["ticker"])
        rec = s.to_dict()
        rec.update(days=0, ret_5d=np.nan, ret_10d=np.nan, ret_now=np.nan,
                   max_up=np.nan, status="nodata")
        if df is None or df.empty:
            rows.append(rec)
            continue
        after = df[df.index.normalize() > pd.Timestamp(s["date"])]
        entry = float(s["close"])
        rec["days"] = len(after)
        if len(after) == 0:
            rec["status"] = "new"
            rows.append(rec)
            continue
        c = after["Close"].values
        rec["ret_now"] = c[-1] / entry - 1
        rec["max_up"] = after["High"].max() / entry - 1
        if len(c) >= 5:
            rec["ret_5d"] = c[4] / entry - 1
        if len(c) >= 10:
            rec["ret_10d"] = c[9] / entry - 1
        hit = after["Low"].values <= float(s["stop"])
        if hit.any():
            k = int(np.argmax(hit))
            rec["status"] = "stopped"
            rec["stop_day"] = k + 1
            # once stopped, the trade result is the stop
            stop_ret = float(s["stop"]) / entry - 1
            if k < 5:
                rec["ret_5d"] = stop_ret
            if k < 10:
                rec["ret_10d"] = stop_ret
        else:
            rec["status"] = "open" if len(c) < 10 else "done10"
        rows.append(rec)
    return pd.DataFrame(rows)


def journal_summary(ev: pd.DataFrame) -> pd.DataFrame:
    """Per-mode stats: signals, win rate at 5d/10d, average returns, % stopped."""
    if ev.empty:
        return pd.DataFrame()
    g = []
    for mode, d in ev.groupby("mode"):
        d5, d10 = d["ret_5d"].dropna(), d["ret_10d"].dropna()
        g.append({
            "mode": mode, "signals": len(d),
            "win_5d": (d5 > 0).mean() * 100 if len(d5) else np.nan,
            "avg_5d": d5.mean() * 100 if len(d5) else np.nan,
            "win_10d": (d10 > 0).mean() * 100 if len(d10) else np.nan,
            "avg_10d": d10.mean() * 100 if len(d10) else np.nan,
            "stopped": (d["status"] == "stopped").mean() * 100,
        })
    return pd.DataFrame(g)
