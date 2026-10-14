"""
VISAR · S&P 500 Screener — web app (Streamlit).
Breakouts, breakout + retest, VCP, RS filter, stops & position sizing, chart on tap,
signal journal fed by the daily auto-scan (daily_scan.py on GitHub Actions). RU / EN.
Run locally:  streamlit run app.py
Not investment advice. / Не является инвестиционной рекомендацией.
"""
import base64
import io
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots
from PIL import Image

import brand
import core
from core import MODES, NY

st.set_page_config(page_title="VISAR · S&P 500 Screener",
                   page_icon=Image.open(io.BytesIO(base64.b64decode(brand.ICON_B64))),
                   layout="centered")

JOURNAL_FILE = Path(__file__).parent / "journal" / "signals.csv"
JOURNAL_URL = ("https://raw.githubusercontent.com/360profcorp/stock-screener/"
               "main/journal/signals.csv")
BRAND_COLORS = ["#36C2C9", "#4E7CF0", "#9B5CF0", "#E0679E"]

BRAND_CSS = """
<style>
.visar-header { display:flex; justify-content:center; margin: 0.2rem 0 0.4rem; }
.visar-header img { height: 64px; max-width: 90%; object-fit: contain; }
.visar-bar { height: 3px; border-radius: 3px; margin: 0 0 1rem;
  background: linear-gradient(90deg, #36C2C9, #4E7CF0, #9B5CF0, #E0679E); }
h1 { text-align: center; font-size: 1.6rem !important; padding-top: 0 !important; }
div[data-testid="stCaptionContainer"] { text-align: center; }
.stButton > button[kind="primary"] {
  background: linear-gradient(90deg, #36C2C9, #4E7CF0, #9B5CF0, #E0679E);
  border: none; color: #fff; font-weight: 600; }
.stButton > button[kind="primary"]:hover { filter: brightness(1.12); color:#fff; }
</style>
"""

