# Retest M (Retest + SPY > MA200) — independent check 2007-06 → 2016-10: result

## Verdict: **INCONCLUSIVE**
- The data gate failed (PLAN.md §10.6), so no backtest of the independent period was run.
- No return, drawdown or trade of M on 2007–2016 was computed.
- No parameter was changed.

## 1. Reproduction gate: passed
`repro/2026-10-26T*/repro.json`: the PR #19 code path, run on dataset 40152515701, reproduces
all 12 reference books exactly (Δ = 0, equal trade counts).

| Book (seen data 2016-10 → 2026-10) | Return | Max DD | Trades |
|---|---:|---:|---:|
| M full, 10 bps | −4.40 % | −45.34 % | 557 |
| M full, 25 bps | −33.86 % | −53.77 % | 559 |
| M 2017–2021, 10 bps | −24.27 % | −30.85 % | 283 |
| M 2022 →, 10 bps | +49.70 % | −22.05 % | 276 |

Retest C was reproduced exactly as well. These figures are reference, not evidence.

## 2. Data gate: failed
- **Source:** Yahoo, `auto_adjust=False`, 2005-12-01 → 2016-10-24.
- **Universe:** PIT S&P 500 from the fja05680 snapshots (sha256 `36326709…`, identical to PR #19).
  762 tickers were members at some point in 2006–2016; Yahoo returned usable bars for 454.

**Coverage** = PIT member-days with a bar ÷ member-days (`data/2026-10-26T174412Z/coverage.json`).
Threshold: 85 %.

| Year | Coverage | Members still in the index at 2016-10-21 | Members removed before then |
|---|---:|---:|---:|
| 2007 | 58.8 % | 78.5 % | 19.5 % |
| 2008 | 60.9 % | 77.8 % | 21.9 % |
| 2009 | 63.2 % | 77.6 % | 20.2 % |
| 2010 | 65.5 % | 77.7 % | 22.3 % |
| 2011 | 66.4 % | 77.6 % | 21.3 % |
| 2012 | 68.5 % | 78.2 % | 22.3 % |
| 2013 | 70.7 % | 78.5 % | 24.0 % |
| 2014 | 71.7 % | 78.1 % | 18.9 % |
| 2015 | 73.5 % | 77.7 % | 18.2 % |
| 2016 | 76.3 % | 77.6 % | 13.4 % |

## 3. Why: survivorship of the data source, not a download error
**Download checks**
- The first run lost 308 tickers.
- The single-ticker retry of §10.12 recovered none.
- A probe (`probe/*/probe.json`, yfinance 1.7.0) requested EA, BK, EQR, IPG and K in four
  different ways (single download, multi download, `history` with dates, `history(period="max")`).
  It got **no history before 2026** for any of them; AAPL returned full history every way.

**Conclusion:** Yahoo serves no history for symbols that are no longer listed.
- Companies taken over or delisted **after** 2016 lose their **whole** history, including
  2007–2016 when they were large S&P 500 members (e.g. Electronic Arts, Interpublic, Kellanova).
- This is why even the members still in the index in 2016 are covered only ~78 %: 112 of them
  have no data.
- Of the members removed during 2007–2016, 160 have no data. Among them are the crisis
  casualties: Bear Stearns, Countrywide, Merrill Lynch, Sun Edison.

**Survivorship assessment (§10.6)**
| Group | With data | Without data |
|---|---:|---:|
| Still members at the end of U | 394 | 112 |
| Removed during U | 53 | 160 |

- The missing stocks are mostly the ones that later failed, were absorbed or were taken private.
- A long-only backtest on what remains would see the index without most of its losers, so the
  bias would **flatter** M, most of all in 2007–2009.

**Ticker reuse is a second, related risk.** Some old symbols now belong to other companies. For
example, WB (Wachovia, a member in 2007–08) is now Weibo. Data under such a symbol would be the
wrong company. It was not used, because no backtest ran.

Since 2016–2026 is development data and 2007–2016 cannot be measured reliably, **there is
currently no independent evidence for or against M's robustness**.

## 4. What it would take (owner decisions; nothing started)
1. **Survivorship-free historical data.** Point-in-time S&P 500 constituents with prices of
   delisted companies, from a licensed source such as CRSP or Norgate, or from another paid vendor
   with delisted coverage. This is a paid source, so it needs the owner's approval. It would
   remove the cause of the INCONCLUSIVE.
2. **A clearly labelled biased check.** Run the same books on the covered names only, as an upper
   bound. It could reject M (if even the flattered result fails the rules) but never confirm it.
   It needs a new decision because it changes the §10.6 gate.
3. **Forward evidence.** The live Paper book runs the production Retest RS-first rules, not M.
   Forward data for M would need a separate paper experiment and an owner decision.

## Status
Production, Paper, `TRADING=dry` and `main` are unchanged. PR #26 stays Draft.
