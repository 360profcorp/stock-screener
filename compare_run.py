"""
Parallel paper comparison runner: Breakout RS-first vs Retest RS-first (control). NO broker,
NO real orders. The original Retest paper book (paper_run.py, paper/state, paper/data) is a
separate experiment and is never touched here.

  python compare_run.py daily     after the US close: one S&P 500 list and ONE price download
                                  for both books; every new session is processed in order for
                                  both books (same rules as paper_run.daily: fills at the open,
                                  stops, 20-session exits, marks, late / reconstructed flags),
                                  then the closed session is scanned and orders are queued
                                  BEFORE the next open. Re-running adds nothing twice.
  python compare_run.py restore DIR   restore both books from a backup artifact (all or
                                  nothing, only if strictly newer)
  python compare_run.py verify    real-data equivalence of both books with the replay engine
  python compare_run.py report    rewrite the comparison report from the saved states

There is deliberately no reset / new-experiment option: a strategy or code change stops both
books (StrategyChanged) until the owner decides.
"""
import hashlib
import json
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import backtest as bt
import core
import paper_run as PR
from paper import books as B
from paper import metrics as pm
from paper import store, verify as V
from paper.portfolio import PaperPortfolio, new_state
from paper.screener import rank_rs_first, scan_day, truncate

ROOT = Path(__file__).resolve().parent


# =====================================================================
# daily
# =====================================================================
def daily(universe=None, prices=None, now=None, root=ROOT, scan_fn=None, refetch="auto") -> dict:
    now = now or datetime.now(timezone.utc)
    scan_fn = scan_fn or B.scan_mode
    if refetch == "auto":
        refetch = PR._refetch if prices is None else None
    universe = core.get_sp500() if universe is None else universe
    frames, spy, sectors = PR.load_market(universe, prices)     # one download for both books
    data_date = PR.closed_data_date(frames, now)
    fp = B.code_fingerprint()
    gen = now.isoformat(timespec="seconds")
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    usig = hashlib.sha256(",".join(sorted(map(str, universe["ticker"]))).encode()).hexdigest()[:12]
    ef = B.experiment_file(root)
    exp = json.loads(ef.read_text()) if ef.exists() else None
    P = {b: B.paths(b, root) for b in B.BOOKS}
    states = {b: store.load_state(P[b]["state_file"]) for b in B.BOOKS}
    present = sorted(b for b, s in states.items() if s is not None)
    if exp is None:
        if present:
            raise B.BooksOutOfStep(f"book state {present} exists without experiment.json")
        label = f"cmp-{data_date.date()}"
        exp = dict(comparison=label, created_at=gen, start_session=str(data_date.date()),
                   first_entry_session=store.next_session(data_date),
                   books={b: B.strategy_id(b) for b in B.BOOKS}, code_fingerprint=fp["combined"],
                   universe_sha=usig, universe_size=len(universe),
                   note="Independent forward books started together from $10,000 with no "
                        "positions. The original Retest paper book is separate.")
        states = {b: B.new_book_state(b, label, fp) for b in B.BOOKS}
        new = True
    else:
        if present != sorted(B.BOOKS):
            raise B.BooksOutOfStep(f"experiment {exp['comparison']} but only {present} saved")
        for b, s in states.items():
            B.check_book(s, b, fp, exp["comparison"])
        thr = {s["processed_through"] for s in states.values()}
        if len(thr) != 1:
            raise B.BooksOutOfStep(f"books processed through different sessions: {thr}")
        new = False
    ports = {b: PaperPortfolio(states[b], B.BOOKS[b], kind="forward") for b in B.BOOKS}
    last = states["retest"]["processed_through"]
    last = pd.Timestamp(last) if last else None
    sessions = sorted({d for d in spy.index if d <= data_date and (last is None or d > last)})
    if new:
        sessions = sessions[-1:]                              # both books start on this session
    report = dict(run_id=run_id, data_date=str(data_date.date()), sessions=[],
                  events={b: [] for b in B.BOOKS})
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
        bsha = B.bars_sha(bars)
        spy_close = float(spy.loc[day, "Close"]) if day in spy.index else None
        nxt = store.next_session(day)
        processed_late = store.is_late(gen, nxt)
        row = dict(day=str(day.date()), bars_sha=bsha, processed_late=processed_late)
        for b, port in ports.items():
            cfg = B.BOOKS[b]
            report["events"][b] += port.step(day, bars, spy_close, processed_late=processed_late)
            scan = scan_fn(tr, spy, day, cfg, sectors, already_truncated=True)
            late = store.is_late(gen, nxt)
            meta = dict(kind="forward", book=b, comparison=exp["comparison"],
                        experiment=port.s["experiment"], run_id=run_id, generated_at=gen,
                        signal_date=str(day.date()), scheduled_for=nxt, late=late,
                        strategy_id=B.strategy_id(b), parameters=cfg.as_dict(),
                        code_fingerprint=fp, bars_sha=bsha,
                        source=PR._source_meta(frames, spy, day, now, usig))
            store.write_snapshot(day, scan, meta, P[b]["snapshots"])
            store.append_signals(scan, gen, nxt, late, run_id, P[b]["signals"],
                                 extra=dict(book=b, strategy_id=B.strategy_id(b),
                                            code_version=fp["combined"], kind="forward",
                                            experiment=port.s["experiment"]))
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
        summ = dict(updated=gen, book=b, comparison=exp["comparison"],
                    strategy_id=port.s["strategy_id"], code_fingerprint=fp["combined"],
                    revision=port.s["revision"], processed_through=port.s["processed_through"],
                    cash=port.s["cash"], open_positions=len(port.s["positions"]),
                    pending_orders=len(port.s["pending"]), forward=pm.forward_report(port.s),
                    snapshot_integrity_failures=store.verify_snapshots(P[b]["snapshots"]))
        (P[b]["state_dir"] / "summary.json").write_text(json.dumps(summ, indent=1, default=str))
    if new:
        store._atomic_write(ef, json.dumps(exp, indent=1))
    comp = write_report(root, exp)
    out = dict(report, comparison=comp)
    print(json.dumps(dict(data_date=report["data_date"], sessions=report["sessions"],
                          books={b: {k: r[k] for k in ("processed_through", "equity",
                                                       "open_positions", "pending_orders")}
                                 for b, r in comp["books"].items()}), default=str))
    return out


