"""'📒 Paper' tab — Retest RS-first paper portfolio dashboard (Task 10). Read-only view of
paper/state/* written by paper_run.py. No broker connection, no orders."""
import json

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from paper import metrics as pm
from paper import store
from paper.config import DEFAULT

TX = {
    "ru": dict(tab="📒 Paper", title="Бумажный портфель: Ретест, сначала RS",
               note="Виртуальный счёт $10 000 без брокера. Сигналы записываются после закрытия, "
                    "покупка — на следующем открытии, стоп −3% под уровнем, выход через 20 дней.",
               empty="Портфель ещё не запущен — он появится после первого запуска paper_run.py.",
               ret="Доходность", spy="SPY за период", dd="Макс. просадка", pf="Profit factor",
               exp="Ожидание", trades="Сделок", win="В плюсе", cur_dd="Текущая просадка",
               eq="Капитал против SPY", ddc="Просадка, %", pos="Открытые позиции",
               pend="Ордера на следующую сессию", led="Закрытые сделки", sig="Сигналы последней сессии",
               orders="Журнал ордеров", none="—", updated="Обновлено: {u} · данные на {d}",
               fwd="**Только форвард:** сделки по сигналам, записанным до открытия сессии. "
                   "Начало: {s}. Сигналов, записанных с опозданием и не торговавшихся: {late}.",
               bf="⚠️ Реконструкция истории (backfill) — НЕ форвард-результат",
               bf_note="Пересчитано задним числом по историческим данным. Не смешивается с "
                       "форвард-портфелем и не является результатом торговли."),
    "en": dict(tab="📒 Paper", title="Paper portfolio: Retest, RS-first",
               note="Virtual $10,000 account, no broker. Signals are recorded after the close, "
                    "bought at the next open, stop 3% under the level, exit after 20 days.",
               empty="The paper portfolio hasn't started yet — it appears after the first paper_run.py.",
               ret="Return", spy="SPY same period", dd="Max drawdown", pf="Profit factor",
               exp="Expectancy", trades="Trades", win="Winners", cur_dd="Current drawdown",
               eq="Equity vs SPY", ddc="Drawdown, %", pos="Open positions",
               pend="Orders for the next session", led="Closed trades",
               sig="Signals of the last session", orders="Order log", none="—",
               updated="Updated: {u} · data as of {d}",
               fwd="**Forward only:** trades from signals recorded before the session open. "
                   "Started {s}. Late signals stored but not traded: {late}.",
               bf="⚠️ Reconstructed history (backfill) — NOT forward results",
               bf_note="Recomputed after the fact from historical data. Kept separate from "
                       "the forward portfolio; not a trading result."),
}


