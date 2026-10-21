"""Bull flag v1 detector — exact implementation of PREREG_BULLFLAG_v1 §2 (R1-R9).

flag_at(x, i) -> (level, stop_base) or None, same interface as backtest.RULES, where
x = backtest.indicators(df) (arrays H, L, C, V, ...). Uses only bars <= i.
"""
import numpy as np

VERSION = "bullflag/1.0"
FLAG_MIN, FLAG_MAX = 3, 12          # flag length in sessions (bars T+1 .. i-1)
POLE_MAX = 15                       # pole_low searched in bars T-15 .. T
POLE_MIN_GAIN = 0.12                # H[T] / pole_low - 1 >= 12 %
DEPTH_MIN, DEPTH_MAX = 0.03, 0.12   # flag depth from H[T]
MAX_RETRACE = 0.50                  # of the pole height
MIN_BARS = 260                      # backtest.WARMUP (RS needs a year of history)


def flag_at(x, i, return_detail=False):
    H, L, C, V = x["H"], x["L"], x["C"], x["V"]
    if i < max(MIN_BARS, FLAG_MAX + POLE_MAX + 2) or i >= len(C):
        return None
    # R1: flag top = latest bar with the highest high among i-13 .. i-4
    lo, hi = i - FLAG_MAX - 1, i - FLAG_MIN - 1
    win = H[lo:hi + 1]
    if not np.isfinite(win).all():
        return None
    T = lo + int(np.flatnonzero(win == win.max())[-1])
    flag = slice(T + 1, i)                                   # bars T+1 .. i-1
    n_flag = i - 1 - T
    if not FLAG_MIN <= n_flag <= FLAG_MAX:
        return None
    top = H[T]
    # R2: the top is the highest high of the pole AND the flag (bars T-15 .. i-1), so a
    #     longer flag whose real top lies outside the R1 window is not re-read as a shorter one
    if H[T - POLE_MAX:i].max() > top:
        return None
    # R3: pole
    pole = slice(T - POLE_MAX, T + 1)
    P = T - POLE_MAX + int(np.argmin(L[pole]))
    pole_low = L[P]
    if not (P < T and pole_low > 0 and top / pole_low - 1 >= POLE_MIN_GAIN):
        return None
    # R4, R5: depth and retracement
    flag_low = L[flag].min()
    depth = 1 - flag_low / top
    if not DEPTH_MIN <= depth <= DEPTH_MAX:
        return None
    if (top - flag_low) / (top - pole_low) > MAX_RETRACE:
        return None
    # R6: volume dries up in the flag
    v_flag = V[flag].mean()
    if not v_flag < V[P:T + 1].mean():
        return None
    # R7, R8: breakout above the flag's upper boundary, first close above, on rising volume
    flag_high = H[flag].max()
    if not (C[i] > flag_high and C[i - 1] <= flag_high and V[i] > v_flag):
        return None
    # R9
    level, stop_base = float(flag_high), float(min(flag_low, L[i]))
    if return_detail:
        return dict(level=level, stop_base=stop_base, T=T, P=P, n_flag=n_flag,
                    pole_gain=top / pole_low - 1, depth=depth,
                    retrace=(top - flag_low) / (top - pole_low))
    return level, stop_base
