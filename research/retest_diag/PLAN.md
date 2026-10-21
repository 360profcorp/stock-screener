# Retest RS-first v1: where the profit and loss come from (diagnostic plan)

Written **before** any diagnostic number is computed. Diagnostic only: no parameter is
optimised and no filter is added. Every cut below is exploratory and is not evidence for a new
trading rule. At most one follow-up hypothesis, and only if the data gives a reason for it.

## 0. Ground rules
- Research branch `research/retest-diag-v1`. The bot, both paper states and the closed
  experiments (AI v1/v2, bull flag v1) are not touched. Earlier results are not overwritten
  (new run directory, write-once files).
- Historical backtest only. The live paper trading (bot `trader.enc`, paper book `paper/`) is
  **not** mixed in and is not read.

## 1. Baseline
- Data: frozen PR #5 dataset, artifact of run 38773034101. `signals.csv.gz` sha256 starts with
  `98b6f816`, `bars.pkl.gz` with `3df57ff9`. The run aborts on any other file.
- Universe: point-in-time S&P 500 members on the signal day; RS against that day's members
  (`rs_pit500`); eligibility `eligible_pit_primary` (RS ≥ 85, SPY > MA50, valid stop).
- Rules unchanged: retest detector of PR #5; entry at the next open; stop `stop_base × 0.97`;
  exit at the stop (a gap through it fills at the open) or the close of the 20th bar.
- Portfolio unchanged: `portfolio_bt.replay`, $10,000, 1 % risk, 5 positions, 3 new entries per
  day, 20 % cap, 10 bps per side, RS-first order within a day, window from session 260 to
  2026-10-14, open positions marked at the last close. Price calendar = every ticker of the
  dataset (as in the AI v1 run).
- **Reproduction target** (AI v1 run `2026-10-15T2007Z`, `portfolio_rs_first.csv`, row
  `pit500,retest`): return 68.35310415699882 %, max DD −19.20456303303514 %, 265 executed
  trades, 261 closed, expectancy +0.22771964261522995 R. The diagnostics run only if these are
  reproduced (tolerance 1e-9); any difference stops the run and has to be explained first.

## 2. Three separate layers (never mixed)
1. **Signals:** all eligible retest signals; signal-level net R per non-overlapping model trade
   (production `one_per_ticker` rule), from the dataset's model trades.
2. **Executed portfolio trades:** the fills of the replay above.
3. **Skipped orders:** candidates the portfolio did not take, counted per replay reason
   (`positions`, `daily_entries`, `ticker_open`, `capital_or_risk`, `missing_prices`, `invalid`),
   with the hypothetical result of each skipped trade (same prices, 10 bps).

## 3. Cuts (fixed now)
- **Time:** year and quarter of the signal date.
- **Sector:** the dataset's GICS sector. *Limitation:* today's classification, not the one on
  the signal day.
- **Market:** SPY close above / below its MA200 on the signal day (all signals already pass
  SPY > MA50).
- **Initial stop distance** `(entry − stop) / entry` at the actual entry price: ≤ 3 %, 3–5 %,
  5–8 %, > 8 % (upper bounds inclusive).

Per group, for layers 1 and 2: number of trades, mean and median net R, profit factor; for
layer 2 also the dollar contribution (sum of net P&L of closed trades, plus open marks shown
separately). Groups with fewer than 30 trades are flagged **small sample**.

## 4. Concentration (arithmetic diagnostics, not a new portfolio)
- Dollar contribution of the best 5 and 10 trades, the best 5 tickers and the best year (by
  exit year), and the remaining dollar result without each.
- Mean R without the best 5 / 10 trades.
- These residuals are arithmetic only. Removing trades would change sizing and slot use, so they
  are **not** the result of a different portfolio.

## 5. Execution and costs
- Gaps through the stop: count, loss beyond the planned stop (in $ and in R).
- Time in the market: share of sessions with ≥ 1 position, mean slots used out of 5, share of
  sessions with all 5 used.
- Skips caused by the limits (5 positions, 3 per day) and the outcome of those skipped trades.
- Costs 10 / 25 / 50 bps per side, rules unchanged:
  - signal level: `net_r_base` / `net_r_wide` / `net_r_stress` from the dataset;
  - portfolio: the replay rerun with `cost_bps` 25 and 50 on the same candidate trades. Sizing
    depends on equity, so this is a full portfolio recalculation, labelled as such.

## 6. Reconciliation (for the independent audit)
`final equity − 10,000 = Σ net P&L of closed trades + Σ (shares × last close − entry cost) of
open positions`, checked to the cent. The exit fee of open positions (not charged in equity) is
shown separately. Every executed trade is listed with its signal date, entry, stop, exit, reason,
shares, net P&L, net R and the cut labels.
