"""Price data for the S&P 1500 research: Yahoo via yfinance, chunked, cached, bounded retries.

* Same price basis as production (`auto_adjust=False`): OHLC split-adjusted, NOT dividend-
  adjusted; dividends kept separately (`actions=True`) so short P&L can pay them explicitly.
* Bounded retries with backoff on HTTP 429 / empty chunks; never substitutes missing data.
* Invalid bars (non-positive prices, High < max(O,C,L), Low > min(O,C,H), NaN) are removed and
  COUNTED per ticker (a removed bar becomes a missing session, never a repaired one).
* Cache: one pickle per chunk under a cache dir (keyed by tickers + period + date) so a rerun
  does not hit Yahoo again; checksums of the cleaned frames are returned for the manifest.
"""
import hashlib
import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd

PRICE_COLS = ["Open", "High", "Low", "Close", "Volume"]


def clean_bars(df: pd.DataFrame) -> tuple:
    """(clean frame, n_invalid_removed). Index normalised, sorted, duplicates dropped."""
    if df is None or df.empty:
        return df, 0
    d = df.copy()
    d.index = pd.to_datetime(d.index).tz_localize(None).normalize() \
        if getattr(d.index, "tz", None) is not None else pd.to_datetime(d.index).normalize()
    d = d[~d.index.duplicated(keep="last")].sort_index()
    d = d.dropna(subset=["Open", "High", "Low", "Close"])
    if d.empty:
        return d, 0
    o, h, l, c = (d[k].astype(float) for k in ("Open", "High", "Low", "Close"))
    tol = 1e-6
    bad = ((o <= 0) | (h <= 0) | (l <= 0) | (c <= 0)
           | (h < np.maximum.reduce([o, c, l]) * (1 - tol))
           | (l > np.minimum.reduce([o, c, h]) * (1 + tol))
           | (d["Volume"].fillna(0) < 0))
    return d[~bad], int(bad.sum())


def frame_sha(df: pd.DataFrame) -> str:
    cols = [c for c in PRICE_COLS + ["Dividends", "Stock Splits"] if c in df]
    b = pd.util.hash_pandas_object(df[cols].round(8), index=True).values.tobytes()
    return hashlib.sha256(b).hexdigest()


def _chunk_key(chunk, period, asof):
    return hashlib.sha256(f"{','.join(chunk)}|{period}|{asof}".encode()).hexdigest()[:16]


def download(tickers, period="3y", chunk=100, cache_dir=None, asof=None, retries=4,
             pause=2.0, downloader=None, log=print) -> tuple:
    """
    Returns (frames {ticker: DataFrame with OHLCV + Dividends + Stock Splits},
             report DataFrame[ticker, status, rows, first, last, invalid_bars, sha256, reason]).
    downloader(chunk) -> MultiIndex DataFrame (injected in tests); default yfinance.
    """
    if downloader is None:
        import yfinance as yf

        def downloader(ch):
            return yf.download(list(ch), period=period, interval="1d", group_by="ticker",
                               auto_adjust=False, actions=True, threads=True, progress=False)
    cache = Path(cache_dir) if cache_dir else None
    if cache:
        cache.mkdir(parents=True, exist_ok=True)
    tickers = list(dict.fromkeys(tickers))
    frames, rows = {}, []
    for k in range(0, len(tickers), chunk):
        ch = tickers[k:k + chunk]
        raw, cpath = None, None
        if cache:
            cpath = cache / f"{_chunk_key(ch, period, asof)}.pkl"
            if cpath.exists():
                raw = pickle.loads(cpath.read_bytes())
        attempt = 0
        while raw is None and attempt <= retries:
            try:
                got = downloader(ch)
                ok = got is not None and len(got) > 0
                if ok:
                    raw = got
                    if cpath:
                        cpath.write_bytes(pickle.dumps(raw))
                    break
                reason = "empty response"
            except Exception as e:                           # 429 and friends
                reason = f"{type(e).__name__}: {str(e)[:120]}"
            attempt += 1
            wait = pause * (2 ** attempt)
            log(f"chunk {k // chunk}: {reason}; retry {attempt}/{retries} in {wait:.0f}s")
            time.sleep(wait)
        for t in ch:
            if raw is None:
                rows.append(dict(ticker=t, status="missing", reason="download failed"))
                continue
            try:
                f = raw[t] if isinstance(raw.columns, pd.MultiIndex) else raw
            except KeyError:
                rows.append(dict(ticker=t, status="missing", reason="not in response"))
                continue
            f, nbad = clean_bars(f)
            if f is None or f.empty:
                rows.append(dict(ticker=t, status="missing", reason="no valid bars",
                                 invalid_bars=nbad))
                continue
            for col in ("Dividends", "Stock Splits"):
                if col not in f:
                    f[col] = 0.0
            frames[t] = f
            rows.append(dict(ticker=t, status="ok", rows=len(f), first=str(f.index[0].date()),
                             last=str(f.index[-1].date()), invalid_bars=nbad,
                             sha256=frame_sha(f), reason=""))
        time.sleep(pause if raw is not None else 0)
    return frames, pd.DataFrame(rows)


def coverage(report: pd.DataFrame, universe: pd.DataFrame, calendar) -> pd.DataFrame:
    """Per group: tickers, with data, missing, % covered, missing sessions vs the SPY calendar."""
    rep = report.merge(universe[["ticker", "group"]], on="ticker", how="right")
    out = []
    cal = pd.DatetimeIndex(calendar)
    for g, d in rep.groupby("group"):
        ok = d[d["status"] == "ok"]
        out.append(dict(group=g, tickers=len(d), with_data=len(ok),
                        missing=int((d["status"] != "ok").sum()),
                        coverage_pct=100 * len(ok) / len(d) if len(d) else np.nan,
                        invalid_bars=int(ok["invalid_bars"].fillna(0).sum()),
                        median_rows=float(ok["rows"].median()) if len(ok) else np.nan,
                        calendar_sessions=len(cal)))
    return pd.DataFrame(out)


def missing_sessions(frames: dict, calendar) -> pd.DataFrame:
    """Sessions of the market calendar a ticker has no bar for (inside its own data span)."""
    cal = pd.DatetimeIndex(calendar)
    rows = []
    for t, f in frames.items():
        span = cal[(cal >= f.index[0]) & (cal <= f.index[-1])]
        miss = span.difference(f.index)
        if len(miss):
            rows.append(dict(ticker=t, missing_sessions=len(miss),
                             first_missing=str(miss[0].date()),
                             last_missing=str(miss[-1].date())))
    return pd.DataFrame(rows, columns=["ticker", "missing_sessions", "first_missing",
                                       "last_missing"])
