"""E: confirmed raises of full-year revenue guidance from original SEC 8-K filings
(PLAN.md §4). Deterministic extraction, no AI APIs, no returns loaded.

    python -m research.event_base.events --candidates S_CANDIDATES_CSV --f345 DIR --out DIR
           [--mode pilot|full] [--docs DIR]

Identity: ticker -> CIK only via issuer trading symbols reported in Forms 3/4/5 (SEC Insider
Transactions Data Sets, f345_sub.csv.gz of artifact v2src-40196473096): exactly one CIK
within +-365 days, otherwise unknown. Timing: EDGAR acceptanceDateTime; a filing is usable
from the calendar day after its acceptance date. Status per S candidate: raise /
known_no_raise / unknown. A missing match is never read as "no event".
"""
import argparse
import hashlib
import html as htmlmod
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 20261025
PILOT_YEARS = range(2018, 2026)
PILOT_PER_YEAR = 10
LOOKBACK_DAYS = 400
MAX_AGE_SESSIONS = 60
ID_WINDOW_DAYS = 365
UA = {"User-Agent": "VISAR research 360pro.corp@gmail.com"}
EXTRACTOR_VERSION = "guidance-regex/1.0"


def nsym(s):
    return str(s).strip().upper().replace(".", "-").replace("/", "-")


# =====================================================================
# identity
# =====================================================================
def resolve_cik(sym, day, f345):
    """f345: DataFrame[issuer_cik, sym, filing_date]. Unique CIK that reported `sym` within
    +-ID_WINDOW_DAYS of `day`; (cik, reason)."""
    day = pd.Timestamp(day)
    w = f345[(f345["sym"] == nsym(sym)) &
             (f345["filing_date"] >= day - pd.Timedelta(days=ID_WINDOW_DAYS)) &
             (f345["filing_date"] <= day + pd.Timedelta(days=ID_WINDOW_DAYS))]
    ciks = sorted(set(int(c) for c in w["issuer_cik"].dropna()))
    if len(ciks) == 1:
        return ciks[0], "unique_form345_symbol"
    return None, ("no_form345_symbol" if not ciks else f"ambiguous_{len(ciks)}_ciks")


# =====================================================================
# extraction
# =====================================================================
NUM = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
UNIT = r"(billion|million|bn|mm|b|m)\b"
MONEY = r"\$\s?" + NUM + r"\s*(?:" + UNIT + r")?"
RANGE = re.compile(r"(?:between\s+)?" + MONEY + r"\s*(?:to|and|-|–|—)\s*\$?\s?" + NUM + r"\s*(?:" + UNIT + r")?", re.I)
REV = re.compile(r"\b(revenues?|net sales|total sales|sales)\b", re.I)
OUTLOOK = re.compile(r"\b(expects?|expected|expecting|guidance|outlook|anticipates?|range|projects?|"
                     r"forecasts?|now sees|raises?|raising|reaffirms?|updates?)\b", re.I)
YEAR = re.compile(r"(?:fiscal(?:\s+year)?|full[- ]year|FY)\s*'?(20\d\d)\b|\b(20\d\d)\s+(?:full[- ]year|fiscal(?:\s+year)?)\b|"
                  r"\bFY\s?'?(\d\d)\b", re.I)
FOREIGN = re.compile(r"€|£|¥|\beuros?\b|\bEUR\b|\bGBP\b|\bJPY\b|\bRMB\b|\bCAD\b|\bC\$|\bA\$|\byen\b|\bpounds?\b", re.I)
MULT = {"billion": 1e9, "bn": 1e9, "b": 1e9, "million": 1e6, "mm": 1e6, "m": 1e6}


def html_to_text(raw):
    t = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
    t = re.sub(r"(?is)<(script|style).*?</\1>", " ", t)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    t = htmlmod.unescape(t).replace("\xa0", " ")
    return re.sub(r"\s+", " ", t)


