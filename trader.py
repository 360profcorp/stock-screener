"""
VISAR trading bot — buy-stop entries above the pivot, managed by the setup rules.

Daily cycle
    python trader.py plan      EVENING (after the auto-scan):
                               1. checks what happened today: which buy-stops filled,
                                  which positions hit their stop or were sold by time
                               2. picks tomorrow's buy-stop orders from journal/pending.csv
                               3. sends a push with today's results + tomorrow's plan
    python trader.py execute   MORNING before the open (~9:15 ET):
                               1. sells positions held HOLD_DAYS (market order at the open)
                               2. places the plan: BUY STOP-LIMIT a hair above the pivot
                                  (+ automatic GTC stop at Schwab once it fills).
                                  If price never reaches the trigger, the order expires.

Modes (TRADING in .github/workflows/trader.yml):
    off     nothing happens
    dry     training mode: identical logic, fills simulated from daily bars (Yahoo)
    manual  real orders, only after you approve the plan in the app (Trading tab)
    auto    real orders without approval

All state (Schwab login, plan, orders, positions, history) is encrypted in state/trader.enc.
"""
import math
import os
import sys
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
PENDING = ROOT / "journal" / "pending.csv"
NAMES = {"breakout": "Пробой", "retest": "Ретест", "vcp": "VCP", "dbottom": "Двойное дно"}


def _env(name, default, cast=float):
    v = os.getenv(name, "").strip()
    try:
        return cast(v) if v else default
    except ValueError:
        return default


MODE = os.getenv("TRADING", "off").strip().lower() or "off"
TRADE_SETUPS = [s.strip() for s in os.getenv("TRADE_SETUPS", "vcp,breakout").split(",")
                if s.strip() in core.PENDING_MODES]
RISK_USD = _env("RISK_USD", 15.0)            # $ lost if the stop is hit
MAX_POSITION_USD = _env("MAX_POSITION_USD", 500.0)
MAX_POSITIONS = _env("MAX_POSITIONS", 5, int)
MAX_NEW_PER_DAY = _env("MAX_NEW_PER_DAY", 3, int)
HOLD_DAYS = _env("HOLD_DAYS", 20, int)
LIMIT_PCT = _env("LIMIT_PCT", 1.0)           # buy-stop limit: max % above the trigger
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


# NYSE holidays (weekdays) — keep extending once a year
HOLIDAYS = ["2026-11-26", "2026-12-25", "2027-01-01", "2027-01-18", "2027-02-15",
            "2027-03-26", "2027-05-31", "2027-06-18", "2027-07-05", "2027-09-06",
            "2027-11-25", "2027-12-24"]


def busdays(a, b) -> int:
    """Trading days between two dates (weekends and NYSE holidays excluded)."""
    return int(np.busday_count(str(a)[:10], str(b)[:10], holidays=HOLIDAYS))


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


def sizing(trigger, limit, stop):
    """Shares so that a fill at the trigger loses RISK_USD at the stop, capped by $ size."""
    per = trigger - stop
    if per <= 0:
        return 0
    return int(min(math.floor(RISK_USD / per), math.floor(MAX_POSITION_USD / limit)))


def is_dry(x):
    return bool(x.get("dry"))


def close_position(state, p, exit_px, reason, day):
    per = p["entry"] - p["stop"]
    rec = {**p, "exit_date": day, "exit": round(float(exit_px), 2), "reason": reason,
           "pnl": round((float(exit_px) - p["entry"]) * p["qty"], 2),
           "r": round((float(exit_px) - p["entry"]) / per, 2) if per > 0 else None}
    state["closed"].append(rec)
    state["positions"] = [x for x in state["positions"] if x is not p]
    return rec


def r_txt(rec):
    return f"{rec['r']:+.1f}R, ${rec['pnl']:+.0f}" if rec.get("r") is not None else \
        f"${rec['pnl']:+.0f}"


# =====================================================================
# Training: fills from Yahoo daily bars
# =====================================================================
class DryBroker:
    dry = True

    def __init__(self, tickers):
        tickers = sorted(set(tickers))
        self.prices = core.get_prices(tuple(tickers), period="3mo") if tickers else None

    def bars(self, t, after, upto):
        """Daily bars with after < date ≤ upto."""
        if self.prices is None:
            return None
        df = core._frame_for(self.prices, t)
        if df is None or df.empty:
            return None
        d = df.index.normalize()
        return df[(d > pd.Timestamp(after)) & (d <= pd.Timestamp(upto))]

    def bar(self, t, day):
        b = self.bars(t, pd.Timestamp(day) - pd.Timedelta(days=1), day)
        return None if b is None or b.empty else b.iloc[-1]


