"""Long Breakout / Retest crisis protection on 10 years (PREREG_CRISIS.md). Research only.

    python -m research.crisis.run --dataset DIR

DIR: dataset artifact of run 40152515701 (bars.pkl.gz, sources/sp500_pit_fja05680.csv).
Writes research/results/crisis/runs/<run_id>/ (write-once).
"""
import argparse
import gzip
import hashlib
import io
import json
import pickle
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import backtest as bt
import core
import portfolio_bt as pf
from research.sp1500 import engine as E
from research.sp1500 import run as RUN
from research.sp1500 import universe as U

ROOT = Path(__file__).resolve().parents[2]
UNIVERSE_CSV = ROOT / "research/results/sp1500/runs/2026-10-25T0156Z/universe.csv"
STRATS = ("breakout", "retest")
CFG = dict(initial_cash=10000., risk_fraction=.01, max_positions=5, max_new_per_day=3,
           max_position_fraction=.20)
PAUSE = 20
VARIANTS = {"C": dict(ma200=False, dd=None), "M": dict(ma200=True, dd=None),
            "D10": dict(ma200=False, dd=0.10), "D15": dict(ma200=False, dd=0.15),
            "MD10": dict(ma200=True, dd=0.10)}
WINDOWS = {"covid_crash": ("2020-02-19", "2020-03-23"),
           "covid_recovery": ("2020-03-24", "2020-12-31"),
           "bear_2022": ("2022-01-03", "2022-10-12"),
           "rebound_2022": ("2022-10-13", "2023-07-31")}
HOLDOUT = pd.Timestamp("2022-01-03")


def load(d):
    d = Path(d)
    bars = next(d.rglob("bars.pkl.gz"))
    pit = next(d.rglob("sp500_pit_fja05680.csv"))
    sha = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (bars, pit)}
    b = pickle.load(io.BytesIO(gzip.decompress(bars.read_bytes())))
    return b["frames"], b["spy"], pit.read_text(), sha


def build(frames, spy, pit_text):
    uni = pd.read_csv(UNIVERSE_CSV)
    cal = pd.DatetimeIndex(spy.index)
    end = cal[-1]
    cur500 = set(uni.loc[uni["group"] == "sp500", "ticker"])
    snaps = U.parse_pit500(pit_text)
    tl = U.pit_from_snapshots(snaps, cur500, end)
    ever = set().union(*[U.member_on(tl, d) for d in cal[::5]]) | cur500
    fr = {t: f for t, f in frames.items() if t in ever}
    meta = pd.DataFrame(dict(ticker=list(fr), group="sp500", sector=""))
    ref500 = sorted(cur500 & set(fr))
    sig, data = E.detect(fr, spy, meta, ref500, pit500=tl, strategies=list(STRATS))
    info = dict(tickers_ever_member=len(ever), with_prices=len(fr), detections=len(sig),
                pit_first=str(snaps["date"].iloc[0].date()), pit_last=str(snaps["date"].iloc[-1].date()))
    return sig, data, cal, info


def eligible(sig, ma200):
    s = sig[(sig["pit_member_sp500"] == True) & (sig["rs_pit500"] >= 85)  # noqa: E712
            & (sig["spy_above50"] == True)]                                 # noqa: E712
    if ma200:
        s = s[s["spy_above200"] == True]                                    # noqa: E712
    return s


def trades_for(sig, data, mode):
    s = sig[sig["strategy"] == mode]
    raw = pd.DataFrame(dict(ticker=s["ticker"], mode=mode, i=s["i"], date=s["signal_date"],
                            close=s["close"], level=s["level"], stop_base=s["stop_base"],
                            rs=s["rs_pit500"], vol_ratio=s["vol_ratio"]))
    t = bt.simulate(raw, data, mode, hold=20, stop_buf=3.0, min_rs=0, min_vol=0.0, max_risk=0.0,
                    market_ok=None, entry_at="open", one_per_ticker=False, include_open=True)
    t["date"] = pd.to_datetime(t["date"]).dt.normalize()
    return t.sort_values(["date", "rs", "ticker"], ascending=[True, False, True],
                         kind="stable").reset_index(drop=True)


def gated_replay(tr, data, start, end, dd, cost_bps):
    """Drawdown breaker by candidate removal + the unchanged replay (PREREG §4)."""
    sessions = sorted({pd.Timestamp(x).normalize() for x in
                       next(iter(data.values()))["dates"]} |
                      {pd.Timestamp(x).normalize() for v in data.values() for x in v["dates"]})
    sessions = [d for d in sessions if start <= d <= end]
    pauses = []
    while True:
        keep = tr
        for a, b in pauses:
            keep = keep[~((keep["date"] > a) & (keep["date"] <= b))]
        curve, ex, m = pf.replay(keep, data, start=start, end=end, open_at_end="mark",
                                 cost_bps=cost_bps, **CFG)
        if dd is None:
            return curve, ex, m, pauses
        eq = curve.set_index("date")["equity"]
        peak, nxt, until = CFG["initial_cash"], None, None
        for day, e in eq.items():
            if until is not None and day <= until:
                if day == until:
                    peak = e                       # reference peak restarts after a pause
                continue
            peak = max(peak, e)
            if e <= peak * (1 - dd):
                k = sessions.index(day) if day in sessions else None
                end_pause = sessions[min(k + PAUSE, len(sessions) - 1)] if k is not None else day
                if (day, end_pause) in pauses:
                    until = end_pause
                    continue
                nxt = (day, end_pause)
                break
        if nxt is None:
            return curve, ex, m, pauses
        pauses.append(nxt)
        pauses.sort()