# =====================================================================
# comparison report (common period only, no winner)
# =====================================================================
def costs_paid(state: dict) -> float:
    fee = state["config"]["cost_bps"] / 1e4
    c = sum(t["shares"] * (t["entry"] + t["exit"]) * fee for t in state.get("ledger", []))
    c += sum(p["qty"] * p["entry"] * fee for p in state.get("positions", {}).values())
    return float(c)


def book_report(state: dict) -> dict:
    init = state["config"]["initial_cash"]
    eq = pd.DataFrame(state.get("equity", []))
    led = pd.DataFrame(state.get("ledger", []))
    perf = pm.performance(eq, led, init) if len(eq) else None
    inv = float(((eq["equity"] - eq["cash"]) / eq["equity"]).mean() * 100) if len(eq) else None
    outc = pd.Series([o["outcome"] for o in state.get("orders_log", [])]).value_counts().to_dict()
    return dict(book=state.get("book"), strategy_id=state.get("strategy_id"),
                experiment=state.get("experiment"), start=state.get("start"),
                processed_through=state.get("processed_through"),
                equity=float(eq["equity"].iloc[-1]) if len(eq) else init, cash=state["cash"],
                return_pct=perf["return_pct"] if perf else 0.0,
                max_drawdown_pct=perf["max_drawdown_pct"] if perf else 0.0,
                closed_trades=len(led), open_positions=len(state.get("positions", {})),
                pending_orders=len(state.get("pending", [])), costs_paid_usd=costs_paid(state),
                capital_invested_mean_pct=inv,
                sessions_with_position_pct=perf["exposure_pct"] if perf else None,
                order_outcomes={str(k): int(v) for k, v in outc.items()},
                positions=[dict(ticker=t, qty=p["qty"], entry=p["entry"], stop=p["stop"],
                                entry_date=p["entry_date"])
                           for t, p in state.get("positions", {}).items()],
                pending=[dict(ticker=o["ticker"], signal_date=o["signal_date"], rs=o["rs"],
                              rank=o.get("rank"), stop=o["stop"],
                              scheduled_for=o.get("scheduled_for"),
                              generated_at=o.get("generated_at"))
                         for o in state.get("pending", [])])


