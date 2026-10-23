"""
"💼 Trading" tab of the app: password-gated view of the trading bot.
Connect Schwab (weekly), approve tomorrow's plan, see open positions and results.

Streamlit secrets used (Manage app → Settings → Secrets):
  STATE_PASSWORD     — same password as in GitHub secrets (unlocks the tab and the state)
  GH_TOKEN           — GitHub token with write access to this repo (to save approvals/login)
  SCHWAB_APP_KEY     — from developer.schwab.com (needed only to connect Schwab)
  SCHWAB_APP_SECRET
"""
import time

import numpy as np
import pandas as pd
import streamlit as st

import bot_status
import trade_metrics as tm
import vault
from schwab_api import auth_url, exchange_code, refresh_age_days

# plotly is imported lazily inside the chart helpers so the table/label unit tests
# (test_trade_tab.TestLabels) can import this module without plotly installed.

# Plotly palette — identical to the Paper tab so the two books read as one app.
C_BREAKOUT, C_RETEST, C_VCP = "#9B5CF0", "#39B5A8", "#E6A23C"
C_WIN, C_LOSS = "#30A46C", "#E5484D"
C_GRID, C_BG, C_FG = "#23232E", "#0B0B12", "#EDEDF5"
STRAT_COLOR = {"breakout": C_BREAKOUT, "retest": C_RETEST, "vcp": C_VCP}