# =====================================================================
# EVENING: reconcile today, then plan tomorrow
# =====================================================================
def reconcile_dry(state, broker, today, events):
    # 1. buy-stop orders placed for today
    for o in [o for o in state.get("orders", []) if is_dry(o) and o["date"] <= today]:
        b = broker.bar(o["ticker"], o["date"])
        state["orders"].remove(o)
        if b is None:
            events.append(f"❔ {o['ticker']}: нет данных за {o['date']} — ордер снят")
            continue
        if b["High"] < o["trigger"]:
            continue                                         # not triggered — expired
        if b["Open"] <= o["limit"]:
            fill = max(float(b["Open"]), o["trigger"])
        elif b["Low"] <= o["limit"]:
            fill = o["limit"]
        else:
            events.append(f"⏭ {o['ticker']}: гэп выше лимита {o['limit']} — не куплено")
            continue
        p = {"ticker": o["ticker"], "mode": o["mode"], "rs": o.get("rs"), "entry_date": o["date"],
             "entry": round(fill, 2), "stop": o["stop"], "qty": o["qty"], "dry": True,
             "checked": o["date"], "signal_date": o.get("signal_date")}
        state["positions"].append(p)
        events.append(f"🟢 {p['ticker']}: buy-stop исполнен ~{p['entry']} × {p['qty']} шт "
                      f"(${p['entry'] * p['qty']:.0f}), стоп {p['stop']}")
        if b["Low"] <= o["stop"]:                            # same-day stop (worst case)
            rec = close_position(state, p, o["stop"], "stop", o["date"])
            events.append(f"🛑 {p['ticker']}: выбило стопом в тот же день ({r_txt(rec)})")

    # 2. open positions: time exits sold at today's open, stops from daily lows
    for p in [p for p in state["positions"] if is_dry(p)]:
        if p.get("exiting"):
            b = broker.bar(p["ticker"], p["exiting"])
            px = float(b["Open"]) if b is not None else p["entry"]
            rec = close_position(state, p, px, "time", p["exiting"])
            events.append(f"⏱ {p['ticker']}: продано через {HOLD_DAYS} дн. ~{rec['exit']} "
                          f"({r_txt(rec)})")
            continue
        bars = broker.bars(p["ticker"], p.get("checked", p["entry_date"]), today)
        if bars is None:
            continue
        for d, b in bars.iterrows():
            if b["Low"] <= p["stop"]:
                px = min(float(b["Open"]), p["stop"])
                rec = close_position(state, p, px, "stop", d.strftime("%Y-%m-%d"))
                events.append(f"🛑 {p['ticker']}: стоп по {rec['exit']} ({r_txt(rec)})")
                break
        else:
            p["checked"] = today


def reconcile_live(state, broker, today, events):
    held = broker.positions()
    known = {p["ticker"] for p in state["positions"] if not is_dry(p)}
    # 1. which buy-stops filled today
    for o in [o for o in state.get("orders", []) if not is_dry(o) and o["date"] <= today]:
        state["orders"].remove(o)
        qty = int(held.get(o["ticker"], 0))
        if qty >= 1 and o["ticker"] not in known:
            fill = broker.last_fill(o["ticker"], "BUY") or o["trigger"]
            p = {"ticker": o["ticker"], "mode": o["mode"], "rs": o.get("rs"),
                 "entry_date": o["date"], "entry": round(fill, 2), "stop": o["stop"],
                 "qty": qty, "dry": False, "order_id": o.get("order_id"),
                 "signal_date": o.get("signal_date")}
            state["positions"].append(p)
            events.append(f"🟢 {p['ticker']}: buy-stop исполнен ~{p['entry']} × {qty} шт, "
                          f"стоп {p['stop']} стоит у Schwab")
    # 2. positions that are gone: stopped out or sold by time
    for p in [p for p in state["positions"] if not is_dry(p)]:
        if held.get(p["ticker"], 0) < p["qty"] * 0.5:
            px = broker.last_fill(p["ticker"], "SELL") or p["stop"]
            reason = "time" if p.get("exiting") else "stop"
            rec = close_position(state, p, px, reason, today)
            icon = "⏱" if reason == "time" else "🛑"
            events.append(f"{icon} {p['ticker']}: закрыта ~{rec['exit']} ({r_txt(rec)})")


