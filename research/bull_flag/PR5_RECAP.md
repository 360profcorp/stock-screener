# PR #5 (S&P 1500 expansion) — recap before the bull-flag study

Source: PR #5 run `research/results/sp1500/runs/2026-10-15T1656Z/` and the portfolio and yearly
tables of the AI v1 review (`research/ai_rank/FINDINGS.md`, run 2026-10-15T2007Z). **No new
run** was made for this recap: the existing results answer the question.

## Conclusions
- **Do not expand the universe for signal count.** Retest RS-first on the whole 1500 returned
  +9 % against +68–78 % on the S&P 500 (same rules, costs and portfolio limits).
  - S&P 600 setups: negative or about zero after costs.
  - S&P 400 breakout and retest: about zero at signal level, with the sign changing between years.
- **The S&P 500 is the universe that works.** Point-in-time members (RS against that day's
  members), retest RS-first: +68 %, max DD −19 %, +0.23 R per trade, positive in every full year.
- **Survivorship inflates the current-list results.**
  - Breakout on today's S&P 500 list: +212 %. On point-in-time members: +56 %.
  - The bull-flag study therefore uses point-in-time S&P 500 members as its primary universe.
- **Shorts (three hypotheses):** negative before costs in nearly every year. Rejected.
- **VCP:** negative as a point-in-time S&P 500 portfolio (−9 %). The signal-level edge disappears in
  the portfolio.

## Limitations carried into this study
- 253 of 439 former members have no Yahoo data, so survivorship bias remains even under PIT.
- Membership comes from community snapshots, not from S&P; sectors are today's GICS.
- Daily bars only: the order of events inside a bar is unknown, and the stop is taken first.
- The whole history 2022-10 → 2026-10 has already been viewed while choosing strategies. Any
  result on it is **exploratory**; independent confirmation must come from future data.
