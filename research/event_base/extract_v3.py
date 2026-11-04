"""Extractor v3: deterministic event status from review-packet text windows (REVIEW_PLAN.md §7).

v3 = v2 plus the fixes of §7.2 and the classification rule of §7.1.

Statuses (same as the manual review): confirmed_raise, confirmed_no_raise,
confirmed_no_suitable_guidance, unknown. No AI, no prices, no returns.

    python -m research.event_base.extract_v3 --packets DIR [--labels MODULE] --out DIR
"""
import argparse
import importlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

VERSION = "extract-v3/1.0"
NUM = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
UNIT = r"(billion|million|bn|mm|b|m)\b"
RANGE = re.compile(r"(?:between\s+)?(~|approximately\s+|approx\.\s+)?\$\s?" + NUM + r"\s*(?:" + UNIT + r")?\s*"
                   r"(?:to|-|–|—|and)\s*\$?\s?" + NUM + r"\s*(?:" + UNIT + r")?", re.I)
POINT = re.compile(r"(?:approximately|about|~|roughly)\s*\$\s?" + NUM + r"\s*(?:" + UNIT + r")?", re.I)
REV = re.compile(r"(?<!closed )(?<!same-store )(?<!same store )(?<!comparable )(?<!comparable store )(?<!organic )"
                 r"\b((?:consolidated\s+)?(?:total\s+|net\s+|products and services\s+|product\s+)?(?:revenues?|sales))\b(?!\s+growth)", re.I)
OTHER_METRIC = re.compile(r"profit|income|ebitda|ebita|\beps\b|earnings|margin|cash|expense|capital|repurchase|dividend|"
                          r"backlog|orders|bookings|\brose\b|increased|\bgrew\b|decreased|declined|\bup\b|\bdown\b", re.I)
TABLE3 = re.compile(r"\$\s?" + NUM + r"\s*(B|M|billion|million)?\s+\$\s?" + NUM + r"\s*(B|M|billion|million)?\s+\$\s?" + NUM +
                    r"\s*(B|M|billion|million)?(?:\s+\$\s?" + NUM + r"\s*(B|M|billion|million)?\s+\$\s?" + NUM +
                    r"\s*(B|M|billion|million)?\s+\$\s?" + NUM + r"\s*(B|M|billion|million)?)?", re.I)
TABLE2 = re.compile(r"\$\s?" + NUM + r"\s+\$\s?" + NUM + r"\b")
STATED_RAISE = re.compile(r"(?:outlook|guidance)\s+(?:raised|increased)|rais\w+\s+(?:its\s+|our\s+|the\s+)?(?:full[- ]year\s+|fiscal\s+(?:year\s+)?|20\d\d\s+)*"
                          r"(?:financial\s+)?(?:outlook|guidance)(?!\s+(?:for|range)?\s*(?:diluted|adjusted|non-gaap|gaap)?\s*(?:eps|earnings))", re.I)
QUARTER = re.compile(r"\bquarter\b|\bQ[1-4]\b|three months|thirteen weeks|13 weeks|first half|second half|\bH[12]\b|"
                     r"\bQ[1-4]'?\d\d|fourth-quarter|third-quarter|second-quarter|first-quarter|\b[1-4]Q\s?\d\d", re.I)
FULLYEAR = re.compile(r"full[- ]year|fiscal(?:\s+year)?\s*'?(20\d\d|\d\d)\b|\bFY\s?'?(20\d\d|\d\d)\b|for the (?:full )?year|"
                      r"\bannual\b|(20\d\d)\s+(?:\w+\s+){0,4}(?:outlook|guidance|objectives|expectations)|"
                      r"(?:outlook|guidance) for (20\d\d)|\bfor (20\d\d)\b|full fiscal year|year ending", re.I)
YEARNUM = re.compile(r"(?:fiscal(?:\s+year)?|FY|full[- ]year|year)\s*'?(20\d\d|\d\d)\b|\b(20\d\d)\b", re.I)
ACQ = re.compile(r"includ\w*\s+(?:the\s+)?(?:recent(?:ly)?\s+)?(?:completed\s+|announced\s+|closed\s+)?acquisitions?|"
                 r"to include the (?:recent )?acquisitions?", re.I)
