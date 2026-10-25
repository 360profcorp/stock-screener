"""SEC data for Institutional v1 (PREREG_INSTITUTIONAL.md §3). Official SEC files only.

    python -m research.institutional.sec_data --pit PIT_CSV --out DIR

Downloads (User-Agent identified, <= 5 requests/s):
  * Insider Transactions Data Sets (Forms 3/4/5), quarterly 2016q1 ->
  * Form 13F Data Sets, every file whose filings fall in 2016 ->
  * Fails-to-Deliver files 2016 -> (CUSIP <-> symbol only)
  * company_tickers.json (ticker <-> CIK)
Writes compact tables for the study tickers (S&P 500 members since 2016):
  form4_buys.csv.gz      issuer ticker, filing_date, owner_cik, trans_date (open-market P, A)
  form4_filings.csv.gz   ticker, filing_date, n (all Form 4 filings: coverage)
  f13_breadth.csv.gz     ticker, period, usable_from, holders_q, holders_q1, breadth_change
                         (13F-HR originals filed by the 45-day deadline; filers in both quarters)
  f13_periods.csv        filers and holding pairs per report quarter
  mapping.csv / sources.json (urls, sha256, rows) / lags.json (publication-time evidence)
"""
import argparse
import gzip
import hashlib
import io
import json
import re
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

UA = {"User-Agent": "VISAR research 360pro.corp@gmail.com"}
SEC = "https://www.sec.gov"
PAGES = {"form345": "/data-research/sec-markets-data/insider-transactions-data-sets",
         "form13f": "/data-research/sec-markets-data/form-13f-data-sets",
         "ftd": "/data-research/sec-markets-data/fails-deliver-data"}
START_YEAR = 2016


def norm(t):
    return str(t).strip().upper().replace(".", "-").replace("/", "-")


class Fetcher:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update(UA)
        self.log, self.t = [], 0.0

    def get(self, url, tries=4):
        url = url if url.startswith("http") else SEC + url
        for k in range(tries):
            wait = 0.25 - (time.time() - self.t)
            if wait > 0:
                time.sleep(wait)
            self.t = time.time()
            try:
                r = self.s.get(url, timeout=180)
                if r.status_code == 200:
                    self.log.append(dict(url=url, bytes=len(r.content),
                                         sha256=hashlib.sha256(r.content).hexdigest()))
                    return r.content
                if r.status_code in (403, 429, 500, 502, 503):
                    time.sleep(5 * (k + 1))
                    continue
                self.log.append(dict(url=url, status=r.status_code))
                return None
            except requests.RequestException:
                time.sleep(5 * (k + 1))
        self.log.append(dict(url=url, status="failed"))
        return None

    def links(self, page):
        html = self.get(PAGES[page]).decode("utf-8", "replace")
        return sorted(set(re.findall(r'href="([^"]+\.zip)"', html)))


def years_in(name):
    m = re.findall(r"(20\d\d)", name)
    return [int(x) for x in m]


def member(z, name):
    """Archive member by base name (some SEC zips keep the files in a sub-folder)."""
    for n in z.namelist():
        if n.split("/")[-1].upper() == name.upper():
            return n
    raise KeyError(f"{name} not in archive ({z.namelist()[:5]})")


def tsv(z, name, usecols=None):
    with z.open(member(z, name)) as f:
        return pd.read_csv(f, sep="\t", dtype=str, usecols=usecols, quoting=3,
                           on_bad_lines="skip", low_memory=False)


def sec_date(s):
    return pd.to_datetime(s, format="%d-%b-%Y", errors="coerce")


# ---------------------------------------------------------------- mapping
def study_tickers(pit_csv):
    df = pd.read_csv(pit_csv)
    df["date"] = pd.to_datetime(df["date"])
    df = df[df["date"] >= f"{START_YEAR}-01-01"]
    out = set()
    for s in df["tickers"]:
        out |= {norm(t) for t in str(s).split(",") if t.strip()}
    return out


def ticker_cik(F):
    j = json.loads(F.get("https://www.sec.gov/files/company_tickers.json"))
    return {norm(v["ticker"]): str(v["cik_str"]).zfill(10) for v in j.values()}


