"""Before / after recomputation of the signal journal on ONE frozen price set.

    python -m research.journal_gap_fix.recompute [--prices FROZEN.csv.gz]

Without --prices it downloads the journal's prices exactly like the app (core.get_prices with
start = first signal date - 7 days), freezes them (CSV + sha256) and uses the frozen copy.
'before' = core.evaluate_journal at BASELINE (main before the fix), 'after' = current code.
Asserts: same signals, same stop days. Writes research/results/journal_gap_fix/<run>/.
"""
import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import core  # noqa: E402

BASELINE = "2895b9b"
FOCUS = ["FAST", "BAX"]


def baseline_eval():
    src = subprocess.run(["git", "show", f"{BASELINE}:core.py"], cwd=ROOT, check=True,
                         capture_output=True, text=True).stdout
    p = Path(tempfile.mkdtemp()) / "core_baseline.py"
    p.write_text(src)
    spec = importlib.util.spec_from_file_location("core_baseline", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.evaluate_journal


def freeze(prices: pd.DataFrame) -> pd.DataFrame:
    long = prices.stack(level=0, future_stack=True).reset_index()
    long.columns = ["Date", "ticker"] + list(long.columns[2:])
    return long.dropna(subset=["Close"]).sort_values(["ticker", "Date"])


def unfreeze(long: pd.DataFrame) -> pd.DataFrame:
    long = long.copy()
    long["Date"] = pd.to_datetime(long["Date"])
    return pd.concat({t: g.set_index("Date").drop(columns="ticker")
                      for t, g in long.groupby("ticker")}, axis=1)


def summary(ev):
    rows = []
    for m, d in ev.groupby("mode"):
        rows.append(dict(mode=m, signals=len(d), stopped=int((d["status"] == "stopped").sum()),
                         gap_stops=int(d.get("gap_through_stop", pd.Series(False, index=d.index))
                                       .fillna(False).astype(bool).sum()),
                         avg_now_pct=d["ret_now"].mean() * 100,
                         n_5d=int(d["ret_5d"].notna().sum()), avg_5d_pct=d["ret_5d"].mean() * 100,
                         n_10d=int(d["ret_10d"].notna().sum()),
                         avg_10d_pct=d["ret_10d"].mean() * 100))
    return pd.DataFrame(rows)


def md(df, fmt="{:.2f}"):
    cols = list(df.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in df.itertuples(index=False):
        out.append("| " + " | ".join("" if isinstance(v, float) and np.isnan(v) else
                                     (fmt.format(v) if isinstance(v, float) else str(v))
                                     for v in r) + " |")
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--prices")
    ap.add_argument("--out", default=str(ROOT / "research/results/journal_gap_fix"))
    ap.add_argument("--run")
    a = ap.parse_args(argv)
    run = a.run or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%MZ")
    out = Path(a.out) / run
    out.mkdir(parents=True, exist_ok=False)
    # frozen file given: copy it verbatim (same bytes, same sha256)
    journal = pd.read_csv(ROOT / "journal/signals.csv")
    if a.prices:
        raw0 = Path(a.prices).read_bytes()
        long = pd.read_csv(a.prices)
    else:
        raw0 = None
        start = (pd.to_datetime(journal["date"]).min() - timedelta(days=7)).strftime("%Y-%m-%d")
        long = freeze(core.get_prices(tuple(sorted(journal["ticker"].unique())), start=start))
    raw = raw0 if raw0 is not None else long.to_csv(index=False).encode()
    (out / "prices_frozen.csv").write_bytes(raw)
    prices = unfreeze(pd.read_csv(out / "prices_frozen.csv"))
    before = baseline_eval()(journal, prices)
    after = core.evaluate_journal(journal, prices)
    key = ["date", "mode", "ticker"]
    assert len(before) == len(after) == len(journal), "signal count changed"
    sb = before.set_index(key)["status"]
    sa = after.set_index(key)["status"]
    assert sb.equals(sa), "statuses changed"
    db = before.set_index(key).get("stop_day")
    da = after.set_index(key).get("stop_day")
    same_stops = (db.fillna(-1) == da.fillna(-1)).all() if db is not None else True
    assert same_stops, "stop days changed"
    cols = ["ret_5d", "ret_10d", "ret_now"]
    m = before[key + cols + ["stop_day"]].merge(
        after[key + cols + ["exit_price", "gap_through_stop", "stop", "close"]],
        on=key, suffixes=("_before", "_after"))
    changed = m[np.any([~np.isclose(m[f"{c}_before"], m[f"{c}_after"], equal_nan=True)
                        for c in cols], axis=0)].copy()
    for c in cols:
        changed[f"{c}_before"] *= 100
        changed[f"{c}_after"] *= 100
    changed = changed[key + ["close", "stop", "stop_day", "exit_price", "gap_through_stop"] +
                      [f"{c}_{w}" for c in cols for w in ("before", "after")]]
    focus = m[m["ticker"].isin(FOCUS)].copy()
    for c in cols:
        focus[f"{c}_before"] *= 100
        focus[f"{c}_after"] *= 100
    focus = focus[key + ["close", "stop", "stop_day", "exit_price", "gap_through_stop"] +
                  [f"{c}_{w}" for c in cols for w in ("before", "after")]]
    sb_, sa_ = summary(before), summary(after)
    tab = sb_.merge(sa_, on="mode", suffixes=("_before", "_after"))
    info = dict(run=run, baseline=BASELINE, git=subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip(),
                prices_sha256=hashlib.sha256(raw).hexdigest(), tickers=int(long["ticker"].nunique()),
                last_bar=str(pd.to_datetime(long["Date"]).max().date()), signals=len(journal),
                stop_days_identical=bool(same_stops), changed_signals=len(changed))
    (out / "before_after.csv").write_text(tab.to_csv(index=False))
    (out / "changed_signals.csv").write_text(changed.to_csv(index=False))
    (out / "info.json").write_text(json.dumps(info, indent=2))
    rep = [f"# Journal gap-through-stop fix — before / after (`{run}`)", "",
           f"Frozen prices: {info['tickers']} tickers, last bar {info['last_bar']}, sha256 "
           f"`{info['prices_sha256'][:16]}…` (`prices_frozen.csv`). Signals {info['signals']}; "
           f"stop days identical: **{info['stop_days_identical']}**; changed signals: "
           f"**{info['changed_signals']}**.", "",
           "Before = `core.evaluate_journal` at " + BASELINE + " (exit always at the stop); "
           "after = exit at the open when it gapped below the stop.", "",
           "## Per strategy", "", md(tab), "## Changed signals (returns in %)", "",
           md(changed), "## FAST and BAX (returns in %)", "", md(focus), ""]
    (out / "REPORT.md").write_text("\n".join(rep))
    print("\n".join(rep))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