PRIOR = re.compile(r"previous(?:ly)?|prior|compared (?:to|with)|versus|vs\.?|from (?:a range of )?\$", re.I)
TABLE_CUR_PRIOR = re.compile(r"\b(current|updated)\s+(prior|previous)\b", re.I)
TABLE_UNIT = re.compile(r"dollars in billions|\(\$ in billions|in billions|dollars in millions|\(\$ in millions|in millions", re.I)
MULT = {"billion": 1e9, "bn": 1e9, "b": 1e9, "million": 1e6, "mm": 1e6, "m": 1e6}
QFY = re.compile(r"quarter\s+of\s+(?:the\s+)?(?:fiscal(?:\s+year)?|FY)|\bQ[1-4]\s*'?(?:FY|fiscal)|fiscal\s+quarter|"
                 r"quarter\s+(?:of\s+)?(?:fiscal\s+)?(?:year\s+)?(?=20\d\d)|\bQ[1-4]\s+(?=20\d\d)", re.I)
EXCL_ACQ = re.compile(r"(?:does|do|will) not (?:reflect|include)[^.]{0,120}?(?:acquisition|merger)", re.I)
PCT_GUIDE = re.compile(r"(?:revenues?|sales)\s+(?:\w+\s+){0,4}?growth[^.]{0,80}?\d+(?:\.\d+)?\s?%|"
                       r"(?:revenues?|sales)\s+(?:to\s+)?(?:grow|increase|decline|decrease|be (?:up|down))[^.]{0,60}?\d+(?:\.\d+)?\s?(?:%|percent)|"
                       r"(?:revenues?|sales)\s+growth\s+(?:of\s+)?(?:in the\s+)?(?:low|mid|high)|"
                       r"(?:identical|comparable|same[- ]store|comp)\s+(?:store\s+)?sales[^.]{0,80}?\d+(?:\.\d+)?\s?%", re.I)
NOT_REV_RAISE = re.compile(r"eps|earnings|per share|margin|profit|ebitda|income", re.I)
ACTUAL = re.compile(r"\b(?:was|were|totaled|totalled|reached|came in at|amounted to)\b", re.I)
AFTER_TABLE = re.compile(r"\s*(?:\(?\d\)?\s*)?(Unchanged|Reaffirmed|Previously\s+\$\s?" + NUM + r"\s*(?:to|-|–)\s*\$?\s?" + NUM + r")", re.I)


def stated_raise(w):
    """A stated raise of the outlook that is not about EPS / margin / profit only."""
    for m in STATED_RAISE.finditer(w):
        before = w[max(0, m.start() - 40):m.start()]
        inside = m.group(0)
        if NOT_REV_RAISE.search(before) or NOT_REV_RAISE.search(inside):
            continue
        return True
    return False
GUIDE = re.compile(r"outlook|guidance|expects?\b|anticipat", re.I)


def _val(num, unit, default):
    u = (unit or "").lower() or default
    if not u:
        return None
    return float(num.replace(",", "")) * MULT[u] / 1e9


def metric_name(s):
    s = s.lower()
    if "products and services" in s:
        return "products_services_revenue"
    if "sales" in s:
        return "sales"
    return "revenue"


def _yr(v):
    return int(v) if len(v) == 4 else 2000 + int(v)


_GENERIC = {"total", "net", "guidance", "outlook", "prior", "year", "full", "fiscal", "the", "our", "and", "of", "for", "company"}


def _brand_before(w, pos):
    """True if the word(s) right before a 'product revenues/sales' phrase name one product (capitalised, not generic)."""
    words = re.findall(r"[A-Za-z®™]+", w[max(0, pos - 40):pos])[-2:]
    words = [x for x in words if x.lower() != "net"]
    return bool(words) and words[-1][0].isupper() and words[-1].lower().strip("®™") not in _GENERIC


