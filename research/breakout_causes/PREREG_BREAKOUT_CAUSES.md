# Why research Breakout is weak: execution audit and three hypotheses (pre-registration)

Written **before** any new calculation. The owner's instruction is dated 2026-10-25.

**Context.** The PR #22 diagnostic was accepted and the strategy stays unchanged.

**Research only:**
- no new paper book until a separate decision;
- Production, Retest Paper, Trading, positions, stops and `TRADING=dry` are unchanged;
- nothing is merged into `main`.

Research Breakout enters at the **next open**. It is not the bot's pre-close breakout.

**Status: exploratory.** The 2017–2026 data were already examined in PR #19 and PR #22. In
particular, PR #22 showed that tight stops and SPY below its MA200 coincide with weak
Breakout trades. Nothing here is independent confirmation. Each threshold below is fixed
from a stated mechanical reason, never by searching for the most profitable value. Only one
variant per hypothesis is run, and no other value is tried.

## 0. Common base (identical for every book)
- **Data:** dataset run 40152515701 (2016-10-24 → 2026-10-23), loaded with
  `research.crisis.run.load` / `build`. Universe: PIT S&P 500.
- **Control C (PR #19):**
  - eligibility: PIT member, RS ≥ 85 (`rs_pit500`), SPY > MA50;
  - Breakout with lookback 3, entry at the next open, stop = base × 0.97;
  - exit by stop (a gap fills at the open) or at the close of the 20th bar.
- **Portfolio:** `portfolio_bt.replay` unchanged: $10,000, 1 % risk, 5 positions, 3 new a
  day, 20 % cap, RS-first, **10 and 25 bps per side**, open positions marked at the end.
- **Windows:**
  - full: 2017-11-03 → 2026-10-23;
  - first half: → 2021-12-31;
  - second half: 2022-01-03 → end.
  
  Each half is a fresh $10,000 book.
- **Reported for every book:** return, CAGR, max drawdown, profit factor, trades,
  expectancy (R), yearly returns.

## 1. Execution audit (descriptive, no rule change)
**Per executed control trade**, net R is split exactly into signal quality and execution
mechanics. R is measured on the risk at the signal close, `risk_sig = close_sig − stop`:

| Part | Formula |
|---|---|
| signal quality | (exit at the planned stop, or the time-exit close) − close_sig |
| entry gap | −(open − close_sig) |
| stop gap | exit − stop, for gap-through stops |
| costs | −(entry + exit) × fee |

The parts add up exactly to `(exit − entry − costs) / risk_sig`. The same split is also
reported for all candidates and for the non-overlapping model trades.

**Also reported:**
- **Gaps at the open:**
  - distribution of (open − close_sig)/close_sig and of the gap as a share of risk_sig;
  - outcome by gap bucket;
  - candidates not traded because the open was at or below the stop.
- **Entry-day stops:** count, R, $, and their share among tight stops.
- **Costs** in $ and R at 10 and 25 bps.
- **Stop width:** the risk_pct buckets of PR #22 at 10 and 25 bps — gross R, cost R, stop
  rate, entry-day stop rate.

## 2. After a 20-day exit: stock vs SPY on the same dates
For every executed control trade closed by time (also for stops, for contrast):
- the stock's close-to-close return over +5 / +10 / +20 sessions after the exit day;
- **minus** SPY's return over the same dates.

Reported: mean, median, % positive, and a bootstrap 90 % interval of the mean excess,
resampled by exit month. Raw stock returns are also shown, so general market drift is not
read as missed alpha. This is hindsight, not a trading rule.

## 3. Hypotheses (one fixed variant each, Breakout only)
| | Hypothesis | Exact rule | Fixed from |
|---|---|---|---|
| **H1** | entry-quality filter | take a candidate only if its planned risk at the actual open, (open − stop)/open, is **≥ 4.0 %** | **cost budget:** at 10 bps per side a round trip costs 0.20 % of the price. A 4 % risk keeps that at ≤ 0.05 R. The threshold is not chosen from P&L. The same 4 % is used at 25 bps, where it gives 0.125 R, to keep one rule |
| **H2** | market regime MA50 + MA200 | eligible only if SPY > MA50 **and** SPY > MA200 on the signal day | the PR #19 variant M, rerun here with the full metric set |
| **H3** | keep a strong position past day 20 | at the close of the 20th bar, a position is **strong** if that close ≥ entry + 1 R (R = entry − stop). Weak positions exit there as now. Strong positions get from bar 21 a **protective trailing stop** = max(entry, highest close since entry − 1 R), checked like the original stop (a gap fills at the open), plus a hard exit at the close of bar **60** | 1 R = the trade's own original risk unit; 60 = 3 × the base 20 bars |

**H3 details:**
- The trailing level uses closes up to the previous session only, so there is no
  look-ahead.
- Everything else, including sizing and slots, stays as in C. Longer holds occupy slots, and
  the portfolio replay accounts for that.

## 4. Benchmarks and decision (applied unchanged)
**Random-removal benchmark (H1, H2).** The filter removes some candidates. 200 books (seeds
1–200) remove the **same number** of candidates at random, at 10 bps, on the full window.
This separates "fewer trades / different slot use" from "better selection".

**A hypothesis is "supported (exploratory)" only if all of these hold:**
1. full window at **10 and 25 bps**: return > C and profit factor > C;
2. max drawdown not more than 3 points deeper than C at 10 bps;
3. return > C in **both** halves at 10 bps;
4. for H1 / H2: full-window 10 bps return above the **80th percentile** of the
   random-removal books.

**Otherwise "not supported".**

Even "supported" means only a candidate for a separately approved forward paper test. No
paper book is started here.

## 5. Outputs
`research/results/breakout_causes/runs/<UTC>/`, write-once:
- `REPORT.md` with charts;
- `results.json`;
- per-book trade lists and equity CSVs;
- `execution_audit.csv`;
- `post_exit_vs_spy.csv`;
- `provenance.json`.

**Reproduction gate:** C must reproduce PR #19 / PR #22 exactly at 10 and 25 bps before
anything is reported. If it does not, the run stops.
