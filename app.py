"""
Скринер S&P 500 — пробои, пробой с ретестом, VCP + фильтр относительной силы (RS)
Данные: Yahoo Finance (yfinance), бесплатно.
Запуск локально:  streamlit run app.py
Не является инвестиционной рекомендацией.
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

st.set_page_config(page_title="Скринер S&P 500", page_icon="📈", layout="centered")

NY = ZoneInfo("America/New_York")
HEADERS = {"User-Agent": "Mozilla/5.0"}
MODES = ["Пробой", "Пробой с ретестом", "VCP"]


# =====================================================================
# Данные
# =====================================================================
@st.cache_data(ttl=24 * 3600, show_spinner=False)
def get_sp500() -> pd.DataFrame:
    """Список S&P 500: Википедия, запасной вариант — GitHub CSV."""
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
    """Дневные свечи за 2 года (нужно для MA200 и RS за 12 месяцев)."""
    return yf.download(list(tickers), period="2y", interval="1d",
                       group_by="ticker", auto_adjust=False,
                       threads=True, progress=False)


def market_is_open(now: datetime) -> bool:
    return now.weekday() < 5 and time(9, 30) <= now.time() < time(16, 0)


def clean_frame(prices, ticker, drop_unclosed, now):
    """Свечи одного тикера; во время торгов убираем незакрытую сегодняшнюю свечу."""
    try:
        df = prices[ticker].dropna(subset=["Close", "High", "Low"])
    except KeyError:
        return None
    if drop_unclosed and len(df) and df.index[-1].date() == now.date() and market_is_open(now):
        df = df.iloc[:-1]
    return df if len(df) else None


# =====================================================================
# Относительная сила (RS Rating в стиле IBD / Минервини)
# =====================================================================
def rs_score(close: pd.Series):
    """Взвешенная доходность: 40% — 3 мес., по 20% — 6, 9, 12 мес."""
    if len(close) < 253:
        return math.nan
    c = close.values
    r = lambda n: c[-1] / c[-1 - n] - 1
    return 0.4 * r(63) + 0.2 * r(126) + 0.2 * r(189) + 0.2 * r(252)


def rs_ratings(frames: dict) -> pd.Series:
    """Перцентиль 1–99 среди всех акций S&P 500."""
    s = pd.Series({t: rs_score(df["Close"]) for t, df in frames.items()}).dropna()
    return (s.rank(pct=True) * 98 + 1).round().astype(int)


# =====================================================================
# Детекторы сигналов. Каждый возвращает dict с деталями или None.
# =====================================================================
def detect_breakout(df, lookback=3):
    """Закрытие последней свечи выше максимума N предыдущих свечей."""
    if len(df) < lookback + 1:
        return None
    level = df["High"].iloc[-1 - lookback:-1].max()
    close = df["Close"].iloc[-1]
    if close <= level:
        return None
    return {"Уровень": level, "Детали": f"закрытие выше хая {lookback} свечей"}


def detect_retest(df, lookback=3, max_days=10, tol=0.02, min_pull=0.03):
    """
    Пробой N свечей был 2..max_days дней назад → цена ушла выше,
    откатилась к пробитому уровню (± tol), удержала его и сегодня разворачивается вверх.
    """
    n = len(df)
    if n < lookback + max_days + 2:
        return None
    H, L, C = df["High"].values, df["Low"].values, df["Close"].values
    last = n - 1
    # Сегодня — разворот вверх
    if not (C[last] > C[last - 1]):
        return None
    # Ищем самый свежий пробой в окне
    for i in range(last - 2, last - max_days - 1, -1):
        level = H[i - lookback:i].max()
        if C[i] <= level:
            continue
        seg = slice(i, last)                       # от пробоя до вчера
        peak_idx = i + int(np.argmax(H[seg]))
        peak = H[peak_idx]
        pull_lows = L[peak_idx + 1:last + 1]       # откат после пика, включая сегодня
        if len(pull_lows) == 0:
            continue                               # отката не было — чистый рост
        pull_low = pull_lows.min()
        touched = level * (1 - tol) <= pull_low <= level * (1 + tol)
        deep_enough = pull_low <= peak * (1 - min_pull)
        held = C[i + 1:last + 1].min() >= level * (1 - tol)
        if touched and deep_enough and held and C[last] > level:
            return {"Уровень": level,
                    "Детали": f"пробой {last - i} дн. назад, откат к уровню, отскок"}
    return None


def swing_highs(high: np.ndarray, w=5):
    """Индексы локальных максимумов (максимум в окне ±w)."""
    idx = []
    for i in range(w, len(high) - 1):
        lo, hi = max(0, i - w), min(len(high), i + w + 1)
        if high[i] == high[lo:hi].max() and (not idx or i - idx[-1] > w):
            idx.append(i)
    return idx


def detect_vcp(df, base_len=65, max_last=0.12, max_first=0.35, near_pivot=0.05):
    """
    Упрощённый VCP (Минервини):
      • Trend Template: close > MA50 > MA150 > MA200, MA200 растёт,
        цена ≥ +25% от 52-нед. минимума и не дальше −25% от 52-нед. максимума
      • в базе 2–4 коррекции, каждая мельче предыдущей, последняя ≤ 12%
      • объём подсыхает: средний за 10 дней < среднего за 50
      • цена в пределах 5% от пивота (хая последней коррекции)
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
    depths = []
    for k, h in enumerate(highs):
        end = highs[k + 1] if k + 1 < len(highs) else len(H)
        low = L[h:end].min()
        depths.append((H[h] - low) / H[h])
    depths = [d for d in depths if d >= 0.02][-4:]     # игнорируем шум < 2%
    if len(depths) < 2:
        return None
    contracting = all(depths[k + 1] < depths[k] for k in range(len(depths) - 1))
    if not (contracting and depths[0] <= max_first and depths[-1] <= max_last):
        return None

    vol = df["Volume"]
    if not vol.iloc[-10:].mean() < vol.iloc[-50:].mean():
        return None

    pivot = H[highs[-1]]
    if c < pivot * (1 - near_pivot):
        return None
    waves = " → ".join(f"{d * 100:.0f}%" for d in depths)
    return {"Уровень": pivot, "Детали": f"коррекции {waves}"}


