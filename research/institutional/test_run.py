"""Point-in-time features and orders (synthetic, no network)."""
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from research.institutional import run as IR


class Features(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        p = Path(self.d.name)
        pd.DataFrame(dict(ticker=["AAA"] * 4, owner_cik=[1, 2, 2, 3],
                          filing_date=["2020-01-10", "2020-03-01", "2020-03-02", "2020-03-05"],
                          trans_date=["2020-01-08", "2020-02-27", "2020-02-28", "2020-03-04"])
                     ).to_csv(p / "form4_buys.csv.gz", index=False)
        pd.DataFrame(dict(ticker=["AAA"], filing_date=["2020-03-01"], n=[1])) \
            .to_csv(p / "form4_filings.csv.gz", index=False)
        pd.DataFrame(dict(ticker=["AAA", "AAA"], period=["2019-12-31", "2020-03-31"],
                          usable_from=["2020-02-15", "2020-05-16"], holders_q=[10, 12],
                          holders_q1=[8, 10], common_filers=[100, 100],
                          breadth_change=[0.25, 0.2])).to_csv(p / "f13_breadth.csv.gz", index=False)
        self.sec = p

    def tearDown(self):
        self.d.cleanup()

    def test_only_filings_before_the_signal_day(self):
        tr = pd.DataFrame(dict(ticker=["AAA"] * 5, signal_date=pd.to_datetime(
            ["2020-03-05", "2020-03-06", "2020-04-15", "2020-05-15", "2020-05-16"])))
        f = IR.features(tr, self.sec).set_index("signal_date")
        self.assertEqual(f.loc["2020-03-05", "F1"], 2)        # owners 1, 2; 3 filed that day
        self.assertEqual(f.loc["2020-03-06", "F1"], 3)
        self.assertEqual(f.loc["2020-04-15", "F1"], 2)        # owner 1 filed > 90 days before
        self.assertEqual(f.loc["2020-05-15", "F2"], 0.25)     # Q1-2020 not public yet
        self.assertEqual(f.loc["2020-05-16", "F2"], 0.2)
        chk = IR.pit_check(f.reset_index())
        self.assertEqual((chk["form4_filings_on_or_after_signal_day"],
                          chk["f13_quarters_not_yet_public"]), (0, 0))

    def test_orders_only_change_the_same_day_sequence(self):
        d = pd.Timestamp("2020-03-06")
        tr = pd.DataFrame(dict(date=[d, d, d, d + pd.Timedelta(days=1)], ticker=list("ABCD"),
                               rs=[99, 90, 95, 80], F1=[0, 3, 1, 5], F2=[0.1, -0.2, 0.3, 0]))
        self.assertEqual(list(IR.order(tr, "RS")["ticker"]), ["A", "C", "B", "D"])
        self.assertEqual(list(IR.order(tr, "INS")["ticker"]), ["B", "C", "A", "D"])
        self.assertEqual(list(IR.order(tr, "BR")["ticker"]), ["C", "A", "B", "D"])
        for how in ("RS", "INS", "BR", "IR", "RND"):
            o = IR.order(tr, how, seed=3)
            self.assertEqual(sorted(o["ticker"]), list("ABCD"))
            self.assertEqual(o["ticker"].iloc[-1], "D")


if __name__ == "__main__":
    unittest.main()
