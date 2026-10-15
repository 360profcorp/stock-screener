"""Equivalence checks for Task 10 (used by unit tests and the real-data CI run).

A) screener_vs_history: scan_day() on data truncated at day D must find exactly the Retest
   signals that backtest.find_signals() finds at D (same tickers, level, stop base, RS),
   and the same eligible set as simulate()'s RS / market filters.
B) stepper_vs_replay: the day-by-day PaperPortfolio, fed day by day, must produce the same
   fills, exits, open positions and equity curve as
   simulate(entry_at="open", one_per_ticker=False, include_open=True) + RS-first order +
   portfolio_bt.replay(open_at_end="mark")  (the corrected Task 6 engine).
"""
import numpy as np
import pandas as pd

import backtest as bt
import portfolio_bt as pf
from paper.config import DEFAULT
from paper.portfolio import PaperPortfolio
from paper.screener import rank_rs_first, scan_day, truncate


# ---------------------------------------------------------------- shared inputs
def calendar(data: dict) -> list:
    return sorted({pd.Timestamp(d).normalize() for x in data.values()
                   for d in pd.to_datetime(x["dates"])})


def bar_index(data: dict) -> dict:
    """{ticker: {date: i}} for fast bar lookup."""
    return {t: {pd.Timestamp(d).normalize(): i for i, d in enumerate(pd.to_datetime(x["dates"]))}
            for t, x in data.items()}


def bars_on(data, idx, day) -> dict:
    out = {}
    for t, m in idx.items():
        i = m.get(day)
        if i is not None:
            x = data[t]
            out[t] = {"O": x["O"][i], "H": x["H"][i], "L": x["L"][i], "C": x["C"][i]}
    return out


def eligible_signals(sig: pd.DataFrame, market_ok, cfg=DEFAULT) -> pd.DataFrame:
    """simulate()'s filters applied to raw find_signals rows (market by signal date)."""
    s = sig[sig["mode"] == cfg.mode].copy()
    s["date"] = pd.to_datetime(s["date"]).dt.normalize()
    if market_ok is not None:
        s = s[s["date"].map(market_ok).fillna(True).astype(bool).values]
    if cfg.min_rs:
        s = s[s["rs"] >= cfg.min_rs]
    s["stop"] = s["stop_base"] * (1 - cfg.stop_buf_pct / 100)
    return s


# ---------------------------------------------------------------- A) screener
def screener_vs_history(frames: dict, spy, sig: pd.DataFrame, market_ok, days, cfg=DEFAULT):
    """Returns list of (day, ok, detail)."""
    res = []
    raw = sig[sig["mode"] == cfg.mode].copy()
    raw["date"] = pd.to_datetime(raw["date"]).dt.normalize()
    el = eligible_signals(sig, market_ok, cfg)
    for day in days:
        day = pd.Timestamp(day).normalize()
        scan = scan_day(truncate(frames, day), spy, day, cfg, already_truncated=True)
        h = raw[raw["date"] == day].set_index("ticker").sort_index()
        e_hist = set(el[el["date"] == day]["ticker"])
        if scan.empty:
            ok = h.empty and not e_hist
            res.append((day, ok, "no signals" if ok else f"history has {len(h)}"))
            continue
        sc = scan.set_index("ticker").sort_index()
        same_set = list(sc.index) == list(h.index)
        num_ok = same_set and np.allclose(sc["level"], h["level"]) and \
            np.allclose(sc["stop_base"], h["stop_base"]) and \
            np.allclose(sc["rs"].fillna(-1), h["rs"].fillna(-1))
        e_scan = set(scan[scan["eligible"]]["ticker"])
        ok = bool(num_ok and e_scan == e_hist)
        res.append((day, ok, f"raw {len(sc)}/{len(h)} eligible {len(e_scan)}/{len(e_hist)}"))
    return res


