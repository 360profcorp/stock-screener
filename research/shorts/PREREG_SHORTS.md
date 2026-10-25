# Short strategies on 10 years: pre-registration (written BEFORE the 10-year data is loaded)

Research only. The live bot, long strategies, stops, positions and `TRADING=dry` are not
touched. No short is traded, on paper or for real, as a result of this study without a
separate decision by the owner.

## 1. Question
Does any of the three pre-registered short setups have a **robust positive net edge** in sharp
crashes and prolonged bear markets, after costs, borrow and dividends, and does it hold
**out of sample**?

## 2. Data
- Re-run the existing research engine (`research.sp1500.run`, rules `sp1500-research/1.0`)
  with **`--period 10y`**: Yahoo daily bars, `auto_adjust=False`, dividends kept separately.
  The run starts ~2016-10; with the 260-bar warm-up, signals start ~2017-10.
- Universe and membership:
  - **Primary:** point-in-time S&P 500 members on the signal day (community snapshot
    dataset), RS against that day's members (`rs_pit500`).
  - **Secondary:** today's S&P 500; the S&P 1500 combined **without** the `ambiguous` group;
    and, reported separately, the S&P 1500 **with** `ambiguous`.
- **Survivorship:** delisted and removed companies are largely missing from Yahoo. For
  shorts this biases results **downward** (failed companies are the best shorts) and also
  removes some of the worst squeezes; the size is unknown and the count of missing former
  members is reported.
- **Borrow availability is unknown.** No locate, borrow-rate or hard-to-borrow history is
  available. Every short is assumed borrowable, and several borrow-fee scenarios are reported.
  This is a stated risk, not a result.
- Decision-time data only: detection, RS and filters use bars up to the signal day (the
  engine's tests check this); trades enter at the next open.

## 3. Rules (unchanged, `research/sp1500/rules.py`)
| Setup | Signal (close of day i) | Stop base |
|---|---|---|
| S1 **Breakdown** | close < lowest low of the prior 20 sessions; previous close ≥ it | highest high of the last 3 bars |
| S2 **Breakdown retest** | breakdown 2–10 bars ago; rally ≥ 3 % off the trough back to within ±2 % of the broken support; closes stayed ≤ support + 2 %; today closes below support and below yesterday | max(support, rally high) |
| S3 **Failed breakout** | close above the prior 20-session high 1–5 bars ago; today closes back below that level and below yesterday's low | highest high since the breakout |

- **Filters:** RS ≤ 20, price ≥ $5, 20-day dollar volume ≥ $5 M, valid stop.
  - **Market `primary`:** SPY close **below** MA50 on the signal day.
  - **Market `off`:** no market filter.
- **Trade:** short at the next open; stop = stop base × 1.03.
  - If the open is at or above the stop, there is no trade.
  - On the entry bar the stop fills at the stop; on later bars at max(open, stop).
  - Otherwise the trade exits at the close of the 20th bar.
- **Nothing is tuned.** No parameter of the rules or filters is chosen on any part of the
  data.

## 4. Costs (recomputed from prices, not renamed)
- Slippage + commission per side: **10 / 25 / 50 bps** (`base` / `wide` / `stress`).
- Borrow fee on calendar days held, APR: **0.25 % / 3 % / 10 % / 30 %** (`gc` / `warm` /
  `hot` / `htb`).
- Dividends: every ex-date in (entry, exit] is paid by the short.
- That gives 12 net scenarios plus gross. **Primary net = base + warm.**
- Each net value is recomputed from the trade's entry, exit, risk, days held and dividends.
  A test reproduces the engine's numbers from first principles.

## 5. Statistics
- **Signal level:** for gross and each of the 12 net scenarios: trades, win rate, profit
  factor, expectancy (mean R), median R.
- **Overlap:** the decision statistics use non-overlapping trades: per ticker and setup, a
  signal is skipped while the previous model trade is open. This is the engine's
  `non_overlapping`, which a test checks against `backtest.simulate(one_per_ticker=True)`.
  All-signal numbers are shown for reference only.
- **Uncertainty:** 90 % interval resampling calendar months, 5,000 draws, seed 20261024.
- **Periods** (signal date):
  - **COVID crash** 2020-02-20 → 2020-03-23;
  - **COVID recovery** 2020-03-24 → 2020-12-31;
  - **2022 bear** 2022-01-03 → 2022-10-12;
  - **2022 rebound** 2022-10-13 → 2023-07-31;
  - **other** 2023-08-01 → end;
  - also each calendar year.
- **Portfolio** (separate from signal statistics, never mixed): one short-only book per
  setup.
  - $10,000 start, 1 % risk per trade, 5 positions, 3 new per day, 20 % notional cap per
    position.
  - Same-day order: weakest RS first, then ticker.
  - Primary net costs (10 bps per side, 3 % borrow, dividends paid); marked at the close.
  - Reported: equity curve, max drawdown, yearly return, trades.
  - Run on the full period and separately on the holdout only (a fresh book on 2022-01-01).

## 6. Development / holdout
- **Development:** signals before 2022-01-01 (includes 2018 Q4 and the 2020 crash).
  **Holdout:** 2022-01-01 → end (the 2022 bear, its rebound and 2023–2026).
- The development period only decides which **setup × market variant** (6 combinations,
  primary universe) **advances**. Nothing else is chosen there.
- **Advance (development, PIT S&P 500, non-overlapping, primary net):** ≥ 30 trades, mean
  net R > 0 and profit factor > 1.
- **Confirmed (holdout, same population, all must hold):**
  - **H1:** ≥ 30 trades.
  - **H2:** mean net R > 0 (primary net) with the 90 % interval's lower bound > 0.
  - **H3:** mean net R > 0 at 25 bps + 3 % borrow.
  - **H4:** mean net R > 0 in the 2022 bear.
  - **H5:** holdout portfolio return > 0.
- **If nothing is confirmed, short strategies v1 are rejected. No re-parametrisation in
  v1.** A confirmed setup may only go to a separate **paper** book after an owner decision;
  live shorts stay off.

## 7. Audit points from Muse (checked in code and reported)
1. `eligible_primary` for shorts ⇔ SPY below MA50 (plus RS / liquidity / stop);
   `eligible_off` ⇔ the same without the market filter. Both are recomputed from the dataset
   and compared row by row.
2. Win rate, PF and expectancy per gross and each net scenario (§5).
3. Costs, slippage, borrow and dividends recomputed (§4).
4. Non-overlap rule = engine = production simulate (§5).
5. `ambiguous` membership shown explicitly: the S&P 1500 combined is reported without and
   with it.
6. Real coverage dates (first and last bar, sessions per year) and the signal count per year,
   so the presence of 2020 and 2022 signals is shown, not assumed.

## Change log
- 2026-10-25, before any 10-year result: the first 10-year run of the full engine (long and
  short rules) was killed by the runner after about 65 minutes, with no output. The dataset is
  now built with `--shorts-only`: the same engine and the same short rules, without the long
  detections, long tables and long portfolios. No rule, filter or parameter changed.
