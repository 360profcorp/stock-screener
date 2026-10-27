"""AppTest of the 50/50 tab: empty book and an activated book (RU and EN)."""
import os
import tempfile
import unittest
from pathlib import Path

import pandas as pd

try:
    from streamlit.testing.v1 import AppTest
except ImportError:                                   # streamlit only in the UI-test job
    AppTest = None

SCRIPT = """
import etf5050_tab
etf5050_tab.render("{lang}")
"""


@unittest.skipIf(AppTest is None and not os.environ.get("REQUIRE_UI_TESTS"), "streamlit not installed")
class Tab(unittest.TestCase):
    def _state(self):
        import paper_etf as P
        import test_etf5050 as T
        d = Path(tempfile.mkdtemp())
        b = T.bars(bil_div={"2026-11-02": 0.30})
        for day in ("2026-10-26", "2026-10-27", "2026-10-30", "2026-11-02", "2026-11-10"):
            P.run_daily(bars={s: f[f.index <= day] for s, f in b.items()}, now=T.at(day), folder=d)
        return d / "state.json"

    def test_empty_and_activated(self):
        os.environ["ETF5050_STATE"] = str(Path(tempfile.mkdtemp()) / "none.json")
        for lang in ("ru", "en"):
            at = AppTest.from_string(SCRIPT.format(lang=lang)).run(timeout=60)
            self.assertFalse(at.exception)
            self.assertTrue(at.info)
        os.environ["ETF5050_STATE"] = str(self._state())
        for lang in ("ru", "en"):
            at = AppTest.from_string(SCRIPT.format(lang=lang)).run(timeout=60)
            self.assertFalse(at.exception, at.exception)
            self.assertGreaterEqual(len(at.dataframe), 3)
            self.assertGreaterEqual(len(at.metric), 8)


if __name__ == "__main__":
    unittest.main()
