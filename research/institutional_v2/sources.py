"""v2 sources (CORRECTION_V2.md). Official SEC files only; compact outputs for the mapping.

    python -m research.institutional_v2.sources --pit PIT_CSV --out DIR --cache CACHE

Outputs (DIR):
  study_symbols.json      PIT S&P 500 symbols since 2016 (historical symbols)
  ftd.csv.gz              fails-to-deliver rows (date, cusip, sym, desc, file) for study symbols
                          and for every CUSIP ever recorded under a study symbol (any symbol)
  f345_sub.csv.gz         Forms 3/4/5 submissions (acc, filing_date, doc_type, issuer_cik,
                          issuer_name, sym, zip) under study symbols or by their issuers
  f345_buys.csv.gz        open-market purchases (P, A) of original Forms 4 in those submissions
  lists13f.csv.gz         Official 13(f) List rows (list, cusip, name, desc) for those CUSIPs
  edgar_names.json        EDGAR name and dated former names of those issuers
  f13_filings.csv.gz      every original 13F-HR filed by period + 45 days (acc, cik, filing_date,
                          period, zip), one row per accession
  f13_hold.npz            share holdings of those CUSIPs: acc index, cusip index (+ tables)
  sources.json            every download (url, bytes, sha256)
"""
import argparse
import hashlib
import io
import json
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from research.institutional.sec_data import PAGES, Fetcher   # HTTP + page names

DEADLINE = 45
START = 2016


def nsym(s):
    return str(s).strip().upper().replace(".", "-").replace("/", "-")


def sdate(s):
    return pd.to_datetime(s, format="%d-%b-%Y", errors="coerce")


def member(z, base):
    for n in z.namelist():
        if n.rsplit("/", 1)[-1].upper() == base.upper():
            return n
    raise KeyError(base)


def links(F, page, start=START):
    out = []
    for l in F.links(page):
        ys = [int(y) for y in re.findall(r"(20\d\d)", l.rsplit("/", 1)[-1])]
        if ys and max(ys) >= start:
            out.append(l)
    return out


def cached(F, url, cache):
    p = Path(cache) / url.rsplit("/", 1)[-1]
    if p.exists():
        return p.read_bytes()
    b = F.get(url)
    if b is None:
        raise RuntimeError(f"download failed: {url}")
    p.write_bytes(b)
    return b


def study_symbols(pit_csv):
    df = pd.read_csv(pit_csv)
    df = df[pd.to_datetime(df["date"]) >= f"{START}-01-01"]
    out = set()
    for s in df["tickers"]:
        out |= {nsym(t) for t in str(s).split(",") if t.strip()}
    return sorted(out)


def ftd(F, syms, cache):
    ls = [l for l in links(F, "ftd")]
    frames = []
    for l in ls:
        z = zipfile.ZipFile(io.BytesIO(cached(F, l, cache)))
        with z.open(z.namelist()[0]) as f:
            d = pd.read_csv(f, sep="|", dtype=str, usecols=[0, 1, 2, 4], encoding="latin-1",
                            on_bad_lines="skip")
        d.columns = ["date", "cusip", "sym", "desc"]
        d = d.dropna(subset=["date", "cusip", "sym"])
        d["cusip"] = d["cusip"].str.strip().str.upper()
        d["sym"] = d["sym"].map(nsym)
        d["date"] = pd.to_datetime(d["date"], format="%Y%m%d", errors="coerce")
        d["file"] = l.rsplit("/", 1)[-1]
        frames.append(d.dropna(subset=["date"]))
    A = pd.concat(frames, ignore_index=True)
    C = set(A.loc[A["sym"].isin(syms) & (A["cusip"].str.len() == 9), "cusip"])
    keep = A[A["sym"].isin(syms) | A["cusip"].isin(C)].drop_duplicates(["date", "cusip", "sym"])
    return keep.sort_values(["cusip", "date"]), sorted(C), len(ls)