# =====================================================================
# Тексты интерфейса / UI strings
# =====================================================================
TEXT = {
    "ru": {
        "title": "Скринер S&P 500",
        "subtitle": "Пробои, ретесты и VCP среди лидеров рынка · данные Yahoo Finance",
        "signal_type": "Тип сигнала",
        "mode_breakout": "Пробой",
        "mode_retest": "Пробой с ретестом",
        "mode_vcp": "VCP",
        "desc_breakout": "Закрытие дня выше максимума последних 2–3 свечей.",
        "desc_retest": "Пробой был несколько дней назад, цена вернулась к уровню, "
                       "удержала его и сегодня пошла вверх.",
        "desc_vcp": "Восходящий тренд, сужающиеся коррекции, подсыхающий объём, "
                    "цена у верхушки базы (упрощённая версия по Минервини).",
        "settings": "⚙️ Настройки сигнала",
        "risk_settings": "💰 Риск и размер позиции",
        "lookback": "Сколько свечей пробивать",
        "min_rs": "Мин. относительная сила (RS)",
        "min_rs_help": "Перцентиль среди акций S&P 500. 70 — сильнее 70% рынка. "
                       "Минервини обычно берёт 80+. 0 — без фильтра.",
        "min_vol": "Мин. объём к среднему за 20 дней",
        "min_vol_help": "1.5 = объём в 1.5 раза выше среднего. 0 — без фильтра.",
        "closed_only": "Только закрытые свечи (во время торгов берётся вчерашняя)",
        "sectors": "Секторы (пусто — все)",
        "account": "Размер счёта, $",
        "risk_pct": "Риск на сделку, % от счёта",
        "stop_buf": "Запас стопа под уровнем, %",
        "stop_help": "Пробой и ретест: стоп ниже пробитого уровня (или минимума отката) "
                     "на этот процент. VCP: ниже минимума последней коррекции.",
        "max_risk": "Макс. риск до стопа, % (0 — без фильтра)",
        "max_risk_help": "Скрыть акции, где стоп дальше этого процента от цены — "
                         "слишком широкий стоп.",
        "scan": "🔍 Сканировать",
        "loading": "Загружаю S&P 500 и котировки… первый раз ~1 мин",
        "found": "Найдено",
        "scanned_at": "Скан",
        "empty": "Сигналов по заданным условиям нет. Попробуй снизить RS или убрать фильтры.",
        "download": "⬇️ Скачать CSV",
        "refresh": "🔄 Обновить котировки (сбросить кэш)",
        "refreshed": "Кэш очищен — нажми «Сканировать»",
        "hint": "Выбери тип сигнала и нажми **Сканировать**.",
        "sizing_note": "Акций = риск на сделку ÷ (цена − стоп), но не больше, чем позволяет счёт.",
        "footer": "Сигналы — стартовый список для ручной проверки графика. "
                  "Не является инвестиционной рекомендацией.",
        "tab_scan": "🔍 Скан",
        "tab_journal": "📒 Журнал",
        "tap_row": "👆 Нажми на строку в таблице — откроется график.",
        "chart_level": "Уровень", "chart_stop": "Стоп", "chart_volume": "Объём",
        "chart_close": "Закрыть график",
        "j_intro": "Автоскан каждый будний день после закрытия рынка (~18:15 по Нью-Йорку) "
                   "записывает все сигналы сюда и присылает пуш на телефон. "
                   "Здесь видно, как они отработали.",
        "j_empty": "Журнал пока пуст. Первая запись появится после первого автоскана. "
                   "Запустить сразу: GitHub → Actions → Daily scan → Run workflow.",
        "j_all": "Все",
        "j_loading": "Считаю результаты сигналов…",
        "j_summary": "Итоги по типам сигналов",
        "j_details": "Все сигналы",
        "j_note": "Результат считается от цены закрытия в день сигнала. "
                  "Если цена коснулась стопа — сделка считается закрытой по стопу.",
        "j_cols": {"mode": "Тип", "signals": "Сигналов", "win_5d": "Плюс через 5д, %",
                   "avg_5d": "Средн. 5д, %", "win_10d": "Плюс через 10д, %",
                   "avg_10d": "Средн. 10д, %", "stopped": "Выбило по стопу, %",
                   "date": "Дата", "ticker": "Тикер", "rs": "RS", "close": "Вход",
                   "stop": "Стоп", "ret_5d": "5 дней", "ret_10d": "10 дней",
                   "ret_now": "Сейчас", "max_up": "Макс. рост", "status": "Статус",
                   "days": "Дней"},
        "status": {"new": "🆕 сегодня", "open": "⏳ в работе", "done10": "✅ 10 дней прошло",
                   "stopped": "🛑 стоп", "nodata": "— нет данных"},
        "cols": {
            "ticker": "Тикер", "rs": "RS", "name": "Компания", "sector": "Сектор",
            "close": "Закрытие", "level": "Уровень", "pct_level": "% от уровня",
            "stop": "Стоп", "risk_pct": "Риск %", "shares": "Акций",
            "pos_value": "Позиция $", "vol_ratio": "Объём / ср.20д",
            "signal": "Сигнал", "date": "Дата", "chart": "График",
        },
    },
    "en": {
        "title": "S&P 500 Screener",
        "subtitle": "Breakouts, retests and VCPs among market leaders · Yahoo Finance data",
        "signal_type": "Signal type",
        "mode_breakout": "Breakout",
        "mode_retest": "Breakout + retest",
        "mode_vcp": "VCP",
        "desc_breakout": "Daily close above the high of the last 2–3 candles.",
        "desc_retest": "Broke out a few days ago, pulled back to the level, "
                       "held it and turned up today.",
        "desc_vcp": "Uptrend, contracting pullbacks, drying volume, "
                    "price near the top of the base (simplified Minervini VCP).",
        "settings": "⚙️ Signal settings",
        "risk_settings": "💰 Risk & position size",
        "lookback": "Candles to break",
        "min_rs": "Min. relative strength (RS)",
        "min_rs_help": "Percentile among S&P 500 stocks. 70 = stronger than 70% of the market. "
                       "Minervini usually wants 80+. 0 = no filter.",
        "min_vol": "Min. volume vs 20-day average",
        "min_vol_help": "1.5 = volume 1.5× above average. 0 = no filter.",
        "closed_only": "Closed candles only (during market hours uses yesterday)",
        "sectors": "Sectors (empty = all)",
        "account": "Account size, $",
        "risk_pct": "Risk per trade, % of account",
        "stop_buf": "Stop buffer below level, %",
        "stop_help": "Breakout & retest: stop this % below the broken level (or pullback low). "
                     "VCP: below the low of the last contraction.",
        "max_risk": "Max. risk to stop, % (0 = no filter)",
        "max_risk_help": "Hide stocks whose stop is farther than this % from price — "
                         "stop too wide.",
        "scan": "🔍 Scan",
        "loading": "Loading S&P 500 and quotes… ~1 min the first time",
        "found": "Found",
        "scanned_at": "Scanned",
        "empty": "No signals for these settings. Try lowering RS or removing filters.",
        "download": "⬇️ Download CSV",
        "refresh": "🔄 Refresh quotes (clear cache)",
        "refreshed": "Cache cleared — press Scan",
        "hint": "Pick a signal type and press **Scan**.",
        "sizing_note": "Shares = risk per trade ÷ (price − stop), capped by account size.",
        "footer": "Signals are a starting list for manual chart review. Not investment advice.",
        "tab_scan": "🔍 Scan",
        "tab_journal": "📒 Journal",
        "tap_row": "👆 Tap a row in the table to open its chart.",
        "chart_level": "Level", "chart_stop": "Stop", "chart_volume": "Volume",
        "chart_close": "Close chart",
        "j_intro": "The auto-scan runs every weekday after the close (~6:15 PM New York), "
                   "logs every signal here and sends a push to your phone. "
                   "This tab shows how they played out.",
        "j_empty": "The journal is empty. The first entries appear after the first auto-scan. "
                   "To run it now: GitHub → Actions → Daily scan → Run workflow.",
        "j_all": "All",
        "j_loading": "Calculating signal results…",
        "j_summary": "Results by signal type",
        "j_details": "All signals",
        "j_note": "Returns are measured from the close on the signal day. "
                  "If price touched the stop, the trade counts as stopped out.",
        "j_cols": {"mode": "Type", "signals": "Signals", "win_5d": "Up after 5d, %",
                   "avg_5d": "Avg 5d, %", "win_10d": "Up after 10d, %",
                   "avg_10d": "Avg 10d, %", "stopped": "Stopped out, %",
                   "date": "Date", "ticker": "Ticker", "rs": "RS", "close": "Entry",
                   "stop": "Stop", "ret_5d": "5 days", "ret_10d": "10 days",
                   "ret_now": "Now", "max_up": "Max run-up", "status": "Status",
                   "days": "Days"},
        "status": {"new": "🆕 today", "open": "⏳ running", "done10": "✅ 10 days done",
                   "stopped": "🛑 stopped", "nodata": "— no data"},
        "cols": {
            "ticker": "Ticker", "rs": "RS", "name": "Company", "sector": "Sector",
            "close": "Close", "level": "Level", "pct_level": "% vs level",
            "stop": "Stop", "risk_pct": "Risk %", "shares": "Shares",
            "pos_value": "Position $", "vol_ratio": "Vol / 20d avg",
            "signal": "Signal", "date": "Date", "chart": "Chart",
        },
    },
}


