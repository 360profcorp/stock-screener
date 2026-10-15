"""Sector exposure analysis for portfolio replays (Task 9 research module).

Reusable, read-only helpers — nothing here places trades or changes strategy rules.

Sector source and its limits
----------------------------
* `sector_map_from_universe(core.get_sp500())` uses the GICS Sector column of the current
  Wikipedia "List of S&P 500 companies" (fallback: datasets/s-and-p-500-companies CSV).
* This is a CURRENT snapshot, not point-in-time: a company's historical sector is assumed
  equal to today's. The last broad GICS reshuffle (announced Dec 2022, effective March 2023:
  e.g. Visa/Mastercard IT -> Financials, Target Discretionary -> Staples) predates a backtest
  window that starts in late 2024, so the main residual errors are individual
  reclassifications after corporate events and today's-constituents survivorship.
* Save the snapshot with `save_sector_snapshot` so a study is reproducible even after
  Wikipedia changes. Truly point-in-time GICS history needs a paid source
  (S&P Capital IQ / Compustat GICS history, MSCI, Sharadar etc.).
"""
from datetime import date

import numpy as np
import pandas as pd

UNKNOWN = "Unknown"


# =====================================================================
# Sector map
# =====================================================================
def _clean(sec):
    return sec.strip() if isinstance(sec, str) and sec.strip() else UNKNOWN


def sector_map_from_universe(universe: pd.DataFrame) -> dict:
    """{ticker: sector} from a frame with 'ticker' and 'sector' columns; blanks -> 'Unknown'."""
    if universe is None or universe.empty or "ticker" not in universe:
        return {}
    sec = universe["sector"] if "sector" in universe else pd.Series(index=universe.index)
    return {str(t): _clean(s) for t, s in zip(universe["ticker"], sec)}


def save_sector_snapshot(sector_map: dict, path, as_of=None) -> pd.DataFrame:
    """Write the map with its as-of date (CSV: ticker, sector, as_of)."""
    df = pd.DataFrame(sorted(sector_map.items()), columns=["ticker", "sector"])
    df["as_of"] = str(as_of or date.today())
    df.to_csv(path, index=False)
    return df


def load_sector_snapshot(path) -> dict:
    df = pd.read_csv(path)
    return {str(t): _clean(s) for t, s in zip(df["ticker"], df["sector"])}


# =====================================================================
# Daily exposure from replay output
# =====================================================================
def holdings(executions: pd.DataFrame, open_positions=None) -> pd.DataFrame:
    """One row per position: ticker, entry_date, exit_date (NaT if still open), shares."""
    rows = []
    if executions is not None and len(executions):
        for r in executions.itertuples():
            rows.append((r.ticker, pd.Timestamp(r.entry_date).normalize(),
                         pd.Timestamp(r.exit_date).normalize(), int(r.shares)))
    for p in open_positions or []:
        rows.append((p["ticker"], pd.Timestamp(p["entry_date"]).normalize(), pd.NaT,
                     int(p["shares"])))
    return pd.DataFrame(rows, columns=["ticker", "entry_date", "exit_date", "shares"])


def daily_exposure(executions, open_positions, data: dict, sector_map: dict,
                   days=None) -> pd.DataFrame:
    """
    Positions held at each day's close, by sector.
    A position counts on day d if entry_date <= d < exit_date (exit day excluded: it was sold
    during that day; a same-day round trip never counts). Value = shares x close of d
    (last known close if the ticker has no bar that day).
    Returns long frame: date, sector, positions, value.
    """
    h = holdings(executions, open_positions)
    if days is None:
        days = sorted({d for x in data.values()
                       for d in pd.DatetimeIndex(pd.to_datetime(x["dates"])).normalize()})
    days = pd.DatetimeIndex(days)
    if h.empty:
        return pd.DataFrame(columns=["date", "sector", "positions", "value"])
    closes = {}
    for t in h["ticker"].unique():
        x = data.get(t)
        if x is None:
            continue
        s = pd.Series(np.asarray(x["C"], float),
                      index=pd.DatetimeIndex(pd.to_datetime(x["dates"])).normalize())
        closes[t] = s[~s.index.duplicated()].reindex(days).ffill()
    rows = []
    for r in h.itertuples():
        end = r.exit_date if pd.notna(r.exit_date) else days[-1] + pd.Timedelta(days=1)
        held = days[(days >= r.entry_date) & (days < end)]
        if not len(held):
            continue
        px = closes.get(r.ticker)
        vals = px.reindex(held).values * r.shares if px is not None else np.full(len(held), np.nan)
        sec = _clean(sector_map.get(r.ticker))
        rows.extend(zip(held, [sec] * len(held), [1] * len(held), vals))
    df = pd.DataFrame(rows, columns=["date", "sector", "positions", "value"])
    return df.groupby(["date", "sector"], as_index=False)[["positions", "value"]].sum()


