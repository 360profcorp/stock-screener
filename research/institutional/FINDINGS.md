# Institutional Intelligence v1 (SEC 13F + Form 4): findings

Pre-registration: `PREREG_INSTITUTIONAL.md` (commit c8c4c39, written before any SEC data).
Run: `research/results/institutional/runs/2026-10-25T0406Z/` (write-once, manifest with hashes).
- SEC build: GitHub run 40160303607. Summary and lags are in `research/results/institutional/sec/`.
- Backtest: GitHub run 40160648657.
- Prices: dataset run 40152515701, sessions 2016-10-24 → 2026-10-23.

Research only. Production, paper books, stops, positions and `TRADING=dry` were not touched.
**Research Breakout = entry at the next open.** It is not the bot's pre-close breakout, and
these results say nothing about the bot's breakouts.

## Verdict
| Strategy | INS (insider buying) | BR (13F breadth) | IR (both) |
|---|---|---|---|
| Research Breakout | not improved | **improves (formal rule; weak evidence)** | not improved |
| Retest | not improved | not improved | not improved |

No result is "undetermined": coverage met the pre-registered thresholds in every year.

**Breakout BR passes the pre-registered rule, but the evidence is weak:**
- Only 1 of 6 tests passes, with no correction for multiple tests.
- The signal-level IC of F2 for Breakout is slightly **negative**: −0.011, 90 % CI −0.040…+0.018. So the book gain is not backed by the trade-level ranking. It is likely a path effect: which trades fill the 5 slots.
- Development beats the RND 80th percentile by only 5.5 points (13.2 % vs 7.7 %), and is below its 95th (19.0 %).
- Much of the holdout gain is 2026 alone (+54.6 % vs +8.4 % for RS).
- At 25 bps the full 2017–2026 BR book is still slightly negative (−5.7 %).

**Recommendation:** no change to production or paper. If the owner wants, Breakout-BR can be a forward paper candidate. Per the pre-registration, that is the only confirmation.

## Books ($10,000, 1 % risk, 5 positions, 3 new/day, 20 % cap; returns in %)
### Research Breakout (next open)
| Order | Window | Return 10 bps | CAGR | Max DD | PF | Trades | Return 25 bps |
|---|---|---|---|---|---|---|---|
| RS | full | −6.5 | −0.7 | −47.7 | 0.97 | 750 | −43.1 |
| INS | full | −15.1 | −1.8 | −47.3 | 0.94 | 730 | −49.2 |
| BR | full | **+85.8** | 7.2 | −29.3 | 1.22 | 724 | −5.7 |
| IR | full | −3.9 | −0.4 | −32.4 | 0.99 | 729 | −29.6 |
| RS | dev 2017–21 | −15.3 | −3.9 | −37.2 | 0.89 | 357 | −27.8 |
| INS | dev | −27.6 | −7.5 | −33.8 | 0.79 | 353 | −38.7 |
| BR | dev | +13.2 | 3.0 | −22.5 | 1.05 | 331 | −5.1 |
| IR | dev | +23.6 | 5.2 | −21.3 | 1.11 | 338 | +3.9 |
| RS | holdout 2022– | +22.6 | 4.3 | −35.9 | 1.10 | 399 | −7.3 |
| INS | holdout | +1.0 | 0.2 | −23.3 | 0.98 | 391 | −15.3 |
| BR | holdout | +73.8 | 12.2 | −26.9 | 1.36 | 397 | +2.5 |
| IR | holdout | −14.2 | −3.1 | −30.4 | 0.92 | 394 | −29.0 |

RND (200 random same-day orders, 10 bps), p50 / p80 / p95:
- development: −8.3 / 7.7 / 19.0
- holdout: 6.1 / 29.2 / 46.1

### Retest
| Order | Window | Return 10 bps | CAGR | Max DD | PF | Trades | Return 25 bps |
|---|---|---|---|---|---|---|---|
| RS | full | +1.3 | 0.1 | −48.0 | 1.01 | 592 | −20.1 |
| INS | full | −9.4 | −1.1 | −38.8 | 0.96 | 587 | −25.2 |
| BR | full | −5.1 | −0.6 | −44.9 | 0.97 | 593 | −16.2 |
| IR | full | +53.8 | 4.9 | −27.7 | 1.19 | 574 | +19.5 |
| RS | dev | −30.4 | −8.3 | −36.3 | 0.72 | 293 | −37.1 |
| INS | dev | −22.3 | −5.9 | −34.6 | 0.77 | 288 | −32.5 |
| BR | dev | −24.4 | −6.5 | −32.1 | 0.78 | 289 | −33.8 |
| IR | dev | +3.9 | 0.9 | −19.3 | 0.99 | 278 | −8.7 |
| RS | holdout | +70.7 | 11.8 | −22.8 | 1.47 | 301 | +48.5 |
| INS | holdout | +34.5 | 6.4 | −18.8 | 1.24 | 303 | +10.7 |
| BR | holdout | +50.7 | 8.9 | −17.8 | 1.28 | 304 | +35.2 |
| IR | holdout | +64.2 | 10.9 | −18.3 | 1.37 | 300 | +47.0 |

RND, p50 / p80 / p95:
- development: −11.7 / −1.9 / 9.6
- holdout: 24.3 / 42.2 / 60.9