TX = {
    "ru": {
        "tab": "💼 Торговля",
        "no_setup": "Бот ещё не настроен: в Streamlit → Manage app → Settings → Secrets нет "
                    "STATE_PASSWORD. Инструкция — в чате с Claude.",
        "pw": "Пароль бота", "unlock": "Открыть", "bad_pw": "Неверный пароль",
        "lock": "🔒 Закрыть", "reload": "🔄 Обновить",
        "mode": "Режим бота", "modes": {"dry": "🧪 тренировка (виртуальные сделки)",
                                        "manual": "✋ ручное подтверждение",
                                        "auto": "🤖 автоматический", "off": "выключен",
                                        None: "ещё не запускался"},
        "no_state": "Бот ещё ни разу не запускался — состояние появится после первого плана.",
        "schwab": "Подключение Schwab",
        "sch_ok": "✅ Подключено, вход действует ещё {d:.1f} дн.",
        "sch_soon": "⚠️ Вход истекает через {d:.1f} дн. — обнови сейчас.",
        "sch_none": "Не подключено (для тренировки не нужно).",
        "sch_steps": "1) Открой ссылку и войди в Schwab, разреши доступ.  \n"
                     "2) Откроется пустая страница с адресом `https://127.0.0.1/?code=...` — "
                     "это нормально.  \n3) Скопируй **весь адрес** и вставь ниже **в течение "
                     "30 секунд**.",
        "sch_link": "🔑 Войти в Schwab", "sch_paste": "Адрес после входа (https://127.0.0.1/?code=…)",
        "sch_save": "Подключить", "sch_done": "Schwab подключён ✅",
        "no_key": "Нет SCHWAB_APP_KEY / SCHWAB_APP_SECRET в Secrets Streamlit.",
        "no_gh": "Нет GH_TOKEN в Secrets Streamlit — приложение не может сохранять изменения.",
        "plan": "План на утро (покупка на открытии)", "plan_none": "Плана нет.",
        "plan_note": "VCP и ретест покупаются на открытии следующего дня. Пробои бот покупает "
                     "сам в тот же день около 15:30, если пробой держится.",
        "orders": "Утренние покупки (ждут подтверждения исполнения)",
        "orders_note": "Покупка по рынку на открытии, стоп ставится сразу. Итог — в вечернем пуше.",
        "auto_brk": "Покупать пробои без подтверждения (около 15:30)",
        "auto_brk_help": "В ручном режиме нет времени подтверждать пробой — до закрытия 30 минут. "
                         "Включено: бот покупает пробои сам с теми же лимитами риска. "
                         "Выключено: присылает пуш со списком, а покупаешь ты сам.",
        "plan_from": "Сигналы от {d} · статус: {s}",
        "status": {"new": "ожидает", "done": "выполнен", "not_approved": "не подтверждён",
                   "rejected": "отклонён", "expired": "устарел"},
        "approve": "✅ Подтвердить покупки", "reject": "❌ Отменить план",
        "approved": "Подтверждён — утром бот купит на открытии.", "rejected_msg": "План отменён.",
        "bot_status": "Статус бота",
        "rules": "Правила этого контура (бот, режим тренировки): VCP и ретест — покупка на "
                 "открытии следующей сессии, пробой — около 15:30; стоп ниже уровня на 3 %; "
                 "выход по времени — продажа на **открытии 21-й сессии** после входа. "
                 "Бумажный портфель Retest RS-first выходит по **закрытию 20-го бара** — это "
                 "разные правила, статистику двух контуров не объединять.",
        "eds": {"unverified": "не проверен (нет минутных данных)", "intraday_ok": "проверен",
                "intraday_hit": "сработал"},
        "pos": "Открытые позиции", "pos_none": "Открытых позиций нет.",
        "closed": "Закрытые сделки", "closed_none": "Закрытых сделок пока нет.",
        "summary": "Сделок: {n} · в плюсе: {w} · итого: {p} · среднее: {r}",
        "log": "Журнал бота",
        "cols": {"ticker": "Тикер", "mode": "Сетап", "rs": "RS", "close": "Закрытие",
                 "level": "Уровень", "est": "≈ Цена", "how": "Когда вход", "date": "Дата",
                 "stop": "Стоп", "est_qty": "≈ Акций", "est_cost": "≈ Сумма $",
                 "entry_date": "Дата входа", "entry": "Цена входа", "qty": "Акций",
                 "days": "Дней", "last": "Сейчас", "pnl_now": "P&L сейчас $",
                 "entry_day_stop": "Стоп в день входа",
                 "dry": "Тренировка",
                 "exit_date": "Дата выхода", "exit": "Цена выхода", "reason": "Причина",
                 "pnl": "P&L $", "r": "R"},
        "reasons": {"stop": "🛑 стоп", "time": "⏱ 20 дней"},
        "how": {"close": "перед закрытием", "open": "на открытии"},
    },
    "en": {
        "tab": "💼 Trading",
        "no_setup": "The bot isn't set up yet: STATE_PASSWORD is missing in Streamlit → "
                    "Manage app → Settings → Secrets.",
        "pw": "Bot password", "unlock": "Unlock", "bad_pw": "Wrong password",
        "lock": "🔒 Lock", "reload": "🔄 Refresh",
        "mode": "Bot mode", "modes": {"dry": "🧪 training (virtual trades)",
                                      "manual": "✋ manual approval", "auto": "🤖 automatic",
                                      "off": "off", None: "not run yet"},
        "no_state": "The bot hasn't run yet — state appears after the first plan.",
        "schwab": "Schwab connection",
        "sch_ok": "✅ Connected, login valid for {d:.1f} more days.",
        "sch_soon": "⚠️ Login expires in {d:.1f} days — renew now.",
        "sch_none": "Not connected (not needed for training mode).",
        "sch_steps": "1) Open the link, log in to Schwab and allow access.  \n"
                     "2) A blank page opens at `https://127.0.0.1/?code=...` — that's expected.  \n"
                     "3) Copy the **whole address** and paste it below **within 30 seconds**.",
        "sch_link": "🔑 Log in to Schwab", "sch_paste": "Address after login (https://127.0.0.1/?code=…)",
        "sch_save": "Connect", "sch_done": "Schwab connected ✅",
        "no_key": "SCHWAB_APP_KEY / SCHWAB_APP_SECRET missing in Streamlit secrets.",
        "no_gh": "GH_TOKEN missing in Streamlit secrets — the app can't save changes.",
        "plan": "Morning plan (buy at the open)", "plan_none": "No plan.",
        "plan_note": "VCP and retest are bought at the next open. Breakouts are bought by the "
                     "bot the same day around 3:30 PM if the breakout holds.",
        "orders": "Morning buys (waiting for fill confirmation)",
        "orders_note": "Market buy at the open, stop placed right away. Results come in the "
                       "evening push.",
        "auto_brk": "Buy breakouts without approval (around 3:30 PM)",
        "auto_brk_help": "In manual mode there's no time to approve a breakout — 30 minutes to "
                         "the close. On: the bot buys breakouts itself within the same risk "
                         "limits. Off: you get a push with the list and buy yourself.",
        "plan_from": "Signals from {d} · status: {s}",
        "status": {"new": "waiting", "done": "executed", "not_approved": "not approved",
                   "rejected": "rejected", "expired": "expired"},
        "approve": "✅ Approve buys", "reject": "❌ Cancel plan",
        "approved": "Approved — the bot buys in the morning.", "rejected_msg": "Plan cancelled.",
        "bot_status": "Bot status",
        "rules": "Rules of this book (bot, training mode): VCP and retest are bought at the next "
                 "session's open, breakouts around 3:30 PM; stop 3 % below the level; time exit "
                 "— sold at the **open of session 21** after entry. The Retest RS-first paper "
                 "portfolio exits at the **close of bar 20** — different rules, never combine "
                 "the two books' statistics.",
        "eds": {"unverified": "not verified (no minute data)", "intraday_ok": "verified",
                "intraday_hit": "hit"},
        "pos": "Open positions", "pos_none": "No open positions.",
        "closed": "Closed trades", "closed_none": "No closed trades yet.",
        "summary": "Trades: {n} · winners: {w} · total: {p} · average: {r}",
        "log": "Bot log",
        "cols": {"ticker": "Ticker", "mode": "Setup", "rs": "RS", "close": "Close",
                 "level": "Level", "est": "≈ Price", "how": "Entry timing", "date": "Date",
                 "stop": "Stop", "est_qty": "≈ Shares", "est_cost": "≈ Amount $",
                 "entry_date": "Entry date", "entry": "Entry price", "qty": "Shares",
                 "days": "Days", "last": "Now", "pnl_now": "Open P&L $", "dry": "Training",
                 "entry_day_stop": "Entry-day stop",
                 "exit_date": "Exit date", "exit": "Exit price", "reason": "Reason",
                 "pnl": "P&L $", "r": "R"},
        "reasons": {"stop": "🛑 stop", "time": "⏱ 20 days"},
        "how": {"close": "before the close", "open": "at the open"},
    },
}


