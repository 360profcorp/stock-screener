"""50 % SPY / 50 % BIL paper book (owner's instruction 2026-10-26). NO broker, NO orders.

A separate, independent forward book in paper/etf5050/. It never reads or writes any other
paper book (paper/state, paper/data, paper/compare) and has no MA, RS, stop or 20-day exit.

Rules (frozen in CONFIG; a change is a new experiment):
* Start: $10,000 virtual cash. Nothing is bought before activation and nothing is backfilled:
  the activation run only records the last closed session and queues the first purchase for
  the NEXT session's open.
* Monthly rebalance to 50 / 50: decided after the close of the last session of each month,
  executed at the open of the next session.
* Orders: share quantities are sized after the close from the previous close and
  cash + market value (dividend receivables excluded). They are filled at the open, sells first,
  and each buy is capped by the cash then available. Whole shares only, cost_bps of notional a side.
* Dividends: shares held at the close before the ex-date are entitled. The amount is a
  receivable on the ex-date and becomes cash on the assumed pay date (SPY: last session of the
  month after the ex-date's month; BIL: 5 sessions after the ex-date). Cash, including
  dividends, waits for the next monthly rebalance.
* Every session is processed in order. A queued order is "late" (reconstructed) when the run that
  executes it starts after that session's open; such fills are flagged, never hidden.
"""
import json
import math
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from paper import nyse
from paper import store

ROOT = Path(__file__).resolve().parent
DIR = ROOT / "paper" / "etf5050"
STATE = DIR / "state.json"
VERSION = "etf5050-monthly/1.0"


@dataclass(frozen=True)
class Config:
    initial_cash: float = 10000.0
    weights: dict = field(default_factory=lambda: {"SPY": 0.5, "BIL": 0.5})
    cost_bps: float = 2.0                 # ETF commission + spread estimate per side
    rebalance: str = "monthly_last_session_close_next_open"
    bil_pay_lag_sessions: int = 5
    risk_reference_dd_pct: float = -20.0  # evaluation reference only, NOT a loss limit

    def as_dict(self):
        return asdict(self)


CONFIG = Config()
SYMS = ("SPY", "BIL")


# ----------------------------------------------------------------- calendar helpers
def _ts(x):
    return pd.Timestamp(x).normalize()


def is_month_end(day) -> bool:
    return _ts(nyse.next_session(day)).month != _ts(day).month


def pay_date(sym, ex_date, cfg=CONFIG):
    ex = _ts(ex_date)
    if sym == "SPY":
        m = ex + pd.offsets.MonthBegin(1)               # first day of the next month
        last = m + pd.offsets.MonthEnd(0)
        d = last
        while not nyse.is_session(d):
            d -= pd.Timedelta(days=1)
        return d
    d = ex
    for _ in range(cfg.bil_pay_lag_sessions):
        d = _ts(nyse.next_session(d))
    return d


