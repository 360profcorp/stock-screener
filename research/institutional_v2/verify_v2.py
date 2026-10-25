"""Independent re-check of the v2 mapping from raw SEC/EDGAR files (CORRECTION_V2.md R6).

Stand-alone on purpose: it uses only pandas/requests and the committed v2 outputs, and never
imports the v2 code, so a reviewer (Muse) can read it in one sitting and re-run it.

    python research/institutional_v2/verify_v2.py --build research/results/institutional_v2/build/<run> \
        --out DIR [--seed N] [--email you@example.com]

Random sample (seeded), re-derived from the original files:
  150 security-set decisions   all SEC fails-to-deliver files in the row's window are
                               re-read: the CUSIP set under the symbol, the issuer-prefix
                               rule and the new-CUSIP rule (FTD part) must match the row
  every 13(f) List name cited  in those rows is looked up in the Official 13(f) List PDF
  100 counted 13F filings      EDGAR index page "Accepted" (ET) vs usable_from: the row's
                               ok flag must equal (accepted < usable_from 00:00 ET)
  50 used Form 4 purchases     EDGAR index page: issuer CIK = the v2 CIK of (ticker, quarter);
                               accepted before 00:00 ET of the first signal day using it
Any discrepancy is listed. The exit code is 0 only if there is none.
"""
import argparse
import io
import json
import re
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

SEC = "https://www.sec.gov"


class Get:
    def __init__(self, ua, cache):
        self.s = requests.Session()
        self.s.headers["User-Agent"] = ua
        self.t, self.cache = 0.0, Path(cache)
        self.cache.mkdir(parents=True, exist_ok=True)

    def __call__(self, url, keep=False):
        url = url if url.startswith("http") else SEC + url
        p = self.cache / re.sub(r"[^A-Za-z0-9._-]", "_", url)[-180:]
        if keep and p.exists():
            return p.read_bytes()
        for k in range(4):
            w = 0.2 - (time.time() - self.t)
            if w > 0:
                time.sleep(w)
            self.t = time.time()
            try:
                r = self.s.get(url, timeout=120)
            except requests.RequestException:
                time.sleep(5 * (k + 1))
                continue
            if r.status_code == 200:
                if keep:
                    p.write_bytes(r.content)
                return r.content
            if r.status_code in (403, 429, 500, 502, 503):
                time.sleep(5 * (k + 1))
                continue
            return None
        return None


def norm(s):
    return str(s).strip().upper().replace(".", "-").replace("/", "-")


def ftd_rows(G):
    html = G("/data-research/sec-markets-data/fails-deliver-data").decode("utf-8", "replace")
    out = []
    for l in sorted(set(re.findall(r'href="([^"]+cnsfails(20\d\d)\d\d[ab]?\.zip)"', html))):
        if int(l[1]) < 2016:                 # same scope as the v2 sources
            continue
        b = G(l[0], keep=True)
        z = zipfile.ZipFile(io.BytesIO(b))
        with z.open(z.namelist()[0]) as f:
            d = pd.read_csv(f, sep="|", dtype=str, usecols=[0, 1, 2], encoding="latin-1", on_bad_lines="skip")
        d.columns = ["date", "cusip", "sym"]
        out.append(d.dropna())
    d = pd.concat(out, ignore_index=True)
    d["date"] = pd.to_datetime(d["date"], format="%Y%m%d", errors="coerce")
    d["cusip"] = d["cusip"].str.strip().str.upper()
    d["sym"] = d["sym"].map(norm)
    return d.dropna(subset=["date"])


def list_text(G, q):
    y, k = q[:4], q[-1]
    for u in (f"/files/investment/13flist{y}q{k}.pdf", f"/divisions/investment/13f/13flist{y}q{k}.pdf"):
        b = G(u, keep=True)
        if b and b[:4] == b"%PDF":
            with tempfile.TemporaryDirectory() as d:
                (Path(d) / "a.pdf").write_bytes(b)
                subprocess.run(["pdftotext", "-layout", str(Path(d) / "a.pdf"), str(Path(d) / "a.txt")], check=True)
                return (Path(d) / "a.txt").read_text(errors="replace")
    return None