# =====================================================================
# Кэш данных / cached data
# =====================================================================
@st.cache_data(ttl=24 * 3600, show_spinner=False)
def get_sp500():
    return core.get_sp500()


@st.cache_data(ttl=15 * 60, show_spinner=False)
def get_prices(tickers: tuple):
    return core.get_prices(tickers)


@st.cache_data(ttl=60 * 60, show_spinner=False)
def get_prices_since(tickers: tuple, start: str):
    return core.get_prices(tickers, start=start)


@st.cache_data(ttl=10 * 60, show_spinner=False)
def load_journal():
    """Journal written by the daily auto-scan: repo file first, GitHub raw as a fallback."""
    for src in (JOURNAL_FILE, JOURNAL_URL):
        try:
            j = pd.read_csv(src)
            if not j.empty:
                return j
        except Exception:
            continue
    return pd.DataFrame(columns=core.JOURNAL_COLS)


# =====================================================================
# График / chart
# =====================================================================
def price_chart(df, ticker, level, stop, T, bars=130):
    df = df.dropna(subset=["Close"])
    c = df["Close"]
    mas = {n: c.rolling(n).mean() for n in (50, 150, 200)}
    d = df.iloc[-bars:]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.76, 0.24],
                        vertical_spacing=0.03)
    fig.add_trace(go.Candlestick(
        x=d.index, open=d["Open"], high=d["High"], low=d["Low"], close=d["Close"],
        increasing_line_color="#36C2C9", decreasing_line_color="#E0679E",
        increasing_fillcolor="#36C2C9", decreasing_fillcolor="#E0679E",
        name=ticker, showlegend=False), row=1, col=1)
    for n, color in zip((50, 150, 200), ("#4E7CF0", "#9B5CF0", "#8A8AA0")):
        fig.add_trace(go.Scatter(x=d.index, y=mas[n].iloc[-bars:], name=f"MA{n}",
                                 line=dict(color=color, width=1.3)), row=1, col=1)
    fig.add_hline(y=level, line=dict(color="#EDEDF5", width=1, dash="dash"), row=1, col=1,
                  annotation_text=f"{T['chart_level']} {level:.2f}",
                  annotation_position="top left", annotation_font_color="#EDEDF5")
    fig.add_hline(y=stop, line=dict(color="#E0679E", width=1.2, dash="dot"), row=1, col=1,
                  annotation_text=f"{T['chart_stop']} {stop:.2f}",
                  annotation_position="bottom left", annotation_font_color="#E0679E")
    up = d["Close"] >= d["Open"]
    fig.add_trace(go.Bar(x=d.index, y=d["Volume"], name=T["chart_volume"], showlegend=False,
                         marker_color=np.where(up, "#36C2C9", "#E0679E"), opacity=0.6),
                  row=2, col=1)
    fig.update_layout(
        height=470, margin=dict(l=8, r=8, t=36, b=8),
        title=dict(text=ticker, x=0.02, font=dict(size=16)),
        paper_bgcolor="#0B0B12", plot_bgcolor="#0B0B12", font=dict(color="#EDEDF5"),
        legend=dict(orientation="h", y=1.06, x=1, xanchor="right", font=dict(size=11)),
        xaxis_rangeslider_visible=False, dragmode="pan")
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])], gridcolor="#1E1E2C")
    fig.update_yaxes(gridcolor="#1E1E2C", side="right")
    return fig