def _fmt(v, f="{:+.1f}%"):
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def render(lang="ru"):
    X = TX[lang]
    st.subheader(X["title"])
    st.caption(X["note"])
    state = store.load_state(store.STATE_FILE)
    if not state or not state.get("equity") or state.get("kind") != "forward":
        st.info(X["empty"])
        _backfill(X)
        return
    late = sum(o.get("outcome") == "not_traded_late" for o in state.get("orders_log", []))
    st.markdown(X["fwd"].format(s=state.get("start"), late=late))
    init = state["config"]["initial_cash"]
    eq = pd.DataFrame(state["equity"])
    eq["date"] = pd.to_datetime(eq["date"])
    led = pd.DataFrame(state["ledger"])
    m = pm.performance(eq, led, init)
    try:
        summ = json.loads((store.STATE_DIR / "summary.json").read_text())
        st.caption(X["updated"].format(u=summ.get("updated", "?"), d=summ.get("data_date", "?")))
    except Exception:
        pass

    c = st.columns(4)
    c[0].metric(X["ret"], _fmt(m["return_pct"]), f"${m['final_equity']:,.0f}", delta_color="off")
    c[1].metric(X["spy"], _fmt(m["spy_return_pct"]))
    c[2].metric(X["dd"], _fmt(m["max_drawdown_pct"]), _fmt(m["current_drawdown_pct"]),
                delta_color="off")
    c[3].metric(X["pf"], _fmt(m["profit_factor"], "{:.2f}"))
    c = st.columns(4)
    c[0].metric(X["exp"], _fmt(m["expectancy_r"], "{:+.2f}R"),
                _fmt(m["expectancy_usd"], "${:+.0f}"), delta_color="off")
    c[1].metric(X["trades"], m["trades"])
    c[2].metric(X["win"], _fmt(m["win_rate_pct"], "{:.0f}%"))
    c[3].metric(X["cur_dd"], _fmt(m["current_drawdown_pct"]))

    spy = pm.spy_curve(eq, init)
    fig = go.Figure()
    fig.add_scatter(x=eq["date"], y=eq["equity"], name="Paper", line=dict(color="#9B5CF0", width=2))
    fig.add_scatter(x=eq["date"], y=spy, name="SPY", line=dict(color="#8A8AA0", width=1.5,
                                                               dash="dot"))
    fig.update_layout(height=300, title=X["eq"], margin=dict(l=8, r=8, t=36, b=8),
                      paper_bgcolor="#0B0B12", plot_bgcolor="#0B0B12", font=dict(color="#EDEDF5"),
                      legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    dd = pm.drawdown(eq["equity"], init)
    fig2 = go.Figure(go.Scatter(x=eq["date"], y=dd, fill="tozeroy",
                                line=dict(color="#E5484D", width=1)))
    fig2.update_layout(height=180, title=X["ddc"], margin=dict(l=8, r=8, t=36, b=8),
                       paper_bgcolor="#0B0B12", plot_bgcolor="#0B0B12",
                       font=dict(color="#EDEDF5"))
    st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})

    st.markdown(f"**{X['pos']}**")
    pos = pd.DataFrame(list(state["positions"].values()))
    if len(pos):
        lp = state["last_prices"]
        pos["last"] = pos["ticker"].map(lp)
        pos["unrealized"] = (pos["last"] - pos["entry"]) * pos["qty"]
        st.dataframe(pos[["ticker", "signal_date", "entry_date", "entry", "stop", "qty",
                          "bars_held", "last", "unrealized", "rs"]].round(2),
                     hide_index=True, use_container_width=True)
    else:
        st.write(X["none"])
    st.markdown(f"**{X['pend']}**")
    pend = pd.DataFrame(state["pending"])
    st.dataframe(pend[["ticker", "rank", "rs", "stop", "signal_date", "scheduled_for",
                       "generated_at", "late"]].round(2) if len(pend) else pend,
                 hide_index=True, use_container_width=True)
    st.markdown(f"**{X['led']}**")
    if len(led):
        st.dataframe(led.iloc[::-1][["ticker", "entry_date", "exit_date", "entry", "exit",
                                     "shares", "reason", "net_pnl", "net_r"]].round(2),
                     hide_index=True, use_container_width=True)
    else:
        st.write(X["none"])
    if store.SIGNALS_FILE.exists():
        sig = pd.read_csv(store.SIGNALS_FILE)
        if len(sig):
            last = sig[sig["signal_date"] == sig["signal_date"].max()]
            st.markdown(f"**{X['sig']}** ({last['signal_date'].iloc[0]})")
            st.dataframe(last[["ticker", "rank", "rs", "eligible", "close", "level", "stop",
                               "sector", "generated_at"]].round(2),
                         hide_index=True, use_container_width=True)
    with st.expander(X["orders"]):
        st.dataframe(pd.DataFrame(state["orders_log"]).iloc[::-1].head(200),
                     hide_index=True, use_container_width=True)
    _backfill(X)


def _backfill(X):
    """Reconstructed history, if any — separate section, never mixed with forward numbers."""
    bf = store.load_state(store.paths("backfill")["state_file"])
    if not bf or bf.get("kind") != "backfill" or not bf.get("equity"):
        return
    with st.expander(X["bf"], expanded=False):
        st.warning(X["bf_note"])
        eq = pd.DataFrame(bf["equity"])
        m = pm.performance(eq, pd.DataFrame(bf["ledger"]), bf["config"]["initial_cash"])
        st.dataframe(pd.DataFrame([{k: m[k] for k in ("return_pct", "max_drawdown_pct",
                                                      "profit_factor", "expectancy_r",
                                                      "trades", "spy_return_pct")}]).round(2),
                     hide_index=True, use_container_width=True)
        st.line_chart(eq.set_index("date")["equity"])
