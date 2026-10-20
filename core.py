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
MODES = ["breakout", "retest", "vcp", "dbottom"]

DETAILS = {
    "ru": {"det_breakout": "закрытие выше хая {n} свечей",
           "det_retest": "пробой {d} дн. назад, откат к уровню, отскок",
           "det_vcp": "коррекции {w}",
           "det_dbottom": "W-база −{d}%, 2-е дно {u}, пробой середины"},
    "en": {"det_breakout": "close above {n}-candle high",
           "det_retest": "broke out {d}d ago, pulled back to level, bounced",
           "det_vcp": "contractions {w}",
           "det_dbottom": "W base −{d}%, 2nd low {u}, mid-peak breakout"},
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


def double_bottom_at(H, L, C, V, ma200, i, min_depth=0.15, max_depth=0.35,
                     undercut=0.03, over=0.02, gap=(15, 50), recent=(3, 25), max_loss=0.07):
    """
    Double bottom / W base (O'Neil) evaluated at bar i, using data up to i only.
      • first low A, a mid-peak M, a second low B 3–10 weeks after A
      • base depth (prior high → A) 15–35%
      • B at A's level or slightly under it (undercut ≤ 3%, or ≤ 2% above)
      • lighter volume around B than around A
      • price above MA200 (W bases inside a long-term uptrend only)
      • today: first close above the mid-peak
    Stop: under the second low, but never more than 7% under the mid-peak
    (O'Neil's 7–8% max-loss rule — a deep base must not mean a huge risk).
    Returns (level = mid-peak, stop_base, depth, undercut) or None.
    """
    if i < 260 or not np.isfinite(ma200[i]) or C[i] <= ma200[i]:
        return None
    lo, hi = i - recent[1], i - recent[0]
    b = lo + int(np.argmin(L[lo:i]))                 # second low = lowest low of the last 25 bars
    if b > hi:                                       # too fresh — needs at least 3 bars of rally
        return None
    a_lo, a_hi = b - gap[1], b - gap[0]
    a = a_lo + int(np.argmin(L[a_lo:a_hi + 1]))      # first low 15–50 bars before B
    if a < 31:
        return None
    m = a + 1 + int(np.argmax(H[a + 1:b]))           # mid-peak between the lows
    top = H[a - 30:a].max()                          # where the base started
    depth = (top - L[a]) / top
    if not (min_depth <= depth <= max_depth):
        return None
    if not (L[a] * (1 - undercut) <= L[b] <= L[a] * (1 + over)):
        return None
    if H[m] < L[a] * 1.05 or H[m] >= top:            # real W: mid-peak +5% off the low, below the top
        return None
    if V[max(b - 2, 0):b + 3].mean() >= V[max(a - 2, 0):a + 3].mean():
        return None                                  # volume should dry up on the second low
    if not (C[i] > H[m] >= C[i - 1]):                # fresh breakout of the mid-peak today
        return None
    return H[m], max(L[b], H[m] * (1 - max_loss)), depth, L[b] / L[a] - 1


def detect_double_bottom(df, lookback=None):
    x = df.dropna(subset=["Close", "High", "Low"])
    ma200 = x["Close"].rolling(200).mean().values
    hit = double_bottom_at(x["High"].values.astype(float), x["Low"].values.astype(float),
                           x["Close"].values.astype(float), x["Volume"].values.astype(float),
                           ma200, len(x) - 1)
    if hit is None:
        return None
    level, stop_base, depth, under = hit
    u = f"{under * 100:+.1f}%"
    return {"level": level, "stop_base": stop_base,
            "detail": ("det_dbottom", {"d": f"{depth * 100:.0f}", "u": u})}


DETECTORS = {"breakout": detect_breakout, "retest": detect_retest, "vcp": detect_vcp,
             "dbottom": detect_double_bottom}


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
        sig = (DETECTORS[mode](df) if mode in ("vcp", "dbottom")
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
    Long exit on the FIRST stop day: at the open if it opened below the stop (gap through
    the stop), otherwise at the stop. That exit price is the result of ret_now and of every
    horizon reached on or after the stop day; later recoveries are ignored.
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
        n = len(c)
        rec["ret_now"] = c[-1] / entry - 1
        rec["max_up"] = after["High"].max() / entry - 1
        stop = float(s["stop"])
        hit = after["Low"].values <= stop
        k = int(np.argmax(hit)) if hit.any() else None
        exit_px = stop
        if k is not None:
            o = float(after["Open"].iloc[k])
            if o < stop:                                  # gapped through the stop
                exit_px = o
            rec["exit_price"] = exit_px
            rec["gap_through_stop"] = bool(o < stop)
        stop_ret = exit_px / entry - 1

        def ret_at(day):
            # result after `day` trading days — only once that many days have passed;
            # if the stop was hit on or before that day, the trade was closed at exit_px
            if n < day:
                return np.nan
            return stop_ret if (k is not None and k < day) else c[day - 1] / entry - 1

        rec["ret_5d"], rec["ret_10d"] = ret_at(5), ret_at(10)
        if k is not None:
            rec["status"] = "stopped"
            rec["stop_day"] = k + 1
            rec["ret_now"] = stop_ret                     # closed trade: result is the exit
            rec["max_up"] = after["High"].iloc[:k + 1].max() / entry - 1
        else:
            rec["status"] = "open" if n < 10 else "done10"
        rows.append(rec)
    return pd.DataFrame(rows)


def journal_summary(ev: pd.DataFrame) -> pd.DataFrame:
    """
    Per-setup stats. 'Now' covers every signal (closed at stop or marked to market);
    5d / 10d stats count only trades whose 5 / 10 days have passed, with the sample size shown.
    """
    if ev.empty:
        return pd.DataFrame()
    g = []
    for mode, d in ev.groupby("mode"):
        now = d["ret_now"].dropna()
        d5, d10 = d["ret_5d"].dropna(), d["ret_10d"].dropna()
        pct = lambda x: (x > 0).mean() * 100 if len(x) else np.nan
        avg = lambda x: x.mean() * 100 if len(x) else np.nan
        g.append({
            "mode": mode, "signals": len(d),
            "win_now": pct(now), "avg_now": avg(now),
            "stopped": (d["status"] == "stopped").mean() * 100,
            "n_5d": len(d5), "win_5d": pct(d5), "avg_5d": avg(d5),
            "n_10d": len(d10), "win_10d": pct(d10), "avg_10d": avg(d10),
        })
    return pd.DataFrame(g)


# =====================================================================
# Состояние рынка / Market regime (S&P 500 via SPY)
# =====================================================================
MARKET_FILTERS = ["off", "ma50", "ma200", "both"]


def market_regime(spy: pd.DataFrame) -> pd.DataFrame:
    """SPY close vs its 50/200-day averages for every day."""
    c = spy["Close"].astype(float)
    out = pd.DataFrame({"close": c, "ma50": c.rolling(50).mean(),
                        "ma200": c.rolling(200).mean()})
    out["above50"] = out["close"] > out["ma50"]
    out["above200"] = out["close"] > out["ma200"]
    out.index = pd.to_datetime(out.index).normalize()
    return out


def regime_ok(reg_row, flt: str) -> bool:
    """Is the market good enough to take signals under filter `flt`?"""
    if flt == "off" or reg_row is None:
        return True
    if flt == "ma50":
        return bool(reg_row["above50"])
    if flt == "ma200":
        return bool(reg_row["above200"])
    return bool(reg_row["above50"] and reg_row["above200"])


def regime_mask(reg: pd.DataFrame, flt: str) -> pd.Series:
    """Per-day True/False under filter `flt` (for the backtest)."""
    if flt == "off":
        return pd.Series(True, index=reg.index)
    if flt == "ma50":
        return reg["above50"]
    if flt == "ma200":
        return reg["above200"]
    return reg["above50"] & reg["above200"]


# =====================================================================
# Отчётность / Earnings dates (Yahoo Finance, upcoming only)
# =====================================================================
def _next_earnings_one(ticker: str, today):
    """Next earnings date for one ticker (date or None). Never raises."""
    try:
        tk = yf.Ticker(ticker)
        cal = tk.calendar
        dates = []
        if isinstance(cal, dict):
            dates = cal.get("Earnings Date") or []
        elif isinstance(cal, pd.DataFrame) and "Earnings Date" in cal.index:
            dates = list(cal.loc["Earnings Date"].values)
        dates = [pd.Timestamp(d).date() for d in dates if pd.notna(d)]
        upcoming = sorted(d for d in dates if d >= today)
        if upcoming:
            return upcoming[0]
        ed = tk.get_earnings_dates(limit=8)              # fallback endpoint
        if ed is not None and len(ed):
            ds = sorted({pd.Timestamp(x).date() for x in ed.index})
            upcoming = [d for d in ds if d >= today]
            return upcoming[0] if upcoming else None
    except Exception:
        pass
    return None


def next_earnings(tickers, today=None) -> dict:
    """{ticker: next earnings date or None} — fetched in parallel, only for given tickers."""
    from concurrent.futures import ThreadPoolExecutor
    today = today or datetime.now(NY).date()
    tickers = list(dict.fromkeys(tickers))
    if not tickers:
        return {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        dates = list(pool.map(lambda t: _next_earnings_one(t, today), tickers))
    return dict(zip(tickers, dates))


def apply_earnings(result: pd.DataFrame, earnings: dict, days: int, today=None):
    """
    Adds 'earnings' (date) and 'earn_days' (trading days until it) to the scan result
    and drops signals whose report is within `days` trading days (0 = keep all).
    Unknown dates are kept. Returns (filtered result, number dropped).
    """
    if result is None or result.empty:
        return result, 0
    today = today or datetime.now(NY).date()
    out = result.copy()
    ed = out["ticker"].map(earnings.get)
    out["earnings"] = ed.map(lambda d: d.strftime("%Y-%m-%d") if d else "")
    out["earn_days"] = ed.map(
        lambda d: int(np.busday_count(today, d)) if d else None).astype("Int64")
    if not days:
        return out.reset_index(drop=True), 0
    soon = out["earn_days"].notna() & (out["earn_days"] <= days)
    return out[~soon].reset_index(drop=True), int(soon.sum())


# =====================================================================
# Buy-stop entries: setups that have NOT broken out yet.
# An order waits above the pivot; it fills only if price trades through it.
# =====================================================================
PENDING_MODES = ["vcp", "breakout"]


def stop_trigger(pivot: float) -> float:
    """Buy-stop price a hair above the pivot (+0.1%, at least 1 cent)."""
    return round(max(pivot * 1.001, pivot + 0.01), 2)


def breakout_pending_at(H, C, i, lookback=3, near=0.02):
    """Close is within `near` below the high of the last N candles (incl. today)."""
    if i < lookback:
        return None
    pivot = float(H[i - lookback + 1:i + 1].max())
    if C[i] >= pivot or C[i] < pivot * (1 - near):
        return None
    return pivot, pivot                     # (pivot, stop_base) — stop under the pivot


def detect_pending(df, mode, lookback=3, near=0.02):
    """Live version for the last bar. Returns dict(pivot, stop_base) or None."""
    if mode == "breakout":
        hit = breakout_pending_at(df["High"].values, df["Close"].values, len(df) - 1,
                                  lookback, near)
        return None if hit is None else {"pivot": hit[0], "stop_base": hit[1]}
    if mode == "vcp":
        s = detect_vcp(df)
        if s and df["Close"].iloc[-1] < s["level"]:            # not broken out yet
            return {"pivot": float(s["level"]), "stop_base": float(s["stop_base"])}
    return None


def pending_candidates(prices, universe, modes=PENDING_MODES, lookback=3, near_pct=2.0,
                       min_rs=85, stop_buf=3.0, max_risk=0.0, limit_pct=1.0,
                       drop_unclosed=True):
    """Tomorrow's buy-stop orders: pivot, buy-stop trigger, limit cap and stop for each."""
    now = datetime.now(NY)
    frames = {}
    for t in universe["ticker"]:
        df = clean_frame(prices, t, drop_unclosed, now)
        if df is not None and len(df) >= 260:
            frames[t] = df
    rs = rs_ratings(frames)
    info = universe.set_index("ticker")
    rows = []
    for t, df in frames.items():
        rating = rs.get(t, np.nan)
        if min_rs and (pd.isna(rating) or rating < min_rs):
            continue
        close = float(df["Close"].iloc[-1])
        for mode in modes:
            hit = detect_pending(df, mode, lookback, near_pct / 100)
            if not hit:
                continue
            trig = stop_trigger(hit["pivot"])
            stop = round(hit["stop_base"] * (1 - stop_buf / 100), 2)
            if stop >= trig:
                continue
            risk = (trig - stop) / trig * 100
            if max_risk and risk > max_risk:
                continue
            rows.append({"date": df.index[-1].strftime("%Y-%m-%d"), "mode": mode,
                         "ticker": t, "rs": int(rating),
                         "sector": info.at[t, "sector"] if t in info.index else "",
                         "close": round(close, 2), "pivot": round(hit["pivot"], 2),
                         "trigger": trig, "limit": round(trig * (1 + limit_pct / 100), 2),
                         "stop": stop, "risk_pct": round(risk, 2),
                         "dist_pct": round((trig / close - 1) * 100, 2)})
            break                                   # one order per stock (vcp first)
    out = pd.DataFrame(rows)
    if not out.empty:
        out["prio"] = out["mode"].map({m: k for k, m in enumerate(modes)})
        out = (out.sort_values(["prio", "rs"], ascending=[True, False])
                  .drop(columns="prio").reset_index(drop=True))
    return out
