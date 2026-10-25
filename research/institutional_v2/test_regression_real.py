"""Regression tests on the REAL v2 mapping outputs (CORRECTION_V2.md R1, R2).

Reads research/results/institutional_v2/build/<run>/ (V2_BUILD=<dir>, else the newest).
Skipped when no build output exists yet.
"""
import os
import unittest
from pathlib import Path

import pandas as pd

from research.institutional_v2 import mapping as M

ROOT = Path(__file__).resolve().parents[2]
AUDIT1 = ROOT / "research/results/institutional/audit/40194202338/A2_conflict_unverified.csv"


def build_dir():
    if os.environ.get("V2_BUILD"):
        return Path(os.environ["V2_BUILD"])
    runs = sorted((ROOT / "research/results/institutional_v2/build").glob("*/security_sets.csv.gz"))
    return runs[-1].parent if runs else None


D = build_dir()

# expected issuer while the ticker was an index member (EDGAR names / CIKs from the first audit)
NAMED = {"TT": ("Trane Technologies", "1466258"), "HWM": ("Howmet Aerospace", "4281"),
         "TFC": ("Truist Financial", "92230"), "BBT": ("BB&T Corp", "92230"),
         "CPAY": ("Corpay", "1175454"), "DASH": ("DoorDash", "1792789"),
         "BAC": ("Bank of America", "70858"), "BNY": ("Bank of New York Mellon", "1390777"),
         "BK": ("Bank of New York Mellon", "1390777")}
NEVER = {"TT": {"45687V106", "G47791101"}, "HWM": {"013872106"}, "TFC": {"084680107"},
         "BBT": {"084680107"}, "CPAY": {"31620R303"}, "DASH": {"G3323L100"}, "BAC": {"46132E103"}}


@unittest.skipIf(D is None, "no v2 build output yet")
class RealMapping(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.S = pd.read_csv(D / "security_sets.csv.gz", dtype=str).fillna("")
        cls.S["member"] = cls.S["member_in_use_window"] == "True"
        cls.C = pd.read_csv(D / "cik_map.csv.gz", dtype=str).fillna("")
        cls.C["member"] = cls.C["member"] == "True"

    def ok(self, t, member=True):
        s = self.S[(self.S["ticker"] == t) & (self.S["status"] == "ok")]
        return s[s["member"]] if member else s

    def test_first_audit_conflicts_are_gone(self):
        a = pd.read_csv(AUDIT1, dtype=str)
        a = a[(a["status"] == "conflict") & (a["member_quarter"] == "True")]
        self.assertGreater(len(a), 100)
        ok = self.S[self.S["status"] == "ok"].set_index(["ticker", "period"])["cusips"].to_dict()
        bad = [(r.ticker, r.period, r.cusip) for r in a.itertuples()
               if r.cusip in ok.get((r.ticker, r.period[:10]), "").split(",")]
        self.assertEqual(bad, [])

    def test_named_cases_securities(self):
        for t, (nm, _) in NAMED.items():
            rows = self.ok(t)
            self.assertGreater(len(rows), 0, t)
            for r in rows.itertuples():
                for c in r.cusips.split(","):
                    self.assertNotIn(c, NEVER.get(t, set()), (t, r.period))
                listed = [x.split("=", 1)[1].split(" [")[0] for x in r.names.split("; ") if "[13(f) list" in x]
                for n in listed:
                    self.assertTrue(M.names_match(n, nm), (t, r.period, n, nm))

    def test_named_cases_issuers(self):
        for t, (_, cik) in NAMED.items():
            c = self.C[(self.C["ticker"] == t) & self.C["member"] & (self.C["status"] == "ok")]
            self.assertGreater(len(c), 0, t)
            if t == "BBT":
                c = c[c["quarter"] <= "2019Q4"]
            self.assertEqual(set(c["cik"].str.lstrip("0")), {cik}, t)

    def test_every_ok_set_is_one_issuer_with_evidence(self):
        ok = self.S[self.S["status"] == "ok"]
        self.assertTrue((ok["cusips"].map(lambda s: len({c[:6] for c in s.split(",")})) == 1).all())
        self.assertTrue((ok["ftd_evidence"].str.len() > 0).all())
        for r in ok.itertuples():
            ev = {e.split(" ")[0] for e in r.ftd_evidence.split("; ")}
            self.assertEqual(ev, set(r.cusips.split(",")))


if __name__ == "__main__":
    unittest.main()
