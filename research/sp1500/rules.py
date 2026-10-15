"""Pre-registered strategy rules for the S&P 1500 / short research (RULES_VERSION below).

Fixed BEFORE any real-data run and NOT tuned on history.
* Long rules: production definitions imported unchanged from backtest.py (read only).
* Short rules: independent hypotheses taken from the owner-supplied draft
  `research/expansion.py` (SP1500_Shorts_AI_Research_v1, prepared against main d54c6dd,
  never run on market data). They are NOT mirror images of the long rules: 20-session
  support / resistance, a fresh-breakdown condition, and a failed-breakout trigger that
  needs a close below the prior day's low. Parameters below are copied verbatim.
History: an earlier local draft (mirror rules) was replaced on the owner's instruction
before any market data was loaded; it was never run.
"""
import numpy as np

import backtest as bt

RULES_VERSION = "sp1500-research/1.0"

# ---------------------------------------------------------------- long (production, unchanged)
LONG_LOOKBACK = 3
LONG_STOP_BUF_PCT = 3.0
MIN_RS_LONG = 85
LONG_RULES = {
    "breakout": lambda x, i: bt.breakout_at(x, i, LONG_LOOKBACK),
    "retest": lambda x, i: bt.retest_at(x, i, LONG_LOOKBACK),
    "vcp": lambda x, i: bt.vcp_at(x, i),
    "dbottom": lambda x, i: bt.dbottom_at(x, i),
}

# ---------------------------------------------------------------- short (independent hypotheses)
SHORT_WINDOW = 20          # support / resistance window
SHORT_STOP_BUF_PCT = 3.0   # stop = stop_base * 1.03
MAX_RS_SHORT = 20          # RS <= 20 (draft value)
MIN_PRICE = 5.0            # liquidity filter for shorts (draft value)
MIN_ADV_USD = 5e6          # 20-day mean dollar volume (draft value)


def breakdown_at(x, i):
    """S1 fresh support breakdown: today closes below the lowest low of the previous 20
    sessions while yesterday closed at/above it. Stop base: highest high of the last 3 bars."""
    C, H, L = x["C"], x["H"], x["L"]
    if i < 30:
        return None
    level = L[i - SHORT_WINDOW:i].min()
    if C[i] < level and C[i - 1] >= level:
        return level, H[i - 2:i + 1].max()
    return None


def breakdown_retest_at(x, i):
    """S2 breakdown then retest from below: a close below the prior 20-session support at bar
    b (2..10 bars ago); afterwards a rally off the trough of >= 3 % whose high comes back to
    within +-2 % of the broken support; closes stayed <= support + 2 %; today closes below
    support and below yesterday. Stop base: max(support, rally high)."""
    C, H, L = x["C"], x["H"], x["L"]
    if i < 30:
        return None
    for b in range(i - 2, max(20, i - 11), -1):
        support = L[b - SHORT_WINDOW:b].min()
        if C[b] >= support:
            continue
        trough = b + int(np.argmin(L[b:i]))
        rally = H[trough + 1:i + 1]
        if (len(rally) and support * .98 <= rally.max() <= support * 1.02
                and rally.max() >= L[trough] * 1.03
                and C[b + 1:i + 1].max() <= support * 1.02
                and C[i] < support and C[i] < C[i - 1]):
            return support, max(support, rally.max())
    return None


def failed_breakout_at(x, i):
    """S3 failed resistance breakout: a close above the prior 20-session high at bar b
    (1..5 bars ago), and today closes back below that resistance AND below yesterday's low.
    Stop base: highest high since the breakout bar."""
    C, H, L = x["C"], x["H"], x["L"]
    if i < 30:
        return None
    for b in range(i - 1, max(20, i - 6), -1):
        resistance = H[b - SHORT_WINDOW:b].max()
        if C[b] > resistance and C[i] < resistance and C[i] < L[i - 1]:
            return resistance, H[b:i + 1].max()
    return None


SHORT_RULES = {"breakdown": breakdown_at, "breakdown_retest": breakdown_retest_at,
               "failed_breakout": failed_breakout_at}
DIRECTION = {**{k: "long" for k in LONG_RULES}, **{k: "short" for k in SHORT_RULES}}
STOP_BUF = {**{k: LONG_STOP_BUF_PCT for k in LONG_RULES},
            **{k: SHORT_STOP_BUF_PCT for k in SHORT_RULES}}

# ---------------------------------------------------------------- execution / costs / labels
ENTRY = "next_open"        # all strategies: entry at the next session's open
HOLD = 20                  # model trade: stop or time exit after 20 sessions (production)
COST_BPS_SIDE = 10.0       # base commission + slippage per side
SLIPPAGE_SCENARIOS_BPS = {"base": 10.0, "wide": 25.0, "stress": 50.0}
BORROW_SCENARIOS_APR = {"unknown": None, "gc": 0.0025, "warm": 0.03, "hot": 0.10,
                        "htb": 0.30}
LABEL_HORIZONS = (1, 5, 10, 20)
BARRIER_TARGET_R = 4.0     # research label (draft value): +4R target vs stop, stop first
MARKET_VARIANTS = ("primary", "off")   # primary: long SPY>MA50, short SPY<MA50
