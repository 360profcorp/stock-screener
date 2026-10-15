"""Storage for the paper portfolio (Task 10).

Layout (forward and backfill are separate trees — acceptance 1):
  paper/state/            forward portfolio.json + CSV exports + summary.json
  paper/data/             forward ML store:
      signals.csv           append-only, one immutable row per (signal_date, ticker):
                            every raw detection incl. rejected ones, decision-time features
      labels.csv            outcomes, filled only once observable (decision, trade result,
                            forward returns); each label carries its observation date
      snapshots/<day>.json  write-once decision-time snapshot of a scan (acceptance 2)
      snapshots/MANIFEST.csv  sha256 of every snapshot (tamper check)
  paper/backfill/state, paper/backfill/data   reconstructed history — never forward
"""
import hashlib
import json
import os
import tempfile
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
NY = ZoneInfo("America/New_York")
STRATEGY_VERSION = "retest-rs-first/1.0"
FINGERPRINT_FILES = ["backtest.py", "core.py", "portfolio_bt.py", "paper/config.py",
                     "paper/screener.py", "paper/portfolio.py"]
LABEL_HORIZONS = (1, 5, 10, 20)

# NYSE holidays (weekdays). Same list as trader.py — extend once a year.
HOLIDAYS = ["2026-11-26", "2026-12-25", "2027-01-01", "2027-01-18", "2027-02-15",
            "2027-03-26", "2027-05-31", "2027-06-18", "2027-07-05", "2027-09-06",
            "2027-11-25", "2027-12-24"]


class ImmutableError(RuntimeError):
    pass


def paths(kind: str = "forward", root: Path = ROOT) -> dict:
    base = Path(root) / "paper" / ("backfill" if kind == "backfill" else "")
    state, data = base / "state", base / "data"
    return dict(state_dir=state, state_file=state / "portfolio.json", data_dir=data,
                signals=data / "signals.csv", labels=data / "labels.csv",
                snapshots=data / "snapshots")


_P = paths("forward")
STATE_DIR, STATE_FILE = _P["state_dir"], _P["state_file"]
DATA_DIR, SIGNALS_FILE, LABELS_FILE = _P["data_dir"], _P["signals"], _P["labels"]


# ---------------------------------------------------------------- calendar / timing
def next_session(day) -> str:
    return str(np.busday_offset(pd.Timestamp(day).strftime("%Y-%m-%d"), 1, roll="forward",
                                holidays=HOLIDAYS))


def session_open_utc(day) -> datetime:
    d = pd.Timestamp(day).date()
    return datetime.combine(d, time(9, 30), tzinfo=NY).astimezone(timezone.utc)


def is_late(generated_at, scheduled_for) -> bool:
    """A signal is late if it was recorded at/after the open of its execution session."""
    g = pd.Timestamp(generated_at)
    g = g.tz_localize("UTC") if g.tzinfo is None else g.tz_convert("UTC")
    return g.to_pydatetime() >= session_open_utc(scheduled_for)


# ---------------------------------------------------------------- versioning
def config_hash(cfg) -> str:
    return hashlib.sha256(json.dumps(cfg.as_dict(), sort_keys=True, default=str)
                          .encode()).hexdigest()[:12]


def code_fingerprint(root: Path = ROOT) -> dict:
    out = {}
    for f in FINGERPRINT_FILES:
        p = Path(root) / f
        out[f] = hashlib.sha256(p.read_bytes()).hexdigest()[:12] if p.exists() else None
    out["combined"] = hashlib.sha256(json.dumps(out, sort_keys=True).encode()).hexdigest()[:12]
    return out


def strategy_id(cfg) -> str:
    return f"{STRATEGY_VERSION}+cfg.{config_hash(cfg)}"


# ---------------------------------------------------------------- state
def _atomic_write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.replace(tmp, path)


def save_state(state: dict, path=STATE_FILE):
    _atomic_write(Path(path), json.dumps(state, indent=1, default=str))


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


# ---------------------------------------------------------------- immutable snapshots
def _jsonable(df: pd.DataFrame) -> list:
    d = df.copy()
    for c in d.columns:
        if pd.api.types.is_datetime64_any_dtype(d[c]):
            d[c] = d[c].dt.strftime("%Y-%m-%d")
    return json.loads(d.to_json(orient="records", double_precision=12))


