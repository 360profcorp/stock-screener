# Task 6 — Portfolio backtest engine corrections

Branch: `fix/portfolio-engine-task6` (from `main` @ 2fa3d36). Not merged, not deployed.
Files: `backtest.py`, `portfolio_bt.py`, `app.py` (portfolio expander only),
`test_portfolio_bt.py` (2 tests pinned to the v3 option), `test_task6_engine.py` (new, 21 tests).

Unchanged: setup definitions, RS, stop buffers, filters, strategy parameters, the
signal-level comparison table, the trading bot, the scanner.

## P1 — Future information in pre-open position sizing (fixed)

**Bug (portfolio_bt.py v3, lines 65–110).** Every day, exits due that day were processed
first, then all entries were sized. For next-day-open (and buy-stop) entries that leaked
information from later in the same session in three ways:
1. `current_equity` included `sum(exits)`, i.e. exit prices known only later (stop fills, closes);
2. a position exiting later that day had already freed its slot at the open (`len(held)`);
3. a same-day stop of an earlier new entry (exits list grows inside the entry loop) changed the
   equity used to size the next candidate.

**Fix.** Each trade carries `entry_at` (`close` | `open` | `stop`; written by `simulate` /
`simulate_stop`, or the new `entry_timing` argument). The daily order is now:
pre-open entries → exits due today → close entries → cash settles → mark-to-market.
Pre-open entries are sized from one pre-session basis: cash before today's exits + held
positions at the previous close, with positions exiting today still occupying their slots.
Close entries keep the v3 rules (exits are known at the close).

**Tests.** `P1Leakage` (6 tests), incl. a seeded property test: exit prices of trades exiting
on/after day D are perturbed ×0.3–3; share counts of every entry on/before D must be identical.
Run against the v3 replay, 4 of the 6 fail (the leak is real and the tests detect it); the
cash test and the close-entry sensitivity test pass on both by design.

## P2 — `busy_until` architecture (fixed)

**Problem.** `simulate`/`simulate_stop` decided ticker ownership with a hypothetical
one-trade-per-ticker rule. A trade the portfolio rejected still hid every later signal on
that ticker for its whole hypothetical life.

**Fix.** Outcome calculation and ownership are separated:
* `_trade()` computes one trade outcome per valid signal, independent of other trades;
* `_finish(one_per_ticker=...)` applies ownership. `one_per_ticker=True` (default) reproduces
  the original rule exactly — used by the signal-level table; `False` returns every valid
  signal — used by the portfolio, where `replay()` alone owns tickers (`held`).
* New columns (only when an option is changed): `signal_date`, `entry_at`, `status`,
  `window_complete`, `mark_date`, `mark`, `mark_r`. Default output has the original 14 columns.

**Exit-day re-entry rule (replay).** Close entry on the exit day: allowed (the exit is
realised before the close). Pre-open entry on the exit day: blocked (`ticker_open`) because
at the open the position is still held; allowed from the next day.

**Equivalence.** Default `simulate`/`simulate_stop` output was compared with the v3 code on
6 random synthetic markets × all setups × close/open × hold 5/20 × two filter sets:
57,501 trades, identical frames. v3 vs new `replay` on close-entry trades: identical equity
curves, fills and metrics in 18 runs.

## P3 — Terminal dates (fixed)

**Problem.** A trade whose stop wasn't hit and whose holding period ran past the last bar was
dropped, while trades stopped early in the same window were kept — the last ~`hold` days
contributed losers only.

**Fix.** `simulate(..., include_open=True)` returns such trades with `status="open"`,
`exit/exit_date/r = NaN` (no invented exit) and `mark`/`mark_r` at the last close.
`replay(open_at_end=...)`:
* `"mark"` (default) — held to the end, valued at the last close, listed in
  `metrics["open_positions"]`; a known exit **after** `end` is ignored (never used);
* `"liquidate"` — sold at the last close of the window (costs applied), `status="liquidated"`;
* `"skip"` — v3 behaviour.
When open trades exist, the default `end` is the last data day. Reconciliation
`executed_trades + Σ skipped == candidate_trades` holds for all three options.
Note: the signal-level table still uses closed trades only (unchanged on purpose for
comparability with the 24 configurations); `window_complete` allows an unbiased
"complete windows only" statistic when we agree to switch.

## P4 — Retest capacity sweep: +87.13 % (10/day) vs +85.52 % (unlimited)

**Conclusion: expected path dependence, not an implementation error.**
* With 20 positions and a 20 % position cap, desired exposure can reach 400 % of equity, so
  **cash, not slots, is the binding constraint**. Allowing unlimited entries on signal-cluster
  days spends the cash on that day's candidates (the last ones cash-limited), leaving none for
  the following days' signals. The traded subset changes, so the return is not monotonic in the
  daily limit. `P4Capacity.test_unlimited_daily_entries_can_underperform` reproduces this
  deterministically.
* The daily cap itself is a plain counter; `None` now means "no limit".
* A 1.6 pp difference over ~2 years is far inside the Monte Carlo spread of single-path replays.
* Contributing factor: close-entry sizing basis includes same-day exit proceeds while cash does
  not (conservative settlement), which makes cash-limited entries frequent. New metric
  `cash_limited_entries` counts entries whose size was cut by free cash.
* Re-run on real data with this branch and report `cash_limited_entries`,
  `skipped['capital_or_risk']` and the MC distribution for both settings to confirm.

## Expected differences vs previous results
| Area | Change |
|---|---|
| Signal-level comparison table | none (bit-identical default output) |
| Portfolio, close entry | many more candidates (raw signals instead of one-per-ticker list) → different executed subset; open trades marked to market at the end instead of dropped; CAGR measured to the last data day |
| Portfolio, open / buy-stop entry | additionally: fewer entries on days with same-day exits (slots/cash no longer freed at the open); share counts independent of same-day exits |
| Metrics | new keys: `closed_trades`, `liquidated_trades`, `open_positions_end`, `open_positions`, `cash_limited_entries`, `entries_pre_open`, `entries_close`; executions get `status` |
| UI | portfolio expander: end-of-period rule selector, open/cash-limited counts |

Direction of the return change on real data cannot be predicted from code; please re-run the
Task 4/5 sweeps and Monte Carlo on this branch.

## How to run the tests
```
python -m unittest test_task6_engine test_portfolio_bt -v     # 29 tests
```