def sentences(text):
    return re.split(r"(?<=[.;!?])\s+(?=[A-Z(])", text)


def parse_guidance(text):
    """Full-year USD revenue ranges. Returns list of dict(year, low, high, excerpt) and the
    count of candidate sentences rejected as not comparable."""
    out, rejected = [], 0
    for s in sentences(text):
        m_rev = REV.search(s)
        if not m_rev or not OUTLOOK.search(s):
            continue
        years = set()
        for y in YEAR.finditer(s):
            v = y.group(1) or y.group(2) or (("20" + y.group(3)) if y.group(3) else None)
            if v:
                years.add(int(v))
        if not years:
            continue
        if FOREIGN.search(s):
            rejected += 1                                  # non-USD currency: not comparable
            continue
        rngs = [r for r in RANGE.finditer(s) if r.start() > m_rev.start()]
        if not rngs:
            continue
        if len(years) != 1:
            rejected += 1
            continue
        r = rngs[0]
        u1, u2 = (r.group(2) or "").lower(), (r.group(4) or "").lower()
        if not (u1 or u2):
            continue                                   # no million/billion: not a revenue range (e.g. EPS)
        u1 = u1 or u2
        u2 = u2 or u1
        lo = round(float(r.group(1).replace(",", "")) * MULT[u1], 2)
        hi = round(float(r.group(3).replace(",", "")) * MULT[u2], 2)
        between = s[m_rev.start():r.start()]
        if re.search(r"%|per share|\bEPS\b", between, re.I) or not 0 < lo <= hi:
            rejected += 1
            continue
        out.append(dict(year=years.pop(), low=lo, high=hi, excerpt=s[:600]))
    # one range per fiscal year per document: the first occurrence
    seen, uniq = set(), []
    for g in out:
        if g["year"] not in seen:
            seen.add(g["year"])
            uniq.append(g)
    return uniq, rejected


def is_raise(old, new):
    return (new["low"] >= old["low"] and new["high"] >= old["high"] and
            (new["low"] + new["high"]) / 2 > (old["low"] + old["high"]) / 2)


# =====================================================================
# fiscal period and status
# =====================================================================
def fiscal_label(day, fye):
    """Fiscal-year label (the calendar year in which the fiscal year ends) on `day` for a
    fiscalYearEnd 'MMDD'; None when the mapping is ambiguous (year ends Jan-Mar: retail
    conventions name such years by their start year)."""
    if not fye or len(str(fye)) != 4:
        return None
    mm, dd = int(str(fye)[:2]), int(str(fye)[2:])
    if mm <= 3:
        return None
    day = pd.Timestamp(day)
    end = pd.Timestamp(year=day.year, month=mm, day=min(dd, 28 if mm == 2 else dd))
    return day.year if day <= end else day.year + 1