# ===================================================================== performance section
# Separate translation table so the large TX dict above is left untouched.
PERF = {
    "ru": {
        "title": "Trading Performance",
        "pick": "Стратегия",
        "empty": "Пока нет ни закрытых сделок, ни открытых позиций — статистика появится "
                 "после первых сделок бота.",
        "total": "Сделок (закрыто)", "open": "Открыто позиций", "win": "Win Rate",
        "pf": "Profit Factor", "total_pnl": "Итого P&L", "avg_pnl": "Средний P&L",
        "exp_r": "Ожидание R", "avg_win": "Средний плюс", "avg_loss": "Средний минус",
        "avg_hold": "Средн. удержание", "days_u": "дн.",
        "max_dd": "Макс. просадка",
        "max_dd_help": "Нужна достоверная кривая капитала. Бот не ведёт учёт капитала, "
                       "историю восстановить нельзя — показатель появится, когда учёт Equity "
                       "будет запущен с проверенной точки. Выдуманную кривую не строим.",
        "strat_pnl": "Накопленный P&L закрытых сделок по стратегиям",
        "strat_pnl_note": "Это накопленный реализованный P&L закрытых сделок (в $), "
                          "НЕ кривая капитала: отдельный капитал по стратегиям не выделяется.",
        "dist": "Распределение результатов, R",
        "dist_win": "Плюсовые", "dist_loss": "Минусовые",
        "no_closed": "Закрытых сделок пока нет.", "no_r": "Нет данных по R.",
        "equity_deferred": "📉 Графики «Капитал против SPY» и «Просадка портфеля» будут "
                           "добавлены отдельно: бот не хранит кэш и ежедневную стоимость "
                           "портфеля, поэтому честную кривую капитала можно вести только "
                           "вперёд, с проверенной стартовой точки. Выдуманную историю "
                           "доходности не показываем.",
        "cmp": "Сравнение стратегий",
        "cmp_note": "Таблица всегда показывает все три стратегии, независимо от "
                    "переключателя выше (он фильтрует карточки и графики).",
        "c_strat": "Стратегия", "c_trades": "Сделок", "c_win": "Win Rate %",
        "c_pf": "PF", "c_r": "Ср. R", "c_pnl": "P&L $",
        "journal": "Журнал сделок",
        "f_reason": "Причина", "f_kind": "Тип", "f_from": "С даты", "f_to": "По дату",
        "kind_all": "все", "kind_dry": "тренировка", "kind_real": "реальные",
        "j_none": "Под выбранные фильтры сделок нет.",
        "j_pnl_pct": "P&L %", "j_hold": "Дней",
        "j_pick": "Выбери сделку в таблице, чтобы открыть её график.",
        "j_chart": "График сделки: {t} ({a} → {b})",
        "j_no_px": "Нет истории котировок для {t} в доступном окне.",
        "j_entry": "вход", "j_exit": "выход",
    },
    "en": {
        "title": "Trading Performance",
        "pick": "Strategy",
        "empty": "No closed trades or open positions yet — statistics appear after the "
                 "bot's first trades.",
        "total": "Trades (closed)", "open": "Open positions", "win": "Win Rate",
        "pf": "Profit Factor", "total_pnl": "Total P&L", "avg_pnl": "Average P&L",
        "exp_r": "Expectancy R", "avg_win": "Avg winner", "avg_loss": "Avg loser",
        "avg_hold": "Avg holding", "days_u": "d",
        "max_dd": "Max drawdown",
        "max_dd_help": "Needs a reliable equity curve. The bot keeps no capital model and "
                       "history cannot be reconstructed — this appears once Equity accounting "
                       "is started from a verified point. We do not fabricate a curve.",
        "strat_pnl": "Cumulative closed-trade P&L by strategy",
        "strat_pnl_note": "Cumulative realized P&L of closed trades (in $), NOT an equity "
                          "curve: no capital is allocated per strategy.",
        "dist": "Outcome distribution, R",
        "dist_win": "Winners", "dist_loss": "Losers",
        "no_closed": "No closed trades yet.", "no_r": "No R data.",
        "equity_deferred": "📉 The 'Equity vs SPY' and 'Portfolio drawdown' charts will be "
                           "added separately: the bot stores no cash or daily portfolio value, "
                           "so an honest equity curve can only run forward from a verified "
                           "start. We do not show a fabricated return history.",
        "cmp": "Strategy comparison",
        "cmp_note": "This table always shows all three strategies, regardless of the "
                    "switch above (which filters the cards and charts).",
        "c_strat": "Strategy", "c_trades": "Trades", "c_win": "Win Rate %",
        "c_pf": "PF", "c_r": "Avg R", "c_pnl": "P&L $",
        "journal": "Trade journal",
        "f_reason": "Reason", "f_kind": "Type", "f_from": "From", "f_to": "To",
        "kind_all": "all", "kind_dry": "training", "kind_real": "real",
        "j_none": "No trades match the selected filters.",
        "j_pnl_pct": "P&L %", "j_hold": "Days",
        "j_pick": "Select a trade in the table to open its chart.",
        "j_chart": "Trade chart: {t} ({a} → {b})",
        "j_no_px": "No quote history for {t} in the available window.",
        "j_entry": "entry", "j_exit": "exit",
    },
}


