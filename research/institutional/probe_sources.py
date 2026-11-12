"""Source feasibility probe (no research result): which historical sources are reachable from
GitHub Actions, how far back, and whether an AI key is configured. Prints only facts."""
import json
import os
import time

import requests

UA = {"User-Agent": "VISAR research 360pro.corp@gmail.com", "Accept-Encoding": "gzip, deflate"}


def get(url, **kw):
    t = time.time()
    try:
        r = requests.get(url, headers=UA, timeout=30, **kw)
        return dict(status=r.status_code, bytes=len(r.content), sec=round(time.time() - t, 1),
                    head=r.text[:160].replace("\n", " "))
    except Exception as e:
        return dict(error=type(e).__name__)


out = {}
out["sec_company_tickers"] = get("https://www.sec.gov/files/company_tickers.json")
out["sec_full_index_2016Q1"] = get("https://www.sec.gov/Archives/edgar/full-index/2016/QTR1/form.idx")
out["sec_full_index_2025Q3"] = get("https://www.sec.gov/Archives/edgar/full-index/2025/QTR3/form.idx")
out["sec_13f_datasets_page"] = get("https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets")
out["sec_insider_datasets_page"] = get("https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets")
out["sec_insider_zip_2016q1"] = get("https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/2016q1_form345.zip", stream=True)
out["sec_13f_zip_2016q1"] = get("https://www.sec.gov/files/structureddata/data/form-13f-data-sets/2016q1_form13f.zip", stream=True)
out["sec_submissions_aapl"] = get("https://data.sec.gov/submissions/CIK0000320193.json")
out["gdelt_doc_api"] = get("https://api.gdeltproject.org/api/v2/doc/doc?query=apple&mode=artlist&format=json&startdatetime=20200301000000&enddatetime=20200302000000&maxrecords=5")
out["gdelt_v1_events_2016"] = get("http://data.gdeltproject.org/gkg/20160104.gkg.csv.zip", stream=True)
out["ai_keys_present"] = {k: bool(os.getenv(k)) for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")}
print(json.dumps(out, indent=1))
print("::notice title=probe::" + json.dumps(out).replace("%", "%25"))
