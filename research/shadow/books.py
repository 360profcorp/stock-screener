"""Shadow paper books: Research Breakout RS-first vs Research Breakout BR (PREREG_SHADOW.md).

The two books differ **only** in the same-day order of their candidates:
- **rs:** RS descending, ties by ticker (current RS-first);
- **br:** 13F ownership-breadth change F2 descending, then RS, then ticker. This is the BR
  order of PR #20.

Everything else is the Task 10 paper machinery, unchanged:
- `paper.books.scan_mode(mode="breakout")`;
- `PaperPortfolio`: fills at the next open, stops, 20-session exits, 1 % risk,
  5 positions, 3 a day, 20 % cap, 10 bps a side;
- the write-once store.

The br book uses `RankedPortfolio`. Its `step` is `PaperPortfolio.step` with **one line**
changed, the sort of the day's due orders. A test checks the source diff, and checks that
with RS ranks it reproduces `PaperPortfolio` exactly.

**Research Breakout** enters at the next open. It is not the bot's pre-close breakout
purchase. These books never touch `paper/`, `state/`, the bot or `TRADING`.
"""
import hashlib
import inspect
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import backtest as bt
from paper import books as PB
from paper import store
from paper.config import DEFAULT
from paper.portfolio import ORDER_EXPIRY_SESSIONS, PaperPortfolio, _d   # noqa: F401
from research.shadow import f13

ROOT = Path(__file__).resolve().parents[2]
BOOKS = {"rs": replace(DEFAULT, mode="breakout"),
         "br": replace(DEFAULT, mode="breakout", ranking="br13f_then_rs")}
VERSIONS = {"rs": "shadow-breakout-rs-first/1.0", "br": "shadow-breakout-br/1.0"}
EARLIEST_START = "2026-10-26"          # PREREG_SHADOW.md: no session before this is a start
F2_MAX_AGE = 120
TREE = ROOT / "research" / "shadow" / "books"


class StrategyChanged(RuntimeError):
    pass


class BooksOutOfStep(RuntimeError):
    pass


# ---------------------------------------------------------------- F2 (point in time)
class F2Table:
    """breadth.csv -> F2 on a signal day: the latest quarter with usable_from <= day (all its
    counted filings were filed by usable_from - 1), at most 120 days old; missing -> 0."""

    def __init__(self, path=None):
        b = pd.read_csv(path or f13.DIR / "breadth.csv", parse_dates=["period", "usable_from"])
        self.by = {t: g.sort_values("usable_from").reset_index(drop=True) for t, g in b.groupby("ticker")}

    def get(self, ticker, day):
        day = pd.Timestamp(day).normalize()
        g = self.by.get(ticker)
        if g is not None:
            u = g[g["usable_from"] <= day]
            if len(u):
                r = u.iloc[-1]
                if (day - r["usable_from"]).days <= F2_MAX_AGE:
                    v = float(r["breadth_change"]) if pd.notna(r["breadth_change"]) else 0.0
                    return dict(F2=v, f2_status="ok" if pd.notna(r["breadth_change"]) else "no holders in Q-1",
                                f2_period=str(r["period"].date()), f2_usable_from=str(r["usable_from"].date()),
                                holders_q=int(r["holders_q"]), holders_q1=int(r["holders_q1"]))
                return dict(F2=0.0, f2_status="stale (>120 days)", f2_period=str(r["period"].date()),
                            f2_usable_from=str(r["usable_from"].date()), holders_q=None, holders_q1=None)
        return dict(F2=0.0, f2_status="no 13F data", f2_period=None, f2_usable_from=None,
                    holders_q=None, holders_q1=None)


def with_f2(scan: pd.DataFrame, day, table: F2Table) -> pd.DataFrame:
    """Attach F2 to every detection; the input RS-first rank is kept as rank_rs."""
    if scan is None or scan.empty:
        return scan
    out = scan.copy()
    f = pd.DataFrame([table.get(t, day) for t in out["ticker"]], index=out.index)
    out = pd.concat([out, f], axis=1)
    out["rank_rs"] = out["rank"]
    return out


def rank_br(scan: pd.DataFrame) -> pd.DataFrame:
    """BR rank among eligible detections: F2 desc, RS desc, ticker (PR #20 order)."""
    if scan is None or scan.empty:
        return scan
    out = scan.copy()
    el = out[out["eligible"]].sort_values(["F2", "rs", "ticker"], ascending=[False, False, True],
                                          kind="stable")
    out["rank"] = np.nan
    out.loc[el.index, "rank"] = np.arange(1, len(el) + 1)
    return out.sort_values(["rank", "ticker"], na_position="last", kind="stable").reset_index(drop=True)