def write_report(root=ROOT, exp=None) -> dict:
    ef = B.experiment_file(root)
    exp = exp or json.loads(ef.read_text())
    states = {b: store.load_state(B.paths(b, root)["state_file"]) for b in B.BOOKS}
    reps = {b: book_report(s) for b, s in states.items()}
    per = {(r["start"], r["processed_through"]) for r in reps.values()}
    comp = dict(comparison=exp["comparison"], start_session=exp["start_session"],
                first_entry_session=exp["first_entry_session"],
                common_period=dict(start=next(iter(per))[0], through=next(iter(per))[1])
                if len(per) == 1 else dict(error=f"books out of step: {sorted(per)}"),
                books=reps,
                note="Forward paper comparison over the common period only. No winner is "
                     "declared on the first days.")
    base = ef.parent
    (base / "comparison.json").write_text(json.dumps(comp, indent=1, default=str))
    rows = ["| Book | Equity | Return | Max DD | Closed | Open | Pending | Costs paid | "
            "Capital invested (mean) |", "|---|---|---|---|---|---|---|---|---|"]
    for b, r in reps.items():
        inv = "—" if r["capital_invested_mean_pct"] is None else f"{r['capital_invested_mean_pct']:.1f} %"
        rows.append(f"| {b} | ${r['equity']:,.2f} | {r['return_pct']:+.2f} % | "
                    f"{r['max_drawdown_pct']:.2f} % | {r['closed_trades']} | {r['open_positions']} | "
                    f"{r['pending_orders']} | ${r['costs_paid_usd']:,.2f} | {inv} |")
    cp = comp["common_period"]
    md = [f"# Paper comparison {exp['comparison']}: Breakout RS-first vs Retest RS-first",
          "", f"Common period {cp.get('start')} → {cp.get('through')}; first possible entry "
          f"{exp['first_entry_session']}. Paper only, no broker. The original Retest paper book "
          "is a separate experiment.", "", *rows, "", comp["note"]]
    (base / "COMPARISON.md").write_text("\n".join(md) + "\n")
    return comp


# =====================================================================
# restore (all or nothing)
# =====================================================================
def restore(backup_dir, root=ROOT) -> str:
    bdir = Path(backup_dir)
    bexp = bdir / "experiment.json"
    if not bexp.exists():
        raise RuntimeError("backup has no experiment.json")
    be = json.loads(bexp.read_text())
    ef = B.experiment_file(root)
    ce = json.loads(ef.read_text()) if ef.exists() else None
    if ce is not None and ce["comparison"] != be["comparison"]:
        raise RuntimeError("restore refused: different comparison")
    why = []
    for b in B.BOOKS:
        bs = store.load_state(bdir / b / "state" / "portfolio.json")
        if bs is None:
            why.append(f"{b}: backup has no state")
            continue
        cs = store.load_state(B.paths(b, root)["state_file"])
        if cs is None:
            continue
        if (bs.get("processed_through") or "") <= (cs.get("processed_through") or ""):
            why.append(f"{b}: backup not newer")
        if int(bs.get("revision", 0)) <= int(cs.get("revision", 0)):
            why.append(f"{b}: backup revision not higher")
        if bs.get("equity", [])[:len(cs.get("equity", []))] != cs.get("equity", []):
            why.append(f"{b}: current history is not a prefix of the backup")
    if why:
        raise RuntimeError("restore refused: " + "; ".join(why))
    for b in B.BOOKS:
        for sub in ("state", "data"):
            src, dst = bdir / b / sub, B.paths(b, root)[f"{sub}_dir"]
            if src.exists():
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
    store._atomic_write(ef, bexp.read_text())
    return f"restored {be['comparison']}"


