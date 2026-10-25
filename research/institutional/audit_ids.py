"""Independent audit of the PR #20 SEC tables (AUDIT_PLAN.md).

    python -m research.institutional.audit_ids --pit PIT_CSV --sec BUILD_DIR \
        --features RUN_DIR --out OUT_DIR

Separate implementation: only the HTTP fetcher is shared with sec_data.py. Extra sources the
build did not use: Official Lists of Section 13(f) Securities (CUSIP -> issuer name per
quarter), EDGAR company submissions (CIK -> dated names), EDGAR filing index pages (filing
date and acceptance time).
"""
import argparse
import io
import json
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from research.institutional.sec_data import PAGES, Fetcher   # HTTP + page names only

DEADLINE = 45
F2_MAX_AGE = 120
F1_DAYS = 90
SEED = 20261025
STOPWORDS = {"INC", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED", "PLC", "LLC", "LP",
             "L", "P", "HLDGS", "HLDG", "HOLDINGS", "HOLDING", "GROUP", "GRP", "THE", "NEW", "CL",
             "CLASS", "A", "B", "C", "COM", "SHS", "ORD", "NV", "N", "V", "SA", "S", "AG", "SE",
             "DEL", "INCORPORATED", "TR", "TRUST", "INTL", "INTERNATIONAL", "CORPORATIO", "CORPORAT",
             "COS", "COMPANIES", "AND", "OF", "DE", "MD", "PA", "NY", "NJ", "OH", "IN", "TX", "VA",
             "INC.", "&", "THE"}


# ---------------------------------------------------------------- small helpers
def nsym(s):
    return str(s).strip().upper().replace(".", "-").replace("/", "-")


def ncik(s):
    s = str(s).strip()
    return s.zfill(10) if s and s.lower() != "nan" else None


def sdate(s):
    return pd.to_datetime(s, format="%d-%b-%Y", errors="coerce")


def zmember(z, base):
    for n in z.namelist():
        if n.rsplit("/", 1)[-1].upper() == base.upper():
            return n
    raise KeyError(base)


def ztsv(z, base, cols):
    with z.open(zmember(z, base)) as f:
        return pd.read_csv(f, sep="\t", dtype=str, usecols=lambda c: c in cols, quoting=3,
                           on_bad_lines="skip", low_memory=False)


def name_tokens(s):
    s = re.sub(r"[^A-Z0-9 ]", " ", str(s).upper())
    return [t for t in s.split() if t not in STOPWORDS]


def names_match(a, b):
    """Same issuer name? Tolerates the 13(f) list's truncation and suffix noise."""
    ta, tb = name_tokens(a), name_tokens(b)
    if not ta or not tb:
        return False
    if ta[0] == tb[0] or ta[0].startswith(tb[0]) or tb[0].startswith(ta[0]):
        if min(len(ta[0]), len(tb[0])) >= 3:
            return True
    jac = len(set(ta) & set(tb)) / len(set(ta) | set(tb))
    if jac >= 0.5:
        return True
    ja, jb = "".join(ta), "".join(tb)                         # "FEDEX" vs "FED EX"
    return len(ja) >= 5 and len(jb) >= 5 and (ja.startswith(jb[:8]) or jb.startswith(ja[:8]))


def qend(p):
    """Quarter end (Timestamp, normalized) of a Period('Q') or Timestamp."""
    p = p if isinstance(p, pd.Period) else pd.Timestamp(p).to_period("Q")
    return p.end_time.normalize()


# ---------------------------------------------------------------- parsers (tested offline)
LIST_RE = re.compile(r"^\s*([0-9A-Z]{6})\s([0-9A-Z]{2})\s([0-9A-Z])\s+(\*\s+)?(.+?)\s*$")


def parse_13f_list(text):
    """Official List of Section 13(f) Securities (pdftotext -layout) -> cusip, name, desc."""
    rows = []
    for line in text.splitlines():
        m = LIST_RE.match(line)
        if not m:
            continue
        rest = re.split(r"\s{2,}", m.group(5).strip())
        name = rest[0]
        desc = rest[1] if len(rest) > 1 else ""
        if len(rest) == 1:                    # single-spaced line: name + desc not separable
            name = rest[0]
        rows.append(dict(cusip=m.group(1) + m.group(2) + m.group(3), name=name, desc=desc))
    return pd.DataFrame(rows, columns=["cusip", "name", "desc"])