# ---------------------------------------------------------------- portfolio with a given order
class RankedPortfolio(PaperPortfolio):
    """PaperPortfolio whose due orders enter in BR order (F2 desc, RS desc, ticker)."""

    def queue_signals(self, day, scan, generated_at=None, scheduled_for=None, late=False):
        before = len(self.s["pending"])
        log_before = len(self.s["orders_log"])
        n = super().queue_signals(day, scan, generated_at, scheduled_for, late)
        f2 = dict(zip(scan["ticker"], scan["F2"])) if scan is not None and len(scan) else {}
        for o in self.s["pending"][before:]:
            o["f2"] = float(f2.get(o["ticker"], 0.0))
        for o in self.s["orders_log"][log_before:]:
            o["f2"] = float(f2.get(o["ticker"], 0.0))
        return n

    def step(self, day, bars: dict, spy_close=None, processed_late: bool = False) -> list:
        """
        Process session `day`. bars: {ticker: {"O","H","L","C"}} for tickers with a bar on
        `day` (at least all held/pending tickers). Returns the day's events.
        processed_late: the session is processed after it happened (runner catch-up).
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
        due.sort(key=lambda o: (-o.get("f2", 0.0), -(o["rs"] if o["rs"] == o["rs"] else -1e9), o["ticker"]))
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
                self._log_order(o, day, "ticker_open"); continue
            if len(held) >= cfg.max_positions:
                self._log_order(o, day, "positions"); continue
            if new_count >= cfg.max_new_per_day:
                self._log_order(o, day, "daily_entries"); continue
            if stop <= 0:
                self._log_order(o, day, "invalid"); continue
            by_risk = basis * cfg.risk_fraction / (entry - stop)
            by_cap = basis * cfg.max_position_fraction / (entry * (1 + fee))
            by_cash = s["cash"] / (entry * (1 + fee))
            qty = int(min(by_risk, by_cap, by_cash))
            if qty < 1:
                self._log_order(o, day, "capital_or_risk"); continue
            spend = qty * entry * (1 + fee)
            s["cash"] -= spend
            held[t] = {"ticker": t, "signal_date": o["signal_date"], "rs": o["rs"],
                       "rank": o.get("rank"), "generated_at": o.get("generated_at"),
                       "entry_date": day, "entry": entry, "stop": stop, "qty": qty,
                       "entry_cost": spend, "risk_dollars": qty * (entry - stop),
                       "bars_held": 0, "cash_limited": by_cash < min(by_risk, by_cap),
                       "entry_processed_late": bool(processed_late)}
            new_count += 1
            self._log_order(o, day, "entered", shares=qty, open=entry)
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
            s["ledger"].append({"origin": self.kind, "ticker": t, "signal_date": p["signal_date"],
                                "signal_generated_at": p.get("generated_at"), "rs": p["rs"],
                                "entry_date": p["entry_date"], "exit_date": day,
                                "shares": p["qty"], "entry": p["entry"], "exit": float(px),
                                "stop": p["stop"], "reason": reason, "net_pnl": pnl,
                                "initial_risk": p["risk_dollars"],
                                "net_r": pnl / p["risk_dollars"], "bars_held": p["bars_held"],
                                "entry_processed_late": p.get("entry_processed_late", False),
                                "exit_processed_late": bool(processed_late)})
            del held[t]
            events.append(f"SELL {t} @ {px:.2f} ({reason}) pnl {pnl:+.2f}")
        s["cash"] += proceeds_today

        # 3) mark to market ----------------------------------------------------
        for t, b in bars.items():
            lp[t] = float(b["C"])
        s["equity"].append({"date": day, "equity": self.equity_now(), "cash": s["cash"],
                            "positions": len(held), "spy_close": spy_close,
                            "processed_late": bool(processed_late)})
        if self.trace is not None:
            self.trace.append({"date": day, "cash": s["cash"], "equity": self.equity_now(),
                               "holdings": tuple(sorted((t, p["qty"]) for t, p in held.items()))})
        keep = []
        for o in s["pending"]:                                # tickers still without a bar
            o["sessions_waited"] = o.get("sessions_waited", 0) + 1
            if o["sessions_waited"] > ORDER_EXPIRY_SESSIONS:
                self._log_order(o, day, "expired_no_bar")
            else:
                keep.append(o)
        s["pending"] = keep
        s["processed_through"] = day
        return events


PORTFOLIO = {"rs": PaperPortfolio, "br": RankedPortfolio}


# ---------------------------------------------------------------- identity / storage
def paths(book, root=ROOT):
    base = Path(root) / "research" / "shadow" / "books" / book
    st, da = base / "state", base / "data"
    return dict(base=base, state_dir=st, state_file=st / "portfolio.json", data_dir=da,
                signals=da / "signals.csv", labels=da / "labels.csv", snapshots=da / "snapshots")


def experiment_file(root=ROOT):
    return Path(root) / "research" / "shadow" / "books" / "experiment.json"


def strategy_id(book):
    return f"{VERSIONS[book]}+cfg.{store.config_hash(BOOKS[book])}"


def code_fingerprint():
    """Task 10 components + breakout detector + paper.books.scan_mode + this module + the
    13F breadth rule. Reporting code (run.py report) is not part of the strategy."""
    out = {k: v for k, v in store.code_fingerprint().items() if k != "combined"}
    for name, obj in {"backtest.breakout_at": bt.breakout_at, "paper.books.scan_mode": PB.scan_mode,
                      "research.shadow.books": inspect.getmodule(rank_br),
                      "f13.parse_form_idx": f13.parse_form_idx,
                      "f13.parse_submission": f13.parse_submission,
                      "f13.breadth_rows": f13.breadth_rows, "f13.edgar_pairs": f13.edgar_pairs,
                      "f13.ingest": f13.ingest, "f13.latest_due": f13.latest_due}.items():
        out[name] = hashlib.sha256(inspect.getsource(obj).encode()).hexdigest()[:12]
    out["combined"] = hashlib.sha256(json.dumps(out, sort_keys=True).encode()).hexdigest()[:12]
    return out


def new_book_state(book, experiment, fp):
    from paper.portfolio import new_state
    s = new_state(BOOKS[book], "forward", strategy_id(book))
    s.update(book=book, experiment=experiment, code_fingerprint=fp["combined"],
             created=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    return s


def check_book(state, book, fp, experiment):
    if state.get("book") != book or state.get("experiment") != experiment:
        raise BooksOutOfStep(f"{book}: state belongs to {state.get('book')}/{state.get('experiment')}")
    if state.get("strategy_id") != strategy_id(book) or state.get("code_fingerprint") != fp["combined"]:
        raise StrategyChanged(f"{book}: strategy/code changed ({state.get('code_fingerprint')} -> "
                              f"{fp['combined']}); the owner decides")