def parse_window(w):
    """Full-year company revenue items in one text window:
    list of dict(kind=range|point|quarterly, year, low, high, metric, old, acq, pos)."""
    out = []
    tunit = None
    mt = TABLE_UNIT.search(w)
    if mt:
        tunit = "billion" if "billion" in mt.group(0).lower() else "million"
    lowhigh = re.search(r"\bLow(?:\s+End)?\b\W+(?:Baseline|Outlook|Mid(?:point)?)?\W*\bHigh\b", w)
    for m in REV.finditer(w):
        if m.group(1).lower().lstrip().startswith("product") and _brand_before(w, m.start()):
            continue                                              # "Jakafi net product revenues": one product, not the company
        tail = w[m.end():m.end() + 170]
        r = RANGE.search(tail)
        if r is not None and re.search(r"\band\b", r.group(0), re.I) and not r.group(0).lower().startswith("between"):
            r = None                                              # "$A and $B" without "between": two figures, not a range
        p = POINT.search(tail)
        t3 = TABLE3.match(tail.lstrip(" 1*:")) if lowhigh else None
        t2 = TABLE2.match(tail.lstrip(" 1*:")) if (lowhigh and t3 is None) else None
        if r is None and p is None and t3 is None and t2 is None:
            continue
        cands = [x for x in (r, p) if x is not None]
        first_any = min(cands, key=lambda x: x.start()) if cands else None
        start_rel = 0 if (t3 is not None or t2 is not None) else first_any.start()
        gap = tail[:start_rel]
        range_intro = re.search(r"(?:range of|to a range of|to be|of|at|between|approximately)\s*$", gap, re.I)
        if len(gap) > 140 or (len(gap) > 90 and not range_intro) or re.search(r"[.;]\s+[A-Z]|per share|\bEPS\b", gap) or OTHER_METRIC.search(gap) or ACTUAL.search(gap) or \
                ("%" in gap and not range_intro):
            continue
        ctx = w[max(0, m.start() - 230):m.end() + start_rel]
        q = [x.start() for x in QUARTER.finditer(ctx)]
        fy = list(FULLYEAR.finditer(ctx))
        last_q = q[-1] if q else -1
        last_fy = fy[-1].start() if fy else -1
        qfy = any(x.start() <= last_fy <= x.end() + 3 for x in QFY.finditer(ctx))
        if last_q > last_fy or qfy:
            out.append(dict(kind="quarterly", pos=m.start()))
            continue
        if last_fy < 0:
            continue                                              # no period marker at all
        g = [v for x in fy for v in x.groups() if v]
        if g:
            year = _yr(g[-1])
        else:
            ys = [y.group(1) or y.group(2) for y in YEARNUM.finditer(ctx[last_fy:])]
            ys = [_yr(v) for v in ys if v]
            year = ys[0] if ys else None
        if year is None or not 2010 <= year <= 2035:
            continue
        if re.search(r"(?:prior|previous(?:ly)?)\s+(?:outlook\s+|guidance\s+|expected\s+)?range\s+of\s*$", gap, re.I):
            continue                                              # the quoted range is the old one
        acq = bool(ACQ.search(w))
        metric = metric_name(m.group(1))
        if t3 is not None or t2 is not None:
            if t3 is not None:
                vals = [(t3.group(k), t3.group(k + 1)) for k in range(1, 12, 2) if t3.group(k)]
                if len(vals) == 6:
                    vals = vals[3:]                               # quarter block first, full year second
                (a, ua), (b, ub) = vals[0], vals[-1]
            else:
                (a, ua), (b, ub) = (t2.group(1), None), (t2.group(2), None)
            ua = {"b": "billion", "m": "million"}.get((ua or "").lower(), ua)
            ub = {"b": "billion", "m": "million"}.get((ub or "").lower(), ub)
            lo, hi = _val(a, ua or ub, tunit), _val(b, ub or ua, tunit)
            if lo and hi and 0 < lo <= hi <= 5 * lo:
                old = None
                end = m.end() + (t3.end() if t3 is not None else t2.end()) + (len(tail) - len(tail.lstrip(" 1*:")))
                at = AFTER_TABLE.match(w[end:end + 80])
                if at is not None:
                    if at.group(1).lower().startswith(("unchanged", "reaffirmed")):
                        old = (lo, hi)
                    else:
                        lo0, hi0 = _val(at.group(2), None, tunit), _val(at.group(3), None, tunit)
                        if lo0 and hi0 and lo0 <= hi0:
                            old = (lo0, hi0)
                out.append(dict(kind="range", year=year, low=lo, high=hi, metric=metric, old=old, acq=acq, pos=m.start()))
            continue
        first = r if (r is not None and (p is None or r.start() <= p.start())) else None
        if first is None:
            out.append(dict(kind="point", year=year, metric=metric, acq=acq, pos=m.start(),
                            value=_val(p.group(1), p.group(2), tunit)))
            continue
        u1, u2 = first.group(3), first.group(5)
        lo = _val(first.group(2), u1 or u2, tunit)
        hi = _val(first.group(4), u2 or u1, tunit)
        if lo is None or hi is None or not 0 < lo <= hi or hi > 5 * lo:
            continue
        old = None
        after = tail[first.end():first.end() + 200]
        r2 = RANGE.search(after)
        if r2 is not None:
            between = after[:r2.start()]
            lo2 = _val(r2.group(2), r2.group(3) or r2.group(5) or u1 or u2, tunit)
            hi2 = _val(r2.group(4), r2.group(5) or r2.group(3) or u2 or u1, tunit)
            if lo2 and hi2 and 0 < lo2 <= hi2:
                if (PRIOR.search(between) and not OTHER_METRIC.search(between)) or \
                        (TABLE_CUR_PRIOR.search(w) and len(between.strip()) < 25):
                    old = (lo2, hi2)
        if re.search(r"from\s+(?:a\s+range\s+of\s+)?$", tail[:first.start()], re.I):
            seg = tail[first.end():first.end() + 90]
            mm = re.match(r"\s*to\s+(?:a\s+range\s+of\s+)?", seg, re.I)
            r3 = RANGE.search(seg) if mm else None
            if r3 is not None:
                lo3 = _val(r3.group(2), r3.group(3) or r3.group(5) or u1 or u2, tunit)
                hi3 = _val(r3.group(4), r3.group(5) or r3.group(3) or u2 or u1, tunit)
                if lo3 and hi3:
                    old, lo, hi = (lo, hi), lo3, hi3
        out.append(dict(kind="range", year=year, low=lo, high=hi, metric=metric, old=old, acq=acq, pos=m.start()))
    return out


