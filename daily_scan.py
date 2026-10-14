"""
VISAR daily auto-scan — runs on GitHub Actions every weekday after the US close.
  1. scans the S&P 500 for all three setups (breakout, retest, VCP)
  2. appends the signals to journal/signals.csv (the app's "Journal" tab reads it)
  3. sends a push notification to the phone via ntfy (free app, no account)

Settings come from environment variables (GitHub → Settings → Secrets and variables → Actions):
  NTFY_TOPIC  — your private ntfy topic name (secret). Without it the push is skipped.
  MIN_RS      — RS filter for the auto-scan (default 70)
  APP_URL     — link opened when you tap the notification
"""
import os
import sys
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


def run_scans():
    universe = core.get_sp500()
    prices = core.get_prices(tuple(universe["ticker"]))
    results = {}
    for mode in core.MODES:
        results[mode] = core.scan(prices, universe, mode, lookback=3, drop_unclosed=True,
                                  min_vol_ratio=0.0, min_rs=MIN_RS)
    return results


def build_message(results, date_str):
    lines = []
    for mode in ("vcp", "retest", "breakout"):          # most selective first
        res = results[mode]
        if res.empty:
            lines.append(f"{NAMES[mode]}: 0")
            continue
        top = ", ".join(f"{r.ticker} ({r.rs})" for r in res.head(6).itertuples())
        more = f" +{len(res) - 6}" if len(res) > 6 else ""
        lines.append(f"{NAMES[mode]}: {len(res)} — {top}{more}")
    return f"Скан {date_str}, RS ≥ {MIN_RS}\n" + "\n".join(lines)


def send_push(message, total):
    if not TOPIC:
        print("NTFY_TOPIC not set — push skipped")
        return
    r = requests.post(
        f"https://ntfy.sh/{TOPIC}",
        data=message.encode("utf-8"),
        headers={"Title": f"VISAR Screener: {total} signals",
                 "Tags": "chart_with_upwards_trend",
                 "Click": APP_URL},
        timeout=20,
    )
    print("push:", r.status_code)


def main():
    now = datetime.now(core.NY)
    if now.weekday() >= 5:
        print("weekend — nothing to do")
        return 0
    results = run_scans()

    dates = [r["date"].iloc[0] for r in results.values() if not r.empty]
    if dates and max(dates) != now.strftime("%Y-%m-%d"):
        print(f"latest candle is {max(dates)}, not today — market holiday? Skipping.")
        return 0

    new = pd.concat([core.journal_rows(results[m], m) for m in core.MODES], ignore_index=True)
    old = pd.read_csv(JOURNAL) if JOURNAL.exists() else None
    journal = core.merge_journal(old, new)
    JOURNAL.parent.mkdir(exist_ok=True)
    journal.to_csv(JOURNAL, index=False)
    print(f"journal: +{len(new)} signals, total {len(journal)}")

    msg = build_message(results, now.strftime("%d.%m.%Y"))
    print(msg)
    send_push(msg, len(new))
    return 0


if __name__ == "__main__":
    sys.exit(main())