# ---------------------------------------------------------------- Form 4
def form4(F, tickers, t2cik, out):
    links = [l for l in F.links("form345") if (years_in(l) or [0])[0] >= START_YEAR]
    buys, filings, symcik = [], [], []
    cik2t = {c: t for t, c in t2cik.items() if t in tickers}
    lags = []
    for l in links:
        b = F.get(l)
        if b is None:
            continue
        z = zipfile.ZipFile(io.BytesIO(b))
        sub = tsv(z, "SUBMISSION.tsv", ["ACCESSION_NUMBER", "FILING_DATE", "DOCUMENT_TYPE",
                                        "ISSUERCIK", "ISSUERTRADINGSYMBOL"])
        sub = sub[sub["DOCUMENT_TYPE"] == "4"]
        sub["sym"] = sub["ISSUERTRADINGSYMBOL"].map(norm)
        sub["cik"] = sub["ISSUERCIK"].str.zfill(10)
        symcik.append(sub[["sym", "cik"]].drop_duplicates())
        sub["ticker"] = sub["cik"].map(cik2t)
        sub.loc[sub["ticker"].isna() & sub["sym"].isin(tickers), "ticker"] = sub["sym"]
        sub = sub[sub["ticker"].notna()]
        sub["filing_date"] = sec_date(sub["FILING_DATE"])
        filings.append(sub.groupby(["ticker", "filing_date"]).size().rename("n").reset_index())
        nd = tsv(z, "NONDERIV_TRANS.tsv")
        acq = next(c for c in nd.columns if "ACQUIRED_DISP" in c)
        nd = nd[(nd["TRANS_CODE"] == "P") & (nd[acq] == "A")][["ACCESSION_NUMBER", "TRANS_DATE"]]
        own = tsv(z, "REPORTINGOWNER.tsv", ["ACCESSION_NUMBER", "RPTOWNERCIK"])
        m = nd.merge(sub[["ACCESSION_NUMBER", "ticker", "filing_date"]], on="ACCESSION_NUMBER") \
            .merge(own, on="ACCESSION_NUMBER")
        m["trans_date"] = sec_date(m["TRANS_DATE"])
        buys.append(m[["ticker", "filing_date", "RPTOWNERCIK", "trans_date", "ACCESSION_NUMBER"]]
                    .rename(columns={"RPTOWNERCIK": "owner_cik"}))
        lags.append((m["filing_date"] - m["trans_date"]).dt.days.dropna())
        print("form4", l.split("/")[-1], len(sub), len(m), flush=True)
    b = pd.concat(buys, ignore_index=True).drop_duplicates()
    f = pd.concat(filings, ignore_index=True).groupby(["ticker", "filing_date"])["n"].sum() \
        .reset_index()
    b.to_csv(out / "form4_buys.csv.gz", index=False)
    f.to_csv(out / "form4_filings.csv.gz", index=False)
    lag = pd.concat(lags) if lags else pd.Series(dtype=float)
    sc = pd.concat(symcik).drop_duplicates()
    return b, f, lag, sc


# ---------------------------------------------------------------- CUSIP <-> ticker (FTD)
def cusip_map(F, tickers, t2cik, symcik):
    links = [l for l in F.links("ftd") if (years_in(l.split("/")[-1]) or [0])[0] >= START_YEAR]
    rows = []
    for l in links:
        b = F.get(l)
        if b is None:
            continue
        z = zipfile.ZipFile(io.BytesIO(b))
        with z.open(z.namelist()[0]) as f:
            d = pd.read_csv(f, sep="|", dtype=str, usecols=[1, 2], encoding="latin-1",
                            on_bad_lines="skip")
        d.columns = ["cusip", "sym"]
        rows.append(d.dropna().drop_duplicates())
    ftd = pd.concat(rows).drop_duplicates()
    ftd["sym"] = ftd["sym"].map(norm)
    # symbol -> study ticker: same symbol, or any symbol the issuer (CIK) filed Form 4 under
    cik_of = {t: t2cik.get(t) for t in tickers}
    syms_of_cik = symcik.groupby("cik")["sym"].apply(set).to_dict()
    sym2t = {}
    for t in tickers:
        sym2t.setdefault(t, t)
        for s in syms_of_cik.get(cik_of.get(t), set()):
            sym2t.setdefault(s, t)
    ftd["ticker"] = ftd["sym"].map(sym2t)
    m = ftd.dropna(subset=["ticker"])
    m = m[m["cusip"].str.len() == 9]
    return m[["cusip", "ticker", "sym"]].drop_duplicates(), len(ftd)


# ---------------------------------------------------------------- 13F
DEADLINE_DAYS = 45


