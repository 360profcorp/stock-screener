"""Facts for the compact "bot status" blocks in the app (no Streamlit here, unit-tested).

Only recorded facts are shown: when a run happened, what it did, and the reason the bot
itself wrote down. When nothing was recorded, the block says so instead of guessing.
"""
from datetime import datetime, time as dtime

import pandas as pd

from paper import nyse

L = {
    "ru": {
        "cmd": {"plan": "Вечер (план)", "execute": "Утро (покупки)", "preclose": "Перед закрытием"},
        "res": {"ok": "✅ выполнен", "skipped": "⏭ пропущен", "error": "❌ ошибка"},
        "never": "нет записей (появятся после следующего запуска бота)",
        "last_ok": "последний успешный: {t}",
        "data": "Данные (сигналы) на {d}",
        "counts": "Сигналов {s} · в плане {p} · заявок {o} · позиций {n}/{m}",
        "r_missed": "план на {d} не исполнен: {why}",
        "r_missed_none": "план на {d} не исполнен: утренний запуск не записан",
        "r_status": {"not_approved": "план не подтверждён", "rejected": "план отменён",
                     "expired": "план устарел (не исполнен вовремя)"},
        "r_nosig": "нет сигналов за {d}",
        "r_full": "лимит позиций: {n}/{m}, сигналов без места {k}",
        "r_held": "сигналы по уже открытым тикерам: {k}",
        "r_small": "размер позиции < 1 акции: {k}",
        "r_wait_fill": "ожидание исполнения: {k} утренних покупок (проверка вечером)",
        "r_wait_data": "ожидание данных: {t}",
        "r_ticker": "{t}: {why}",
        "r_error": "ошибка запуска «{c}»: {why}",
        "r_skip": "запуск «{c}» пропущен: {why}",
        "r_none": "причины не записаны",
        "reasons": "Почему нет новых сделок",
    },
    "en": {
        "cmd": {"plan": "Evening (plan)", "execute": "Morning (buys)", "preclose": "Before the close"},
        "res": {"ok": "✅ done", "skipped": "⏭ skipped", "error": "❌ error"},
        "never": "no records yet (they appear after the bot's next run)",
        "last_ok": "last success: {t}",
        "data": "Data (signals) as of {d}",
        "counts": "Signals {s} · in plan {p} · orders {o} · positions {n}/{m}",
        "r_missed": "plan for {d} not executed: {why}",
        "r_missed_none": "plan for {d} not executed: no morning run recorded",
        "r_status": {"not_approved": "plan not approved", "rejected": "plan cancelled",
                     "expired": "plan expired (not executed in time)"},
        "r_nosig": "no signals for {d}",
        "r_full": "position limit: {n}/{m}, signals without a slot {k}",
        "r_held": "signals for tickers already held: {k}",
        "r_small": "position size < 1 share: {k}",
        "r_wait_fill": "waiting for fills: {k} morning buys (checked in the evening)",
        "r_wait_data": "waiting for data: {t}",
        "r_ticker": "{t}: {why}",
        "r_error": "run '{c}' failed: {why}",
        "r_skip": "run '{c}' skipped: {why}",
        "r_none": "no reasons recorded",
        "reasons": "Why there are no new trades",
    },
}


def bot_status(state: dict, lang: str, today: str, max_positions: int = 5,
               after_open: bool = False) -> dict:
    """{'runs': [(label, line)], 'data': str|None, 'counts': str, 'reasons': [str]}."""
    X = L[lang]
    runs, ok = state.get("runs") or {}, state.get("runs_ok") or {}
    lines = []
    for c in ("plan", "execute", "preclose"):
        r = runs.get(c)
        if not r:
            lines.append((X["cmd"][c], X["never"]))
            continue
        txt = f"{r['at']} ET · {X['res'].get(r['result'], r['result'])}"
        if r.get("reason"):
            txt += f" — {r['reason']}"
        if r["result"] != "ok" and ok.get(c):
            txt += f" · {X['last_ok'].format(t=ok[c]['at'])}"
        lines.append((X["cmd"][c], txt))
    plan = state.get("plan") or {}
    data_date = (runs.get("plan") or {}).get("data_date") or plan.get("date")
    counts = X["counts"].format(s=plan.get("signals", "—"), p=len(plan.get("items") or []),
                                o=len(state.get("orders") or []),
                                n=len(state.get("positions") or []), m=max_positions)
    return dict(runs=lines, data=X["data"].format(d=data_date) if data_date else None,
                counts=counts, reasons=no_trade_reasons(state, lang, today, max_positions,
                                                        after_open))


