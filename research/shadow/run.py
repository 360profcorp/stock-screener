"""Shadow paper books runner (PREREG_SHADOW.md). NO broker, NO real orders.

    python -m research.shadow.run daily    after the US close: one S&P 500 list and one price
                                           download for both books; due 13F quarters are read
                                           from EDGAR first; every new session is processed
                                           for both books, then the closed session is scanned
                                           and orders are queued before the next open
    python -m research.shadow.run report   rewrite REPORT.md / report.json / decisions.csv
    python -m research.shadow.run verify   real-data equivalence of the br book with the
                                           replay engine on the BR order (before activation)

Never writes paper/, state/, the bot or its settings. There is no reset option.
"""
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import core
import paper_run as PR
from paper import books as PB
from paper import metrics as pm
from paper import store
from paper.screener import truncate
from research.shadow import books as SB
from research.shadow import f13

ROOT = Path(__file__).resolve().parents[2]


def breadth_path(root=ROOT):
    return Path(root) / "research" / "shadow" / "f13" / "breadth.csv"


def ensure_quarters(days, root=ROOT, ingest=f13.ingest):
    """Every 13F quarter due on any of `days` must be in breadth.csv before scanning."""
    br = pd.read_csv(breadth_path(root), usecols=["period"])
    have = set(br["period"].astype(str))
    done = []
    for p in sorted({f13.latest_due(d) for d in days} - {None}):
        if str(p.date()) not in have:
            done.append(ingest(p))
            have.add(str(p.date()))
    return done


