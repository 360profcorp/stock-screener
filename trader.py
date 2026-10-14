"""
VISAR trading bot — buys the scanner's signals at Schwab and manages them by the setup rules.

    python trader.py plan      evening, after the auto-scan: picks tomorrow's buys from the
                               journal and sends the plan by push
    python trader.py execute   next morning (~9:45 ET): checks stops, sells positions held
                               HOLD_DAYS, then buys the plan (market buy + GTC stop at Schwab)

Modes (TRADING in .github/workflows/trader.yml):
    off     nothing happens
    dry     training mode: everything runs, but orders are virtual (prices from Yahoo).
            No Schwab connection needed. Start here.
    manual  real orders, but only after you approve the plan in the app (Trading tab)
    auto    real orders without approval

All state (Schwab login, plan, positions, history) is kept encrypted in state/trader.enc.
"""
import math
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests

import core
import vault
from schwab_api import Schwab, SchwabError, refresh_age_days

ROOT = Path(__file__).parent
STATE_FILE = ROOT / vault.STATE_PATH
JOURNAL = ROOT / "journal" / "signals.csv"
NAMES = {"breakout": "Пробой", "retest": "Ретест", "vcp": "VCP", "dbottom": "Двойное дно"}


def _env(name, default, cast=float):
    v = os.getenv(name, "").strip()
    try:
        return cast(v) if v else default
    except ValueError:
        return default


MODE = os.getenv("TRADING", "off").strip().lower() or "off"
TRADE_SETUPS = [s.strip() for s in os.getenv("TRADE_SETUPS", "vcp,breakout").split(",")
                if s.strip() in core.MODES]
RISK_USD = _env("RISK_USD", 15.0)            # $ lost if the stop is hit
MAX_POSITION_USD = _env("MAX_POSITION_USD", 500.0)
MAX_POSITIONS = _env("MAX_POSITIONS", 5, int)
MAX_NEW_PER_DAY = _env("MAX_NEW_PER_DAY", 3, int)
HOLD_DAYS = _env("HOLD_DAYS", 20, int)
MAX_CHASE_PCT = _env("MAX_CHASE_PCT", 3.0)   # skip if price opened this % above signal close
ACCOUNT = os.getenv("SCHWAB_ACCOUNT", "").strip()
PASSWORD = os.getenv("STATE_PASSWORD", "")
APP_KEY = os.getenv("SCHWAB_APP_KEY", "")
APP_SECRET = os.getenv("SCHWAB_APP_SECRET", "")
TOPIC = os.getenv("NTFY_TOPIC", "").strip()
APP_URL = os.getenv("APP_URL", "https://dmitry-screener.streamlit.app")
FORCE = os.getenv("FORCE", "").strip() == "1"


# =====================================================================
# helpers
# =====================================================================
def now_ny():
    return datetime.now(core.NY)


def busdays(a, b) -> int:
    return int(np.busday_count(str(a)[:10], str(b)[:10]))


def push(title, text, tags="robot"):
    print(f"[push] {title}\n{text}")
    if not TOPIC:
        return
    try:
        requests.post(f"https://ntfy.sh/{TOPIC}", data=text.encode("utf-8"),
                      headers={"Title": title.encode("utf-8"), "Tags": tags, "Click": APP_URL},
                      timeout=20)
    except Exception as e:
        print("push failed:", e)


def mode_label(mode):
    return {"dry": "🧪 тренировка", "manual": "✋ ручное подтверждение",
            "auto": "🤖 авто", "off": "выключен"}.get(mode, mode)


