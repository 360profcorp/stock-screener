# Institutional Intelligence v1 (SEC 13F + Form 4): pre-registration

Written **before** any SEC data is loaded for the study and before any result.

**Note on sources.** The owner's original `PREREG_INSTITUTIONAL_AI.md` / `CLAUDE_TASK.md`
did not reach this session: the attachments arrived empty three times. This document follows
the owner's written instructions of 2026-10-24:
- SEC 13F and Form 4 first;
- no paid AI API;
- no news without verifiable archived content as an edge;
- research Breakout (next open) kept separate from the bot's pre-close Breakout.

If the original pre-registration arrives later, any difference is listed in a change log
**before** results are read. If it conflicts, a new version is run; this one is not tuned.

Research only. Production, paper, stops, positions and `TRADING=dry` are not changed. The PR
stays a draft.

## 1. Question
On the **same signals** and with the **same risk limits**, does ordering the day's candidates
by an institutional / insider rating produce a better portfolio than the current
**RS-first** order?

## 2. Signals and portfolio (fixed, identical for every order)
- **Prices:** the 10-year bars of dataset run 40152515701, sessions 2016-10-24 → 2026-10-23.
  **Universe:** point-in-time S&P 500 members (the same as the crisis study's control **C**).
- **Signals:**
  - Retest and **research Breakout**: lookback 3, **entry at the next open**. This is **not**
    the bot's pre-close breakout purchase. Results are never mixed with the bot's breakouts.
  - Eligible: PIT member, RS ≥ 85 (`rs_pit500`), SPY > MA50.
- **Trades:** `backtest.simulate(entry_at="open")`: stop base × 0.97, 20-session exit.
- **Portfolio:** `portfolio_bt.replay`, unchanged: $10,000, 1 % risk, 5 positions, 3 new per
  day, 20 % cap, 10 bps per side (stress 25 bps).
- **Only the same-day order of the candidates differs** between the books.

## 3. Data (official SEC files only; used only from their publication date)
| Source | Content | Time stamp used |
|---|---|---|
| SEC **Insider Transactions Data Sets** (Forms 3/4/5, quarterly, 2016 Q1 →) | non-derivative transactions: code, shares, price; reporting owner; issuer CIK and trading symbol | `FILING_DATE` |
| SEC **Form 13F Data Sets** (2016 →) | each 13F-HR's holdings: CUSIP, shares, value; report period | `FILING_DATE` |
| SEC **Fails-to-Deliver** data (twice monthly) | CUSIP ↔ trading symbol | to map CUSIPs to tickers only |
| SEC `company_tickers.json` + Form 4 issuer symbols | ticker ↔ CIK | mapping only |

**Point-in-time rule:** a filing is usable for a signal on day *d* (decided at the close of
*d*) only if its **filing date is strictly before *d***. Same-day filings are excluded, because
the acceptance time is not in the data sets. Amended 13F-HR/A are excluded (their dates
differ from the original). The test suite checks that no feature uses a filing dated on or
after the signal day.

## 4. Features (no fitted weights)
- **F1 — insider buying.** Number of **distinct reporting insiders** with an open-market
  **purchase** (transaction code `P`, non-derivative, acquired) in the issuer's stock, filed in
  the **90 calendar days** before *d*. Sales are ignored: most are pre-planned or for
  compensation.
- **F2 — 13F ownership breadth change.** For the latest report quarter *Q* whose 13F-HR
  filings are public before *d*, the number of 13F filers holding the stock in *Q* (filed
  before *d*) minus the number holding it in *Q−1*, divided by the number in *Q−1*.
  - *Q* becomes usable from its 45-day filing deadline + 1 day. Before that, *Q−1* is used.
    This avoids comparing a partly filed quarter with a complete one.
  - Only filers present in both quarters count, so new or departed filers do not create
    breadth by themselves.
- A missing feature is treated as **neutral**: F1 = 0, F2 = 0.

## 5. Ratings (orders) compared
| Book | Same-day order (ties → ticker) |
|---|---|
| **RS** | RS descending (current) |
| **INS** | F1 descending, then RS |
| **BR** | F2 descending, then RS |
| **IR** | mean of the day's percentile ranks of F1 and F2, descending, then RS |
| **RND** | 200 random orders (seeds 1–200): the luck distribution |

## 6. Periods, outputs, decision
- **Books:** full 2017-10 → 2026-10; **development** 2017-10 → 2021-12; **holdout**
  2022-01-03 → end (fresh books).
- **Reported for every book:** return, CAGR, max drawdown, profit factor, trades, yearly
  returns.
- **Signal-level information content:** daily Spearman IC of F1 / F2 / IR vs net R
  (non-overlapping trades), mean and month-bootstrap interval.
- **Coverage by year:** share of eligible candidates with any Form 4 data, with F1 > 0, with
  a 13F match, and with a usable F2.
- **Publication-time check:**
  - lag distribution Form 4 filing date − transaction date;
  - lag distribution 13F filing date − period end;
  - a count of filings that would have been used before publication (must be 0).
- **Decision (per strategy).** A rating **improves** on RS-first only if:
  - in **both** development and holdout, its return > RS's and above the **80th percentile
    of RND**; and
  - its max drawdown is not more than 3 points deeper than RS's; and
  - the holdout result holds at 25 bps.
- **Otherwise:**
  - **not improved** if the coverage requirement below is met;
  - **undetermined** if the 13F match covers < 70 % of eligible candidates in any full
    year, or if F1 is > 0 for < 5 % of candidates (too little signal to judge).
- Four ratings are tested, so a single pass is weak evidence. A forward paper test, decided
  by the owner, is the only confirmation.