def no_trade_reasons(state: dict, lang: str, today: str, max_positions: int = 5,
                     after_open: bool = False) -> list:
    """after_open: it is already past 9:30 ET on `today` (the morning window has ended)."""
    X = L[lang]
    out = []
    runs = state.get("runs") or {}
    for c, r in runs.items():
        if r.get("result") == "error":
            out.append(X["r_error"].format(c=X["cmd"].get(c, c), why=r.get("reason")))
    plan = state.get("plan") or {}
    status = plan.get("status")
    if plan and status == "new" and plan.get("for") and plan["for"] <= today and \
            state.get("last_execute") != plan["for"]:
        ex = runs.get("execute")
        if plan["for"] < today or after_open:
            if ex and ex["at"][:10] == plan["for"] and ex.get("result") != "ok":
                out.append(X["r_missed"].format(d=plan["for"], why=ex.get("reason")))
            else:
                out.append(X["r_missed_none"].format(d=plan["for"]))
    if status in X["r_status"]:
        out.append(X["r_status"][status])
    if plan and not plan.get("items"):
        if plan.get("signals") == 0:
            out.append(X["r_nosig"].format(d=plan.get("date")))
    if plan.get("skipped_full"):
        out.append(X["r_full"].format(n=len(state.get("positions") or []), m=max_positions,
                                      k=plan["skipped_full"]))
    if plan.get("already_held"):
        out.append(X["r_held"].format(k=plan["already_held"]))
    if plan.get("too_small"):
        out.append(X["r_small"].format(k=plan["too_small"]))
    for t, why in plan.get("results") or []:
        if why != "ok":
            out.append(X["r_ticker"].format(t=t, why=why))
    orders = state.get("orders") or []
    waiting = [o["ticker"] for o in orders if o.get("waiting_data")]
    if waiting:
        out.append(X["r_wait_data"].format(t=", ".join(waiting)))
    if len(orders) > len(waiting):
        out.append(X["r_wait_fill"].format(k=len(orders) - len(waiting)))
    pre = runs.get("preclose")
    if pre and pre.get("result") == "skipped" and pre["at"][:10] == today:
        out.append(X["r_skip"].format(c=X["cmd"]["preclose"], why=pre.get("reason")))
    elif pre and pre.get("result") == "ok" and pre.get("reason") and pre["at"][:10] == today:
        out.append(f"{X['cmd']['preclose']}: {pre['reason']}")
    return out


# =====================================================================
# Paper portfolio (paper_run.py)
# =====================================================================
P = {
    "ru": {"last_run": "Последнее обновление: {u}", "data": "Данные на {d} · ожидается {e}",
           "behind": "⚠️ Данные отстают: последняя закрытая сессия {e}, обработано по {d}. "
                     "Успешного обновления после {e} не было.",
           "ok": "✅ Обработано по последней закрытой сессии",
           "sessions": "Сессий в последнем запуске: {n}{det}",
           "none_new": " (новых сессий не было)",
           "counts": "Сигналов {s} · заявок на {f}: {o} · позиций {p}/{m}",
           "outcomes": "Решения по заявкам за {d}: {o}",
           "no_orders": "За {d} заявок к исполнению не было",
           "wait": "Ожидание исполнения: {o} заявок на открытии {f}",
           "out": {"entered": "вход", "positions": "лимит позиций", "daily_entries":
                   "лимит входов за день", "capital_or_risk": "не хватило капитала/риска",
                   "ticker_open": "тикер уже в портфеле",
                   "no_trade_open_below_stop": "открытие ниже стопа",
                   "no_trade_max_risk": "риск выше лимита", "expired_no_bar":
                   "истекло без котировки", "not_traded_late": "сигнал опоздал",
                   "invalid": "неверный стоп"}},
    "en": {"last_run": "Last update: {u}", "data": "Data as of {d} · expected {e}",
           "behind": "⚠️ Data is behind: last closed session {e}, processed through {d}. "
                     "No successful update after {e}.",
           "ok": "✅ Processed through the last closed session",
           "sessions": "Sessions in the last run: {n}{det}",
           "none_new": " (no new sessions)",
           "counts": "Signals {s} · orders for {f}: {o} · positions {p}/{m}",
           "outcomes": "Order decisions for {d}: {o}",
           "no_orders": "No orders were due on {d}",
           "wait": "Waiting for fills: {o} orders at the {f} open",
           "out": {"entered": "entered", "positions": "position limit", "daily_entries":
                   "daily entry limit", "capital_or_risk": "capital/risk",
                   "ticker_open": "ticker already held",
                   "no_trade_open_below_stop": "open below stop",
                   "no_trade_max_risk": "risk above limit", "expired_no_bar":
                   "expired without a quote", "not_traded_late": "late signal",
                   "invalid": "invalid stop"}},
}


def last_closed_session(now: datetime) -> str:
    """Last NYSE session whose close (+15 min for data) is before `now`."""
    from paper.store import NY
    ny = now.astimezone(NY)
    d = ny.date()
    if not (nyse.is_session(d) and ny.time() >= dtime(16, 15)):
        d = (pd.Timestamp(d) - pd.Timedelta(days=1)).date()
        while not nyse.is_session(d):
            d = (pd.Timestamp(d) - pd.Timedelta(days=1)).date()
    return str(d)


def paper_status(state: dict, summary: dict, lang: str, now: datetime) -> dict:
    X = P[lang]
    done = state.get("processed_through")
    exp = last_closed_session(now)
    lines = [X["last_run"].format(u=(summary or {}).get("updated", "—")),
             X["data"].format(d=done, e=exp)]
    flag = "ok" if done and done >= exp else "behind"
    lines.append(X["ok"] if flag == "ok" else X["behind"].format(e=exp, d=done))
    ses = (summary or {}).get("sessions") or []
    det = "" if ses else X["none_new"]
    if ses:
        det = " (" + ", ".join(f"{s['day']}: {s['raw']}/{s['queued']}" for s in ses) + ")"
    lines.append(X["sessions"].format(n=len(ses), det=det))
    pend = state.get("pending") or []
    nxt = pend[0].get("scheduled_for") if pend else None
    cfg = state.get("config") or {}
    last_sig = sum(1 for o in pend if o.get("signal_date") == done)
    lines.append(X["counts"].format(s=last_sig, f=nxt or "—", o=len(pend),
                                    p=len(state.get("positions") or {}),
                                    m=cfg.get("max_positions", "—")))
    log = pd.DataFrame(state.get("orders_log") or [])
    if done and len(log) and (log["session"] == done).any():
        c = log[log["session"] == done]["outcome"].value_counts()
        lines.append(X["outcomes"].format(d=done, o=", ".join(
            f"{X['out'].get(k, k)} {v}" for k, v in c.items())))
    elif done:
        lines.append(X["no_orders"].format(d=done))
    if pend:
        lines.append(X["wait"].format(o=len(pend), f=nxt))
    return dict(flag=flag, lines=lines)
