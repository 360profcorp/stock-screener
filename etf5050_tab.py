"""'⚖️ 50/50' tab — read-only view of the 50 % SPY / 50 % BIL paper book (paper/etf5050/).
No broker connection, no orders."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import paper_etf as P

TX = {
    "ru": dict(tab="⚖️ 50/50", title="Бумажный портфель: 50% SPY / 50% BIL",
               note="Виртуальный счёт $10 000 без брокера. Пропорции 50/50 восстанавливаются раз в месяц: "
                    "решение после последней сессии месяца, исполнение на открытии следующей. "
                    "Без MA, RS, стопов и выхода через 20 дней.",
               risk="Просадка −20% — ориентир оценки риска, а не гарантированный ограничитель потерь.",
               empty="Книга ещё не активирована — она появится после первого запуска etf5050_run.py.",
               ret="Доходность", eq_now="Капитал", dd="Макс. просадка", cur_dd="Текущая просадка",
               fees="Комиссии", divs="Дивиденды получено", cash="Деньги", rec="Дивиденды к получению",
               pos="Позиции", weights="Текущие доли", eqc="Капитал", ddc="Просадка, %",
               rebal="Журнал ребалансировок", fills="Исполнения", dlog="Дивиденды", pend="Ордера на следующую сессию",
               none="—", act="Активация {a} · данные на {d} · обновлено {u}",
               late="⚠️ Есть реконструированные (обработанные с опозданием) исполнения: {n}",
               cagr="CAGR (после года истории)"),
    "en": dict(tab="⚖️ 50/50", title="Paper portfolio: 50% SPY / 50% BIL",
               note="Virtual $10,000 account, no broker. Rebalanced to 50/50 monthly: decided after the "
                    "last session of the month, executed at the next session's open. No MA, RS, stops "
                    "or 20-day exit.",
               risk="The −20% drawdown is a risk-evaluation reference, not a guaranteed loss limit.",
               empty="The book is not activated yet — it appears after the first etf5050_run.py run.",
               ret="Return", eq_now="Equity", dd="Max drawdown", cur_dd="Current drawdown",
               fees="Fees", divs="Dividends received", cash="Cash", rec="Dividends receivable",
               pos="Positions", weights="Current weights", eqc="Equity", ddc="Drawdown, %",
               rebal="Rebalance log", fills="Fills", dlog="Dividends", pend="Orders for the next session",
               none="—", act="Activated {a} · data as of {d} · updated {u}",
               late="⚠️ Reconstructed (late-processed) fills: {n}",
               cagr="CAGR (after one year of history)"),
}


def _f(v, f="{:+.2f}%"):
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def render(lang="ru"):
    X = TX[lang]
    st.subheader(X["title"])
    st.caption(X["note"])
    st.caption(X["risk"])
    s = P.load()
    if not s or not s.get("equity"):
        st.info(X["empty"])
        return
    S = P.summary(s)
    st.caption(X["act"].format(a=s["activation_session"], d=s.get("data_date"), u=s.get("updated_at")))
    if S["late_fills"]:
        st.warning(X["late"].format(n=S["late_fills"]))
    c = st.columns(4)
    c[0].metric(X["ret"], _f(S.get("return_pct")), f"${S.get('equity', 0):,.2f}", delta_color="off")
    c[1].metric(X["dd"], _f(S.get("max_drawdown_pct")))
    c[2].metric(X["cur_dd"], _f(S.get("current_drawdown_pct")))
    c[3].metric(X["cagr"], _f(S.get("cagr_pct")))
    c = st.columns(4)
    c[0].metric(X["cash"], f"${s['cash']:,.2f}")
    c[1].metric(X["rec"], f"${S['receivables']:,.2f}")
    c[2].metric(X["divs"], f"${S['dividends_received']:,.2f}")
    c[3].metric(X["fees"], f"${S['fees_total']:,.2f}")

    eq = pd.DataFrame(s["equity"])
    eq["date"] = pd.to_datetime(eq["date"])
    last = eq.iloc[-1]
    st.markdown(f"**{X['pos']}**")
    pos = pd.DataFrame([dict(symbol=k, shares=s["shares"][k], last_close=last[f"{k}_close"],
                             value=last[f"{k}_value"], weight_pct=100 * (last[f"w_{k}"] or 0))
                        for k in P.SYMS])
    st.dataframe(pos.round(2), hide_index=True, use_container_width=True)
    st.markdown(f"**{X['weights']}**: SPY {100 * (last['w_SPY'] or 0):.1f}% · BIL {100 * (last['w_BIL'] or 0):.1f}% · "
                f"{X['cash']} {100 * last['cash'] / last['equity']:.1f}%")

    fig = go.Figure(go.Scatter(x=eq["date"], y=eq["equity"], line=dict(color="#9B5CF0", width=2)))
    fig.add_hline(y=s["config"]["initial_cash"], line_color="#8A8AA0", line_dash="dot")
    fig.update_layout(height=280, title=X["eqc"], margin=dict(l=8, r=8, t=36, b=8),
                      paper_bgcolor="#0B0B12", plot_bgcolor="#0B0B12", font=dict(color="#EDEDF5"))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    fig2 = go.Figure(go.Scatter(x=eq["date"], y=eq["drawdown_pct"], fill="tozeroy",
                                line=dict(color="#E5484D", width=1)))
    fig2.add_hline(y=s["config"]["risk_reference_dd_pct"], line_color="#F5A524", line_dash="dash")
    fig2.update_layout(height=180, title=X["ddc"], margin=dict(l=8, r=8, t=36, b=8),
                       paper_bgcolor="#0B0B12", plot_bgcolor="#0B0B12", font=dict(color="#EDEDF5"))
    st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})

    st.markdown(f"**{X['pend']}**")
    pend = pd.DataFrame(s["pending"])
    st.dataframe(pend if len(pend) else pd.DataFrame({X["none"]: []}), hide_index=True, use_container_width=True)
    st.markdown(f"**{X['rebal']}**")
    rb = pd.DataFrame(s["rebalances"])
    st.dataframe(rb.iloc[::-1] if len(rb) else pd.DataFrame({X["none"]: []}), hide_index=True,
                 use_container_width=True)
    with st.expander(X["fills"]):
        fl = pd.DataFrame(s["fills"])
        st.dataframe(fl.iloc[::-1].round(4) if len(fl) else pd.DataFrame({X["none"]: []}), hide_index=True,
                     use_container_width=True)
    with st.expander(X["dlog"]):
        dv = pd.DataFrame(s["dividends"])
        st.dataframe(dv.iloc[::-1].round(4) if len(dv) else pd.DataFrame({X["none"]: []}), hide_index=True,
                     use_container_width=True)
