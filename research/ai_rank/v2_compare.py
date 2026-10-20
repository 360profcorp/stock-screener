"""Compare two v2 dataset builds (rank_rs fix): what changed and what must not.

    python -m research.ai_rank.v2_compare OLD.csv.gz NEW.csv.gz OUT.json
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

KEY = ["ticker", "signal_date", "strategy"]
MUST_EQUAL = ["split", "label_end", "trade_status", "exit_date", "entry_date", "net_r_base",
              "rs", "i"]


def main(old, new, out):
    a = pd.read_csv(old, low_memory=False).sort_values(KEY).reset_index(drop=True)
    b = pd.read_csv(new, low_memory=False).sort_values(KEY).reset_index(drop=True)
    res = dict(old_sha256=hashlib.sha256(Path(old).read_bytes()).hexdigest(),
               new_sha256=hashlib.sha256(Path(new).read_bytes()).hexdigest(),
               rows_old=len(a), rows_new=len(b))
    res["same_signals"] = bool(a[KEY].equals(b[KEY]))
    eq = {}
    for c in MUST_EQUAL:
        x, y = a[c], b[c]
        if pd.api.types.is_numeric_dtype(x):
            eq[c] = bool(np.allclose(x.astype(float), y.astype(float), equal_nan=True))
        else:
            eq[c] = bool(x.fillna("").astype(str).equals(y.fillna("").astype(str)))
    res["unchanged"] = eq
    other = [c for c in a.columns if c in b.columns and c not in KEY + MUST_EQUAL + ["rank_rs"]]
    res["other_columns_unchanged"] = {c: bool(np.allclose(a[c].astype(float), b[c].astype(float),
                                                          equal_nan=True))
                                      if pd.api.types.is_numeric_dtype(a[c]) else
                                      bool(a[c].fillna("").astype(str).equals(
                                          b[c].fillna("").astype(str))) for c in other}
    ch = ~np.isclose(a["rank_rs"], b["rank_rs"], equal_nan=True)
    res["rank_rs_changed"] = {s: int(ch[a["strategy"] == s].sum()) for s in sorted(a["strategy"].unique())}
    res["rank_rs_changed_total"] = int(ch.sum())
    r = a["strategy"] == "retest"
    res["retest_rank_rs_changed_by_split"] = a[r & ch]["split"].value_counts().to_dict()
    res["new_columns"] = [c for c in b.columns if c not in a.columns]
    res["ok"] = bool(res["same_signals"] and all(eq.values()) and
                     all(res["other_columns_unchanged"].values()))
    Path(out).write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=1))
    return 0 if res["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:4]))