# =====================================================================
# verification (real data): both books vs the replay engine
# =====================================================================
def screener_vs_history(frames, spy, sig, market_ok, days, cfg):
    res = []
    raw = sig[sig["mode"] == cfg.mode].copy()
    raw["date"] = pd.to_datetime(raw["date"]).dt.normalize()
    el = V.eligible_signals(sig, market_ok, cfg)
    for day in days:
        day = pd.Timestamp(day).normalize()
        scan = B.scan_mode(truncate(frames, day), spy, day, cfg, already_truncated=True)
        h = raw[raw["date"] == day].set_index("ticker").sort_index()
        e_hist = set(el[el["date"] == day]["ticker"])
        if scan.empty:
            ok = h.empty and not e_hist
            res.append((day, ok, "no signals" if ok else f"history has {len(h)}"))
            continue
        sc = scan.set_index("ticker").sort_index()
        same = list(sc.index) == list(h.index)
        num = same and np.allclose(sc["level"], h["level"]) and \
            np.allclose(sc["stop_base"], h["stop_base"]) and \
            np.allclose(sc["rs"].fillna(-1), h["rs"].fillna(-1))
        e_scan = set(scan[scan["eligible"]]["ticker"])
        res.append((day, bool(num and e_scan == e_hist),
                    f"raw {len(sc)}/{len(h)} eligible {len(e_scan)}/{len(e_hist)}"))
    return res


def run_stepper_live(frames, spy, data, start, end, cfg):
    """Live path: scan_mode() on truncated data every session (as the daily runner)."""
    cal = V.calendar(data)
    idx = V.bar_index(data)
    port = PaperPortfolio(new_state(cfg, "verification"), cfg=cfg, kind="verification",
                          trace=True)
    scan = lambda d: B.scan_mode(truncate(frames, d), spy, d, cfg, already_truncated=True)  # noqa
    prev = [d for d in cal if d < start]
    if prev:
        port.queue_signals(prev[-1], scan(prev[-1]))
    for day in [d for d in cal if start <= d <= end]:
        port.step(day, V.bars_on(data, idx, day))
        port.queue_signals(day, scan(day))
    return port


