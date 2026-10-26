"""S: first exit from a fixed contracting base (PLAN.md §2). Research only.

Detection after the close of ticker bar t on the 20 bars t-19..t (plus bar t-20 for the first
true range), all on consecutive SPY sessions. Width <= 12 %, compression mean TR(last 5) <=
0.75 * mean TR(first 10). The base is frozen on detection and watched for the next 10 bars:
close > high -> signal, close < low -> cancelled, 10 bars -> expired, missing session ->
broken. One base at a time per ticker; formation windows never overlap.
"""
import numpy as np
import pandas as pd

WINDOW = 20
MAX_WIDTH = 0.12
LAST_N, FIRST_N, RATIO = 5, 10, 0.75
WATCH = 10
STOP_MULT = 0.97


def session_index(dates, cal_pos):
    """Position of each bar's date in the SPY calendar (-1 if the date is not a session)."""
    return np.array([cal_pos.get(pd.Timestamp(d).normalize(), -1) for d in dates], dtype=int)


def true_range(H, L, C):
    prev = np.r_[np.nan, C[:-1]]
    return np.maximum(H, prev) - np.minimum(L, prev)


def scan(x, sess, start_i=260):
    """All bases of one ticker in time order. x: arrays (H, L, C, dates); sess: session index
    per bar. Returns a list of dicts (one per base, with its outcome)."""
    H, L, C = (np.asarray(x[k], dtype=float) for k in ("H", "L", "C"))
    dates = x["dates"]
    n = len(C)
    if n < WINDOW + 1:
        return []
    tr = true_range(H, L, C)
    consec = np.r_[False, (np.diff(sess) == 1) & (sess[1:] >= 0) & (sess[:-1] >= 0)]
    out, last_end, t = [], -1, max(start_i, WINDOW)
    while t < n:
        a = t - WINDOW + 1
        if a <= last_end or not consec[a:t + 1].all():
            t += 1
            continue
        hi, lo = float(H[a:t + 1].max()), float(L[a:t + 1].min())
        width = hi / lo - 1
        first, last = float(np.mean(tr[a:a + FIRST_N])), float(np.mean(tr[t - LAST_N + 1:t + 1]))
        if not (width <= MAX_WIDTH and last <= RATIO * first):
            t += 1
            continue
        rec = dict(i_start=a, i_end=t, base_start=pd.Timestamp(dates[a]), base_end=pd.Timestamp(dates[t]),
                   base_high=hi, base_low=lo, width_pct=100 * width, tr_ratio=last / first)
        outcome, j = "expired", t
        for k in range(1, WATCH + 1):
            j = t + k
            if j >= n:
                outcome, j = "open_at_data_end", n - 1
                break
            if not consec[j]:
                outcome = "broken"
                break
            if C[j] > hi:
                outcome = "signal"
                break
            if C[j] < lo:
                outcome = "cancelled"
                break
        rec.update(outcome=outcome, i_outcome=j, outcome_date=pd.Timestamp(dates[j]))
        out.append(rec)
        last_end = t
        if outcome == "open_at_data_end":
            break
        t = j + 1
    return out


def detect_all(data, cal, start_i=260):
    """{ticker: arrays} -> DataFrame of every base (all outcomes)."""
    cal_pos = {pd.Timestamp(d).normalize(): k for k, d in enumerate(pd.DatetimeIndex(cal))}
    rows = []
    for t, x in data.items():
        sess = session_index(x["dates"], cal_pos)
        for r in scan(x, sess, start_i):
            r["ticker"] = t
            if r["outcome"] == "signal":
                j = r["i_outcome"]
                r.update(i=j, signal_date=r["outcome_date"], close=float(x["C"][j]),
                         stop=r["base_high"] * STOP_MULT)
            rows.append(r)
    cols = ["ticker", "i_start", "i_end", "base_start", "base_end", "base_high", "base_low",
            "width_pct", "tr_ratio", "outcome", "i_outcome", "outcome_date", "i", "signal_date",
            "close", "stop"]
    return pd.DataFrame(rows).reindex(columns=cols)
