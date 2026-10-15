"""Performance metrics for the paper portfolio (pure functions, tested).

SPY comparison is PRICE-ONLY (no dividends): it understates SPY's total return by roughly the
dividend yield (~1.2-1.5 % a year), so "excess" figures are vs SPY price return.
"""
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
               spy_price_return_pct=np.nan, excess_vs_spy_price_pct=np.nan)
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
            out["spy_price_return_pct"] = 100 * (float(spy.dropna().iloc[-1]) / initial - 1)
            out["excess_vs_spy_price_pct"] = out["return_pct"] - out["spy_price_return_pct"]
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


# =====================================================================
# Forward-integrity report (Task 10B, P0-1)
# =====================================================================
PORTFOLIO_KEYS = ("days", "final_equity", "return_pct", "cagr_pct", "max_drawdown_pct",
                  "current_drawdown_pct", "exposure_pct", "spy_price_return_pct",
                  "excess_vs_spy_price_pct")


def trade_stats(ledger: pd.DataFrame) -> dict:
    """Trade-level statistics (R and $). NOT a portfolio return."""
    if ledger is None or not len(ledger):
        return dict(closed=0, win_rate_pct=None, profit_factor=None, expectancy_r=None,
                    expectancy_usd=None, total_pnl_usd=0.0)
    pnl = ledger["net_pnl"].astype(float)
    w, l = pnl[pnl > 0], pnl[pnl <= 0]
    return dict(closed=len(pnl), win_rate_pct=100 * len(w) / len(pnl),
                profit_factor=float(w.sum() / -l.sum()) if l.sum() < 0 else None,
                expectancy_r=float(ledger["net_r"].mean()), expectancy_usd=float(pnl.mean()),
                total_pnl_usd=float(pnl.sum()))


def classify(state: dict) -> dict:
    """
    A  timely        entry AND exit (if any) processed in their own session's run
    B  reconstructed entry OR exit processed retrospectively (runner catch-up)
    C  late signals  recorded at/after their execution session's open; never traded
    The portfolio is CONTAMINATED from the first session containing a B execution.
    """
    led = pd.DataFrame(state.get("ledger", []))
    pos = pd.DataFrame(list(state.get("positions", {}).values()))
    if len(led):
        late = led["entry_processed_late"].astype(bool) | led["exit_processed_late"].astype(bool)
        led = led.assign(category=np.where(late, "reconstructed", "timely"))
    if len(pos):
        pos = pos.assign(category=np.where(pos["entry_processed_late"].astype(bool),
                                           "reconstructed", "timely"))
    events = []
    for r in (led.to_dict("records") if len(led) else []):
        if r["entry_processed_late"]:
            events.append((r["entry_date"], "entry", r["ticker"]))
        if r["exit_processed_late"]:
            events.append((r["exit_date"], "exit", r["ticker"]))
    for r in (pos.to_dict("records") if len(pos) else []):
        if r["entry_processed_late"]:
            events.append((r["entry_date"], "entry", r["ticker"]))
    events.sort()
    c = [o for o in state.get("orders_log", []) if o.get("outcome") == "not_traded_late"]
    eq = state.get("equity", [])
    return dict(ledger=led, positions=pos, reconstructed_events=events,
                contaminated_since=events[0][0] if events else None,
                late_not_traded=c,
                late_processed_sessions=[r["date"] for r in eq if r.get("processed_late")])


def forward_report(state: dict) -> dict:
    """Separated forward results for summary.json and the dashboard.

    genuine_forward: portfolio-level metrics ONLY while no reconstructed execution has
    happened. Equity is path-dependent, so after contamination they are reported as
    unavailable — the pre-contamination window is kept, frozen at genuine_through.
    """
    init = state["config"]["initial_cash"]
    cl = classify(state)
    eq = pd.DataFrame(state.get("equity", []))
    led, pos = cl["ledger"], cl["positions"]
    since = cl["contaminated_since"]
    gen = dict(available=since is None, contaminated_since=since, genuine_through=None,
               reason=None, metrics=None)
    if len(eq):
        clean = eq[eq["date"] < since] if since else eq
        if len(clean):
            m = performance(clean, None, init)
            gen["genuine_through"] = clean["date"].iloc[-1]
            gen["metrics"] = {k: m[k] for k in PORTFOLIO_KEYS}
        if since:
            gen["reason"] = (f"reconstructed execution(s) from {since}: portfolio-level "
                             f"genuine-forward return, drawdown, CAGR and SPY-relative "
                             f"performance are unavailable after "
                             f"{gen['genuine_through'] or 'the start'}")
    observed = performance(eq, None, init) if len(eq) else None
    pick = lambda df, cat: df[df["category"] == cat] if len(df) else df
    return dict(
        genuine_forward=gen,
        observed_portfolio=dict(contains_reconstructed=since is not None,
                                metrics={k: observed[k] for k in PORTFOLIO_KEYS}
                                if observed else None),
        timely=dict(trades=trade_stats(pick(led, "timely")),
                    open_positions=int(len(pick(pos, "timely"))),
                    note="trade-level statistics, not a counterfactual portfolio return"
                    + (f"; position sizes after {since} depend on contaminated equity"
                       if since else "")),
        reconstructed=dict(trades=trade_stats(pick(led, "reconstructed")),
                           open_positions=int(len(pick(pos, "reconstructed"))),
                           events=[dict(date=d, kind=k, ticker=t)
                                   for d, k, t in cl["reconstructed_events"]]),
        late_not_traded=dict(count=len(cl["late_not_traded"]),
                             signals=[dict(ticker=o["ticker"], signal_date=o["signal_date"],
                                           generated_at=o.get("generated_at"))
                                      for o in cl["late_not_traded"]]),
        late_processed_sessions=cl["late_processed_sessions"],
        benchmark_note="SPY comparison is price-only (dividends excluded)")