def verify(out=ROOT / "research" / "results" / "compare", n_screen_days=25, live_days=30):
    t0 = time.time()
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    frames, spy, _ = PR.load_market()
    sig, data = bt.find_signals(frames, lookback=3, modes=list(B.BOOKS))
    res = dict(generated=datetime.now(timezone.utc).isoformat(timespec="seconds"),
               tickers=len(frames), code_fingerprint=B.code_fingerprint()["combined"],
               task10_fingerprint=store.code_fingerprint()["combined"], books={})
    cal = V.calendar(data)
    E = cal[-1]
    for b, cfg in B.BOOKS.items():
        mo = core.regime_mask(core.market_regime(spy), cfg.market_filter)
        s = sig[sig["mode"] == cfg.mode]
        first = pd.to_datetime(s["date"]).min().normalize()
        S = [d for d in cal if d > first][0]
        days = sorted(pd.to_datetime(s["date"]).dt.normalize().unique())
        pick = [days[int(k)] for k in np.linspace(0, len(days) - 1, n_screen_days)]
        A = screener_vs_history(frames, spy, sig, mo, pick, cfg)
        rB = V.compare(V.run_stepper(sig, data, mo, S, E, cfg),
                       V.reference_replay(sig, data, mo, S, E, cfg), cfg)
        S2 = cal[-live_days]
        rC = V.compare(run_stepper_live(frames, spy, data, S2, E, cfg),
                       V.reference_replay(sig, data, mo, S2, E, cfg), cfg)
        r = dict(raw_signals=len(s), window=[str(S.date()), str(E.date())],
                 screener=dict(days=len(A), ok=sum(ok for _, ok, _ in A),
                               detail=[(str(d.date()), ok, x) for d, ok, x in A]),
                 portfolio_full_period=rB, portfolio_live_path=rC)
        if b == "retest":                     # the control's scanner IS the Task 10 scanner
            same = []
            for d in pick:
                a = B.scan_mode(truncate(frames, d), spy, d, cfg, already_truncated=True)
                c = scan_day(truncate(frames, d), spy, d, cfg, already_truncated=True)
                same.append(bool(a.equals(c)))
            r["identical_to_task10_scan_day"] = dict(days=len(same), ok=sum(same))
        r["all_ok"] = bool(r["screener"]["ok"] == r["screener"]["days"] and rB["ok"] and rC["ok"]
                           and r.get("identical_to_task10_scan_day", {"ok": 1, "days": 1})["ok"]
                           == r.get("identical_to_task10_scan_day", {"ok": 1, "days": 1})["days"])
        res["books"][b] = r
    res["all_ok"] = all(r["all_ok"] for r in res["books"].values())
    res["runtime_sec"] = round(time.time() - t0)
    (out / "verify.json").write_text(json.dumps(res, indent=1, default=str))
    md = [f"# Paper comparison: real-data equivalence ({res['generated']})", "",
          f"Tickers {res['tickers']}; comparison fingerprint `{res['code_fingerprint']}`; Task 10 "
          f"fingerprint `{res['task10_fingerprint']}`.", "", f"**All checks passed: {res['all_ok']}**", ""]
    for b, r in res["books"].items():
        rB, rC = r["portfolio_full_period"], r["portfolio_live_path"]
        md += [f"## {b}", f"- raw signals {r['raw_signals']}, window {r['window'][0]} → {r['window'][1]}",
               f"- A) scanner vs history: {r['screener']['ok']}/{r['screener']['days']} days identical",
               f"- B) book vs replay, full period: fills {rB['fills_new']}/{rB['fills_ref']}, decisions "
               f"{rB['decisions_ok']} ({rB['decisions_new']}/{rB['decisions_ref']}), cash {rB['cash_ok']}, "
               f"holdings {rB['holdings_ok']}, equity {rB['equity_ok']} ({rB['equity_days']} days), open "
               f"{rB['open_ok']}, final {rB['final_new']:.2f} vs {rB['final_ref']:.2f}, violations "
               f"{len(rB['outcome_violations'])}",
               f"- C) live path (daily scan), last {live_days} sessions: fills {rC['fills_new']}/{rC['fills_ref']}, "
               f"decisions {rC['decisions_ok']}, cash {rC['cash_ok']}, holdings {rC['holdings_ok']}, equity "
               f"{rC['equity_ok']}, open {rC['open_ok']}"]
        if "identical_to_task10_scan_day" in r:
            i = r["identical_to_task10_scan_day"]
            md.append(f"- control scanner identical to Task 10 `scan_day`: {i['ok']}/{i['days']} days")
        md.append("")
    (out / "VERIFY.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    return res


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "daily":
        daily()
    elif cmd == "restore":
        print(restore(sys.argv[2]))
    elif cmd == "verify":
        sys.exit(0 if verify()["all_ok"] else 1)
    elif cmd == "report":
        write_report()
    else:
        print(__doc__)
        sys.exit(1)
