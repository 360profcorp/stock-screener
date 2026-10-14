"""
VISAR daily auto-scan — runs on GitHub Actions every weekday after the US close.
  1. scans the S&P 500 for all three setups (breakout, retest, VCP)
  2. appends the signals to journal/signals.csv (the app's "Journal" tab reads it)
  3. sends a push notification to the phone via ntfy (free app, no account)

A push is sent on every run — with signals, or with the reason nothing was found.
The journal de-duplicates by date + setup + ticker, so re-runs and holidays are harmless.

Settings come from environment variables — the `env:` block in .github/workflows/daily-scan.yml:
  NTFY_TOPIC   — your private ntfy topic name (repository secret). Without it the push is skipped.
  MIN_RS       — minimum relative strength, 0–99 (default 70)
  MIN_VOL      — minimum volume vs 20-day average, e.g. 1.5; 0 = no filter (default 0)
  STOP_BUF     — stop buffer below the level, % (default 1)
  MAX_RISK     — skip signals whose stop is farther than this %, 0 = no limit (default 0)
  LOOKBACK     — candles to break for breakout / retest, 2 or 3 (default 3)
  MARKET_FILTER — take signals only when the market is in an uptrend (SPY):
                 off | ma50 | ma200 | both  (default off)
  SETUPS       — which setups the auto-scan logs and pushes, comma-separated
                 (default breakout,retest,vcp — double bottom is off: the backtest rated it ❌)
  REPEAT_DAYS  — don't log the same stock + setup again within this many trading days,
                 0 = log every day (default 10, like the backtest's holding period)
  APP_URL      — link opened when you tap the notification
"""
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests

import core

JOURNAL = Path(__file__).parent / "journal" / "signals.csv"
def _env(name, default, cast=float):
    v = os.getenv(name, "").strip()
    try:
        return cast(v) if v else default
    except ValueError:
        print(f"bad {name}={v!r}, using {default}")
        return default


MIN_RS = _env("MIN_RS", 70, int)
MIN_VOL = _env("MIN_VOL", 0.0)
STOP_BUF = _env("STOP_BUF", 1.0)
MAX_RISK = _env("MAX_RISK", 0.0)
LOOKBACK = _env("LOOKBACK", 3, int)
REPEAT_DAYS = _env("REPEAT_DAYS", 10, int)
SETUPS = [m.strip() for m in os.getenv("SETUPS", "breakout,retest,vcp").lower().split(",")
          if m.strip() in core.MODES] or ["breakout", "retest", "vcp"]
MARKET_FILTER = os.getenv("MARKET_FILTER", "off").strip().lower() or "off"
if MARKET_FILTER not in core.MARKET_FILTERS:
    print(f"bad MARKET_FILTER={MARKET_FILTER!r}, using off")
    MARKET_FILTER = "off"
MKT_NAMES = {"off": "без фильтра", "ma50": "SPY > MA50", "ma200": "SPY > MA200",
             "both": "SPY > MA50 и MA200"}
APP_URL = os.getenv("APP_URL", "https://dmitry-screener.streamlit.app")
TOPIC = os.getenv("NTFY_TOPIC", "").strip()
NAMES = {"breakout": "Пробой", "retest": "Ретест", "vcp": "VCP", "dbottom": "Двойное дно"}


def send_push(title, message, tags="chart_with_upwards_trend"):
    if not TOPIC:
        print("NTFY_TOPIC not set — push skipped")
        return
    try:
        r = requests.post(f"https://ntfy.sh/{TOPIC}", data=message.encode("utf-8"),
                          headers={"Title": title.encode("utf-8"), "Tags": tags,
                                   "Click": APP_URL},
                          timeout=20)
        print("push:", r.status_code)
    except Exception as e:                                   # never fail the job on a push
        print("push failed:", e)


def last_dates(prices, tickers):
    """Date of the last candle for every ticker that has data."""
    out = {}
    for t in tickers:
        df = core._frame_for(prices, t)
        if df is not None and len(df):
            out[t] = df.index[-1].strftime("%Y-%m-%d")
    return pd.Series(out, dtype=object)


SKIPPED = {}


def drop_repeats(res, mode, old, data_date):
    """Skip a stock if the same setup was already logged within REPEAT_DAYS trading days."""
    if not REPEAT_DAYS or res.empty or old is None or old.empty:
        return res
    prev = old[(old["mode"] == mode) & (old["date"].astype(str) < data_date)]
    if prev.empty:
        return res
    last = prev.groupby("ticker")["date"].max().astype(str)
    gap = {t: np.busday_count(d, data_date) for t, d in last.items()}
    keep = res["ticker"].map(lambda t: gap.get(t, 10**6) > REPEAT_DAYS)
    skipped = (~keep).sum()
    if skipped:
        SKIPPED[mode] = int(skipped)
        print(f"{mode}: {skipped} repeat signal(s) skipped")
    return res[keep].reset_index(drop=True)


