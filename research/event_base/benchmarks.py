"""Index alternatives on the same windows (PLAN.md §5). Whole shares, ETF costs per side,
distributions credited on the ex-date and reinvested at that close, cash at 0 %.

Decisions are taken after a close and executed at the next session's open.
"""
import math

import numpy as np
import pandas as pd

import core


def _frame(df):
    d = df.copy()
    d.index = pd.to_datetime(d.index).normalize()
    if "Dividends" not in d:
        d["Dividends"] = 0.0
    return d[["Open", "Close", "Dividends"]].astype(float)


def etf_book(prices, days, rule, cost_bps=2.0, initial=10000., with_dist=True):
    """prices: {"SPY": frame, "BIL": frame}; days: sessions of the window;
    rule(k, day, state) -> target weights dict for the NEXT open, or None (no trade).
    The rule is called at the close of session k (k = -1 before the first open)."""
    fee = cost_bps / 1e4
    P = {s: _frame(f).reindex(days) for s, f in prices.items()}
    sh = {s: 0 for s in P}
    cash, rows, target = float(initial), [], rule(-1, None, None)
    notional = fees = dist = 0.0
    for k, day in enumerate(days):
        if target is not None:
            eq_open = cash + sum(sh[s] * P[s].at[day, "Open"] for s in P if sh[s])
            for s in P:                                         # sells first
                want = int(math.floor(target.get(s, 0.0) * eq_open / (P[s].at[day, "Open"] * (1 + fee))))
                if want < sh[s]:
                    q = sh[s] - want
                    cash += q * P[s].at[day, "Open"] * (1 - fee)
                    notional += q * P[s].at[day, "Open"]
                    fees += q * P[s].at[day, "Open"] * fee
                    sh[s] = want
            for s in P:
                px = P[s].at[day, "Open"]
                want = int(math.floor(target.get(s, 0.0) * eq_open / (px * (1 + fee))))
                q = min(want - sh[s], int(math.floor(cash / (px * (1 + fee))))) if want > sh[s] else 0
                if q > 0:
                    cash -= q * px * (1 + fee)
                    notional += q * px
                    fees += q * px * fee
                    sh[s] += q
            target = None
        for s in P:                                             # distributions: ex-date, reinvest
            dv = P[s].at[day, "Dividends"] if with_dist else 0.0
            if sh[s] and dv and np.isfinite(dv) and dv > 0:
                amt = sh[s] * dv
                cash += amt
                dist += amt
                px = P[s].at[day, "Close"]
                q = int(math.floor(amt / (px * (1 + fee))))
                if q > 0:
                    cash -= q * px * (1 + fee)
                    notional += q * px
                    fees += q * px * fee
                    sh[s] += q
        mv = sum(sh[s] * P[s].at[day, "Close"] for s in P)
        rows.append(dict(date=day, equity=cash + mv, cash=cash, market_value=mv))
        target = rule(k, day, dict(sh=dict(sh)))
    curve = pd.DataFrame(rows)
    assert (curve["cash"] >= -1e-6).all()
    return dict(curve=curve, totals=dict(notional=notional, fees=fees, distributions=dist))


def month_end(days):
    s = pd.Series(pd.DatetimeIndex(days))
    return set(s[s.dt.month != s.shift(-1).dt.month].iloc[:-1])     # last session of each month


def rules(spy_full, days):
    """The four benchmark rules of PLAN.md §5."""
    me = month_end(days)
    reg = core.market_regime(spy_full)
    on = (reg["above50"] & reg["above200"]).reindex(days).fillna(False)

    def hold_spy(k, day, st):
        return {"SPY": 1.0} if k == -1 else None

    def fifty(res):
        def f(k, day, st):
            if k == -1 or day in me:
                return {"SPY": 0.5, res: 0.5} if res != "CASH" else {"SPY": 0.5}
            return None
        return f

    state = {"in": False}

    def timing(k, day, st):
        if k == -1:
            state["in"] = False
            return None
        now = bool(on.loc[day])
        if now != state["in"]:
            state["in"] = now
            return {"SPY": 0.5} if now else {"SPY": 0.0}
        if now and day in me:
            return {"SPY": 0.5}
        return None
    return {"SPY100": hold_spy, "SPY50_CASH50": fifty("CASH"), "SPY50_BIL50": fifty("BIL"),
            "SPY_TIMING50": timing}