def candidate_status(cand, releases, fye, sessions):
    """cand: dict(base_start, signal_date); releases: list of dict(accession, accepted
    (Timestamp), retrieved (bool), guidance (list from parse_guidance)) for the issuer, all
    Item 2.02 8-Ks; sessions: SPY calendar. Returns dict(status, reason, ...)."""
    bs, sd = pd.Timestamp(cand["base_start"]), pd.Timestamp(cand["signal_date"])
    Y = fiscal_label(sd, fye)
    if Y is None:
        return dict(status="unknown", reason="fiscal_year_mapping_ambiguous")
    usable = lambda r: pd.Timestamp(r["accepted"]).normalize() + pd.Timedelta(days=1)    # noqa: E731
    rel = sorted([r for r in releases if usable(r) <= sd], key=lambda r: r["accepted"])
    window = [r for r in rel if usable(r) >= bs - pd.Timedelta(days=LOOKBACK_DAYS)]
    if not window:
        return dict(status="unknown", reason="no_release_in_window")
    if any(not r["retrieved"] for r in window):
        return dict(status="unknown", reason="release_not_retrieved")
    latest = window[-1]
    g_new = next((g for g in latest["guidance"] if g["year"] == Y), None)
    if g_new is None:
        return dict(status="unknown", reason="guidance_for_period_not_found_in_latest_release",
                    latest=latest["accession"], period=Y)
    prev = None
    for r in reversed(rel[:rel.index(latest)]):
        if not r["retrieved"]:
            return dict(status="unknown", reason="previous_release_not_retrieved", period=Y)
        g = next((g for g in r["guidance"] if g["year"] == Y), None)
        if g is not None:
            prev = (r, g)
            break
    out = dict(period=Y, latest=latest["accession"], latest_accepted=str(latest["accepted"]),
               new_low=g_new["low"], new_high=g_new["high"])
    if prev is None:
        return dict(out, status="known_no_raise", reason="initial_guidance_no_previous_range")
    out.update(prev=prev[0]["accession"], old_low=prev[1]["low"], old_high=prev[1]["high"])
    if not is_raise(prev[1], g_new):
        return dict(out, status="known_no_raise", reason="latest_update_not_a_raise")
    cal = pd.DatetimeIndex(sessions)
    u = usable(latest)
    age = int(((cal >= u) & (cal <= sd)).sum())
    out["age_sessions"] = age
    if not pd.Timestamp(latest["accepted"]).normalize() < bs:
        return dict(out, status="known_no_raise", reason="raise_not_known_before_base_start")
    if age > MAX_AGE_SESSIONS:
        return dict(out, status="known_no_raise", reason="raise_older_than_60_sessions")
    return dict(out, status="raise", reason="confirmed_raise", event=latest["accession"])


def consume_events(status_df):
    """One structural signal per event: keep the first S signal (by date, ticker) of each
    raise; later signals using the same raise become known_no_raise."""
    d = status_df.sort_values(["signal_date", "ticker"]).copy()
    seen = set()
    for k, r in d.iterrows():
        if r["status"] == "raise":
            key = (r["cik"], r["event"])
            if key in seen:
                d.at[k, "status"], d.at[k, "reason"] = "known_no_raise", "event_already_used"
            seen.add(key)
    return d


def pilot_sample(cands, seed=SEED):
    c = cands[cands["status"] == "candidate"].copy()
    c["signal_date"] = pd.to_datetime(c["signal_date"])
    c = c.sort_values(["signal_date", "ticker"]).reset_index(drop=True)
    rng = np.random.default_rng(seed)
    out = []
    for y in PILOT_YEARS:
        g = c[c["signal_date"].dt.year == y]
        k = min(PILOT_PER_YEAR, len(g))
        if k:
            out.append(g.iloc[sorted(rng.choice(len(g), k, replace=False))])
    return pd.concat(out).reset_index(drop=True) if out else c.iloc[:0]


# =====================================================================
# EDGAR
# =====================================================================
class Edgar:
    def __init__(self, docs_dir=None, pause=0.15):
        import requests
        self.s = requests.Session()
        self.s.headers.update(UA)
        self.pause, self.t, self.log = pause, 0.0, []
        self.docs = Path(docs_dir) if docs_dir else None
        if self.docs:
            self.docs.mkdir(parents=True, exist_ok=True)

    def get(self, url, tries=4):
        for k in range(tries):
            w = self.pause - (time.time() - self.t)
            if w > 0:
                time.sleep(w)
            self.t = time.time()
            try:
                r = self.s.get(url, timeout=60)
            except Exception as e:                          # noqa: BLE001
                err = str(e)[:100]
                time.sleep(3 * (k + 1))
                continue
            if r.status_code == 200:
                b = r.content
                self.log.append(dict(url=url, bytes=len(b), sha256=hashlib.sha256(b).hexdigest(),
                                     fetched_utc=datetime.now(timezone.utc).isoformat()))
                return b
            err = f"http {r.status_code}"
            if r.status_code in (403, 429, 500, 502, 503):
                time.sleep(5 * (k + 1))
                continue
            break
        self.log.append(dict(url=url, error=err))
        return None

    def submissions(self, cik):
        b = self.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
        if b is None:
            return None
        j = json.loads(b)
        frames = [pd.DataFrame(j["filings"]["recent"])]
        for f in j["filings"].get("files", []):
            bb = self.get(f"https://data.sec.gov/submissions/{f['name']}")
            if bb is None:
                return dict(meta=j, filings=None)
            frames.append(pd.DataFrame(json.loads(bb)))
        return dict(meta=j, filings=pd.concat(frames, ignore_index=True))

    def exhibits(self, cik, acc):
        nod = acc.replace("-", "")
        base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{nod}/"
        idx = self.get(base + f"{acc}-index.htm")
        if idx is None:
            return None
        h = idx.decode("utf-8", "replace")
        rows = re.findall(r'<a href="(/Archives/edgar/data/[^"]+)">[^<]*</a>\s*</td>\s*<td[^>]*>\s*(EX-99[^<]*)</td>', h, re.I)
        return [("https://www.sec.gov" + href, typ.strip()) for href, typ in rows]