def filing_items(f):
    """Per filing: first company-level full-year range per year (document order), points, flags."""
    rng, pts, quarterly, ptv = {}, set(), False, {}
    gw, stated, pct, excl = 0, False, False, False
    docs_ok = bool(f["documents"]) and all("error" not in d for d in f["documents"])
    for d in f["documents"]:
        gw += d.get("guidance_words") or 0
        for w in d.get("windows", []):
            w = re.sub(r"[\s\u200b\u00a0]+", " ", w)
            stated |= stated_raise(w)
            excl |= bool(EXCL_ACQ.search(w))
            pct |= bool(PCT_GUIDE.search(w))
            for it in parse_window(w):
                if it["kind"] == "quarterly":
                    quarterly = True
                elif it["kind"] == "point":
                    pts.add(it["year"])
                    if it.get("value"):
                        ptv.setdefault(it["year"], []).append(it["value"])
                elif it["year"] not in rng:
                    rng[it["year"]] = it
    for y in list(rng):                                           # a range well below a revenue point for the same
        mid = (rng[y]["low"] + rng[y]["high"]) / 2                # year in the same filing is one product/segment
        if any(mid < 0.75 * v for v in ptv.get(y, [])):
            del rng[y]
    return dict(ranges=rng, points=pts, quarterly=quarterly, gw=gw, docs_ok=docs_ok, stated_raise=stated, pct=pct, excl_acq=excl)


def fy_end(label, released, fye):
    """End date of fiscal-year `label` seen in a release on `released` (first candidate end >= release)."""
    s = str(fye or "1231").zfill(4)
    mm, dd = int(s[:2]), int(s[2:])
    for y in (label, label + 1):
        try:
            e = pd.Timestamp(year=y, month=mm, day=min(dd, 28 if mm == 2 else dd))
        except ValueError:
            e = pd.Timestamp(year=y, month=mm, day=28)
        if e >= pd.Timestamp(released).normalize():
            return e
    return pd.Timestamp(year=label + 1, month=mm, day=min(dd, 28))


