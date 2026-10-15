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

## Short hypotheses v1 (independent, fixed) — from the owner-supplied draft
Source: `SP1500_Shorts_AI_Research_v1` (`research/expansion.py`, prepared against main d54c6dd,
never run on market data). Copied verbatim; **not** mirror images of the long rules. An
earlier local mirror-rule draft was replaced on the owner's instruction before any data load.

| ID | Rule | Stop base (stop = ×1.03) |
|---|---|---|
| S1 `breakdown` | fresh breakdown: close < lowest low of previous 20 sessions, yesterday's close >= it | highest high of last 3 bars |
| S2 `breakdown_retest` | close below prior 20-session support 2–10 bars ago; rally >= 3 % off the trough whose high retests support within ±2 %; closes stayed <= support + 2 %; today closes below support and below yesterday | max(support, rally high) |
| S3 `failed_breakout` | close above prior 20-session high 1–5 bars ago; today closes below that resistance and below yesterday's low | highest high since the breakout |

Filters (all shorts): RS <= 20; price >= $5; 20-day mean dollar volume >= $5M; market: SPY <
MA50 (primary) and "off" (pre-registered sensitivity, reported, never selected).

Execution (all shorts): short at next open; **no trade if the open is at/above the stop**; stop on
the entry bar fills at the stop, later bars at max(open, stop) (gap through the stop); time exit
at the close of the 20th session after entry.

Costs: 10 bps per side base; slippage scenarios 10/25/50 bps per side; borrow scenarios
`unknown` (net result left empty), 0.25 %, 3 %, 10 %, 30 % APR on the short notional for the
calendar days held (/365); **dividends paid** by the short for ex-dates inside (entry, exit].
Borrow availability, locate and recall risk are **not observable**: short results are
*preliminary, not executable*.

## Ambiguity rules
- Daily bars only. If the stop and the +4R research target are both inside the same candle,
  the outcome is `ambiguous_same_bar` and valued conservatively as the stop.
- Missing ticker bars on a market session: horizons count **market sessions** (SPY calendar);
  a missing bar on the horizon session leaves that label empty with reason `missing_bar`.

## Labels (outcomes) — origin of each horizon
* `px_ret_h` (h = 1/5/10/20): price move from the **signal-session close** to the close h market
  sessions later, signed by direction. Observable on that session's date.
* Model trade: entry at the **next session's open**, exit by stop / 20-session time exit; net R
  after costs; MFE/MAE from the entry price over the holding window up to the exit; barrier
  label (+4R vs stop within 20 sessions, stop first on a shared candle).
  Observable on the exit date.
* Portfolio result: separate backtest (long only, existing engine), never mixed into labels.
A label is written only when its observation date <= data end, with that date stored.

## AI dataset
Every detection (incl. rejected, with reason), unique ID, decision-time features only,
historical kind only (never mixed with forward data), chronological train / validation / test
(60 / 20 / 20 % of signal dates) with a purge of 20 sessions + 5-session embargo between splits.
No model is trained; nothing is connected to the bot.
