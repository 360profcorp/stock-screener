"""Pre-registered strategy rules for the S&P 1500 / short research (RULES_VERSION below).

Committed BEFORE any real-data run. Parameters are fixed here and are NOT tuned on history.
Long rules are imported unchanged from backtest.py (the validated production definitions are
only read, never modified). Short rules are mirror images of the long rules, written once.
"""
import numpy as np

import backtest as bt

RULES_VERSION = "sp1500-research/1.0"

# ---------------------------------------------------------------- shared, fixed parameters
LOOKBACK = 3            # candles a breakout / breakdown must clear (same as production)
STOP_BUF_PCT = 3.0      # stop buffer beyond the level (same as production)
HOLD = 20               # time exit after 20 sessions (same as production)
ENTRY = "next_open"     # entry at the open of the session after the signal (bot's Retest entry)
COST_BPS_SIDE = 10.0    # commission + slippage per side, base case (same as Task 6/9/10)
MIN_RS_LONG = 85        # long filter (same as production)
MAX_RS_SHORT = 15       # short filter: mirror of RS >= 85 (weakest 15 %)
SHORT_MIN_PRICE = 10.0  # liquidity / shortability proxies for shorts (fixed, not tuned)
SHORT_MIN_ADV_USD = 20e6
LABEL_HORIZONS = (1, 5, 10, 20)
BARRIER_TARGET_R = 2.0  # research label only: does +2R come before the stop within 20 sessions

# ---------------------------------------------------------------- cost scenarios (shorts)
BORROW_SCENARIOS_PCT_YR = {"gc": 0.25, "warm": 3.0, "hot": 10.0, "htb": 30.0}
SLIPPAGE_SCENARIOS_BPS = {"base": 10.0, "wide": 25.0, "stress": 50.0}

# market filters (SPY vs MA50 on the signal day)
LONG_MARKET = "spy_above_ma50"          # production rule
SHORT_MARKET = "spy_below_ma50"         # mirror, primary variant
SHORT_MARKET_ALT = "off"                # pre-registered sensitivity variant (reported, not chosen)


# ---------------------------------------------------------------- long rules (unchanged)
LONG_RULES = {
    "breakout": lambda x, i: bt.breakout_at(x, i, LOOKBACK),
    "retest": lambda x, i: bt.retest_at(x, i, LOOKBACK),
    "vcp": lambda x, i: bt.vcp_at(x, i),
    "dbottom": lambda x, i: bt.dbottom_at(x, i),
}


# ---------------------------------------------------------------- short rules v1
def breakdown_at(x, i, lookback=LOOKBACK):
    """S1 support breakdown: close below the lowest low of the previous `lookback` candles.
    Returns (level, stop_base) — the stop goes STOP_BUF_PCT above stop_base."""
    if i < lookback:
        return None
    level = x["L"][i - lookback:i].min()
    return (level, level) if x["C"][i] < level else None


def breakdown_retest_at(x, i, lookback=LOOKBACK, max_days=10, tol=0.02, min_bounce=0.03):
    """S2 breakdown + retest from below (mirror of backtest.retest_at):
    a breakdown at bar b (2..max_days bars ago); price then bounces >= min_bounce off its
    low and retests the broken level from below (high within +-tol of the level); closes
    stayed <= level*(1+tol); today closes down and below the level."""
    H, L, C = x["H"], x["L"], x["C"]
    if i + 1 < lookback + max_days + 2 or not C[i] < C[i - 1]:
        return None
    for b in range(i - 2, i - max_days - 1, -1):
        level = L[b - lookback:b].min()
        if C[b] >= level:
            continue
        trough_idx = b + int(np.argmin(L[b:i]))
        trough = L[trough_idx]
        bounce = H[trough_idx + 1:i + 1]
        if len(bounce) == 0:
            continue
        bounce_high = bounce.max()
        touched = level * (1 - tol) <= bounce_high <= level * (1 + tol)
        deep_enough = bounce_high >= trough * (1 + min_bounce)
        held = C[b + 1:i + 1].max() <= level * (1 + tol)
        if touched and deep_enough and held and C[i] < level:
            return level, max(level, bounce_high)
    return None


def failed_breakout_at(x, i, lookback=LOOKBACK, max_fail_days=3):
    """S3 failed resistance breakout (bull trap): a close above the prior `lookback`-candle
    high at bar b (1..max_fail_days bars ago), closes stayed above that level until
    yesterday, and today closes back below it. Stop base = highest high since b."""
    H, C = x["H"], x["C"]
    for b in range(i - 1, i - max_fail_days - 1, -1):
        if b < lookback:
            return None
        level = H[b - lookback:b].max()
        if C[b] <= level:
            continue
        if (C[b + 1:i] > level).all() and C[i] < level:
            return level, H[b:i + 1].max()
        return None                     # most recent breakout decides; no older search
    return None


SHORT_RULES = {"breakdown": breakdown_at, "breakdown_retest": breakdown_retest_at,
               "failed_breakout": failed_breakout_at}
SHORT_RS_FILTER = {"breakdown": True, "breakdown_retest": True, "failed_breakout": False}
DIRECTION = {**{k: "long" for k in LONG_RULES}, **{k: "short" for k in SHORT_RULES}}
