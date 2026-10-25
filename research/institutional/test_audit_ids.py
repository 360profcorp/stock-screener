"""Audit helpers on synthetic data (no network)."""
import unittest

import numpy as np
import pandas as pd

from research.institutional import audit_ids as A

Q = pd.Period


class Parsers(unittest.TestCase):
    def test_13f_list_and_index_page(self):
        txt = ("Run Date: 4/9/2024   ** List of Section 13F Securities **   Page 1\n"
               "B38564 10 8   *   EURONAV NV                      SHS                 \n"
               "037833 10 0   *   APPLE INC                       COM                 \n"
               "G0131Y 10 0       AGRICULTURE & NAT SOL ACQ CO    SHS CL A        ADDED\n")
        d = A.parse_13f_list(txt)
        self.assertEqual(list(d["cusip"]), ["B38564108", "037833100", "G0131Y100"])
        self.assertEqual(d.loc[1, "name"], "APPLE INC")
        h = ('<div class="infoHead">Filing Date</div>\n<div class="info">2024-02-14</div>'
             '<div class="infoHead">Accepted</div>\n<div class="info">2024-02-13 17:45:01</div>'
             '<div class="infoHead">Period of Report</div>\n<div class="info">2023-12-31</div>')
        self.assertEqual(A.parse_index(h), dict(filing_date="2024-02-14",
                                                accepted="2024-02-13 17:45:01", period="2023-12-31"))

    def test_names(self):
        self.assertTrue(A.names_match("META PLATFORMS INC", "Meta Platforms, Inc."))
        self.assertTrue(A.names_match("ALPHABET INC", "Alphabet Inc."))
        self.assertTrue(A.names_match("BERKSHIRE HATHAWAY INC DEL", "BERKSHIRE HATHAWAY INC"))
        self.assertFalse(A.names_match("APPLE INC", "MICROSOFT CORP"))
        self.assertFalse(A.names_match("SQUARE INC", "BLOCK INC"))


class Identity(unittest.TestCase):
    def setUp(self):
        rows = [("XYZ", Q("2017Q1"), "0000000001", 30), ("XYZ", Q("2017Q2"), "0000000001", 30),
                ("XYZ", Q("2022Q1"), "0000000002", 20), ("XYZ", Q("2022Q2"), "0000000002", 20),
                ("XYZ", Q("2022Q2"), "0000000009", 1),
                ("OLD", Q("2017Q1"), "0000000003", 10), ("NEW", Q("2022Q1"), "0000000003", 10)]
        self.f4 = pd.DataFrame(rows, columns=["sym", "q", "cik", "n"])
        self.I = A.Identity(self.f4, {"NEW": "0000000003"})

    def test_dated_issuer(self):
        self.assertEqual(self.I.cik("XYZ", Q("2017Q2")), "0000000001")
        self.assertEqual(self.I.cik("XYZ", Q("2017Q4")), "0000000001")     # nearest within 2
        self.assertEqual(self.I.cik("XYZ", Q("2022Q2")), "0000000002")
        self.assertIsNone(self.I.cik("XYZ", Q("2019Q3")))
        self.assertEqual(self.I.cik("NEW", Q("2017Q1")), "0000000003")     # renamed symbol

    def test_validity_reuse_and_rename(self):
        # CUSIP C1 is company 1 (XYZ until 2017), C2 is company 2 (XYZ from 2022)
        ftd = pd.DataFrame([("C1", "XYZ", Q("2017Q1")), ("C2", "XYZ", Q("2022Q1")),
                            ("C3", "OLD", Q("2017Q1")), ("C3", "NEW", Q("2022Q1"))],
                           columns=["cusip", "sym", "q"])
        mapping = pd.DataFrame(dict(cusip=["C1", "C2", "C3"], ticker=["XYZ", "XYZ", "NEW"]))
        per = [pd.Timestamp("2017-03-31"), pd.Timestamp("2022-03-31")]
        V = A.validity(mapping, per, self.I, ftd, {}, {}, {}).set_index(["cusip", "period"])["status"]
        self.assertEqual(V[("C1", per[0])], "ftd")
        self.assertEqual(V[("C1", per[1])], "unverified")     # C1 not traded then, no name proof
        self.assertEqual(V[("C2", per[0])], "unverified")
        self.assertEqual(V[("C2", per[1])], "ftd")
        self.assertEqual(V[("C3", per[0])], "ftd")             # old symbol of the same CIK
        self.assertEqual(V[("C3", per[1])], "ftd")

    def test_conflict_and_name_route(self):
        ftd = pd.DataFrame([("C9", "OLD", Q("2022Q1"))], columns=["cusip", "sym", "q"])
        f4 = pd.concat([self.f4, pd.DataFrame([("OLD", Q("2022Q1"), "0000000005", 9)],
                                              columns=["sym", "q", "cik", "n"])])
        I = A.Identity(f4, {})
        p = pd.Timestamp("2022-03-31")
        mapping = pd.DataFrame(dict(cusip=["C9", "C8"], ticker=["XYZ", "XYZ"]))
        lists = {p: {"C8": "SECOND COMPANY INC"}}
        edgar = {"0000000002": dict(name="Second Company, Inc.", formerNames=[])}
        V = A.validity(mapping, [p], I, ftd, lists, edgar, {}).set_index("cusip")["status"]
        self.assertEqual(V["C9"], "conflict")
        self.assertEqual(V["C8"], "name")


class Holders(unittest.TestCase):
    def test_breadth_common_filers_and_pit(self):
        p0, p1 = pd.Timestamp("2019-12-31"), pd.Timestamp("2020-03-31")
        # filer f holds cusip c: code f*4096+c; filer 2 only files in p1 (not common)
        pairs = {p0: np.array([0 * 4096 + 0, 1 * 4096 + 0, 1 * 4096 + 1]),
                 p1: np.array([0 * 4096 + 0, 2 * 4096 + 0, 1 * 4096 + 1])}
        filers = {p0: {0, 1}, p1: {0, 1, 2}}
        assign = lambda p: np.array([0, 1])                     # noqa: E731
        B = A.breadth(pairs, filers, 4096, assign, 2, ["AAA", "BBB"]).set_index("ticker")
        self.assertEqual((B.at["AAA", "holders_q1"], B.at["AAA", "holders_q"]), (2, 1))
        self.assertEqual((B.at["BBB", "holders_q1"], B.at["BBB", "holders_q"]), (1, 1))
        self.assertEqual(str(B.at["AAA", "usable_from"].date()), "2020-05-16")
        rows = pd.DataFrame(dict(ticker=["AAA", "AAA", "AAA"], signal_date=pd.to_datetime(
            ["2020-05-15", "2020-05-16", "2020-10-01"])))
        f2, used, uf = A.f2_pit(rows, B.reset_index())
        self.assertEqual(list(f2), [0.0, -0.5, 0.0])            # not public / public / too old

    def test_order_changes(self):
        rows = pd.DataFrame(dict(ticker=list("ABC"), signal_date=[pd.Timestamp("2020-01-02")] * 3,
                                 rs=[99, 95, 90]))
        self.assertEqual(len(A.order_changes(rows, [0.1, 0.2, 0.0], [0.1, 0.2, 0.0])), 0)
        oc = A.order_changes(rows, [0.1, 0.2, 0.0], [0.3, 0.2, 0.0])
        self.assertEqual(oc.iloc[0]["top3_build"], "B,A,C")
        self.assertEqual(oc.iloc[0]["top3_audit"], "A,B,C")


if __name__ == "__main__":
    unittest.main()