def daily(universe=None, prices=None, now=None, root=ROOT, refetch="auto", ingest=f13.ingest):
    now = now or datetime.now(timezone.utc)
    if refetch == "auto":
        refetch = PR._refetch if prices is None else None
    universe = core.get_sp500() if universe is None else universe
    frames, spy, sectors = PR.load_market(universe, prices)
    data_date = PR.closed_data_date(frames, now)
    fp = SB.code_fingerprint()
    gen = now.isoformat(timespec="seconds")
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    usig = hashlib.sha256(",".join(sorted(map(str, universe["ticker"]))).encode()).hexdigest()[:12]
    ef = SB.experiment_file(root)
    exp = json.loads(ef.read_text()) if ef.exists() else None
    P = {b: SB.paths(b, root) for b in SB.BOOKS}
    states = {b: store.load_state(P[b]["state_file"]) for b in SB.BOOKS}
    present = sorted(b for b, s in states.items() if s is not None)
    if exp is None:
        if present:
            raise SB.BooksOutOfStep(f"book state {present} exists without experiment.json")
        if str(data_date.date()) < SB.EARLIEST_START:
            raise SB.BooksOutOfStep(f"start session {data_date.date()} is before the pre-registered "
                                    f"earliest start {SB.EARLIEST_START}")
        label = f"shadow-br-{data_date.date()}"
        exp = dict(experiment=label, created_at=gen, start_session=str(data_date.date()),
                   first_entry_session=store.next_session(data_date),
                   books={b: SB.strategy_id(b) for b in SB.BOOKS}, code_fingerprint=fp["combined"],
                   universe_sha=usig, universe_size=len(universe),
                   prereg="research/shadow/PREREG_SHADOW.md",
                   note="Two forward shadow books from $10,000 with no positions, same list and "
                        "prices; only the same-day order differs. Research only.")
        states = {b: SB.new_book_state(b, label, fp) for b in SB.BOOKS}
        new = True
    else:
        if present != sorted(SB.BOOKS):
            raise SB.BooksOutOfStep(f"experiment {exp['experiment']} but only {present} saved")
        for b, s in states.items():
            SB.check_book(s, b, fp, exp["experiment"])
        thr = {s["processed_through"] for s in states.values()}
        if len(thr) != 1:
            raise SB.BooksOutOfStep(f"books processed through different sessions: {thr}")
        new = False
    ports = {b: SB.PORTFOLIO[b](states[b], SB.BOOKS[b], kind="forward") for b in SB.BOOKS}
    last = states["rs"]["processed_through"]
    last = pd.Timestamp(last) if last else None
    sessions = sorted({d for d in spy.index if d <= data_date and (last is None or d > last)})
    if new:
        sessions = sessions[-1:]
    ingested = ensure_quarters(sessions, root, ingest)
    table = SB.F2Table(breadth_path(root))
    report = dict(run_id=run_id, data_date=str(data_date.date()), sessions=[], ingested=ingested,
                  events={b: [] for b in SB.BOOKS})
    for day in sessions:
        held = set().union(*(p.s["positions"] for p in ports.values()))
        probs = PR.data_problems(frames, day, held)
        tries = 0
        while probs and refetch is not None and tries < 2:
            tries += 1
            missing = [p.split("held ")[1].split(" ")[0] for p in probs if "held " in p]
            if not missing:
                break
            time.sleep(5 * tries)
            frames = refetch(frames, missing)
            probs = PR.data_problems(frames, day, held)
        if probs:
            raise PR.DataError("session not processed, nothing saved: " + "; ".join(probs))
        tr = truncate(frames, day)
        bars = {t: {"O": df["Open"].iloc[-1], "H": df["High"].iloc[-1],
                    "L": df["Low"].iloc[-1], "C": df["Close"].iloc[-1]}
                for t, df in tr.items() if df.index[-1] == day}
        bsha = PB.bars_sha(bars)
        spy_close = float(spy.loc[day, "Close"]) if day in spy.index else None
        nxt = store.next_session(day)
        late = store.is_late(gen, nxt)
        scan_rs = PB.scan_mode(tr, spy, day, SB.BOOKS["rs"], sectors, already_truncated=True)
        scan_f2 = SB.with_f2(scan_rs, day, table)
        scans = {"rs": scan_f2, "br": SB.rank_br(scan_f2)}
        row = dict(day=str(day.date()), bars_sha=bsha, processed_late=late)
        for b, port in ports.items():
            cfg = SB.BOOKS[b]
            report["events"][b] += port.step(day, bars, spy_close, processed_late=late)
            scan = scans[b]
            meta = dict(kind="forward", book=b, experiment=exp["experiment"], run_id=run_id,
                        generated_at=gen, signal_date=str(day.date()), scheduled_for=nxt, late=late,
                        strategy_id=SB.strategy_id(b), parameters=cfg.as_dict(), code_fingerprint=fp,
                        bars_sha=bsha, source=PR._source_meta(frames, spy, day, now, usig))
            store.write_snapshot(day, scan, meta, P[b]["snapshots"])
            store.append_signals(scan, gen, nxt, late, run_id, P[b]["signals"],
                                 extra=dict(book=b, strategy_id=SB.strategy_id(b),
                                            code_version=fp["combined"], kind="forward",
                                            experiment=exp["experiment"]))
            n = port.queue_signals(day, scan, gen, nxt, late)
            row[b] = dict(raw=0 if scan is None else len(scan), queued=n, late=late)
        report["sessions"].append(row)
    asof = truncate(frames, data_date)
    for b, port in ports.items():
        store.update_labels(asof, data_date, P[b]["signals"], P[b]["labels"], port.s, gen)
        port.s["revision"] = int(port.s.get("revision", 0)) + 1
        port.s["last_run"] = run_id
        store.save_state(port.s, P[b]["state_file"])
        store.export_tables(port.s, P[b]["state_dir"])
    if new:
        store._atomic_write(ef, json.dumps(exp, indent=1))
    rep = write_report(root)
    print(json.dumps(dict(data_date=report["data_date"], sessions=report["sessions"],
                          ingested=ingested, books={b: {k: r[k] for k in ("processed_through", "equity",
                                                                       "open_positions", "pending_orders")}
                                                   for b, r in rep["books"].items()}), default=str))
    return dict(report, comparison=rep)


# =====================================================================
# report: daily decisions, overlap, returns after costs, drawdowns, reasons
# =====================================================================
OUTCOME_TEXT = {"entered": "bought at the open", "positions": "not bought: 5 positions already held",
                "daily_entries": "not bought: 3 entries already made that day",
                "ticker_open": "not bought: already held", "capital_or_risk": "not bought: cash/risk too small",
                "no_trade_open_below_stop": "not bought: opened at/below the stop",
                "no_trade_max_risk": "not bought: risk above the limit", "invalid": "not bought: invalid stop",
                "not_traded_late": "not bought: signal recorded after the open (late)",
                "expired_no_bar": "dropped: no bar for 10 sessions"}


