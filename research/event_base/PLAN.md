# Event & First-Base Breakout v1 — plan and pre-registration

Written on 2026-10-25, **before any result of this study was computed**. The owner's full task
text is reproduced verbatim in the appendix. This file fixes how the technical ambiguities of
that text are resolved. Thresholds and rules are not changed after results are seen.

**Status: exploratory.**
- The whole 2017–2026 period was already examined in earlier studies. Neither half is a new
  independent holdout.
- Passing the criteria is only a reason to discuss a future paper test. It does not authorise
  one and does not prove future returns.
- The historical drawdown limit is not a guarantee of future losses.

**Not changed:**
- Production, existing Paper and Trading, orders, positions, stops of live books, secrets and
  `TRADING=dry`.
- No paper book, no real orders, no schedules. The Draft PR is never merged.

## 0. Code and data versions (pinned)
**Branch** `research/event-base-v1` starts from `origin/main` f0c784d.
- `portfolio_bt.py`, `backtest.py` and `core.py` are taken from main. `portfolio_bt.py` and
  `backtest.py` are byte-identical to the research branches.
- The `core.py` difference touches only `evaluate_journal`, which no research code here uses.
- **Copied unchanged** from `origin/research/breakout-ma200-v1` @ 531960c:
  - `research/sp1500/{data,engine,rules,run,universe,test_sp1500}.py`, `RULES.md`,
    `membership_evidence.csv` (last change 301c651);
  - `research/crisis/{run,test_crisis}.py` (bd87e01);
  - `research/long_diagnostic/{run,test_diagnostic}.py`;
  - `research/results/sp1500/runs/2026-10-25T0156Z/universe.csv`
    (sha256 248deb17fe8fe3c781fcafd6eb94c8468ca26af8cce33d4105e74e82aa82f7d2);
  - the PR #23 reference `research/results/breakout_ma200/runs/2026-10-25T205752Z/results.json`,
    used only for the reproduction gate.

**Prices.** GitHub Actions artifact `shorts10y-dataset-40152515701` (run 40152515701):
- `bars.pkl.gz` and `sources/sp500_pit_fja05680.csv`; the SHA256 of both is written to the
  manifest;
- Yahoo daily bars with `auto_adjust=False`: OHLC split-adjusted, not dividend-adjusted;
  `Dividends` kept separately. Invalid bars were removed (a missing session, never repaired).

**Point-in-time S&P 500** (`fja05680` snapshots plus the current list, as in the crisis study):
- The run reports, by year, the share of PIT member-days without a price. Former members
  missing from Yahoo lack price history, so the early years carry survivorship bias of unknown
  sign.
- Yahoo symbols are current symbols. A symbol reused by another company is a known limitation
  of the price set; it cannot be fixed here.

**BIL:** downloaded in the run (yfinance, `auto_adjust=False`, `actions=True`). Its SHA256 is
recorded. If the download fails, the 50/50 SPY/BIL comparison is marked **incomplete**.

**Calendar and windows.** The calendar is the SPY sessions. The first test session is `cal[260]`;
the run asserts it equals **2017-11-03**. The last session is **2026-10-23**.

| Window | Sessions | Book |
|---|---|---|
| full | 2017-11-03 – 2026-10-23 | own $10,000 |
| 2017–2021 | 2017-11-03 – 2021-12-31 | own $10,000 |
| 2022–2026 | 2022-01-03 – 2026-10-23 | own $10,000 |

- A signal is used if its signal session lies inside the window.
- An order whose execution session would fall after the window end is not executed.
- Positions open at the end are marked at the last close, without an invented exit.

