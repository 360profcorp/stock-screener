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
import vault
import schwab_auth
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
        "renew": "🔑 Продлить подключение Schwab",
        "renew_go": "➡️ Перейти ко входу Schwab (ссылка одноразовая, 10 минут)",
        "renew_help": "Войди в Schwab и разреши доступ — сканер откроется сам и сохранит вход.",
        "renew_no_cb": "Автопродление выключено: в Secrets Streamlit нет SCHWAB_CALLBACK_URL "
                       "(адрес сканера, зарегистрированный в Schwab Developer Portal).",
        "renew_ok": "✅ Подключение Schwab продлено и сохранено. Вход действует до {t} (Нью-Йорк).",
        "renew_fail": "❌ Подключение не продлено: {r}",
        "expires": "Вход действует до {t} (Нью-Йорк), осталось {h:.0f} ч.",
        "expired": "⛔ Вход в Schwab истёк — новые входы бота заблокированы, стопы у Schwab "
                   "остаются. Продли подключение.",
        "revoked": "⛔ Schwab отклонил вход досрочно — новые входы заблокированы, стопы у Schwab "
                   "остаются. Войди заново.",
        "manual_way": "Запасной способ (вставить адрес вручную)",
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
        "summary": "Сделок: {n} · в плюсе: {w:.0f}% · итого: ${p:+,.0f} · среднее: {r:+.2f}R",
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
        "renew": "🔑 Renew Schwab connection",
        "renew_go": "➡️ Go to the Schwab login (one-time link, 10 minutes)",
        "renew_help": "Log in to Schwab and allow access — the scanner reopens and saves the login.",
        "renew_no_cb": "Automatic renewal is off: SCHWAB_CALLBACK_URL is missing in Streamlit "
                       "secrets (the scanner address registered in the Schwab Developer Portal).",
        "renew_ok": "✅ Schwab connection renewed and saved. Login valid until {t} (New York).",
        "renew_fail": "❌ Connection not renewed: {r}",
        "expires": "Login valid until {t} (New York), {h:.0f} h left.",
        "expired": "⛔ The Schwab login has expired — the bot's new entries are blocked, stops at "
                   "Schwab stay. Renew the connection.",
        "revoked": "⛔ Schwab refused the login early — new entries are blocked, stops at Schwab "
                   "stay. Log in again.",
        "manual_way": "Fallback (paste the address manually)",
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
        "summary": "Trades: {n} · winners: {w:.0f}% · total: ${p:+,.0f} · average: {r:+.2f}R",
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
    df["mode"] = df["mode"].map(lambda m: T.get(f"mode_{m}", m))
    df["reason"] = df["reason"].map(X["reasons"])
    return _view(df.iloc[::-1], CLOSED_COLS, X["cols"])


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


@st.cache_resource
def _pending_states():
    """One-time login states, shared by the app's sessions (Schwab's redirect opens a new
    session). Only hashes are kept."""
    return schwab_auth.PendingStates()


