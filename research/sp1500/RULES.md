# Pre-registration — S&P 1500 expansion, short hypotheses, AI dataset (`sp1500-research/1.0`)

Committed before any real-data run. Nothing here is tuned on history; a change requires a new
`RULES_VERSION` and is reported as a new version, never silently.

## Isolation
Research-only branch. No change to the production Retest RS-first strategy, its parameters,
shared code in its fingerprint (`backtest.py`, `core.py`, `paper/*`), GitHub Actions schedules,
`paper/state`, `paper/data`, the bot or broker connections. All new code is in
`research/sp1500/`, outputs in `research/results/sp1500/`.

## Universe
S&P 500 + S&P MidCap 400 + S&P SmallCap 600, saved with source, retrieval time and sha256.
Overlaps (a ticker in two lists) are resolved only with dated evidence (dated holdings files or
dated change tables); unresolved overlaps are kept, flagged `ambiguous`, counted once in the
combined set and excluded from single-group comparisons. If only today's membership is
available, results carry an explicit **survivorship bias** flag.

## Long strategies (production definitions, unchanged)
breakout, retest, vcp, dbottom from `backtest.py`; RS >= 85; SPY > MA50 on the signal day;
stop 3 % beyond the level; entry next open; exit by stop or after 20 sessions; 10 bps per side.
Two effects are measured separately:
1. **universe expansion** — RS percentile measured against the **S&P 500** cross-section
   (same meaning of "RS 85" as production) for all 1500 stocks;
2. **RS base change** — RS percentile against the full **1500** cross-section.

## Short hypotheses v1 (independent, fixed)
| ID | Rule | RS filter | Market filter (primary / pre-registered alternative) |
|---|---|---|---|
| S1 `breakdown` | close below the lowest low of the previous 3 candles | RS <= 15 | SPY < MA50 / off |
| S2 `breakdown_retest` | mirror of production retest: breakdown 2–10 bars ago, bounce >= 3 % off the low, high retests the level within ±2 %, closes stayed <= level+2 %, today closes down and below the level | RS <= 15 | SPY < MA50 / off |
| S3 `failed_breakout` | close above prior 3-candle high 1–3 bars ago, closes held above it until yesterday, today closes back below | none | SPY < MA50 / off |

Execution (all shorts): short at next open; **no trade if the open is at/above the stop**;
stop = stop_base × 1.03; stop on the entry bar fills at the stop, later bars at max(open, stop)
(gap through the stop); time exit at the close of the 20th session; liquidity filter price >= $10
and 20-day average dollar volume >= $20M.

Costs: 10 bps per side base; slippage scenarios 10/25/50 bps per side; borrow scenarios 0.25 %,
3 %, 10 %, 30 % per year on the short notional for the holding days (/360); **dividends paid**
by the short for ex-dates inside the holding period (from Yahoo dividend actions).
Borrow availability, locate, and recall risk are **not observable** in the data: short results
are labelled *preliminary, not executable*.

## Ambiguity rules
- Daily bars only. If the stop and the +2R research target are both inside the same candle,
  the outcome is `ambiguous_same_bar` and valued conservatively as the stop.
- Missing ticker bars on a market session: horizons count **market sessions** (SPY calendar);
  a missing bar on the horizon session leaves that label empty with reason `missing_bar`.

## Labels (outcomes) — origin of each horizon
* `px_ret_h` (h = 1/5/10/20): price move from the **signal-session close** to the close h market
  sessions later, signed by direction. Observable on that session's date.
* Model trade: entry at the **next session's open**, exit by stop / 20-session time exit; net R
  after costs; MFE/MAE from the entry price over the holding window; barrier label (+2R vs stop).
  Observable on the exit date.
* Portfolio result: separate backtest (long only, existing engine), never mixed into labels.
A label is written only when its observation date <= data end, with that date stored.

## AI dataset
Every detection (incl. rejected, with reason), unique ID, decision-time features only,
historical kind only (never mixed with forward data), chronological train / validation / test
(60 / 20 / 20 % of signal dates) with a purge of 20 sessions + 5-session embargo between splits.
No model is trained; nothing is connected to the bot.
