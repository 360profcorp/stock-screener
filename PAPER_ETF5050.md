# Paper book: 50 % SPY / 50 % BIL

Owner's instruction, 2026-10-26: an implementation, not a research study. **Paper only:**
- no broker and no orders;
- `TRADING=dry` and the bot are untouched;
- the existing paper books (`paper/state`, `paper/data`, `paper/compare`) are not read or written.
  The workflow hashes them before and after every run.

| Rule | Value |
|---|---|
| Start | $10,000 virtual cash. The activation run buys nothing and backfills nothing; the first purchase is queued for the next session's open. |
| Target | 50 % SPY, 50 % BIL, whole shares |
| Rebalance | decided after the close of the last session of each month (NYSE calendar), executed at the next session's open |
| Order sizing | quantities = floor(50 % × (cash + shares × previous close) ÷ previous close); sells first; each buy is capped by the cash then available |
| Fees | 2 bps of notional per side, recorded per fill and in total |
| Dividends | shares held at the close before the ex-date; receivable on the ex-date; cash on the assumed pay date (SPY: last session of the next month; BIL: 5 sessions after the ex-date). Cash waits for the next rebalance. |
| Cash | leftover cash and received dividends are tracked separately and count in equity |
| Not included | MA, RS, stops, 20-day exit (other strategies) |
| Risk | −20 % drawdown is a risk-evaluation reference, **not** a guaranteed loss limit |

**Data:** Yahoo daily bars (`auto_adjust=False`, dividends as amounts).
- A session is processed only with valid bars for both ETFs; otherwise processing stops and the
  problem is recorded.
- Today's bar is ignored before 16:15 New York.

**Late runs:** an order executed by a run that started after that session's open is flagged
`late` (reconstructed) in the fills and the rebalance log. It is never hidden.

**Files:**
- `paper_etf.py` (engine), `etf5050_run.py` (CLI), `etf5050_tab.py` (⚖️ 50/50 tab);
- `.github/workflows/paper-etf5050.yml`: weekdays 22:20 UTC; manual run; or a push of
  `paper/etf5050/ACTIVATE` to `main`;
- state in `paper/etf5050/` (`state.json`, `summary.json`, `equity.csv`, `fills.csv`,
  `rebalances.csv`, `dividends.csv`);
- tests: `test_etf5050.py`, `test_etf5050_ui.py`.

**Checks on every run:**
- the cash identity, to the cent: initial − buys + sells − fees + dividends received;
- the share identity, from the fills.
