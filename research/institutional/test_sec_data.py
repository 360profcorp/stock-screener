"""SEC builders on synthetic SEC-format files (no network)."""
import io
import tempfile
import unittest
import zipfile
from pathlib import Path

import pandas as pd

from research.institutional import sec_data as S


def zbytes(files):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for n, txt in files.items():
            z.writestr(n, txt)
    return b.getvalue()


class FakeF:
    def __init__(self, pages, blobs):
        self.pages, self.blobs, self.log = pages, blobs, []

    def links(self, page):
        return self.pages[page]

    def get(self, url):
        return self.blobs.get(url)


F4 = {
    "SUBMISSION.tsv": "ACCESSION_NUMBER\tFILING_DATE\tPERIOD_OF_REPORT\tDOCUMENT_TYPE\tISSUERCIK\tISSUERNAME\tISSUERTRADINGSYMBOL\n"
                      "a1\t05-FEB-2020\t03-FEB-2020\t4\t0000000001\tAAA INC\tAAA\n"
                      "a2\t06-FEB-2020\t04-FEB-2020\t4\t0000000002\tOLD NAME\tOLDB\n"
                      "a3\t07-FEB-2020\t05-FEB-2020\t4/A\t0000000001\tAAA INC\tAAA\n",
    "NONDERIV_TRANS.tsv": "ACCESSION_NUMBER\tTRANS_DATE\tTRANS_CODE\tTRANS_SHARES\tTRANS_ACQUIRED_DISP_CD\n"
                          "a1\t03-FEB-2020\tP\t100\tA\na1\t03-FEB-2020\tS\t100\tD\n"
                          "a2\t04-FEB-2020\tP\t50\tA\na3\t05-FEB-2020\tP\t10\tA\n",
    "REPORTINGOWNER.tsv": "ACCESSION_NUMBER\tRPTOWNERCIK\na1\t0000000901\na2\t0000000902\na3\t0000000903\n",
}
FTD = "SETTLEMENT DATE|CUSIP|SYMBOL|QUANTITY (FAILS)|DESCRIPTION|PRICE\n" \
      "20200115|000000AA1|AAA|10|AAA|1\n20200115|000000BB2|OLDB|10|B|1\n20200115|000000ZZ9|ZZZ|1|Z|1\n"


def f13(sub_rows, info_rows):
    return zbytes({
        "SUBMISSION.tsv": "ACCESSION_NUMBER\tFILING_DATE\tSUBMISSIONTYPE\tCIK\tPERIODOFREPORT\n" +
                          "".join("\t".join(r) + "\n" for r in sub_rows),
        "INFOTABLE.tsv": "ACCESSION_NUMBER\tINFOTABLE_SK\tNAMEOFISSUER\tTITLEOFCLASS\tCUSIP\tFIGI\tVALUE\tSSHPRNAMT\tSSHPRNAMTTYPE\tPUTCALL\n" +
                         "".join(f"{a}\t1\tX\tCOM\t{c}\t\t1\t1\t{t}\t{p}\n" for a, c, t, p in info_rows)})


class Builders(unittest.TestCase):
    def test_form4_ftd_13f(self):
        q4 = f13([("h1", "10-FEB-2020", "13F-HR", "M1", "31-DEC-2019"),
                  ("h2", "11-FEB-2020", "13F-HR", "M2", "31-DEC-2019"),
                  ("h3", "20-MAR-2020", "13F-HR", "M3", "31-DEC-2019")],     # late: excluded
                 [("h1", "000000AA1", "SH", ""), ("h2", "000000AA1", "SH", ""),
                  ("h2", "000000BB2", "SH", ""), ("h1", "000000BB2", "SH", "Put"),
                  ("h3", "000000AA1", "SH", "")])
        q1 = f13([("k1", "10-MAY-2020", "13F-HR", "M1", "31-MAR-2020"),
                  ("k2", "11-MAY-2020", "13F-HR", "M2", "31-MAR-2020")],
                 [("k1", "000000AA1", "SH", ""), ("k1", "000000BB2", "SH", ""),
                  ("k2", "000000BB2", "SH", "")])
        F = FakeF({"form345": ["/x/2020q1_form345.zip"], "ftd": ["/x/cnsfails202001a.zip"],
                   "form13f": ["/x/2020q1_form13f.zip", "/x/2020q2_form13f.zip"]},
                  {"/x/2020q1_form345.zip": zbytes(F4), "/x/cnsfails202001a.zip": zbytes({"f.txt": FTD}),
                   "/x/2020q1_form13f.zip": q4, "/x/2020q2_form13f.zip": q1})
        tickers = {"AAA", "NEWB"}
        t2cik = {"AAA": "0000000001", "NEWB": "0000000002"}
        with tempfile.TemporaryDirectory() as d:
            b, f, lag, sc = S.form4(F, tickers, t2cik, Path(d))
            # only P/A on an original Form 4; the renamed issuer maps through its CIK
            self.assertEqual(sorted(zip(b["ticker"], b["owner_cik"])),
                             [("AAA", "0000000901"), ("NEWB", "0000000902")])
            self.assertEqual(sorted(lag.tolist()), [2, 2])
            cmap, _ = S.cusip_map(F, tickers, t2cik, sc)
            self.assertEqual(dict(zip(cmap["cusip"], cmap["ticker"])),
                             {"000000AA1": "AAA", "000000BB2": "NEWB"})
            B, per, lag13 = S.form13f(F, cmap, Path(d))
            r = B.set_index("ticker")
            # Q1-2020 vs Q4-2019 among filers in both (M1, M2); M3 filed late -> ignored;
            # the put does not count as holding
            self.assertEqual((r.at["AAA", "holders_q1"], r.at["AAA", "holders_q"]), (2, 1))
            self.assertEqual((r.at["NEWB", "holders_q1"], r.at["NEWB", "holders_q"]), (1, 2))
            self.assertEqual(str(r.at["AAA", "usable_from"]), "2020-05-16")
            self.assertAlmostEqual(r.at["AAA", "breadth_change"], -0.5)


if __name__ == "__main__":
    unittest.main()