def f345(F, syms, cache):
    ls = links(F, "form345")
    subs = []
    for l in ls:
        z = zipfile.ZipFile(io.BytesIO(cached(F, l, cache)))
        with z.open(member(z, "SUBMISSION.tsv")) as f:
            s = pd.read_csv(f, sep="\t", dtype=str, quoting=3, on_bad_lines="skip",
                            usecols=lambda c: c in {"ACCESSION_NUMBER", "FILING_DATE", "DOCUMENT_TYPE",
                                                    "ISSUERCIK", "ISSUERNAME", "ISSUERTRADINGSYMBOL"})
        s["sym"] = s["ISSUERTRADINGSYMBOL"].map(nsym)
        s["zip"] = l.rsplit("/", 1)[-1]
        subs.append(s)
        print("f345", s["zip"].iloc[0] if len(s) else l, len(s), flush=True)
    A = pd.concat(subs, ignore_index=True)
    A["issuer_cik"] = A["ISSUERCIK"].str.strip().str.lstrip("0")
    K = set(A.loc[A["sym"].isin(syms), "issuer_cik"])
    S = A[A["sym"].isin(syms) | A["issuer_cik"].isin(K)].rename(columns={
        "ACCESSION_NUMBER": "acc", "FILING_DATE": "filing_date", "DOCUMENT_TYPE": "doc_type",
        "ISSUERNAME": "issuer_name"})[["acc", "filing_date", "doc_type", "issuer_cik", "issuer_name", "sym", "zip"]]
    S["filing_date"] = sdate(S["filing_date"])
    acc4 = set(S.loc[S["doc_type"] == "4", "acc"])
    buys = []
    for l in ls:
        z = zipfile.ZipFile(io.BytesIO(cached(F, l, cache)))
        with z.open(member(z, "NONDERIV_TRANS.tsv")) as f:
            nd = pd.read_csv(f, sep="\t", dtype=str, quoting=3, on_bad_lines="skip")
        acq = next(c for c in nd.columns if "ACQUIRED_DISP" in c)
        nd = nd[(nd["TRANS_CODE"] == "P") & (nd[acq] == "A") & nd["ACCESSION_NUMBER"].isin(acc4)]
        with z.open(member(z, "REPORTINGOWNER.tsv")) as f:
            ow = pd.read_csv(f, sep="\t", dtype=str, quoting=3, on_bad_lines="skip",
                             usecols=["ACCESSION_NUMBER", "RPTOWNERCIK"])
        m = nd[["ACCESSION_NUMBER", "TRANS_DATE"]].merge(ow, on="ACCESSION_NUMBER")
        buys.append(m.rename(columns={"ACCESSION_NUMBER": "acc", "TRANS_DATE": "trans_date",
                                      "RPTOWNERCIK": "owner_cik"}))
    B = pd.concat(buys, ignore_index=True).drop_duplicates()
    B["trans_date"] = sdate(B["trans_date"])
    return S.drop_duplicates("acc"), B, sorted(K), len(ls)


LIST_RE = re.compile(r"^\s*([0-9A-Z]{6})\s([0-9A-Z]{2})\s([0-9A-Z])\s+(\*\s+)?(.+?)\s*$")


def parse_13f_list(text):
    rows = []
    for line in text.splitlines():
        m = LIST_RE.match(line)
        if not m:
            continue
        rest = re.split(r"\s{2,}", m.group(5).strip())
        rows.append(dict(cusip=m.group(1) + m.group(2) + m.group(3), name=rest[0],
                         desc=rest[1] if len(rest) > 1 else ""))
    return pd.DataFrame(rows, columns=["cusip", "name", "desc"])


def lists13f(F, cusips):
    found = set()
    for p in ("/rules-regulations/staff-guidance/official-list-section-13f-securities",
              "/divisions/investment/13flists.htm"):
        h = F.get(p)
        if h:
            found |= set(re.findall(r'href="([^"]*13flist(20\d\d)q([1-4])\.pdf)"', h.decode("utf-8", "replace")))
    by = {(int(y), int(k)): u for u, y, k in found}
    out, log = [], []
    for y in range(2015, 2027):
        for k in range(1, 5):
            b, used = None, None
            for u in ([by[(y, k)]] if (y, k) in by else []) + [f"/files/investment/13flist{y}q{k}.pdf",
                                                              f"/divisions/investment/13f/13flist{y}q{k}.pdf"]:
                b = F.get(u, tries=2)
                if b and b[:4] == b"%PDF":
                    used = u
                    break
                b = None
            if b is None:
                log.append(dict(list=f"{y}q{k}", status="missing"))
                continue
            with tempfile.TemporaryDirectory() as d:
                (Path(d) / "a.pdf").write_bytes(b)
                subprocess.run(["pdftotext", "-layout", str(Path(d) / "a.pdf"), str(Path(d) / "a.txt")], check=True)
                df = parse_13f_list((Path(d) / "a.txt").read_text(errors="replace"))
            n_all = len(df)
            df = df[df["cusip"].isin(cusips)].assign(list=f"{y}q{k}", url=used)
            out.append(df)
            log.append(dict(list=f"{y}q{k}", status="ok", rows=n_all, study_cusips=len(df), url=used))
    return pd.concat(out, ignore_index=True), log


def edgar_names(F, ciks):
    out = {}
    for c in ciks:
        b = F.get(f"https://data.sec.gov/submissions/CIK{str(c).zfill(10)}.json", tries=3)
        if b:
            j = json.loads(b)
            out[c] = dict(name=j.get("name"), formerNames=j.get("formerNames") or [])
    return out