def costs_paid(state):
    fee = state["config"]["cost_bps"] / 1e4
    c = sum(t["shares"] * (t["entry"] + t["exit"]) * fee for t in state.get("ledger", []))
    c += sum(p["qty"] * p["entry"] * fee for p in state.get("positions", {}).values())
    return float(c)


def decisions(root=ROOT):
    """One row per eligible candidate per signal day, with both books' rank, the reason
    data (RS, F2, 13F holders, quarter used) and each book's next-session outcome."""
    rows = []
    snaps = {}
    for b in SB.BOOKS:
        for f in sorted(SB.paths(b, root)["snapshots"].glob("*.json")):
            snaps.setdefault(f.stem, {})[b] = json.loads(f.read_text())
    logs = {}
    for b in SB.BOOKS:
        s = store.load_state(SB.paths(b, root)["state_file"]) or {}
        for o in s.get("orders_log", []):
            logs[(b, o["signal_date"], o["ticker"])] = o
    for day, by in sorted(snaps.items()):
        sig = {b: {r["ticker"]: r for r in v["signals"]} for b, v in by.items()}
        el = sorted({t for v in sig.values() for t, r in v.items() if r.get("eligible")})
        for t in el:
            r = sig.get("br", {}).get(t) or sig.get("rs", {}).get(t)
            out = dict(signal_date=day, ticker=t, rs=r.get("rs"), F2=r.get("F2"),
                       holders_q=r.get("holders_q"), holders_q1=r.get("holders_q1"),
                       f13_quarter=r.get("f2_period"), f13_usable_from=r.get("f2_usable_from"),
                       f2_status=r.get("f2_status"), stop=r.get("stop"))
            for b in SB.BOOKS:
                rk = sig.get(b, {}).get(t, {}).get("rank")
                o = logs.get((b, day, t))
                out[f"rank_{b}"] = None if rk is None or rk != rk else int(rk)
                out[f"outcome_{b}"] = o["outcome"] if o else "pending"
                out[f"session_{b}"] = o["session"] if o else None
                out[f"shares_{b}"] = o.get("shares") if o else None
                out[f"open_{b}"] = o.get("open") if o else None
            f2 = "n/a" if out["F2"] is None else f"{100 * out['F2']:+.1f} %"
            hold = "" if out["holders_q"] is None else f", 13F holders {out['holders_q1']}→{out['holders_q']}"
            out["reason_rs"] = (f"RS rank {out['rank_rs']} (RS {out['rs']:.0f}); "
                                f"{OUTCOME_TEXT.get(out['outcome_rs'], out['outcome_rs'])}")
            out["reason_br"] = (f"BR rank {out['rank_br']} (F2 {f2}{hold}, 13F quarter "
                                f"{out['f13_quarter'] or '—'}, {out['f2_status']}; RS {out['rs']:.0f}); "
                                f"{OUTCOME_TEXT.get(out['outcome_br'], out['outcome_br'])}")
            rows.append(out)
    return pd.DataFrame(rows)


def book_metrics(state):
    init = state["config"]["initial_cash"]
    eq = pd.DataFrame(state.get("equity", []))
    led = pd.DataFrame(state.get("ledger", []))
    perf = pm.performance(eq, led, init) if len(eq) else None
    fr = pm.forward_report(state)
    return dict(start=state.get("start"), processed_through=state.get("processed_through"),
                equity=float(eq["equity"].iloc[-1]) if len(eq) else init, cash=state["cash"],
                return_after_costs_pct=perf["return_pct"] if perf else 0.0,
                max_drawdown_pct=perf["max_drawdown_pct"] if perf else 0.0,
                current_drawdown_pct=perf["current_drawdown_pct"] if perf else 0.0,
                spy_price_return_pct=perf["spy_price_return_pct"] if perf else None,
                closed_trades=len(led), win_rate_pct=perf["win_rate_pct"] if perf else None,
                profit_factor=perf["profit_factor"] if perf else None,
                open_positions=len(state.get("positions", {})), pending_orders=len(state.get("pending", [])),
                costs_paid_usd=costs_paid(state),
                genuine_forward=fr["genuine_forward"]["available"],
                contaminated_since=fr["genuine_forward"]["contaminated_since"],
                positions=[dict(ticker=t, qty=p["qty"], entry=p["entry"], stop=p["stop"],
                                entry_date=p["entry_date"]) for t, p in state.get("positions", {}).items()])