# =====================================================================
# Metrics
# =====================================================================
def concentration_metrics(exposure: pd.DataFrame, n_days: int) -> dict:
    """
    Concentration over all `n_days` of the window (days with no positions count as 0).
      max_same_sector        most positions ever held in one sector at a close
      days_ge2_same_sector   % of days with >=2 positions in one sector (likewise ge3)
      avg/max_top_sector_weight  largest sector's share of invested value (invested days)
      avg_hhi                Herfindahl of sector weights on invested days (1 = one sector)
      avg_sectors_held       distinct sectors held (invested days)
    """
    out = dict(max_same_sector=0, days_ge2_same_sector_pct=0.0, days_ge3_same_sector_pct=0.0,
               avg_top_sector_weight_pct=np.nan, max_top_sector_weight_pct=np.nan,
               avg_hhi=np.nan, avg_sectors_held=np.nan, invested_days_pct=0.0)
    if exposure is None or exposure.empty or n_days <= 0:
        return out
    g = exposure.groupby("date")
    top_n = g["positions"].max()
    tot = g["value"].sum()
    w = exposure.assign(w=exposure["value"] / exposure["date"].map(tot))
    top_w = w.groupby("date")["w"].max()
    hhi = w.assign(w2=w["w"] ** 2).groupby("date")["w2"].sum()
    out.update(
        max_same_sector=int(top_n.max()),
        days_ge2_same_sector_pct=100 * (top_n >= 2).sum() / n_days,
        days_ge3_same_sector_pct=100 * (top_n >= 3).sum() / n_days,
        avg_top_sector_weight_pct=100 * float(top_w.mean()),
        max_top_sector_weight_pct=100 * float(top_w.max()),
        avg_hhi=float(hhi.mean()),
        avg_sectors_held=float(g["sector"].nunique().mean()),
        invested_days_pct=100 * len(top_n) / n_days)
    return out


def sector_breakdown(exposure: pd.DataFrame) -> pd.DataFrame:
    """Share of position-days and of invested value per sector over the window."""
    if exposure is None or exposure.empty:
        return pd.DataFrame(columns=["sector", "position_days", "position_days_pct",
                                     "value_pct", "max_positions"])
    s = exposure.groupby("sector").agg(position_days=("positions", "sum"),
                                       value=("value", "sum"),
                                       max_positions=("positions", "max")).reset_index()
    s["position_days_pct"] = 100 * s["position_days"] / s["position_days"].sum()
    s["value_pct"] = 100 * s["value"] / s["value"].sum()
    return s.drop(columns="value").sort_values("position_days", ascending=False,
                                               ignore_index=True)


def downside_metrics(curve: pd.DataFrame) -> dict:
    """Risk of the equity curve (daily closes)."""
    eq = curve.set_index("date")["equity"].astype(float)
    ret = eq.pct_change().dropna()
    peak = eq.cummax()
    dd = eq / peak - 1
    under = dd < 0
    longest = cur = 0
    for u in under:
        cur = cur + 1 if u else 0
        longest = max(longest, cur)
    r20 = eq / eq.shift(20) - 1
    return dict(ann_vol_pct=100 * float(ret.std() * np.sqrt(252)) if len(ret) > 1 else np.nan,
                worst_day_pct=100 * float(ret.min()) if len(ret) else np.nan,
                worst_20d_pct=100 * float(r20.min()) if r20.notna().any() else np.nan,
                max_drawdown_pct=100 * float(dd.min()),
                longest_drawdown_days=int(longest),
                ulcer_index=float(np.sqrt(((100 * dd) ** 2).mean())))