def collect(cands, f345, edgar, sessions, log=print):
    """Event status for each candidate row + registry/extraction tables."""
    status, registry, extractions = [], [], []
    subs_cache, rel_cache = {}, {}
    for c in cands.to_dict("records"):
        cik, why = resolve_cik(c["ticker"], c["signal_date"], f345)
        base = dict(ticker=c["ticker"], signal_date=pd.Timestamp(c["signal_date"]), base_start=c["base_start"],
                    cik=cik, identity=why)
        if cik is None:
            status.append(dict(base, status="unknown", reason="identity_" + why))
            continue
        if cik not in subs_cache:
            subs_cache[cik] = edgar.submissions(cik)
        sub = subs_cache[cik]
        if sub is None or sub.get("filings") is None:
            status.append(dict(base, status="unknown", reason="submissions_not_retrieved"))
            continue
        meta, f = sub["meta"], sub["filings"]
        base["issuer_name"] = meta.get("name")
        f = f[f["form"].isin(["8-K", "8-K/A"]) & f["items"].fillna("").str.contains(r"2\.02")].copy()
        f["accepted"] = pd.to_datetime(f["acceptanceDateTime"], utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
        lo = pd.Timestamp(c["base_start"]) - pd.Timedelta(days=LOOKBACK_DAYS + 120)
        f = f[(f["accepted"] >= lo) & (f["accepted"] < pd.Timestamp(c["signal_date"]))]
        rels = []
        for r in f.to_dict("records"):
            acc = r["accessionNumber"]
            if acc not in rel_cache:
                ex = edgar.exhibits(cik, acc)
                rec = dict(accession=acc, accepted=r["accepted"], form=r["form"], retrieved=ex is not None and len(ex) > 0,
                           guidance=[])
                for url, typ in (ex or []):
                    b = edgar.get(url)
                    if b is None:
                        rec["retrieved"] = False
                        continue
                    sha = hashlib.sha256(b).hexdigest()
                    if edgar.docs:
                        (edgar.docs / f"{sha}.htm").write_bytes(b)
                    gs, rej = parse_guidance(html_to_text(b))
                    registry.append(dict(cik=cik, issuer_name=meta.get("name"), accession=acc, form=r["form"],
                                         accepted_et=str(r["accepted"]), exhibit_type=typ, url=url, bytes=len(b),
                                         sha256=sha, ranges_found=len(gs), rejected_sentences=rej,
                                         extractor=EXTRACTOR_VERSION))
                    for g in gs:
                        extractions.append(dict(cik=cik, accession=acc, url=url, sha256=sha, accepted_et=str(r["accepted"]),
                                                fiscal_year=g["year"], low_usd=g["low"], high_usd=g["high"],
                                                excerpt=g["excerpt"]))
                        if g["year"] not in [x["year"] for x in rec["guidance"]]:
                            rec["guidance"].append(g)
                rel_cache[acc] = rec
            rels.append(rel_cache[acc])
        st = candidate_status(c, rels, meta.get("fiscalYearEnd"), sessions)
        status.append(dict(base, fiscal_year_end=meta.get("fiscalYearEnd"), releases_in_lookback=len(rels),
                           **{k: v for k, v in st.items()}))
        log(f"{c['ticker']} {pd.Timestamp(c['signal_date']).date()}: {st['status']} ({st['reason']})")
    return pd.DataFrame(status), pd.DataFrame(registry), pd.DataFrame(extractions)


def coverage(status, years=PILOT_YEARS):
    s = status.copy()
    s["year"] = pd.to_datetime(s["signal_date"]).dt.year
    by = {}
    for y in years:
        g = s[s["year"] == y]
        if len(g):
            known = int(g["status"].isin(["raise", "known_no_raise"]).sum())
            by[int(y)] = dict(candidates=int(len(g)), known=known, raise_=int((g["status"] == "raise").sum()),
                              coverage_pct=round(100 * known / len(g), 1))
    return dict(by_year=by, all_years_ge_80=bool(by) and all(v["coverage_pct"] >= 80 for v in by.values()),
                unknown_reasons=s.loc[s["status"] == "unknown", "reason"].value_counts().to_dict(),
                status_counts=s["status"].value_counts().to_dict())


def main(argv=None):
    from research.sp1500 import run as RUN
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--f345", required=True, help="folder containing f345_sub.csv.gz")
    ap.add_argument("--calendar", required=True, help="equity csv with a date column (SPY sessions)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--docs", default=None)
    ap.add_argument("--mode", default="pilot", choices=["pilot", "full"])
    a = ap.parse_args(argv)
    root0 = Path(__file__).resolve().parents[2]
    out = Path(a.out).resolve() / datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    root = root0 if root0 in out.parents else Path(a.out).resolve()
    man = {}
    W = lambda n, b: RUN.write_once(out / n, b, man, root)                      # noqa: E731
    cands = pd.read_csv(a.candidates, parse_dates=["signal_date", "base_start"])
    f345p = next(Path(a.f345).rglob("f345_sub.csv.gz"))
    f345 = pd.read_csv(f345p, usecols=["issuer_cik", "sym", "filing_date"], parse_dates=["filing_date"])
    f345["sym"] = f345["sym"].map(nsym)
    sessions = pd.to_datetime(pd.read_csv(a.calendar)["date"])
    sample = pilot_sample(cands) if a.mode == "pilot" else cands[cands["status"] == "candidate"]
    W("sample.csv", RUN.csv_bytes(sample[["ticker", "signal_date", "base_start"]]))
    ed = Edgar(a.docs)
    st, reg, ext = collect(sample, f345, ed, sessions)
    st = consume_events(st) if len(st) else st
    cov = coverage(st, PILOT_YEARS if a.mode == "pilot" else sorted(pd.to_datetime(st["signal_date"]).dt.year.unique()))
    cov.update(mode=a.mode, extractor=EXTRACTOR_VERSION, f345_source=str(f345p.name),
               f345_sha256=hashlib.sha256(f345p.read_bytes()).hexdigest(),
               full_collection_passed=bool(a.mode == "full" and cov["all_years_ge_80"]),
               requests=len(ed.log), failed_requests=sum(1 for x in ed.log if "error" in x))
    W("event_status.csv", RUN.csv_bytes(st))
    W("source_registry.csv", RUN.csv_bytes(reg))
    W("extractions.csv", RUN.csv_bytes(ext))
    W("fetch_log.csv", RUN.csv_bytes(pd.DataFrame(ed.log)))
    W("coverage.json", json.dumps(cov, indent=1, default=str))
    W("manifest.json", json.dumps(dict(files=dict(man)), indent=1))
    print(json.dumps(cov, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