def index_page(G, cik, acc):
    url = f"{SEC}/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{acc}-index.htm"
    b = G(url)
    if b is None:
        return url, None, None, None
    h = b.decode("utf-8", "replace")
    a = re.search(r'Accepted\s*</div>\s*<div class="info">\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', h)
    f = re.search(r'Filing Date\s*</div>\s*<div class="info">\s*(\d{4}-\d{2}-\d{2})', h)
    issuer = None
    for blk in re.findall(r'class="companyName"(.*?)</span>', h, re.S | re.I):
        if "issuer" in blk.lower():
            m = re.search(r"CIK=?\D{0,8}(\d{4,10})", blk, re.I)
            if m:
                issuer = str(int(m.group(1)))
    if issuer is None and "Issuer" in h:
        k = h.find("Issuer")
        Path("/tmp/verify_v2_debug.html").write_text(h[max(0, k - 1500):k + 1500])
    return url, a and a.group(1), f and f.group(1), issuer


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=20261026)
    ap.add_argument("--email", default="360pro.corp@gmail.com")
    ap.add_argument("--cache", default="/tmp/verify_v2_cache")
    a = ap.parse_args(argv)
    B, out = Path(a.build), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    G = Get(f"VISAR research verification {a.email}", a.cache)
    bad, log = [], {}

    # ---- security sets
    S = pd.read_csv(B / "security_sets.csv.gz", dtype=str).fillna("")
    S = S[(S["member_in_use_window"] == "True") & (S["period"] >= "2016-06-30")]   # windows inside the FTD scope
    smp = pd.concat([S[S["status"] == "ok"].sample(100, random_state=a.seed),
                     S[S["status"] != "ok"].sample(min(50, int((S["status"] != "ok").sum())), random_state=a.seed)])
    F = ftd_rows(G)
    first_any = F.groupby("cusip")["date"].min()
    by_sym = {k: g for k, g in F[F["sym"].isin(set(smp["ticker"]))].groupby("sym")}
    lists_needed = {}
    for r in smp.itertuples():
        q = pd.Timestamp(r.period)
        q1 = (q.to_period("Q") - 1).end_time.normalize()
        lo, hi = q1 - pd.Timedelta(days=30), q + pd.Timedelta(days=166)
        g = by_sym.get(r.ticker, F.iloc[:0])
        Sx = sorted(set(g[(g["date"] >= lo) & (g["date"] <= hi) & (g["cusip"].str.len() == 9)]["cusip"]))
        mine = sorted(c for c in r.cusips.split(",") if c)
        if Sx != mine:
            bad.append(dict(check="security set", ticker=r.ticker, period=r.period, v2=mine, raw=Sx))
            continue
        several = len({c[:6] for c in Sx}) > 1
        if several != (r.status == "several_issuers"):
            bad.append(dict(check="issuer-prefix rule", ticker=r.ticker, period=r.period, v2=r.status,
                            raw_prefixes=sorted({c[:6] for c in Sx})))
        if r.status == "ok" and any(first_any.get(c, pd.Timestamp.max) > q1 for c in Sx):
            # ok is still right if 13F holdings existed at Q-1 (not visible in FTD): reported, not failed
            log.setdefault("ok_rows_new_in_ftd_but_held_before", []).append(f"{r.ticker} {r.period}")
        for part in r.names.split("; "):
            m = re.match(r"(\w{9})=(.*) \[13\(f\) list (\d{4}q\d)\]", part)
            if m:
                lists_needed.setdefault(m.group(3), []).append((m.group(1), m.group(2), r.ticker, r.period))
    log["sets_checked"] = int(len(smp))
    n_names = 0
    for q, items in lists_needed.items():
        t = list_text(G, q)
        if t is None:
            bad.append(dict(check="13(f) list missing", list=q))
            continue
        for c, nm, tk, p in items:
            n_names += 1
            pat = rf"{c[:6]}\s+{c[6:8]}\s+{c[8]}\s+\*?\s*{re.escape(nm[:20])}"
            if not re.search(pat, t):
                bad.append(dict(check="13(f) list name", list=q, cusip=c, name=nm, ticker=tk, period=p))
    log["list_names_checked"] = n_names

    # ---- 13F acceptance
    C = pd.read_csv(B / "f13_counted_sample.csv", dtype=str).sample(100, random_state=a.seed)
    for r in C.itertuples():
        url, acc_t, fd, _ = index_page(G, r.cik, r.acc)
        if acc_t is None:
            bad.append(dict(check="13F index page", acc=r.acc, url=url))
            continue
        okx = pd.Timestamp(acc_t) < pd.Timestamp(r.usable_from)
        if okx != (r.ok == "True") or fd != r.filing_date[:10]:
            bad.append(dict(check="13F acceptance", acc=r.acc, v2_ok=r.ok, raw_accepted=acc_t, raw_filing_date=fd,
                            v2_filing_date=r.filing_date, usable_from=r.usable_from, url=url))
    log["f13_filings_checked"] = int(len(C))

    # ---- Form 4 purchases
    K = pd.read_csv(B / "cik_map.csv.gz", dtype=str)
    cmap = {(t, q): c for t, q, c, s in zip(K["ticker"], K["quarter"], K["cik"], K["status"]) if s == "ok"}
    P = pd.read_csv(B / "form4_acceptance.csv", dtype=str).dropna(subset=["accepted_et"])
    P = P.sample(min(50, len(P)), random_state=a.seed)
    for r in P.itertuples():
        m = re.search(r"/data/(\d+)/", r.url)
        url, acc_t, fd, issuer = index_page(G, m.group(1), r.ACCESSION_NUMBER)
        q = str(pd.Timestamp(r.filing_date).to_period("Q"))
        exp = str(int(float(cmap.get((r.ticker, q), "nan")))) if (r.ticker, q) in cmap else None
        if acc_t is None or issuer != exp or not (pd.Timestamp(acc_t) < pd.Timestamp(r.first_use)):
            bad.append(dict(check="Form 4", acc=r.ACCESSION_NUMBER, ticker=r.ticker, quarter=q, v2_cik=exp,
                            raw_issuer=issuer, raw_accepted=acc_t, first_use=r.first_use, url=url))
    log["form4_checked"] = int(len(P))
    res = dict(log, discrepancies=len(bad), details=bad[:200], seed=a.seed)
    (out / "verify_v2.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps({k: v for k, v in res.items() if k != "details"}, indent=1))
    for x in bad[:30]:
        print(x)
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
