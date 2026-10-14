"""
S&P 500 Screener — breakouts, breakout + retest, VCP, RS filter, stops & position sizing.
Скринер S&P 500 — пробои, ретест, VCP, фильтр RS, стопы и размер позиции. RU / EN.
Data: Yahoo Finance (yfinance), free.
Run locally:  streamlit run app.py
Not investment advice. / Не является инвестиционной рекомендацией.
"""
import io
import math
from datetime import datetime, time
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="S&P 500 Screener", page_icon="📈", layout="centered")

NY = ZoneInfo("America/New_York")
HEADERS = {"User-Agent": "Mozilla/5.0"}
MODES = ["breakout", "retest", "vcp"]

# =====================================================================
# Тексты интерфейса / UI strings
# =====================================================================
TEXT = {
    "ru": {
        "title": "📈 Скринер S&P 500",
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
        "det_breakout": "закрытие выше хая {n} свечей",
        "det_retest": "пробой {d} дн. назад, откат к уровню, отскок",
        "det_vcp": "коррекции {w}",
        "cols": {
            "ticker": "Тикер", "rs": "RS", "name": "Компания", "sector": "Сектор",
            "close": "Закрытие", "level": "Уровень", "pct_level": "% от уровня",
            "stop": "Стоп", "risk_pct": "Риск %", "shares": "Акций",
            "pos_value": "Позиция $", "vol_ratio": "Объём / ср.20д",
            "signal": "Сигнал", "date": "Дата", "chart": "График",
        },
    },
    "en": {
        "title": "📈 S&P 500 Screener",
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
        "det_breakout": "close above {n}-candle high",
        "det_retest": "broke out {d}d ago, pulled back to level, bounced",
        "det_vcp": "contractions {w}",
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
# Данные / Data
# =====================================================================
@st.cache_data(ttl=24 * 3600, show_spinner=False)
def get_sp500() -> pd.DataFrame:
    """S&P 500 list: Wikipedia, fallback — GitHub CSV."""
    rename = {"Symbol": "ticker", "Security": "name", "Name": "name",
              "GICS Sector": "sector", "Sector": "sector"}
    try:
        html = requests.get(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            headers=HEADERS, timeout=20).text
        df = pd.read_html(io.StringIO(html))[0].rename(columns=rename)
    except Exception:
        df = pd.read_csv(
            "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/"
            "main/data/constituents.csv").rename(columns=rename)
    df["ticker"] = df["ticker"].astype(str).str.replace(".", "-", regex=False)  # BRK.B -> BRK-B
    for col in ("name", "sector"):
        if col not in df:
            df[col] = ""
    return df[["ticker", "name", "sector"]].drop_duplicates("ticker").reset_index(drop=True)


@st.cache_data(ttl=15 * 60, show_spinner=False)
def get_prices(tickers: tuple) -> pd.DataFrame:
    """2 years of daily candles (needed for MA200 and 12-month RS)."""
    return yf.download(list(tickers), period="2y", interval="1d",
                       group_by="ticker", auto_adjust=False,
                       threads=True, progress=False)


def market_is_open(now: datetime) -> bool:
    return now.weekday() < 5 and time(9, 30) <= now.time() < time(16, 0)


def clean_frame(prices, ticker, drop_unclosed, now):
    """One ticker's candles; during market hours drop today's unfinished candle."""
    try:
        df = prices[ticker].dropna(subset=["Close", "High", "Low"])
    except KeyError:
        return None
    if drop_unclosed and len(df) and df.index[-1].date() == now.date() and market_is_open(now):
        df = df.iloc[:-1]
    return df if len(df) else None


# =====================================================================
# Относительная сила / Relative strength (IBD / Minervini style)
# =====================================================================
def rs_score(close: pd.Series):
    """Weighted return: 40% — 3 months, 20% each — 6, 9, 12 months."""
    if len(close) < 253:
        return math.nan
    c = close.values
    r = lambda n: c[-1] / c[-1 - n] - 1
    return 0.4 * r(63) + 0.2 * r(126) + 0.2 * r(189) + 0.2 * r(252)


def rs_ratings(frames: dict) -> pd.Series:
    """Percentile 1–99 among all S&P 500 stocks."""
    s = pd.Series({t: rs_score(df["Close"]) for t, df in frames.items()}).dropna()
    return (s.rank(pct=True) * 98 + 1).round().astype(int)


# =====================================================================
# Детекторы / Detectors.
# Return dict: level, stop_base (price the stop goes under), detail (key, args) — or None.
# =====================================================================
def detect_breakout(df, lookback=3):
    """Last close above the high of the previous N candles."""
    if len(df) < lookback + 1:
        return None
    level = df["High"].iloc[-1 - lookback:-1].max()
    if df["Close"].iloc[-1] <= level:
        return None
    return {"level": level, "stop_base": level,
            "detail": ("det_breakout", {"n": lookback})}


def detect_retest(df, lookback=3, max_days=10, tol=0.02, min_pull=0.03):
    """
    N-candle breakout 2..max_days ago → price ran up, pulled back to the broken
    level (± tol), held it, and turns up today.
    """
    n = len(df)
    if n < lookback + max_days + 2:
        return None
    H, L, C = df["High"].values, df["Low"].values, df["Close"].values
    last = n - 1
    if not (C[last] > C[last - 1]):                # today turns up
        return None
    for i in range(last - 2, last - max_days - 1, -1):
        level = H[i - lookback:i].max()
        if C[i] <= level:
            continue
        peak_idx = i + int(np.argmax(H[i:last]))   # high from breakout to yesterday
        peak = H[peak_idx]
        pull_lows = L[peak_idx + 1:last + 1]       # pullback after the peak, incl. today
        if len(pull_lows) == 0:
            continue                               # no pullback — straight run-up
        pull_low = pull_lows.min()
        touched = level * (1 - tol) <= pull_low <= level * (1 + tol)
        deep_enough = pull_low <= peak * (1 - min_pull)
        held = C[i + 1:last + 1].min() >= level * (1 - tol)
        if touched and deep_enough and held and C[last] > level:
            return {"level": level, "stop_base": min(level, pull_low),
                    "detail": ("det_retest", {"d": last - i})}
    return None


def swing_highs(high: np.ndarray, w=5):
    """Indices of local highs (max within ±w bars)."""
    idx = []
    for i in range(w, len(high) - 1):
        lo, hi = max(0, i - w), min(len(high), i + w + 1)
        if high[i] == high[lo:hi].max() and (not idx or i - idx[-1] > w):
            idx.append(i)
    return idx


def detect_vcp(df, base_len=65, max_last=0.12, max_first=0.35, near_pivot=0.05):
    """
    Simplified Minervini VCP:
      • Trend Template: close > MA50 > MA150 > MA200, MA200 rising,
        price ≥ +25% above 52-wk low and within 25% of 52-wk high
      • 2–4 pullbacks in the base, each shallower, last ≤ 12%
      • volume drying up: 10-day avg < 50-day avg
      • price within 5% of the pivot (high of the last contraction)
    """
    if len(df) < 260:
        return None
    C = df["Close"]
    ma50, ma150, ma200 = (C.rolling(n).mean() for n in (50, 150, 200))
    c = C.iloc[-1]
    hi52, lo52 = df["High"].iloc[-252:].max(), df["Low"].iloc[-252:].min()
    trend_ok = (c > ma50.iloc[-1] > ma150.iloc[-1] > ma200.iloc[-1]
                and ma200.iloc[-1] > ma200.iloc[-21]
                and c >= lo52 * 1.25 and c >= hi52 * 0.75)
    if not trend_ok:
        return None

    base = df.iloc[-base_len:]
    H, L = base["High"].values, base["Low"].values
    highs = swing_highs(H)
    if len(highs) < 2:
        return None
    waves = []                                     # (depth, low of that pullback)
    for k, h in enumerate(highs):
        end = highs[k + 1] if k + 1 < len(highs) else len(H)
        low = L[h:end].min()
        waves.append(((H[h] - low) / H[h], low))
    waves = [w for w in waves if w[0] >= 0.02][-4:]     # ignore noise < 2%
    if len(waves) < 2:
        return None
    depths = [w[0] for w in waves]
    contracting = all(depths[k + 1] < depths[k] for k in range(len(depths) - 1))
    if not (contracting and depths[0] <= max_first and depths[-1] <= max_last):
        return None

    vol = df["Volume"]
    if not vol.iloc[-10:].mean() < vol.iloc[-50:].mean():
        return None

    pivot = H[highs[-1]]
    if c < pivot * (1 - near_pivot):
        return None
    return {"level": pivot, "stop_base": waves[-1][1],
            "detail": ("det_vcp", {"w": " → ".join(f"{d * 100:.0f}%" for d in depths)})}


DETECTORS = {"breakout": detect_breakout, "retest": detect_retest, "vcp": detect_vcp}


# =====================================================================
# Сканирование / Scan  (returns internal column keys; UI renames per language)
# =====================================================================
def scan(prices, universe, mode, lookback, drop_unclosed, min_vol_ratio, min_rs,
         account=10_000.0, risk_pct=1.0, stop_buf=1.0, max_risk=0.0):
    now = datetime.now(NY)
    frames = {}
    for t in universe["ticker"]:
        df = clean_frame(prices, t, drop_unclosed, now)
        if df is not None:
            frames[t] = df
    rs = rs_ratings(frames)
    info = universe.set_index("ticker")
    risk_dollars = account * risk_pct / 100

    rows = []
    for t, df in frames.items():
        if len(df) < 25:
            continue
        rating = rs.get(t, np.nan)
        if min_rs and (pd.isna(rating) or rating < min_rs):
            continue
        sig = (detect_vcp(df) if mode == "vcp"
               else DETECTORS[mode](df, lookback))
        if not sig:
            continue

        last = df.iloc[-1]
        close = float(last["Close"])
        avg_vol = df["Volume"].iloc[-21:-1].mean()
        vol_ratio = last["Volume"] / avg_vol if avg_vol else math.nan
        if min_vol_ratio and (math.isnan(vol_ratio) or vol_ratio < min_vol_ratio):
            continue

        level = float(sig["level"])
        stop = float(sig["stop_base"]) * (1 - stop_buf / 100)
        per_share = close - stop
        if per_share <= 0:
            continue
        risk = per_share / close * 100
        if max_risk and risk > max_risk:
            continue
        shares = int(min(risk_dollars // per_share, account // close))

        key, args = sig["detail"]
        rows.append({
            "ticker": t,
            "rs": None if pd.isna(rating) else int(rating),
            "name": info.at[t, "name"] if t in info.index else "",
            "sector": info.at[t, "sector"] if t in info.index else "",
            "close": round(close, 2),
            "level": round(level, 2),
            "pct_level": round((close / level - 1) * 100, 2),
            "stop": round(stop, 2),
            "risk_pct": round(risk, 2),
            "shares": shares,
            "pos_value": round(shares * close, 0),
            "vol_ratio": round(float(vol_ratio), 2),
            "signal_ru": TEXT["ru"][key].format(**args),
            "signal_en": TEXT["en"][key].format(**args),
            "date": df.index[-1].strftime("%Y-%m-%d"),
            "chart": f"https://www.tradingview.com/chart/?symbol={t.replace('-', '.')}",
        })
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["rs", "vol_ratio"], ascending=False,
                              na_position="last").reset_index(drop=True)
    return out


# =====================================================================
# Интерфейс / UI
# =====================================================================
def main():
    lang_label = st.segmented_control("Language", ["🇷🇺 RU", "🇺🇸 EN"], default="🇷🇺 RU",
                                      key="lang", label_visibility="collapsed")
    lang = "en" if lang_label == "🇺🇸 EN" else "ru"
    T = TEXT[lang]

    st.title(T["title"])
    st.caption(T["subtitle"])

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
            prices = get_prices(tuple(universe["ticker"]))   # RS uses the whole S&P 500
            result = scan(prices, universe, mode, lookback, drop_unclosed,
                          min_vol_ratio, min_rs, account, risk_pct, stop_buf, max_risk)
            if sectors and not result.empty:
                result = result[result["sector"].isin(sectors)].reset_index(drop=True)
        st.session_state.update(result=result, mode_scanned=mode,
                                scanned_at=datetime.now(NY).strftime("%d.%m %H:%M ET"))

    if "result" in st.session_state:
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
            st.dataframe(
                view, hide_index=True, use_container_width=True,
                column_config={
                    C["ticker"]: st.column_config.TextColumn(pinned=True),
                    C["rs"]: st.column_config.ProgressColumn(C["rs"], min_value=0,
                                                             max_value=99, format="%d"),
                    C["chart"]: st.column_config.LinkColumn(C["chart"],
                                                            display_text="TradingView"),
                    C["pct_level"]: st.column_config.NumberColumn(format="%.2f%%"),
                    C["risk_pct"]: st.column_config.NumberColumn(format="%.2f%%"),
                    C["pos_value"]: st.column_config.NumberColumn(format="$%d"),
                    C["vol_ratio"]: st.column_config.NumberColumn(format="%.2fx"),
                },
            )
            st.download_button(T["download"], view.to_csv(index=False).encode("utf-8"),
                               "signals.csv", "text/csv", use_container_width=True)
        if st.button(T["refresh"], use_container_width=True):
            get_prices.clear()
            st.toast(T["refreshed"])
    else:
        st.write(T["hint"])

    st.caption(T["footer"])


if __name__ == "__main__":
    main()
