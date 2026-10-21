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

    def test_branch_never_modifies_fingerprinted_files(self):
        """This research branch must not touch the files the strategy fingerprint is built
        from (relative to where it left main). main itself may change unrelated functions in
        them (e.g. core.evaluate_journal, PR #10); the fingerprint test above still demands
        the live fingerprint."""
        if git("rev-parse", "--verify", "origin/main").returncode != 0:
            if os.environ.get("REQUIRE_MAIN") == "1":
                self.fail("origin/main not available")
            self.skipTest("origin/main not fetched")
        base = git("merge-base", "HEAD", "origin/main").stdout.strip()
        self.assertTrue(base)
        for f in FINGERPRINTED:
            self.assertEqual(git("diff", "--quiet", base, "HEAD", "--", f).returncode, 0, f)
            self.assertEqual(git("diff", "--quiet", "HEAD", "--", f).returncode, 0, f)


if __name__ == "__main__":
    unittest.main()
