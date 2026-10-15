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
               ret="Доходность", spy="SPY (только цена)", dd="Макс. просадка", pf="Profit factor",
               exp="Ожидание", trades="Сделок", win="В плюсе", cur_dd="Текущая просадка",
               eq="Капитал против SPY", ddc="Просадка, %", pos="Открытые позиции",
               pend="Ордера на следующую сессию", led="Закрытые сделки", sig="Сигналы последней сессии",
               orders="Журнал ордеров", none="—", updated="Обновлено: {u} · данные на {d}",
               exp_id="Эксперимент {e} · начало {s} · отпечаток стратегии {f}",
               gen="Настоящий форвард (портфель целиком)",
               gen_ok="Все исполнения обработаны вовремя — показатели портфеля настоящие.",
               gen_cut="С {since} есть реконструированные исполнения. Показатели портфеля ниже "
                       "заморожены на {thr}; после этой даты настоящий форвард-результат "
                       "портфеля недоступен.",
               gen_na="Реконструированные исполнения с {since}, с самого начала — показатели "
                      "настоящего форвард-портфеля недоступны.",
               cats="Исполнения по категориям", cat="Категория",
               catA="A — вовремя", catB="B — реконструировано (вход или выход позже)",
               catC="C — опоздавшие сигналы, не торговались", n_closed="Закрыто",
               n_open="Открыто",
               trade_note="Показатели по сделкам — это статистика сделок, а не доходность "
                          "портфеля. SPY — только цена, без дивидендов.",
               obs="⚠️ Наблюдаемый портфель — содержит реконструированные исполнения",
               obs_clean="Наблюдаемый портфель", obs_line="Наблюдаемый капитал",
               obs_warn="Эта кривая включает реконструированные исполнения и НЕ является "
                        "форвард-результатом. Красная линия — начало реконструкции.",
               bf="⚠️ Реконструкция истории (backfill) — НЕ форвард-результат",
               bf_note="Пересчитано задним числом по историческим данным. Не смешивается с "
                       "форвард-портфелем и не является результатом торговли."),
    "en": dict(tab="📒 Paper", title="Paper portfolio: Retest, RS-first",
               note="Virtual $10,000 account, no broker. Signals are recorded after the close, "
                    "bought at the next open, stop 3% under the level, exit after 20 days.",
               empty="The paper portfolio hasn't started yet — it appears after the first paper_run.py.",
               ret="Return", spy="SPY (price only)", dd="Max drawdown", pf="Profit factor",
               exp="Expectancy", trades="Trades", win="Winners", cur_dd="Current drawdown",
               eq="Equity vs SPY", ddc="Drawdown, %", pos="Open positions",
               pend="Orders for the next session", led="Closed trades",
               sig="Signals of the last session", orders="Order log", none="—",
               updated="Updated: {u} · data as of {d}",
               exp_id="Experiment {e} · started {s} · strategy fingerprint {f}",
               gen="Genuine forward (whole portfolio)",
               gen_ok="All executions were processed on time — portfolio metrics are genuine.",
               gen_cut="Reconstructed executions since {since}. Portfolio metrics below are frozen "
                       "at {thr}; after that date the genuine-forward portfolio result is "
                       "unavailable.",
               gen_na="Reconstructed executions since {since}, from the start — genuine-forward "
                      "portfolio metrics are unavailable.",
               cats="Executions by category", cat="Category",
               catA="A — timely", catB="B — reconstructed (late entry or exit)",
               catC="C — late signals, never traded", n_closed="Closed", n_open="Open",
               trade_note="Category figures are trade-level statistics, not a portfolio return. "
                          "SPY is price-only (dividends excluded).",
               obs="⚠️ Observed portfolio — contains reconstructed executions",
               obs_clean="Observed portfolio", obs_line="Observed equity",
               obs_warn="This curve includes reconstructed executions and is NOT a forward "
                        "result. The red line marks the first reconstruction.",
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
    init = state["config"]["initial_cash"]
    eq = pd.DataFrame(state["equity"])
    eq["date"] = pd.to_datetime(eq["date"])
    R = pm.forward_report(state)
    g = R["genuine_forward"]
    try:
        summ = json.loads((store.STATE_DIR / "summary.json").read_text())
        st.caption(X["updated"].format(u=summ.get("updated", "?"), d=summ.get("data_date", "?")))
    except Exception:
        pass
    st.caption(X["exp_id"].format(e=state.get("experiment"), s=state.get("start"),
                                  f=(state.get("code_fingerprint") or {}).get("combined")))

    # ---- headline: genuine-forward portfolio only
    st.markdown(f"#### {X['gen']}")
    gm = g["metrics"]
    if g["available"] and gm:
        st.success(X["gen_ok"])
    elif gm:
        st.error(X["gen_cut"].format(since=g["contaminated_since"], thr=g["genuine_through"]))
    else:
        st.error(X["gen_na"].format(since=g["contaminated_since"]))
    if gm:
        c = st.columns(4)
        c[0].metric(X["ret"], _fmt(gm["return_pct"]), f"${gm['final_equity']:,.0f}",
                    delta_color="off")
        c[1].metric(X["spy"], _fmt(gm["spy_price_return_pct"]))
        c[2].metric(X["dd"], _fmt(gm["max_drawdown_pct"]))
        c[3].metric("CAGR", _fmt(gm["cagr_pct"]))

    # ---- A / B / C
    st.markdown(f"#### {X['cats']}")
    A, B, C = R["timely"], R["reconstructed"], R["late_not_traded"]
    cats = pd.DataFrame([
        {X["cat"]: X["catA"], X["n_closed"]: A["trades"]["closed"], X["n_open"]: A["open_positions"],
         "PF": A["trades"]["profit_factor"], X["exp"]: A["trades"]["expectancy_r"],
         X["win"]: A["trades"]["win_rate_pct"], "P&L $": A["trades"]["total_pnl_usd"]},
        {X["cat"]: X["catB"], X["n_closed"]: B["trades"]["closed"], X["n_open"]: B["open_positions"],
         "PF": B["trades"]["profit_factor"], X["exp"]: B["trades"]["expectancy_r"],
         X["win"]: B["trades"]["win_rate_pct"], "P&L $": B["trades"]["total_pnl_usd"]},
        {X["cat"]: X["catC"], X["n_closed"]: C["count"], X["n_open"]: 0, "PF": None,
         X["exp"]: None, X["win"]: None, "P&L $": None}])
    st.dataframe(cats.round(2), hide_index=True, use_container_width=True)
    st.caption(X["trade_note"])

    # ---- observed (may contain reconstructed executions)
    obs = R["observed_portfolio"]
    with st.expander(X["obs"] if obs["contains_reconstructed"] else X["obs_clean"],
                     expanded=not obs["contains_reconstructed"]):
        if obs["contains_reconstructed"]:
            st.warning(X["obs_warn"])
        spy = pm.spy_curve(eq, init)
        fig = go.Figure()
        fig.add_scatter(x=eq["date"], y=eq["equity"], name=X["obs_line"],
                        line=dict(color="#9B5CF0", width=2))
        fig.add_scatter(x=eq["date"], y=spy, name="SPY (price only)",
                        line=dict(color="#8A8AA0", width=1.5, dash="dot"))
        if g["contaminated_since"]:
            fig.add_vline(x=pd.Timestamp(g["contaminated_since"]), line_color="#E5484D",
                          line_dash="dash")
        fig.update_layout(height=300, title=X["eq"], margin=dict(l=8, r=8, t=36, b=8),
                          paper_bgcolor="#0B0B12", plot_bgcolor="#0B0B12",
                          font=dict(color="#EDEDF5"), legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        dd = pm.drawdown(eq["equity"], init)
        fig2 = go.Figure(go.Scatter(x=eq["date"], y=dd, fill="tozeroy",
                                    line=dict(color="#E5484D", width=1)))
        fig2.update_layout(height=180, title=X["ddc"], margin=dict(l=8, r=8, t=36, b=8),
                           paper_bgcolor="#0B0B12", plot_bgcolor="#0B0B12",
                           font=dict(color="#EDEDF5"))
        st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})
    led = pd.DataFrame(state["ledger"])

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
                                                      "trades", "spy_price_return_pct")}]).round(2),
                     hide_index=True, use_container_width=True)
        st.line_chart(eq.set_index("date")["equity"])
