"""
Task 10 — Retest RS-first paper trading runner. NO broker, NO real orders.

  python paper_run.py daily    after the US close: processes every new session since the last
                               run in order (fills at the open, stops, 20-day exits, marks),
                               scans the closed session and records signals BEFORE the next
                               session. Sessions processed after the next session's open
                               (missed runs) are RECONSTRUCTED: their entry fills, exits and
                               marks are flagged processed_late, their signals are never
                               traded, and genuine-forward portfolio metrics stop there.
  python paper_run.py daily --new-experiment LABEL   archive the current forward experiment
                               and start a new one (required after a strategy change)
  python paper_run.py restore DIR   restore state from a backup artifact (only if strictly newer)
  python paper_run.py backfill YYYY-MM-DD   reconstructed history into paper/backfill/
                               (labelled backfill, never mixed with forward results)
  python paper_run.py verify   real-data equivalence report (scanner vs history,
                               paper portfolio vs the Task 6 replay engine).

State:  paper/state/portfolio.json (+ CSV exports, summary.json)
ML:     paper/data/signals.csv  (all raw Retest detections with as-of features + labels)
"""
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import backtest as bt
import core
from paper import metrics as pm
from paper import store, verify as V
from paper.config import DEFAULT
from paper.portfolio import PaperPortfolio, new_state
from paper.screener import scan_day, truncate

ROOT = Path(__file__).resolve().parent


def load_market(universe=None, prices=None):
    universe = core.get_sp500() if universe is None else universe
    tickers = tuple(universe["ticker"])
    prices = core.get_prices(tickers + ("SPY",), period="3y") if prices is None else prices
    frames = {}
    for t in tickers:
        df = core._frame_for(prices, t)
        if df is not None and len(df):
            df = df.copy()
            df.index = pd.to_datetime(df.index).normalize()
            frames[t] = df
    spy = core._frame_for(prices, "SPY")
    if spy is not None:
        spy = spy.copy()
        spy.index = pd.to_datetime(spy.index).normalize()
    sectors = dict(zip(universe["ticker"], universe.get("sector", pd.Series(dtype=str))))
    return frames, spy, sectors


def closed_data_date(frames: dict, now: datetime) -> pd.Timestamp:
    """Most common last bar date; today's bar is ignored until 16:15 New York (unfinished)."""
    last = pd.Series({t: df.index[-1] for t, df in frames.items()})
    d = last.value_counts().idxmax()
    ny = now.astimezone(core.NY)
    if d.date() == ny.date() and (ny.hour, ny.minute) < (16, 15):
        prev = sorted({x for df in frames.values() for x in df.index if x < d})
        d = prev[-1]
    return pd.Timestamp(d).normalize()


def _source_meta(frames, spy, day, now, universe_sig):
    last = pd.Series({t: df.index[-1] for t, df in frames.items()})
    try:
        import yfinance
        yf_ver = yfinance.__version__
    except Exception:
        yf_ver = None
    return dict(downloaded_at=now.isoformat(timespec="seconds"), source="yahoo/yfinance",
                yfinance=yf_ver, bar_date=str(pd.Timestamp(day).date()),
                tickers_total=len(frames),
                tickers_with_bar=int(sum(day in df.index for df in frames.values())),
                latest_bar_in_download=str(last.max().date()),
                spy_last_bar=str(spy.index[-1].date()) if spy is not None else None,
                universe_sha=universe_sig)


class StrategyChanged(RuntimeError):
    pass


def _slug(x: str) -> str:
    import re
    return re.sub(r"[^A-Za-z0-9._+-]+", "-", str(x)).strip("-")


def _archive(P, root, label):
    """Move a finished forward experiment out of the way (never deleted)."""
    import shutil
    dest = Path(root) / "paper" / "archive" / label
    if dest.exists():
        raise RuntimeError(f"archive {dest} already exists")
    dest.mkdir(parents=True)
    for k in ("state_dir", "data_dir"):
        if P[k].exists():
            shutil.move(str(P[k]), str(dest / P[k].name))
    return dest


