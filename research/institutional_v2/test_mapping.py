"""Regression cases of the first audit on synthetic SEC-shaped records (no network).

Each case mirrors a confirmed PR #20 error: TT, HWM, BBT/TFC, CPAY, DASH, BAC, BNY/BK,
and the safe cases (FB -> META rename, GE CUSIP change with the same issuer prefix).
"""
import unittest

import numpy as np
import pandas as pd

from research.institutional_v2 import mapping as M

T = pd.Timestamp


def ftd(rows):
    """rows: (sym, cusip, first day, last day) -> twice-monthly records in between."""
    out = []
    for sym, c, a, b in rows:
        for d in pd.date_range(a, b, freq="SMS"):
            out.append(dict(date=d, cusip=c, sym=sym, desc="", file=f"cnsfails{d:%Y%m}a.zip"))
    return pd.DataFrame(out)


R = ftd([
    # TT / IR: Ingersoll-Rand plc (IR) became Trane (TT, new CUSIP); IR then = Gardner Denver
    ("IR", "G47791101", "2016-01-01", "2020-02-28"), ("TT", "G8994E103", "2020-03-02", "2026-09-30"),
    ("GDI", "45687V106", "2017-05-15", "2020-02-28"), ("IR", "45687V106", "2020-03-02", "2026-09-30"),
    # HWM / ARNC / AA
    ("ARNC", "03965L100", "2016-11-01", "2020-03-31"), ("HWM", "443201108", "2020-04-01", "2026-09-30"),
    ("ARNC", "03966V107", "2020-04-01", "2023-08-15"), ("AA", "013872106", "2016-11-01", "2026-09-30"),
    # BBT -> TFC; the symbol BBT re-used in 2025 by Berkshire Hills (was BHLB)
    ("BBT", "054937107", "2016-01-01", "2019-12-06"), ("TFC", "89832Q109", "2019-12-09", "2026-09-30"),
    ("BHLB", "084680107", "2016-01-01", "2025-08-29"), ("BBT", "084680107", "2025-09-02", "2026-09-30"),
    # FLT -> CPAY (new CUSIP); FNF is another company
    ("FLT", "339041105", "2016-01-01", "2024-03-22"), ("CPAY", "219948106", "2024-03-25", "2026-09-30"),
    ("FNF", "31620R303", "2016-01-01", "2026-09-30"),
    ("DASH", "25809K105", "2020-12-09", "2026-09-30"), ("FN", "G3323L100", "2016-01-01", "2026-09-30"),
    ("BAC", "060505104", "2016-01-01", "2026-09-30"), ("VKI", "46132E103", "2016-01-01", "2026-09-30"),
    # BNY: a BlackRock municipal fund until 2026-02; BK renamed BNY afterwards (same CUSIP)
    ("BNY", "09249E101", "2016-01-01", "2026-02-27"), ("BK", "064058100", "2016-01-01", "2026-03-06"),
    ("BNY", "064058100", "2026-03-09", "2026-09-30"),
    # safe: FB -> META (same CUSIP); GE CUSIP change with the same issuer prefix
    ("FB", "30303M102", "2016-01-01", "2022-06-08"), ("META", "30303M102", "2022-06-09", "2026-09-30"),
    ("GE", "369604103", "2016-01-01", "2021-07-30"), ("GE", "369604301", "2021-08-02", "2026-09-30"),
])
recs = M.SymbolRecords(R)
names = M.ListNames(pd.DataFrame([dict(list="2020q2", cusip="G8994E103", name="TRANE TECHNOLOGIES PLC"),
                                  dict(list="2020q2", cusip="45687V106", name="INGERSOLL RAND INC"),
                                  dict(list="2020q1", cusip="G47791101", name="INGERSOLL-RAND PLC"),
                                  dict(list="2024q2", cusip="31620R303", name="FIDELITY NATIONAL FINANCIAL"),
                                  dict(list="2024q2", cusip="219948106", name="CORPAY INC"),
                                  dict(list="2022q2", cusip="060505104", name="BANK AMER CORP"),
                                  dict(list="2022q2", cusip="46132E103", name="INVESCO ADVANTAGE MUN INCOME"),
                                  dict(list="2026q1", cusip="064058100", name="BANK NEW YORK MELLON CORP"),
                                  dict(list="2026q1", cusip="09249E101", name="BLACKROCK NEW YORK MUN INCOME")]))
first = recs.first


def row(sym, q):
    q = T(q)
    q1 = (q.to_period("Q") - 1).end_time.normalize()
    return M.classify_row(sym, q1, q, recs, names, first)


