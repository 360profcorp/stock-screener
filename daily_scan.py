"""
VISAR daily auto-scan — runs on GitHub Actions every weekday after the US close.
  1. scans the S&P 500 for all three setups (breakout, retest, VCP)
  2. appends the signals to journal/signals.csv (the app's "Journal" tab reads it)
  3. sends a push notification to the phone via ntfy (free app, no account)

A push is sent on every run — with signals, or with the reason nothing was found.
The journal de-duplicates by date + setup + ticker, so re-runs and holidays are harmless.

Settings come from environment variables (GitHub → Settings → Secrets and variables → Actions):
  NTFY_TOPIC  — your private ntfy topic name (secret). Without it the push is skipped.
  MIN_RS      — RS filter for the auto-scan (default 70)
  APP_URL     — link opened when you tap the notification
"""
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

import core

JOURNAL = Path(__file__).parent / "journal" / "signals.csv"
MIN_RS = int(os.getenv("MIN_RS", "70"))
APP_URL = os.getenv("APP_URL", "https://dmitry-screener.streamlit.app")
TOPIC = os.getenv("NTFY_TOPIC", "").strip()
NAMES = {"breakout": "Пробой", "retest": "Ретест", "vcp": "VCP"}


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


def build_message(results, data_date):
    lines = []
    for mode in ("vcp", "retest", "breakout"):          # most selective first
        res = results[mode]
        if res.empty:
            lines.append(f"{NAMES[mode]}: 0")
            continue
        top = ", ".join(f"{r.ticker} ({r.rs})" for r in res.head(6).itertuples())
        more = f" +{len(res) - 6}" if len(res) > 6 else ""
        lines.append(f"{NAMES[mode]}: {len(res)} — {top}{more}")
    d = datetime.strptime(data_date, "%Y-%m-%d").strftime("%d.%m.%Y")
    return f"Свечи на {d}, RS ≥ {MIN_RS}\n" + "\n".join(lines)


def main():
    now = datetime.now(core.NY)
    if now.weekday() >= 5:
        print("weekend — nothing to do")
        return 0

    universe = core.get_sp500()
    tickers = list(universe["ticker"])
    prices = core.get_prices(tuple(tickers))

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

    results = {m: core.scan(prices, fresh, m, lookback=3, drop_unclosed=True,
                            min_vol_ratio=0.0, min_rs=MIN_RS)
               for m in core.MODES}

    new = pd.concat([core.journal_rows(results[m], m) for m in core.MODES], ignore_index=True)
    old = pd.read_csv(JOURNAL) if JOURNAL.exists() else None
    before = 0 if old is None else len(old)
    journal = core.merge_journal(old, new)
    JOURNAL.parent.mkdir(exist_ok=True)
    journal.to_csv(JOURNAL, index=False)
    print(f"journal: {len(new)} signals today, total {len(journal)} (+{len(journal) - before})")

    msg = build_message(results, data_date)
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
