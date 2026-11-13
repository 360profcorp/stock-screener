# Long Breakout / Retest: crisis protection, 10 years — pre-registration

Written **before** any long result on the 10-year data has been computed. Research only. Paper,
trading, positions, stops and `TRADING=dry` are not changed; nothing is merged into main
without a separate decision.

## 1. Question
Do two simple protections reduce the losses of the long books in the 2020 and 2022 crises,
and what do they cost in return and in the recovery after the crisis?
- an **SPY > MA200** entry filter;
- a **portfolio drawdown circuit breaker**.

## 2. Data
- **Prices:** the 10-year bars already downloaded for the short study (dataset run
  40152515701, `bars.pkl.gz`): Yahoo daily, `auto_adjust=False`, sessions
  2016-10-24 → 2026-10-23. No new download, so every variant sees the same prices.
- **Universe:** point-in-time S&P 500 members on the signal day, from the community
  snapshot dataset `sp500_pit_fja05680.csv` of the same run. The current list applies after
  the last snapshot (2026-08-18). RS is measured against that day's members.
- **Survivorship:** of the former members requested, only those with Yahoo data are
  included (219 of 670 for the whole S&P 1500). Missing failed companies make **long**
  results look **better** than reality, by an unknown amount. This bias is the same for every
  variant, so the comparison between variants is less affected than the absolute numbers.

## 3. Signals and execution (production rules, unchanged)
- Breakout (lookback 3) and Retest from `backtest.py`, detected by the research engine
  (`research.sp1500.engine.detect`) with `rs_pit500`.
- **Eligible:** PIT member, RS ≥ 85, SPY close > MA50 on the signal day. These are the
  current rules.
- **Trades:** `backtest.simulate(entry_at="open", one_per_ticker=False, include_open=True)`:
  next-open entry; stop = stop base × 0.97 (on the entry bar at the stop, later at
  min(open, stop)); exit at the close of the 20th bar.
- **Portfolio:** `portfolio_bt.replay`, unchanged: $10,000, 1 % risk, 5 positions, 3 new per
  day, 20 % cap, RS-first order, open positions marked at the end.
- **Costs:** 10 bps per side; **stress 25 bps** reported for every variant.

## 4. Variants (all parameters fixed here, no search)
| Id | Rule |
|---|---|
| **C** control | current rules |
| **M** MA200 | C + SPY close > MA200 on the signal day (both from bars ≤ the signal day) |
| **D10** drawdown breaker 10 % | C; when the book's equity at a close is ≥ 10 % below its reference peak, no new entries for the next 20 sessions. Open positions keep their stops and exits. After the pause the reference peak restarts at the equity of that day |
| **D15** drawdown breaker 15 % | as D10 with 15 % |
| **MD10** | M + D10 |

Breakers use only the book's own equity at the close before the entry session. They are
implemented by removing the paused entries from the candidate list and re-running the
unchanged `portfolio_bt.replay` until no new trigger appears. A test checks that without
triggers it equals the plain replay exactly.

## 5. Reported for each strategy × variant
- **Overall:** return, CAGR, max drawdown, profit factor (closed trades, net $), trades,
  yearly returns.
- **Crisis and recovery windows:**
  - COVID crash 2020-02-19 → 2020-03-23;
  - COVID recovery 2020-03-24 → 2020-12-31;
  - 2022 bear 2022-01-03 → 2022-10-12;
  - 2022 rebound 2022-10-13 → 2023-07-31.

  Each window gets the book return, the SPY price return and the book return ÷ SPY return
  (recovery capture).
- **Recovery after the deepest drawdown:** sessions from the trough to a new equity high, or
  "not recovered".
- **Development** 2017-10 → 2021-12 and **holdout** 2022-01-03 → end, each as a fresh book.

## 6. Decision rule (fixed now)
A variant is a **candidate for a separate paper test** (owner decision) only if, for **both
Breakout and Retest**, in **both** the development and the holdout book:
- its max drawdown is at least **3 percentage points** shallower than C's; **and**
- its CAGR is no more than **2 percentage points** below C's; **and**
- the same two conditions hold at **25 bps**.

Otherwise the current rules stay. With 5 variants tested, a pass on history alone is weak
evidence; only forward paper data can confirm it.