def build_plan(pending: pd.DataFrame, state: dict, today: str) -> dict | None:
    if pending is None or pending.empty:
        return None
    day = str(pending["date"].max())
    p = pending[(pending["date"].astype(str) == day) & pending["mode"].isin(TRADE_SETUPS)]
    busy = {x["ticker"] for x in state["positions"]}
    p = p[~p["ticker"].isin(busy)].copy()
    p["prio"] = p["mode"].map({m: i for i, m in enumerate(TRADE_SETUPS)})
    p = p.sort_values(["prio", "rs"], ascending=[True, False]).drop_duplicates("ticker")
    room = max(0, min(MAX_NEW_PER_DAY, MAX_POSITIONS - len(state["positions"])))
    items = []
    for r in p.itertuples():
        if len(items) >= room:
            break
        trig = float(r.trigger)
        lim = round(trig * (1 + LIMIT_PCT / 100), 2)
        qty = sizing(trig, lim, float(r.stop))
        if qty < 1:
            continue
        items.append({"ticker": r.ticker, "mode": r.mode, "rs": int(r.rs),
                      "close": round(float(r.close), 2), "trigger": trig, "limit": lim,
                      "stop": round(float(r.stop), 2), "est_qty": qty,
                      "est_cost": round(qty * trig, 2), "dist_pct": float(r.dist_pct)})
    return {"date": day, "for": str(np.busday_offset(day, 1, roll="forward", holidays=HOLIDAYS)),
            "created": now_ny().strftime("%Y-%m-%d %H:%M"), "items": items,
            "skipped_full": max(0, len(p) - len(items)), "status": "new",
            "approved": MODE in ("auto", "dry")}


def cmd_plan():
    state = vault.load_file(STATE_FILE, PASSWORD)
    state.setdefault("orders", [])
    state["mode"] = MODE
    today = now_ny().strftime("%Y-%m-%d")
    events = []

    # ---- 1. what happened today
    if MODE == "dry":
        tick = [o["ticker"] for o in state["orders"] if is_dry(o)] + \
               [p["ticker"] for p in state["positions"] if is_dry(p)]
        if tick:
            reconcile_dry(state, DryBroker(tick), today, events)
    elif MODE in ("manual", "auto") and (refresh_age_days(state.get("token")) or 99) < 7:
        try:
            reconcile_live(state, Schwab(APP_KEY, APP_SECRET, state["token"], ACCOUNT),
                           today, events)
        except SchwabError as e:
            events.append(f"⚠️ Schwab: {str(e)[:120]}")

    # ---- 2. tomorrow's plan
    pending = pd.read_csv(PENDING) if PENDING.exists() else None
    plan = build_plan(pending, state, today)
    fresh = plan is not None and busdays(plan["date"], today) == 0     # today's candidates only
    if fresh:
        old = state.get("plan")
        if not (old and old.get("date") == plan["date"] and old.get("approved")
                and MODE == "manual"):
            state["plan"] = plan
    vault.log(state, f"plan {today}: events {len(events)}, "
                     f"items {[i['ticker'] for i in plan['items']] if fresh else '—'}")
    vault.save_file(STATE_FILE, state, PASSWORD)

    # ---- 3. push
    lines = []
    if events:
        lines += ["Сегодня:"] + events + [""]
    plan = state.get("plan") if fresh and state.get("plan", {}).get("status") == "new" else None
    if not plan:
        lines.append("Кандидатов на завтра нет." if pending is not None and pending.empty
                     else "Плана на завтра нет — автоскан сегодня не обновил кандидатов.")
    elif not plan["items"]:
        lines.append("План на завтра пуст: " + (f"нет мест ({len(state['positions'])}/"
                                                 f"{MAX_POSITIONS})" if plan["skipped_full"]
                                                 else "подходящих сетапов нет") + ".")
    else:
        lines.append(f"Завтра buy-stop (риск ${RISK_USD:.0f}, держать {HOLD_DAYS} дн.):")
        lines += [f"{i['ticker']} ({NAMES[i['mode']]}, RS {i['rs']}): купить выше {i['trigger']} "
                  f"(лимит {i['limit']}), стоп {i['stop']}, ~{i['est_qty']} шт"
                  for i in plan["items"]]
        lines.append("✋ Подтверди в приложении → «Торговля» до 9:15 утра." if MODE == "manual"
                     else "🧪 Тренировка: ордера виртуальные." if MODE == "dry"
                     else "Ордера будут выставлены утром до открытия.")
    open_n = len(state["positions"])
    lines.append(f"Открыто позиций: {open_n}/{MAX_POSITIONS}")
    push(f"VISAR бот {mode_label(MODE)}: {today}", "\n".join(lines), tags="clipboard")


