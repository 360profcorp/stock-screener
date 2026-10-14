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

import backtest as bt
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
        "j_intro": "Автоскан каждый будний день после закрытия рынка (~19:30 по Нью-Йорку) "
                   "записывает все сигналы сюда и присылает пуш на телефон. "
                   "Здесь видно, как они отработали.",
        "j_empty": "Журнал пока пуст. Первая запись появится после первого автоскана. "
                   "Запустить сразу: GitHub → Actions → Daily scan → Run workflow.",
        "j_all": "Все",
        "j_loading": "Считаю результаты сигналов…",
        "j_summary": "Итоги по типам сигналов",
        "j_details": "Все сигналы",
        "j_note": "Результат считается от цены закрытия в день сигнала. Если цена коснулась "
                  "стопа — сделка закрыта по стопу. Колонки 5д и 10д заполняются, только когда "
                  "прошло 5 / 10 торговых дней; «Прошло 5д» — по скольким сделкам это посчитано.",
        "j_cols": {"mode": "Тип", "signals": "Сигналов",
                   "win_now": "Сейчас в плюсе, %", "avg_now": "Средн. сейчас, %",
                   "stopped": "Выбило по стопу, %",
                   "n_5d": "Прошло 5д", "win_5d": "Плюс через 5д, %", "avg_5d": "Средн. 5д, %",
                   "n_10d": "Прошло 10д", "win_10d": "Плюс через 10д, %",
                   "avg_10d": "Средн. 10д, %",
                   "date": "Дата", "ticker": "Тикер", "rs": "RS", "close": "Вход",
                   "stop": "Стоп", "ret_5d": "5 дней", "ret_10d": "10 дней",
                   "ret_now": "Итог / сейчас", "max_up": "Макс. рост", "status": "Статус",
                   "days": "Дней"},
        "status": {"new": "🆕 сегодня", "open": "⏳ в работе", "done10": "✅ 10 дней прошло",
                   "stopped": "🛑 стоп", "nodata": "— нет данных"},
        "tab_bt": "🧪 Бэктест",
        "bt_intro": "Проверка трёх сетапов на истории S&P 500 примерно за 2 года по тем же правилам, "
                    "что и живой скан. Вход — по закрытию дня сигнала, выход — по стопу или через "
                    "N дней. Одна сделка на акцию за раз.",
        "bt_settings": "⚙️ Настройки бэктеста",
        "bt_hold": "Держать позицию, торговых дней",
        "bt_run": "🧪 Запустить бэктест",
        "bt_loading": "Загружаю 3 года котировок S&P 500 и ищу сигналы на истории… "
                      "первый раз 1–2 минуты, дальше мгновенно",
        "bt_hint": "Нажми **Запустить бэктест**. После первого запуска настройки пересчитываются сразу.",
        "bt_period": "Период проверки: {a} — {b} · сигналов на истории: {n}",
        "bt_compare": "Сравнение сетапов",
        "bt_detail": "Подробно по сетапу",
        "bt_equity": "Накопленный результат в R (каждая сделка рискует 1R)",
        "bt_by_rs": "По уровню RS",
        "bt_by_vol": "По объёму в день сигнала",
        "bt_trades": "Сделки",
        "bt_download": "⬇️ Скачать сделки CSV",
        "bt_none": "Сделок нет — ослабь фильтры (RS, объём, макс. риск).",
        "bt_read": "**Как читать:** главное — *Ожидание R* (средний результат сделки в единицах риска). "
                   "Больше 0 — сетап зарабатывает; 0.2R+ — хорошо. *Profit factor* = сумма прибылей ÷ "
                   "сумма убытков: больше 1.5 — хорошо. Процент прибыльных сам по себе мало значит: "
                   "40% прибыльных с большим средним плюсом лучше, чем 60% с маленьким.",
        "bt_limits": "Ограничения: сегодняшний состав S&P 500 (акции, выбывшие из индекса, не учтены), "
                     "без комиссий и проскальзывания, вход по цене закрытия. Прошлые результаты не "
                     "гарантируют будущих.",
        "bt_reason": {"stop": "🛑 стоп", "time": "⏱ по времени"},
        "bt_cols": {"mode": "Сетап", "trades": "Сделок", "win_rate": "Прибыльных, %",
                    "avg_win": "Средн. плюс, %", "avg_loss": "Средн. минус, %",
                    "expectancy": "Ожидание, %", "expectancy_r": "Ожидание, R",
                    "profit_factor": "Profit factor", "stopped": "По стопу, %",
                    "max_losing_streak": "Макс. серия убытков", "total_r": "Итого, R",
                    "avg_days": "Средн. дней", "bucket": "Группа",
                    "ticker": "Тикер", "date": "Вход", "exit_date": "Выход", "days": "Дней",
                    "rs": "RS", "vol_ratio": "Объём", "entry": "Цена входа", "stop": "Стоп",
                    "exit": "Цена выхода", "risk_pct": "Риск %", "ret_pct": "Результат %",
                    "r": "R", "reason": "Выход по", "max_up_pct": "Макс. рост %"},
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
        "j_intro": "The auto-scan runs every weekday after the close (~7:30 PM New York), "
                   "logs every signal here and sends a push to your phone. "
                   "This tab shows how they played out.",
        "j_empty": "The journal is empty. The first entries appear after the first auto-scan. "
                   "To run it now: GitHub → Actions → Daily scan → Run workflow.",
        "j_all": "All",
        "j_loading": "Calculating signal results…",
        "j_summary": "Results by signal type",
        "j_details": "All signals",
        "j_note": "Returns are measured from the close on the signal day. If price touched the "
                  "stop, the trade is closed at the stop. 5d / 10d columns fill in only after "
                  "5 / 10 trading days; '5d done' shows how many trades they are based on.",
        "j_cols": {"mode": "Type", "signals": "Signals",
                   "win_now": "Up now, %", "avg_now": "Avg now, %",
                   "stopped": "Stopped out, %",
                   "n_5d": "5d done", "win_5d": "Up after 5d, %", "avg_5d": "Avg 5d, %",
                   "n_10d": "10d done", "win_10d": "Up after 10d, %",
                   "avg_10d": "Avg 10d, %",
                   "date": "Date", "ticker": "Ticker", "rs": "RS", "close": "Entry",
                   "stop": "Stop", "ret_5d": "5 days", "ret_10d": "10 days",
                   "ret_now": "Result / now", "max_up": "Max run-up", "status": "Status",
                   "days": "Days"},
        "status": {"new": "🆕 today", "open": "⏳ running", "done10": "✅ 10 days done",
                   "stopped": "🛑 stopped", "nodata": "— no data"},
        "tab_bt": "🧪 Backtest",
        "bt_intro": "Tests the three setups on ~2 years of S&P 500 history with the same rules as the "
                    "live scan. Entry at the signal-day close, exit at the stop or after N days. "
                    "One trade per stock at a time.",
        "bt_settings": "⚙️ Backtest settings",
        "bt_hold": "Holding period, trading days",
        "bt_run": "🧪 Run backtest",
        "bt_loading": "Loading 3 years of S&P 500 quotes and finding historical signals… "
                      "1–2 min the first time, instant afterwards",
        "bt_hint": "Press **Run backtest**. After the first run, settings recalculate instantly.",
        "bt_period": "Test period: {a} — {b} · historical signals: {n}",
        "bt_compare": "Setup comparison",
        "bt_detail": "Setup details",
        "bt_equity": "Cumulative result in R (each trade risks 1R)",
        "bt_by_rs": "By RS level",
        "bt_by_vol": "By volume on the signal day",
        "bt_trades": "Trades",
        "bt_download": "⬇️ Download trades CSV",
        "bt_none": "No trades — loosen the filters (RS, volume, max risk).",
        "bt_read": "**How to read:** the key number is *Expectancy R* (average trade result in units of "
                   "risk). Above 0 — the setup makes money; 0.2R+ is good. *Profit factor* = gross "
                   "profit ÷ gross loss: above 1.5 is good. Win rate alone means little: 40% winners "
                   "with big average wins beat 60% with small ones.",
        "bt_limits": "Limitations: today's S&P 500 members (stocks that left the index are missing), "
                     "no commissions or slippage, entry at the close. Past results don't guarantee "
                     "future ones.",
        "bt_reason": {"stop": "🛑 stop", "time": "⏱ time"},
        "bt_cols": {"mode": "Setup", "trades": "Trades", "win_rate": "Winners, %",
                    "avg_win": "Avg win, %", "avg_loss": "Avg loss, %",
                    "expectancy": "Expectancy, %", "expectancy_r": "Expectancy, R",
                    "profit_factor": "Profit factor", "stopped": "Stopped, %",
                    "max_losing_streak": "Max losing streak", "total_r": "Total, R",
                    "avg_days": "Avg days", "bucket": "Group",
                    "ticker": "Ticker", "date": "Entry", "exit_date": "Exit", "days": "Days",
                    "rs": "RS", "vol_ratio": "Volume", "entry": "Entry price", "stop": "Stop",
                    "exit": "Exit price", "risk_pct": "Risk %", "ret_pct": "Result %",
                    "r": "R", "reason": "Exit by", "max_up_pct": "Max run-up %"},
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
def _fmt(v, pattern):
    """Number → text; empty values show as a dash instead of 'None'."""
    return "—" if v is None or pd.isna(v) else pattern.format(v)


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
    for col in ("win_now", "avg_now", "stopped", "win_5d", "avg_5d", "win_10d", "avg_10d"):
        summ[col] = summ[col].map(lambda v: _fmt(v, "{:.1f}"))
    st.dataframe(summ.rename(columns=J), hide_index=True, use_container_width=True)

    st.subheader(T["j_details"])
    det = ev[["date", "mode", "ticker", "rs", "close", "stop", "ret_5d", "ret_10d",
              "ret_now", "max_up", "status"]].copy()
    for col in ("ret_5d", "ret_10d", "ret_now", "max_up"):
        det[col] = det[col].map(lambda v: _fmt(v * 100, "{:+.1f}%"))
    det["mode"] = det["mode"].map(lambda m: T[f"mode_{m}"])
    det["status"] = det["status"].map(T["status"])
    st.dataframe(det.rename(columns=J), hide_index=True, use_container_width=True,
                 column_config={J["ticker"]: st.column_config.TextColumn(pinned=True)})
    st.caption(T["j_note"])