def _usd(v):
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"${v:+,.0f}"


def _pct(v):
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"{v:.0f}%"


def _rr(v):
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"{v:+.2f}R"


def _num(v):
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"{v:.2f}"


def _days(v, unit):
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"{v:.0f} {unit}"


def _style(fig, height):
    fig.update_layout(height=height, margin=dict(l=8, r=8, t=12, b=8),
                      paper_bgcolor=C_BG, plot_bgcolor=C_BG, font=dict(color=C_FG),
                      legend=dict(orientation="h", y=1.14, x=0),
                      xaxis=dict(gridcolor=C_GRID, zerolinecolor=C_GRID),
                      yaxis=dict(gridcolor=C_GRID, zerolinecolor=C_GRID))
    return fig


PLAN_COLS = ["ticker", "mode", "rs", "close", "stop", "est_qty", "est_cost"]
ORDER_COLS = ["ticker", "mode", "date", "est", "stop", "qty", "dry"]
POS_COLS = ["ticker", "mode", "how", "entry_date", "entry", "stop", "qty", "days", "last",
            "pnl_now", "entry_day_stop", "dry"]
CLOSED_COLS = ["ticker", "mode", "entry_date", "entry", "exit_date", "exit", "qty", "reason",
               "pnl", "r", "dry"]


def _view(df: pd.DataFrame, cols: list, labels: dict) -> pd.DataFrame:
    """Columns `cols` (missing ones shown empty) renamed to display labels. Two fields with
    the same label would crash st.dataframe (PyArrow: duplicate column names), so that is
    refused here with the conflicting fields named."""
    shown = [labels.get(c, c) for c in cols]
    dup = sorted({x for x in shown if shown.count(x) > 1})
    if dup:
        raise ValueError("duplicate display labels " +
                         str({x: [c for c in cols if labels.get(c, c) == x] for x in dup}))
    return df.reindex(columns=cols).rename(columns=labels)


def plan_table(items, T, X) -> pd.DataFrame:
    df = pd.DataFrame(items).reindex(columns=PLAN_COLS)
    df["mode"] = df["mode"].map(lambda m: T.get(f"mode_{m}", m))
    return _view(df, PLAN_COLS, X["cols"])


def orders_table(orders, T, X) -> pd.DataFrame:
    df = pd.DataFrame(orders).reindex(columns=ORDER_COLS)
    df["mode"] = df["mode"].map(lambda m: T.get(f"mode_{m}", m))
    return _view(df, ORDER_COLS, X["cols"])


def positions_table(pos, T, X, get_prices, today=None) -> pd.DataFrame:
    df = pd.DataFrame(pos)
    today = today or time.strftime("%Y-%m-%d")
    df["days"] = df["entry_date"].map(lambda d: int(np.busday_count(d, today)))
    try:
        px = get_prices(tuple(sorted(df["ticker"].unique())))
        last = {}
        for t in df["ticker"]:
            try:
                last[t] = float(px[t]["Close"].dropna().iloc[-1])
            except Exception:
                pass
        df["last"] = df["ticker"].map(last)
        df["pnl_now"] = ((df["last"] - df["entry"]) * df["qty"]).round(2)
    except Exception:                       # prices unavailable: show the positions anyway
        df["last"], df["pnl_now"] = np.nan, np.nan
    df["mode"] = df["mode"].map(lambda m: T.get(f"mode_{m}", m))
    df["how"] = df.get("how", pd.Series(index=df.index, dtype=object)).map(X["how"])
    df["entry_day_stop"] = df.get("entry_day_stop", pd.Series(index=df.index, dtype=object)) \
        .map(X["eds"])
    return _view(df, POS_COLS, X["cols"])