def parse_index(html):
    """EDGAR filing index page -> filing date, acceptance time, period of report."""
    def grab(label, pat):
        m = re.search(r'infoHead">\s*' + label + r'\s*</div>\s*<div class="info">\s*(' + pat + r')',
                      html)
        return m.group(1).strip() if m else None
    return dict(filing_date=grab("Filing Date", r"\d{4}-\d{2}-\d{2}"),
                accepted=grab("Accepted", r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"),
                period=grab("Period of Report", r"\d{4}-\d{2}-\d{2}"))


# ---------------------------------------------------------------- dated identity
class Identity:
    """Dominant issuer CIK per (trading symbol, quarter) from Forms 3/4/5."""

    def __init__(self, f4agg, cur_cik=None):
        self.cur = cur_cik or {}
        self.active = set(zip(f4agg["cik"], f4agg["q"]))
        a = f4agg.groupby(["sym", "q", "cik"])["n"].sum().reset_index()
        tot = a.groupby(["sym", "q"])["n"].transform("sum")
        a["share"] = a["n"] / tot
        a = a.sort_values(["sym", "q", "n", "cik"], ascending=[True, True, False, True])
        self.all = a
        top = a.drop_duplicates(["sym", "q"])
        self.top = {(s, q): (c, sh) for s, q, c, sh in zip(top["sym"], top["q"], top["cik"],
                                                           top["share"])}
        self.qs = {}
        for s, q in self.top:
            self.qs.setdefault(s, []).append(q)

    def cik(self, sym, q, reach=2):
        """Issuer CIK of a trading symbol in quarter q: the dominant Form 3/4/5 issuer under
        that symbol (nearest quarter within `reach`); else today's company_tickers CIK if
        that CIK filed in that period under any symbol (renamed symbol)."""
        if (sym, q) in self.top:
            return self.top[(sym, q)][0]
        for k in range(1, reach + 1):
            for qq in (q - k, q + k):
                if (sym, qq) in self.top:
                    return self.top[(sym, qq)][0]
        c = self.cur.get(sym)
        if c and any((c, q + k) in self.active for k in range(-reach, reach + 1)):
            return c
        return None


def cik_names(cik, edgar, f4names, p):
    """Names of a CIK valid around period p (EDGAR current/former names + Form 4 issuer names)."""
    out = set()
    e = edgar.get(cik)
    lo, hi = p - pd.Timedelta(days=200), p + pd.Timedelta(days=200)
    if e:
        former = e.get("formerNames") or []
        last_to = None
        for f in former:
            fr = pd.to_datetime(f.get("from"), errors="coerce", utc=True)
            to = pd.to_datetime(f.get("to"), errors="coerce", utc=True)
            fr = fr.tz_localize(None) if pd.notna(fr) else pd.Timestamp.min
            to = to.tz_localize(None) if pd.notna(to) else pd.Timestamp.max
            last_to = max(last_to, to) if last_to is not None else to
            if fr <= hi and to >= lo:
                out.add(f["name"])
        if last_to is None or last_to <= hi:
            out.add(e.get("name", ""))
    q = p.to_period("Q")
    for qq in (q - 1, q, q + 1):
        out |= f4names.get((cik, qq), set())
    return {n for n in out if n}


def validity(mapping, periods, ident, ftd_q, list13, edgar, f4names):
    """Status of each (cusip, ticker) for each 13F report period: ftd / name / conflict /
    unverified (AUDIT_PLAN.md A)."""
    ftd_by_c = {}
    for c, s, q in zip(ftd_q["cusip"], ftd_q["sym"], ftd_q["q"]):
        ftd_by_c.setdefault(c, []).append((q, s))
    lists = sorted(list13)
    rows = []
    for c, t in mapping[["cusip", "ticker"]].drop_duplicates().itertuples(index=False):
        recs = ftd_by_c.get(c, [])
        for p in periods:
            q = p.to_period("Q")
            tcik = ident.cik(t, q)
            syms = {s for qq, s in recs if abs((qq - q).n) <= 2}
            fciks = {ident.cik(s, q) for s in syms} - {None}
            if tcik is not None and tcik in fciks:
                st = "ftd"
            elif tcik is None and t in syms:
                st = "ftd"
            else:
                n13 = None
                for lp in sorted(lists, key=lambda x: abs((x - p).days))[:3]:
                    if abs((lp - p).days) <= 100 and c in list13[lp]:
                        n13 = list13[lp][c]
                        break
                tn = cik_names(tcik, edgar, f4names, p) if tcik else set()
                if n13 and any(names_match(n13, x) for x in tn):
                    st = "name"
                elif fciks and tcik not in fciks:
                    st = "conflict"
                else:
                    st = "unverified"
            rows.append(dict(cusip=c, ticker=t, period=p, status=st, ticker_cik=tcik,
                             ftd_syms=",".join(sorted(syms)), ftd_ciks=",".join(sorted(fciks))))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 13F holders
def breadth(pairs, filers, nf_mult, assign, ntick, tickers):
    """Holders among filers present in both quarters (PREREG §4 F2). assign(period) ->
    array cusip_idx -> ticker_idx or -1."""
    periods = sorted(pairs)
    rows = []
    for k in range(1, len(periods)):
        q, q1 = periods[k], periods[k - 1]
        if (q - q1).days > 100:
            continue
        common = np.array(sorted(filers.get(q, set()) & filers.get(q1, set())), dtype="int64")
        hs = []
        for p in (q, q1):
            code = pairs[p]
            f, c = code // nf_mult, code % nf_mult
            t = assign(p)[c]
            m = (t >= 0) & np.isin(f, common)
            u = np.unique(f[m] * ntick + t[m])
            hs.append(np.bincount(u % ntick, minlength=ntick))
        for i in np.nonzero(hs[0] + hs[1])[0]:
            rows.append(dict(ticker=tickers[i], period=q, usable_from=q + pd.Timedelta(days=DEADLINE + 1),
                             holders_q=int(hs[0][i]), holders_q1=int(hs[1][i]),
                             common_filers=int(len(common))))
    B = pd.DataFrame(rows, columns=["ticker", "period", "usable_from", "holders_q", "holders_q1",
                                    "common_filers"])
    B["breadth_change"] = (B["holders_q"] - B["holders_q1"]) / B["holders_q1"].where(B["holders_q1"] > 0)
    return B


def f2_pit(rows, br):
    """Independent point-in-time F2 for (ticker, signal_date) rows: latest quarter with
    usable_from <= day, at most 120 days old; missing -> 0. Returns F2 and the period used."""
    br = br.sort_values(["ticker", "usable_from"])
    by = {t: (g["usable_from"].values.astype("datetime64[ns]"), g["breadth_change"].values,
              g["period"].values) for t, g in br.groupby("ticker")}
    f2, used, uf = [], [], []
    for t, d in zip(rows["ticker"], pd.to_datetime(rows["signal_date"])):
        x = by.get(t)
        v, p, u = 0.0, pd.NaT, pd.NaT
        if x is not None:
            k = np.searchsorted(x[0], np.datetime64(d), side="right") - 1
            if k >= 0 and (d - pd.Timestamp(x[0][k])).days <= F2_MAX_AGE:
                v = float(x[1][k]) if pd.notna(x[1][k]) else 0.0
                p, u = pd.Timestamp(x[2][k]), pd.Timestamp(x[0][k])
        f2.append(v)
        used.append(p)
        uf.append(u)
    return np.array(f2), used, uf


def order_changes(rows, f2a, f2b):
    """Days whose BR same-day order (F2 desc, RS desc, ticker) differs between two F2s."""
    d = rows[["ticker", "signal_date", "rs"]].copy()
    d["a"], d["b"] = f2a, f2b
    out = []
    for day, g in d.groupby("signal_date"):
        if len(g) < 2:
            continue
        oa = list(g.sort_values(["a", "rs", "ticker"], ascending=[False, False, True])["ticker"])
        ob = list(g.sort_values(["b", "rs", "ticker"], ascending=[False, False, True])["ticker"])
        if oa != ob:
            first = next(k for k in range(len(oa)) if oa[k] != ob[k])
            out.append(dict(signal_date=day, candidates=len(g), first_diff_rank=first + 1,
                            top3_build=",".join(oa[:3]), top3_audit=",".join(ob[:3])))
    return pd.DataFrame(out, columns=["signal_date", "candidates", "first_diff_rank",
                                      "top3_build", "top3_audit"])


# ---------------------------------------------------------------- downloads (network)
def links(F, page, start=2016):
    out = []
    for l in F.links(page):
        ys = [int(y) for y in re.findall(r"(20\d\d)", l.rsplit("/", 1)[-1])]
        if ys and max(ys) >= start:
            out.append(l)
    return out


def read_f345(F, buy_acc):
    agg, names, acc = [], [], []
    for l in links(F, "form345"):
        b = F.get(l)
        if b is None:
            print("MISSING", l, flush=True)
            continue
        z = zipfile.ZipFile(io.BytesIO(b))
        s = ztsv(z, "SUBMISSION.tsv", {"ACCESSION_NUMBER", "FILING_DATE", "DOCUMENT_TYPE",
                                      "ISSUERCIK", "ISSUERNAME", "ISSUERTRADINGSYMBOL"})
        s["date"] = sdate(s["FILING_DATE"])
        s = s.dropna(subset=["date"])
        s["q"] = s["date"].dt.to_period("Q")
        s["sym"] = s["ISSUERTRADINGSYMBOL"].map(nsym)
        s["cik"] = s["ISSUERCIK"].map(ncik)
        s = s[s["sym"].str.len().between(1, 6) & ~s["sym"].isin(["NONE", "N-A", "NA"])]
        agg.append(s.groupby(["sym", "q", "cik"]).size().rename("n").reset_index())
        names.append(s[["cik", "q", "ISSUERNAME"]].drop_duplicates())
        acc.append(s[s["ACCESSION_NUMBER"].isin(buy_acc)][["ACCESSION_NUMBER", "cik", "sym", "date"]])
        print("f345", l.rsplit("/", 1)[-1], len(s), flush=True)
    A = pd.concat(agg).groupby(["sym", "q", "cik"])["n"].sum().reset_index()
    N = pd.concat(names).drop_duplicates()
    f4names = {}
    for c, q, n in zip(N["cik"], N["q"], N["ISSUERNAME"]):
        f4names.setdefault((c, q), set()).add(n)
    return A, f4names, pd.concat(acc).drop_duplicates("ACCESSION_NUMBER")


def read_ftd(F):
    parts = []
    for l in links(F, "ftd"):
        b = F.get(l)
        if b is None:
            print("MISSING", l, flush=True)
            continue
        z = zipfile.ZipFile(io.BytesIO(b))
        with z.open(z.namelist()[0]) as f:
            d = pd.read_csv(f, sep="|", dtype=str, usecols=[0, 1, 2, 4], encoding="latin-1",
                            on_bad_lines="skip")
        d.columns = ["date", "cusip", "sym", "desc"]
        d["date"] = pd.to_datetime(d["date"], format="%Y%m%d", errors="coerce")
        d = d.dropna(subset=["date", "cusip", "sym"])
        d["cusip"] = d["cusip"].str.strip().str.upper()
        d["sym"] = d["sym"].map(nsym)
        d["q"] = d["date"].dt.to_period("Q")
        parts.append(d.groupby(["cusip", "sym", "q"]).agg(desc=("desc", "first")).reset_index())
    return pd.concat(parts).drop_duplicates(["cusip", "sym", "q"])


def read_13f_lists(F, cusips):
    pages = ["/rules-regulations/staff-guidance/official-list-section-13f-securities",
             "/divisions/investment/13flists.htm"]
    found = set()
    for p in pages:
        h = F.get(p)
        if h:
            found |= set(re.findall(r'href="([^"]*13flist(20\d\d)q([1-4])\.pdf)"',
                                    h.decode("utf-8", "replace")))
    by_q = {(int(y), int(k)): u for u, y, k in found}
    out, log = {}, []
    for y in range(2015, 2027):
        for k in range(1, 5):
            cands = ([by_q[(y, k)]] if (y, k) in by_q else []) + [
                f"/files/investment/13flist{y}q{k}.pdf",
                f"/divisions/investment/13f/13flist{y}q{k}.pdf"]
            b = None
            for u in cands:
                b = F.get(u, tries=2)
                if b and b[:4] == b"%PDF":
                    break
                b = None
            if b is None:
                log.append(dict(list=f"{y}q{k}", status="missing"))
                continue
            with tempfile.TemporaryDirectory() as d:
                (Path(d) / "a.pdf").write_bytes(b)
                subprocess.run(["pdftotext", "-layout", str(Path(d) / "a.pdf"), str(Path(d) / "a.txt")],
                               check=True)
                df = parse_13f_list((Path(d) / "a.txt").read_text(errors="replace"))
            p = qend(pd.Period(f"{y}Q{k}"))
            df = df[df["cusip"].isin(cusips)]
            out[p] = dict(zip(df["cusip"], df["name"]))
            log.append(dict(list=f"{y}q{k}", status="ok", mapped_cusips_listed=len(out[p])))
            print("13flist", y, k, len(df), flush=True)
    return out, log


def read_edgar(F, ciks):
    out = {}
    for c in sorted(ciks):
        b = F.get(f"https://data.sec.gov/submissions/CIK{c}.json", tries=3)
        if b:
            j = json.loads(b)
            out[c] = dict(name=j.get("name"), formerNames=j.get("formerNames"), tickers=j.get("tickers"))
    return out


def read_13f(F, cusips):
    cidx = {c: i for i, c in enumerate(sorted(cusips))}
    fidx, pairs, filers, counted, seen = {}, {}, {}, [], set()
    for l in links(F, "form13f"):
        b = F.get(l)
        if b is None:
            print("MISSING", l, flush=True)
            continue
        z = zipfile.ZipFile(io.BytesIO(b))
        s = ztsv(z, "SUBMISSION.tsv", {"ACCESSION_NUMBER", "FILING_DATE", "SUBMISSIONTYPE", "CIK",
                                      "PERIODOFREPORT"})
        s = s[s["SUBMISSIONTYPE"] == "13F-HR"].copy()
        s["fd"], s["period"] = sdate(s["FILING_DATE"]), sdate(s["PERIODOFREPORT"])
        s = s.dropna(subset=["fd", "period"])
        s = s[(s["fd"] - s["period"]).dt.days.le(DEADLINE) & (s["period"] >= "2015-01-01")]
        s = s[~s["ACCESSION_NUMBER"].isin(seen)]
        seen |= set(s["ACCESSION_NUMBER"])
        s["f"] = [fidx.setdefault(c, len(fidx)) for c in s["CIK"]]
        for p, g in s.groupby("period"):
            filers.setdefault(p, set()).update(g["f"])
        counted.append(s[["ACCESSION_NUMBER", "CIK", "fd", "period"]])
        a2 = s.set_index("ACCESSION_NUMBER")[["f", "period"]]
        with z.open(zmember(z, "INFOTABLE.tsv")) as fh:
            for ch in pd.read_csv(fh, sep="\t", dtype=str, quoting=3, on_bad_lines="skip",
                                  usecols=["ACCESSION_NUMBER", "CUSIP", "SSHPRNAMTTYPE", "PUTCALL"],
                                  chunksize=1_000_000):
                ch = ch[(ch["SSHPRNAMTTYPE"] == "SH") & ch["PUTCALL"].isna()]
                ch = ch.assign(c=ch["CUSIP"].str.upper().str.strip().map(cidx)).dropna(subset=["c"])
                ch = ch.join(a2, on="ACCESSION_NUMBER", how="inner")
                for p, g in ch.groupby("period"):
                    pairs.setdefault(p, []).append(
                        np.unique(g["f"].astype("int64").values * 4096 + g["c"].astype("int64").values))
        print("13f", l.rsplit("/", 1)[-1], len(s), flush=True)
    pairs = {p: np.unique(np.concatenate(v)) for p, v in pairs.items()}
    return pairs, filers, cidx, pd.concat(counted)


def check_index(F, rows, cik_col, acc_col):
    out = []
    for r in rows.itertuples(index=False):
        cik, acc = str(int(getattr(r, cik_col))), getattr(r, acc_col)
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{acc}-index.htm"
        b = F.get(url, tries=3)
        x = parse_index(b.decode("utf-8", "replace")) if b else dict(filing_date=None, accepted=None,
                                                                    period=None)
        out.append(dict(r._asdict(), url=url, **{"edgar_" + k: v for k, v in x.items()}))
    return pd.DataFrame(out)


# ---------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--pit", required=True)
    ap.add_argument("--sec", required=True)
    ap.add_argument("--features", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tables", required=True, help="corrected tables (artifact, not committed)")
    a = ap.parse_args(argv)
    out, tab = Path(a.out), Path(a.tables)
    out.mkdir(parents=True, exist_ok=True)
    tab.mkdir(parents=True, exist_ok=True)
    sec, fe = Path(a.sec), Path(a.features)
    F = Fetcher()
    S = {}

    mapping = pd.read_csv(sec / "mapping.csv", dtype=str)
    br_build = pd.read_csv(sec / "f13_breadth.csv.gz", parse_dates=["period", "usable_from"])
    buys = pd.read_csv(sec / "form4_buys.csv.gz", dtype={"owner_cik": str},
                       parse_dates=["filing_date", "trans_date"])
    feats = {st: pd.read_csv(fe / f"features_{st}.csv", parse_dates=["signal_date"])
             for st in ("breakout", "retest")}
    pit = pd.read_csv(a.pit)
    pit["date"] = pd.to_datetime(pit["date"])
    pit = pit[pit["date"] >= "2016-01-01"]
    member_q = {}
    for d, s in zip(pit["date"], pit["tickers"]):
        for t in str(s).split(","):
            if t.strip():
                member_q.setdefault(nsym(t), set()).add(d.to_period("Q"))
    tickers = sorted(member_q)

    # ---- downloads
    f4agg, f4names, buy_iss = read_f345(F, set(buys["ACCESSION_NUMBER"]))
    j_ = json.loads(F.get("https://www.sec.gov/files/company_tickers.json"))
    cur_cik = {nsym(v["ticker"]): str(v["cik_str"]).zfill(10) for v in j_.values()}
    ident = Identity(f4agg, cur_cik)
    ftd_q = read_ftd(F)
    cus = set(mapping["cusip"])
    pairs, filers, cidx, counted = read_13f(F, cus)
    periods = sorted(pairs)
    list13, list_log = read_13f_lists(F, cus)
    ciks = set()
    for t in tickers:
        ciks |= {c for (s, q), (c, _) in ident.top.items() if s == t}
    for s in set(ftd_q[ftd_q["cusip"].isin(cus)]["sym"]):
        ciks |= {ident.top[(s, q)][0] for q in ident.qs.get(s, [])}
    ciks |= {cur_cik[t] for t in tickers if t in cur_cik}
    edgar = read_edgar(F, ciks)
    S["sources"] = dict(f13_lists=list_log, edgar_ciks_requested=len(ciks), edgar_ciks_ok=len(edgar),
                        failed_downloads=[x for x in F.log if "status" in x][:50])

    # ---- A0 reproduction of the build's holders with the build's static mapping
    tick_m = sorted(set(mapping["ticker"]))
    tix = {t: k for k, t in enumerate(tick_m)}
    static = np.full(len(cidx), -1, dtype="int64")
    c2t = dict(zip(mapping["cusip"], mapping["ticker"]))        # same dict semantics as build
    for c, i in cidx.items():
        static[i] = tix[c2t[c]]
    B0 = breadth(pairs, filers, 4096, lambda p: static, len(tick_m), tick_m)
    k = ["ticker", "period"]
    cmp_ = br_build.merge(B0, on=k, how="outer", suffixes=("_build", "_audit"), indicator=True)
    mism = cmp_[(cmp_["_merge"] != "both") |
                (cmp_["holders_q_build"] != cmp_["holders_q_audit"]) |
                (cmp_["holders_q1_build"] != cmp_["holders_q1_audit"]) |
                (cmp_["common_filers_build"] != cmp_["common_filers_audit"])]
    mism.head(500).to_csv(out / "A0_reproduction_mismatches.csv", index=False)
    S["A0_reproduction"] = dict(build_rows=int(len(br_build)), audit_rows=int(len(B0)),
                                mismatched_rows=int(len(mism)),
                                usable_from_is_period_plus_46=bool(
                                    ((br_build["usable_from"] - br_build["period"]).dt.days == 46).all()))

    # ---- A1 ticker identity over time
    f4_by_cik = {}
    for (cc, _q), v in f4names.items():
        f4_by_cik.setdefault(cc, set()).update(v)

    def all_names(c):
        e = edgar.get(c) or {}
        n = {e.get("name") or ""} | {f["name"] for f in (e.get("formerNames") or [])}
        return {x for x in n | f4_by_cik.get(c, set()) if x}
    name_cache = {}

    def names_of(c):
        if c not in name_cache:
            name_cache[c] = all_names(c)
        return name_cache[c]
    idrows = []
    for t in tickers:
        qs = sorted(q for (s, q) in ident.top if s == t and q.year >= 2016)
        runs = []
        for q in qs:
            c = ident.top[(t, q)][0]
            if runs and runs[-1]["cik"] == c:
                runs[-1]["last"], runs[-1]["quarters"] = q, runs[-1]["quarters"] + 1
            else:
                runs.append(dict(cik=c, first=q, last=q, quarters=1))
        main_runs = [r for r in runs if r["quarters"] >= 2]
        seq = list(dict.fromkeys(r["cik"] for r in main_runs))
        if not qs:
            cls = "no Form 3/4/5 under this symbol"
        elif len(seq) <= 1:
            cls = "single issuer"
        else:
            linked = all(any(names_match(x, y) for x in names_of(a_) for y in names_of(b_))
                         for a_, b_ in zip(seq, seq[1:]))
            cls = "issuer CIK changed, names linked" if linked else "issuer CIK changed, names differ"
        cur = cur_cik.get(t)
        mq = sorted(member_q[t])
        idrows.append(dict(ticker=t, member_first=str(mq[0]), member_last=str(mq[-1]),
                           classification=cls, current_cik=cur,
                           current_cik_is_last_issuer=(cur == seq[-1]) if seq else None,
                           cik_runs=" | ".join(
                               f"{r['cik']} {r['first']}-{r['last']} "
                               f"({(edgar.get(r['cik']) or {}).get('name') or next(iter(names_of(r['cik'])), '')})"
                               for r in main_runs),
                           minor_ciks=len([r for r in runs if r["quarters"] < 2])))
    ID = pd.DataFrame(idrows)
    ID.to_csv(out / "A1_ticker_identity.csv", index=False)
    S["A1_identity"] = ID["classification"].value_counts().to_dict()

    # ---- A2 dated validity of every mapping row
    V = validity(mapping, periods, ident, ftd_q[ftd_q["cusip"].isin(cus)], list13, edgar, f4names)
    held = []                                                  # holders per (cusip, period)
    inv = {i: c for c, i in cidx.items()}
    for p in periods:
        code = pairs[p]
        cc = np.bincount(code % 4096, minlength=len(cidx))
        held += [dict(cusip=inv[i], period=p, holders=int(cc[i])) for i in np.nonzero(cc)[0]]
    H = pd.DataFrame(held)
    V = V.merge(H, on=["cusip", "period"], how="left").fillna({"holders": 0})
    V["member_quarter"] = [p.to_period("Q") in member_q.get(t, set()) or (p.to_period("Q") + 1) in
                           member_q.get(t, set()) for t, p in zip(V["ticker"], V["period"])]
    rel = V[(V["holders"] > 0)]
    S["A2_validity"] = dict(
        cusip_ticker_rows=int(mapping[["cusip", "ticker"]].drop_duplicates().shape[0]),
        holding_rows_by_status=rel["status"].value_counts().to_dict(),
        holder_weight_by_status=rel.groupby("status")["holders"].sum().astype(int).to_dict(),
        member_quarters_by_status=rel[rel["member_quarter"]]["status"].value_counts().to_dict())
    bad = rel[rel["status"].isin(["conflict", "unverified"])]
    bad.sort_values(["status", "holders"], ascending=[True, False]).to_csv(
        out / "A2_conflict_unverified.csv", index=False)
    sym_diff = mapping[mapping["sym"] != mapping["ticker"]]
    multi = mapping.groupby("cusip")["ticker"].nunique()
    S["A2_mapping"] = dict(rows=int(len(mapping)), symbol_differs_from_ticker=int(len(sym_diff)),
                           cusips_with_several_tickers=int((multi > 1).sum()))
    sym_diff.to_csv(out / "A2_symbol_differs.csv", index=False)
    mapping[mapping["cusip"].isin(multi[multi > 1].index)].to_csv(out / "A2_cusip_several_tickers.csv",
                                                                  index=False)

    # ---- A3 CUSIP reuse: several issuers over time
    cr = []
    fq = ftd_q[ftd_q["cusip"].isin(cus)]
    for c, g in fq.groupby("cusip"):
        iss = {ident.cik(s, q) for s, q in zip(g["sym"], g["q"])} - {None}
        nm = {list13[p][c] for p in list13 if c in list13[p]}
        distinct_names = []
        for n in nm:
            if not any(names_match(n, x) for x in distinct_names):
                distinct_names.append(n)
        if len(iss) > 1 or len(distinct_names) > 1:
            cr.append(dict(cusip=c, issuer_ciks=",".join(sorted(iss)), list_names=" | ".join(sorted(nm)),
                           syms=",".join(sorted(set(g["sym"]))), mapped_to=c2t.get(c)))
    CR = pd.DataFrame(cr, columns=["cusip", "issuer_ciks", "list_names", "syms", "mapped_to"])
    CR.to_csv(out / "A3_cusip_several_issuers.csv", index=False)
    S["A3_cusip_several_issuers"] = int(len(CR))

    # ---- A4 impact: dated mapping, strict and lenient
    rank_ = {"ftd": 0, "name": 1, "unverified": 2, "conflict": 3}
    best = {}
    for c, p, t, st_ in zip(V["cusip"], V["period"], V["ticker"], V["status"]):
        if (c, p) not in best or rank_[st_] < rank_[best[(c, p)][1]]:
            best[(c, p)] = (t, st_)
    S["A4_cusips_valid_for_several_tickers"] = int(
        V[V["status"].isin(["ftd", "name"])].groupby(["cusip", "period"])["ticker"].nunique().gt(1).sum())

    def dated(keep):
        cache = {}

        def f(p):
            if p not in cache:
                arr = np.full(len(cidx), -1, dtype="int64")
                for c, i in cidx.items():
                    t, st_ = best.get((c, p), (None, None))
                    if st_ in keep:
                        arr[i] = tix[t]
                cache[p] = arr
            return cache[p]
        return f
    Bs = breadth(pairs, filers, 4096, dated({"ftd", "name"}), len(tick_m), tick_m)
    Bl = breadth(pairs, filers, 4096, dated({"ftd", "name", "unverified"}), len(tick_m), tick_m)
    Bs.to_csv(tab / "f13_breadth_strict.csv.gz", index=False)
    Bl.to_csv(tab / "f13_breadth_lenient.csv.gz", index=False)
    S["A4_impact"] = {}
    S["B3_f2_recompute"] = {}
    for st, rows in feats.items():
        f2b, _, ufb = f2_pit(rows, br_build)
        diff = np.abs(f2b - rows["F2"].fillna(0).values) > 1e-12
        late = sum(1 for u, d in zip(ufb, rows["signal_date"]) if pd.notna(u) and u > d)
        S["B3_f2_recompute"][st] = dict(rows=int(len(rows)), differs_from_stored=int(diff.sum()),
                                        quarter_not_yet_public=int(late))
        res = {}
        for nm, Bx in (("strict", Bs), ("lenient", Bl)):
            f2x, _, ufx = f2_pit(rows, Bx)
            ch = np.abs(f2x - f2b) > 1e-12
            oc = order_changes(rows, f2b, f2x)
            oc.to_csv(out / f"A4_order_changes_{st}_{nm}.csv", index=False)
            big = np.abs(f2x - f2b) > 0.01
            res[nm] = dict(f2_changed=int(ch.sum()), f2_changed_by_more_than_1pt=int(big.sum()),
                           days=int(rows["signal_date"].nunique()),
                           days_with_br_order_change=int(len(oc)),
                           days_with_top3_change=int((oc["top3_build"] != oc["top3_audit"]).sum()) if len(oc) else 0)
            if nm == "strict":
                x = rows[["ticker", "signal_date", "rs", "F2"]].copy()
                x["F2_strict"] = f2x
                x[ch].to_csv(out / f"A4_f2_changes_{st}.csv", index=False)
        S["A4_impact"][st] = res

    # ---- A5 Form 4 issuer identity of the purchases used for F1
    j = buys.merge(buy_iss, on="ACCESSION_NUMBER", how="left")
    j["q"] = j["filing_date"].dt.to_period("Q")
    j["ticker_cik"] = [ident.cik(t, q) for t, q in zip(j["ticker"], j["q"])]
    j["ok"] = j["cik"] == j["ticker_cik"]
    S["A5_form4"] = dict(purchase_rows=int(len(j)), issuer_matches_dated_cik=int(j["ok"].sum()),
                         mismatched=int((~j["ok"]).sum()))
    j[~j["ok"]].to_csv(out / "A5_form4_mismatches.csv", index=False)

    # ---- B1 13F publication time vs EDGAR
    counted["usable_from"] = counted["period"] + pd.Timedelta(days=DEADLINE + 1)
    counted["margin"] = (counted["usable_from"] - counted["fd"]).dt.days
    rng = np.random.default_rng(SEED)
    samp = []
    for y, g in counted.groupby(counted["fd"].dt.year):
        samp.append(g.iloc[rng.choice(len(g), size=min(20, len(g)), replace=False)])
    samp.append(counted.sort_values(["margin", "ACCESSION_NUMBER"]).head(100))
    s13 = pd.concat(samp).drop_duplicates("ACCESSION_NUMBER")
    P13 = check_index(F, s13, "CIK", "ACCESSION_NUMBER")
    P13["edgar_filing_date"] = pd.to_datetime(P13["edgar_filing_date"])
    P13["edgar_accepted"] = pd.to_datetime(P13["edgar_accepted"])
    P13["ok_date"] = P13["edgar_filing_date"] == P13["fd"]
    P13["ok_period"] = pd.to_datetime(P13["edgar_period"]) == P13["period"]
    P13["ok_public"] = P13["edgar_accepted"] < P13["usable_from"]
    P13.to_csv(out / "B1_13f_edgar.csv", index=False)
    S["B1_13f"] = dict(sampled=int(len(P13)), fetched=int(P13["edgar_accepted"].notna().sum()),
                       filing_date_mismatch=int((~P13["ok_date"]).sum()),
                       period_mismatch=int((~P13["ok_period"]).sum()),
                       accepted_on_or_after_usable_from=int((~P13["ok_public"]).sum()),
                       min_margin_days=int(P13["margin"].min()))

    # ---- B2 Form 4 publication time vs EDGAR (purchases used by F1)
    use = []
    rows = pd.concat(feats.values())[["ticker", "signal_date"]].drop_duplicates()
    sd = {t: np.sort(g["signal_date"].values.astype("datetime64[ns]")) for t, g in rows.groupby("ticker")}
    for r in j.dropna(subset=["cik"]).itertuples(index=False):
        x = sd.get(r.ticker)
        if x is None:
            continue
        k = np.searchsorted(x, np.datetime64(r.filing_date), side="right")
        if k < len(x) and (pd.Timestamp(x[k]) - r.filing_date).days <= F1_DAYS:
            use.append(dict(ACCESSION_NUMBER=r.ACCESSION_NUMBER, cik=r.cik, ticker=r.ticker,
                            fd=r.filing_date, first_signal=pd.Timestamp(x[k]),
                            gap=(pd.Timestamp(x[k]) - r.filing_date).days))
    U = pd.DataFrame(use, columns=["ACCESSION_NUMBER", "cik", "ticker", "fd", "first_signal", "gap"]
                     ).drop_duplicates("ACCESSION_NUMBER")
    s4 = pd.concat([U.sort_values(["gap", "ACCESSION_NUMBER"]).head(150),
                    U.iloc[rng.choice(len(U), size=min(150, len(U)), replace=False)] if len(U) else U]
                   ).drop_duplicates("ACCESSION_NUMBER")
    P4 = check_index(F, s4, "cik", "ACCESSION_NUMBER")
    P4["edgar_filing_date"] = pd.to_datetime(P4["edgar_filing_date"])
    P4["edgar_accepted"] = pd.to_datetime(P4["edgar_accepted"])
    P4["ok_date"] = P4["edgar_filing_date"] == P4["fd"]
    P4["ok_public"] = P4["edgar_accepted"] < P4["first_signal"]
    P4.to_csv(out / "B2_form4_edgar.csv", index=False)
    S["B2_form4"] = dict(used_purchases=int(len(U)), sampled=int(len(P4)),
                         fetched=int(P4["edgar_accepted"].notna().sum()),
                         filing_date_mismatch=int((~P4["ok_date"]).sum()),
                         accepted_on_or_after_signal_day=int((~P4["ok_public"]).sum()),
                         min_gap_days=int(P4["gap"].min()))

    # ---- verdicts (AUDIT_PLAN.md)
    S["pass_A"] = bool(all(v["strict"]["days_with_br_order_change"] == 0 for v in S["A4_impact"].values())
                       and S["A0_reproduction"]["mismatched_rows"] == 0)
    S["pass_B"] = bool(S["B1_13f"]["fetched"] == S["B1_13f"]["sampled"] and
                       S["B1_13f"]["filing_date_mismatch"] == 0 and S["B1_13f"]["period_mismatch"] == 0 and
                       S["B1_13f"]["accepted_on_or_after_usable_from"] == 0 and
                       S["B2_form4"]["fetched"] == S["B2_form4"]["sampled"] and
                       S["B2_form4"]["accepted_on_or_after_signal_day"] == 0 and
                       all(v["differs_from_stored"] == 0 and v["quarter_not_yet_public"] == 0
                           for v in S["B3_f2_recompute"].values()))
    (out / "summary.json").write_text(json.dumps(S, indent=1, default=str))
    print(json.dumps({k: v for k, v in S.items() if k != "sources"}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