# =====================================================================
# Сканирование
# =====================================================================
def scan(prices, universe, mode, lookback, drop_unclosed, min_vol_ratio, min_rs):
    now = datetime.now(NY)
    frames = {}
    for t in universe["ticker"]:
        df = clean_frame(prices, t, drop_unclosed, now)
        if df is not None:
            frames[t] = df
    rs = rs_ratings(frames)
    info = universe.set_index("ticker")

    rows = []
    for t, df in frames.items():
        if len(df) < 25:
            continue
        rating = rs.get(t, np.nan)
        if min_rs and (pd.isna(rating) or rating < min_rs):
            continue
        if mode == "Пробой":
            sig = detect_breakout(df, lookback)
        elif mode == "Пробой с ретестом":
            sig = detect_retest(df, lookback)
        else:
            sig = detect_vcp(df)
        if not sig:
            continue

        last = df.iloc[-1]
        avg_vol = df["Volume"].iloc[-21:-1].mean()
        vol_ratio = last["Volume"] / avg_vol if avg_vol else math.nan
        if min_vol_ratio and (math.isnan(vol_ratio) or vol_ratio < min_vol_ratio):
            continue

        level = sig["Уровень"]
        rows.append({
            "Тикер": t,
            "RS": None if pd.isna(rating) else int(rating),
            "Компания": info.at[t, "name"] if t in info.index else "",
            "Сектор": info.at[t, "sector"] if t in info.index else "",
            "Закрытие": round(float(last["Close"]), 2),
            "Уровень": round(float(level), 2),
            "% от уровня": round((last["Close"] / level - 1) * 100, 2),
            "Объём / ср.20д": round(float(vol_ratio), 2),
            "Сигнал": sig["Детали"],
            "Дата": df.index[-1].strftime("%Y-%m-%d"),
            "График": f"https://www.tradingview.com/chart/?symbol={t.replace('-', '.')}",
        })
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["RS", "Объём / ср.20д"], ascending=False,
                              na_position="last").reset_index(drop=True)
    return out


