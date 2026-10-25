# Breakout + MA200 — Turnover & Selection Audit: findings (exploratory)

- **Pre-registration:** `PREREG_TURNOVER_SELECTION.md` (commit 5dcc224, before the run).
- **Run:** GitHub Actions 40235624901, output `research/results/turnover_selection/runs/2026-10-25T212841Z/`.
- **Full report with charts:** `REPORT.md` in that folder.
- **Reproduction:** M and B reproduce PR #23 exactly (3 windows × 2 costs).
- **Scope:** every book is a full sequential replay; no trade was removed from an already
  computed P&L.
- **Limits:** the 2017–2021 history misses many former index members. Nothing here is
  independent confirmation. Research Breakout enters at the next open, not like
  `trader.py`.

## Verdict
**B does not show a convincing advantage beyond simple turnover reduction. Recommendation:
do not implement B.** The pre-registered rule fails on criterion 4, as the table below
shows:

| Criterion | Result |
|---|---|
| B CAGR > R1 p90 at 10 and 25 bps | yes (B at the 95th / 99th percentile) |
| B PF > R1 p80 at 10 and 25 bps | yes |
| B max DD within 3 pt of R1's median | yes |
| **extension effect B − B0 > 0 at 10 and 25 bps** | **no**: −$899 at 10 bps, +$1,099 at 25 bps |

## 1. Where B's advantage comes from
**Isolating book B0.** B0 has B's exit dates, so the slots are held as long as in B. Every
runner, however, earns only M's day-20 price.

| Full window | B − M | B0 − M (slot / turnover / composition) | B − B0 (price effect of extending) |
|---|---:|---:|---:|
| 10 bps | +$604 | **+$1,503** | **−$899** |
| 25 bps | +$2,410 | +$1,311 | +$1,099 |
| 2017–2021, 10 bps | +$231 | −$596 | +$827 |
| 2022–2026, 10 bps | +$1,554 | +$3,174 | −$1,620 |

- **At 10 bps, keeping the runners in their slots without the extra gain does better than B
  itself.** The extended holding earned less than closing at day 20, about −$900.
- **The sign of the extension effect changes** with costs and periods. It is not a stable
  edge.

**Exact accounting split of profit_B − profit_M (full, 10 bps):**

| Part | $ | Trades |
|---|---:|---:|
| runner trades (same entry, later exit) | **+$208** | 64 |
| trades only in B | −$1,610 | 179 |
| trades only in M, avoided by B | +$2,258 | 251 |
| identical trades (sizing only) | −$772 | 371 |
| open positions at the end | +$520 | — |
| **total** | **+$604** | — |

**The core of B's advantage at 10 bps:** busy slots made B skip 251 M trades that lost
$2,258 in total. The extension itself earned only $208.

## 2. B against random controls (200 seeds each)
**R1 — random entry reduction** (each candidate dropped with q = 0.8725; 614 trades at the
median, B has 616):
- B is at the **95th** (10 bps) and **99th** (25 bps) percentile of CAGR.
- However, R1 drops 87 % of the candidates at random, which destroys the RS-first selection.
  B keeps it.
- The ordering test shows how much that selection is worth: M with RS-first sits at the
  **98th percentile** of 200 random same-day orders (+47.8 % vs a median of −10.1 %).
- So beating R1 mostly reflects preserved RS-first selection, not the runner rule.

**R2 — random runners** (the same number of extensions as B, without the +2 R condition):
- B is at the **72nd** (10 bps) and **92nd** (25 bps) percentile.
- **Choosing the +2 R positions is not clearly better than extending random time exits.**
- B makes fewer trades (616 vs about 660), which helps at higher costs.

**Volume and exposure:**

| | Trades (full, 10 bps) | Turnover | Invested |
|---|---:|---:|---:|
| B | 616 | 24.7× a year | 60.8 % |
| R1 (median) | 614 | 24.3× | 57.3 % |
| R2 (median) | 660 | 26.4× | 59.2 % |
| M | 690 | 27.9× | 58.9 % |

## 3. Why candidates average −0.028 R while M's trades average +0.101 R
**Candidate chain, 10 bps:**

| Step | Mean R | Effect |
|---|---:|---:|
| all candidates (24,707) | −0.028 | |
| days weighted equally | −0.016 | crowding +0.013 |
| at most 3 random a day | −0.018 | daily limit +0.011 |
| top 3 by RS a day | +0.029 | **RS-first +0.047** |
| entered by the portfolio (686) | +0.101 | **slots / held tickers / sequence +0.072** |

**What drives the slot effect:**
- The top-3-by-RS candidates skipped because **all slots were full** (2,648) average
  **−0.046 R**.
- Those skipped because the **ticker was already held** average +0.160 R. The entered ones
  average +0.135 R.
- Full slots therefore keep the book out of signals that arrive after a burst of earlier
  entries. Those late signals are on average poor. This is a property of the sequence, not
  of a rule we chose.

**Regime (descriptive):**
- Days with **10–20 candidates** (the middle breadth tercile) are negative at every step:
  the entered trades average −0.244 R.
- Narrow days (< 10) and very broad days (> 20) are positive for the entered trades: +0.245
  and +0.240 R.
- By the SPY 20-session return, the middle tercile (+1.8…3.6 %) is the best: +0.300 R. The
  strongest rallies are slightly negative: −0.080 R.
- These are correlations on data already seen, not rules.

## Context only: the `research/breakout-causes` run (base C, not mixed with M / B)
- **Execution on C:** signal quality +0.145 R a trade, entry gap −0.037, stop gap −0.045,
  costs −0.048, net +0.014 R.
- **The MA200 filter on C (= M)** beat random removal of the same number of candidates: M
  +47.8 % against a random p95 of +31.4 %.
- **H3 on C** (a different runner rule) was not supported.
- **After a time exit vs SPY:** on C, +1.66 % at +20 sessions (90 % CI +0.59…+2.65). On M,
  only +0.60 %, with an interval including 0. The two base strategies do not behave the
  same here.

## Conclusion
- **Do not implement B.** It does not add an edge beyond lower turnover and changed slot
  occupancy, and the extension effect itself is unstable in sign.
- **Better explained by these results:**
  - **RS-first selection** has strong evidence on this data: 98th percentile against random
    order.
  - **The slot limit** filters out late signals.
- Both observations are exploratory and survivorship-affected. Any rule built on them would
  need its own pre-registration and a forward test.
