"""
Task 10 — Retest RS-first paper trading runner. NO broker, NO real orders.

  python paper_run.py daily    after the US close: processes every new session since the last
                               run (fills at the open, stops, 20-day exits, mark-to-market),
                               scans the closed session, records signals with timestamps
                               BEFORE the next session, updates ML labels, saves state.
  python paper_run.py verify   real-data equivalence report (scanner vs history,
                               paper portfolio vs the Task 6 replay engine).

State:  paper/state/portfolio.json (+ CSV exports, summary.json)
ML:     paper/data/signals.csv  (all raw Retest detections with as-of features + labels)
"""
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


def daily(universe=None, prices=None, now=None, state_path=store.STATE_FILE,
          signals_path=store.SIGNALS_FILE, out_dir=store.STATE_DIR, cfg=DEFAULT) -> dict:
    now = now or datetime.now(timezone.utc)
    frames, spy, sectors = load_market(universe, prices)
    data_date = closed_data_date(frames, now)
    state = store.load_state(state_path) or new_state(cfg)
    if state["config"] != cfg.as_dict():
        raise RuntimeError("paper/state config differs from paper/config.py — a strategy change "
                           "needs a new portfolio (move the old state away first)")
    port = PaperPortfolio(state, cfg)
    last = pd.Timestamp(state["processed_through"]) if state["processed_through"] else None
    sessions = sorted({d for d in spy.index if d <= data_date and (last is None or d > last)})
    if last is None:
        sessions = sessions[-1:]                          # a new portfolio starts today
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    report = dict(run_id=run_id, data_date=str(data_date.date()), sessions=[], events=[])
    for day in sessions:
        tr = truncate(frames, day)
        bars = {t: {"O": df["Open"].iloc[-1], "H": df["High"].iloc[-1],
                    "L": df["Low"].iloc[-1], "C": df["Close"].iloc[-1]}
                for t, df in tr.items() if df.index[-1] == day}
        spy_close = float(spy.loc[day, "Close"]) if day in spy.index else None
        report["events"] += port.step(day, bars, spy_close)
        scan = scan_day(tr, spy, day, cfg, sectors, already_truncated=True)
        gen = datetime.now(timezone.utc).isoformat(timespec="seconds")
        nxt = store.next_session(day)
        late = day < data_date                            # caught up after the fact
        store.append_signals(scan, gen, nxt, late, run_id, signals_path)
        n = port.queue_signals(day, scan, gen, nxt, late)
        report["sessions"].append(dict(day=str(day.date()), raw=len(scan), queued=n,
                                       late=late))
    store.update_labels(frames, signals_path)
    store.save_state(port.s, state_path)
    store.export_tables(port.s, out_dir)
    perf = pm.performance(port.equity_df(), port.ledger_df(), cfg.initial_cash)
    summary = dict(updated=now.isoformat(timespec="seconds"), **report,
                   processed_through=port.s["processed_through"], cash=port.s["cash"],
                   open_positions=len(port.s["positions"]),
                   pending_orders=len(port.s["pending"]), performance=perf)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    (Path(out_dir) / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    print(json.dumps({k: summary[k] for k in ("data_date", "sessions", "processed_through",
                                              "open_positions", "pending_orders")},
                     default=str))
    return summary


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
                   V.reference_replay(sig, data, market_ok, S, E, cfg))
    res["portfolio_full_period"] = rB
    # C) live path (scanner every day) over the last sessions vs replay
    S2 = cal[-live_days]
    rC = V.compare(V.run_stepper(sig, data, market_ok, S2, E, cfg, scanner=(frames, spy)),
                   V.reference_replay(sig, data, market_ok, S2, E, cfg))
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
          f"C) Live path (daily scan) vs replay, last {live_days} sessions: fills "
          f"{rC['fills_new']}/{rC['fills_ref']}, equity identical {rC['equity_ok']}, "
          f"open positions equal {rC['open_ok']}", "", "| Day | OK | Detail |", "|---|---|---|"]
    md += [f"| {d} | {ok} | {s} |" for d, ok, s in res["screener"]["detail"]]
    (out / "VERIFY.md").write_text("\n".join(md) + "\n")
    print("\n".join(md[:9]))
    return res


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "daily":
        daily()
    elif cmd == "verify":
        r = verify()
        sys.exit(0 if r["all_ok"] else 1)
    else:
        print(__doc__)
        sys.exit(1)