# =====================================================================
# v2 (REVIEW_PLAN.md §5): entitlement at the previous close, accrual on the ex-date, cash on
# the (assumed) pay date, reinvestment of the whole accumulated balance at the next open.
# =====================================================================
def pay_dates(ex_days, sym, full_cal, mode="assumed"):
    """{ex-date: pay date}. mode 'assumed': SPY = last session of the month after the ex-date
    month, BIL = 5 sessions after the ex-date; mode 'exdate': pay on the ex-date."""
    cal = pd.DatetimeIndex(full_cal)
    out = {}
    for d in ex_days:
        if mode == "exdate":
            out[d] = d
        elif sym == "SPY":
            m = (pd.Timestamp(d) + pd.offsets.MonthBegin(1))
            nxt = cal[(cal.year == m.year) & (cal.month == m.month)]
            out[d] = nxt[-1] if len(nxt) else pd.Timestamp(d) + pd.offsets.MonthEnd(2)
        else:
            k = cal.searchsorted(pd.Timestamp(d))
            out[d] = cal[k + 5] if k + 5 < len(cal) else pd.Timestamp(d) + pd.Timedelta(days=7)
    return out


def etf_book_v2(prices, days, rule, cost_bps=2.0, initial=10000., with_dist=True, full_cal=None,
                pay_mode="assumed", sweep_all=False):
    fee = cost_bps / 1e4
    full_cal = pd.DatetimeIndex(full_cal if full_cal is not None else days)
    P = {s: _frame(f).reindex(days) for s, f in prices.items()}
    raw = {s: _frame(f) for s, f in prices.items()}
    pay = {s: pay_dates(raw[s].index[raw[s]["Dividends"].fillna(0) > 0], s, full_cal, pay_mode) for s in P}
    sh = {s: 0 for s in P}
    pool = {s: 0.0 for s in P}
    recv = []                                             # (pay_day, sym, amount)
    cash, rows, target = float(initial), [], rule(-1, None, None)
    notional = fees = dist = 0.0

    def buy(s, px, q):
        nonlocal cash, notional, fees
        cash -= q * px * (1 + fee)
        notional += q * px
        fees += q * px * fee
        sh[s] += q

    for k, day in enumerate(days):
        sh_prev = dict(sh)
        if target is not None:                            # rebalance / switch (receivables excluded)
            eq_open = cash + sum(sh[s] * P[s].at[day, "Open"] for s in P if sh[s])
            for s in P:
                want = int(math.floor(target.get(s, 0.0) * eq_open / (P[s].at[day, "Open"] * (1 + fee))))
                if want < sh[s]:
                    q = sh[s] - want
                    cash += q * P[s].at[day, "Open"] * (1 - fee)
                    notional += q * P[s].at[day, "Open"]
                    fees += q * P[s].at[day, "Open"] * fee
                    sh[s] = want
            for s in P:
                px = P[s].at[day, "Open"]
                want = int(math.floor(target.get(s, 0.0) * eq_open / (px * (1 + fee))))
                q = min(want - sh[s], int(math.floor(cash / (px * (1 + fee))))) if want > sh[s] else 0
                if q > 0:
                    buy(s, px, q)
            pool = {s: 0.0 for s in P}
            target = None
        else:                                             # reinvest accumulated balances
            if sweep_all:
                pool = {s: 0.0 for s in P}
                pool["SPY"] = cash
            for s in P:
                if pool[s] > 0 and (sh[s] > 0 or sweep_all):
                    px = P[s].at[day, "Open"]
                    q = int(math.floor(min(pool[s], cash) / (px * (1 + fee))))
                    if q > 0:
                        before = cash
                        buy(s, px, q)
                        pool[s] -= before - cash
        for s in P:                                       # accrual on the ex-date, shares at prior close
            dv = P[s].at[day, "Dividends"] if with_dist else 0.0
            if sh_prev[s] and dv and np.isfinite(dv) and dv > 0:
                amt = sh_prev[s] * dv
                dist += amt
                recv.append((pay[s].get(day, day), s, amt))
        keep = []
        for pd_, s, amt in recv:                          # cash on the pay date
            if pd_ <= day:
                cash += amt
                pool[s] += amt
            else:
                keep.append((pd_, s, amt))
        recv = keep
        mv = sum(sh[s] * P[s].at[day, "Close"] for s in P)
        rec = sum(a for _, _, a in recv)
        rows.append(dict(date=day, equity=cash + mv + rec, cash=cash, market_value=mv, receivable=rec))
        target = rule(k, day, dict(sh=dict(sh)))
    curve = pd.DataFrame(rows)
    assert (curve["cash"] >= -1e-6).all()
    return dict(curve=curve, totals=dict(notional=notional, fees=fees, distributions=dist,
                                         receivable_end=float(curve["receivable"].iloc[-1])))
