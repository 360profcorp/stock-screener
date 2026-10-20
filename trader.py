"""
VISAR trading bot. Entries chosen by the backtest (2 years, S&P 500, RS ≥ 85, stop −3%, 20 days):
  • Breakout       — bought the SAME day, ~30 min before the close, if the breakout is holding
                     (at-close entry: 0.25R vs 0.19R at the next open).
  • VCP, retest    — signal from the evening scan, bought the NEXT morning at the open
                     (at-open entry: VCP 0.27R, retest 0.18R).
Every buy gets a GTC stop at Schwab right after the fill; exit by the stop or after HOLD_DAYS.

Daily cycle (New York time)
    python trader.py preclose  ~15:30  scans breakouts on today's live candles and buys
                                       those still above the level (market order + stop)
    python trader.py plan      ~20:05  1. checks what happened today (fills, stops, time exits)
                                       2. tomorrow's plan from journal/signals.csv (VCP, retest;
                                          breakouts too if the pre-close run didn't happen)
                                       3. push with results + plan
    python trader.py execute   ~9:15   1. sells positions held HOLD_DAYS (at the open)
                                       2. places the plan: market buy at the open + GTC stop

Modes (TRADING in .github/workflows/trader.yml):
    off     nothing happens
    dry     training: same logic, fills simulated from Yahoo prices
    manual  real orders; the morning plan needs approval in the app (Trading tab).
            Breakouts can't wait for approval (30 min to the close) — they're bought only
            if "buy breakouts without approval" is switched on in the app, otherwise you get
            a push with the list.
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
SIGNALS = ROOT / "journal" / "signals.csv"
NAMES = {"breakout": "Пробой", "retest": "Ретест", "vcp": "VCP", "dbottom": "Двойное дно"}
OPEN_MODES = ("vcp", "retest")            # bought at the next open
CLOSE_MODES = ("breakout",)               # bought before today's close


def _env(name, default, cast=float):
    v = os.getenv(name, "").strip()
    try:
        return cast(v) if v else default
    except ValueError:
        return default


MODE = os.getenv("TRADING", "off").strip().lower() or "off"
TRADE_SETUPS = [s.strip() for s in os.getenv("TRADE_SETUPS", "breakout,vcp,retest").split(",")
                if s.strip() in OPEN_MODES + CLOSE_MODES]
RISK_USD = _env("RISK_USD", 15.0)            # $ lost if the stop is hit
MAX_POSITION_USD = _env("MAX_POSITION_USD", 500.0)
MAX_POSITIONS = _env("MAX_POSITIONS", 5, int)
MAX_NEW_PER_DAY = _env("MAX_NEW_PER_DAY", 3, int)
HOLD_DAYS = _env("HOLD_DAYS", 20, int)
# breakout scan before the close — same rules as the auto-scan / backtest
MIN_RS = _env("MIN_RS", 85, int)
STOP_BUF = _env("STOP_BUF", 3.0)
MAX_RISK = _env("MAX_RISK", 0.0)
LOOKBACK = _env("LOOKBACK", 3, int)
EARNINGS_DAYS = _env("EARNINGS_DAYS", 5, int)
MARKET_FILTER = os.getenv("MARKET_FILTER", "ma50").strip().lower() or "ma50"
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


def sizing(price, stop):
    """Shares so that the stop loses about RISK_USD, capped by MAX_POSITION_USD."""
    per = price - stop
    if per <= 0 or price <= 0:
        return 0
    return int(min(math.floor(RISK_USD / per), math.floor(MAX_POSITION_USD / price)))


def is_dry(x):
    return bool(x.get("dry"))


def new_today(state, today):
    return (sum(p.get("entry_date") == today for p in state["positions"])
            + sum(o.get("date") == today for o in state["orders"]))


def room_today(state, today):
    return max(0, min(MAX_NEW_PER_DAY - new_today(state, today),
                      MAX_POSITIONS - len(state["positions"]) - len(state["orders"])))


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


ORDER_DATA_WAIT_DAYS = 3                 # a dry order waits this long for ITS session's bar
LIVE_EXECUTE_WINDOW = ((8, 0), (9, 29))  # real orders: only before the open
DRY_EXECUTE_WINDOW = ((6, 0), (16, 0))   # paper: a plan committed before the open may be
#                                          processed late the same day (GitHub cron delays);
#                                          it still fills at THAT session's open, never later
OPEN_HM = (9, 30)


def record_run(state, cmd, result, reason="", **extra):
    """Facts about the last attempt of each command (shown in the app's status block).
    result: ok | skipped | error. The last successful run is kept separately."""
    now = now_ny()
    rec = {"at": now.strftime("%Y-%m-%d %H:%M"), "result": result, "reason": reason, **extra}
    runs = state.setdefault("runs", {})
    runs[cmd] = rec
    if result == "ok":
        state.setdefault("runs_ok", {})[cmd] = rec


def load_state():
    state = vault.load_file(STATE_FILE, PASSWORD)
    state.setdefault("orders", [])
    state.setdefault("positions", [])
    state.setdefault("closed", [])
    # orders/plans from the old buy-stop version are dropped
    old = [o for o in state["orders"] if o.get("kind") != "open"]
    if old:
        state["orders"] = [o for o in state["orders"] if o.get("kind") == "open"]
        vault.log(state, f"dropped {len(old)} old buy-stop order(s)")
    if state.get("plan") and state["plan"].get("kind") != "open":
        state["plan"] = None
    state["mode"] = MODE
    return state


def schwab_or_none(state):
    """Live broker, or None (+ push) when the weekly Schwab login has expired."""
    age = refresh_age_days(state.get("token"))
    if age is None or age >= 7:
        push("VISAR бот: нужен вход в Schwab",
             "Доступ к Schwab истёк (живёт 7 дней). Открой приложение → «Торговля» → "
             "«Подключить Schwab». Пока бот не торгует.", tags="warning")
        return None
    return Schwab(APP_KEY, APP_SECRET, state["token"], ACCOUNT)


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

    def intraday(self, t, day):
        """Minute bars of `day` (New York time) or None. Yahoo keeps ~7 days of 1m data."""
        try:
            import yfinance as yf
            df = yf.download(t, period="7d", interval="1m", auto_adjust=False,
                             progress=False)
            if df is None or df.empty:
                return None
            if isinstance(df.columns, pd.MultiIndex):
                df = df.xs(t, axis=1, level=1) if t in df.columns.get_level_values(1) else \
                    df.droplevel(1, axis=1)
            idx = df.index.tz_convert(core.NY) if df.index.tz is not None else df.index
            df = df.set_axis(idx)
            return df[idx.strftime("%Y-%m-%d") == str(day)[:10]].dropna(subset=["Low"])
        except Exception as e:
            print("intraday unavailable:", e)
            return None


# =====================================================================
# EVENING: reconcile today, then plan tomorrow
# =====================================================================
def reconcile_dry(state, broker, today, events):
    # 1. morning buys at the open
    for o in [o for o in state["orders"] if is_dry(o) and o["date"] <= today]:
        # the fill belongs to the order's own session (o["date"]): only that bar is loaded,
        # the purchase is never moved to a later session
        b = broker.bar(o["ticker"], o["date"])
        if b is None:                    # no open bar yet: never invent a fill, wait for data
            if busdays(o["date"], today) < ORDER_DATA_WAIT_DAYS:
                o["waiting_data"] = True
                events.append(f"❔ {o['ticker']}: нет котировки за {o['date']} — ждём данные")
            else:
                state["orders"].remove(o)
                events.append(f"❔ {o['ticker']}: нет котировки за {o['date']} "
                              f"{ORDER_DATA_WAIT_DAYS} дн. — покупка не засчитана")
            continue
        state["orders"].remove(o)
        fill = float(b["Open"])
        if fill <= o["stop"]:
            events.append(f"⏭ {o['ticker']}: открылась {fill:.2f} — ниже стопа, не куплено")
            continue
        qty = sizing(fill, o["stop"])               # live sizes by the pre-market quote ≈ open
        if qty < 1:
            events.append(f"⏭ {o['ticker']}: открылась {fill:.2f} — позиция < 1 акции")
            continue
        p = {"ticker": o["ticker"], "mode": o["mode"], "rs": o.get("rs"), "entry_date": o["date"],
             "entry": round(fill, 2), "stop": o["stop"], "qty": qty, "dry": True,
             "checked": o["date"], "signal_date": o.get("signal_date"), "how": "open",
             "committed_at": o.get("committed_at"), "late_run": bool(o.get("late_run"))}
        state["positions"].append(p)
        events.append(f"🟢 {p['ticker']} ({NAMES[p['mode']]}): куплено на открытии "
                      f"~{p['entry']} × {qty} шт (${p['entry'] * qty:.0f}), стоп {p['stop']}")
        if b["Low"] <= o["stop"]:                            # stopped the same day
            rec = close_position(state, p, o["stop"], "stop", o["date"])
            events.append(f"🛑 {p['ticker']}: выбило стопом в тот же день ({r_txt(rec)})")

    # 2. breakouts bought before the close: the entry day's daily low may have happened BEFORE
    #    the purchase, so it is never used. Only minute bars after the entry time count; without
    #    them the entry-day stop stays unverified (flag kept on the position and the trade).
    for p in [p for p in state["positions"] if is_dry(p) and p.get("how") == "close"
              and not p.get("entry_day_stop")]:
        check_entry_day_stop(state, broker, p, events)

    # 3. open positions: time exits sold at today's open, stops from daily lows
    gaps = []                            # positions whose latest session bar is missing
    for p in [p for p in state["positions"] if is_dry(p)]:
        upto = today
        if p.get("exiting"):             # sold at the open of the exit day: stops before it first
            upto = str(np.busday_offset(p["exiting"], -1, roll="backward", holidays=HOLIDAYS))
        bars = broker.bars(p["ticker"], p.get("checked", p["entry_date"]), upto)
        stopped = False
        if bars is not None:
            for d, b in bars.iterrows():
                if b["Low"] <= p["stop"]:
                    px = min(float(b["Open"]), p["stop"])
                    rec = close_position(state, p, px, "stop", d.strftime("%Y-%m-%d"))
                    events.append(f"🛑 {p['ticker']}: стоп по {rec['exit']} ({r_txt(rec)})")
                    stopped = True
                    break
            else:
                if len(bars):
                    p["checked"] = bars.index[-1].strftime("%Y-%m-%d")
        if not stopped:
            need = upto if p.get("exiting") else last_session(today)
            if need > p.get("checked", p["entry_date"]):     # bars for `need` not received
                gaps.append(p["ticker"])
        if stopped or not p.get("exiting"):
            continue
        b = broker.bar(p["ticker"], p["exiting"])
        if b is None:                    # never invent an exit price: retry at the next check
            events.append(f"❔ {p['ticker']}: нет котировки открытия за {p['exiting']} — "
                          "выход по времени будет засчитан, когда появятся данные")
            continue
        rec = close_position(state, p, float(b["Open"]), "time", p["exiting"])
        events.append(f"⏱ {p['ticker']}: продано через {HOLD_DAYS} дн. ~{rec['exit']} "
                      f"({r_txt(rec)})")
    if gaps:
        events.append(f"⚠️ Нет котировок за {last_session(today)} для проверки позиций: "
                      f"{', '.join(gaps)} — стопы проверятся при следующем запуске")
    return gaps


def last_session(day) -> str:
    """Latest NYSE session on or before `day`."""
    return str(np.busday_offset(str(day)[:10], 0, roll="backward", holidays=HOLIDAYS))


def check_entry_day_stop(state, broker, p, events):
    """Stop between the pre-close purchase and the close of the entry day (paper mode)."""
    t0 = p.get("entry_time")
    bars = broker.intraday(p["ticker"], p["entry_date"]) if t0 and hasattr(broker, "intraday") \
        else None
    if bars is None or bars.empty:
        p["entry_day_stop"] = "unverified"       # no minute data: explicit limitation
        return
    hm = bars.index.strftime("%H:%M")
    after = bars[hm > t0]
    if after.empty or hm.max() < "15:59":
        p["entry_day_stop"] = "unverified"       # minute data incomplete
        return
    hit = after[after["Low"] <= p["stop"]]
    if hit.empty:
        p["entry_day_stop"] = "intraday_ok"
        return
    first = hit.iloc[0]
    px = min(float(first["Open"]), p["stop"])
    p["entry_day_stop"] = "intraday_hit"
    rec = close_position(state, p, px, "stop", p["entry_date"])
    events.append(f"🛑 {p['ticker']}: стоп в день покупки после {t0} "
                  f"({hit.index[0]:%H:%M}) по {rec['exit']} ({r_txt(rec)})")


def reconcile_live(state, broker, today, events):
    held = broker.positions()
    # 1. breakouts bought before the close: confirm the fill
    for p in [p for p in state["positions"] if not is_dry(p) and p.get("pending_fill")]:
        qty = int(held.get(p["ticker"], 0))
        if qty >= 1:
            p["entry"] = round(broker.last_fill(p["ticker"], "BUY") or p["entry"], 2)
            p["qty"] = qty
            p.pop("pending_fill")
        else:
            state["positions"].remove(p)
            events.append(f"⏭ {p['ticker']}: покупка перед закрытием не исполнилась")
    # 2. morning buys at the open
    known = {p["ticker"] for p in state["positions"] if not is_dry(p)}
    for o in [o for o in state["orders"] if not is_dry(o) and o["date"] <= today]:
        state["orders"].remove(o)
        qty = int(held.get(o["ticker"], 0))
        if qty >= 1 and o["ticker"] not in known:
            fill = broker.last_fill(o["ticker"], "BUY") or o.get("est", 0)
            p = {"ticker": o["ticker"], "mode": o["mode"], "rs": o.get("rs"),
                 "entry_date": o["date"], "entry": round(fill, 2), "stop": o["stop"],
                 "qty": qty, "dry": False, "order_id": o.get("order_id"),
                 "signal_date": o.get("signal_date"), "how": "open"}
            state["positions"].append(p)
            known.add(p["ticker"])
            events.append(f"🟢 {p['ticker']} ({NAMES[p['mode']]}): куплено ~{p['entry']} × "
                          f"{qty} шт, стоп {p['stop']} стоит у Schwab")
        elif qty < 1:
            events.append(f"⏭ {o['ticker']}: утренняя покупка не исполнилась")
    # 3. positions that are gone: stopped out or sold by time
    for p in [p for p in state["positions"] if not is_dry(p)]:
        if held.get(p["ticker"], 0) < p["qty"] * 0.5:
            px = broker.last_fill(p["ticker"], "SELL") or p["stop"]
            reason = "time" if p.get("exiting") else "stop"
            rec = close_position(state, p, px, reason, today)
            icon = "⏱" if reason == "time" else "🛑"
            events.append(f"{icon} {p['ticker']}: закрыта ~{rec['exit']} ({r_txt(rec)})")


def build_plan(signals: pd.DataFrame, state: dict, today: str) -> dict | None:
    """Tomorrow-at-the-open plan from today's auto-scan signals."""
    if signals is None or signals.empty:
        return None
    day = str(signals["date"].astype(str).max())
    modes = [m for m in TRADE_SETUPS if m in OPEN_MODES]
    fallback = "breakout" in TRADE_SETUPS and state.get("last_preclose") != day
    if fallback:                       # the pre-close run didn't happen → breakouts at the open
        modes.append("breakout")
    s = signals[(signals["date"].astype(str) == day) & signals["mode"].isin(modes)]
    n_signals = int(s["ticker"].nunique())
    busy = {x["ticker"] for x in state["positions"]} | {o["ticker"] for o in state["orders"]}
    n_busy = int(s[s["ticker"].isin(busy)]["ticker"].nunique())
    s = s[~s["ticker"].isin(busy)].copy()
    s["prio"] = s["mode"].map({m: i for i, m in enumerate(modes)})
    s = s.sort_values(["prio", "rs"], ascending=[True, False]).drop_duplicates("ticker")
    room = max(0, min(MAX_NEW_PER_DAY, MAX_POSITIONS - len(state["positions"])))
    items, too_small = [], 0
    for r in s.itertuples():
        if len(items) >= room:
            break
        close, stop = float(r.close), round(float(r.stop), 2)
        qty = sizing(close, stop)
        if qty < 1:
            too_small += 1
            continue
        items.append({"ticker": r.ticker, "mode": r.mode, "rs": int(r.rs), "close": round(close, 2),
                      "level": round(float(r.level), 2), "stop": stop, "est_qty": qty,
                      "est_cost": round(qty * close, 2)})
    return {"kind": "open", "date": day,
            "for": str(np.busday_offset(day, 1, roll="forward", holidays=HOLIDAYS)),
            "created": now_ny().strftime("%Y-%m-%d %H:%M"), "items": items,
            "skipped_full": max(0, len(s) - len(items)), "status": "new",
            "approved": MODE in ("auto", "dry"), "fallback_breakouts": fallback,
            "signals": n_signals, "already_held": n_busy, "too_small": too_small,
            "room": room}


def cmd_plan():
    state = load_state()
    today = now_ny().strftime("%Y-%m-%d")
    events = []

    # ---- 1. what happened today
    gaps = []
    if MODE == "dry":
        tick = [o["ticker"] for o in state["orders"] if is_dry(o)] + \
               [p["ticker"] for p in state["positions"] if is_dry(p)]
        if tick:
            gaps = reconcile_dry(state, DryBroker(tick), today, events)
    elif MODE in ("manual", "auto") and (refresh_age_days(state.get("token")) or 99) < 7:
        try:
            reconcile_live(state, Schwab(APP_KEY, APP_SECRET, state["token"], ACCOUNT),
                           today, events)
        except SchwabError as e:
            events.append(f"⚠️ Schwab: {str(e)[:120]}")

    # ---- 2. tomorrow's plan
    signals = pd.read_csv(SIGNALS) if SIGNALS.exists() else None
    plan = build_plan(signals, state, today) if MODE != "off" else None
    fresh = plan is not None and busdays(plan["date"], today) == 0     # today's signals only
    if fresh:
        old = state.get("plan")
        if not (old and old.get("date") == plan["date"] and old.get("approved")
                and MODE == "manual"):
            state["plan"] = plan
    vault.log(state, f"plan {today}: events {len(events)}, "
                     f"items {[i['ticker'] for i in plan['items']] if fresh else '—'}")
    sig_day = str(signals["date"].astype(str).max()) if signals is not None and len(signals) \
        else None
    why = [] if fresh else [f"автоскан не записал сигналов за {today} "
                            f"(последние сигналы: {sig_day or 'нет'})"]
    if gaps:
        why.append(f"нет котировок за {last_session(today)} для проверки позиций: "
                   f"{', '.join(gaps)}")
    record_run(state, "plan", "ok", "; ".join(why),
               data_date=sig_day, events=len(events),
               plan_items=len(plan["items"]) if fresh else 0, quote_gaps=gaps)
    vault.save_file(STATE_FILE, state, PASSWORD)

    # ---- 3. push
    lines = []
    if events:
        lines += ["Сегодня:"] + events + [""]
    plan = state.get("plan") if fresh and state.get("plan", {}).get("status") == "new" else None
    if not plan:
        lines.append("Плана на завтра нет — автоскан сегодня не записал сигналов.")
    elif not plan["items"]:
        lines.append("Покупок на завтра нет: " + (f"нет мест ({len(state['positions'])}/"
                                                   f"{MAX_POSITIONS})" if plan["skipped_full"]
                                                   else "сигналов VCP / ретеста нет") + ".")
    else:
        lines.append(f"Завтра на открытии (риск ~${RISK_USD:.0f}, держать {HOLD_DAYS} дн.):")
        lines += [f"{i['ticker']} ({NAMES[i['mode']]}, RS {i['rs']}): ~{i['est_qty']} шт "
                  f"по ~{i['close']}, стоп {i['stop']}" for i in plan["items"]]
        if plan.get("fallback_breakouts"):
            lines.append("(пробои тоже утром — сегодня перед закрытием бот не сработал)")
        lines.append("✋ Подтверди в приложении → «Торговля» до 9:15 утра." if MODE == "manual"
                     else "🧪 Тренировка: сделки виртуальные." if MODE == "dry"
                     else "Покупка по рынку на открытии, стоп сразу у Schwab.")
    lines.append(f"Открыто позиций: {len(state['positions'])}/{MAX_POSITIONS}")
    push(f"VISAR бот {mode_label(MODE)}: {today}", "\n".join(lines), tags="clipboard")


# =====================================================================
# MORNING: time exits + buys at the open
# =====================================================================
def committed_before_open(plan) -> bool:
    """The plan (and, in paper mode, its auto-approval) was fixed before the open of the
    session it is for — so a late run may still model fills at that open."""
    created = str(plan.get("created") or "")
    return bool(created) and created < f"{plan.get('for')} {OPEN_HM[0]:02d}:{OPEN_HM[1]:02d}"


def run_execute(state, broker, today, events, now=None):
    dry = getattr(broker, "dry", False)
    now = now or now_ny()
    late = (now.hour, now.minute) >= OPEN_HM
    # 1. sell positions held HOLD_DAYS (at the open)
    for p in [p for p in state["positions"] if is_dry(p) == dry and not p.get("exiting")]:
        if busdays(p["entry_date"], today) >= HOLD_DAYS:
            if not dry:
                for oid in broker.open_sell_orders(p["ticker"]):
                    broker.cancel(oid)
                broker.sell_market(p["ticker"], p["qty"])
            p["exiting"] = today
            events.append(f"⏱ {p['ticker']}: {HOLD_DAYS} дн. прошло — продажа на открытии")

    # 2. buys at the open from the plan
    plan = state.get("plan")
    if not plan or plan.get("status") != "new":
        return
    if busdays(plan["date"], today) != 1:
        plan["status"] = "expired"
        return
    if late and not (dry and committed_before_open(plan)):
        # a decision made after the open is never given the past opening price
        plan["status"] = "expired"
        events.append("⏭ План не исполнен: запуск после открытия, а план не был "
                      "зафиксирован до открытия.")
        return
    if MODE == "manual" and not plan.get("approved"):
        plan["status"] = "rejected" if plan.get("rejected") else "not_approved"
        if not plan.get("rejected"):
            events.append("✋ План не подтверждён — покупок нет.")
        return
    busy = {p["ticker"] for p in state["positions"]} | {o["ticker"] for o in state["orders"]}
    room = room_today(state, today)
    quotes = {} if dry else broker.quotes([i["ticker"] for i in plan["items"]])
    results = []
    for it in plan["items"]:
        t = it["ticker"]
        if t in busy:
            continue
        if room <= 0:
            results.append((t, "нет мест"))
            continue
        est = quotes.get(t) or it["close"]
        if est <= it["stop"]:
            results.append((t, f"премаркет {est:.2f} ниже стопа — пропуск"))
            continue
        qty = sizing(est, it["stop"])
        if qty < 1:
            results.append((t, "размер < 1 акции"))
            continue
        oid = "dry"
        if not dry:
            try:
                oid = broker.buy_with_stop(t, qty, it["stop"])
            except SchwabError as e:
                results.append((t, f"ошибка ордера: {str(e)[:80]}"))
                continue
        state["orders"].append({"kind": "open", "ticker": t, "mode": it["mode"], "rs": it["rs"],
                                "date": today, "est": round(est, 2), "stop": it["stop"],
                                "qty": qty, "order_id": oid, "dry": dry,
                                "signal_date": plan["date"], "fill_session": today,
                                "committed_at": plan.get("created"),
                                "run_at": now.strftime("%Y-%m-%d %H:%M"), "late_run": late})
        room -= 1
        results.append((t, "ok"))
        events.append(f"📌 {t} ({NAMES[it['mode']]}): покупка {qty} шт на открытии "
                      f"(~{est:.2f}), стоп {it['stop']}"
                      + (f" — запуск опоздал ({now:%H:%M} ET), заявка из плана от "
                         f"{plan.get('created')}, исполнение по открытию {today}" if late else ""))
    for t, why in results:
        if why != "ok":
            events.append(f"⏭ {t}: {why}")
    plan["status"], plan["results"] = "done", results


def check_day(now, state, key, window, label, cmd=None):
    """Common guards: mode, weekend, holiday, time window, already ran today.
    A skip that leaves today's work undone (outside the window with no successful run today)
    is recorded in the state with its reason, so the app can show it; benign skips are not."""
    today = now.strftime("%Y-%m-%d")
    if MODE == "off":
        print("TRADING=off")
        return False
    if now.weekday() >= 5 or today in HOLIDAYS:
        print("market closed today")
        return False
    if not FORCE and not (window[0] <= (now.hour, now.minute) < window[1]):
        why = (f"запуск в {now:%H:%M} ET вне окна {window[0][0]}:{window[0][1]:02d}–"
               f"{window[1][0]}:{window[1][1]:02d}")
        print(f"outside the {label} window ({now:%H:%M} ET)")
        if cmd and state.get(key) != today:
            record_run(state, cmd, "skipped", why)
            vault.save_file(STATE_FILE, state, PASSWORD)
        return False
    if state.get(key) == today and not FORCE:
        print(f"{label}: already ran today")
        return False
    return True


def cmd_execute():
    state = load_state()
    now = now_ny()
    today = now.strftime("%Y-%m-%d")
    window = DRY_EXECUTE_WINDOW if MODE == "dry" else LIVE_EXECUTE_WINDOW
    if not check_day(now, state, "last_execute", window, "pre-market", "execute"):
        return
    events = []
    if MODE == "dry":
        broker = DryBroker([])
    else:
        broker = schwab_or_none(state)
        if broker is None:
            record_run(state, "execute", "skipped", "вход в Schwab истёк")
            vault.save_file(STATE_FILE, state, PASSWORD)
            return

    run_execute(state, broker, today, events, now)
    state["last_execute"] = today
    plan = state.get("plan") or {}
    late = (now.hour, now.minute) >= OPEN_HM
    record_run(state, "execute", "ok",
               (plan.get("status") or "плана нет")
               + (f"; запуск опоздал ({now:%H:%M} ET) — заявки из плана до открытия, "
                  "исполнение по открытию этой сессии" if late else ""),
               plan_date=plan.get("date"), orders=len(state["orders"]), late=late)
    vault.log(state, f"execute {today}: {len(events)} events")
    vault.save_file(STATE_FILE, state, PASSWORD)

    age = refresh_age_days(state.get("token"))
    if MODE in ("manual", "auto") and age is not None and age >= 5.5:
        events.append(f"🔑 Вход в Schwab истекает через {7 - age:.1f} дн. — обнови в приложении.")
    if events:
        push(f"VISAR бот {mode_label(MODE)}: утро {today}", "\n".join(events))
    else:
        print("nothing to do")


# =====================================================================
# BEFORE THE CLOSE: breakouts on today's live candle
# =====================================================================
def breakouts_now(today):
    """(candidates DataFrame, market line, market passes, note) from today's live candles."""
    universe = core.get_sp500()
    prices = core.get_prices(tuple(universe["ticker"]) + ("SPY",))
    spy = core._frame_for(prices, "SPY")
    if spy is None or spy.empty or spy.index[-1].strftime("%Y-%m-%d") != today:
        return None, "", False, "Yahoo ещё не отдаёт сегодняшние свечи"
    reg = core.market_regime(spy).dropna()
    row = reg.iloc[-1]
    ok = core.regime_ok(row, MARKET_FILTER)
    line = f"SPY {row['close']:.0f}, MA50 {row['ma50']:.0f}, MA200 {row['ma200']:.0f}"
    fresh = []
    for t in universe["ticker"]:
        df = core._frame_for(prices, t)
        if df is not None and len(df) and df.index[-1].strftime("%Y-%m-%d") == today:
            fresh.append(t)
    uni = universe[universe["ticker"].isin(fresh)]
    res = core.scan(prices, uni, "breakout", LOOKBACK, False, 0, MIN_RS,
                    stop_buf=STOP_BUF, max_risk=MAX_RISK)
    if not ok or res.empty:
        return res.iloc[0:0] if not res.empty else res, line, ok, ""
    note = ""
    if EARNINGS_DAYS:
        earn = core.next_earnings(list(res["ticker"].head(30)), today=pd.Timestamp(today).date())
        res, dropped = core.apply_earnings(res, earn, EARNINGS_DAYS,
                                           today=pd.Timestamp(today).date())
        if dropped:
            note = f"📅 пропущено из-за отчёта: {dropped}"
    return res, line, ok, note


def cmd_preclose():
    state = load_state()
    now = now_ny()
    today = now.strftime("%Y-%m-%d")
    if not check_day(now, state, "last_preclose", ((15, 10), (15, 58)), "pre-close",
                     "preclose"):
        return
    if "breakout" not in TRADE_SETUPS:
        print("breakouts are not traded (TRADE_SETUPS)")
        return

    res, mkt_line, mkt_ok, note = breakouts_now(today)
    if res is None:
        record_run(state, "preclose", "skipped", note)
        vault.save_file(STATE_FILE, state, PASSWORD)
        push(f"VISAR бот: пробои {today}", f"{note} — пробои купим завтра на открытии.",
             tags="warning")
        return
    state["last_preclose"] = today
    lines = []
    if not mkt_ok:
        lines.append(f"⛔ Рынок не проходит фильтр ({mkt_line}) — пробои сегодня не покупаем.")
    busy = {p["ticker"] for p in state["positions"]} | {o["ticker"] for o in state["orders"]}
    cand = res[~res["ticker"].isin(busy)] if not res.empty else res
    room = room_today(state, today)

    live = MODE in ("manual", "auto")
    broker = None
    if live and not cand.empty:
        if MODE == "manual" and not state.get("auto_breakouts"):
            lines.append("Пробои сейчас (в ручном режиме бот их не покупает — включи "
                         "«Покупать пробои без подтверждения» в приложении):")
            lines += [f"{r.ticker} (RS {r.rs}): {r.close}, уровень {r.level}, стоп {r.stop}"
                      for r in cand.head(6).itertuples()]
            cand = cand.iloc[0:0]
        else:
            broker = schwab_or_none(state)
            if broker is None:
                cand = cand.iloc[0:0]
    quotes = broker.quotes(list(cand["ticker"].head(room + 5))) if broker and room else {}

    bought = []
    for r in cand.itertuples():
        if len(bought) >= room:
            lines.append(f"⏭ ещё {len(cand) - len(bought)} пробоев — нет мест "
                         f"({len(state['positions'])}/{MAX_POSITIONS}, сегодня до {MAX_NEW_PER_DAY})")
            break
        px = float(quotes.get(r.ticker) or r.close)
        if px <= r.level:
            lines.append(f"⏭ {r.ticker}: цена {px:.2f} вернулась под уровень {r.level}")
            continue
        qty = sizing(px, r.stop)
        if qty < 1:
            continue
        oid = "dry"
        if broker:
            try:
                oid = broker.buy_with_stop(r.ticker, qty, r.stop)
            except SchwabError as e:
                lines.append(f"⚠️ {r.ticker}: ошибка ордера {str(e)[:80]}")
                continue
        p = {"ticker": r.ticker, "mode": "breakout", "rs": int(r.rs), "entry_date": today,
             "entry": round(px, 2), "stop": round(float(r.stop), 2), "qty": qty,
             "dry": not live, "checked": today, "signal_date": today, "how": "close",
             "order_id": oid, "entry_time": now.strftime("%H:%M")}
        if live:
            p["pending_fill"] = True
        state["positions"].append(p)
        bought.append(r.ticker)
        lines.append(f"🟢 {r.ticker} (RS {r.rs}): {qty} шт по ~{px:.2f} (${px * qty:.0f}), "
                     f"уровень {r.level}, стоп {r.stop}")
    if not bought and mkt_ok and not any(l.startswith("Пробои сейчас") for l in lines):
        lines.append("Пробоев с RS ≥ %d сейчас нет." % MIN_RS if res.empty
                     else "Новых покупок нет.")
    if note:
        lines.append(note)
    lines.append(f"Открыто позиций: {len(state['positions'])}/{MAX_POSITIONS}")
    record_run(state, "preclose", "ok",
               "" if bought else ("рынок не проходит фильтр" if not mkt_ok
                                  else "нет пробоев" if res.empty else "нет новых покупок"),
               data_date=today, candidates=int(len(res)), bought=len(bought))
    vault.log(state, f"preclose {today}: bought {bought}")
    vault.save_file(STATE_FILE, state, PASSWORD)
    title = f"VISAR бот {mode_label(MODE)}: пробои {now:%H:%M}"
    push(title, "\n".join(lines), tags="chart_with_upwards_trend")


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
        elif cmd == "preclose":
            cmd_preclose()
        else:
            print(__doc__)
            return 1
    except Exception as e:
        traceback.print_exc()
        push("VISAR бот: ошибка", f"{cmd}: {str(e)[:300]}", tags="rotating_light")
        try:                             # record the failure on the last SAVED state only
            st = vault.load_file(STATE_FILE, PASSWORD)
            record_run(st, cmd, "error", f"{type(e).__name__}: {str(e)[:200]}")
            vault.save_file(STATE_FILE, st, PASSWORD)
        except Exception:
            traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