def market_status(prices, data_date):
    """('🟢 Рынок: …' line, does the market pass MARKET_FILTER)."""
    spy = core._frame_for(prices, "SPY")
    if spy is None or len(spy) < 200:
        return "Рынок: нет данных по SPY", True
    reg = core.market_regime(spy)
    day = pd.Timestamp(data_date)
    row = reg.loc[:day].dropna().iloc[-1]
    if row["above50"] and row["above200"]:
        icon, word = "🟢", "в аптренде"
    elif not row["above50"] and not row["above200"]:
        icon, word = "🔴", "слабый"
    else:
        icon, word = "🟡", "смешанный"
    line = (f"{icon} Рынок {word}: SPY {row['close']:.0f}, "
            f"MA50 {row['ma50']:.0f}, MA200 {row['ma200']:.0f}")
    return line, core.regime_ok(row, MARKET_FILTER)


def build_message(results, data_date):
    lines = []
    for mode in [m for m in ("vcp", "dbottom", "retest", "breakout") if m in results]:
        res = results[mode]
        rep = f" (+{SKIPPED[mode]} повтор.)" if SKIPPED.get(mode) else ""
        if res.empty:
            lines.append(f"{NAMES[mode]}: 0{rep}")
            continue
        top = ", ".join(f"{r.ticker} ({r.rs})" for r in res.head(6).itertuples())
        more = f" +{len(res) - 6}" if len(res) > 6 else ""
        lines.append(f"{NAMES[mode]}: {len(res)} — {top}{more}{rep}")
    d = datetime.strptime(data_date, "%Y-%m-%d").strftime("%d.%m.%Y")
    return f"Свечи на {d}, RS ≥ {MIN_RS}, стоп −{STOP_BUF:g}%\n" + "\n".join(lines)


def main():
    now = datetime.now(core.NY)
    if now.weekday() >= 5:
        print("weekend — nothing to do")
        return 0

    universe = core.get_sp500()
    tickers = list(universe["ticker"])
    prices = core.get_prices(tuple(tickers) + ("SPY",))

    dates = last_dates(prices, tickers)
    print(f"tickers with data: {len(dates)}/{len(tickers)}")
    if dates.empty:
        send_push("VISAR Screener: нет данных",
                  "Yahoo не отдал котировки серверу GitHub. Попробую завтра; "
                  "можно перезапустить вручную: Actions → Daily scan → Run workflow.",
                  tags="warning")
        return 0
    print("last candle dates:", dates.value_counts().head(3).to_dict())

    # The market date = the most common last-candle date. Tickers whose data stops
    # earlier (stale/partial download) are left out so they don't produce old signals.
    data_date = dates.value_counts().idxmax()
    fresh = universe[universe["ticker"].isin(dates[dates == data_date].index)]
    print(f"data date: {data_date}, fresh tickers: {len(fresh)}")

    reg_line, market_pass = market_status(prices, data_date)
    print(reg_line)
    print(f"settings: RS≥{MIN_RS}, vol≥{MIN_VOL}, stop buffer {STOP_BUF}%, "
          f"max risk {MAX_RISK or '—'}%, lookback {LOOKBACK}, repeat {REPEAT_DAYS}d, "
          f"market filter {MARKET_FILTER}, setups {','.join(SETUPS)}")
    results = {m: core.scan(prices, fresh, m, LOOKBACK, True, MIN_VOL, MIN_RS,
                            stop_buf=STOP_BUF, max_risk=MAX_RISK)
               for m in SETUPS}

    if not market_pass:
        print(f"market filter {MARKET_FILTER}: market doesn't pass — no signals logged")
        results = {m: r.iloc[0:0] for m, r in results.items()}

    old = pd.read_csv(JOURNAL) if JOURNAL.exists() else None
    results = {m: drop_repeats(results[m], m, old, data_date) for m in SETUPS}
    new = pd.concat([core.journal_rows(results[m], m) for m in SETUPS], ignore_index=True)
    before = 0 if old is None else len(old)
    journal = core.merge_journal(old, new)
    JOURNAL.parent.mkdir(exist_ok=True)
    journal.to_csv(JOURNAL, index=False)
    print(f"journal: {len(new)} signals today, total {len(journal)} (+{len(journal) - before})")

    msg = build_message(results, data_date) + "\n" + reg_line
    if not market_pass:
        msg += f"\n⛔ Фильтр рынка ({MKT_NAMES[MARKET_FILTER]}): сигналы сегодня не записаны."
    if data_date != now.strftime("%Y-%m-%d"):
        msg += "\n⚠️ Сегодняшних свечей ещё нет — это сигналы прошлой сессии."
    print(msg)
    send_push(f"VISAR Screener: {len(new)} signals", msg)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        send_push("VISAR Screener: ошибка скана",
                  traceback.format_exc(limit=2)[-600:], tags="rotating_light")
        sys.exit(1)
