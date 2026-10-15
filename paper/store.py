"""Storage for the paper portfolio: state JSON, CSV exports, and the ML signal store."""
import json
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "paper" / "state"
DATA_DIR = ROOT / "paper" / "data"
STATE_FILE = STATE_DIR / "portfolio.json"
SIGNALS_FILE = DATA_DIR / "signals.csv"
LABEL_HORIZONS = (1, 5, 10, 20)

# NYSE holidays (weekdays). Same list as trader.py — extend once a year.
HOLIDAYS = ["2026-11-26", "2026-12-25", "2027-01-01", "2027-01-18", "2027-02-15",
            "2027-03-26", "2027-05-31", "2027-06-18", "2027-07-05", "2027-09-06",
            "2027-11-25", "2027-12-24"]


def next_session(day) -> str:
    return str(np.busday_offset(pd.Timestamp(day).strftime("%Y-%m-%d"), 1, roll="forward",
                                holidays=HOLIDAYS))


# ---------------------------------------------------------------- state
def save_state(state: dict, path=STATE_FILE):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(state, f, indent=1, default=str)
    os.replace(tmp, path)                                   # atomic


def load_state(path=STATE_FILE):
    path = Path(path)
    return json.loads(path.read_text()) if path.exists() else None


def export_tables(state: dict, folder=STATE_DIR):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for name in ("ledger", "equity", "orders_log"):
        pd.DataFrame(state.get(name, [])).to_csv(folder / f"{name}.csv", index=False)
    pd.DataFrame(list(state.get("positions", {}).values())).to_csv(folder / "positions.csv",
                                                                    index=False)
    pd.DataFrame(state.get("pending", [])).to_csv(folder / "pending.csv", index=False)


# ---------------------------------------------------------------- ML signal store
def append_signals(scan: pd.DataFrame, generated_at: str, scheduled_for: str, late: bool,
                   run_id: str, path=SIGNALS_FILE) -> int:
    """Append every raw detection of a scan; (signal_date, ticker) is unique (first write wins,
    so the stored generated_at is the earliest — i.e. truly before execution)."""
    if scan is None or scan.empty:
        return 0
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    new = scan.copy()
    new["signal_date"] = pd.to_datetime(new["signal_date"]).dt.strftime("%Y-%m-%d")
    new["generated_at"] = generated_at
    new["scheduled_for"] = scheduled_for
    new["late"] = bool(late)
    new["run_id"] = run_id
    old = pd.read_csv(path) if path.exists() else None
    if old is not None and len(old):
        key = set(zip(old["signal_date"].astype(str), old["ticker"]))
        new = new[[(d, t) not in key for d, t in zip(new["signal_date"], new["ticker"])]]
        out = pd.concat([old, new], ignore_index=True)
    else:
        out = new
    out.to_csv(path, index=False)
    return len(new)


def update_labels(frames: dict, path=SIGNALS_FILE) -> int:
    """Fill forward-looking labels once they are known: fwd_ret_N (close->close N bars later),
    next_open_ret, mfe_20 / mae_20 (max high / min low over the next 20 bars vs close).
    Labels are only for research — they are never read by the screener or the portfolio."""
    path = Path(path)
    if not path.exists():
        return 0
    df = pd.read_csv(path)
    if df.empty:
        return 0
    cols = [f"fwd_ret_{n}" for n in LABEL_HORIZONS] + ["next_open_ret", "mfe_20", "mae_20"]
    for c in cols:
        if c not in df:
            df[c] = np.nan
    filled = 0
    for k, r in df.iterrows():
        if pd.notna(r["fwd_ret_20"]) and pd.notna(r["mfe_20"]):
            continue
        f = frames.get(r["ticker"])
        if f is None:
            continue
        idx = pd.to_datetime(f.index).normalize()
        pos = np.where(idx == pd.Timestamp(r["signal_date"]))[0]
        if not len(pos):
            continue
        i, C = pos[0], f["Close"].values
        for n in LABEL_HORIZONS:
            if i + n < len(C) and pd.isna(r[f"fwd_ret_{n}"]):
                df.at[k, f"fwd_ret_{n}"] = C[i + n] / C[i] - 1; filled += 1
        if i + 1 < len(C) and pd.isna(r["next_open_ret"]):
            df.at[k, "next_open_ret"] = f["Open"].values[i + 1] / C[i] - 1
        if i + 20 < len(C):
            df.at[k, "mfe_20"] = f["High"].values[i + 1:i + 21].max() / C[i] - 1
            df.at[k, "mae_20"] = f["Low"].values[i + 1:i + 21].min() / C[i] - 1
    df.to_csv(path, index=False)
    return filled