def daily(universe=None, prices=None, now=None, root=ROOT, cfg=DEFAULT,
          new_experiment: str = None, scan_fn=None) -> dict:
    """
    FORWARD paper trading, run after the US close.

    Every session since the last run is processed in order. A session D counts as processed
    on time only if this run starts before the open of the session after D; otherwise its
    executions are RECONSTRUCTED (flag processed_late): entry fills of orders queued on
    time, stop / time exits and marks are computed from D's bars after the fact. Signals
    found in a reconstructed session are recorded but never traded (not_traded_late).
    Reconstructed executions are reported separately and end the genuine-forward
    portfolio-level record (metrics.forward_report).

    The strategy fingerprint (parameters + code of the strategy functions) is stored when
    the portfolio is created; if it changes, the run stops unless new_experiment="<label>"
    is given, which archives the old experiment and starts a new one.
    """
    now = now or datetime.now(timezone.utc)
    scan_fn = scan_fn or scan_day
    P = store.paths("forward", root)
    universe = core.get_sp500() if universe is None else universe
    frames, spy, sectors = load_market(universe, prices)
    data_date = closed_data_date(frames, now)
    sid, fp = store.strategy_id(cfg), store.code_fingerprint(root)
    state = store.load_state(P["state_file"])
    if state is not None:
        changed = []
        if state.get("kind") != "forward":
            changed.append(f"kind={state.get('kind')}")
        if state["config"] != cfg.as_dict():
            changed.append("parameters")
        old_fp = (state.get("code_fingerprint") or {}).get("combined")
        if old_fp != fp["combined"]:
            diff = sorted(k for k in fp if (state.get("code_fingerprint") or {}).get(k) != fp[k])
            changed.append(f"strategy code {old_fp} -> {fp['combined']} ({', '.join(diff)})")
        if changed:
            if not new_experiment:
                raise StrategyChanged(
                    "forward experiment " + str(state.get("experiment")) + " cannot continue: "
                    + "; ".join(changed) + ". Re-run with an explicit new experiment label "
                    "(paper_run.py daily --new-experiment <label>) to archive it and start anew.")
            _archive(P, root, _slug(f"{state.get('experiment')}_until_"
                                    f"{state['processed_through']}"))
            state = None
    if state is None:
        state = new_state(cfg, "forward", sid)
        state.update(code_fingerprint=fp,
                     experiment=_slug(new_experiment or f"forward-{sid}"), revision=0)
    port = PaperPortfolio(state, cfg, kind="forward")
    last = pd.Timestamp(state["processed_through"]) if state["processed_through"] else None
    sessions = sorted({d for d in spy.index if d <= data_date and (last is None or d > last)})
    if last is None:
        sessions = sessions[-1:]                          # a new portfolio starts today
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    gen = now.isoformat(timespec="seconds")
    usig = hashlib.sha256(",".join(sorted(map(str, universe["ticker"]))).encode()
                          ).hexdigest()[:12]
    report = dict(run_id=run_id, data_date=str(data_date.date()), sessions=[], events=[])
    for day in sessions:
        tr = truncate(frames, day)
        bars = {t: {"O": df["Open"].iloc[-1], "H": df["High"].iloc[-1],
                    "L": df["Low"].iloc[-1], "C": df["Close"].iloc[-1]}
                for t, df in tr.items() if df.index[-1] == day}
        spy_close = float(spy.loc[day, "Close"]) if day in spy.index else None
        nxt = store.next_session(day)
        processed_late = store.is_late(gen, nxt)          # run started after next open
        report["events"] += port.step(day, bars, spy_close, processed_late=processed_late)
        scan = scan_fn(tr, spy, day, cfg, sectors, already_truncated=True)
        late = store.is_late(gen, nxt)
        meta = dict(kind="forward", experiment=state["experiment"], run_id=run_id,
                    generated_at=gen, signal_date=str(day.date()), scheduled_for=nxt,
                    late=late, strategy_id=sid, strategy_version=store.STRATEGY_VERSION,
                    parameters=cfg.as_dict(), code_fingerprint=fp,
                    source=_source_meta(frames, spy, day, now, usig))
        store.write_snapshot(day, scan, meta, P["snapshots"])
        store.append_signals(scan, gen, nxt, late, run_id, P["signals"],
                             extra=dict(strategy_id=sid, code_version=fp["combined"],
                                        kind="forward", experiment=state["experiment"]))
        n = port.queue_signals(day, scan, gen, nxt, late)
        report["sessions"].append(dict(day=str(day.date()), raw=len(scan), queued=n,
                                       late=late, processed_late=processed_late))
    store.update_labels(truncate(frames, data_date), data_date, P["signals"], P["labels"],
                        port.s, gen)
    port.s["revision"] = int(port.s.get("revision", 0)) + 1
    port.s["last_run"] = run_id
    store.save_state(port.s, P["state_file"])
    store.export_tables(port.s, P["state_dir"])
    fwd = pm.forward_report(port.s)
    summary = dict(updated=gen, kind="forward", experiment=port.s["experiment"],
                   strategy_id=sid, code_fingerprint=fp["combined"],
                   revision=port.s["revision"], **report,
                   processed_through=port.s["processed_through"], cash=port.s["cash"],
                   open_positions=len(port.s["positions"]),
                   pending_orders=len(port.s["pending"]), forward=fwd,
                   snapshot_integrity_failures=store.verify_snapshots(P["snapshots"]))
    (P["state_dir"] / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    print(json.dumps({k: summary[k] for k in ("data_date", "sessions", "processed_through",
                                              "open_positions", "pending_orders", "revision")},
                     default=str))
    return summary


def restore(backup_dir, root=ROOT) -> str:
    """
    Restore forward state from a GitHub Actions backup artifact — ONLY if it strictly extends
    the current state (same experiment, later processed_through, higher revision, and the
    current equity history is an exact prefix of the backup's). Otherwise refuse loudly, so a
    stale backup can never overwrite valid later state.
    """
    import shutil
    P = store.paths("forward", root)
    b = store.load_state(Path(backup_dir) / "state" / "portfolio.json")
    if b is None:
        raise RuntimeError("backup has no state/portfolio.json")
    cur = store.load_state(P["state_file"])
    if cur is not None:
        why = []
        if b.get("experiment") != cur.get("experiment"):
            why.append("different experiment")
        if (b.get("processed_through") or "") <= (cur.get("processed_through") or ""):
            why.append(f"backup is not newer ({b.get('processed_through')} <= "
                       f"{cur.get('processed_through')})")
        if int(b.get("revision", 0)) <= int(cur.get("revision", 0)):
            why.append("backup revision is not higher")
        if b.get("equity", [])[:len(cur.get("equity", []))] != cur.get("equity", []):
            why.append("current history is not a prefix of the backup")
        if why:
            raise RuntimeError("restore refused: " + "; ".join(why))
    for sub in ("state", "data"):
        src, dst = Path(backup_dir) / sub, P[f"{sub}_dir"]
        if src.exists():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
    return f"restored revision {b.get('revision')} through {b.get('processed_through')}"


def backfill(start, end=None, root=ROOT, cfg=DEFAULT) -> dict:
    """RECONSTRUCTED history in paper/backfill — clearly labelled, never merged with forward."""
    frames, spy, _ = load_market()
    sig, data = bt.find_signals(frames, lookback=cfg.lookback, modes=[cfg.mode])
    market_ok = core.regime_mask(core.market_regime(spy), cfg.market_filter)
    cal = V.calendar(data)
    end = pd.Timestamp(end) if end else cal[-1]
    port = V.run_stepper(sig, data, market_ok, start, end, cfg, kind="backfill")
    port.s["strategy_id"] = store.strategy_id(cfg)
    port.s["note"] = "RECONSTRUCTED BACKFILL — not forward paper trading"
    P = store.paths("backfill", root)
    store.save_state(port.s, P["state_file"])
    store.export_tables(port.s, P["state_dir"])
    perf = pm.performance(port.equity_df(), port.ledger_df(), cfg.initial_cash)
    (P["state_dir"] / "summary.json").write_text(json.dumps(dict(
        kind="backfill", start=str(pd.Timestamp(start).date()), end=str(end.date()),
        generated=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        performance=perf), indent=1, default=str))
    return perf


def verify(out=ROOT / "research" / "results" / "task10", n_screen_days=25, live_days=30,
           cfg=DEFAULT):
    t0 = time.time()
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    frames, spy, _ = load_market()
    sig, data = bt.find_signals(frames, lookback=cfg.lookback, modes=[cfg.mode])
    market_ok = core.regime_mask(core.market_regime(spy), cfg.market_filter)
    cal = V.calendar(data)
    first_sig = pd.to_datetime(sig["date"]).min().normalize()
    S, E = [d for d in cal if d > first_sig][0], cal[-1]
    res = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "tickers": len(frames), "raw_signals": len(sig), "window": [str(S.date()),
                                                                     str(E.date())]}
    # A) scanner vs history
    sig_days = sorted(pd.to_datetime(sig["date"]).dt.normalize().unique())
    pick = [sig_days[int(k)] for k in np.linspace(0, len(sig_days) - 1, n_screen_days)]
    A = V.screener_vs_history(frames, spy, sig, market_ok, pick, cfg)
    res["screener"] = dict(days=len(A), ok=sum(ok for _, ok, _ in A),
                           detail=[(str(d.date()), ok, s) for d, ok, s in A])
    # B) full-period stepper vs replay (signals from history, validated by A)
    rB = V.compare(V.run_stepper(sig, data, market_ok, S, E, cfg),
                   V.reference_replay(sig, data, market_ok, S, E, cfg), cfg)
    res["portfolio_full_period"] = rB
    # C) live path (scanner every day) over the last sessions vs replay
    S2 = cal[-live_days]
    rC = V.compare(V.run_stepper(sig, data, market_ok, S2, E, cfg, scanner=(frames, spy)),
                   V.reference_replay(sig, data, market_ok, S2, E, cfg), cfg)
    res["portfolio_live_path"] = rC
    res["all_ok"] = bool(res["screener"]["ok"] == res["screener"]["days"] and rB["ok"] and rC["ok"])
    res["runtime_sec"] = round(time.time() - t0)
    (out / "verify.json").write_text(json.dumps(res, indent=1, default=str))
    md = [f"# Task 10 — real-data equivalence ({res['generated']})", "",
          f"Tickers {res['tickers']}, raw Retest signals {res['raw_signals']}, "
          f"window {res['window'][0]} → {res['window'][1]}.", "",
          f"**All checks passed: {res['all_ok']}**", "",
          f"A) Scanner vs history: {res['screener']['ok']}/{res['screener']['days']} days identical",
          f"B) Paper portfolio vs replay, full period: fills {rB['fills_new']}/{rB['fills_ref']}, "
          f"open positions equal {rB['open_ok']}, equity identical on {rB['equity_days']} days "
          f"({rB['equity_ok']}), final {rB['final_new']:.2f} vs {rB['final_ref']:.2f}",
          f"   decisions identical in order/outcome/shares: {rB['decisions_ok']} "
          f"({rB['decisions_new']}/{rB['decisions_ref']}; outcomes {rB['decision_outcomes']}), "
          f"cash every close {rB['cash_ok']}, holdings every close {rB['holdings_ok']}",
          f"   outcome mapping: {rB['outcome_categories']}, violations {len(rB['outcome_violations'])}",
          f"C) Live path (daily scan) vs replay, last {live_days} sessions: fills "
          f"{rC['fills_new']}/{rC['fills_ref']}, decisions {rC['decisions_ok']} "
          f"({rC['decisions_new']}/{rC['decisions_ref']}), cash {rC['cash_ok']}, holdings "
          f"{rC['holdings_ok']}, equity {rC['equity_ok']}, open positions {rC['open_ok']}",
          "", "| Day | OK | Detail |", "|---|---|---|"]
    md += [f"| {d} | {ok} | {s} |" for d, ok, s in res["screener"]["detail"]]
    (out / "VERIFY.md").write_text("\n".join(md) + "\n")
    print("\n".join(md[:10]))
    return res


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "daily":
        exp = sys.argv[sys.argv.index("--new-experiment") + 1] \
            if "--new-experiment" in sys.argv else None
        daily(new_experiment=exp)
    elif cmd == "restore":
        print(restore(sys.argv[2]))
    elif cmd == "backfill":
        backfill(sys.argv[2] if len(sys.argv) > 2 else "2025-01-02")
    elif cmd == "verify":
        r = verify()
        sys.exit(0 if r["all_ok"] else 1)
    else:
        print(__doc__)
        sys.exit(1)