def closed_table(closed, T, X) -> pd.DataFrame:
    df = pd.DataFrame(closed)
    # tolerate old/partial records: missing columns and non-numeric values must not crash
    for c in ("entry", "exit", "qty", "pnl", "r"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    mode = df["mode"] if "mode" in df.columns else pd.Series(index=df.index, dtype=object)
    reason = df["reason"] if "reason" in df.columns else pd.Series(index=df.index, dtype=object)
    df["mode"] = mode.map(lambda m: T.get(f"mode_{m}", m))
    df["reason"] = reason.map(lambda x: X["reasons"].get(x, x) if isinstance(x, str) else x)
    return _view(df.iloc[::-1], CLOSED_COLS, X["cols"])


def _num_col(df: pd.DataFrame, name: str) -> pd.Series:
    """Numeric Series for column `name`, ALWAYS a Series aligned to df.index — even when
    the column is entirely absent (old records) — so callers never get a bare scalar from
    df.get(name). Non-numeric values become NaN."""
    s = df[name] if name in df.columns else pd.Series(index=df.index, dtype="float64")
    return pd.to_numeric(s, errors="coerce")


def closed_summary(closed, X) -> str:
    """One-line closed-trades summary. Missing/unavailable metrics render as '—', never
    'nan', and a wholly missing pnl/r column can't crash the tab."""
    df = pd.DataFrame(closed)
    pnl, rr = _num_col(df, "pnl"), _num_col(df, "r")
    has_pnl, has_r = bool(pnl.notna().any()), bool(rr.notna().any())
    return X["summary"].format(
        n=len(df),
        w=f"{(pnl.dropna() > 0).mean() * 100:.0f}%" if has_pnl else "—",
        p=f"${pnl.sum():+,.0f}" if has_pnl else "—",
        r=f"{rr.dropna().mean():+.2f}R" if has_r else "—")


def _strategy_switch(P):
    """ALL|BREAKOUT|RETEST|VCP switch. Seeds session_state before the widget (instead of
    passing default=) so the initial value is ALL AND tests/callers can preset the choice
    via session_state without the default+session_state conflict Streamlit raises on."""
    opts = ["ALL", "BREAKOUT", "RETEST", "VCP"]
    key = "trade_perf_strategy"
    if key not in st.session_state:
        st.session_state[key] = "ALL"
    try:
        sel = st.segmented_control(P["pick"], opts, key=key, label_visibility="collapsed")
    except Exception:                                   # older streamlit: plain radio
        rkey = "trade_perf_strategy_r"
        if rkey not in st.session_state:
            st.session_state[rkey] = "ALL"
        sel = st.radio(P["pick"], opts, horizontal=True, key=rkey,
                       label_visibility="collapsed")
    return (sel or "ALL").lower()


def _inject_card_css():
    """At most 2 metric cards per row on phones (<=640px); the natural 4-wide layout
    stays on wider screens. Scoped to column rows that actually contain a metric, so
    button/filter rows are untouched. Re-injected every run (Streamlit rebuilds the DOM)."""
    st.markdown(
        '<style>@media (max-width:640px){'
        'div[data-testid="stHorizontalBlock"]:has(div[data-testid="stMetric"])'
        '{flex-wrap:wrap!important}'
        'div[data-testid="stHorizontalBlock"]:has(div[data-testid="stMetric"])'
        '>div[data-testid="stColumn"]'
        '{flex:1 1 calc(50% - 0.5rem)!important;min-width:calc(50% - 0.5rem)!important;'
        'width:calc(50% - 0.5rem)!important}}</style>',
        unsafe_allow_html=True)


def render_performance(state, lang):
    """Top 'Trading Performance' block: strategy switch + metric cards. Returns the
    selected strategy ('all'/'breakout'/'retest'/'vcp') for the rest of the tab."""
    P = PERF[lang]
    closed = state.get("closed") or []
    positions = state.get("positions") or []
    st.markdown(f"### {P['title']}")
    strat = _strategy_switch(P)
    if not closed and not positions:
        st.info(P["empty"])
        return strat
    _inject_card_css()
    s = tm.strategy_stats(closed, positions, strat)
    r1 = st.columns(4)
    r1[0].metric(P["total"], s["total_trades"])
    r1[1].metric(P["open"], s["open_positions"] if s["open_positions"] is not None else "—")
    r1[2].metric(P["win"], _pct(s["win_rate_pct"]))
    r1[3].metric(P["pf"], _num(s["profit_factor"]))
    r2 = st.columns(4)
    r2[0].metric(P["total_pnl"], _usd(s["total_pnl_usd"]))
    r2[1].metric(P["avg_pnl"], _usd(s["avg_pnl_usd"]))
    r2[2].metric(P["exp_r"], _rr(s["expectancy_r"]))
    r2[3].metric(P["avg_hold"], _days(s["avg_holding_days"], P["days_u"]))
    r3 = st.columns(4)
    r3[0].metric(P["avg_win"], _usd(s["avg_winner_usd"]))
    r3[1].metric(P["avg_loss"], _usd(s["avg_loser_usd"]))
    r3[2].metric(P["max_dd"], "—", help=P["max_dd_help"])
    return strat


def render_perf_charts(state, lang, strat):
    """B) cumulative closed-trade P&L by strategy, D) R distribution. Equity/drawdown
    (A/C) are deferred — a clear note stands in instead of a fabricated curve."""
    import plotly.graph_objects as go
    P = PERF[lang]
    closed = state.get("closed") or []

    st.markdown(f"**{P['strat_pnl']}**")
    wide = tm.cumulative_pnl_by_strategy(closed, strat)
    if wide.empty:
        st.caption(P["no_closed"])
    else:
        fig = go.Figure()
        for col in wide.columns:
            fig.add_scatter(x=wide.index, y=wide[col], mode="lines", name=col.capitalize(),
                            line=dict(color=STRAT_COLOR.get(col, C_FG), width=2))
        st.plotly_chart(_style(fig, 280), use_container_width=True,
                        config={"displayModeBar": False})
    st.caption(P["strat_pnl_note"])

    st.markdown(f"**{P['dist']}**")
    r = tm.r_values(closed, strat)
    if not len(r):
        st.caption(P["no_r"])
    else:
        wins, losses = r[r > 0], r[r <= 0]
        fig = go.Figure()
        if len(losses):
            fig.add_histogram(x=losses, name=P["dist_loss"], marker_color=C_LOSS,
                              xbins=dict(size=0.5), opacity=0.85)
        if len(wins):
            fig.add_histogram(x=wins, name=P["dist_win"], marker_color=C_WIN,
                              xbins=dict(size=0.5), opacity=0.85)
        fig.update_layout(barmode="overlay", bargap=0.05)
        st.plotly_chart(_style(fig, 240), use_container_width=True,
                        config={"displayModeBar": False})
    st.caption(P["equity_deferred"])


def render_comparison(state, lang):
    P = PERF[lang]

    def rnd(v, n):
        return round(v, n) if isinstance(v, (int, float)) and np.isfinite(v) else v

    rows = tm.comparison_rows(state.get("closed") or [], state.get("positions") or [])
    df = pd.DataFrame([{
        P["c_strat"]: r["strategy"].capitalize(),
        P["c_trades"]: r["total_trades"],
        P["c_win"]: rnd(r["win_rate_pct"], 1),
        P["c_pf"]: rnd(r["profit_factor"], 2),
        P["c_r"]: rnd(r["expectancy_r"], 2),
        P["c_pnl"]: rnd(r["total_pnl_usd"], 2),
    } for r in rows])
    st.markdown(f"**{P['cmp']}**")
    st.dataframe(df, hide_index=True, use_container_width=True)
    st.caption(P["cmp_note"])


def _selected_rows(event):
    """Row indices selected in an st.dataframe(on_select=...) — tolerant of the object
    shape across streamlit versions and of AppTest returning nothing."""
    sel = getattr(event, "selection", None)
    if sel is None and isinstance(event, dict):
        sel = event.get("selection")
    if sel is None:
        return []
    rows = getattr(sel, "rows", None)
    if rows is None and isinstance(sel, dict):
        rows = sel.get("rows")
    return list(rows or [])


def _trade_chart(row, lang, get_prices):
    import plotly.graph_objects as go
    P = PERF[lang]
    t = row.get("ticker")
    a, b = str(row.get("entry_date"))[:10], str(row.get("exit_date"))[:10]
    st.markdown(f"_{P['j_chart'].format(t=t, a=a, b=b)}_")
    try:
        close = get_prices((t,))[t]["Close"].dropna()
        close.index = pd.to_datetime(close.index)
    except Exception:
        close = pd.Series(dtype=float)
    if len(close):
        lo = pd.to_datetime(a) - pd.Timedelta(days=12)
        hi = pd.to_datetime(b) + pd.Timedelta(days=12)
        close = close[(close.index >= lo) & (close.index <= hi)]
    if not len(close):
        st.caption(P["j_no_px"].format(t=t))
        return
    fig = go.Figure()
    fig.add_scatter(x=close.index, y=close.values, mode="lines", name=t,
                    line=dict(color=C_FG, width=1.6))
    for d, price, color, lbl in [(a, row.get("entry"), C_WIN, P["j_entry"]),
                                 (b, row.get("exit"), C_LOSS, P["j_exit"])]:
        try:
            fig.add_scatter(x=[pd.to_datetime(d)], y=[float(price)], mode="markers+text",
                            marker=dict(color=color, size=11), text=[lbl],
                            textposition="top center", showlegend=False)
        except Exception:
            pass
    st.plotly_chart(_style(fig, 260), use_container_width=True,
                    config={"displayModeBar": False})


def render_journal(state, lang, strat, get_prices):
    """Filterable closed-trade journal (strategy/reason/type/date) with click-to-chart."""
    P, X = PERF[lang], TX[lang]
    st.markdown(f"**{P['journal']}**")
    closed = state.get("closed") or []
    if not closed:
        st.write(X["closed_none"])
        return
    # Normalise to a canonical schema so old/partial records never KeyError or crash the
    # tab: missing fields become NaN, numeric fields are coerced (non-numeric -> NaN).
    CANON = ["ticker", "mode", "entry_date", "entry", "exit_date", "exit", "qty",
             "reason", "pnl", "r", "dry", "stop"]
    df = pd.DataFrame(closed).reindex(columns=CANON)
    for c in ("entry", "exit", "qty", "pnl", "r", "stop"):
        df[c] = pd.to_numeric(df[c], errors="coerce")

    if strat and strat != "all":
        df = df[df["mode"] == strat]

    f1, f2, f3 = st.columns(3)
    reasons = sorted(df["reason"].dropna().unique().tolist())
    pick_reason = f1.multiselect(P["f_reason"], reasons,
                                 format_func=lambda x: X["reasons"].get(x, x),
                                 key="journal_reason")
    kind = f2.selectbox(P["f_kind"], [P["kind_all"], P["kind_dry"], P["kind_real"]],
                        key="journal_kind")
    if pick_reason:
        df = df[df["reason"].isin(pick_reason)]
    dry = df["dry"]                             # present after reindex; NaN where unrecorded
    if kind == P["kind_dry"]:
        df = df[dry == True]                                                # noqa: E712
    elif kind == P["kind_real"]:
        df = df[dry == False]                   # unrecorded (NaN) shows only under "all"

    ed = pd.to_datetime(df["exit_date"], errors="coerce") if len(df) else pd.Series([], dtype="datetime64[ns]")
    if len(df) and ed.notna().any():
        dmin, dmax = ed.min().date(), ed.max().date()
        rng = f3.date_input(f"{P['f_from']} — {P['f_to']}", value=(dmin, dmax),
                            min_value=dmin, max_value=dmax, key="journal_dates")
        if isinstance(rng, (list, tuple)) and len(rng) == 2:
            lo, hi = pd.to_datetime(rng[0]), pd.to_datetime(rng[1])
            df = df[(ed >= lo) & (ed <= hi)]

    if not len(df):
        st.caption(P["j_none"])
        return
    df = df.reset_index(drop=True)
    with np.errstate(divide="ignore", invalid="ignore"):
        df["pnl_pct"] = pd.to_numeric(df["pnl"], errors="coerce") / (
            pd.to_numeric(df["entry"], errors="coerce")
            * pd.to_numeric(df["qty"], errors="coerce")) * 100
    df["hold"] = df.apply(lambda r: tm.holding_days(r["entry_date"], r["exit_date"]), axis=1)

    show = df.iloc[::-1].reset_index().rename(columns={"index": "_src"})
    C = X["cols"]
    disp = pd.DataFrame({
        C["ticker"]: show["ticker"],
        C["mode"]: show["mode"].map(lambda m: m.capitalize() if isinstance(m, str) else m),
        C["entry_date"]: show["entry_date"], C["entry"]: show["entry"],
        C["exit_date"]: show["exit_date"], C["exit"]: show["exit"],
        C["qty"]: show["qty"],
        C["pnl"]: pd.to_numeric(show["pnl"], errors="coerce").round(2),
        P["j_pnl_pct"]: show["pnl_pct"].round(1),
        C["r"]: pd.to_numeric(show["r"], errors="coerce").round(2),
        C["reason"]: show["reason"].map(lambda x: X["reasons"].get(x, x)),
        P["j_hold"]: show["hold"],
    })
    if "stop" in show and show["stop"].notna().any():                       # only if recorded
        disp[C["stop"]] = show["stop"]
    event = st.dataframe(disp, hide_index=True, use_container_width=True,
                         on_select="rerun", selection_mode="single-row", key="journal_tbl")
    rows = _selected_rows(event)
    if rows:
        _trade_chart(df.iloc[int(show.iloc[rows[0]]["_src"])], lang, get_prices)
    else:
        st.caption(P["j_pick"])


def render_status(state, lang, now=None):
    """Compact status block: facts recorded by the bot only (see bot_status.py)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    now = now or datetime.now(ZoneInfo("America/New_York"))
    S = bot_status.bot_status(state, lang, now.strftime("%Y-%m-%d"),
                              after_open=(now.hour, now.minute) >= (9, 30))
    st.markdown(f"**{TX[lang]['bot_status']}**")
    st.markdown("  \n".join(f"{a}: {b}" for a, b in S["runs"]))
    st.caption(" · ".join(x for x in (S["data"], S["counts"]) if x))
    if S["reasons"]:
        st.markdown(f"_{bot_status.L[lang]['reasons']}:_  \n" +
                    "  \n".join(f"• {r}" for r in S["reasons"]))
    return S


def _secret(name):
    try:
        return st.secrets.get(name, "")
    except Exception:                       # no secrets file at all
        return ""


def render(T, lang, get_prices):
    X = TX[lang]
    password = _secret("STATE_PASSWORD")
    if not password:
        st.info(X["no_setup"])
        return
    if not st.session_state.get("bot_unlocked"):
        pw = st.text_input(X["pw"], type="password", key="bot_pw")
        if st.button(X["unlock"]):
            if pw == password:
                st.session_state["bot_unlocked"] = True
                st.rerun()
            else:
                st.error(X["bad_pw"])
        return

    store = vault.GitHubStore(password, _secret("GH_TOKEN") or None)
    c1, c2 = st.columns(2)
    if c1.button(X["reload"], use_container_width=True) or "bot_state" not in st.session_state:
        try:
            st.session_state["bot_state"], st.session_state["bot_sha"] = store.get()
        except Exception as e:
            st.error(str(e))
            return
    if c2.button(X["lock"], use_container_width=True):
        st.session_state["bot_unlocked"] = False
        st.rerun()
    state, sha = st.session_state["bot_state"], st.session_state["bot_sha"]

    def save(msg):
        try:
            st.session_state["bot_sha"] = store.put(state, st.session_state["bot_sha"], msg)
            return True
        except Exception as e:
            st.error(str(e))
            return False

    st.markdown(f"**{X['mode']}:** {X['modes'].get(state.get('mode'), state.get('mode'))}")
    if sha is None:
        st.caption(X["no_state"])
    render_status(state, lang)
    st.caption(X["rules"])

    # ---------- Trading Performance (per-strategy analytics) ----------
    perf_strat = render_performance(state, lang)
    if state.get("closed"):                 # charts/comparison need closed trades
        render_perf_charts(state, lang, perf_strat)
        render_comparison(state, lang)
    st.divider()

    # ---------- Schwab ----------
    with st.expander(X["schwab"], expanded=False):
        age = refresh_age_days(state.get("token"))
        if age is None:
            st.write(X["sch_none"])
        elif 7 - age < 1.5:
            st.warning(X["sch_soon"].format(d=max(0, 7 - age)))
        else:
            st.success(X["sch_ok"].format(d=7 - age))
        key, secret = _secret("SCHWAB_APP_KEY"), _secret("SCHWAB_APP_SECRET")
        if not (key and secret):
            st.caption(X["no_key"])
        else:
            st.markdown(X["sch_steps"])
            st.link_button(X["sch_link"], auth_url(key), use_container_width=True)
            url = st.text_input(X["sch_paste"], key="sch_url")
            if st.button(X["sch_save"], type="primary", disabled=not url):
                try:
                    state["token"] = exchange_code(key, secret, url)
                    vault.log(state, "schwab connected")
                    if save("Bot: Schwab login"):
                        st.success(X["sch_done"])
                except Exception as e:
                    st.error(str(e))
        if not _secret("GH_TOKEN"):
            st.caption(X["no_gh"])

    # ---------- plan ----------
    st.subheader(X["plan"])
    plan = state.get("plan")
    if not plan or not plan.get("items"):
        st.write(X["plan_none"])
    else:
        st.caption(X["plan_from"].format(d=plan["date"],
                                         s=X["status"].get(plan.get("status"), plan.get("status"))))
        st.dataframe(plan_table(plan["items"], T, X), hide_index=True,
                     use_container_width=True)
        if plan.get("status") == "new" and state.get("mode") == "manual":
            if plan.get("approved"):
                st.success(X["approved"])
            else:
                a, b = st.columns(2)
                if a.button(X["approve"], type="primary", use_container_width=True):
                    plan["approved"], plan["rejected"] = True, False
                    if save("Bot: plan approved"):
                        st.rerun()
                if b.button(X["reject"], use_container_width=True):
                    plan["approved"], plan["rejected"] = False, True
                    if save("Bot: plan rejected"):
                        st.success(X["rejected_msg"])

    st.caption(X["plan_note"])
    if state.get("mode") == "manual":
        on = st.toggle(X["auto_brk"], value=bool(state.get("auto_breakouts")),
                       help=X["auto_brk_help"], key="auto_brk")
        if on != bool(state.get("auto_breakouts")):
            state["auto_breakouts"] = on
            vault.log(state, f"auto breakouts {'on' if on else 'off'}")
            save("Bot: auto breakouts " + ("on" if on else "off"))

    # ---------- morning buys waiting for the evening check ----------
    orders = state.get("orders") or []
    if orders:
        st.subheader(X["orders"])
        st.dataframe(orders_table(orders, T, X), hide_index=True, use_container_width=True)
        st.caption(X["orders_note"])

    # ---------- open positions ----------
    st.subheader(X["pos"])
    pos = state.get("positions") or []
    if not pos:
        st.write(X["pos_none"])
    else:
        st.dataframe(positions_table(pos, T, X, get_prices), hide_index=True,
                     use_container_width=True)

    # ---------- closed trades ----------
    st.subheader(X["closed"])
    closed = state.get("closed") or []
    if not closed:
        st.write(X["closed_none"])
    else:
        st.markdown(closed_summary(closed, X))
        st.dataframe(closed_table(closed, T, X), hide_index=True, use_container_width=True)

    # ---------- trade journal (filters + click-to-chart) ----------
    with st.expander(PERF[lang]["journal"], expanded=False):
        render_journal(state, lang, perf_strat, get_prices)

    with st.expander(X["log"], expanded=False):
        for row in reversed(state.get("log", [])[-30:]):
            st.caption(f"{row['t']} — {row['msg']}")
