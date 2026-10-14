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

import vault
from schwab_api import auth_url, exchange_code, refresh_age_days

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
        "plan": "План на следующую сессию", "plan_none": "Плана нет.",
        "plan_from": "Сигналы от {d} · статус: {s}",
        "status": {"new": "ожидает", "done": "выполнен", "not_approved": "не подтверждён",
                   "rejected": "отклонён", "expired": "устарел"},
        "approve": "✅ Подтвердить покупки", "reject": "❌ Отменить план",
        "approved": "Подтверждён — бот купит утром.", "rejected_msg": "План отменён.",
        "pos": "Открытые позиции", "pos_none": "Открытых позиций нет.",
        "closed": "Закрытые сделки", "closed_none": "Закрытых сделок пока нет.",
        "summary": "Сделок: {n} · в плюсе: {w:.0f}% · итого: ${p:+,.0f} · среднее: {r:+.2f}R",
        "log": "Журнал бота",
        "cols": {"ticker": "Тикер", "mode": "Сетап", "rs": "RS", "close": "Цена сигнала",
                 "stop": "Стоп", "est_qty": "≈ Акций", "est_cost": "≈ Сумма $",
                 "entry_date": "Вход", "entry": "Цена входа", "qty": "Акций",
                 "days": "Дней", "last": "Сейчас", "pnl_now": "P&L $", "dry": "Тренировка",
                 "exit_date": "Выход", "exit": "Цена выхода", "reason": "Причина",
                 "pnl": "P&L $", "r": "R"},
        "reasons": {"stop": "🛑 стоп", "time": "⏱ 20 дней"},
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
        "plan": "Plan for the next session", "plan_none": "No plan.",
        "plan_from": "Signals from {d} · status: {s}",
        "status": {"new": "waiting", "done": "executed", "not_approved": "not approved",
                   "rejected": "rejected", "expired": "expired"},
        "approve": "✅ Approve buys", "reject": "❌ Cancel plan",
        "approved": "Approved — the bot buys in the morning.", "rejected_msg": "Plan cancelled.",
        "pos": "Open positions", "pos_none": "No open positions.",
        "closed": "Closed trades", "closed_none": "No closed trades yet.",
        "summary": "Trades: {n} · winners: {w:.0f}% · total: ${p:+,.0f} · average: {r:+.2f}R",
        "log": "Bot log",
        "cols": {"ticker": "Ticker", "mode": "Setup", "rs": "RS", "close": "Signal price",
                 "stop": "Stop", "est_qty": "≈ Shares", "est_cost": "≈ Amount $",
                 "entry_date": "Entry", "entry": "Entry price", "qty": "Shares",
                 "days": "Days", "last": "Now", "pnl_now": "P&L $", "dry": "Training",
                 "exit_date": "Exit", "exit": "Exit price", "reason": "Reason",
                 "pnl": "P&L $", "r": "R"},
        "reasons": {"stop": "🛑 stop", "time": "⏱ 20 days"},
    },
}


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

    C = X["cols"]
    # ---------- plan ----------
    st.subheader(X["plan"])
    plan = state.get("plan")
    if not plan or not plan.get("items"):
        st.write(X["plan_none"])
    else:
        st.caption(X["plan_from"].format(d=plan["date"],
                                         s=X["status"].get(plan.get("status"), plan.get("status"))))
        df = pd.DataFrame(plan["items"])[["ticker", "mode", "rs", "close", "stop", "est_qty",
                                          "est_cost"]]
        df["mode"] = df["mode"].map(lambda m: T.get(f"mode_{m}", m))
        st.dataframe(df.rename(columns=C), hide_index=True, use_container_width=True)
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

    # ---------- open positions ----------
    st.subheader(X["pos"])
    pos = state.get("positions") or []
    if not pos:
        st.write(X["pos_none"])
    else:
        df = pd.DataFrame(pos)
        today = time.strftime("%Y-%m-%d")
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
        except Exception:
            df["last"], df["pnl_now"] = np.nan, np.nan
        df["mode"] = df["mode"].map(lambda m: T.get(f"mode_{m}", m))
        cols = ["ticker", "mode", "entry_date", "entry", "stop", "qty", "days", "last", "pnl_now",
                "dry"]
        st.dataframe(df[cols].rename(columns=C), hide_index=True, use_container_width=True)

    # ---------- closed trades ----------
    st.subheader(X["closed"])
    closed = state.get("closed") or []
    if not closed:
        st.write(X["closed_none"])
    else:
        df = pd.DataFrame(closed)
        st.markdown(X["summary"].format(n=len(df), w=(df["pnl"] > 0).mean() * 100,
                                        p=df["pnl"].sum(), r=df["r"].dropna().mean()))
        df["mode"] = df["mode"].map(lambda m: T.get(f"mode_{m}", m))
        df["reason"] = df["reason"].map(X["reasons"])
        cols = ["ticker", "mode", "entry_date", "entry", "exit_date", "exit", "qty", "reason",
                "pnl", "r", "dry"]
        st.dataframe(df[cols].iloc[::-1].rename(columns=C), hide_index=True,
                     use_container_width=True)

    with st.expander(X["log"], expanded=False):
        for row in reversed(state.get("log", [])[-30:]):
            st.caption(f"{row['t']} — {row['msg']}")
