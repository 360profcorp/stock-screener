"""Point-in-time identification for v2 (CORRECTION_V2.md §1–§2). Pure functions, tested.

Securities are identified by the CUSIPs recorded under the trading symbol **at the time**
(SEC fails-to-deliver files), never by today's identifiers. Issuers are identified by the
Form 3/4/5 issuer CIKs under that symbol, confirmed by name against the Official 13(f) List
name of the security at the time.
"""
import re
from bisect import bisect_left, bisect_right

import numpy as np
import pandas as pd

DEADLINE = 45
USE_DAYS = 120
STOPWORDS = {"INC", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED", "PLC", "LLC", "LP",
             "L", "P", "HLDGS", "HLDG", "HOLDINGS", "HOLDING", "GROUP", "GRP", "THE", "NEW", "CL",
             "CLASS", "A", "B", "C", "COM", "SHS", "ORD", "NV", "N", "V", "SA", "S", "AG", "SE",
             "DEL", "INCORPORATED", "TR", "TRUST", "INTL", "INTERNATIONAL", "CORPORATIO", "CORPORAT",
             "COS", "COMPANIES", "AND", "OF", "DE", "MD", "PA", "NY", "NJ", "OH", "IN", "TX", "VA", "T"}


def name_tokens(s):
    s = re.sub(r"[^A-Z0-9 ]", " ", str(s).upper().replace("&", " "))
    return [t for t in s.split() if t not in STOPWORDS]


GENERIC = {"BANK", "FIRST", "AMERICAN", "AMERICA", "GENERAL", "NATIONAL", "UNITED", "US", "U",
           "GLOBAL", "PACIFIC", "WESTERN", "EASTERN", "SOUTHERN", "NORTHERN", "CAPITAL", "ENERGY",
           "HEALTH", "DATA", "MUNICIPAL", "FEDERAL", "STANDARD", "ROYAL", "NEW"}


def names_match(a, b):
    """Same issuer name? Tolerates the 13(f) List's truncation and suffix noise. A generic
    first word (BANK, FIRST, ...) is not enough: the second word must agree too."""
    if not a or not b:
        return False
    ta, tb = name_tokens(a), name_tokens(b)
    if not ta or not tb:
        ja = re.sub(r"[^A-Z0-9]", "", str(a).upper())
        jb = re.sub(r"[^A-Z0-9]", "", str(b).upper())
        return bool(ja) and ja == jb
    def pre(x, y):
        return min(len(x), len(y)) >= 3 and (x.startswith(y) or y.startswith(x))
    if pre(ta[0], tb[0]):
        if ta[0] not in GENERIC and tb[0] not in GENERIC:
            return True
        if len(ta) >= 2 and len(tb) >= 2 and pre(ta[1], tb[1]):
            return True
    jac = len(set(ta) & set(tb)) / len(set(ta) | set(tb))
    if jac >= 0.5:
        return True
    ja, jb = "".join(ta), "".join(tb)
    return len(ja) >= 5 and len(jb) >= 5 and (ja.startswith(jb[:8]) or jb.startswith(ja[:8]))


# ---------------------------------------------------------------- FTD symbol records
class SymbolRecords:
    """Dated (cusip, symbol) records from the fails-to-deliver files."""

    def __init__(self, ftd: pd.DataFrame):
        f = ftd[ftd["cusip"].astype(str).str.len() == 9].copy()
        f["date"] = pd.to_datetime(f["date"])
        f = f.sort_values(["sym", "date"])
        self.by_sym = {s: (list(g["date"]), list(g["cusip"]), list(g.get("file", [""] * len(g))))
                       for s, g in f.groupby("sym")}
        self.first = f.groupby("cusip")["date"].min().to_dict()
        self.desc = {}
        for c, g in f.dropna(subset=["desc"]).groupby("cusip"):
            self.desc[c] = g["desc"].mode().iloc[0]

    def cusips(self, sym, lo, hi):
        """{cusip: (first date, last date, n records, files)} under `sym` within [lo, hi]."""
        x = self.by_sym.get(sym)
        if not x:
            return {}
        d, c, fl = x
        i, j = bisect_left(d, pd.Timestamp(lo)), bisect_right(d, pd.Timestamp(hi))
        out = {}
        for k in range(i, j):
            e = out.setdefault(c[k], [d[k], d[k], 0, set()])
            e[1] = d[k]
            e[2] += 1
            e[3].add(fl[k])
        return out


class ListNames:
    """Official 13(f) List names by CUSIP and list quarter."""

    def __init__(self, lists: pd.DataFrame):
        L = lists.copy()
        L["p"] = [pd.Period(x.upper().replace("Q", "Q"), freq="Q").end_time.normalize() for x in L["list"]]
        self.by = {c: sorted(zip(g["p"], g["name"], g["list"])) for c, g in L.groupby("cusip")}

    def name(self, cusip, p, reach_days=200):
        x = self.by.get(cusip)
        if not x:
            return None, None
        best = min(x, key=lambda r: abs((r[0] - pd.Timestamp(p)).days))
        if abs((best[0] - pd.Timestamp(p)).days) > reach_days:
            return None, None
        return best[1], best[2]


