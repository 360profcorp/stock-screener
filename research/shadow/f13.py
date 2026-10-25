"""13F ownership breadth for the shadow books (PREREG_SHADOW.md §3).

Same rule as the PR #20 backtest (PREREG_INSTITUTIONAL.md §4 F2):
- count original 13F-HR filings whose period is Q and whose filing date is <= Q + 45 days;
- count holders among filers present in both Q and Q-1;
- shares only (SH), no options;
- the row is usable from Q + 46 days.

Forward quarters cannot wait for the SEC's quarterly data sets: the September quarter's set
comes out in December. They are therefore read from EDGAR itself:
- the full-index `form.idx` lists the 13F-HR filings;
- each filing's complete submission text gives the header (period, filing date) and the
  information table.

The `validate` command checks, before activation, that this EDGAR path gives the same
filer/CUSIP pairs as the data set for the 2026-06-30 quarter.

    python -m research.shadow.f13 seed     --period 2026-06-30   # data set -> pairs file
    python -m research.shadow.f13 validate --period 2026-06-30   # EDGAR vs data set
    python -m research.shadow.f13 ingest   --period 2026-09-30   # EDGAR -> pairs + breadth
"""
import argparse
import io
import json
import re
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from research.institutional.sec_data import Fetcher

ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "research" / "shadow" / "f13"
DEADLINE = 45
SEC = "https://www.sec.gov"


# ---------------------------------------------------------------- parsing (offline-tested)
def parse_form_idx(text):
    """EDGAR full-index form.idx (fixed width) -> form, cik, date, path."""
    rows, body = [], False
    for line in text.splitlines():
        if line.startswith("-----"):
            body = True
            continue
        if not body or not line.strip():
            continue
        m = re.match(r"^(\S+(?: \S+)*?)\s{2,}(.+?)\s{2,}(\d+)\s+(\d{4}-\d{2}-\d{2})\s+(\S+)\s*$", line)
        if m:
            rows.append(dict(form=m.group(1), cik=m.group(3), date=m.group(4), path=m.group(5)))
    return pd.DataFrame(rows, columns=["form", "cik", "date", "path"])


TAG = r"(?:\w+:)?"


def parse_submission(text):
    """Complete submission text of a 13F-HR -> header fields and share holdings (CUSIPs)."""
    def hdr(name):
        m = re.search(name + r":\s*(\S+)", text)
        return m.group(1) if m else None
    out = dict(type=hdr("CONFORMED SUBMISSION TYPE"), period=hdr("CONFORMED PERIOD OF REPORT"),
               filed=hdr("FILED AS OF DATE"), accession=hdr("ACCESSION NUMBER"))
    cik = re.search(r"FILER:.*?CENTRAL INDEX KEY:\s*(\d+)", text, re.S)
    out["cik"] = cik.group(1) if cik else None
    cus = []
    for blk in re.finditer(rf"<{TAG}infoTable\b[^>]*>(.*?)</{TAG}infoTable>", text, re.S | re.I):
        b = blk.group(1)
        c = re.search(rf"<{TAG}cusip>\s*([^<]+?)\s*</", b, re.I)
        t = re.search(rf"<{TAG}sshPrnamtType>\s*([^<]+?)\s*</", b, re.I)
        pc = re.search(rf"<{TAG}putCall>\s*([^<]*?)\s*</", b, re.I)
        if c and t and t.group(1).upper() == "SH" and not (pc and pc.group(1).strip()):
            cus.append(c.group(1).strip().upper())
    out["cusips"] = cus
    out["n_info"] = len(re.findall(rf"<{TAG}infoTable\b", text, re.I))
    return out