# ---------------------------------------------------------------- B) portfolio
def reference_replay(sig, data, market_ok, start, end, cfg=DEFAULT):
    trades = bt.simulate(sig, data, cfg.mode, hold=cfg.hold_days, stop_buf=cfg.stop_buf_pct,
                         min_rs=cfg.min_rs, min_vol=0.0, max_risk=cfg.max_risk_pct,
                         market_ok=market_ok, entry_at=cfg.entry_at, one_per_ticker=False,
                         include_open=True)
    trades = trades.sort_values(["date", "rs", "ticker"], ascending=[True, False, True],
                                kind="stable").reset_index(drop=True)
    return pf.replay(trades, data, initial_cash=cfg.initial_cash,
                     risk_fraction=cfg.risk_fraction, max_positions=cfg.max_positions,
                     max_new_per_day=cfg.max_new_per_day,
                     max_position_fraction=cfg.max_position_fraction, cost_bps=cfg.cost_bps,
                     start=start, end=end, open_at_end="mark")


def run_stepper(sig, data, market_ok, start, end, cfg=DEFAULT, scanner=None):
    """
    Drive PaperPortfolio over [start, end]. Signals come from `sig` (fast path) or, if
    scanner=(frames, spy) is given, from scan_day() on truncated data each day (live path).
    Signals of the session before `start` are queued first, like replay(start=...) admits
    trades whose entry date is >= start.
    """
    cal = calendar(data)
    start, end = pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()
    idx = bar_index(data)
    el = eligible_signals(sig, market_ok, cfg) if scanner is None else None
    port = PaperPortfolio(cfg=cfg)

    def signals_for(day):
        if scanner is not None:
            frames, spy = scanner
            return scan_day(truncate(frames, day), spy, day, cfg, already_truncated=True)
        d = el[el["date"] == day]
        if d.empty:
            return d
        d = rank_rs_first(d.assign(eligible=True))
        return d.assign(rank=np.arange(1, len(d) + 1))

    prev = [d for d in cal if d < start]
    if prev:
        port.queue_signals(prev[-1], signals_for(prev[-1]))
    for day in [d for d in cal if start <= d <= end]:
        port.step(day, bars_on(data, idx, day))
        port.queue_signals(day, signals_for(day))
    return port


def compare(port, ref) -> dict:
    """Field-by-field comparison; returns dict with ok flag and diffs."""
    curve, ex, m = ref
    led = port.ledger_df()
    cols = ["ticker", "entry_date", "exit_date", "shares", "entry", "exit", "net_pnl"]
    a = ex[ex["status"] == "closed"][cols].copy() if len(ex) else pd.DataFrame(columns=cols)
    b = led[cols].copy() if len(led) else pd.DataFrame(columns=cols)
    for d in (a, b):
        for c in ("entry_date", "exit_date"):
            d[c] = pd.to_datetime(d[c]).dt.strftime("%Y-%m-%d")
        d.sort_values(["entry_date", "ticker"], inplace=True, ignore_index=True)
    fills_ok = len(a) == len(b) and (len(a) == 0 or (
        (a[["ticker", "entry_date", "exit_date"]].values ==
         b[["ticker", "entry_date", "exit_date"]].values).all()
        and (a["shares"].values == b["shares"].values).all()
        and np.allclose(a[["entry", "exit", "net_pnl"]].astype(float).values,
                        b[["entry", "exit", "net_pnl"]].astype(float).values, atol=1e-6)))
    op_ref = sorted((p["ticker"], int(p["shares"])) for p in m["open_positions"])
    op_new = sorted((t, int(p["qty"])) for t, p in port.s["positions"].items())
    eq_ref = curve.set_index(pd.to_datetime(curve["date"]).dt.strftime("%Y-%m-%d"))["equity"]
    eq_new = port.equity_df().set_index("date")["equity"]
    common = eq_ref.index.intersection(eq_new.index)
    eq_ok = len(common) == len(eq_ref) and np.allclose(eq_ref[common], eq_new[common], atol=1e-6)
    return dict(ok=bool(fills_ok and op_ref == op_new and eq_ok), fills_ref=len(a),
                fills_new=len(b), fills_ok=bool(fills_ok), open_ref=op_ref, open_new=op_new,
                open_ok=op_ref == op_new, equity_days=len(common), equity_ok=bool(eq_ok),
                final_ref=float(eq_ref.iloc[-1]) if len(eq_ref) else None,
                final_new=float(eq_new.iloc[-1]) if len(eq_new) else None)
