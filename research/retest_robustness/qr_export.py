"""Runs INSIDE the QuantRocket zipline container (PLAN.md §11). Reads the ingested learning bundle
directly (unadjusted daily bars + split / dividend tables + symbol history) for the requested
symbols and writes one pickle to a path on the container. Prints only counts, never prices.

    python qr_export.py BUNDLE SYMBOLS_FILE OUT_PICKLE DIAG_JSON
"""
import glob
import gzip
import json
import os
import pickle
import sqlite3
import sys

import numpy as np
import pandas as pd


def find_bundle_dir(code):
    roots = [os.environ.get("ZIPLINE_ROOT", ""), os.path.expanduser("~/.zipline"), "/root/.zipline",
             "/var/lib/quantrocket/zipline", "/codeload/.zipline"]
    hits = []
    for r in roots:
        if r:
            hits += glob.glob(os.path.join(r, "data", code, "*"))
    hits += glob.glob(f"/**/data/{code}/*", recursive=True)[:20]
    hits = sorted({h for h in hits if os.path.isdir(h)})
    return hits[-1] if hits else None, hits


def norm(s):
    return "".join(ch for ch in str(s).upper() if ch.isalnum())


def main(code, sym_file, out, diag_path):
    diag = dict(code=code)
    want = {norm(x) for x in open(sym_file).read().split()}
    d, hits = find_bundle_dir(code)
    diag["bundle_dirs"] = hits
    if d is None:
        diag["error"] = "bundle directory not found"
        json.dump(diag, open(diag_path, "w"), indent=1)
        return 2
    diag["files"] = sorted(os.listdir(d))
    assets = next(iter(sorted(glob.glob(os.path.join(d, "assets-*.sqlite")))), None)
    con = sqlite3.connect(assets)
    maps = pd.read_sql("SELECT sid, symbol, start_date, end_date FROM equity_symbol_mappings", con)
    eq = pd.read_sql("SELECT sid, asset_name, exchange, start_date, end_date FROM equities", con)
    for c in ("start_date", "end_date"):
        maps[c] = pd.to_datetime(maps[c], unit="ns")
        eq[c] = pd.to_datetime(eq[c], unit="ns")
    diag.update(assets_db=os.path.basename(assets), equities=int(len(eq)), symbol_rows=int(len(maps)),
                distinct_symbols=int(maps["symbol"].nunique()))
    maps["key"] = maps["symbol"].map(norm)
    sel = sorted(set(maps.loc[maps["key"].isin(want), "sid"]))
    diag["selected_sids"] = len(sel)
    from zipline.data.bcolz_daily_bars import BcolzDailyBarReader
    try:
        reader = BcolzDailyBarReader(os.path.join(d, "daily_equities.bcolz"))
    except Exception as e:                               # newer versions may store elsewhere
        diag["bcolz_error"] = f"{type(e).__name__}: {e}"
        json.dump(diag, open(diag_path, "w"), indent=1)
        return 3
    sessions = pd.DatetimeIndex(reader.sessions)
    first, last = sessions[0], sessions[-1]
    cols = ["open", "high", "low", "close", "volume"]
    arr = {}
    ok_sids, parts = [], {c: [] for c in cols}
    for k in range(0, len(sel), 200):                    # chunks; a failing chunk is retried per sid
        ch = sel[k:k + 200]
        try:
            got = reader.load_raw_arrays(cols, first, last, ch)
            keep = ch
        except Exception:
            got, keep = None, []
            for s in ch:
                try:
                    g1 = reader.load_raw_arrays(cols, first, last, [s])
                    got = g1 if got is None else [np.hstack([x, y]) for x, y in zip(got, g1)]
                    keep.append(s)
                except Exception:
                    pass
        if got is not None:
            ok_sids += keep
            for c, a in zip(cols, got):
                parts[c].append(np.asarray(a, dtype=np.float32))
    for c in cols:
        arr[c] = np.hstack(parts[c]) if parts[c] else np.zeros((len(sessions), 0), np.float32)
    diag["unreadable_sids"] = len(sel) - len(ok_sids)
    adj = sqlite3.connect(os.path.join(d, "adjustments.sqlite"))
    splits = pd.read_sql("SELECT sid, effective_date, ratio FROM splits", adj)
    try:
        divs = pd.read_sql("SELECT sid, ex_date, amount FROM dividend_payouts", adj)
    except Exception:
        divs = pd.DataFrame(columns=["sid", "ex_date", "amount"])
    splits = splits[splits["sid"].isin(ok_sids)]
    divs = divs[divs["sid"].isin(ok_sids)]
    splits["effective_date"] = pd.to_datetime(splits["effective_date"], unit="s")
    if len(divs):
        divs["ex_date"] = pd.to_datetime(divs["ex_date"], unit="s")
    diag.update(sessions=int(len(sessions)), first_session=str(first.date()), last_session=str(last.date()),
                exported_sids=len(ok_sids), splits=int(len(splits)), dividends=int(len(divs)))
    blob = dict(sessions=sessions, sids=ok_sids, arrays=arr, splits=splits, divs=divs,
                maps=maps[maps["sid"].isin(ok_sids)], equities=eq[eq["sid"].isin(ok_sids)])
    with gzip.open(out, "wb") as f:
        pickle.dump(blob, f)
    json.dump(diag, open(diag_path, "w"), indent=1, default=str)
    print(json.dumps({k: diag[k] for k in ("sessions", "first_session", "last_session", "exported_sids",
                                            "splits", "dividends")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:5]))
