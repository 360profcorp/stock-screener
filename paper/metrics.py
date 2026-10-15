"""Performance metrics for the paper portfolio dashboard (pure functions, tested)."""
import numpy as np
import pandas as pd


def drawdown(equity: pd.Series, initial: float) -> pd.Series:
    peak = np.maximum(initial, equity.cummax())
    return 100 * (equity / peak - 1)


def spy_curve(eq: pd.DataFrame, initial: float) -> pd.Series:
    """Buy-and-hold SPY scaled to the starting capital on the first equity day."""
    s = pd.to_numeric(eq["spy_close"], errors="coerce").ffill()
    if s.dropna().empty:
        return pd.Series(np.nan, index=eq.index)
    first = s.dropna().iloc[0]
    return initial * s / first


def performance(eq: pd.DataFrame, ledger: pd.DataFrame, initial: float) -> dict:
    out = dict(days=0, final_equity=initial, return_pct=0.0, cagr_pct=np.nan,
               max_drawdown_pct=0.0, current_drawdown_pct=0.0, trades=0, win_rate_pct=np.nan,
               profit_factor=np.nan, expectancy_usd=np.nan, expectancy_r=np.nan,
               avg_win_usd=np.nan, avg_loss_usd=np.nan, exposure_pct=np.nan,
               spy_return_pct=np.nan, excess_return_pct=np.nan)
    if eq is not None and len(eq):
        e = eq["equity"].astype(float).reset_index(drop=True)
        d = pd.to_datetime(eq["date"]).reset_index(drop=True)
        dd = drawdown(e, initial)
        years = (d.iloc[-1] - d.iloc[0]).days / 365.25
        final = float(e.iloc[-1])
        spy = spy_curve(eq.reset_index(drop=True), initial)
        out.update(days=len(e), final_equity=final, return_pct=100 * (final / initial - 1),
                   cagr_pct=100 * ((final / initial) ** (1 / years) - 1) if years >= 0.25
                   else np.nan,
                   max_drawdown_pct=float(dd.min()), current_drawdown_pct=float(dd.iloc[-1]),
                   exposure_pct=100 * float((eq["positions"] > 0).mean()))
        if spy.notna().any():
            out["spy_return_pct"] = 100 * (float(spy.dropna().iloc[-1]) / initial - 1)
            out["excess_return_pct"] = out["return_pct"] - out["spy_return_pct"]
    if ledger is not None and len(ledger):
        pnl = ledger["net_pnl"].astype(float)
        wins, losses = pnl[pnl > 0], pnl[pnl <= 0]
        out.update(trades=len(pnl), win_rate_pct=100 * len(wins) / len(pnl),
                   profit_factor=float(wins.sum() / -losses.sum()) if losses.sum() < 0
                   else np.inf,
                   expectancy_usd=float(pnl.mean()), expectancy_r=float(ledger["net_r"].mean()),
                   avg_win_usd=float(wins.mean()) if len(wins) else np.nan,
                   avg_loss_usd=float(losses.mean()) if len(losses) else np.nan)
    return out