# =====================================================================
# Training broker — same interface as Schwab, prices from Yahoo, no real orders
# =====================================================================
class DryBroker:
    dry = True

    def __init__(self, state, tickers):
        self.state = state
        tickers = sorted(set(tickers))
        self.prices = core.get_prices(tuple(tickers), period="3mo") if tickers else None

    def _df(self, t):
        return None if self.prices is None else core._frame_for(self.prices, t)

    def quotes(self, tickers):
        out = {}
        for t in tickers:
            df = self._df(t)
            if df is not None and len(df):
                out[t] = float(df["Close"].iloc[-1])
        return out

    def stop_hit(self, p, today):
        """(hit?, exit price) from daily lows after the entry day."""
        df = self._df(p["ticker"])
        if df is None or df.empty:
            return False, None
        after = df[(df.index.normalize() > pd.Timestamp(p["entry_date"]))
                   & (df.index.normalize() <= pd.Timestamp(today))]
        for _, bar in after.iterrows():
            if bar["Low"] <= p["stop"]:
                return True, float(min(bar["Open"], p["stop"]))      # gap below → open
        return False, None

    def buy_with_stop(self, ticker, qty, stop):
        return "dry"

    def sell_market(self, ticker, qty):
        return "dry"

    def open_sell_orders(self, ticker):
        return []

    def cancel(self, oid):
        pass


# =====================================================================
# plan (evening)
# =====================================================================
def build_plan(journal: pd.DataFrame, state: dict) -> dict | None:
    if journal is None or journal.empty:
        return None
    day = str(journal["date"].max())
    sig = journal[(journal["date"].astype(str) == day) & (journal["mode"].isin(TRADE_SETUPS))]
    held = {p["ticker"] for p in state["positions"]}
    sig = sig[~sig["ticker"].isin(held)].copy()
    sig["prio"] = sig["mode"].map({m: i for i, m in enumerate(TRADE_SETUPS)})
    sig = sig.sort_values(["prio", "rs"], ascending=[True, False]).drop_duplicates("ticker")
    room = max(0, min(MAX_NEW_PER_DAY, MAX_POSITIONS - len(state["positions"])))
    items = []
    for r in sig.head(room).itertuples():
        per_share = r.close - r.stop
        qty = math.floor(RISK_USD / per_share) if per_share > 0 else 0
        qty = min(qty, math.floor(MAX_POSITION_USD / r.close))
        items.append({"ticker": r.ticker, "mode": r.mode, "rs": int(r.rs),
                      "close": round(float(r.close), 2), "stop": round(float(r.stop), 2),
                      "level": round(float(r.level), 2), "est_qty": int(qty),
                      "est_cost": round(qty * float(r.close), 2)})
    return {"date": day, "created": now_ny().strftime("%Y-%m-%d %H:%M"), "items": items,
            "skipped_full": max(0, len(sig) - len(items)), "status": "new",
            "approved": MODE in ("auto", "dry")}


def cmd_plan():
    state = vault.load_file(STATE_FILE, PASSWORD)
    state["mode"] = MODE
    journal = pd.read_csv(JOURNAL) if JOURNAL.exists() else None
    plan = build_plan(journal, state)
    if not plan:
        print("no journal — nothing to plan")
        return
    if busdays(plan["date"], now_ny().strftime("%Y-%m-%d")) > 1:
        print(f"latest signals are from {plan['date']} — auto-scan didn't run today, no plan")
        return
    old = state.get("plan")
    if old and old.get("date") == plan["date"] and old.get("status") != "new":
        print("plan for this date was already used")
        return
    if old and old.get("date") == plan["date"] and old.get("approved") and MODE == "manual":
        print("plan for this date already approved — keeping it")
        return
    state["plan"] = plan
    vault.log(state, f"plan {plan['date']}: {[i['ticker'] for i in plan['items']]}")
    vault.save_file(STATE_FILE, state, PASSWORD)

    if not plan["items"]:
        why = ("нет свободных мест — открыто " f"{len(state['positions'])}/{MAX_POSITIONS}"
               if plan["skipped_full"] else "подходящих сигналов нет")
        push("VISAR бот: план на завтра пуст", f"{mode_label(MODE)}: {why}.")
        return
    lines = [f"{i['ticker']} ({NAMES[i['mode']]}, RS {i['rs']}): ~{i['est_qty']} шт "
             f"≈ ${i['est_cost']:.0f}, стоп {i['stop']}" for i in plan["items"]]
    tail = ("\n✋ Подтверди в приложении → вкладка «Торговля» до 9:30 утра."
            if MODE == "manual" else "\nКупит утром автоматически." if MODE == "auto"
            else "\n🧪 Тренировка: сделки будут виртуальными.")
    push(f"VISAR бот: план на завтра ({len(lines)})",
         f"Риск ${RISK_USD:.0f}/сделку, держать {HOLD_DAYS} дн.\n" + "\n".join(lines) + tail,
         tags="clipboard")


