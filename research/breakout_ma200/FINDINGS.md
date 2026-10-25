# Breakout + MA200 — Quality & Exit Study v1: findings (exploratory)

- **Pre-registration:** `PREREG_MA200_QE.md` (commit 3bbee24, before any calculation).
- **Run:** GitHub Actions 40233173029, output `research/results/breakout_ma200/runs/2026-10-25T205752Z/`.
- **Full tables and charts:** `REPORT.md` in that folder.
- **Status: exploratory.** The ten years were already examined, so nothing here confirms a
  strategy. Research Breakout buys at the **next open**; this is **not** a test of
  `trader.py`'s pre-close purchases. No paper book is started.
- **Not changed:** Production, Paper, Trading, risk, stops and `TRADING=dry`.

## Checks (all passed)
- **Reproduction:** control M reproduces PR #19 exactly, to ≤ 1e-6 with equal trade counts.
  This holds at 10 and 25 bps on the full window and on both halves. Full window, 10 bps:
  +47.84 %, CAGR 4.46 %, max DD −32.69 %, 690 trades.
- **Money:** reconciled to the cent; the cash identity holds.
- **Next-open entries:** 0 violations in 24,833 candidates.
- **No look-ahead:** 11,421 candidates identical when the data are cut at 2021-12-31. B's
  trailing level uses data up to the previous session only (tests).
- **Missing history of former members:**
  - 117 of 726 former members have no prices;
  - the share of PIT member-days without a price falls from 20.6 % (2017) to 1.1 % (2026);
  - the 2017–2021 half is therefore the most affected by survivorship bias. Its sign cannot
    be measured.

## Stage 1 — diagnostic of M (from its own trades; not carried over from the book without MA200)
**Exact split, 10 bps, risk at the signal close:**

| Part | $ | R per trade |
|---|---:|---:|
| signal quality | +8,564 | +0.255 |
| entry gap | +950 | −0.028 |
| stop gap | −2,164 | −0.045 |
| costs | −2,326 | −0.049 |
| **net** | **+5,024** | **+0.133** |

- At 25 bps the costs take 0.121 R and the net falls to +0.022 R (full return −3.1 %).
- **Unlike the book without MA200, M has a real gross edge.** Costs are the main drag.

**Exits**
- Stops: 425 (−$34.2k).
- Time exits: 261 (+$39.3k, mean +2.11 R; mean MFE 3.31 R).
- 52 entry-day stops; 56 gaps through the stop (−$2.2k).

**Concentration:** the top 10 winners earn $8.8k; without them the rest is −$3.7k. 62 trades
≥ 3 R earn $24.2k.

**Entry quality**
- RS 95–99 averages +0.15 R; RS 85–94 is negative (124 trades).
- Risk at the open 6–10 % and > 10 % averages +0.22 and +0.33 R; below 4 % about +0.05 R.

**Capital:** invested 58.9 % on average, fully in cash 20.3 % of sessions, all 5 slots full
46.7 %.

**After a time exit, compared with SPY on the same dates:** excess −0.31 / −0.27 / +0.60 %
at +5 / +10 / +20 sessions. Every 90 % interval includes 0, so there is **no evidence of alpha
missed by the 20-day exit**. The raw stock rise mostly follows the market.

**2018 (−21.7 %, the same as without MA200):**
- SPY stayed above MA200 for most of the year, so the filter did not engage.
- Losses came in the February–April correction (24 of 26 exits were stops, about −20 %) and
  in October (8 of 10 stops, −6.3 %).
- In April and in November–December the book was largely in cash.

**2019 (−1.9 % while SPY rose 28.8 %):**
- September lost −9.4 %, with 10 of 13 exits by stop: the momentum reversal of
  September 2019.
- The MA200 filter also removed 386 early-2019 candidates. In hindsight they would have
  averaged +0.75 R; these were rebound trades after the late-2018 decline.

**2021 (−2.5 % while SPY rose 27.0 %):**
- March lost −10.8 % (14 of 17 exits by stop) in the growth-to-value rotation.
- November–December lost about −9.7 % (19 of 23 exits by stop).
- The good months (June +10.5 %, February +7.8 %) did not make up for it.

**Where the filter mattered:** in 2022 it removed 1,154 candidates that would have averaged
−0.30 R. That is the main source of M's advantage over the book without MA200 (2022: −12.6 %
vs −31.6 %).

## Stages 2–3 — hypotheses
| Book | Full 10 bps CAGR / DD / PF | Full 25 bps CAGR / PF | Full 50 bps CAGR | 2017–21 CAGR (10) | 2022–26 CAGR (10) | Trades | Invested |
|---|---|---|---|---|---|---:|---:|
| **M** | 4.5 % / −32.7 % / 1.14 | −0.3 % / 0.98 | −8.2 % | −3.4 % | 10.3 % | 690 | 59 % |
| **A** quality ≥ 4 % | 4.1 % / −36.0 % / 1.12 | +0.5 % / 1.01 | −3.3 % | −2.8 % | 10.4 % | 597 | 56 % |
| **B** runner exit | **4.9 % / −34.4 % / 1.16** | **+2.2 % / 1.06** | −5.5 % | −2.8 % | **12.4 %** | 616 | 61 % |
| SPY (price) | 12.8 % / −34.1 % | — | — | 15.8 % | 10.3 % | — | 100 % |

**A — not supported.**
- It removes 53 % of the candidates (13,117 of 24,833).
- At 10 bps it is slightly worse than M: CAGR 4.1 % vs 4.5 %, PF 1.12 vs 1.14, max DD
  3.3 points deeper.
- It is better at 25 and 50 bps (lower turnover: 22× vs 28× a year) and beats the
  random-removal 80th percentile (+44.0 % vs +32.4 %). It still fails the pre-registered
  rule.

**B — formally "supported (exploratory)".** Every criterion passes, but how it wins matters:
- **What the runner rule itself earned:** 64 portfolio trades became runners. Holding them
  earned **+$208** more than M's day-20 exits (+0.09 R each).
- **Candidate level:** runners averaged 3.66 R at their exit against 3.74 R at day 20. In
  other words, no gain.
- **Where the rest came from:** the remaining ~+$400 of the +$606 difference comes from
  path and slot effects. Runners held slots, so B took 74 fewer trades. The 251 M-only trades
  lost $2,258; the 179 B-only trades lost $1,610.
- **So the advantage is mostly lower turnover and a different sequence of trades,** not a
  stronger exit edge. That is fragile.
- **At 25 bps** the gap widens (+21.0 % vs −3.1 %), mainly because fewer trades means lower
  costs.
- **At 50 bps** both lose: B −39.9 % vs M −53.7 %.
- **Limits of the 2017–2026 test:** the result is exploratory and survivorship-affected. It
  is only a candidate for a separately approved forward test; it is not a confirmed
  improvement.

**Risk and exposure compared with SPY**
- The books risk 1 % per trade, hold at most 5 positions and are invested 56–61 % of the
  time. Their 10-year CAGR (4–5 %) is far below SPY's price-only 12.8 %, with a similar
  maximum drawdown.
- In 2022–2026 M matches SPY (10.3 % each) and B is above it (12.4 %).
- In 2017–2021 every book lost while SPY gained 15.8 % a year.
- SPY is price only, with no dividends; the books earn no cash interest.

## Confidence
- **High:** reproduction; the accounting split; costs; turnover; counts.
- **Medium:** the year and month attribution of 2018 / 2019 / 2021.
- **Low:** the hypothesis verdicts and every hindsight comparison. They rest on data
  already examined, they are path-dependent, and the first half has incomplete history.