# =====================================================================
# Вкладка «Бэктест» / Backtest tab
# =====================================================================
@st.cache_resource(ttl=12 * 3600, show_spinner=False)
def backtest_signals(tickers: tuple):
    """3 years of quotes → every historical signal (cached; filters are applied later)."""
    prices = core.get_prices(tickers, period="3y")
    frames = {}
    for t in tickers:
        df = core._frame_for(prices, t)
        if df is not None and len(df):
            frames[t] = df
    return bt.find_signals(frames)


def _num(df, cols, pattern):
    for c in cols:
        if c in df:
            df[c] = df[c].map(lambda v: "∞" if v == np.inf else _fmt(v, pattern))
    return df


def backtest_tab(T):
    st.caption(T["bt_intro"])
    with st.expander(T["bt_settings"], expanded=False):
        hold = st.radio(T["bt_hold"], [5, 10, 20], index=1, horizontal=True, key="bt_hold")
        min_rs = st.slider(T["min_rs"], 0, 99, 70, help=T["min_rs_help"], key="bt_rs")
        min_vol = st.slider(T["min_vol"], 0.0, 3.0, 0.0, 0.1, help=T["min_vol_help"],
                            key="bt_vol")
        stop_buf = st.slider(T["stop_buf"], 0.0, 5.0, 1.0, 0.25, help=T["stop_help"],
                             key="bt_buf")
        max_risk = st.slider(T["max_risk"], 0.0, 15.0, 0.0, 0.5, help=T["max_risk_help"],
                             key="bt_maxrisk")

    if st.button(T["bt_run"], type="primary", use_container_width=True):
        st.session_state["bt_ready"] = True
    if not st.session_state.get("bt_ready"):
        st.write(T["bt_hint"])
        return

    with st.spinner(T["bt_loading"]):
        sig, data = backtest_signals(tuple(get_sp500()["ticker"]))
    if sig.empty:
        st.info(T["bt_none"])
        return
    dates = pd.to_datetime(sig["date"])
    st.caption(T["bt_period"].format(a=dates.min().strftime("%d.%m.%Y"),
                                     b=dates.max().strftime("%d.%m.%Y"), n=f"{len(sig):,}"))

    B = T["bt_cols"]
    trades = {m: bt.simulate(sig, data, m, hold, stop_buf, min_rs, min_vol, max_risk)
              for m in MODES}

    # --- comparison of the three setups
    st.subheader(T["bt_compare"])
    rows = []
    for m in MODES:
        s = bt.stats(trades[m])
        if s["trades"]:
            rows.append({"mode": T[f"mode_{m}"], **s})
    if not rows:
        st.info(T["bt_none"])
        return
    comp = pd.DataFrame(rows)[["mode", "trades", "win_rate", "avg_win", "avg_loss",
                               "expectancy", "expectancy_r", "profit_factor", "stopped",
                               "max_losing_streak", "total_r", "avg_days"]]
    comp = _num(comp, ["win_rate", "avg_win", "avg_loss", "expectancy", "stopped",
                       "avg_days", "total_r"], "{:.1f}")
    comp = _num(comp, ["expectancy_r", "profit_factor"], "{:.2f}")
    st.dataframe(comp.rename(columns=B), hide_index=True, use_container_width=True)
    st.markdown(T["bt_read"])

    # --- one setup in detail
    st.subheader(T["bt_detail"])
    mode = st.segmented_control(T["signal_type"], MODES, default="vcp",
                                format_func=lambda m: T[f"mode_{m}"], key="bt_mode") or "vcp"
    tr = trades[mode]
    if tr.empty:
        st.info(T["bt_none"])
        return

    eq = bt.equity_r(tr)
    fig = go.Figure(go.Scatter(x=eq.index, y=eq.values, mode="lines",
                               line=dict(color="#9B5CF0", width=2),
                               fill="tozeroy", fillcolor="rgba(155,92,240,0.12)"))
    fig.update_layout(height=300, margin=dict(l=8, r=8, t=36, b=8),
                      title=dict(text=T["bt_equity"], x=0.02, font=dict(size=14)),
                      paper_bgcolor="#0B0B12", plot_bgcolor="#0B0B12",
                      font=dict(color="#EDEDF5"), showlegend=False)
    fig.update_xaxes(gridcolor="#1E1E2C")
    fig.update_yaxes(gridcolor="#1E1E2C", side="right", zeroline=True,
                     zerolinecolor="#8A8AA0")
    st.plotly_chart(fig, use_container_width=True,
                    config={"displayModeBar": False, "scrollZoom": False})

    c1, c2 = st.columns(2)
    for col, title, key, bins, labels in (
        (c1, T["bt_by_rs"], "rs", [0, 50, 70, 80, 90, 100],
         ["<50", "50–69", "70–79", "80–89", "90–99"]),
        (c2, T["bt_by_vol"], "vol_ratio", [0, 1, 1.5, 2, np.inf],
         ["<1x", "1–1.5x", "1.5–2x", "≥2x"]),
    ):
        with col:
            st.markdown(f"**{title}**")
            bk = bt.by_bucket(tr, key, bins, labels)
            if not bk.empty:
                bk = _num(bk, ["win_rate", "expectancy"], "{:.1f}")
                bk = _num(bk, ["expectancy_r", "profit_factor"], "{:.2f}")
                st.dataframe(bk.rename(columns=B), hide_index=True, use_container_width=True)

    st.markdown(f"**{T['bt_trades']}**")
    view = tr.sort_values("date", ascending=False).copy()
    view["date"] = pd.to_datetime(view["date"]).dt.strftime("%Y-%m-%d")
    view["exit_date"] = pd.to_datetime(view["exit_date"]).dt.strftime("%Y-%m-%d")
    view["reason"] = view["reason"].map(T["bt_reason"])
    view["rs"] = view["rs"].round().astype("Int64")
    view = view.round({"rs": 0, "vol_ratio": 2, "entry": 2, "stop": 2, "exit": 2,
                       "risk_pct": 2, "ret_pct": 2, "r": 2, "max_up_pct": 2})
    view = view.rename(columns=B)
    st.dataframe(view, hide_index=True, use_container_width=True, height=360,
                 column_config={B["ticker"]: st.column_config.TextColumn(pinned=True)})
    st.download_button(T["bt_download"], view.to_csv(index=False).encode("utf-8"),
                       f"backtest_{mode}.csv", "text/csv", use_container_width=True)
    st.caption(T["bt_limits"])


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

    tab_scan, tab_journal, tab_bt = st.tabs([T["tab_scan"], T["tab_journal"], T["tab_bt"]])
    with tab_scan:
        scan_tab(T, lang)
    with tab_journal:
        journal_tab(T)
    with tab_bt:
        backtest_tab(T)

    st.caption(T["footer"])


if __name__ == "__main__":
    main()