# ----------------------------------------------------------------- state
def new_state(cfg=CONFIG, now=None):
    return dict(kind="forward", version=VERSION, config=cfg.as_dict(), config_hash=store.config_hash(cfg),
                experiment=f"etf5050-{(now or datetime.now(timezone.utc)).strftime('%Y%m%d')}",
                created_at=(now or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
                activation_session=None, processed_through=None, cash=cfg.initial_cash,
                shares={s: 0 for s in SYMS}, receivables=[], pending=[], equity=[], fills=[],
                rebalances=[], dividends=[], fees_total=0.0, dividends_received=0.0,
                last_close={}, revision=0, problems=[])


def load(path=None):
    p = Path(path or os.environ.get("ETF5050_STATE") or STATE)
    return json.loads(p.read_text()) if p.exists() else None


def save(state, folder=DIR):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    store._atomic_write(folder / "state.json", json.dumps(state, indent=1, default=str))
    for name in ("equity", "fills", "rebalances", "dividends"):
        pd.DataFrame(state[name]).to_csv(folder / f"{name}.csv", index=False)


# ----------------------------------------------------------------- data
def valid_bar(df, day):
    if df is None or day not in df.index:
        return False
    r = df.loc[day]
    vals = [float(r[c]) for c in ("Open", "High", "Low", "Close")]
    return all(np.isfinite(v) and v > 0 for v in vals) and float(r["High"]) >= max(vals) * (1 - 1e-6) \
        and float(r["Low"]) <= min(vals) * (1 + 1e-6)


def download(period="6mo"):
    import yfinance as yf
    out = {}
    for s in SYMS:
        y = yf.download(s, period=period, auto_adjust=False, actions=True, progress=False)
        if isinstance(y.columns, pd.MultiIndex):
            y = y.droplevel(1, axis=1) if y.columns.nlevels > 1 else y
        y.index = pd.to_datetime(y.index).tz_localize(None).normalize()
        for c in ("Dividends", "Stock Splits"):
            if c not in y:
                y[c] = 0.0
        out[s] = y
    return out


def closed_session(bars, now):
    """Last session with a bar for both ETFs; today's bar is ignored until 16:15 New York."""
    common = bars["SPY"].index.intersection(bars["BIL"].index)
    ny = now.astimezone(store.NY)
    d = common[-1]
    if d.date() == ny.date() and (ny.hour, ny.minute) < (16, 15):
        d = common[-2]
    return _ts(d)


# ----------------------------------------------------------------- engine
def _equity_basis(state, prev_close):
    return state["cash"] + sum(state["shares"][s] * prev_close[s] for s in SYMS)


def _queue(state, scheduled, reason, now, decided_on):
    state["pending"].append(dict(scheduled_for=str(_ts(scheduled).date()), reason=reason,
                                 decided_on=str(_ts(decided_on).date()),
                                 generated_at=now.isoformat(timespec="seconds"),
                                 late=bool(store.is_late(now, scheduled))))


def _execute(state, day, bars, cfg, run_started):
    """Fill the orders scheduled for `day` at its open."""
    todo = [o for o in state["pending"] if o["scheduled_for"] == str(day.date())]
    if not todo:
        return
    state["pending"] = [o for o in state["pending"] if o not in todo]
    o = todo[-1]
    fee = cfg.cost_bps / 1e4
    prev = {s: float(state["last_close"][s]) for s in SYMS}
    basis = _equity_basis(state, prev)
    target = {s: int(math.floor(cfg.weights[s] * basis / prev[s])) for s in SYMS}   # buys capped by cash
    late = bool(o["late"] or store.is_late(run_started, day))
    before = dict(state["shares"])
    rows = []
    for s in SYMS:                                         # sells first
        q = state["shares"][s] - target[s]
        if q > 0:
            px = float(bars[s].loc[day, "Open"])
            fees = q * px * fee
            state["cash"] += q * px - fees
            state["fees_total"] += fees
            state["shares"][s] -= q
            rows.append(dict(date=str(day.date()), symbol=s, side="SELL", qty=q, price=px, fee=fees,
                             reason=o["reason"], late=late))
    for s in SYMS:
        want = target[s] - state["shares"][s]
        if want > 0:
            px = float(bars[s].loc[day, "Open"])
            q = min(want, int(math.floor(state["cash"] / (px * (1 + fee)))))
            if q > 0:
                fees = q * px * fee
                state["cash"] -= q * px + fees
                state["fees_total"] += fees
                state["shares"][s] += q
                rows.append(dict(date=str(day.date()), symbol=s, side="BUY", qty=q, price=px, fee=fees,
                                 reason=o["reason"], late=late))
    assert state["cash"] >= -1e-6, "cash negative"
    state["fills"] += rows
    opn = {s: float(bars[s].loc[day, "Open"]) for s in SYMS}
    eq_open = state["cash"] + sum(state["shares"][s] * opn[s] for s in SYMS)
    state["rebalances"].append(dict(
        decided_on=o["decided_on"], executed_on=str(day.date()), reason=o["reason"], late=late,
        basis_prev_close=round(basis, 2),
        **{f"{s}_before": before[s] for s in SYMS}, **{f"{s}_after": state["shares"][s] for s in SYMS},
        **{f"w_{s}_after_at_open": round(state["shares"][s] * opn[s] / eq_open, 4) for s in SYMS},
        cash_after=round(state["cash"], 2), fills=len(rows)))


def _dividends(state, day, bars, cfg):
    for s in SYMS:
        dv = float(bars[s].loc[day].get("Dividends", 0.0) or 0.0)
        held = state["held_prev_close"][s]
        if dv > 0 and held > 0:
            amt = held * dv
            pdte = pay_date(s, day, cfg)
            state["receivables"].append(dict(symbol=s, ex_date=str(day.date()), pay_date=str(pdte.date()),
                                             amount=amt))
            state["dividends"].append(dict(symbol=s, ex_date=str(day.date()), per_share=dv, shares=held,
                                           amount=amt, pay_date=str(pdte.date()), paid=False))
    keep = []
    for r in state["receivables"]:
        if _ts(r["pay_date"]) <= day:
            state["cash"] += r["amount"]
            state["dividends_received"] += r["amount"]
            for d in state["dividends"]:
                if d["symbol"] == r["symbol"] and d["ex_date"] == r["ex_date"]:
                    d["paid"] = True
        else:
            keep.append(r)
    state["receivables"] = keep


def _mark(state, day, bars):
    close = {s: float(bars[s].loc[day, "Close"]) for s in SYMS}
    val = {s: state["shares"][s] * close[s] for s in SYMS}
    rec = sum(r["amount"] for r in state["receivables"])
    eq = state["cash"] + sum(val.values()) + rec
    peak = max([state["config"]["initial_cash"]] + [e["equity"] for e in state["equity"]] + [eq])
    state["equity"].append(dict(date=str(day.date()), equity=round(eq, 4), cash=round(state["cash"], 4),
                                SPY_value=round(val["SPY"], 4), BIL_value=round(val["BIL"], 4),
                                receivable=round(rec, 4), w_SPY=round(val["SPY"] / eq, 4) if eq else None,
                                w_BIL=round(val["BIL"] / eq, 4) if eq else None,
                                drawdown_pct=round((eq / peak - 1) * 100, 4),
                                SPY_close=close["SPY"], BIL_close=close["BIL"]))
    state["last_close"] = close


def run_daily(bars=None, now=None, folder=DIR, cfg=CONFIG):
    """Process every closed session since the last run. Returns the saved state."""
    now = now or datetime.now(timezone.utc)
    folder = Path(folder)
    state = load(folder / "state.json")
    if state is not None and state.get("config_hash") != store.config_hash(cfg):
        raise RuntimeError("configuration changed: start a new experiment explicitly")
    bars = download() if bars is None else bars
    last = closed_session(bars, now)
    if state is None:                                      # ---- activation: nothing is bought today
        state = new_state(cfg, now)
        if not (valid_bar(bars["SPY"], last) and valid_bar(bars["BIL"], last)):
            raise RuntimeError(f"no valid bars for activation session {last.date()}")
        state["activation_session"] = str(last.date())
        state["held_prev_close"] = {s: 0 for s in SYMS}
        _mark(state, last, bars)
        state["processed_through"] = str(last.date())
        _queue(state, nyse.next_session(last), "initial", now, last)
    else:
        start = _ts(state["processed_through"])
        sessions = [d for d in pd.bdate_range(start + pd.Timedelta(days=1), last) if nyse.is_session(d)]
        for day in sessions:                               # every NYSE session, in order
            if not (valid_bar(bars["SPY"], day) and valid_bar(bars["BIL"], day)):
                state["problems"].append(dict(day=str(day.date()), problem="invalid or missing bar; stopped"))
                break
            state["held_prev_close"] = dict(state["shares"])
            _execute(state, day, bars, cfg, now)
            _dividends(state, day, bars, cfg)
            _mark(state, day, bars)
            state["processed_through"] = str(day.date())
            if is_month_end(day):
                _queue(state, nyse.next_session(day), "monthly_rebalance", now, day)
    state["revision"] += 1
    state["updated_at"] = now.isoformat(timespec="seconds")
    state["data_date"] = str(last.date())
    reconcile(state)
    save(state, folder)
    (folder / "summary.json").write_text(json.dumps(summary(state), indent=1, default=str))
    return state


def reconcile(state):
    """Cash identity to the cent: initial - buys + sells - fees + dividends received = cash."""
    f = pd.DataFrame(state["fills"])
    buys = float((f.loc[f["side"] == "BUY", "qty"] * f.loc[f["side"] == "BUY", "price"]).sum()) if len(f) else 0.0
    sells = float((f.loc[f["side"] == "SELL", "qty"] * f.loc[f["side"] == "SELL", "price"]).sum()) if len(f) else 0.0
    cash = state["config"]["initial_cash"] - buys + sells - state["fees_total"] + state["dividends_received"]
    if abs(cash - state["cash"]) > 0.01:
        raise AssertionError(f"cash identity broken: {cash:.4f} vs {state['cash']:.4f}")
    held = {s: 0 for s in SYMS}
    for r in state["fills"]:
        held[r["symbol"]] += r["qty"] if r["side"] == "BUY" else -r["qty"]
    if held != {s: state["shares"][s] for s in SYMS}:
        raise AssertionError("share identity broken")
    return True


def summary(state):
    eq = pd.DataFrame(state["equity"])
    init = state["config"]["initial_cash"]
    out = dict(version=state["version"], experiment=state["experiment"], activation_session=state["activation_session"],
               processed_through=state["processed_through"], data_date=state.get("data_date"),
               updated_at=state.get("updated_at"), revision=state["revision"], cash=round(state["cash"], 2),
               shares=state["shares"], pending=state["pending"], fees_total=round(state["fees_total"], 4),
               dividends_received=round(state["dividends_received"], 4),
               receivables=round(sum(r["amount"] for r in state["receivables"]), 4),
               late_fills=int(sum(1 for f in state["fills"] if f["late"])), problems=state["problems"][-5:])
    if len(eq):
        e = eq["equity"].astype(float)
        out.update(equity=round(float(e.iloc[-1]), 2), return_pct=round((e.iloc[-1] / init - 1) * 100, 4),
                   max_drawdown_pct=round(float(eq["drawdown_pct"].min()), 4),
                   current_drawdown_pct=round(float(eq["drawdown_pct"].iloc[-1]), 4),
                   w_SPY=eq["w_SPY"].iloc[-1], w_BIL=eq["w_BIL"].iloc[-1])
        days = (_ts(eq["date"].iloc[-1]) - _ts(eq["date"].iloc[0])).days
        out["cagr_pct"] = round(((e.iloc[-1] / init) ** (365.25 / days) - 1) * 100, 4) if days >= 365 else None
    return out
