# AI ranking v1 and PR #5 review — findings

Run `research/results/ai_rank/runs/2026-10-15T2007Z/` (workflow run 38799343053) on the PR #5
dataset (run 38773034101): 661,469 detections, sessions 2021-10-15 → 2026-10-14. With the
260-bar warm-up, trades start in 2022-10. "2022" is Oct–Dec only; "2026" runs to 14 Oct.
Research only. The bot and both paper portfolios are unchanged.

## 1. Dataset audit (before training)
| Check | Result |
|---|---|
| Per-ticker features recomputed from bars cut at the decision bar | 400/400 equal |
| RS recomputed from closes up to the signal day (3 dates) | 1,866/1,866 equal |
| Labels after the data end / exit before entry / entry not after the signal | 0 / 0 / 0 |
| **Purge of v1.0 splits (20 sessions)** | **FAIL: 716 train rows and 483 validation rows had labels ending inside the next split** (trade = entry next session + 20 bars = signal + 21) |
| Fix | Purge by the label's true end (exit date, at least signal + 21 sessions); `engine.assign_splits` corrected and tested |
| Overlap | 70 % of eligible long signals repeat an open setup. Non-overlapping statistics are reported; standard errors on all signals are understated |
| Test-period independence | **Not independent.** Retest RS-first and its parameters were chosen in Tasks 6 and 9 on backtests covering 2023–2026, which includes the test window (2025-12-30 → 2026-10-14) |

## 2. Portfolio results (production engine, RS-first, $10k / 1 % / 5 positions / 3 per day / 10 bps)
Signal statistics are kept separate (section 3). PIT = S&P 500 membership on the signal day.
Every other universe uses today's lists, so it carries survivorship bias.

| Book | Trades | Return | CAGR | Max DD | Exp. R/trade | Exp. $/trade | 2023 | 2024 | 2025 | 2026* |
|---|---|---|---|---|---|---|---|---|---|---|
| **PIT S&P 500 retest** | 265 | +68 % | 14.0 % | −19.2 % | +0.23 | +25 | +2.6 | +15.4 | +20.7 | +31.0 |
| PIT S&P 500 breakout | 353 | +56 % | 11.9 % | −18.9 % | +0.18 | +15 | +17.0 | +18.6 | +2.2 | +25.8 |
| PIT S&P 500 VCP | 273 | −9 % | −2.3 % | −21.5 % | −0.04 | −3 | +4.1 | +12.4 | −13.7 | −3.5 |
| PIT S&P 500 double bottom | 12 | +3 % | — | −1.9 % | +0.35 | +27 | sample too small | | | |
| current S&P 500 retest | 276 | +78 % | 15.7 % | −16.5 % | +0.26 | +29 | | | | |
| current S&P 500 breakout | 369 | +212 % | 33.3 % | −27.5 % | +0.37 | +57 | survivorship: 4× the PIT result | | | |
| S&P 400 breakout / retest / VCP | 349 / 284 / 270 | +51 / +36 / +12 % | 10.9 / 8.0 / 2.9 % | −22 / −22 / −21 % | +0.16 / +0.12 / +0.04 | | current lists only | | | |
| S&P 600 breakout / retest / VCP | 402 / 303 / 287 | +28 / −7 / −34 % | 6.4 / −1.7 / −9.8 % | −30 / −20 / −42 % | +0.05 / −0.02 / −0.10 | | | | | |
| 1500 combined retest | 307 | +9 % | 2.3 % | −26 % | +0.04 | +3 | | | | |
| 1500 combined breakout | 385 | +275 % | 39.6 % | −19.6 % | +0.42 | +69 | current lists, survivorship | | | |

\*2026 runs to 14 Oct.

## 3. Signal level by year (non-overlapping, net R after 10 bps; not a portfolio)
- **S&P 500.** Retest +0.18 / +0.23 / +0.16 / +0.09 (2023–2026). Breakout +0.09 / +0.22 / +0.19 / +0.01. VCP +0.05 / +0.30 / +0.22 / +0.09. All long setups were negative in Q4 2022.
- **S&P 400.** Around zero, changing sign from year to year: retest +0.07 / −0.08 / +0.15 / −0.14.
- **S&P 600.** Negative in most years for every setup.
- **Shorts** (gross, before costs and borrow). Negative in almost every group and year. The few positive cells (breakdown 2023 / 2026 in the 400 and 600) are small, and costs and dividends erase them.

