# Retest RS-first v1 — diagnostic findings (historical backtest, PIT S&P 500)

Run `research/results/retest_diag/runs/2026-10-21T0134Z/` (plan: `PLAN.md`, committed before
the run). Data: frozen PR #5 dataset (`signals` 98b6f816…, `bars` 3df57ff9…), sessions
2022-10-27 → 2026-10-14. All cuts are **exploratory**, not evidence for new rules. The live paper
trading is not included.

## Baseline
- **Reproduced exactly** (difference 0): +68.35 %, max DD −19.20 %, 265 executed / 261 closed,
  +0.228 R per closed trade (AI v1 run 2026-10-15T2007Z).
- **Money reconciled to the cent:** final equity $16,835.31 − $10,000 = closed net P&L
  $6,511.80 + open marks $323.51 (4 positions; their $6.21 exit fee is not charged in equity).

## Three layers
| Layer | Count | Mean R | Median R | PF |
|---|---|---|---|---|
| Eligible signals (non-overlapping model trades, 10 bps) | 2,183 of 7,060 | +0.08 | −0.38 | 1.15 |
| Executed portfolio trades (closed) | 261 | +0.23 | −0.18 | 1.46 |
| Skipped: 5 slots full | 6,078 | +0.01 if taken | −0.47 | |
| Skipped: ticker already held | 613 | +0.31 if taken | −0.02 | |
| Skipped: 3-per-day limit | 62 | +0.46 if taken | +0.10 | |
| Skipped: size < 1 share | 6 | | | |

## Where the profit is
- **Years:** almost all from 2024–2026 (+$1,693 / +$3,780 / +$2,067). Q4 2022 and 2023 lost
  money (−$618, −$410). Every quarter has fewer than 30 trades: small samples.
- **Sector (today's GICS, a limitation):** Information Technology, 86 trades, +0.50 R, **$4,471 =
  65 % of the total result**. All other sectors together: 175 trades, +$2,041. Materials
  +$1,646 from 8 trades (small sample). Signal level agrees in direction (IT +0.24 R over 578).
- **Market:** SPY > MA200, 238 trades, +$6,674. Below MA200 (inside SPY > MA50): 23 trades,
  −$163 (small sample; signal level −0.08 R over 180).
- **Stop distance:** no clear gradient. 3–5 % +0.31 R (44), 5–8 % +0.18 R (128), > 8 % +0.25 R
  (88); ≤ 3 % has 1 trade (the 3 % buffer makes it rare).

## Where the losses are
- Energy (−$540), Financials (−$338), Communication Services (−$289), Health Care (−$281); all
  under 30 trades.
- Q4 2022, Q1 and Q3 2023, Q1 2025.
- **Gaps through the stop:** 16 trades, −$2,372 in total, −1.58 R on average (worst PANW
  −4.34 R). The gap part beyond the planned stop cost $813.

## Dependence on rare winners
- Best 5 trades $3,378 and best 10 trades $5,861 of the $6,835 total; arithmetic residual $3,458
  and **$974**. Mean R falls from +0.23 to +0.10 without the best 5 and to **+0.02 without the best
  10**. Six of the 10 are IT (PLTR, TER, STX, WDC, GLW, FTNT).
- Best 5 tickers (STX, ALB, PLTR, TPR, GLW) $4,412, residual $2,424. Best exit year 2026 $3,466,
  residual $3,369.
- Winners +$19,151 against losers −$12,639. The median trade loses (−0.18 R): the system lives on
  the right tail. Residuals are arithmetic and not the result of a different portfolio.

## Execution and costs
- In the market on 91 % of sessions, 4.0 of 5 slots used on average, all 5 used on 61 % of
  sessions. The 5-slot limit is the dominant constraint (6,078 skipped orders).
- **Costs per side, rules unchanged:**

| Costs | Signal mean R | Portfolio (recomputed) | Max DD | R/trade |
|---|---|---|---|---|
| 10 bps | +0.08 | +68 % | −19.2 % | +0.23 |
| 25 bps | +0.03 | +48 % | −21.6 % | +0.18 |
| 50 bps | −0.06 | +24 % | −24.8 % | +0.10 |

  The portfolio figures are a full replay at each cost level: same candidate trades, sizing
  from equity.

## One follow-up hypothesis (from the data, not a rule change)
Executed trades (+0.23 R) are far better than all eligible signals (+0.08 R) and than the orders
skipped for full slots (+0.01 R). The hypothesis is that **the RS-first choice among the queue,
not the retest signal itself, is the main source of the portfolio's edge**. The only earlier
evidence is the AI v1 test window (RS-first +27.5 % against a random-order median +7.6 %, a
window that is not independent). A check on the whole history would replay the same candidates
in many random same-day orders and compare the distribution with RS-first. That is a diagnostic
of the existing rule, not a new rule, and would need its own plan.