# =====================================================================
# Вкладка «Скан» / Scan tab
# =====================================================================
def scan_tab(T, lang):
    mode = st.segmented_control(T["signal_type"], MODES, default="breakout",
                                format_func=lambda m: T[f"mode_{m}"], key="mode") or "breakout"
    st.caption(T[f"desc_{mode}"])

    with st.expander(T["settings"], expanded=False):
        lookback = st.radio(T["lookback"], [2, 3], index=1, horizontal=True,
                            disabled=(mode == "vcp"), key="lookback")
        min_rs = st.slider(T["min_rs"], 0, 99, 70, help=T["min_rs_help"], key="min_rs")
        min_vol_ratio = st.slider(T["min_vol"], 0.0, 3.0, 0.0, 0.1,
                                  help=T["min_vol_help"], key="min_vol")
        drop_unclosed = st.checkbox(T["closed_only"], value=True, key="closed_only")
        sectors_all = sorted(get_sp500()["sector"].dropna().unique())
        sectors = st.multiselect(T["sectors"], sectors_all, key="sectors")

    with st.expander(T["risk_settings"], expanded=False):
        account = st.number_input(T["account"], min_value=100.0, value=10_000.0,
                                  step=1_000.0, format="%.0f", key="account")
        risk_pct = st.number_input(T["risk_pct"], min_value=0.1, max_value=10.0,
                                   value=1.0, step=0.25, key="risk_pct")
        stop_buf = st.slider(T["stop_buf"], 0.0, 5.0, 1.0, 0.25,
                             help=T["stop_help"], key="stop_buf")
        max_risk = st.slider(T["max_risk"], 0.0, 15.0, 0.0, 0.5,
                             help=T["max_risk_help"], key="max_risk")
        st.caption(T["sizing_note"])

    if st.button(T["scan"], type="primary", use_container_width=True):
        with st.spinner(T["loading"]):
            universe = get_sp500()
            tickers = tuple(universe["ticker"])
            prices = get_prices(tickers)                  # RS uses the whole S&P 500
            result = core.scan(prices, universe, mode, lookback, drop_unclosed,
                               min_vol_ratio, min_rs, account, risk_pct, stop_buf, max_risk)
            if sectors and not result.empty:
                result = result[result["sector"].isin(sectors)].reset_index(drop=True)
        st.session_state.update(result=result, mode_scanned=mode, tickers=tickers,
                                scanned_at=datetime.now(NY).strftime("%d.%m %H:%M ET"))

    if "result" not in st.session_state:
        st.write(T["hint"])
        return

    res = st.session_state["result"]
    st.metric(f"{T['found']}: {T['mode_' + st.session_state['mode_scanned']]}", len(res),
              help=f"{T['scanned_at']}: {st.session_state['scanned_at']}")
    if res.empty:
        st.info(T["empty"])
    else:
        C = T["cols"]
        other = "en" if lang == "ru" else "ru"
        view = (res.drop(columns=[f"signal_{other}"])
                   .rename(columns={f"signal_{lang}": "signal"})
                   .rename(columns=C))
        st.caption(T["tap_row"])
        event = st.dataframe(
            view, hide_index=True, use_container_width=True,
            on_select="rerun", selection_mode="single-row", key="scan_table",
            column_config={
                C["ticker"]: st.column_config.TextColumn(pinned=True),
                C["rs"]: st.column_config.ProgressColumn(C["rs"], min_value=0,
                                                         max_value=99, format="%d"),
                C["chart"]: st.column_config.LinkColumn(C["chart"], display_text="TradingView"),
                C["pct_level"]: st.column_config.NumberColumn(format="%.2f%%"),
                C["risk_pct"]: st.column_config.NumberColumn(format="%.2f%%"),
                C["pos_value"]: st.column_config.NumberColumn(format="$%d"),
                C["vol_ratio"]: st.column_config.NumberColumn(format="%.2fx"),
            },
        )
        rows = event.selection.rows if event and hasattr(event, "selection") else []
        if rows:
            r = res.iloc[rows[0]]
            prices = get_prices(st.session_state["tickers"])
            df = core._frame_for(prices, r["ticker"])
            if df is not None and len(df):
                st.plotly_chart(price_chart(df, r["ticker"], r["level"], r["stop"], T),
                                use_container_width=True,
                                config={"displayModeBar": False, "scrollZoom": False})
        st.download_button(T["download"], view.to_csv(index=False).encode("utf-8"),
                           "signals.csv", "text/csv", use_container_width=True)
    if st.button(T["refresh"], use_container_width=True):
        get_prices.clear()
        st.toast(T["refreshed"])