def overlap(states):
    ent = {b: {(o["ticker"], o["session"]) for o in s.get("orders_log", []) if o["outcome"] == "entered"}
           for b, s in states.items()}
    a, b = ent["rs"], ent["br"]
    u = a | b
    return dict(entries_rs=len(a), entries_br=len(b), common=len(a & b), only_rs=len(a - b),
                only_br=len(b - a), common_share_of_all_pct=100 * len(a & b) / len(u) if u else None,
                rs_entries_also_in_br_pct=100 * len(a & b) / len(a) if a else None,
                br_entries_also_in_rs_pct=100 * len(a & b) / len(b) if b else None)


def write_report(root=ROOT):
    ef = SB.experiment_file(root)
    exp = json.loads(ef.read_text())
    states = {b: store.load_state(SB.paths(b, root)["state_file"]) for b in SB.BOOKS}
    reps = {b: book_metrics(s) for b, s in states.items()}
    ov = overlap(states)
    D = decisions(root)
    base = ef.parent
    D.to_csv(base / "decisions.csv", index=False)
    eqs = []
    for b, s in states.items():
        e = pd.DataFrame(s.get("equity", []))
        if len(e):
            eqs.append(e[["date", "equity"]].rename(columns={"equity": b}).set_index("date"))
    E = pd.concat(eqs, axis=1).reset_index() if eqs else pd.DataFrame()
    if len(E):
        E.to_csv(base / "equity_daily.csv", index=False)
    rep = dict(experiment=exp["experiment"], start_session=exp["start_session"],
               first_entry_session=exp["first_entry_session"], books=reps, overlap=ov,
               generated=datetime.now(timezone.utc).isoformat(timespec="seconds"),
               note="Forward shadow paper books, research only. The PR #20 backtest is not "
                    "independent confirmation. No winner before the pre-registered horizon.")
    (base / "report.json").write_text(json.dumps(rep, indent=1, default=str))
    fmt = lambda v, f="{:+.2f} %": "—" if v is None or v != v else f.format(v)   # noqa: E731
    md = [f"# Shadow books {exp['experiment']}: Research Breakout RS-first vs Breakout BR", "",
          f"Start session {exp['start_session']}; first possible entry {exp['first_entry_session']}. "
          "Paper only, no broker. Research Breakout = entry at the next open (not the bot's "
          "pre-close breakout). Pre-registration: `research/shadow/PREREG_SHADOW.md`.", "",
          "| Book | Equity | Return after costs | Max DD | Current DD | Closed | Win % | Open | Pending | Costs paid | SPY (price) |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for b, r in reps.items():
        md.append(f"| {b} | ${r['equity']:,.2f} | {fmt(r['return_after_costs_pct'])} | "
                  f"{fmt(r['max_drawdown_pct'])} | {fmt(r['current_drawdown_pct'])} | {r['closed_trades']} | "
                  f"{fmt(r['win_rate_pct'], '{:.0f}')} | {r['open_positions']} | {r['pending_orders']} | "
                  f"${r['costs_paid_usd']:,.2f} | {fmt(r['spy_price_return_pct'])} |")
    md += ["", f"**Overlap of entries:** {ov['common']} common, {ov['only_rs']} only RS, {ov['only_br']} "
           f"only BR (common share {fmt(ov['common_share_of_all_pct'], '{:.0f} %')}).", ""]
    if len(D):
        md += ["## Decisions, latest 10 signal days", "",
               "| Signal day | Ticker | RS | F2 | 13F holders | RS book | BR book |", "|---|---|---|---|---|---|---|"]
        for r in D[D["signal_date"].isin(sorted(D["signal_date"].unique())[-10:])].itertuples():
            h = "—" if r.holders_q is None or r.holders_q != r.holders_q else f"{int(r.holders_q1)}→{int(r.holders_q)}"
            md.append(f"| {r.signal_date} | {r.ticker} | {r.rs:.0f} | {fmt(r.F2 * 100 if r.F2 == r.F2 else None, '{:+.1f} %')} | "
                      f"{h} | #{r.rank_rs}: {OUTCOME_TEXT.get(r.outcome_rs, r.outcome_rs)} | "
                      f"#{r.rank_br}: {OUTCOME_TEXT.get(r.outcome_br, r.outcome_br)} |")
    md += ["", rep["note"]]
    (base / "REPORT.md").write_text("\n".join(md) + "\n")
    return rep


# =====================================================================
# verification: br book == replay engine on the BR order (real data)
# =====================================================================
def verify(out=ROOT / "research" / "shadow" / "verify", days=250):
    import backtest as bt
    import portfolio_bt as pf
    from paper import verify as V
    from paper.portfolio import new_state
    t0 = time.time()
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    frames, spy, _ = PR.load_market()
    sig, data = bt.find_signals(frames, lookback=3, modes=["breakout"])
    cal = V.calendar(data)
    S, E = cal[-days], cal[-1]
    table = SB.F2Table()
    res = dict(generated=datetime.now(timezone.utc).isoformat(timespec="seconds"), window=[str(S.date()), str(E.date())],
               code_fingerprint=SB.code_fingerprint()["combined"], books={})
    for b, cfg in SB.BOOKS.items():
        mo = core.regime_mask(core.market_regime(spy), cfg.market_filter)
        trades = bt.simulate(sig, data, cfg.mode, hold=cfg.hold_days, stop_buf=cfg.stop_buf_pct,
                             min_rs=cfg.min_rs, min_vol=0.0, max_risk=cfg.max_risk_pct, market_ok=mo,
                             entry_at=cfg.entry_at, one_per_ticker=False, include_open=True)
        trades["F2"] = [table.get(t, d)["F2"] for t, d in zip(trades["ticker"], trades["signal_date"])]
        keys = ["date", "rs", "ticker"] if b == "rs" else ["date", "F2", "rs", "ticker"]
        asc = [True, False, True] if b == "rs" else [True, False, False, True]
        trades = trades.sort_values(keys, ascending=asc, kind="stable").reset_index(drop=True)
        ref = pf.replay(trades, data, initial_cash=cfg.initial_cash, risk_fraction=cfg.risk_fraction,
                        max_positions=cfg.max_positions, max_new_per_day=cfg.max_new_per_day,
                        max_position_fraction=cfg.max_position_fraction, cost_bps=cfg.cost_bps,
                        start=S, end=E, open_at_end="mark", record_decisions=True)
        el = V.eligible_signals(sig, mo, cfg)
        idx = V.bar_index(data)
        port = SB.PORTFOLIO[b](new_state(cfg, "verification"), cfg=cfg, kind="verification", trace=True)

        def signals_for(day):
            d = el[el["date"] == day]
            if d.empty:
                return d
            d = d.assign(eligible=True)
            d = d.sort_values(["rs", "ticker"], ascending=[False, True], kind="stable")
            d = d.assign(rank=np.arange(1, len(d) + 1))
            d = SB.with_f2(d, day, table)
            return SB.rank_br(d) if b == "br" else d
        prev = [d for d in cal if d < S]
        port.queue_signals(prev[-1], signals_for(prev[-1]))
        for day in [d for d in cal if S <= d <= E]:
            port.step(day, V.bars_on(data, idx, day))
            port.queue_signals(day, signals_for(day))
        r = V.compare(port, ref, cfg)
        res["books"][b] = r
    res["all_ok"] = all(r["ok"] for r in res["books"].values())
    res["runtime_sec"] = round(time.time() - t0)
    (out / "verify.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(res, indent=1, default=str)[:4000])
    return res


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "daily":
        daily()
    elif cmd == "report":
        write_report()
    elif cmd == "verify":
        sys.exit(0 if verify()["all_ok"] else 1)
    else:
        print(__doc__)
        sys.exit(1)
