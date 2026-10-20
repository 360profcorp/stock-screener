"""Guard: AI ranking research must not change the live paper strategy (PREREG v2.1 §0)."""
import json
import os
import subprocess
import unittest
from pathlib import Path

from paper import store

ROOT = Path(__file__).resolve().parents[2]
FROZEN_FINGERPRINT = "17454c61f631"
FINGERPRINTED = ["backtest.py", "core.py", "paper/config.py", "paper/nyse.py",
                 "paper/portfolio.py", "paper/screener.py", "paper/store.py"]


def git(*a):
    return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True)


class TestGuard(unittest.TestCase):
    def test_strategy_fingerprint_unchanged(self):
        self.assertEqual(store.code_fingerprint()["combined"], FROZEN_FINGERPRINT)

    def test_matches_live_state_on_main(self):
        r = git("show", "origin/main:paper/state/portfolio.json")
        if r.returncode != 0:
            if os.environ.get("REQUIRE_MAIN") == "1":
                self.fail("origin/main not available")
            self.skipTest("origin/main not fetched")
        live = json.loads(r.stdout)["code_fingerprint"]["combined"]
        self.assertEqual(live, FROZEN_FINGERPRINT)
        self.assertEqual(store.code_fingerprint()["combined"], live)

    def test_fingerprinted_files_identical_to_main(self):
        if git("rev-parse", "--verify", "origin/main").returncode != 0:
            if os.environ.get("REQUIRE_MAIN") == "1":
                self.fail("origin/main not available")
            self.skipTest("origin/main not fetched")
        for f in FINGERPRINTED:
            self.assertEqual(git("diff", "--quiet", "origin/main", "--", f).returncode, 0, f)


if __name__ == "__main__":
    unittest.main()