def form13f(F, cmap, out):
    """Breadth per (ticker, report quarter Q), PREREG §4 F2. Only original 13F-HR filed by the
    45-day deadline count, so the value is fixed and public from deadline + 1 day on."""
    import numpy as np
    links = [l for l in F.links("form13f") if max(years_in(l.split("/")[-1]) or [0]) >= START_YEAR]
    c2t = dict(zip(cmap["cusip"], cmap["ticker"]))
    tick = sorted(set(c2t.values()))
    tidx = {t: k for k, t in enumerate(tick)}
    fidx, codes, filers, lags = {}, {}, {}, []
    for l in links:
        b = F.get(l)
        if b is None:
            continue
        z = zipfile.ZipFile(io.BytesIO(b))
        sub = tsv(z, "SUBMISSION.tsv", ["ACCESSION_NUMBER", "FILING_DATE", "SUBMISSIONTYPE",
                                        "CIK", "PERIODOFREPORT"])
        sub = sub[sub["SUBMISSIONTYPE"] == "13F-HR"].copy()
        sub["filing_date"] = sec_date(sub["FILING_DATE"])
        sub["period"] = sec_date(sub["PERIODOFREPORT"])
        sub = sub.dropna(subset=["filing_date", "period"])
        lags.append((sub["filing_date"] - sub["period"]).dt.days)
        sub = sub[(sub["filing_date"] <= sub["period"] + pd.Timedelta(days=DEADLINE_DAYS)) &
                  (sub["period"].dt.year >= START_YEAR - 1)]
        for c in sub["CIK"].unique():
            fidx.setdefault(c, len(fidx))
        sub["f"] = sub["CIK"].map(fidx)
        for per, g in sub.groupby("period"):
            filers.setdefault(per, set()).update(g["f"].tolist())
        a2 = sub.set_index("ACCESSION_NUMBER")[["f", "period"]]
        n = 0
        with z.open(member(z, "INFOTABLE.tsv")) as fh:
            for ch in pd.read_csv(fh, sep="\t", dtype=str, quoting=3, on_bad_lines="skip",
                                  usecols=["ACCESSION_NUMBER", "CUSIP", "SSHPRNAMTTYPE",
                                           "PUTCALL"], chunksize=1_000_000):
                ch = ch[(ch["SSHPRNAMTTYPE"] == "SH") & ch["PUTCALL"].isna()]
                ch = ch.assign(t=ch["CUSIP"].str.upper().str.strip().map(c2t)).dropna(subset=["t"])
                ch = ch.join(a2, on="ACCESSION_NUMBER", how="inner")
                if not len(ch):
                    continue
                code = ch["f"].astype("int64").values * 4096 + ch["t"].map(tidx).astype("int64").values
                for per, cc in pd.Series(code).groupby(ch["period"].values):
                    codes.setdefault(per, []).append(np.unique(cc.values))
                n += len(ch)
        print("13f", l.split("/")[-1], len(sub), n, flush=True)
    periods = sorted(codes)
    hold = {p: np.unique(np.concatenate(codes[p])) for p in periods}
    rows = []
    for k in range(1, len(periods)):
        q, q1 = periods[k], periods[k - 1]
        if (q - q1).days > 100:
            continue
        common = np.array(sorted(filers.get(q, set()) & filers.get(q1, set())), dtype="int64")
        cq, cq1 = hold[q], hold[q1]
        mq = np.isin(cq // 4096, common)
        mq1 = np.isin(cq1 // 4096, common)
        hq = np.bincount(cq[mq] % 4096, minlength=len(tick))
        hq1 = np.bincount(cq1[mq1] % 4096, minlength=len(tick))
        usable = q + pd.Timedelta(days=DEADLINE_DAYS + 1)
        for t, i in tidx.items():
            if hq[i] or hq1[i]:
                rows.append(dict(ticker=t, period=q.date(), usable_from=usable.date(),
                                 holders_q=int(hq[i]), holders_q1=int(hq1[i]),
                                 common_filers=int(len(common))))
    B = pd.DataFrame(rows)
    B["breadth_change"] = (B["holders_q"] - B["holders_q1"]) / B["holders_q1"].where(
        B["holders_q1"] > 0)
    B.to_csv(out / "f13_breadth.csv.gz", index=False)
    pf_ = pd.DataFrame([dict(period=p.date(), filers_by_deadline=len(filers.get(p, ())),
                             holding_pairs=int(len(hold[p]))) for p in periods])
    pf_.to_csv(out / "f13_periods.csv", index=False)
    return B, pf_, pd.concat(lags) if lags else pd.Series(dtype=float)


def describe(s):
    s = s.dropna()
    if not len(s):
        return {}
    q = s.quantile([.01, .5, .9, .99]).round(1).to_dict()
    return dict(n=int(len(s)), min=float(s.min()), p01=q[.01], median=q[.5], p90=q[.9],
                p99=q[.99], max=float(s.max()), negative=int((s < 0).sum()))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--pit", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    F = Fetcher()
    tickers = study_tickers(a.pit)
    t2cik = ticker_cik(F)
    b, f, lag4, symcik = form4(F, tickers, t2cik, out)
    cmap, ftd_rows = cusip_map(F, tickers, t2cik, symcik)
    cmap.to_csv(out / "mapping.csv", index=False)
    H, filers, lag13 = form13f(F, cmap, out)
    lags = dict(form4_filing_minus_transaction_days=describe(lag4),
                f13_filing_minus_period_end_days=describe(lag13))
    (out / "lags.json").write_text(json.dumps(lags, indent=1))
    info = dict(study_tickers=len(tickers), tickers_with_cik=sum(t in t2cik for t in tickers),
                ftd_pairs=int(ftd_rows), cusips_mapped=int(len(cmap)),
                tickers_with_cusip=int(cmap["ticker"].nunique()),
                form4_buy_rows=int(len(b)), form4_filing_days=int(len(f)),
                f13_breadth_rows=int(len(H)), f13_periods=filers.to_dict("records"))
    (out / "sources.json").write_text(json.dumps(dict(info=info, downloads=F.log), indent=1, default=str))
    print(json.dumps(dict(info={k: v for k, v in info.items() if k != "f13_periods"}, lags=lags),
                     indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
