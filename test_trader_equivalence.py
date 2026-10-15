"""Differential test: the paper bot's execution rules are unchanged by the audit fixes.

    python -m unittest test_trader_equivalence -v

The baseline is trader.py at commit d95ccd4 (main before the audit). Both versions run the
same randomized paper scenarios with COMPLETE daily data and on-time morning runs; every
position, closed trade and order must be identical. (The fixes only change behaviour when
data is missing, a run is late, or a pre-close buy needs its entry-day stop — covered by
test_audit_cycle.)
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
BASELINE = os.environ.get("TRADER_BASELINE_REV", "d95ccd4")
import test_audit_cycle as TA  # noqa: E402  (sets the paper-mode environment first)
import core  # noqa: E402

trader = TA.trader


def load_baseline():
    src = subprocess.run(["git", "show", f"{BASELINE}:trader.py"], cwd=ROOT,
                         capture_output=True, text=True)
    if src.returncode != 0:
        raise unittest.SkipTest(f"baseline {BASELINE} not available: {src.stderr.strip()}")
    tmp = Path(tempfile.mkdtemp()) / "trader_baseline.py"
    tmp.write_text(src.stdout)
    spec = importlib.util.spec_from_file_location("trader_baseline", tmp)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(ROOT))
    spec.loader.exec_module(mod)
    return mod


def scenario(seed, n_t=5, n=70):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2026-10-19", periods=n, freq="C", holidays=trader.HOLIDAYS)
    frames = {}
    for j in range(n_t):
        c = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
        o = c * np.exp(rng.normal(0, 0.012, n))
        h = np.maximum(o, c) * (1 + rng.uniform(0, 0.02, n))
        lo = np.minimum(o, c) * (1 - rng.uniform(0, 0.02, n))
        frames[f"T{j}"] = pd.DataFrame({"Open": o, "High": h, "Low": lo, "Close": c,
                                        "Volume": 1e6}, index=days)
    sig = {}
    for k in range(n - 1):
        rows = []
        for t in rng.choice(list(frames), size=rng.integers(0, 4), replace=False):
            c = float(frames[t]["Close"].iloc[k])
            rows.append(dict(date=days[k].strftime("%Y-%m-%d"), ticker=t,
                             mode=str(rng.choice(["retest", "vcp"])), rs=int(rng.integers(85, 99)),
                             close=c, level=c * .98, stop=c * float(rng.uniform(.9, .97))))
        sig[k] = pd.DataFrame(rows, columns=["date", "ticker", "mode", "rs", "close", "level",
                                             "stop"])
    return days, frames, sig


KEYS_P = ("ticker", "mode", "entry_date", "entry", "stop", "qty", "how", "checked", "exiting")
KEYS_C = ("ticker", "entry_date", "exit_date", "exit", "reason", "pnl", "r", "qty")
KEYS_O = ("ticker", "date", "stop", "qty", "est")


def view(st):
    return (sorted(tuple(p.get(k) for k in KEYS_P) for p in st["positions"]),
            [tuple(c.get(k) for k in KEYS_C) for c in st["closed"]],
            sorted(tuple(o.get(k) for k in KEYS_O) for o in st["orders"]))


class TestRulesUnchanged(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old = load_baseline()

    def test_randomized_complete_data_identical(self):
        trades = 0
        for seed in range(int(os.environ.get("EQUIV_SEEDS", "60"))):
            days, frames, sig = scenario(seed)
            b = TA.FakeBroker(frames)
            states = {"new": TA.empty_state(), "old": TA.empty_state()}
            for k in range(len(days) - 1):
                day = days[k].strftime("%Y-%m-%d")
                at9 = datetime(days[k].year, days[k].month, days[k].day, 9, 0, tzinfo=core.NY)
                trader.run_execute(states["new"], b, day, [], at9)
                self.old.run_execute(states["old"], b, day, [])
                trader.reconcile_dry(states["new"], b, day, [])
                self.old.reconcile_dry(states["old"], b, day, [])
                for name, mod in (("new", trader), ("old", self.old)):
                    plan = mod.build_plan(sig[k], states[name], day)
                    if plan:
                        plan["created"] = f"{day} 20:38"
                    states[name]["plan"] = plan
                self.assertEqual(view(states["new"]), view(states["old"]), (seed, day))
            trades += len(states["new"]["closed"])
        self.assertGreater(trades, 100)            # the scenarios really exercise exits


if __name__ == "__main__":
    unittest.main()