## 4. Verdict per market and strategy
| Market + strategy | Verdict | Reason |
|---|---|---|
| S&P 500 retest (RS-first) | **Keep as the control** (already in paper) | Positive in every full year under PIT; the test window is not independent |
| S&P 500 breakout | **Allowed to a separate paper test** (its own book, never mixed) | PIT +56 %, positive 2023–2026 but weak in 2025; the current-list result (+212 %) is mostly survivorship |
| S&P 500 VCP | Reject for the portfolio, continue only as research | Negative PIT portfolio; the signal-level edge disappears in the portfolio |
| S&P 500 double bottom | Continue research | 12–30 trades: not testable |
| S&P 400 retest / breakout | Continue research (needs PIT) | Signal level unstable around 0; portfolio uses current lists only |
| S&P 400 VCP, all S&P 600 setups | **Reject** | Negative or near-zero after costs, unstable |
| 1500 combined (expansion) | **Reject expanding for signal count** | Retest falls from +68–78 % (S&P 500) to +9 %; breakout's gain is survivorship |
| Shorts S1–S3, all groups | **Reject** | Negative before costs in nearly every year; borrow availability, fees and recall unknown |

## 5. First ranker (long signals, PIT S&P 500)
Setup:
- Same eligible signals, same trade list, capital, limits and costs; only the same-day order differs.
- Models: ridge regression or a shallow gradient boosting on 19 decision-time features; the target is net R, winsorised.
- Data: fit on train (purged), model chosen on validation (2025-03-17 → 2025-12-29), refit on train + validation, test evaluated **once** (2025-12-30 → 2026-10-14).

Results:

| | Retest only (E1) | All long setups (E2) |
|---|---|---|
| Test, RS-first | +27.5 %, DD −7.7 %, 0.47 R, 55 % winners | +11.5 %, DD −16.9 %, 0.23 R |
| Test, model | **+13.7 %, DD −19.5 %**, 0.23 R, 34 % winners | **−11.3 %, DD −26.9 %**, −0.26 R |
| Test, random order (50) | median +7.6 % (p10 −6.0 %, p90 +18.1 %) | median +10.4 % (p10 −8.3 %, p90 +27.0 %) |
| Same-day rank correlation, test | −0.06 | −0.02 |
| Walk-forward inside development (RS-first vs model) | 2024: +22.7 vs +12.4 %; 2025: +23.9 vs +20.3 % | 2023: +8.4 vs −1.2 %; 2024: +25.3 vs +8.6 %; 2025: +6.5 vs −1.1 % |

**Conclusion.** The ranker gets worse results than RS-first everywhere. Validation chose a model whose rank correlation was already ≤ 0, so its validation return was a lucky path, not real ranking skill.

RS-first beats the random-order median on the retest test window (+27.5 % against +7.6 %). This supports RS ordering, but the window is not independent.

Nothing is connected to the bot.

## 6. What was not tested
- Bull flag: not implemented.
- Buy-stop / pending entries on the 1500.
- Short portfolios: the portfolio engine is long-only.
- Earnings filter: the bot uses `EARNINGS_DAYS`, the research does not.
- Sector limits on the 1500.
- PIT portfolios for the 400 and 600 (change tables are best effort; most removed names have no Yahoo data).
- Intraday entry ambiguity.

## 7. Limitations
- Survivorship bias remains even under PIT: 253 of 439 former members are missing from Yahoo.
- Only one validation and one test window, about 9 months each.
- Overlapping signals.
- Daily bars.
- Borrow data unknown.
- All of this is a backtest, not a forward result.

## 8. Next step
1. Keep RS-first.
2. If wanted, run S&P 500 breakout as a separate paper book with its own rules and statistics.
3. Retry a ranker only with new information, such as earnings timing, sector or industry strength, or market breadth, and with a genuinely forward test window. Collect that window by letting the paper books run.