# =====================================================================
# MORNING: time exits + place buy-stops
# =====================================================================
def run_execute(state, broker, today, events):
    dry = getattr(broker, "dry", False)
    # 1. sell positions held HOLD_DAYS (at the open)
    for p in [p for p in state["positions"] if is_dry(p) == dry and not p.get("exiting")]:
        if busdays(p["entry_date"], today) >= HOLD_DAYS:
            if not dry:
                for oid in broker.open_sell_orders(p["ticker"]):
                    broker.cancel(oid)
                broker.sell_market(p["ticker"], p["qty"])
            p["exiting"] = today
            events.append(f"⏱ {p['ticker']}: {HOLD_DAYS} дн. прошло — продажа на открытии")

    # 2. buy-stop orders from the plan
    plan = state.get("plan")
    if not plan or plan.get("status") != "new":
        return
    if busdays(plan["date"], today) != 1:
        plan["status"] = "expired"
        return
    if MODE == "manual" and not plan.get("approved"):
        plan["status"] = "rejected" if plan.get("rejected") else "not_approved"
        if not plan.get("rejected"):
            events.append("✋ План не подтверждён — ордеров нет.")
        return
    busy = {p["ticker"] for p in state["positions"]} | {o["ticker"] for o in state["orders"]}
    room = MAX_POSITIONS - len(state["positions"]) - len(state["orders"])
    quotes = {} if dry else broker.quotes([i["ticker"] for i in plan["items"]])
    results = []
    for it in plan["items"]:
        t = it["ticker"]
        if t in busy:
            continue
        if room <= 0:
            results.append((t, "нет мест"))
            continue
        q = quotes.get(t)
        if q and q > it["limit"]:
            results.append((t, f"премаркет {q:.2f} уже выше лимита — пропуск"))
            continue
        qty = sizing(it["trigger"], it["limit"], it["stop"])
        if qty < 1:
            results.append((t, "размер < 1 акции"))
            continue
        oid = "dry"
        if not dry:
            try:
                oid = broker.buy_stop_with_stop(t, qty, it["trigger"], it["limit"], it["stop"])
            except SchwabError as e:
                results.append((t, f"ошибка ордера: {str(e)[:80]}"))
                continue
        state["orders"].append({"ticker": t, "mode": it["mode"], "rs": it["rs"], "date": today,
                                "trigger": it["trigger"], "limit": it["limit"],
                                "stop": it["stop"], "qty": qty, "order_id": oid, "dry": dry,
                                "signal_date": plan["date"]})
        room -= 1
        results.append((t, "ok"))
        events.append(f"📌 {t}: buy-stop {qty} шт выше {it['trigger']} (лимит {it['limit']}), "
                      f"стоп {it['stop']}")
    for t, why in results:
        if why != "ok":
            events.append(f"⏭ {t}: {why}")
    plan["status"], plan["results"] = "done", results


def market_open_today(today) -> bool:
    return today not in HOLIDAYS


def cmd_execute():
    state = vault.load_file(STATE_FILE, PASSWORD)
    state.setdefault("orders", [])
    state["mode"] = MODE
    now = now_ny()
    today = now.strftime("%Y-%m-%d")
    if MODE == "off":
        print("TRADING=off")
        return
    if now.weekday() >= 5:
        print("weekend")
        return
    if not FORCE and not ((8, 0) <= (now.hour, now.minute) < (9, 29)):
        print(f"outside the pre-market window ({now:%H:%M} ET)")
        return
    if state.get("last_execute") == today and not FORCE:
        print("already executed today")
        return
    if not market_open_today(today):
        print("market holiday")
        return

    events = []
    if MODE == "dry":
        broker = DryBroker([])
        broker.dry = True
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
    if events:
        push(f"VISAR бот {mode_label(MODE)}: утро {today}", "\n".join(events))
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
