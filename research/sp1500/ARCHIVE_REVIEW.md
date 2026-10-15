# Review of `SP1500_Shorts_AI_Research_v1.zip` (`research/expansion.py`, 12 tests)

The archive was prepared against main `d54c6dd` and never run on market data (`STATUS.txt`).
Its 12 synthetic tests pass in its own design. It was reviewed, not applied. Below: what was
kept, what was changed in `research/sp1500/`, and why.

## Kept as is
- The three short hypotheses (`breakdown`, `breakdown_retest`, `failed_breakout`), their
  parameters and stop bases. They are copied verbatim into `rules.py` as pre-registered v1.0.
  They are independent rules, not mirror images of the long setups.
- Filters: RS ≤ 20 for shorts, price ≥ $5, 20-day dollar volume ≥ $5M, market direction.
- Rejected signals are kept with their reasons. The signal ID is a sha256 of
  version/date/ticker/strategy/direction. A short with unknown borrow gets no net result.
  When stop and target fall in the same candle, the stop counts first.
- Write-once outputs (`immutable_json` became `run.write_once`), frozen input bars and
  checksums.

## Problems found and how the research code handles them
| # | Archive behaviour | Effect | Fix in `research/sp1500` |
|---|---|---|---|
| 1 | `yf.download(auto_adjust=True)` | Prices are adjusted for dividends, so levels and stops differ from the production basis (`auto_adjust=False`). The dividends a short has to pay are also hidden inside the price series. | `auto_adjust=False, actions=True`. Dividends are paid explicitly for ex-dates in (entry, exit]. |
| 2 | RS ranked inside "available S&P 1500" only | Expanding the universe and changing the RS base get mixed into one effect. "RS 85" then means something different from production. | Main variant: RS percentile against the **S&P 500** reference. RS vs 1500 is a separate variant, and so is a point-in-time S&P 500 reference. |
| 3 | Any ticker in two lists → `ValueError` | CORT, EAT and FORM, listed in both the 400 and the 600, block the whole run. | Overlaps are resolved only with dated evidence (holdings as-of dates, dated change tables). Otherwise the ticker is flagged `ambiguous`, kept, and excluded from single-group comparisons. |
| 4 | Long modes: breakout/retest/vcp only | `dbottom`, which is part of `core.MODES`, is missing. | All four production long modes are included. |
| 5 | MFE/MAE taken over the whole horizon window, even after a stop | Look-ahead: MFE includes price moves after the trade had already exited. | MFE/MAE are truncated at the exit bar (tested). |
| 6 | The price-move label, the 4R-target trade and the horizon exit are all in one record | Price move, model trade and barrier label are mixed. The model trade also differs from production, which has no target. | Kept separate: `px_ret_h` runs from the signal close; the model trade is the production one (stop or 20 sessions); the barrier label is ±4R. Each has its own observable date. |
| 7 | Missing horizon bars → the label is silently dropped | Cannot tell an immature label from one with missing data. | Every horizon gets a status (`mature`, `immature` or `missing_bar`) plus an observable date. |
| 8 | No handling of 429 errors or exceptions in `yf.download` | One error aborts the run and nothing is cached. | Chunked downloads, bounded exponential retries, a per-chunk cache, a per-ticker report and an Actions cache. |
| 9 | Coverage below 95 % → no report | The task asks for the coverage itself to be reported. | Coverage per group is written to the report and listed as a blocker if low. |
| 10 | Any invalid bar rejects the whole ticker | A single bad bar removes a stock from the universe. | The invalid bar is removed and counted. It becomes a missing session and is never repaired. |
| 11 | Indicators recomputed for every day on truncated frames | O(N²) runtime. | Causal rolling arrays are computed once. Leakage tests perturb future bars and check the features do not change. |
| 12 | `training_pairs`: purge but no embargo and no test split | Incomplete chronological protocol. | 60/20/20 chronological split, 20-session purge, 5-session embargo. No model is trained. |
| 13 | iShares share-class tickers (`BRKB`) not handled (the archive used Wikipedia only) | Yahoo misses these names. | Mapped to the reference spelling (`BRK-B`). |
| 14 | Membership is current only | Survivorship bias. | The point-in-time S&P 500 is rebuilt from Wikipedia's dated change table, and removed members are downloaded where Yahoo still has them. The 400 and 600 are flagged. |

## Entry on a missing next bar
The archive skips the trade when the ticker has no bar on the next market session. The
research engine follows production instead (`backtest.simulate`: the ticker's next bar). It
records `entry_delay_sessions` so that such rows can be filtered out.