def is_raise(old, lo, hi):
    return lo >= old[0] - 1e-9 and hi >= old[1] - 1e-9 and (lo + hi) / 2 > (old[0] + old[1]) / 2 + 1e-9


def case_status(p, sessions):
    sd, bs = pd.Timestamp(p["signal_date"]), pd.Timestamp(p["base_start"])
    fl = sorted([f for f in p["filings"] if pd.Timestamp(f["accepted_et"]) < sd], key=lambda f: f["accepted_et"])
    if p.get("cik") is None:
        return dict(status="unknown", reason="identity")
    rel202 = [f for f in fl if "2.02" in str(f["items"]) or "blank" in str(f["items"])]
    if not rel202 or (sd - pd.Timestamp(rel202[-1]["accepted_et"])).days > 120:
        return dict(status="unknown", reason="incomplete_history_no_recent_release")
    win = [f for f in fl if pd.Timestamp(f["accepted_et"]) >= bs - pd.Timedelta(days=400)]
    def _complete(f):
        return bool(f["documents"]) and not any("error" in d for d in f["documents"])
    # §7.1: a missing release matters only if no complete Item 2.02 release follows it before the signal
    miss = [f for f in win if f in rel202 and not _complete(f)]
    incomplete = bool(miss) and not any(_complete(g) and g["accepted_et"] > miss[-1]["accepted_et"] for g in rel202)
    items = [(f, filing_items(f)) for f in fl]
    # fiscal years with a range anywhere in the record, and the one in force on the signal date
    labels = {}
    for f, it in items:
        for y in it["ranges"]:
            labels.setdefault(y, fy_end(y, f["accepted_et"], p.get("fiscal_year_end")))
        for y in it["points"]:
            labels.setdefault(y, fy_end(y, f["accepted_et"], p.get("fiscal_year_end")))
    cur = sorted([y for y, e in labels.items() if e >= sd and e - pd.Timedelta(days=400) < sd])
    ranges_in_window = any(it["ranges"] for f, it in items if f in win)
    if not ranges_in_window:
        if incomplete:
            return dict(status="unknown", reason="incomplete_history_missing_document")
        if any(it["points"] for f, it in items if f in win):
            return dict(status="confirmed_no_suitable_guidance", reason="point estimates only")
        if any(it["stated_raise"] for f, it in items if f in win) and not any(it["pct"] for f, it in items if f in win):
            return dict(status="unknown", reason="extraction: guidance change stated but no range parsed")
        return dict(status="confirmed_no_suitable_guidance",
                    reason="no full-year USD revenue range in the filed record" +
                           (" (quarterly ranges only)" if any(it["quarterly"] for _, it in items) else ""))
    if not cur:
        if incomplete:
            return dict(status="unknown", reason="incomplete_history_missing_document")
        return dict(status="confirmed_no_suitable_guidance",
                    reason="prior_fy_range_only: no range for the fiscal year in progress at the signal (§7.1)")
    Y = cur[0]
    if not any(Y in it["ranges"] for f, it in items):
        return dict(status="confirmed_no_suitable_guidance", reason="current fiscal year guided only as a point estimate", year=Y)
    upd = [(f, it) for f, it in items if Y in it["ranges"] or Y in it["points"]]
    if not upd:
        return dict(status="confirmed_no_raise", reason="no range for the current fiscal year")
    f_last, it_last = upd[-1]
    later = [f for f, it in items if f["accepted_et"] > f_last["accepted_et"] and f in rel202 and it["stated_raise"]]
    if later:
        return dict(status="unknown", reason="later release with guidance language but no parsed update", year=Y)
    if Y in it_last["points"] and Y not in it_last["ranges"]:
        return dict(status="confirmed_no_raise", reason="latest update is a point estimate", year=Y)
    new = it_last["ranges"][Y]
    old = new.get("old")
    prev = [it["ranges"][Y] for f, it in upd[:-1] if Y in it["ranges"]]
    prev_f = [it for f, it in upd[:-1] if Y in it["ranges"]]
    if prev_f and prev_f[-1]["excl_acq"] and not it_last["excl_acq"]:
        return dict(status="confirmed_no_raise", reason="prior guidance excluded a pending acquisition: not comparable", year=Y)
    if old is None and prev:
        old = (prev[-1]["low"], prev[-1]["high"])
        if prev[-1]["metric"] != new["metric"]:
            return dict(status="confirmed_no_raise", reason="metric changed: not comparable", year=Y)
    out = dict(year=Y, new=(new["low"], new["high"]), old=old, accession=f_last["accession"],
               accepted=f_last["accepted_et"])
    if old is None:
        return dict(out, status="confirmed_no_raise", reason="initial guidance")
    if new["acq"]:
        return dict(out, status="confirmed_no_raise", reason="update includes acquisitions: not comparable")
    if not is_raise(old, new["low"], new["high"]):
        return dict(out, status="confirmed_no_raise", reason="latest update not a raise")
    acc = pd.Timestamp(f_last["accepted_et"])
    cal = pd.DatetimeIndex(sessions)
    age = int(((cal >= acc.normalize() + pd.Timedelta(days=1)) & (cal <= sd)).sum())
    if not acc.normalize() < bs:
        return dict(out, status="confirmed_no_raise", reason="raise not known before base start", age=age)
    if age > 60:
        return dict(out, status="confirmed_no_raise", reason="raise older than 60 sessions", age=age)
    return dict(out, status="confirmed_raise", reason="confirmed raise", age=age)


