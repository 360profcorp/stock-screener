# Long Breakout / Retest crisis protection, 10 years — findings

Pre-registration: `PREREG_CRISIS.md`, committed before any long result on the 10-year data.
- Run: `research/results/crisis/runs/2026-10-25T0255Z/` (`results.json`, `books.csv`, equity
  curves).
- Data: the 10-year bars of dataset run 40152515701, sessions 2016-10-24 → 2026-10-23.
- Universe: point-in-time S&P 500, 726 tickers ever members, 609 with prices.
- Execution and costs: production rules and engine, 10 bps per side, stress test at 25 bps.

## Verdict
**No variant meets the pre-registered rule; the current rules stay.**

The rule needed a gain for both Breakout and Retest, in both the development and the holdout
period, and at both cost levels. No variant got that.

## 1. The most important finding is about the current strategy itself
Over 10 years the control books are roughly **flat with ~48 % drawdowns**:

| Control (current rules), 10 bps | 2017–2026 | CAGR | Max DD | PF | Development 2017–2021 | Holdout 2022→ |
|---|---|---|---|---|---|---|
| Breakout | −6.5 % | −0.8 % | −47.7 % | 0.97 | −15.3 % (DD −37 %) | +22.6 % (DD −36 %) |
| Retest RS-first | +1.3 % | +0.1 % | −48.1 % | 1.01 | **−30.4 %** (DD −36 %) | **+70.7 %** (DD −23 %) |

- Retest's holdout figure is consistent with the earlier 5-year study (+68 % from 2022-10).
- **2017–2021 was a losing period for both books: 2018 −22 % each, then 2019–2021
  negative or flat.** The edge seen since 2022 does not hold over the decade.
- At 25 bps, retest ends at −20 % and breakout at −43 % over 10 years.

Caveats:
- Prices of removed companies are partly missing (survivorship), which most likely
  **flatters** long results.
- The 2017–2021 losses therefore probably are not a data artefact against the strategy, but
  this has not been proven.

## 2. Variants (full period, 10 bps; holdout in brackets)
| Breakout | Return | CAGR | Max DD | PF | Holdout CAGR / DD |
|---|---|---|---|---|---|
| C | −6.5 % | −0.8 % | −47.7 % | 0.97 | 4.3 % / −35.9 % |
| **M (SPY > MA200)** | **+47.8 %** | **4.5 %** | **−32.7 %** | 1.14 | **10.3 % / −19.9 %** |
| D10 | −7.8 % | −0.9 % | −53.3 % | 0.96 | 6.2 % / −31.3 % |
| D15 | −36.7 % | −5.0 % | −58.2 % | 0.86 | −2.8 % / −32.9 % |
| MD10 | +73.2 % | 6.3 % | −32.2 % | 1.20 | 11.8 % / −18.7 % |

| Retest | Return | CAGR | Max DD | PF | Holdout CAGR / DD |
|---|---|---|---|---|---|
| C | +1.3 % | 0.1 % | −48.1 % | 1.01 | 11.8 % / −22.9 % |
| M | −4.4 % | −0.5 % | −45.3 % | 0.98 | 8.8 % / −22.1 % |
| D10 | −11.1 % | −1.3 % | −49.9 % | 0.93 | 10.5 % / −21.4 % |
| D15 | +28.8 % | 2.9 % | −40.9 % | 1.12 | 12.1 % / −20.0 % |
| MD10 | +18.6 % | 1.9 % | −38.6 % | 1.08 | 7.8 % / −20.0 % |

- **The MA200 filter helps Breakout clearly** in both periods (development DD −32 % vs
  −37 %; holdout DD −20 % vs −36 % with a higher CAGR). It **does not help Retest**: CAGR is
  lower and DD about the same. The pre-registered rule needed both strategies, so it fails.
  For breakout it held in development and holdout, and in the holdout also at 25 bps
  (CAGR −1.6 % → +7.5 %). An MA200 filter for breakout alone could only be a new,
  separately registered hypothesis checked forward, because this result was seen first.
- **The drawdown breakers do not work as protection.** They often make the drawdown deeper,
  because they pause entries close to the bottom and miss the rebound. Breakout D10 and D15
  never get back to their previous equity peak. Results swing with the threshold (Retest D10
  −11 %, D15 +29 %): a sign of chance, not of a robust rule.

## 3. Crises and recoveries (full-period books, 10 bps; book % vs SPY %)
| Window | SPY | Breakout C | Breakout M | Retest C | Retest M |
|---|---|---|---|---|---|
| COVID crash 02-19 → 03-23-2020 | −33.8 % | −9.0 % | −9.0 % | −8.1 % | −6.3 % |
| COVID recovery → 2020-12-31 | +67.7 % | +20.1 % (0.30×) | +11.4 % (0.17×) | +2.0 % (0.03×) | +4.8 % (0.07×) |
| 2022 bear 01-03 → 10-12 | −24.9 % | −22.0 % | **−10.3 %** | −6.5 % | −9.0 % |
| 2022 rebound → 2023-07-31 | +28.4 % | +3.9 % (0.14×) | +9.5 % (0.34×) | −6.1 % | −6.8 % |

- The **COVID crash cost both books about 8–10 %**, much less than SPY: the SPY > MA50 filter
  already stopped new entries, and the stops cut the open ones.
- The **recoveries are where the books lag most**:
  - After COVID, retest caught only 3 % of SPY's +68 %. The MA50 filter keeps it out early,
    and the pullback setups are rare in a V-shaped rally.
  - After 2022, retest lost money during the rebound.
- **Sessions from the worst trough to a new high:**

  | Book | Sessions |
  |---|---|
  | Breakout C | 768 |
  | Breakout M | 419 |
  | Retest C | 659 |
  | Retest M, D10 | not recovered by 2026-10 |

## 4. What follows (nothing is changed; owner decisions)
1. **Do not adopt** MA200 or a drawdown breaker for both books: the pre-registered test
   failed.
2. **Retest RS-first has a weak 10-year record.** Its strong results come from 2022–2026. The
   live paper book is the right place to keep watching it; this backtest is not a reason to
   change it, but it is a reason not to expect the 2022–2026 numbers to repeat.
3. **A possible separate hypothesis:** an SPY > MA200 entry filter for **Breakout only**. It
   would need a new pre-registration and a forward paper test, because the decade has now
   been seen.

Overfitting: 5 variants × 2 strategies were looked at. A single good cell on history is weak
evidence, which is why the rule required consistency across both strategies, periods and cost
levels.
