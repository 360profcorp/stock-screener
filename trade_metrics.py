"""Per-strategy performance metrics for the TRADING bot (the 💼 Trading book).

Pure functions, tested. Operates on the bot's own closed-trade and open-position
records as stored by trader.py in the encrypted state:

    closed trade: {ticker, mode, entry_date, entry, exit_date, exit, qty,
                   reason, pnl, r, dry}
    open position: {ticker, mode, entry_date, entry, stop, qty, ...}

`mode` is the STRATEGY SETUP — one of breakout / retest / vcp — NOT the bot run
mode (dry/manual/auto). Statistics here are TRADE-LEVEL (R and $); they are not a
portfolio return and say nothing about equity or drawdown, which the bot does not
track (no cash model). Conventions match paper/metrics.trade_stats so the two books
stay comparable:
  * winners = pnl > 0 ; losers = pnl <= 0 (a breakeven counts as a loser)
  * profit factor = sum(winning pnl) / -sum(losing pnl); None when there are no losers
  * expectancy R = mean of the per-trade R multiples
Never combine these numbers with the Paper (Retest RS-first) book — different exit
rules (see the rules caption on each tab).
"""
import numpy as np
import pandas as pd

# The three setups the bot trades. Fixed order for stable tables/legends.
STRATEGIES = ("breakout", "retest", "vcp")


def holding_days(entry_date, exit_date) -> float:
    """Business days held, entry -> exit. NaN if either date is missing/unparseable."""
    try:
        return float(np.busday_count(np.datetime64(str(entry_date)[:10]),
                                     np.datetime64(str(exit_date)[:10])))
    except Exception:
        return np.nan


def _closed_df(closed) -> pd.DataFrame:
    """Normalise the closed-trade list to a typed frame. Missing columns are created
    empty so downstream code never KeyErrors on a sparse/old state."""
    cols = ["ticker", "mode", "entry_date", "entry", "exit_date", "exit", "qty",
            "reason", "pnl", "r", "dry"]
    df = pd.DataFrame(list(closed or [])).reindex(columns=cols)
    df["pnl"] = pd.to_numeric(df["pnl"], errors="coerce")
    df["r"] = pd.to_numeric(df["r"], errors="coerce")
    return df


def _positions_df(positions) -> pd.DataFrame:
    df = pd.DataFrame(list(positions or []))
    if "mode" not in df.columns:
        df["mode"] = pd.Series(dtype=object)
    return df


def _filter(df: pd.DataFrame, strategy) -> pd.DataFrame:
    """Rows for one strategy, or all rows when strategy is falsy / 'all'."""
    if not strategy or str(strategy).lower() == "all" or not len(df):
        return df
    return df[df["mode"] == str(strategy).lower()]


def strategy_stats(closed, positions=None, strategy=None) -> dict:
    """Headline metrics for one strategy (or all). Drops rows only on the pnl needed
    for a given figure, so a trade missing R still counts toward P&L and win rate.

    max_drawdown_pct is None on purpose: it needs a reliable equity curve, which the
    trading bot does not keep. The dashboard shows it as "—"."""
    cdf = _filter(_closed_df(closed), strategy)
    pdf = _filter(_positions_df(positions), strategy) if positions is not None else None

    out = dict(
        strategy=(str(strategy).lower() if strategy else "all"),
        total_trades=int(len(cdf)),
        open_positions=(int(len(pdf)) if pdf is not None else None),
        win_rate_pct=None, profit_factor=None, total_pnl_usd=0.0, avg_pnl_usd=None,
        expectancy_r=None, avg_winner_usd=None, avg_loser_usd=None,
        avg_holding_days=None, max_drawdown_pct=None,
    )
    if not len(cdf):
        return out

    pnl = cdf["pnl"].dropna()
    if len(pnl):
        wins, losses = pnl[pnl > 0], pnl[pnl <= 0]
        out["total_pnl_usd"] = float(pnl.sum())
        out["avg_pnl_usd"] = float(pnl.mean())
        out["win_rate_pct"] = 100.0 * len(wins) / len(pnl)
        out["profit_factor"] = (float(wins.sum() / -losses.sum())
                                if losses.sum() < 0 else None)
        out["avg_winner_usd"] = float(wins.mean()) if len(wins) else None
        out["avg_loser_usd"] = float(losses.mean()) if len(losses) else None

    r = cdf["r"].dropna()
    if len(r):
        out["expectancy_r"] = float(r.mean())

    hold = cdf.apply(lambda row: holding_days(row["entry_date"], row["exit_date"]),
                     axis=1).dropna()
    if len(hold):
        out["avg_holding_days"] = float(hold.mean())
    return out


def comparison_rows(closed, positions=None) -> list:
    """One stats dict per strategy in STRATEGIES, for the comparison table."""
    return [strategy_stats(closed, positions, s) for s in STRATEGIES]


def cumulative_pnl_by_strategy(closed, strategy=None) -> pd.DataFrame:
    """Cumulative CLOSED-TRADE P&L ($) by exit date, one column per strategy.

    This is realized P&L accumulated at exit, NOT an equity curve and NOT a
    per-strategy capital curve (no capital is allocated per strategy). Trades are
    ordered by exit_date; ties keep input order. Empty frame when nothing qualifies.
    """
    df = _filter(_closed_df(closed), strategy)
    df = df.dropna(subset=["pnl"]).copy()
    if not len(df):
        return pd.DataFrame()
    df["exit_dt"] = pd.to_datetime(df["exit_date"], errors="coerce")
    df = df.dropna(subset=["exit_dt"]).sort_values("exit_dt", kind="stable")
    if not len(df):
        return pd.DataFrame()
    cols = STRATEGIES if (not strategy or str(strategy).lower() == "all") \
        else (str(strategy).lower(),)
    wide = pd.DataFrame(index=df["exit_dt"].unique())
    for s in cols:
        daily = df[df["mode"] == s].groupby("exit_dt")["pnl"].sum()
        wide[s] = daily
    wide = wide.sort_index().fillna(0.0).cumsum()
    # columns that never had a trade are all-zero and meaningless -> drop them
    return wide.loc[:, (wide != 0).any(axis=0)] if len(wide.columns) else wide


def r_values(closed, strategy=None) -> pd.Series:
    """Per-trade R multiples (for the win/loss distribution). NaNs dropped."""
    df = _filter(_closed_df(closed), strategy)
    return df["r"].dropna().reset_index(drop=True)