class Rows(unittest.TestCase):
    def test_tt_never_gets_ingersoll_rand_inc(self):
        self.assertEqual(row("TT", "2020-03-31")["status"], "new_cusip")         # new CUSIP at the rename
        for q in ("2020-06-30", "2021-12-31", "2025-06-30"):
            r = row("TT", q)
            self.assertEqual((r["status"], r["cusips"]), ("ok", ["G8994E103"]))
        self.assertEqual(row("IR", "2020-03-31")["status"], "several_issuers")   # two companies under IR
        self.assertEqual(row("IR", "2019-12-31")["status"], "several_issuers")

    def test_hwm_never_gets_alcoa_and_arnc_split_is_disputed(self):
        self.assertEqual(row("HWM", "2020-06-30")["status"], "new_cusip")
        r = row("HWM", "2020-09-30")
        self.assertEqual((r["status"], r["cusips"]), ("ok", ["443201108"]))
        self.assertEqual(row("ARNC", "2020-03-31")["status"], "several_issuers")
        for q in pd.date_range("2016-12-31", "2026-06-30", freq="QE"):
            self.assertNotIn("013872106", row("HWM", q)["cusips"])

    def test_bbt_reuse_and_tfc(self):
        self.assertEqual(row("BBT", "2019-06-30")["cusips"], ["054937107"])
        self.assertEqual(row("TFC", "2019-12-31")["status"], "new_cusip")
        self.assertEqual(row("TFC", "2020-03-31")["cusips"], ["89832Q109"])
        for q in pd.date_range("2016-03-31", "2026-06-30", freq="QE"):
            c = row("BBT", q)["cusips"]
            self.assertFalse("054937107" in c and "084680107" in c, q)
            self.assertNotIn("084680107", row("TFC", q)["cusips"])

    def test_cpay_dash_bac(self):
        self.assertEqual(row("CPAY", "2024-03-31")["status"], "new_cusip")
        self.assertEqual(row("CPAY", "2024-06-30")["cusips"], ["219948106"])
        for q in pd.date_range("2021-03-31", "2026-06-30", freq="QE"):
            self.assertNotIn("31620R303", row("CPAY", q)["cusips"])
            self.assertNotIn("G3323L100", row("DASH", q)["cusips"])
            self.assertEqual(row("BAC", q)["cusips"], ["060505104"])

    def test_bny_transition_disputed_bk_stable(self):
        self.assertEqual(row("BNY", "2025-12-31")["status"], "several_issuers")
        r = row("BNY", "2026-06-30")
        self.assertEqual((r["status"], r["cusips"]), ("ok", ["064058100"]))
        self.assertEqual(row("BNY", "2019-06-30")["cusips"], ["09249E101"])       # the fund, years before
        for q in pd.date_range("2016-03-31", "2026-03-31", freq="QE"):
            self.assertEqual(row("BK", q)["cusips"], ["064058100"])

    def test_safe_rename_and_same_prefix_cusip_change(self):
        r = row("META", "2022-06-30")
        self.assertEqual((r["status"], r["cusips"]), ("ok", ["30303M102"]))
        self.assertEqual(row("FB", "2022-03-31")["cusips"], ["30303M102"])
        self.assertEqual(row("GE", "2021-09-30")["status"], "new_cusip")
        r = row("GE", "2021-12-31")
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["cusips"], ["369604301"])        # old CUSIP last traded before the window

    def test_holders_same_set_both_quarters(self):
        ph_q = {0: np.array([1, 2, 3]), 1: np.array([3, 4])}
        self.assertEqual(M.holders([0, 1], ph_q, np.array([1, 3, 4])), 3)
        self.assertEqual(M.holders([1], ph_q, np.array([1, 3])), 1)
        self.assertEqual(M.holders([7], ph_q, np.array([1])), 0)


class Issuers(unittest.TestCase):
    def setUp(self):
        Q = pd.Period
        self.cand = {("FNF", Q("2024Q2")): {"1331875": 40, "1175454": 1},       # a Corpay Form 4 typed FNF
                     ("CPAY", Q("2024Q2")): {"1175454": 30},
                     ("BAC", Q("2022Q2")): {"70858": 80, "908993": 1},          # a fund Form 4 typed BAC
                     ("BNY", Q("2026Q1")): {"1137390": 5, "1390777": 9},
                     ("TT", Q("2020Q2")): {"1466258": 20}}
        self.edgar = {"1331875": dict(name="Fidelity National Financial, Inc.", formerNames=[]),
                      "1175454": dict(name="CORPAY, INC.", formerNames=[dict(name="FLEETCOR TECHNOLOGIES INC",
                                                                             **{"from": "2010-01-01T00:00:00Z",
                                                                                "to": "2024-03-22T00:00:00Z"})]),
                      "70858": dict(name="BANK OF AMERICA CORP /DE/", formerNames=[]),
                      "908993": dict(name="Invesco Advantage Municipal Income Trust II", formerNames=[]),
                      "1137390": dict(name="BLACKROCK NEW YORK MUNICIPAL INCOME TRUST", formerNames=[]),
                      "1390777": dict(name="Bank of New York Mellon Corp", formerNames=[]),
                      "1466258": dict(name="Trane Technologies plc", formerNames=[dict(
                          name="Ingersoll-Rand plc", **{"from": "2009-01-01T00:00:00Z", "to": "2020-03-02T00:00:00Z"})])}

    def a(self, sym, q):
        return M.assign_cik(sym, pd.Period(q), self.cand, recs, names, self.edgar, {})

    def test_typed_symbols_never_attribute_another_issuer(self):
        self.assertEqual(self.a("FNF", "2024Q2")["cik"], "1331875")
        self.assertEqual(self.a("CPAY", "2024Q2")["cik"], "1175454")
        self.assertEqual(self.a("BAC", "2022Q2")["cik"], "70858")
        self.assertEqual(self.a("TT", "2020Q2")["cik"], "1466258")

    def test_bny_transition_not_assigned(self):
        r = self.a("BNY", "2026Q1")
        self.assertIsNone(r["cik"])
        self.assertEqual(r["status"], "several_confirmed_issuers")

    def test_names(self):
        self.assertTrue(M.names_match("BANK NEW YORK MELLON CORP", "Bank of New York Mellon Corp"))
        self.assertTrue(M.names_match("BANK AMER CORP", "BANK OF AMERICA CORP /DE/"))
        self.assertFalse(M.names_match("BANK AMER CORP", "Invesco Advantage Municipal Income Trust II"))
        self.assertFalse(M.names_match("FIDELITY NATIONAL FINANCIAL", "CORPAY, INC."))


if __name__ == "__main__":
    unittest.main()
