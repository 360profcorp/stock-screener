"""Persistent day-by-day paper portfolio (Task 10). No broker, no real orders.

It applies, one session at a time, the same rules as backtest.simulate(entry_at="open",
one_per_ticker=False) + portfolio_bt.replay (Task 6 engine, pre-open sizing):

  session D, with only bars <= D:
    1. pre-open entries: orders queued after the previous close, RS-first order; sized from
       cash before today's exits + held positions at the previous close; fill at today's
       open; skipped if the open is at/below the stop; slots/daily/cash limits as replay
    2. exits: stop (entry day: at the stop; later days: min(open, stop)), else time exit at
       the close of the hold-th bar after entry; proceeds settle at the end of the day
    3. mark to market at today's close
  after the close of D: queue_signals(D, scan) -> orders for the next session

State is a plain JSON-serialisable dict (paper/state/portfolio.json).
"""
import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from paper.config import DEFAULT, PaperConfig

ORDER_EXPIRY_SESSIONS = 10        # an order whose ticker has no bar for this long is dropped


def _d(x) -> str:
    return pd.Timestamp(x).strftime("%Y-%m-%d")


def new_state(cfg: PaperConfig = DEFAULT) -> dict:
    return {"config": cfg.as_dict(), "created": datetime.now(timezone.utc).isoformat(
                timespec="seconds"),
            "start": None, "processed_through": None, "cash": float(cfg.initial_cash),
            "positions": {}, "pending": [], "last_prices": {}, "ledger": [],
            "orders_log": [], "equity": []}