def breadth_rows(q, pq, fq, q1, pq1, fq1, c2t):
    """Breadth per ticker for quarter q vs q1. p*: set of (filer_cik, cusip); f*: filer sets;
    c2t: cusip -> ticker. Same definition as the backtest."""
    common = fq & fq1
    hq, hq1 = {}, {}
    for pairs, h in ((pq, hq), (pq1, hq1)):
        seen = set()
        for f, c in pairs:
            t = c2t.get(c)
            if t is not None and f in common and (f, t) not in seen:
                seen.add((f, t))
                h[t] = h.get(t, 0) + 1
    rows = []
    for t in sorted(set(hq) | set(hq1)):
        a, b = hq.get(t, 0), hq1.get(t, 0)
        rows.append(dict(ticker=t, period=pd.Timestamp(q).date(),
                         usable_from=(pd.Timestamp(q) + pd.Timedelta(days=DEADLINE + 1)).date(),
                         holders_q=a, holders_q1=b, common_filers=len(common),
                         breadth_change=(a - b) / b if b > 0 else np.nan))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- sources
def quarter_idx(F, day):
    p = pd.Timestamp(day).to_period("Q")
    b = F.get(f"{SEC}/Archives/edgar/full-index/{p.year}/QTR{p.quarter}/form.idx")
    return parse_form_idx(b.decode("latin-1")) if b else None


def edgar_pairs(F, period, cusips, log=None):
    """13F-HR (original) filings for `period` filed by period + 45 days, from EDGAR."""
    P = pd.Timestamp(period)
    last = P + pd.Timedelta(days=DEADLINE)
    idx = pd.concat([x for x in (quarter_idx(F, P), quarter_idx(F, last)) if x is not None])
    idx = idx.drop_duplicates("path")
    idx = idx[(idx["form"] == "13F-HR") & (pd.to_datetime(idx["date"]) >= P) &
              (pd.to_datetime(idx["date"]) <= last)]
    pairs, filers, bad = set(), set(), []
    for k, r in enumerate(idx.itertuples(index=False)):
        b = F.get(f"{SEC}/Archives/{r.path}", tries=4)
        if b is None:
            bad.append(r.path)
            continue
        s = parse_submission(b.decode("latin-1"))
        if s["type"] != "13F-HR" or s["period"] != P.strftime("%Y%m%d") or \
                pd.to_datetime(s["filed"], format="%Y%m%d") > last:
            continue
        f = str(int(s["cik"] or r.cik))
        filers.add(f)
        pairs |= {(f, c) for c in s["cusips"] if c in cusips}
        if k % 500 == 0:
            print("edgar", k, len(idx), len(filers), flush=True)
    if log is not None:
        log.update(index_rows=int(len(idx)), filers=len(filers), failed=bad)
    return pairs, filers


def dataset_pairs(F, periods, cusips, log=None):
    """The same from the SEC Form 13F data sets (as in the backtest), for several periods in
    one pass: {period: (pairs, filers)}."""
    Ps = [pd.Timestamp(p) for p in periods]
    html = F.get("/data-research/sec-markets-data/form-13f-data-sets").decode("utf-8", "replace")
    links = sorted(set(re.findall(r'href="([^"]+\.zip)"', html)))
    y0 = min(P.year for P in Ps)
    links = [l for l in links if any(int(y) >= y0 for y in re.findall(r"(20\d\d)", l.rsplit("/", 1)[-1]))]
    out = {P: (set(), set()) for P in Ps}
    used = []
    for l in links:
        b = F.get(l)
        if b is None:
            raise RuntimeError(f"13F data set {l} could not be downloaded")
        z = zipfile.ZipFile(io.BytesIO(b))
        nm = {n.rsplit("/", 1)[-1].upper(): n for n in z.namelist()}
        with z.open(nm["SUBMISSION.TSV"]) as fh:
            s = pd.read_csv(fh, sep="\t", dtype=str, quoting=3, on_bad_lines="skip")
        s = s[s["SUBMISSIONTYPE"] == "13F-HR"].copy()
        s["fd"] = pd.to_datetime(s["FILING_DATE"], format="%d-%b-%Y", errors="coerce")
        s["pe"] = pd.to_datetime(s["PERIODOFREPORT"], format="%d-%b-%Y", errors="coerce")
        s = s[s["pe"].isin(Ps) & (s["fd"] <= s["pe"] + pd.Timedelta(days=DEADLINE))]
        if not len(s):
            continue
        used.append(l)
        a2 = {a: (str(int(c)), pe) for a, c, pe in zip(s["ACCESSION_NUMBER"], s["CIK"], s["pe"])}
        for f, pe in a2.values():
            out[pe][1].add(f)
        with z.open(nm["INFOTABLE.TSV"]) as fh:
            for ch in pd.read_csv(fh, sep="\t", dtype=str, quoting=3, on_bad_lines="skip",
                                  usecols=["ACCESSION_NUMBER", "CUSIP", "SSHPRNAMTTYPE", "PUTCALL"],
                                  chunksize=1_000_000):
                ch = ch[ch["ACCESSION_NUMBER"].isin(a2) & (ch["SSHPRNAMTTYPE"] == "SH") &
                        ch["PUTCALL"].isna()]
                cu = ch["CUSIP"].str.upper().str.strip()
                m = cu.isin(cusips)
                for acc, c in zip(ch["ACCESSION_NUMBER"][m], cu[m]):
                    f, pe = a2[acc]
                    out[pe][0].add((f, c))
        print("dataset", l.rsplit("/", 1)[-1], len(s), flush=True)
    if log is not None:
        log.update(zips=used, filers={str(P.date()): len(v[1]) for P, v in out.items()})
    return out


