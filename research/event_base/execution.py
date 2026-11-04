"""Sequential limit-order portfolio for C / S / E (PLAN.md §3). Research only.

Orders are created after the close of the signal session with a share count fixed from the
limit (close x 1.01), costs and the equity at that close; they are filled at the next
session's open only if open <= limit. Cash, reservations, positions, dividends and exits are
booked day by day; nothing is taken from precomputed trade P&L.
"""
import hashlib
import math
from collections import defaultdict

import numpy as np
import pandas as pd

CFG = dict(initial_cash=10000., risk_fraction=0.005, max_position_fraction=0.10,
           max_positions=5, max_new_per_day=3, limit_mult=1.01, hold=20)
SENSITIVITY = {"base": {}, "stop_slip": dict(stop_slip=0.005), "intrabar_worst": dict(stop_at_low=True),
               "tight_limit": dict(limit_mult=1.00), "nonfill20": dict(nonfill_mod=5)}


def _nonfill(tag, ticker, day, mod):
    h = hashlib.sha256(f"{tag}|{ticker}|{pd.Timestamp(day).date()}".encode()).hexdigest()
    return int(h, 16) % mod == 0


def run_book(cands, data, cal, start, end, cost_bps, tag="book", initial_cash=None, **kw):
    """cands: DataFrame[ticker, i, signal_date, close, stop, rs] (signal bar index i in the
    ticker's arrays). Returns dict(curve, trades, orders, metrics-ready totals)."""
    p = {**CFG, **kw}
    if initial_cash is not None:
        p["initial_cash"] = initial_cash
    fee = cost_bps / 1e4
    stop_slip = p.get("stop_slip", 0.0)
    stop_at_low = p.get("stop_at_low", False)
    nonfill_mod = p.get("nonfill_mod")
    cal = pd.DatetimeIndex(cal)
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    days = [d for d in cal if start <= d <= end]
    pos_of = {d: k for k, d in enumerate(days)}
    idx = {}
    for t in set(cands["ticker"]):
        idx[t] = {pd.Timestamp(d).normalize(): j for j, d in enumerate(data[t]["dates"])}
    by_day = defaultdict(list)
    for r in cands.sort_values(["signal_date", "rs", "ticker"], ascending=[True, False, True],
                               kind="stable").to_dict("records"):
        d = pd.Timestamp(r["signal_date"]).normalize()
        if start <= d <= end:
            by_day[d].append(r)
    cash = float(p["initial_cash"])
    held, orders, last_close = {}, [], {}
    trades, order_log, curve = [], [], []
    tot = defaultdict(float)

    def close_pos(t, pos, day, px, reason, exits):
        proceeds = pos["qty"] * px * (1 - fee)
        tot["fees"] += pos["qty"] * px * fee
        tot["notional"] += pos["qty"] * px
        exits.append(proceeds)
        pnl = proceeds - pos["entry_cost"]
        trades.append(dict(ticker=t, signal_date=pos["signal_date"], entry_date=pos["entry_date"],
                           exit_date=day, qty=pos["qty"], limit=pos["limit"], entry=pos["entry"],
                           stop=pos["stop"], exit=px, reason=reason, status="closed",
                           bars_held=pos["bars"], dividends=pos["div"], net_pnl=pnl,
                           planned_risk=pos["planned_risk"],
                           net_r=(pnl + pos["div"]) / pos["planned_risk"]))

    for day in days:
        # ---- 1) open: fill or expire yesterday's orders (qty fixed yesterday)
        exits, new_today = [], set()
        for o in orders:
            t, x = o["ticker"], data[o["ticker"]]
            j = o["i"] + 1
            cash_res = o["reserve"]
            o_rec = dict(ticker=t, signal_date=o["signal_date"], order_date=o["signal_date"],
                         exec_date=day, qty=o["qty"], limit=o["limit"], stop=o["stop"], rs=o["rs"])
            if j >= len(x["C"]) or pd.Timestamp(x["dates"][j]).normalize() != day:
                order_log.append(dict(o_rec, outcome="expired_no_bar"))
                continue
            O = float(x["O"][j])
            if not np.isfinite(O) or O > o["limit"]:
                order_log.append(dict(o_rec, outcome="expired_above_limit", open=O))
                continue
            if nonfill_mod and _nonfill(tag, t, day, nonfill_mod):
                order_log.append(dict(o_rec, outcome="simulated_nonfill", open=O))
                continue
            cost = o["qty"] * O * (1 + fee)
            assert cost <= cash_res + 1e-6, "fill exceeds reservation"
            cash -= cost
            tot["fees"] += o["qty"] * O * fee
            tot["notional"] += o["qty"] * O
            pos = dict(qty=o["qty"], entry=O, stop=o["stop"], limit=o["limit"], e=j, entry_date=day,
                       signal_date=o["signal_date"], entry_cost=cost, div=0.0, bars=0,
                       planned_risk=o["qty"] * (o["limit"] - o["stop"]))
            if O <= o["stop"]:
                order_log.append(dict(o_rec, outcome="filled_at_or_below_stop", open=O))
                close_pos(t, pos, day, O, "entry_at_or_below_stop", exits)
                continue
            order_log.append(dict(o_rec, outcome="filled", open=O))
            held[t] = pos
            new_today.add(t)
        orders = []
        # ---- 2) dividends (positions held at the previous close), then exits
        divs = 0.0
        for t, pos in held.items():
            if t in new_today:
                continue
            j = idx[t].get(day)
            if j is not None:
                dv = float(data[t]["div"][j]) if "div" in data[t] else 0.0
                if dv > 0:
                    pos["div"] += pos["qty"] * dv
                    divs += pos["qty"] * dv
        for t in list(held):
            pos = held[t]
            x = data[t]
            j = idx[t].get(day)
            if j is None:
                continue
            pos["bars"] = j - pos["e"]
            L, O, C = float(x["L"][j]), float(x["O"][j]), float(x["C"][j])
            px = reason = None
            if L <= pos["stop"]:
                px = pos["stop"] if j == pos["e"] else min(O, pos["stop"])
                if stop_at_low:
                    px = L
                px *= (1 - stop_slip)
                reason = "stop"
            elif j == pos["e"] + p["hold"]:
                px, reason = C, "time"
            if px is not None:
                close_pos(t, held.pop(t), day, px, reason, exits)
        # ---- 3) close: settle, mark
        cash += sum(exits) + divs
        tot["dividends"] += divs
        for t, pos in held.items():
            j = idx[t].get(day)
            if j is not None:
                last_close[t] = float(data[t]["C"][j])
        mv = sum(pos["qty"] * last_close.get(t, pos["entry"]) for t, pos in held.items())
        equity = cash + mv
        assert cash >= -1e-6, "negative cash"
        # ---- 4) orders for the next session
        nxt = pos_of[day] + 1
        free, n_new, pending = cash, 0, set()
        for r in by_day.get(day, []):
            t = r["ticker"]
            rec = dict(ticker=t, signal_date=day, order_date=day, exec_date=None, qty=0,
                       limit=r["close"] * p["limit_mult"], stop=r["stop"], rs=r["rs"])
            if nxt >= len(days):
                order_log.append(dict(rec, outcome="after_window"))
                continue
            if t in held or t in pending:
                order_log.append(dict(rec, outcome="skip_ticker_open"))
                continue
            if len(held) + len(pending) >= p["max_positions"]:
                order_log.append(dict(rec, outcome="skip_positions"))
                continue
            if n_new >= p["max_new_per_day"]:
                order_log.append(dict(rec, outcome="skip_daily_entries"))
                continue
            limit, stop = rec["limit"], float(r["stop"])
            if not (np.isfinite(limit) and np.isfinite(stop) and 0 < stop < limit):
                order_log.append(dict(rec, outcome="skip_invalid"))
                continue
            q = min(p["risk_fraction"] * equity / (limit - stop),
                    p["max_position_fraction"] * equity / (limit * (1 + fee)),
                    free / (limit * (1 + fee)))
            qty = int(math.floor(q + 1e-9))
            if qty < 1:
                order_log.append(dict(rec, outcome="skip_capital_or_risk"))
                continue
            reserve = qty * limit * (1 + fee)
            free -= reserve
            n_new += 1
            pending.add(t)
            orders.append(dict(ticker=t, i=int(r["i"]), signal_date=day, qty=qty, limit=limit,
                               stop=stop, rs=r["rs"], reserve=reserve))
            order_log.append(dict(rec, qty=qty, outcome="placed"))
        assert free >= -1e-6, "reservations exceed cash"
        curve.append(dict(date=day, equity=equity, cash=cash, market_value=mv,
                          reserved=cash - free, positions=len(held)))
    curve = pd.DataFrame(curve)
    open_rows = []
    for t, pos in held.items():
        mark = last_close.get(t, pos["entry"])
        open_rows.append(dict(ticker=t, signal_date=pos["signal_date"], entry_date=pos["entry_date"],
                              exit_date=pd.NaT, qty=pos["qty"], limit=pos["limit"], entry=pos["entry"],
                              stop=pos["stop"], exit=np.nan, mark=mark, reason="open", status="open",
                              bars_held=pos["bars"], dividends=pos["div"],
                              net_pnl=pos["qty"] * mark - pos["entry_cost"],
                              planned_risk=pos["planned_risk"],
                              net_r=(pos["qty"] * mark - pos["entry_cost"] + pos["div"]) / pos["planned_risk"]))
        tot["notional_open"] += pos["qty"] * pos["entry"]
    tr = pd.DataFrame(trades + open_rows)
    rec = reconcile(curve, tr, p["initial_cash"])
    if not rec["matches_cent"]:
        raise AssertionError(f"reconciliation failed: {rec}")
    return dict(curve=curve, trades=tr, orders=pd.DataFrame(order_log), totals=dict(tot), recon=rec,
                initial=p["initial_cash"])


def reconcile(curve, tr, initial):
    """final equity = initial + closed net P&L + all dividends + open (qty*mark - entry cost)."""
    final = float(curve["equity"].iloc[-1]) if len(curve) else initial
    pnl = float(tr["net_pnl"].sum()) if len(tr) else 0.0
    div = float(tr["dividends"].sum()) if len(tr) else 0.0
    expect = initial + pnl + div
    return dict(final_equity=final, expected=expect, diff=final - expect,
                matches_cent=abs(final - expect) < 0.005)