# =====================================================================
# execute (morning)
# =====================================================================
def close_position(state, p, exit_px, reason, today):
    per_share = p["entry"] - p["stop"]
    rec = {**p, "exit_date": today, "exit": round(float(exit_px), 2), "reason": reason,
           "pnl": round((float(exit_px) - p["entry"]) * p["qty"], 2),
           "r": round((float(exit_px) - p["entry"]) / per_share, 2) if per_share > 0 else None}
    state["closed"].append(rec)
    state["positions"] = [x for x in state["positions"] if x is not p]
    return rec


def run_execute(state, broker, today, events):
    dry = getattr(broker, "dry", False)
    mine = [p for p in state["positions"] if bool(p.get("dry")) == dry]

    # 1. positions closed by the stop at the broker
    if dry:
        for p in list(mine):
            hit, px = broker.stop_hit(p, today)
            if hit:
                rec = close_position(state, p, px, "stop", today)
                events.append(f"🛑 {p['ticker']}: стоп по {rec['exit']} ({rec['r']:+.1f}R, "
                              f"${rec['pnl']:+.0f})")
    else:
        held = broker.positions()
        for p in list(mine):
            if p.get("entry_est"):                         # learn the real buy price
                fill = broker.last_fill(p["ticker"], "BUY")
                if fill:
                    p["entry"], p["entry_est"] = round(fill, 2), False
            if held.get(p["ticker"], 0) < p["qty"] * 0.5:
                px = broker.last_fill(p["ticker"], "SELL") or p["stop"]
                rec = close_position(state, p, px, "stop", today)
                events.append(f"🛑 {p['ticker']}: закрыта по стопу ~{rec['exit']} "
                              f"({rec['r']:+.1f}R, ${rec['pnl']:+.0f})")

    # 2. time exit after HOLD_DAYS
    mine = [p for p in state["positions"] if bool(p.get("dry")) == dry]
    due = [p for p in mine if busdays(p["entry_date"], today) >= HOLD_DAYS]
    if due:
        q = broker.quotes([p["ticker"] for p in due])
        for p in due:
            for oid in broker.open_sell_orders(p["ticker"]):
                broker.cancel(oid)
            broker.sell_market(p["ticker"], p["qty"])
            rec = close_position(state, p, q.get(p["ticker"], p["entry"]), "time", today)
            events.append(f"⏱ {p['ticker']}: продано через {HOLD_DAYS} дн. ~{rec['exit']} "
                          f"({rec['r']:+.1f}R, ${rec['pnl']:+.0f})")

    # 3. new entries from the plan
    plan = state.get("plan")
    if not plan or plan.get("status") != "new":
        return
    age = busdays(plan["date"], today)
    if age < 1 or age > 3:
        plan["status"] = "expired" if age > 3 else plan["status"]
        return
    if MODE == "manual" and not plan.get("approved"):
        if plan.get("rejected"):
            plan["status"] = "rejected"
            return
        events.append("✋ План не подтверждён — покупок нет.")
        plan["status"] = "not_approved"
        return
    room = MAX_POSITIONS - len([p for p in state["positions"] if bool(p.get("dry")) == dry])
    items = [i for i in plan["items"] if i["ticker"] not in {p["ticker"] for p in state["positions"]}]
    q = broker.quotes([i["ticker"] for i in items])
    results = []
    for it in items:
        t, px = it["ticker"], q.get(it["ticker"])
        if room <= 0:
            results.append((t, "нет мест"))
            continue
        if not px:
            results.append((t, "нет цены"))
            continue
        if px > it["close"] * (1 + MAX_CHASE_PCT / 100):
            results.append((t, f"гэп вверх {px / it['close'] * 100 - 100:+.1f}% — не догоняем"))
            continue
        if px <= it["stop"] * 1.003:
            results.append((t, "цена уже у стопа"))
            continue
        qty = min(math.floor(RISK_USD / (px - it["stop"])), math.floor(MAX_POSITION_USD / px))
        if qty < 1:
            results.append((t, "позиция < 1 акции при заданном риске"))
            continue
        try:
            oid = broker.buy_with_stop(t, qty, it["stop"])
        except SchwabError as e:
            results.append((t, f"ошибка ордера: {str(e)[:80]}"))
            continue
        state["positions"].append({
            "ticker": t, "mode": it["mode"], "rs": it["rs"], "entry_date": today,
            "entry": round(px, 2), "entry_est": not dry, "stop": it["stop"], "qty": qty,
            "order_id": oid, "dry": dry, "signal_date": plan["date"]})
        room -= 1
        results.append((t, "ok"))
        events.append(f"🟢 {t}: куплено {qty} шт ~{px:.2f} (${qty * px:.0f}), стоп {it['stop']} "
                      f"(риск ${qty * (px - it['stop']):.0f})")
    for t, why in results:
        if why != "ok":
            events.append(f"⏭ {t}: пропуск — {why}")
    plan["status"], plan["results"] = "done", results