# ---------------------------------------------------------------- storage
def save_pairs(period, pairs, filers, source):
    DIR.mkdir(parents=True, exist_ok=True)
    p = pd.Timestamp(period).date()
    pd.DataFrame(sorted(pairs), columns=["filer", "cusip"]).to_csv(DIR / f"pairs_{p}.csv.gz", index=False)
    pd.DataFrame(sorted(filers), columns=["filer"]).to_csv(DIR / f"filers_{p}.csv.gz", index=False)
    meta = dict(period=str(p), source=source, pairs=len(pairs), filers=len(filers))
    (DIR / f"quarter_{p}.json").write_text(json.dumps(meta, indent=1))


def load_pairs(period):
    p = pd.Timestamp(period).date()
    a = pd.read_csv(DIR / f"pairs_{p}.csv.gz", dtype=str)
    f = pd.read_csv(DIR / f"filers_{p}.csv.gz", dtype=str)
    return set(zip(a["filer"], a["cusip"])), set(f["filer"])


def mapping():
    m = pd.read_csv(DIR / "mapping_forward.csv", dtype=str)
    return dict(zip(m["cusip"], m["ticker"]))


def latest_due(today):
    """Latest quarter whose breadth must be usable on `today` (period + 46 <= today)."""
    q = pd.Timestamp(today).to_period("Q")
    for k in range(0, 3):
        p = (q - k).end_time.normalize()
        if p + pd.Timedelta(days=DEADLINE + 1) <= pd.Timestamp(today):
            return p
    return None


def ingest(period, F=None):
    """Forward quarter from EDGAR: pairs file + breadth rows appended to breadth.csv."""
    F = F or Fetcher()
    P = pd.Timestamp(period)
    q1 = (P.to_period("Q") - 1).end_time.normalize()
    c2t = mapping()
    log = {}
    pq, fq = edgar_pairs(F, P, set(c2t), log)
    if log.get("failed"):
        raise RuntimeError(f"{len(log['failed'])} EDGAR filings could not be read: {log['failed'][:5]}")
    pq1, fq1 = load_pairs(q1)
    save_pairs(P, pq, fq, "edgar")
    rows = breadth_rows(P, pq, fq, q1, pq1, fq1, c2t)
    br = pd.read_csv(DIR / "breadth.csv")
    br = br[br["period"] != str(P.date())]
    pd.concat([br, rows]).to_csv(DIR / "breadth.csv", index=False)
    return dict(period=str(P.date()), rows=len(rows), **{k: v for k, v in log.items() if k != "failed"})