IR on Retest looks good over the full period, with a shallower drawdown. It still fails the rule, because its holdout return (+64.2 %) is below RS's (+70.7 %).

### Yearly returns, full books, 10 bps (%)
| | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|---|
| Breakout RS | −2.2 | −21.7 | −9.4 | 27.7 | −4.3 | −31.6 | 16.3 | 21.8 | 5.0 | 8.4 |
| Breakout INS | 0.1 | −19.0 | −6.6 | 5.8 | −9.6 | −19.9 | 22.2 | −0.3 | 31.8 | −8.9 |
| Breakout BR | −0.5 | 0.5 | −2.4 | 2.9 | 12.6 | −24.2 | 8.0 | 15.5 | 12.2 | 54.6 |
| Breakout IR | −0.4 | −7.0 | 1.6 | 9.2 | 20.3 | −22.7 | 14.8 | 1.9 | −3.5 | −10.8 |
| Retest RS | −1.1 | −22.0 | 4.1 | −4.3 | −9.3 | −16.0 | 3.4 | 18.0 | 19.7 | 18.5 |
| Retest INS | −0.1 | −21.1 | −0.9 | 2.0 | −2.6 | −11.5 | 8.9 | 1.8 | 6.0 | 12.3 |
| Retest BR | −2.8 | −8.6 | −1.3 | −3.5 | −10.7 | −21.9 | 18.7 | 7.5 | 17.7 | 7.1 |
| Retest IR | −2.8 | −6.8 | −0.7 | 14.0 | 1.3 | −21.3 | 18.5 | 11.4 | 15.0 | 23.9 |

## Signal-level information (daily Spearman IC vs net R, non-overlapping trades)
| | F1 insiders | F2 13F breadth | RS |
|---|---|---|---|
| Breakout | −0.017 [−0.046, +0.016], 478 days | −0.011 [−0.040, +0.018], 1016 days | −0.029 [−0.055, −0.003] |
| Retest | +0.009 [−0.053, +0.067], 269 days | +0.025 [−0.013, +0.062], 661 days | +0.004 [−0.031, +0.039] |

The intervals are 90 % month bootstraps. None of the SEC features has an IC distinguishable from zero.

## Data coverage by year (% of eligible candidates)
| Year | Breakout candidates | Form 4 data (12 m) | F1 > 0 | 13F usable | Retest candidates | Form 4 | F1 > 0 | 13F |
|---|---|---|---|---|---|---|---|---|
| 2017 | 535 | 99.4 | 5.4 | 97.0 | 239 | 97.9 | 7.9 | 100.0 |
| 2018 | 2266 | 99.1 | 12.3 | 97.7 | 858 | 99.0 | 16.2 | 97.2 |
| 2019 | 3106 | 99.6 | 10.7 | 98.1 | 1196 | 99.4 | 12.0 | 97.2 |
| 2020 | 3033 | 99.2 | 10.7 | 99.0 | 1850 | 99.2 | 11.1 | 99.1 |
| 2021 | 3536 | 97.6 | 7.2 | 98.4 | 1880 | 97.5 | 7.1 | 98.6 |
| 2022 | 1511 | 100.0 | 14.2 | 99.7 | 818 | 100.0 | 15.0 | 99.8 |
| 2023 | 3088 | 99.3 | 7.5 | 98.2 | 1601 | 99.7 | 7.7 | 99.2 |
| 2024 | 3806 | 98.9 | 7.4 | 98.1 | 1830 | 98.4 | 6.9 | 97.9 |
| 2025 | 3274 | 98.4 | 10.5 | 98.6 | 1723 | 98.1 | 10.6 | 98.3 |
| 2026 | 2773 | 98.2 | 7.0 | 98.2 | 1614 | 98.6 | 7.1 | 98.8 |

The thresholds were met in every year: 13F ≥ 70 % and F1 > 0 in ≥ 5 % of candidates.
- 13F filers used per quarter, by the deadline: 3,015 (2015 Q4) to 8,695 (2026 Q2).
- Mapping: 724 of 745 study tickers have a CUSIP; 599 have a CIK in today's `company_tickers.json`. Delisted issuers are matched through their Form 4 issuer symbols.

## SEC publication-time check
| Check | Result |
|---|---|
| Form 4 filed − transaction (open-market purchases) | median 1 day, p90 4, p99 969 (late filers), 2 negative of 31,005 |
| 13F-HR filed − period end | median 41 days, p90 46, p99 923; only filings by period + 45 days are used |
| Features using a Form 4 filed on/after the signal day | **0** (Breakout 26,928 rows; Retest 13,609) |
| Features using a 13F quarter before its deadline + 1 day | **0** |

Late filings are used only from their own filing date, so they cannot leak information.

## Limits
- The data sets give a filing **date**, not the acceptance time. Same-day filings are therefore excluded, which is conservative.
- The current `company_tickers.json` misses some delisted CIKs. Form 4 coverage still stayed at ≥ 97.5 % per year.
- The owner's original pre-registration and instructions (`PREREG_INSTITUTIONAL_AI.md`, `CLAUDE_TASK.md`, the zip) never reached the session. This study follows the written instructions. If those files arrive, any difference will be logged before re-running.
- No news or paid AI API was used.