def security_name(c, p, names: ListNames, recs: SymbolRecords):
    n, src = names.name(c, p)
    if n:
        return n, f"13(f) list {src}"
    d = recs.desc.get(c)
    return (d, "FTD description") if d else (None, None)


def one_issuer(cusips, p, names, recs):
    """True if all CUSIPs share one 6-character issuer prefix (CORRECTION_V2 §1, change log:
    names are evidence only and never merge prefixes). Returns (bool, {cusip: (name, source)})."""
    nm = {c: security_name(c, p, names, recs) for c in sorted(cusips)}
    return len({c[:6] for c in cusips}) <= 1, nm


# ---------------------------------------------------------------- breadth rows (F2)
def window(q1, q):
    return pd.Timestamp(q1) - pd.Timedelta(days=30), pd.Timestamp(q) + pd.Timedelta(days=DEADLINE + 1 + USE_DAYS)


def classify_row(sym, q1, q, recs, names, first_seen):
    """Security set and status for the breadth row (sym, Q). first_seen: cusip -> first date
    the CUSIP appears anywhere (FTD any symbol, or 13F holdings period)."""
    lo, hi = window(q1, q)
    rec = recs.cusips(sym, lo, hi)
    S = sorted(rec)
    if not S:
        return dict(status="no_symbol_record", cusips=[], evidence=rec, names={})
    ok, nm = one_issuer(S, q, names, recs)
    if not ok:
        return dict(status="several_issuers", cusips=S, evidence=rec, names=nm)
    new = [c for c in S if first_seen.get(c, pd.Timestamp.max) > pd.Timestamp(q1)]
    if new:
        return dict(status="new_cusip", cusips=S, evidence=rec, names=nm, new=new)
    return dict(status="ok", cusips=S, evidence=rec, names=nm)


def holders(S_idx, period_holders, common):
    """Distinct common filers holding any CUSIP in S at one period. period_holders:
    cusip_idx -> sorted filer index array."""
    arrs = [period_holders[c] for c in S_idx if c in period_holders]
    if not arrs:
        return 0
    u = np.unique(np.concatenate(arrs))
    return int(np.isin(u, common, assume_unique=True).sum())


# ---------------------------------------------------------------- issuer CIK (F1)
def cik_names(cik, edgar, f4names, p):
    """Names of a CIK valid around period p: EDGAR name / dated former names + Form 4 issuer
    names in the neighbouring quarters."""
    out = set()
    e = edgar.get(str(cik)) or {}
    lo, hi = pd.Timestamp(p) - pd.Timedelta(days=200), pd.Timestamp(p) + pd.Timedelta(days=200)
    last_to = None
    for f in e.get("formerNames") or []:
        fr = pd.to_datetime(f.get("from"), errors="coerce", utc=True)
        to = pd.to_datetime(f.get("to"), errors="coerce", utc=True)
        fr = fr.tz_localize(None) if pd.notna(fr) else pd.Timestamp.min
        to = to.tz_localize(None) if pd.notna(to) else pd.Timestamp.max
        last_to = to if last_to is None else max(last_to, to)
        if fr <= hi and to >= lo:
            out.add(f.get("name"))
    if e.get("name") and (last_to is None or last_to <= hi):
        out.add(e["name"])
    q = pd.Timestamp(p).to_period("Q")
    for qq in (q - 1, q, q + 1):
        out |= f4names.get((str(cik), qq), set())
    return {n for n in out if isinstance(n, str) and n}


def assign_cik(sym, k, cand, recs, names, edgar, f4names):
    """CIK(sym, quarter k) per CORRECTION_V2 §2. cand: {(sym, quarter): {cik: n filings}}."""
    pool = {}
    for d in range(-2, 3):
        for c, n in cand.get((sym, k + d), {}).items():
            pool[c] = pool.get(c, 0) + n
    if not pool:
        return dict(status="no_form4_issuer", cik=None, candidates={})
    lo = k.start_time - pd.Timedelta(days=90)
    hi = k.end_time.normalize() + pd.Timedelta(days=90)
    sec = recs.cusips(sym, lo, hi)
    p = k.end_time.normalize()
    snames = {c: security_name(c, p, names, recs)[0] for c in sec}
    snames = {c: n for c, n in snames.items() if n}
    if not snames:
        return dict(status="no_security_name", cik=None, candidates=pool)
    conf = []
    for c in sorted(pool):
        cn = cik_names(c, edgar, f4names, p)
        if any(names_match(a, b) for a in cn for b in snames.values()):
            conf.append(c)
    if len(conf) == 1:
        return dict(status="ok", cik=conf[0], candidates=pool, security_names=snames)
    return dict(status="no_confirmed_issuer" if not conf else "several_confirmed_issuers", cik=None,
                candidates=pool, confirmed=conf, security_names=snames)