def run(packets, sessions):
    rows = []
    for p in packets:
        s = case_status(p, sessions)
        rows.append(dict(case=p["case"], ticker=p["ticker"], cik=p.get("cik"), signal_date=p["signal_date"],
                         base_start=p["base_start"], **{k: (str(v) if isinstance(v, tuple) else v) for k, v in s.items()}))
    return pd.DataFrame(rows)


def compare(v2, labels):
    lab = pd.DataFrame([dict(case=l[0], manual=l[1]) for l in labels])
    m = v2.merge(lab, on="case")
    agree = (m["status"] == m["manual"])
    false_raise = ((m["status"] == "confirmed_raise") & (m["manual"] != "confirmed_raise"))
    return m, dict(cases=int(len(m)), agree=int(agree.sum()), agree_pct=round(100 * agree.mean(), 1),
                   false_raise=int(false_raise.sum()),
                   missed_raise=int(((m["manual"] == "confirmed_raise") & (m["status"] != "confirmed_raise")).sum()),
                   confusion=pd.crosstab(m["manual"], m["status"]).to_dict())


def main(argv=None):
    from research.sp1500 import run as RUN
    ap = argparse.ArgumentParser()
    ap.add_argument("--packets", required=True)
    ap.add_argument("--labels", default=None, help="module with LABELS (e.g. research.event_base.manual_labels_v1)")
    ap.add_argument("--calendar", default="research/results/event_base/runs/2026-10-26T011603Z/equity_C_full_10bps.csv")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    root0 = Path(__file__).resolve().parents[2]
    packets = json.loads((Path(a.packets) / "packets.json").read_text())
    sessions = pd.to_datetime(pd.read_csv(root0 / a.calendar if not Path(a.calendar).is_absolute() else a.calendar,
                                          usecols=["date"])["date"])
    v2 = run(packets, sessions)
    out = Path(a.out).resolve() / datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    root = root0 if root0 in out.parents else Path(a.out).resolve()
    man = {}
    W = lambda n, b: RUN.write_once(out / n, b, man, root)                      # noqa: E731
    res = dict(version=VERSION, packets=str(a.packets), git=RUN._git_rev(), status_counts=v2["status"].value_counts().to_dict())
    if a.labels:
        m, cmp = compare(v2, importlib.import_module(a.labels).LABELS)
        res["comparison"] = cmp
        W("comparison.csv", RUN.csv_bytes(m))
    W("event_status_v2.csv", RUN.csv_bytes(v2))
    W("summary.json", json.dumps(res, indent=1, default=str))
    W("manifest.json", json.dumps(dict(files=dict(man)), indent=1))
    print(json.dumps(res, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