## 1. Reproduction gate (old M, old rules)
- **What is rebuilt:** M of PR #19 / #23 (`CR.trades_for(CR.eligible(sig, True), data,
  "breakout")` plus the unchanged `portfolio_bt.replay` with `CR.CFG`: 1 % risk, 20 % cap,
  actual open entry) for full, 2017–2021 and 2022–2026 at 10, 25 and 50 bps.
- **Pass condition:** return and max DD within 1e-6, with equal trade counts, against the PR #23
  reference. If it fails, the run stops.
- **It is not a control.** M uses the old execution and risk model. The +47.84 % of M is never
  compared directly with C, S or E.

## 2. Variants
**Common candidate filters**, applied on the signal session:
- point-in-time S&P 500 member;
- `rs_pit500 >= 85`: the production RS score ranked within that day's PIT members, 1..99;
- SPY close > SMA50 **and** > SMA200 (`core.market_regime`).

**Same-day priority:** RS descending, then ticker ascending.

**C — control.**
- The existing three-session breakout `backtest.breakout_at(x, i, 3)`: close above the highest
  high of the three previous bars.
- Stop = that level × 0.97.
- No signal-level ownership rule: the portfolio decides (one position or open order per ticker).

**S — first exit from a contracting base.** All parameters fixed, no search.
- **Detection** after the close of ticker bar `t`. The window is the 20 bars `t-19..t`. It needs
  21 bars `t-20..t` that fall on 21 **consecutive SPY sessions**. Bar `t-20` supplies the
  previous close for the first true range. A missing or removed bar breaks continuity.
- **True range:** `TR_k = max(H_k, C_{k-1}) - min(L_k, C_{k-1})`, using the previous completed
  close.
- **Width:** `max(H[t-19..t]) / min(L[t-19..t]) - 1 <= 0.12`.
- **Compression:** `mean(TR[t-4..t]) <= 0.75 * mean(TR[t-19..t-10])`. Bars `t-9..t-5` are not
  used.
- **Degenerate bars** (added 2026-10-25 after a crash on the first run, before any S result existed):
  if `mean(TR[t-19..t-10]) = 0` (stale bars with H = L = C), no contraction can be measured
  and the window is not a base.
- **Fixed on detection:** `base_high = max H`, `base_low = min L`, `base_start = date(t-19)`,
  `base_end = date(t)`. They never move.
- **Watch** sessions `t+1..t+10`: the next 10 ticker bars, each on the next consecutive SPY
  session. At each watch bar `j`:
  - `C_j > base_high` → **signal at j**. Strictly above; an equal close is not a signal.
  - `C_j < base_low` → **cancelled**.
  - otherwise the watch continues.
  - After 10 bars without either → **expired**.
  - A missing session during the watch ends the base (**broken**).
- **One base at a time per ticker.** While a base is being watched, no new base is detected.
  The formation window of the next base must start after the `base_end` of the previous used
  base, so windows never overlap. Signal, cancellation, expiry and breaking all count as use.
- **The first exit is consumed** even if it fails the market / RS / membership filter, or later
  the capital / execution rules. There is no waiting for a later "good" day.
- **Stop** = `base_high × 0.97`. No base-low or ATR stop in this experiment.
- **Warm-up:** detection starts at bar `bt.WARMUP` (260), as for C. Signals count only inside
  the window.

**E — event plus structure** (§4). The S signal is kept only if a confirmed raise of full-year
revenue guidance is in force.

**S-covered** = S restricted to exactly the candidates whose event status is **known** (raise or
confirmed non-raise). E is compared only with S-covered.

## 3. Execution and capital model (identical for C, S, E)
A separate research adapter, `research/event_base/execution.py`. `portfolio_bt.replay` is not
used for C / S / E, and no production code changes.

**Sizing.** Capital $10,000; whole shares; no leverage, no shorts.

**After the close of the signal session t** (orders processed in RS order):
- **Equity basis:** `E_t = cash_t + Σ qty × last close ≤ t` (all of day t's exits settled).
- **Limit** = `C_t × 1.01`.
- **Slots:** held positions plus accepted orders ≤ 5. Positions that will exit tomorrow still
  occupy their slot.
- At most **3 new orders a day**; one position or order per ticker.
- **Order size:** `qty = floor(min(0.005·E_t / (limit − stop), 0.10·E_t / (limit·(1+fee)),
  free_cash / (limit·(1+fee))))`. `free_cash` is cash minus the reservations already made that
  evening.
- `qty < 1` → skipped (`capital_or_risk`).
- Planned risk is measured from the limit, the worst allowed fill.

**At the next session t+1** (the next SPY session; the ticker's next bar must be dated that
session):
- **No bar on t+1** → the order expires (`no_bar`).
- **`O > limit`** → the order expires (`above_limit`). There is no intraday second chance.
- **`O <= limit`** → fill at `O` with the precomputed `qty`. The reservation is released and the
  cost is `qty·O·(1+fee)`.
- **`O <= stop`** → bought at O and sold at O in the same session, both fees paid
  (`entry_at_or_below_stop`). The trade is kept.

**Exits.** The stop is fixed.
- **On the entry bar:** `L <= stop` → exit at the stop. The open was above the stop, so the touch
  came after the fill.
- **Later bars:** `L <= stop` → exit at `min(O, stop)`, i.e. at the open on a gap.
- **Time exit:** the close of ticker bar `e+20`, the existing engine convention.

**Daily order:**
1. open fills;
2. exits;
3. at the close: dividends credited, exit proceeds settled, equity marked, next orders created.

Proceeds of a session's exits are never available at that session's open. They can be used for
orders placed after its close.

**Dividends:** `qty × Dividends` on the ex-date, for a position held at the previous close
(`entry session < ex-date <= exit session`). Credited once, as cash, on the ex-date; the real
payment date is later (a simplification). Recorded separately.

**Costs:** `bps` of traded notional on each side (10 and 25; 50 = stress).

**Reconciliation (fail closed):**
- `final equity = initial + Σ closed net P&L + Σ dividends + Σ open (qty·mark − entry cost)`, to
  the cent;
- cash is never negative;
- reservations never exceed cash.

**Sensitivity**, reported but not a decision criterion. Each runs on the full window at 10 and
25 bps, as one book (no random portfolios):

| Name | Change |
|---|---|
| stop slippage | every stop exit fills 0.5 % below the modelled price |
| intrabar worst | a stop touched on a bar exits at that bar's Low |
| tight limit | limit = `C_t × 1.00` |
| 20 % non-fill | a deterministic 20 % of orders, chosen by `sha256(variant|ticker|date) mod 5 == 0`, are not filled |

**Known limits:**
- The open fill is a model of the opening auction on daily bars.
- The stop fill ignores intraday liquidity.
- Same-bar sequences beyond those above are unknown on daily bars.

## 4. Event E (SEC 8-K)
**Source:** original SEC EDGAR filings only.
- 8-K filings with Item 2.02, and their EX-99.x press-release exhibits.
- Times come from EDGAR `acceptanceDateTime`.
- No paid AI APIs. No news sentiment, price gaps or analyst expectations as substitutes.

**Historical identity of the issuer:**
- A ticker on a date is mapped to a CIK only through issuer trading symbols reported in Forms
  3/4/5. The source is the SEC Insider Transactions Data Sets table `f345_sub.csv.gz` from
  artifact `v2src-40196473096`.
- The mapping holds only if exactly one CIK reported that symbol within ±365 days of the date.
- Otherwise the identity is `unknown`. A current ticker → CIK file is never used.

**Guidance extraction** (deterministic regex, the same code for every filing):
- A sentence mentioning revenue / net sales / sales together with an outlook word (`expect`,
  `guidance`, `outlook`, `anticipate`, `range`, `project`, `forecast`).
- A full-year period label: `fiscal 20XX`, `FY20XX`, `full year 20XX`, `20XX` plus `full year` or
  `fiscal year`.
- A USD range `$X (million|billion) to/- $Y (million|billion)` or `between $X and $Y`.
- Values are normalised to USD.
- A sentence with a non-USD currency, or a period label that cannot be read, is
  `not comparable`.
- Each extraction keeps the exhibit URL, accession number, CIK, SHA256 of the document,
  acceptance time and a quoted excerpt.

**Raise** (same CIK, same fiscal-year label, USD): `new_low >= old_low`, `new_high >= old_high`,
`new_mid > old_mid`. `old` is the most recent earlier parsed range for that period.

**Timing**
- A filing is usable from the calendar day **after** its acceptance date, never the same day.
- The raise must be usable on or before `base_start`; acceptance date < base_start.
- On the signal date the raise must be no older than **60 SPY sessions**, counted from its usable
  day.
- The fiscal year must not be over on the signal date. The year end comes from the EDGAR
  `fiscalYearEnd` of the CIK. If the label year cannot be mapped unambiguously to an end date,
  the status is `unknown`.
- **Superseding update:** any later usable update (≤ signal date) for that period that is not a
  raise, cannot be compared, or withdraws guidance cancels the raise.

**Status per S candidate** (computed without looking at any return):

| Status | Meaning |
|---|---|
| `raise` | E qualifies |
| `known_no_raise` | the latest parsed update in force is not a qualifying raise, and every Item 2.02 release from that update to the signal date was retrieved and parsed |
| `unknown` | anything else: identity unknown, a release not retrieved, guidance not found, period not comparable |

- **A missing match is never read as "no event".**
- **One structural signal per event:** a raise is consumed by the first S signal that uses it,
  before market, capital and execution filters.

**Coverage** = (`raise` + `known_no_raise`) / all S candidates, by full calendar year.

**Pilot first** (no returns loaded):
- A stratified sample of S candidates: 10 per calendar year 2018–2025 (fewer if a year has fewer),
  drawn with seed 20261025 before any event data is downloaded.
- If pilot coverage is below 80 % in any full year, **E = INSUFFICIENT_DATA**. No full collection
  is made and no E return is computed.
- C versus S is never delayed by E.

## 5. Index alternatives (same windows)
**ETF costs:** 2 bps per side (sensitivity 5 bps). SPY and BIL use `auto_adjust=False` prices
plus their distributions, credited on the ex-date and reinvested at that close (with costs).
Fund expenses are already in the prices and are not deducted again.

| Benchmark | Rule |
|---|---|
| **SPY 100 %** | bought at the first session's open, distributions reinvested |
| **50 % SPY / 50 % cash** | cash earns 0 %; monthly rebalance to 50 / 50 |
| **50 % SPY / 50 % BIL** | monthly rebalance; BIL distributions reinvested in BIL |
| **SPY timing** | 50 % of equity in SPY while SPY > SMA50 and > SMA200, otherwise all cash (0 %); monthly rebalance to 50 % while on |

- **Monthly rebalance:** decided after the close of the last session of a month, executed at the
  next session's open.
- **SPY timing:** decided after the close, executed at the next session's open.
- **First session:** the 50/50 benchmarks invest at its open; SPY timing waits for the first
  signal.
- If distributions are missing, a price-only diagnostic is shown and the economic comparison is
  marked incomplete.
- The trading books' idle cash earns 0 %; no BIL yield is credited to them.

## 6. Metrics
For each book:
- trades: executed, closed, open at end;
- return, CAGR, max DD (daily equity), annualised volatility of daily returns;
- PF (closed net P&L), win rate;
- turnover (traded notional per year / mean equity), costs paid, dividends;
- mean invested share;
- yearly returns and negative years;
- orders: placed, filled, expired above limit, expired with no bar, entered at or below the
  stop;
- skips by reason.

## 7. Decision criteria (fixed now)
A variant is a **research candidate** only if all of these hold:

1. **Drawdown:** max DD of daily equity ≥ −20.00 % on full, 2017–2021 and 2022–2026, at 10 and
   at 25 bps.
2. **Result:**
   - full-window return > 0 and PF > 1 at 10 and at 25 bps;
   - both half-books have return > 0 at 25 bps.
3. **Signal benefit:**
   - S: full CAGR(S) > CAGR(C) at 10 and 25 bps;
   - E: full CAGR(E) > CAGR(S-covered) at 10 and 25 bps.
4. **Versus 50 % SPY / 50 % BIL** (full window, at 10 and at 25 bps, benchmark at 2 bps), at
   least one of:
   - CAGR ≥ benchmark + 1.0 pt a year and max DD no more than 1.0 pt worse;
   - max DD at least 3.0 pt smaller and CAGR no more than 0.5 pt a year lower.
5. **No simpler benchmark dominates:** no benchmark of §5 whose full max DD is ≥ −20 % has both a
   strictly higher CAGR and a strictly smaller drawdown than the variant (full window, 10 and
   25 bps).
6. **Sample:**
   - C and S: ≥ 100 closed trades on the full window and ≥ 30 in each half-book;
   - E: ≥ 50 and ≥ 20.
   - Fewer trades means **INSUFFICIENT_DATA**, not a rejection.
7. **E only:** confirmed event coverage ≥ 80 % of S candidates in every full calendar year.
   Otherwise **INSUFFICIENT_DATA**.

**C is the control.** Its result against criteria 1, 2, 4, 5 and 6 is reported for information.

**Uncertainty** (exploratory, not a decision criterion):
- Paired daily return differences on the full window: S − C, S − 50/50 SPY/BIL and, if E is
  computed, E − S-covered.
- A block bootstrap by calendar month: 2,000 resamples, seed 20261025. It reports the annualised
  mean difference (252 × mean), its 90 % interval and the share of resamples above 0.
- Six comparisons are reported without a multiplicity correction; this is said in the results.
- No searches over random portfolios.

## 8. Mandatory technical tests (`test_event_base.py`)
1. Changing bars after t does not change bases detected up to t.
2. The first exit is used once, including when it fails a filter.
3. Base formation windows never overlap.
4. A later guidance update cancels an earlier raise.
5. Unknown ≠ absent.
6. No issuer confusion: ambiguous symbol → CIK is unknown.
7. Share count fixed before the open.
8. No cash from same-session exits at the open.
9. Expiry above the limit and when the bar is missing.
10. Entry at or below the stop.
11. A missing bar breaks a base.
12. Cash and P&L reconcile to the cent.
13. Dividends credited once.
14. A rerun is identical; output folders are write-once (no duplicates).

## 9. Outputs
**Run folder:** `research/results/event_base/runs/<UTC>/` (write-once). It contains:
- `trades_*.csv`, `orders_*.csv`, `equity_*.csv`;
- `s_candidates.csv`, without return columns;
- `results.json`, `manifest.json` (dataset, BIL and every output file with SHA256).

**Event sources:** `research/results/event_base/events/<UTC>/`, holding `source_registry.csv`,
`extractions.csv`, `coverage.json` and `manifest.json`.

**Summary:** one `research/event_base/RESULTS.md`. Earlier studies are not overwritten.

---

## Appendix — owner's task (verbatim)

Claude, начинаем исследование Event & First-Base Breakout v1 в репозитории 360profcorp/stock-screener.

Это полное текстовое задание. Вложений не будет. Не жди архив, PLAN.md или готовый код: создай необходимые файлы и реализацию по этому сообщению.

Цель владельца — полезная доходность после расходов при максимальной исторической просадке не выше 20%, с обязательным сравнением с простыми индексными портфелями. Исторический предел не является гарантией будущих потерь.

1. Границы работы

Работай в отдельной ветке research/event-base-v1 от актуального main. Необходимые зависимости из прежних исследовательских веток перенеси явно, зафиксировав исходные версии.

Создай Draft PR. Не сливай его и не включай расписания.

Не менять: Production, существующие Paper и Trading, заявки, позиции, стопы действующих книг, секреты и TRADING=dry. Новые бумажные портфели и реальные сделки не запускать.

Это новое исследование входов, а не продолжение подбора параметров MA200 или Runner. Весь уже просмотренный период 2017–2026 считать разведочным, а не независимым подтверждением.

2. Сравниваем только три варианта

C — контроль. Существующий трёхдневный Breakout. Условия рынка: SPY выше SMA50 и SMA200. RS акции ≥85. Приоритет кандидатов — RS по убыванию, при равенстве — тикер.

S — структура. Первый выход из заранее зафиксированной сжимающейся консолидации. Фильтры SPY и RS те же, что у C.

E — событие плюс структура. Тот же S, но после подтверждённого повышения годового прогноза выручки компании. Событие должно быть известно до начала формирования всей базы.

Чтобы не смешать пользу события с качеством покрытия данных, E дополнительно сравнивается с S-covered: вариантом S на точно том же наборе бумаг и дат, для которого достоверно установлена полнота наблюдения за событиями.

Отсутствие найденных данных о событии нельзя считать доказанным отсутствием события.

Другие индикаторы, секторные фильтры, BR, новые выходы и комбинации в этот прогон не добавлять. Перебора параметров нет.

3. Точное определение структурного сигнала S

После закрытия сессии t исследуй 20 завершённых последовательных биржевых сессий акции.

База подходит, если одновременно выполняются условия:

* Ширина: max(High) / min(Low) − 1 ≤ 12%.
* Сжатие: средний True Range последних 5 сессий не превышает 0,75 среднего True Range первых 10 сессий этого же двадцатидневного окна.

True Range рассчитывается с использованием предыдущего завершённого закрытия.

После обнаружения базы зафиксируй её максимум, минимум, дату начала и дату окончания. Не передвигай эти границы после появления новых свечей.

Сигнал — первое последующее дневное закрытие строго выше зафиксированного максимума в течение следующих 10 биржевых сессий.

Закрытие ниже зафиксированного минимума отменяет базу. Сигнал, истечение срока или отмена завершают её использование. Окно формирования следующей базы не должно пересекаться с использованным окном формирования предыдущей.

Пропущенная или некорректная свеча прерывает непрерывность.

Если первый выход не прошёл фильтр рынка или RS, он всё равно считается использованным. Нельзя ждать следующего удачного дня и называть его первым выходом.

Начальный стоп: зафиксированный максимум базы ×0,97. В этом эксперименте не заменять его стопом под минимумом базы или ATR-стопом: сначала изолируем влияние определения сигнала.

Числа 20, 12%, 5/10, 0,75 и 10 сессий — фиксированные исследовательские допущения, а не доказанные оптимальные значения.

4. Точное определение события E

Используй оригинальные приложения к SEC Form 8-K с результатами компании либо независимо проверяемые архивные публикации самого эмитента.

Нужны предыдущий и новый числовые диапазоны годового прогноза выручки, относящиеся к одному эмитенту, одному финансовому периоду, одинаковой валюте, единицам измерения и сопоставимому составу бизнеса.

Повышение подтверждено, если:

новая нижняя граница ≥ предыдущая нижняя граница;

новая верхняя граница ≥ предыдущая верхняя граница;

новая середина диапазона > предыдущая середина диапазона.

Сохраняй ссылки, идентификаторы подач и эмитента, исходные документы, SHA256, подтверждающие выдержки, время доступности обеих публикаций и исторически корректную привязку ценной бумаги.

Не переносить современные тикеры и CIK на прошлых владельцев символа.

Консервативно исключать использование публикации в тот же календарный день. Использовать проверяемое время принятия SEC или публичной доступности, а не конец отчётного квартала и не дату поздней пересказанной статьи.

Событие должно быть известно до первой сессии всей базы, а на дату сигнала — не старше 60 биржевых сессий. Период прогноза не должен быть завершён.

Последующее известное обновление прогноза — нейтральное, негативное, отозванное или несопоставимое — отменяет действие прежнего повышения.

На одно событие допускается один исходный структурный сигнал. Он расходуется до применения фильтров рынка, капитала и исполнения.

Собирай не только повышения, но и остальные обновления, а также неизвестные случаи. Начни с проверяемого ручного или детерминированного пилота без просмотра последующей доходности.

Платные AI API не подключать. Не подменять повышение прогноза гэпом цены, тональностью новости или придуманными историческими ожиданиями аналитиков.

Если надёжное покрытие получить невозможно, E получает статус INSUFFICIENT_DATA. Это не должно задерживать сравнение C и S.

5. Одинаковая модель капитала и исполнения для C, S и E

Начальный капитал — $10 000.

Плановый риск новой сделки — максимум 0,5% капитала. Размер новой позиции — максимум 10% капитала. Одновременно максимум 5 позиций, максимум 3 новых входа за день. Плечо и шорты запрещены.

После закрытия сигнального дня заранее зафиксируй лимит покупки на следующем открытии:

лимит = цена закрытия сигнального дня ×1,01.

Количество целых акций и резерв денег рассчитываются до появления фактической цены открытия, по этому лимиту, расходам и стоимости портфеля на предыдущем закрытии.

Уже открытые позиции занимают свои места. Деньги от выходов, которые произойдут позже в новой сессии, нельзя использовать для покупок на её открытии.

На непосредственно следующей биржевой сессии:

* Если открытие выше лимита — исполнения нет, заявка истекает. Внутридневного повторного шанса нет.
* Если открытие не выше лимита — моделируется исполнение по открытию с заранее определённым количеством акций.
* Если открытие оказалось на уровне защитного стопа или ниже — учитывать модельную покупку и немедленное закрытие с расходами. Нельзя задним числом удалить такую сделку.
* Если свеча следующей сессии отсутствует — кандидат истекает. Не переносить покупку на удобную последующую дату.

Исходный стоп остаётся фиксированным. При последующем гэпе ниже стопа выход моделируется по открытию.

Выход по времени — закрытие бара e+20, по существующей конвенции движка. Оставшиеся позиции на конце данных переоцениваются, а не получают выдуманное закрытие.

Модель аукционного исполнения и немедленного стопа на дневных свечах приблизительная. Отдельно указать ограничения и проверить чувствительность к проскальзыванию, неисполнению и неизвестной последовательности движения внутри свечи.

Важно: существующий portfolio_bt.replay рассчитывает размер от заранее рассчитанной фактической цены входа. Простая фильтрация его входных строк не реализует описанную модель. Нужен отдельный исследовательский адаптер с последовательным учётом денег, заявок и позиций. Производственный код не менять.

6. Данные и исходная проверка

Переиспользуй сохранённый набор из GitHub Actions #40152515701. Зафиксируй полные хеши, состав S&P 500 на соответствующие даты и недостатки покрытия исключённых компаний.

Сначала воспроизведи прежний контроль M из PR #19/#23 с его прежними правилами исполнения и риска. Это проверка воспроизводимости, а не новый контроль для сравнения сигналов.

Затем C, S и E должны использовать одинаковую новую модель исполнения и риска из раздела 5.

Нельзя сравнить новые S/E напрямую со старыми +47,84% и приписать всю разницу качеству сигнала: одновременно изменились исполнение и размер позиций.

Окна:

* Полный период: 2017-11-03 — 2026-10-23.
* 2017–2021 — отдельный портфель с первоначальными $10 000.
* 2022–2026 — отдельный портфель с первоначальными $10 000.

Покажи фактические даты покрытия. Уже просмотренные половины истории не называть новым независимым holdout.

7. Расходы и индексные альтернативы

Для акций: 10 и 25 б.п. на каждую сторону, 50 б.п. — стресс-сценарий.

Для экономических выводов нужен корректный учёт дивидендов и корпоративных действий без двойного начисления. Основной остаток денег у бота получает нулевую доходность. Не начислять ему выдуманный доход BIL.

На тех же датах сравни:

100% SPY с распределениями;

50% SPY / 50% денежных средств с нулевой доходностью резерва;

50% SPY / 50% BIL с ежемесячной ребалансировкой;

простой индексный контроль: 50% капитала в SPY при SPY выше SMA50 и SMA200, остальное в деньгах; при невыполнении условий — полностью деньги. Решение после закрытия, исполнение не раньше следующей сессии.

Для ETF зафиксируй расходы 2 б.п. на сторону, дополнительная чувствительность — 5 б.п.

Учитывай распределения и фактические операции с резервом. Не вычитай расходы фонда повторно, если они уже отражены в его стоимости.

Если история распределений или резервного инструмента недоступна, покажи ценовую диагностику и прямо отметь экономическое сравнение как неполное.

8. Критерии оценки фиксируются до результатов

Для исследовательского кандидата требуется:

Просадка: не выше 20,00% по ежедневной стоимости всего портфеля за полный период и в обоих отдельных подокнах, при расходах 10 и 25 б.п.

Результат: полная доходность положительная и PF >1 при обоих уровнях расходов; обе половины истории также положительные при 25 б.п.

Дополнительная польза сигнала: S улучшает полный CAGR относительно нового C при 10 и 25 б.п.; E улучшает CAGR относительно S-covered при тех же расходах.

Польза против 50% SPY / 50% BIL: выполняется хотя бы одно условие:

* CAGR минимум на 1 процентный пункт в год выше, а просадка не более чем на 1 пункт хуже;
* просадка минимум на 3 пункта меньше, а CAGR ниже не более чем на 0,5 пункта в год.

Более простой эталон, укладывающийся в ограничение просадки, не должен одновременно превосходить кандидата и по доходности, и по просадке.

Минимальная выборка: для технических вариантов — 100 закрытых сделок за полный период и 30 в каждой половине; для E — 50 и 20 соответственно.

Подтверждённое покрытие событий — минимум 80% исходных кандидатов S в каждом полном году. Недостаток данных или сделок означает INSUFFICIENT_DATA, а не опровержение экономической идеи.

Прохождение этих критериев — только основание обсудить будущий бумажный тест, не разрешение на его запуск и не доказательство будущей доходности.

Пороги после просмотра результатов не менять. Не запускать новые поиски на сотнях случайных портфелей. Для разведочной оценки неопределённости использовать парные дневные разности доходностей и заранее фиксированный блочный бутстрэп по месяцам на 2 000 повторений, указав ограничения и множественность сравнений.

9. Порядок выполнения и результат

Сначала сохрани это задание в PLAN.md, зафиксируй версии кода и явно разреши технические неоднозначности до расчёта результатов.

Затем воспроизведи прежний M, реализуй C/S и проведи их сравнение. Не задерживай техническую часть из-за недоступных архивных новостей.

Отдельно проверь источники для E. Его доходность рассчитывай только после проверки покрытия, времени публикаций и исторической идентификации компаний.

Обязательные технические тесты: будущие свечи не меняют прошлые базы; первый сигнал расходуется один раз; окна баз не переиспользуются с пересечением; новое обновление прогноза отменяет старое повышение; неизвестное событие не равно отсутствующему; нет путаницы эмитентов; количество акций фиксируется до открытия; деньги от будущих выходов не используются; корректны истечение заявок, вход ниже стопа, пропущенные свечи, сверка денег и P&L, однократное начисление дивидендов и повторный запуск без дубликатов.

Подготовь один итоговый RESULTS.md: количество сделок, доходность, CAGR, максимальная просадка, волатильность, PF, оборот, расходы, доля вложенного капитала, плохие годы, неисполненные заявки, неизвестные события и решение по каждому варианту.

Сохрани сделки, решения, кривые капитала, реестр источников и полный manifest прогона. Старые исследования не перезаписывать.

Нужны реальные результаты C против S. E — только при достоверных данных. Если есть блокер, сообщи конкретно, чего не хватает. Пока исторический прогон не выполнен, не называй подготовленный план или код завершённым исследованием.