class PaperPortfolio:
    def __init__(self, state: dict = None, cfg: PaperConfig = DEFAULT):
        self.cfg = cfg
        self.s = state if state is not None else new_state(cfg)

    # ------------------------------------------------------------------ helpers
    @property
    def fee(self):
        return self.cfg.cost_bps / 10000.

    def _log_order(self, o, day, status, **extra):
        self.s["orders_log"].append({**{k: o.get(k) for k in (
            "ticker", "signal_date", "rs", "rank", "stop", "generated_at", "late")},
            "session": day, "status": status, **extra})

    def equity_now(self) -> float:
        lp = self.s["last_prices"]
        return self.s["cash"] + sum(p["qty"] * lp.get(t, p["entry"])
                                    for t, p in self.s["positions"].items())

    # ------------------------------------------------------------------ one session
    def step(self, day, bars: dict, spy_close=None) -> list:
        """
        Process session `day`. bars: {ticker: {"O","H","L","C"}} for tickers with a bar on
        `day` (at least all held/pending tickers). Returns the day's events.
        """
        day = _d(day)
        s, cfg, fee = self.s, self.cfg, self.fee
        if s["processed_through"] and day <= s["processed_through"]:
            raise ValueError(f"session {day} already processed")
        s["start"] = s["start"] or day
        held, lp, events = s["positions"], s["last_prices"], []

        # 1) pre-open entries ------------------------------------------------
        due = [o for o in s["pending"] if o["ticker"] in bars]
        s["pending"] = [o for o in s["pending"] if o["ticker"] not in bars]
        # RS-first: all due orders enter today, so order by RS descending, ties by ticker
        due.sort(key=lambda o: (-(o["rs"] if o["rs"] == o["rs"] else -1e9), o["ticker"]))
        basis = s["cash"] + sum(p["qty"] * lp.get(t, p["entry"]) for t, p in held.items())
        new_count = 0
        for o in due:
            t, b = o["ticker"], bars[o["ticker"]]
            entry, stop = float(b["O"]), float(o["stop"])
            if not (stop < entry):                            # simulate: no trade at all
                self._log_order(o, day, "no_trade_open_below_stop", open=entry)
                continue
            risk = (entry - stop) / entry
            if cfg.max_risk_pct and risk * 100 > cfg.max_risk_pct:
                self._log_order(o, day, "no_trade_max_risk", open=entry)
                continue
            if t in held:
                self._log_order(o, day, "skipped_ticker_open"); continue
            if len(held) >= cfg.max_positions:
                self._log_order(o, day, "skipped_positions"); continue
            if new_count >= cfg.max_new_per_day:
                self._log_order(o, day, "skipped_daily_entries"); continue
            if stop <= 0:
                self._log_order(o, day, "skipped_invalid"); continue
            by_risk = basis * cfg.risk_fraction / (entry - stop)
            by_cap = basis * cfg.max_position_fraction / (entry * (1 + fee))
            by_cash = s["cash"] / (entry * (1 + fee))
            qty = int(min(by_risk, by_cap, by_cash))
            if qty < 1:
                self._log_order(o, day, "skipped_capital_or_risk"); continue
            spend = qty * entry * (1 + fee)
            s["cash"] -= spend
            held[t] = {"ticker": t, "signal_date": o["signal_date"], "rs": o["rs"],
                       "rank": o.get("rank"), "entry_date": day, "entry": entry, "stop": stop,
                       "qty": qty, "entry_cost": spend, "risk_dollars": qty * (entry - stop),
                       "bars_held": 0, "cash_limited": by_cash < min(by_risk, by_cap)}
            new_count += 1
            self._log_order(o, day, "filled", open=entry, qty=qty)
            events.append(f"BUY {t} {qty} @ {entry:.2f} stop {stop:.2f}")

        # 2) exits -------------------------------------------------------------
        proceeds_today = 0.0
        for t in list(held):
            if t not in bars:
                continue
            p, b = held[t], bars[t]
            if p["entry_date"] == day:                        # entry bar: stop only
                hit = float(b["L"]) <= p["stop"]
                px, reason = (p["stop"], "stop") if hit else (None, None)
            else:
                p["bars_held"] += 1
                if float(b["L"]) <= p["stop"]:
                    px, reason = min(float(b["O"]), p["stop"]), "stop"
                elif p["bars_held"] >= cfg.hold_days:
                    px, reason = float(b["C"]), "time"
                else:
                    px, reason = None, None
            if px is None:
                continue
            proceeds = p["qty"] * float(px) * (1 - fee)
            proceeds_today += proceeds
            pnl = proceeds - p["entry_cost"]
            s["ledger"].append({"ticker": t, "signal_date": p["signal_date"], "rs": p["rs"],
                                "entry_date": p["entry_date"], "exit_date": day,
                                "shares": p["qty"], "entry": p["entry"], "exit": float(px),
                                "stop": p["stop"], "reason": reason, "net_pnl": pnl,
                                "initial_risk": p["risk_dollars"],
                                "net_r": pnl / p["risk_dollars"],
                                "bars_held": p["bars_held"]})
            del held[t]
            events.append(f"SELL {t} @ {px:.2f} ({reason}) pnl {pnl:+.2f}")
        s["cash"] += proceeds_today

        # 3) mark to market ----------------------------------------------------
        for t, b in bars.items():
            lp[t] = float(b["C"])
        s["equity"].append({"date": day, "equity": self.equity_now(), "cash": s["cash"],
                            "positions": len(held), "spy_close": spy_close})
        # stale orders (ticker without bars for a long time)
        keep = []
        for o in s["pending"]:
            o["sessions_waited"] = o.get("sessions_waited", 0) + 1
            if o["sessions_waited"] > ORDER_EXPIRY_SESSIONS:
                self._log_order(o, day, "expired_no_bar")
            else:
                keep.append(o)
        s["pending"] = keep
        s["processed_through"] = day
        return events

    # ------------------------------------------------------------------ after the close
    def queue_signals(self, day, scan: pd.DataFrame, generated_at: str = None,
                      scheduled_for: str = None, late: bool = False) -> int:
        """Queue eligible signals of `day` (RS-first ranked) for the next session."""
        if scan is None or scan.empty:
            return 0
        gen = generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
        el = scan[scan["eligible"]].sort_values("rank")
        for r in el.itertuples():
            self.s["pending"].append({"ticker": r.ticker, "signal_date": _d(day),
                                      "rs": float(r.rs), "rank": int(r.rank),
                                      "stop": float(r.stop), "generated_at": gen,
                                      "scheduled_for": scheduled_for, "late": bool(late)})
        return len(el)

    # ------------------------------------------------------------------ views
    def ledger_df(self) -> pd.DataFrame:
        return pd.DataFrame(self.s["ledger"])

    def equity_df(self) -> pd.DataFrame:
        return pd.DataFrame(self.s["equity"])