def market_open_today(today) -> bool:
    """True if SPY has a daily bar for today (catches market holidays)."""
    try:
        spy = core._frame_for(core.get_prices(("SPY",), period="5d"), "SPY")
        return spy is not None and len(spy) and spy.index[-1].strftime("%Y-%m-%d") == today
    except Exception:
        return True                     # if Yahoo fails, don't block — Schwab would reject anyway


def cmd_execute():
    state = vault.load_file(STATE_FILE, PASSWORD)
    state["mode"] = MODE
    now = now_ny()
    today = now.strftime("%Y-%m-%d")
    if MODE == "off":
        print("TRADING=off")
        return
    if now.weekday() >= 5:
        print("weekend")
        return
    if not FORCE and not ((now.hour, now.minute) >= (9, 35) and now.hour < 15):
        print(f"outside the trading window ({now:%H:%M} ET)")
        return
    if state.get("last_execute") == today and not FORCE:
        print("already executed today")
        return
    if not market_open_today(today):
        print("market closed today (holiday)")
        return

    events = []
    if MODE == "dry":
        tickers = [p["ticker"] for p in state["positions"] if p.get("dry")]
        if state.get("plan"):
            tickers += [i["ticker"] for i in state["plan"]["items"]]
        broker = DryBroker(state, tickers)
    else:
        age = refresh_age_days(state.get("token"))
        if age is None or age >= 7:
            push("VISAR бот: нужен вход в Schwab",
                 "Доступ к Schwab истёк (живёт 7 дней). Открой приложение → «Торговля» → "
                 "«Подключить Schwab». Сегодня бот не торгует.", tags="warning")
            vault.save_file(STATE_FILE, state, PASSWORD)
            return
        broker = Schwab(APP_KEY, APP_SECRET, state["token"], ACCOUNT)

    run_execute(state, broker, today, events)
    state["last_execute"] = today
    vault.log(state, f"execute {today}: {len(events)} events")
    vault.save_file(STATE_FILE, state, PASSWORD)

    age = refresh_age_days(state.get("token"))
    if MODE in ("manual", "auto") and age is not None and age >= 5.5:
        events.append(f"🔑 Вход в Schwab истекает через {7 - age:.1f} дн. — обнови в приложении.")
    open_n = len([p for p in state["positions"] if bool(p.get("dry")) == (MODE == "dry")])
    if events:
        push(f"VISAR бот {mode_label(MODE)}: {today}",
             "\n".join(events) + f"\nОткрыто позиций: {open_n}/{MAX_POSITIONS}")
    else:
        print("nothing to do")


def main():
    if not PASSWORD:
        print("STATE_PASSWORD is not set — add it to GitHub secrets")
        return 1
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        if cmd == "plan":
            cmd_plan()
        elif cmd == "execute":
            cmd_execute()
        else:
            print(__doc__)
            return 1
    except Exception as e:
        traceback.print_exc()
        push("VISAR бот: ошибка", f"{cmd}: {str(e)[:300]}", tags="rotating_light")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