def write_snapshot(day, scan: pd.DataFrame, meta: dict, folder) -> Path:
    """
    Write-once decision-time snapshot of one scan. Re-writing identical content is a no-op;
    different content for an existing day raises ImmutableError. The sha256 goes to MANIFEST.csv.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{pd.Timestamp(day).strftime('%Y-%m-%d')}.json"
    body = json.dumps({"meta": meta, "signals": _jsonable(scan) if scan is not None else []},
                      indent=1, sort_keys=True, default=str)
    if path.exists():
        if path.read_text() == body:
            return path
        raise ImmutableError(f"snapshot {path.name} already exists with different content")
    _atomic_write(path, body)
    os.chmod(path, 0o444)                                    # read-only on disk
    man = folder / "MANIFEST.csv"
    row = pd.DataFrame([dict(file=path.name, sha256=hashlib.sha256(body.encode()).hexdigest(),
                             written_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))])
    row.to_csv(man, mode="a", header=not man.exists(), index=False)
    return path


def verify_snapshots(folder) -> list:
    """Files whose content no longer matches the manifest (or are missing from it)."""
    folder = Path(folder)
    man = folder / "MANIFEST.csv"
    if not man.exists():
        return []
    m = pd.read_csv(man).drop_duplicates("file", keep="first").set_index("file")["sha256"]
    bad = []
    for f in sorted(folder.glob("*.json")):
        h = hashlib.sha256(f.read_bytes()).hexdigest()
        if m.get(f.name) != h:
            bad.append(f.name)
    return bad


# ---------------------------------------------------------------- signal store (append-only)
def append_signals(scan: pd.DataFrame, generated_at: str, scheduled_for: str, late: bool,
                   run_id: str, path=SIGNALS_FILE, extra: dict = None) -> int:
    """Append every raw detection; (signal_date, ticker) is unique and first write wins, so a
    row is never modified after it was recorded (the stored generated_at is the earliest)."""
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
    for k, v in (extra or {}).items():
        new[k] = v
    if path.exists():
        old = pd.read_csv(path, usecols=["signal_date", "ticker"])
        key = set(zip(old["signal_date"].astype(str), old["ticker"]))
        new = new[[(d, t) not in key for d, t in zip(new["signal_date"], new["ticker"])]]
        if new.empty:
            return 0
        cols = pd.read_csv(path, nrows=0).columns.tolist()
        new = new.reindex(columns=cols + [c for c in new.columns if c not in cols])
        if len(new.columns) > len(cols):                    # new columns: rewrite header once
            pd.concat([pd.read_csv(path), new], ignore_index=True).to_csv(path, index=False)
        else:
            new.to_csv(path, mode="a", header=False, index=False)
    else:
        new.to_csv(path, index=False)
    return len(new)


# ---------------------------------------------------------------- labels (observable only)
LABEL_COLS = ([f"fwd_ret_{n}" for n in LABEL_HORIZONS] + ["next_open_ret", "mfe_20", "mae_20",
              "decision", "decision_session", "trade_exit_date", "trade_net_r"])


def update_labels(frames: dict, asof, signals_path=SIGNALS_FILE, labels_path=LABELS_FILE,
                  state: dict = None, observed_at: str = None) -> int:
    """
    Fill outcome labels for stored signals ONLY when observable as of `asof` (the last
    processed session): a label needing bar i+n is written only if that bar's date <= asof.
    A written label is never changed. Each label gets <name>_observed (the bar date it
    became known). Portfolio decisions/trade results are taken from `state` once they exist.
    Labels are research data only — the screener and the portfolio never read them.
    """
    signals_path, labels_path = Path(signals_path), Path(labels_path)
    if not signals_path.exists():
        return 0
    asof = pd.Timestamp(asof).normalize()
    sig = pd.read_csv(signals_path, usecols=["signal_date", "ticker"])
    lab = pd.read_csv(labels_path) if labels_path.exists() else pd.DataFrame(
        columns=["signal_date", "ticker"])
    lab = sig.merge(lab, on=["signal_date", "ticker"], how="left")
    for c in LABEL_COLS:
        for col in (c, f"{c}_observed"):
            if col not in lab:
                lab[col] = np.nan
    text_cols = ["decision", "decision_session", "trade_exit_date"] + \
        [f"{c}_observed" for c in LABEL_COLS]
    lab = lab.astype({c: object for c in text_cols})
    decisions, trades = {}, {}
    if state:
        for o in state.get("orders_log", []):
            decisions.setdefault((o["signal_date"], o["ticker"]), (o["outcome"], o["session"]))
        for t in state.get("ledger", []):
            trades[(t["signal_date"], t["ticker"])] = t
    obs = observed_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    filled = 0

    def put(k, col, val, when):
        nonlocal filled
        if pd.isna(lab.at[k, col]):
            lab.at[k, col] = val
            lab.at[k, f"{col}_observed"] = when
            filled += 1

    for k, r in lab.iterrows():
        key = (str(r["signal_date"]), r["ticker"])
        if key in decisions and pd.Timestamp(decisions[key][1]) <= asof:
            put(k, "decision", decisions[key][0], decisions[key][1])
            put(k, "decision_session", decisions[key][1], decisions[key][1])
        if key in trades and pd.Timestamp(trades[key]["exit_date"]) <= asof:
            put(k, "trade_exit_date", trades[key]["exit_date"], trades[key]["exit_date"])
            put(k, "trade_net_r", trades[key]["net_r"], trades[key]["exit_date"])
        f = frames.get(r["ticker"])
        if f is None:
            continue
        idx = pd.to_datetime(f.index).normalize()
        f = f[idx <= asof]                                   # nothing after asof is visible
        idx = idx[idx <= asof]
        pos = np.where(idx == pd.Timestamp(r["signal_date"]))[0]
        if not len(pos):
            continue
        i, C = pos[0], f["Close"].values
        day = lambda j: str(idx[j].date())
        for n in LABEL_HORIZONS:
            if i + n < len(C):
                put(k, f"fwd_ret_{n}", C[i + n] / C[i] - 1, day(i + n))
        if i + 1 < len(C):
            put(k, "next_open_ret", f["Open"].values[i + 1] / C[i] - 1, day(i + 1))
        if i + 20 < len(C):
            put(k, "mfe_20", f["High"].values[i + 1:i + 21].max() / C[i] - 1, day(i + 20))
            put(k, "mae_20", f["Low"].values[i + 1:i + 21].min() / C[i] - 1, day(i + 20))
    lab["labels_updated_at"] = obs
    labels_path.parent.mkdir(parents=True, exist_ok=True)
    lab.to_csv(labels_path, index=False)
    return filled