def f13(F, cusips, cache):
    cidx = {c: i for i, c in enumerate(cusips)}
    filings, accs, cus, seen = [], [], [], {}
    for l in links(F, "form13f"):
        b = F.get(l)
        if b is None:
            raise RuntimeError(f"download failed: {l}")
        z = zipfile.ZipFile(io.BytesIO(b))
        with z.open(member(z, "SUBMISSION.tsv")) as f:
            s = pd.read_csv(f, sep="\t", dtype=str, quoting=3, on_bad_lines="skip",
                            usecols=["ACCESSION_NUMBER", "FILING_DATE", "SUBMISSIONTYPE", "CIK", "PERIODOFREPORT"])
        s = s[s["SUBMISSIONTYPE"] == "13F-HR"].copy()
        s["filing_date"], s["period"] = sdate(s["FILING_DATE"]), sdate(s["PERIODOFREPORT"])
        s = s.dropna(subset=["filing_date", "period"])
        s = s[((s["filing_date"] - s["period"]).dt.days <= DEADLINE) & (s["period"] >= "2015-01-01")]
        s = s[~s["ACCESSION_NUMBER"].isin(seen)]
        base = len(seen)
        for k, a in enumerate(s["ACCESSION_NUMBER"]):
            seen[a] = base + k
        s["zip"] = l.rsplit("/", 1)[-1]
        filings.append(s[["ACCESSION_NUMBER", "CIK", "filing_date", "period", "zip"]])
        with z.open(member(z, "INFOTABLE.tsv")) as fh:
            for ch in pd.read_csv(fh, sep="\t", dtype=str, quoting=3, on_bad_lines="skip",
                                  usecols=["ACCESSION_NUMBER", "CUSIP", "SSHPRNAMTTYPE", "PUTCALL"],
                                  chunksize=1_000_000):
                ch = ch[(ch["SSHPRNAMTTYPE"] == "SH") & ch["PUTCALL"].isna()]
                c = ch["CUSIP"].str.upper().str.strip().map(cidx)
                a = ch["ACCESSION_NUMBER"].map(seen)
                m = c.notna() & a.notna() & (a >= base)
                accs.append(a[m].astype("int32").values)
                cus.append(c[m].astype("int16").values)
        print("13f", s["zip"].iloc[0] if len(s) else l, len(s), flush=True)
    Fl = pd.concat(filings, ignore_index=True).rename(columns={"ACCESSION_NUMBER": "acc", "CIK": "cik"})
    Fl["cik"] = Fl["cik"].str.strip().str.lstrip("0")
    a, c = np.concatenate(accs), np.concatenate(cus)
    code = np.unique(a.astype("int64") * 4096 + c)
    return Fl, (code // 4096).astype("int32"), (code % 4096).astype("int16")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--pit", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache", required=True)
    a = ap.parse_args(argv)
    out, cache = Path(a.out), Path(a.cache)
    out.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    F = Fetcher()
    syms = study_symbols(a.pit)
    (out / "study_symbols.json").write_text(json.dumps(syms))
    D, C, nftd = ftd(F, set(syms), cache)
    if len(C) >= 4096:
        raise RuntimeError(f"{len(C)} CUSIPs: index width exceeded")
    D.to_csv(out / "ftd.csv.gz", index=False)
    print("ftd files", nftd, "rows", len(D), "cusips", len(C), flush=True)
    S, B, K, n345 = f345(F, set(syms), cache)
    S.to_csv(out / "f345_sub.csv.gz", index=False)
    B.to_csv(out / "f345_buys.csv.gz", index=False)
    L, llog = lists13f(F, set(C))
    L.to_csv(out / "lists13f.csv.gz", index=False)
    (out / "edgar_names.json").write_text(json.dumps(edgar_names(F, K)))
    Fl, acc_i, cus_i = f13(F, C, cache)
    Fl.to_csv(out / "f13_filings.csv.gz", index=False)
    np.savez_compressed(out / "f13_hold.npz", acc=acc_i, cusip=cus_i, cusips=np.array(C))
    info = dict(study_symbols=len(syms), ftd_files=nftd, ftd_rows=int(len(D)), cusips=len(C),
                f345_files=n345, f345_rows=int(len(S)), purchases=int(len(B)), issuers=len(K),
                lists=llog, f13_filings=int(len(Fl)), f13_holding_rows=int(len(acc_i)))
    (out / "sources.json").write_text(json.dumps(dict(info=info, downloads=F.log), indent=1, default=str))
    print(json.dumps({k: v for k, v in info.items() if k != "lists"}, indent=1))
    print("lists missing:", [x["list"] for x in llog if x["status"] != "ok"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