def spy_ret(spy, a, b):
    c = spy["Close"]
    w = c[(c.index >= a) & (c.index <= b)]
    prev = c[c.index < a]
    base = prev.iloc[-1] if len(prev) else w.iloc[0]
    return float((w.iloc[-1] / base - 1) * 100) if len(w) else None


def metrics(curve, ex, m, spy, initial=10000.):
    eq = curve.set_index("date")["equity"]
    closed = ex[ex["status"] == "closed"] if len(ex) else ex
    w, l = closed.loc[closed["net_pnl"] > 0, "net_pnl"], closed.loc[closed["net_pnl"] <= 0, "net_pnl"]
    peak = np.maximum(initial, eq.cummax())
    ddser = eq / peak - 1
    trough = ddser.idxmin()
    after = eq[eq.index > trough]
    pk = peak.loc[trough]
    rec = after[after >= pk]
    yearly = eq.groupby(eq.index.year).last()
    prev = yearly.shift(1).fillna(initial)
    win = {}
    for name, (a, b) in WINDOWS.items():
        x = eq[(eq.index >= a) & (eq.index <= b)]
        if not len(x):
            continue
        p = eq[eq.index < a]
        base = p.iloc[-1] if len(p) else initial
        br, sr = float((x.iloc[-1] / base - 1) * 100), spy_ret(spy, a, b)
        win[name] = dict(book_pct=round(br, 2), spy_pct=round(sr, 2) if sr is not None else None,
                         capture=round(br / sr, 2) if sr else None)
    return dict(return_pct=m["return_pct"], cagr_pct=m["cagr_pct"], max_dd_pct=m["max_drawdown_pct"],
                profit_factor=float(w.sum() / -l.sum()) if l.sum() < 0 else None,
                trades=m["executed_trades"], expectancy_r=float(closed["net_r"].mean()) if len(closed) else None,
                yearly_return_pct={int(y): round(float((v / p - 1) * 100), 2)
                                   for y, v, p in zip(yearly.index, yearly, prev)},
                worst_dd_trough=str(trough.date()),
                sessions_trough_to_new_high=int(len(after[after.index <= rec.index[0]]))
                if len(rec) else "not recovered", windows=win)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--out", default=str(ROOT / "research/results/crisis/runs"))
    a = ap.parse_args(argv)
    root = Path(a.out)
    out = root / datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%MZ")
    man = {}
    frames, spy, pit_text, sha = load(a.dataset)
    sig, data, cal, info = build(frames, spy, pit_text)
    start = cal[min(260, len(cal) - 1)]
    windows = dict(full=(start, cal[-1]), development=(start, pd.Timestamp("2021-12-31")),
                   holdout=(cal[cal >= HOLDOUT][0], cal[-1]))
    res = dict(prereg="research/crisis/PREREG_CRISIS.md", dataset_sha256=sha, git=RUN._git_rev(),
               data=info, books={})
    W = lambda n, b: RUN.write_once(out / n, b, man, root)                  # noqa: E731
    cnt = {}
    for st in STRATS:
        for vid, v in VARIANTS.items():
            tr = trades_for(eligible(sig, v["ma200"]), data, st)
            cnt[f"{st}/{vid}"] = int(len(tr))
            for wname, (s0, s1) in windows.items():
                for bps in (10., 25.):
                    curve, ex, m, pauses = gated_replay(tr, data, s0, s1, v["dd"], bps)
                    key = f"{st}|{vid}|{wname}|{int(bps)}bps"
                    res["books"][key] = dict(metrics(curve, ex, m, spy), pauses=[
                        [str(x.date()), str(y.date())] for x, y in pauses])
                    if wname == "full" and bps == 10.:
                        W(f"equity_{st}_{vid}.csv", RUN.csv_bytes(curve[["date", "equity", "cash",
                                                                         "open_positions"]]))
    res["candidates"] = cnt
    dec = {}
    for vid in [v for v in VARIANTS if v != "C"]:
        ok = True
        for st in STRATS:
            for wname in ("development", "holdout"):
                for bps in (10, 25):
                    c = res["books"][f"{st}|C|{wname}|{bps}bps"]
                    x = res["books"][f"{st}|{vid}|{wname}|{bps}bps"]
                    good = (x["max_dd_pct"] - c["max_dd_pct"] >= 3.0 and
                            (x["cagr_pct"] or -99) >= (c["cagr_pct"] or -99) - 2.0)
                    ok &= good
        dec[vid] = bool(ok)
    res["decision"] = dec
    res["verdict"] = ("paper-test candidates: " + ", ".join(k for k, v in dec.items() if v)
                      if any(dec.values()) else "no variant meets the pre-registered rule: "
                      "current rules stay")
    W("results.json", json.dumps(res, indent=1, default=str))
    rows = [dict(zip(("strategy", "variant", "window", "costs"), k.split("|")),
                 **{c: v[c] for c in ("return_pct", "cagr_pct", "max_dd_pct", "profit_factor",
                                      "trades", "sessions_trough_to_new_high")})
            for k, v in res["books"].items()]
    W("books.csv", RUN.csv_bytes(pd.DataFrame(rows)))
    RUN.write_once(out / "manifest.json", json.dumps(dict(files=man, dataset=sha), indent=1), {}, root)
    print(json.dumps(dict(verdict=res["verdict"], decision=dec), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
