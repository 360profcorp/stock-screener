"""EDGAR acceptance timestamps of every counted 13F-HR filing (CORRECTION_V2.md §3).

    python -m research.institutional_v2.accept --src V2SRC_DIR --out DIR

Source: EDGAR submissions data of each filer (data.sec.gov/submissions/CIK##########.json and
its older pages). Calibration: a random sample of 200 accessions is compared with the EDGAR
filing index page ("Accepted", Eastern time).

Outputs: acceptance.csv.gz (acc, cik, edgar_filing_date, acceptance_raw, accepted_et, form),
         calibration.csv, accept.json
"""
import argparse
import json
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd

from research.institutional.sec_data import Fetcher

SEED = 20261025


class FastFetcher(Fetcher):
    """SEC fair access allows 10 requests/s; stay at about 6."""
    GAP = 0.16

    def get(self, url, tries=4):
        import requests
        url = url if url.startswith("http") else "https://www.sec.gov" + url
        for k in range(tries):
            w = self.GAP - (time.time() - self.t)
            if w > 0:
                time.sleep(w)
            self.t = time.time()
            try:
                r = self.s.get(url, timeout=120)
                if r.status_code == 200:
                    return r.content
                if r.status_code in (403, 429, 500, 502, 503):
                    time.sleep(5 * (k + 1))
                    continue
                return None
            except requests.RequestException:
                time.sleep(5 * (k + 1))
        self.log.append(dict(url=url, status="failed"))
        return None


def rows_of(block):
    n = len(block.get("accessionNumber", []))
    return pd.DataFrame(dict(acc=block.get("accessionNumber", []), edgar_filing_date=block.get("filingDate", []),
                             acceptance_raw=block.get("acceptanceDateTime", []), form=block.get("form", [])))[:n]


def fetch_cik(F, cik, need):
    """Acceptance rows for the accessions in `need` (dict acc -> filing date) of one filer."""
    b = F.get(f"https://data.sec.gov/submissions/CIK{str(cik).zfill(10)}.json")
    if b is None:
        return pd.DataFrame(), "no submissions file"
    j = json.loads(b)
    got = [rows_of(j.get("filings", {}).get("recent", {}))]
    have = set(got[0]["acc"])
    missing = set(need) - have
    if missing:
        lo = min(need[a] for a in missing)
        hi = max(need[a] for a in missing)
        for f in j.get("filings", {}).get("files", []):
            fr, to = pd.Timestamp(f.get("filingFrom", "1990-01-01")), pd.Timestamp(f.get("filingTo", "2100-01-01"))
            if to < lo - pd.Timedelta(days=5) or fr > hi + pd.Timedelta(days=5):
                continue
            p = F.get(f"https://data.sec.gov/submissions/{f['name']}")
            if p is None:
                continue
            got.append(rows_of(json.loads(p)))
            missing -= set(got[-1]["acc"])
            if not missing:
                break
    d = pd.concat(got, ignore_index=True)
    return d[d["acc"].isin(need)], None


def parse_index_accepted(html):
    m = re.search(r'infoHead">\s*Accepted\s*</div>\s*<div class="info">\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', html)
    f = re.search(r'infoHead">\s*Filing Date\s*</div>\s*<div class="info">\s*(\d{4}-\d{2}-\d{2})', html)
    return (m.group(1) if m else None), (f.group(1) if f else None)


def to_et(raw, mode):
    """acceptanceDateTime -> naive Eastern time. mode 'label' = the clock time already is
    Eastern (the 'Z' is a label only); mode 'utc' = true UTC."""
    t = pd.to_datetime(pd.Series(raw), errors="coerce", utc=True)
    if mode == "utc":
        return t.dt.tz_convert("America/New_York").dt.tz_localize(None)
    return t.dt.tz_localize(None)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    fl = pd.read_csv(Path(a.src) / "f13_filings.csv.gz", dtype={"cik": str}, parse_dates=["filing_date", "period"])
    F = FastFetcher()
    parts, errors = [], {}
    by = fl.groupby("cik")
    t0 = time.time()
    for k, (cik, g) in enumerate(by):
        d, err = fetch_cik(F, cik, dict(zip(g["acc"], g["filing_date"])))
        if err:
            errors[cik] = err
        if len(d):
            parts.append(d.assign(cik=cik))
        if k % 500 == 0:
            print("ciks", k, by.ngroups, round(time.time() - t0), flush=True)
    A = pd.concat(parts, ignore_index=True).drop_duplicates("acc")
    # calibration against EDGAR index pages
    rng = np.random.default_rng(SEED)
    s = A.iloc[rng.choice(len(A), size=min(200, len(A)), replace=False)]
    cal = []
    for r in s.itertuples(index=False):
        url = f"https://www.sec.gov/Archives/edgar/data/{int(r.cik)}/{r.acc.replace('-', '')}/{r.acc}-index.htm"
        b = F.get(url)
        acc_t, fd = parse_index_accepted(b.decode("utf-8", "replace")) if b else (None, None)
        cal.append(dict(acc=r.acc, cik=r.cik, url=url, index_accepted_et=acc_t, index_filing_date=fd,
                        acceptance_raw=r.acceptance_raw, edgar_filing_date=r.edgar_filing_date))
    C = pd.DataFrame(cal)
    ok = {}
    for mode in ("label", "utc"):
        C[f"et_{mode}"] = to_et(C["acceptance_raw"], mode).values
        ok[mode] = int((pd.to_datetime(C["index_accepted_et"]) == C[f"et_{mode}"]).sum())
    mode = max(ok, key=ok.get)
    C.to_csv(out / "calibration.csv", index=False)
    A["accepted_et"] = to_et(A["acceptance_raw"], mode).values
    A.to_csv(out / "acceptance.csv.gz", index=False)
    info = dict(filings=int(len(fl)), ciks=int(by.ngroups), with_timestamp=int(fl["acc"].isin(A["acc"]).sum()),
                without_timestamp=int((~fl["acc"].isin(A["acc"])).sum()), cik_errors=len(errors),
                calibration=dict(n=int(len(C)), fetched=int(C["index_accepted_et"].notna().sum()),
                                 agree_label=ok["label"], agree_utc=ok["utc"], mode=mode,
                                 filing_date_agree=int((C["index_filing_date"] == C["edgar_filing_date"]).sum())),
                failed_requests=len([x for x in F.log if x.get("status") == "failed"]),
                runtime_sec=round(time.time() - t0))
    (out / "accept.json").write_text(json.dumps(dict(info, cik_error_examples=dict(list(errors.items())[:30])),
                                                indent=1, default=str))
    print(json.dumps(info, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