def _ny(ts):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime.fromtimestamp(ts, ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M")


def save_token(store, token, attempts=3):
    """Put the new login into the encrypted state through the GitHub API (the store Actions
    read). Reloads and retries when the bot saved in between. Raises if it could not save."""
    import time as _t
    last = None
    for _ in range(attempts):
        state, sha = store.get()
        state["token"] = token
        state["schwab_reconnected_at"] = _t.strftime("%Y-%m-%d %H:%M:%S", _t.gmtime())
        vault.log(state, "schwab login renewed in the app")
        try:
            store.put(state, sha, "Bot: Schwab login (renewed)")
            return state
        except RuntimeError as e:                 # 409: changed meanwhile -> reload, retry
            last = e
    raise last or RuntimeError("could not save")


def handle_schwab_return(X, password, http=None):
    """Runs on every page load BEFORE the password prompt: Schwab's code lives ~30 s.
    Only a one-time state issued by an unlocked session is accepted. The address bar is
    cleaned in every case; success is shown only after the token was saved."""
    qp = st.query_params
    if "code" not in qp and "state" not in qp:
        return None
    params = {k: qp.get(k) for k in ("code", "state", "error")}
    st.query_params.clear()                        # code/state never stay in the address bar
    key, secret = _secret("SCHWAB_APP_KEY"), _secret("SCHWAB_APP_SECRET")
    cb = _secret("SCHWAB_CALLBACK_URL")
    if not (password and key and secret and cb):
        res = dict(ok=False, reason="the app is not configured for automatic renewal",
                   step="config")
    else:
        import requests
        store = vault.GitHubStore(password, _secret("GH_TOKEN") or None)
        res = schwab_auth.handle_callback(
            params, _pending_states(),
            lambda code: schwab_auth.exchange(key, secret, code, cb, http or requests),
            lambda token: save_token(store, token))
    if res["ok"]:
        st.session_state.pop("bot_state", None)    # reload the saved state on unlock
        st.success(X["renew_ok"].format(t=_ny(res["expires_at"])))
    elif res["ok"] is False:
        st.error(X["renew_fail"].format(r=res["reason"]))
    st.session_state["sch_last_result"] = {k: res[k] for k in ("ok", "step", "reason")}
    return res


def _secret(name):
    try:
        return st.secrets.get(name, "")
    except Exception:                       # no secrets file at all
        return ""


def render(T, lang, get_prices):
    X = TX[lang]
    password = _secret("STATE_PASSWORD")
    handle_schwab_return(X, password)
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

    # ---------- Schwab ----------
    with st.expander(X["schwab"], expanded=False):
        age = refresh_age_days(state.get("token"))
        S = schwab_auth.status(state.get("token"))
        auth = state.get("schwab_auth") or {}
        login = (str(int(float(state["token"]["refresh_created"])))
                 if S["state"] != "none" else None)
        if age is None:
            st.write(X["sch_none"])
        elif S["state"] == "expired":
            st.error(X["expired"])
        elif auth.get("revoked") and auth.get("login") == login:
            st.error(X["revoked"])
        elif 7 - age < 1.5:
            st.warning(X["sch_soon"].format(d=max(0, 7 - age)))
        else:
            st.success(X["sch_ok"].format(d=7 - age))
        if S["expires_at"] and S["state"] != "expired":
            st.caption(X["expires"].format(t=_ny(S["expires_at"]), h=S["seconds_left"] / 3600))
        key, secret = _secret("SCHWAB_APP_KEY"), _secret("SCHWAB_APP_SECRET")
        cb = _secret("SCHWAB_CALLBACK_URL")
        if not (key and secret):
            st.caption(X["no_key"])
        elif not cb:
            st.caption(X["renew_no_cb"])
        else:
            if st.button(X["renew"], type="primary", use_container_width=True):
                st.session_state["sch_login_url"] = schwab_auth.login_url(
                    key, cb, _pending_states().issue())
            if st.session_state.get("sch_login_url"):
                st.link_button(X["renew_go"], st.session_state["sch_login_url"],
                               use_container_width=True)
                st.caption(X["renew_help"])
        if key and secret and st.toggle(X["manual_way"], key="sch_manual", value=not cb):
            st.markdown(X["sch_steps"])
            st.link_button(X["sch_link"], auth_url(key), use_container_width=True)
            url = st.text_input(X["sch_paste"], key="sch_url")
            if st.button(X["sch_save"], type="primary", disabled=not url):
                try:
                    state["token"] = exchange_code(key, secret, url)
                    state["schwab_reconnected_at"] = time.strftime("%Y-%m-%d %H:%M:%S",
                                                                   time.gmtime())
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
        df = pd.DataFrame(closed)
        st.markdown(X["summary"].format(n=len(df), w=(df["pnl"] > 0).mean() * 100,
                                        p=df["pnl"].sum(), r=df["r"].dropna().mean()))
        st.dataframe(closed_table(closed, T, X), hide_index=True, use_container_width=True)

    with st.expander(X["log"], expanded=False):
        for row in reversed(state.get("log", [])[-30:]):
            st.caption(f"{row['t']} — {row['msg']}")