# =====================================================================
# Интерфейс
# =====================================================================
def main():
    st.title("📈 Скринер S&P 500")
    st.caption("Пробои, ретесты и VCP среди лидеров рынка · данные Yahoo Finance")

    mode = st.segmented_control("Тип сигнала", MODES, default="Пробой") or "Пробой"
    st.caption({
        "Пробой": "Закрытие дня выше максимума последних 2–3 свечей.",
        "Пробой с ретестом": "Пробой был несколько дней назад, цена вернулась к уровню, "
                             "удержала его и сегодня пошла вверх.",
        "VCP": "Восходящий тренд, сужающиеся коррекции, подсыхающий объём, "
               "цена у верхушки базы (упрощённая версия по Минервини).",
    }[mode])

    with st.expander("⚙️ Настройки", expanded=False):
        lookback = st.radio("Сколько свечей пробивать", [2, 3], index=1, horizontal=True,
                            disabled=(mode == "VCP"))
        min_rs = st.slider("Мин. относительная сила (RS)", 0, 99, 70,
                           help="Перцентиль среди акций S&P 500. 70 — сильнее 70% рынка. "
                                "Минервини обычно берёт 80+. 0 — без фильтра.")
        min_vol_ratio = st.slider("Мин. объём к среднему за 20 дней", 0.0, 3.0, 0.0, 0.1,
                                  help="1.5 = объём в 1.5 раза выше среднего. 0 — без фильтра.")
        drop_unclosed = st.checkbox("Только закрытые свечи (во время торгов берётся вчерашняя)",
                                    value=True)
        sectors_all = sorted(get_sp500()["sector"].dropna().unique())
        sectors = st.multiselect("Секторы (пусто — все)", sectors_all)

    if st.button("🔍 Сканировать", type="primary", use_container_width=True):
        with st.spinner("Загружаю S&P 500 и котировки… первый раз ~1 мин"):
            universe = get_sp500()
            prices = get_prices(tuple(universe["ticker"]))   # RS считается по всему S&P 500
            result = scan(prices, universe, mode, lookback, drop_unclosed,
                          min_vol_ratio, min_rs)
            if sectors and not result.empty:
                result = result[result["Сектор"].isin(sectors)].reset_index(drop=True)
        st.session_state.update(result=result, mode_scanned=mode,
                                scanned_at=datetime.now(NY).strftime("%d.%m %H:%M ET"))

    if "result" in st.session_state:
        res = st.session_state["result"]
        st.metric(f"Найдено: {st.session_state['mode_scanned']}", len(res),
                  help=f"Скан: {st.session_state['scanned_at']}")
        if res.empty:
            st.info("Сигналов по заданным условиям нет. Попробуй снизить RS или убрать фильтр объёма.")
        else:
            st.dataframe(
                res, hide_index=True, use_container_width=True,
                column_config={
                    "Тикер": st.column_config.TextColumn(pinned=True),
                    "RS": st.column_config.ProgressColumn("RS", min_value=0, max_value=99,
                                                          format="%d"),
                    "График": st.column_config.LinkColumn("График", display_text="TradingView"),
                    "% от уровня": st.column_config.NumberColumn(format="%.2f%%"),
                    "Объём / ср.20д": st.column_config.NumberColumn(format="%.2fx"),
                },
            )
            st.download_button("⬇️ Скачать CSV", res.to_csv(index=False).encode("utf-8"),
                               "signals.csv", "text/csv", use_container_width=True)
        if st.button("🔄 Обновить котировки (сбросить кэш)", use_container_width=True):
            get_prices.clear()
            st.toast("Кэш очищен — нажми «Сканировать»")
    else:
        st.write("Выбери тип сигнала и нажми **Сканировать**.")

    st.caption("Сигналы — стартовый список для ручной проверки графика. "
               "Не является инвестиционной рекомендацией.")


if __name__ == "__main__":
    main()