def compare_breadth(a, b):
    k = ["ticker", "period"]
    m = a.merge(b, on=k, how="outer", suffixes=("_a", "_b"), indicator=True)
    for c in ("holders_q", "holders_q1"):
        m[c + "_diff"] = (m[c + "_a"].fillna(0) - m[c + "_b"].fillna(0)).abs()
    bad = m[(m["_merge"] != "both") | (m["holders_q_diff"] > 0) | (m["holders_q1_diff"] > 0)]
    return dict(rows_a=int(len(a)), rows_b=int(len(b)), differing_rows=int(len(bad)),
                max_holders_q_diff=float(m["holders_q_diff"].max()) if len(m) else 0.0,
                max_breadth_change_diff=float((m["breadth_change_a"] - m["breadth_change_b"]).abs().max())
                if len(m) else 0.0,
                examples=bad.head(15)[k + ["holders_q_a", "holders_q_b", "holders_q1_a",
                                           "holders_q1_b"]].to_dict("records"))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["seed", "validate", "ingest"])
    ap.add_argument("--period", required=True)
    a = ap.parse_args(argv)
    F = Fetcher()
    c2t = mapping()
    P = pd.Timestamp(a.period)
    Q1 = (P.to_period("Q") - 1).end_time.normalize()
    if a.cmd == "seed":
        log = {}
        d = dataset_pairs(F, [P], set(c2t), log)
        save_pairs(P, *d[P], "sec-13f-data-set")
        print(json.dumps(dict(log, pairs=len(d[P][0])), indent=1, default=str))
    elif a.cmd == "validate":
        l1, l2 = {}, {}
        d = dataset_pairs(F, [Q1, P], set(c2t), l1)
        (pd2, fd2), (pd1, fd1) = d[P], d[Q1]
        pe, fe = edgar_pairs(F, P, set(c2t), l2)
        tick = lambda ps: {(f, c2t[c]) for f, c in ps}          # noqa: E731
        B_ds = breadth_rows(P, pd2, fd2, Q1, pd1, fd1, c2t)
        B_ed = breadth_rows(P, pe, fe, Q1, pd1, fd1, c2t)
        tab = pd.read_csv(DIR / "breadth.csv")
        tab = tab[tab["period"] == str(P.date())].copy()
        for x in (B_ds, B_ed):
            x["period"] = x["period"].astype(str)
        res = dict(period=str(P.date()), dataset=dict(l1, pairs=len(pd2)),
                   edgar=dict({k: v for k, v in l2.items() if k != "failed"},
                              failed=len(l2.get("failed", [])), pairs=len(pe)),
                   filers_only_dataset=len(fd2 - fe), filers_only_edgar=len(fe - fd2),
                   pairs_only_dataset=len(pd2 - pe), pairs_only_edgar=len(pe - pd2),
                   filer_ticker_only_dataset=len(tick(pd2) - tick(pe)),
                   filer_ticker_only_edgar=len(tick(pe) - tick(pd2)),
                   examples_only_dataset=sorted(pd2 - pe)[:20], examples_only_edgar=sorted(pe - pd2)[:20],
                   filer_examples_only_dataset=sorted(fd2 - fe)[:20],
                   filer_examples_only_edgar=sorted(fe - fd2)[:20],
                   breadth_dataset_vs_table=compare_breadth(B_ds, tab),
                   breadth_edgar_vs_dataset=compare_breadth(B_ed, B_ds))
        res["pass"] = bool(res["breadth_dataset_vs_table"]["differing_rows"] == 0 and
                           res["breadth_edgar_vs_dataset"]["differing_rows"] == 0 and
                           res["edgar"]["failed"] == 0)
        (DIR / f"validate_{P.date()}.json").write_text(json.dumps(res, indent=1, default=str))
        print(json.dumps(res, indent=1, default=str))
        return 0 if res["pass"] else 2
    else:
        print(json.dumps(ingest(a.period, F), indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