# =====================================================================
# Вкладка «Журнал» / Journal tab
# =====================================================================
def journal_tab(T):
    st.caption(T["j_intro"])
    journal = load_journal()
    if journal.empty:
        st.info(T["j_empty"])
        return

    modes = [T["j_all"]] + [T[f"mode_{m}"] for m in MODES]
    pick = st.segmented_control(T["signal_type"], modes, default=T["j_all"],
                                key="j_mode") or T["j_all"]
    if pick != T["j_all"]:
        code = MODES[modes.index(pick) - 1]
        journal = journal[journal["mode"] == code]
        if journal.empty:
            st.info(T["j_empty"])
            return

    start = (pd.to_datetime(journal["date"]).min() - timedelta(days=7)).strftime("%Y-%m-%d")
    with st.spinner(T["j_loading"]):
        prices = get_prices_since(tuple(sorted(journal["ticker"].unique())), start)
        ev = core.evaluate_journal(journal, prices)

    J = T["j_cols"]
    st.subheader(T["j_summary"])
    summ = core.journal_summary(ev)
    summ["mode"] = summ["mode"].map(lambda m: T[f"mode_{m}"])
    st.dataframe(summ.round(1).rename(columns=J), hide_index=True, use_container_width=True)

    st.subheader(T["j_details"])
    det = ev[["date", "mode", "ticker", "rs", "close", "stop", "ret_5d", "ret_10d",
              "ret_now", "max_up", "status"]].copy()
    for col in ("ret_5d", "ret_10d", "ret_now", "max_up"):
        det[col] = det[col] * 100
    det["mode"] = det["mode"].map(lambda m: T[f"mode_{m}"])
    det["status"] = det["status"].map(T["status"])
    pct = st.column_config.NumberColumn(format="%.1f%%")
    st.dataframe(det.rename(columns=J), hide_index=True, use_container_width=True,
                 column_config={J["ticker"]: st.column_config.TextColumn(pinned=True),
                                J["ret_5d"]: pct, J["ret_10d"]: pct,
                                J["ret_now"]: pct, J["max_up"]: pct})
    st.caption(T["j_note"])


# =====================================================================
# Интерфейс / UI
# =====================================================================
def main():
    lang_label = st.segmented_control("Language", ["RU", "EN"], default="RU",
                                      key="lang", label_visibility="collapsed")
    lang = "en" if lang_label == "EN" else "ru"
    T = TEXT[lang]

    st.markdown(BRAND_CSS, unsafe_allow_html=True)
    st.markdown(f'<div class="visar-header"><img src="data:image/png;base64,{brand.HEADER_B64}" '
                f'alt="VISAR"></div><div class="visar-bar"></div>', unsafe_allow_html=True)
    st.title(T["title"])
    st.caption(T["subtitle"])

    tab_scan, tab_journal = st.tabs([T["tab_scan"], T["tab_journal"]])
    with tab_scan:
        scan_tab(T, lang)
    with tab_journal:
        journal_tab(T)

    st.caption(T["footer"])


if __name__ == "__main__":
    main()
