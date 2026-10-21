"""Parallel paper comparison: Breakout RS-first vs Retest RS-first (control). NO broker.

Two NEW independent forward books, started together on one session from one S&P 500 list and
one price download. The original Retest paper book (paper/state, paper/data, paper_run.py) is
a separate experiment and is never read or written here.

Both books use the unchanged Task 10 machinery: PaperPortfolio (fills at the next open, stop on
the entry bar at the stop and later at min(open, stop), time exit at the close of the 20th bar,
1 % risk, 5 positions, 3 entries a day, 20 % cap, 10 bps a side, RS-first ranking), the store
(write-once snapshots, append-only signal store, observable-only labels) and the same late /
reconstructed-session rules. Only the detector differs: backtest.RULES[mode].

Layout:  paper/compare/experiment.json          common start, books, universe/price hashes
         paper/compare/<book>/state, /data      one tree per book (same layout as paper/)
"""
import hashlib
import inspect
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

import backtest as bt
from paper import store
from paper.config import DEFAULT, PaperConfig
from paper.portfolio import PaperPortfolio, new_state
from paper.screener import _features, market_state, rank_rs_first, truncate

ROOT = Path(__file__).resolve().parents[1]
BOOKS = {"breakout": replace(DEFAULT, mode="breakout"),     # every other field = Task 10
         "retest": replace(DEFAULT, mode="retest")}         # control
VERSIONS = {"breakout": "breakout-rs-first/1.0", "retest": "retest-rs-first/1.0"}
TREE = "compare"


class StrategyChanged(RuntimeError):
    pass


class BooksOutOfStep(RuntimeError):
    """The two books do not share one start / one processed session: never run on."""


# ---------------------------------------------------------------- detector + screener
def scan_mode(frames: dict, spy: pd.DataFrame, day, cfg: PaperConfig = DEFAULT,
              sectors: dict = None, already_truncated=False) -> pd.DataFrame:
    """paper.screener.scan_day with the detector backtest.RULES[cfg.mode] (identical output to
    scan_day for mode='retest'; a test asserts it). Only bars <= day are used."""
    rule = bt.RULES[cfg.mode]
    day = pd.Timestamp(day).normalize()
    fr = frames if already_truncated else truncate(frames, day)
    rs = bt.rs_history(fr)
    rs_today = rs.loc[day] if day in rs.index else pd.Series(dtype=float)
    mkt = market_state(spy, day, cfg.market_filter)
    rows, above50, scanned = [], 0, 0
    for t, df in fr.items():
        if pd.Timestamp(df.index[-1]).normalize() != day:
            continue
        i = len(df) - 1
        if i < bt.WARMUP:
            continue
        x = bt.indicators(df)
        scanned += 1
        above50 += bool(x["C"][i] > x["ma50"][i])
        hit = rule(x, i, cfg.lookback)
        if hit is None:
            continue
        level, stop_base = float(hit[0]), float(hit[1])
        stop = stop_base * (1 - cfg.stop_buf_pct / 100)
        rows.append(dict(ticker=t, signal_date=day, close=float(x["C"][i]), level=level,
                         stop_base=stop_base, stop=stop,
                         risk_pct_at_close=(x["C"][i] - stop) / x["C"][i] * 100,
                         rs=rs_today.get(t, np.nan), sector=(sectors or {}).get(t, ""),
                         **_features(x, i, level, stop_base)))
    out = pd.DataFrame(rows)
    breadth = 100 * above50 / scanned if scanned else np.nan
    if out.empty:
        return out
    out["passes_rs"] = out["rs"].ge(cfg.min_rs).fillna(False) if cfg.min_rs else True
    out["passes_market"] = mkt["market_ok"]
    out["eligible"] = out["passes_rs"] & out["passes_market"]
    for k, v in mkt.items():
        out[k] = v
    out["breadth_above_ma50_pct"] = breadth
    out["universe_scanned"] = scanned
    out["raw_signals_today"] = len(out)
    elig = rank_rs_first(out[out["eligible"]])
    out["rank"] = np.nan
    out.loc[elig.index, "rank"] = np.arange(1, len(elig) + 1)
    return rank_rs_first(out).sort_values("rank", na_position="last",
                                          kind="stable").reset_index(drop=True)


# ---------------------------------------------------------------- identity / storage
def paths(book: str, root: Path = ROOT) -> dict:
    base = Path(root) / "paper" / TREE / book
    state, data = base / "state", base / "data"
    return dict(base=base, state_dir=state, state_file=state / "portfolio.json", data_dir=data,
                signals=data / "signals.csv", labels=data / "labels.csv",
                snapshots=data / "snapshots")


def experiment_file(root: Path = ROOT) -> Path:
    return Path(root) / "paper" / TREE / "experiment.json"


def strategy_id(book: str) -> str:
    return f"{VERSIONS[book]}+cfg.{store.config_hash(BOOKS[book])}"


def code_fingerprint() -> dict:
    """Task 10 strategy components + the breakout detector + this module (detector, books,
    parameters). Reporting code lives in compare_run.py and is not part of the strategy."""
    out = {k: v for k, v in store.code_fingerprint().items() if k != "combined"}
    for name, obj in {"backtest.breakout_at": bt.breakout_at,
                      "paper.books": inspect.getmodule(scan_mode)}.items():
        out[name] = hashlib.sha256(inspect.getsource(obj).encode()).hexdigest()[:12]
    out["combined"] = hashlib.sha256(json.dumps(out, sort_keys=True).encode()).hexdigest()[:12]
    return out


def bars_sha(bars: dict) -> str:
    """Hash of one session's OHLC for every ticker: proves both books saw the same prices."""
    body = json.dumps({t: [round(float(b[k]), 8) for k in "OHLC"] for t, b in sorted(bars.items())})
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def new_book_state(book: str, experiment: str, fp: dict) -> dict:
    s = new_state(BOOKS[book], "forward", strategy_id(book))
    s.update(code_fingerprint=fp, experiment=f"{experiment}-{book}", book=book,
             comparison=experiment, revision=0)
    return s


def check_book(state: dict, book: str, fp: dict, experiment: str):
    why = []
    if state.get("kind") != "forward" or state.get("book") != book:
        why.append(f"kind/book {state.get('kind')}/{state.get('book')}")
    if state.get("comparison") != experiment:
        why.append(f"comparison {state.get('comparison')} != {experiment}")
    if state["config"] != BOOKS[book].as_dict():
        why.append("parameters")
    old = (state.get("code_fingerprint") or {}).get("combined")
    if old != fp["combined"]:
        diff = sorted(k for k in fp if (state.get("code_fingerprint") or {}).get(k) != fp[k])
        why.append(f"strategy code {old} -> {fp['combined']} ({', '.join(diff)})")
    if why:
        raise StrategyChanged(f"book {book} cannot continue: " + "; ".join(why) +
                              ". The comparison is stopped; a new comparison needs an "
                              "explicit owner decision (no automatic reset).")
