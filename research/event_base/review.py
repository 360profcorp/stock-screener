"""Review packets for the manual relabelling of the 80 E pilot cases (REVIEW_PLAN.md §2).
Text only: no prices or returns are loaded.

    python -m research.event_base.review --events DIR --docs DIR --out DIR

For each case: every 8-K (Items 2.02, 7.01, 8.01) of the issuer accepted from base_start - 520
days to the signal date; for each document the text windows around outlook words that also
mention revenue / sales. Saved EX-99 exhibits are read from --docs (by SHA256); anything else is
fetched from EDGAR and saved there.
"""
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from research.event_base import events as EV

ANCHOR = re.compile(r"outlook|guidance|expects?\b|expected|expecting|anticipat\w*|forecast\w*|now sees|reaffirm\w*|"
                    r"full[- ]year|fiscal(?: year)? ?'?20\d\d|\bFY ?'?\d\d|\braises?\b|\braising\b|narrow\w*", re.I)
REVW = re.compile(r"\b(revenues?|net sales|sales|net revenue)\b", re.I)
GUIDEW = re.compile(r"outlook|guidance", re.I)
LOOK_DAYS = 520


def windows(text, before=300, after=450, cap=14):
    spans = []
    for m in ANCHOR.finditer(text):
        a, b = max(0, m.start() - before), min(len(text), m.end() + after)
        w = text[a:b]
        if REVW.search(w) and re.search(r"\$|%", w):
            if spans and a <= spans[-1][1]:
                spans[-1] = (spans[-1][0], b)
            else:
                spans.append((a, b))
    out = [text[a:b] for a, b in spans]
    out.sort(key=lambda w: (0 if "$" in w else 1))
    return out[:cap], len(spans)


def index_docs(ed, cik, acc):
    nod = acc.replace("-", "")
    idx = ed.get(f"https://www.sec.gov/Archives/edgar/data/{cik}/{nod}/{acc}-index.htm")
    if idx is None:
        return None
    h = idx.decode("utf-8", "replace")
    rows = re.findall(r'<a href="(/Archives/edgar/data/[^"]+)">[^<]*</a>\s*</td>\s*<td[^>]*>\s*([^<]*)</td>', h, re.I)
    return [("https://www.sec.gov" + href, typ.strip()) for href, typ in rows]


def main(argv=None):
    from research.sp1500 import run as RUN
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", required=True)
    ap.add_argument("--docs", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    ev = Path(a.events)
    st = pd.read_csv(ev / "event_status.csv", parse_dates=["signal_date", "base_start"])
    reg = pd.read_csv(ev / "source_registry.csv")
    docs = Path(a.docs)
    docs.mkdir(parents=True, exist_ok=True)
    have = {p.stem for p in docs.rglob("*.htm")}
    ed = EV.Edgar(docs)
    out = Path(a.out).resolve() / datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    root0 = Path(__file__).resolve().parents[2]
    root = root0 if root0 in out.parents else Path(a.out).resolve()
    man, packets, docrows = {}, [], []
    W = lambda n, b: RUN.write_once(out / n, b, man, root)                      # noqa: E731
    subs = {}
    text_cache = {}

    def doc_text(url, sha=None):
        if sha and sha in have:
            b = next(docs.rglob(f"{sha}.htm")).read_bytes()
        else:
            b = ed.get(url)
            if b is None:
                return None, None
            sha = hashlib.sha256(b).hexdigest()
            (docs / f"{sha}.htm").write_bytes(b)
            have.add(sha)
        if sha not in text_cache:
            text_cache[sha] = EV.html_to_text(b)
        return text_cache[sha], sha

    for n, c in enumerate(st.to_dict("records")):
        cik = int(c["cik"]) if pd.notna(c["cik"]) else None
        case = dict(case=n, ticker=c["ticker"], issuer=c.get("issuer_name"), cik=cik,
                    base_start=str(c["base_start"].date()), signal_date=str(c["signal_date"].date()),
                    fiscal_year_end=c.get("fiscal_year_end"), auto_status=c["status"], auto_reason=c["reason"],
                    filings=[])
        if cik is None:
            packets.append(case)
            continue
        if cik not in subs:
            subs[cik] = ed.submissions(cik)
        sub = subs[cik]
        if sub is None or sub.get("filings") is None:
            case["error"] = "submissions_not_retrieved"
            packets.append(case)
            continue
        f = sub["filings"]
        f = f[f["form"].isin(["8-K", "8-K/A"]) & f["items"].fillna("").str.contains(r"2\.02|7\.01|8\.01")].copy()
        f["accepted"] = pd.to_datetime(f["acceptanceDateTime"], utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
        f = f[(f["accepted"] >= c["base_start"] - pd.Timedelta(days=LOOK_DAYS)) & (f["accepted"] < c["signal_date"])]
        for r in f.sort_values("accepted").to_dict("records"):
            acc = r["accessionNumber"]
            fl = dict(accession=acc, form=r["form"], items=r["items"], accepted_et=str(r["accepted"]), documents=[])
            saved = reg[reg["accession"] == acc]
            if len(saved):
                targets = [(u, t, s) for u, t, s in zip(saved["url"], saved["exhibit_type"], saved["sha256"])]
            else:
                idx = index_docs(ed, cik, acc)
                if idx is None:
                    fl["error"] = "index_not_retrieved"
                    case["filings"].append(fl)
                    continue
                ex = [(u, t, None) for u, t in idx if t.upper().startswith("EX-99")]
                if not ex and "2.02" in str(r["items"]):
                    ex = [(u, t, None) for u, t in idx if t.upper() in ("8-K", "8-K/A") and u.lower().endswith((".htm", ".html", ".txt"))]
                    fl["note"] = "no EX-99 exhibit; primary 8-K document used"
                fl["index_types"] = sorted({t for _, t in idx})
                targets = ex
            for url, typ, sha in targets:
                txt, sha2 = doc_text(url, sha)
                if txt is None:
                    fl["documents"].append(dict(url=url, type=typ, error="not_retrieved"))
                    continue
                ws, nspan = windows(txt)
                d = dict(url=url, type=typ, sha256=sha2, chars=len(txt), guidance_words=len(GUIDEW.findall(txt)),
                         windows_total=nspan, windows=ws)
                fl["documents"].append(d)
                docrows.append(dict(case=n, cik=cik, accession=acc, items=r["items"], accepted_et=str(r["accepted"]),
                                    url=url, type=typ, sha256=sha2, chars=len(txt), guidance_words=d["guidance_words"],
                                    windows=nspan))
            case["filings"].append(fl)
        packets.append(case)
        print(f"case {n} {c['ticker']}: {len(case['filings'])} filings", flush=True)
    W("packets.json", json.dumps(packets, indent=1, default=str))
    W("documents.csv", RUN.csv_bytes(pd.DataFrame(docrows)))
    W("fetch_log.csv", RUN.csv_bytes(pd.DataFrame(ed.log)))
    md = []
    for p in packets:
        md.append(f"\n\n# Case {p['case']}: {p['ticker']} — {p.get('issuer')} (CIK {p['cik']})\n"
                  f"base_start {p['base_start']}, signal {p['signal_date']}, FYE {p.get('fiscal_year_end')}; "
                  f"automated: {p['auto_status']} / {p['auto_reason']}\n")
        for fl in p["filings"]:
            md.append(f"\n## {fl['accepted_et']} {fl['form']} items {fl['items']} {fl['accession']} {fl.get('note', '')}"
                      f"{' ERROR ' + fl['error'] if 'error' in fl else ''}")
            if "2.02" not in str(fl["items"]) and not any(d.get("windows") for d in fl["documents"]):
                md.append("(no revenue/outlook text)")
                continue
            for d in fl["documents"]:
                md.append(f"- {d.get('type')} {d.get('url')} sha {str(d.get('sha256'))[:12]} chars {d.get('chars')} "
                          f"guidance-words {d.get('guidance_words')} windows {d.get('windows_total')}"
                          f"{' ERROR ' + d['error'] if 'error' in d else ''}")
                for w in d.get("windows", []):
                    md.append("  > " + w.replace("\n", " "))
    W("packets.md", "\n".join(md) + "\n")
    W("manifest.json", json.dumps(dict(files=dict(man)), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
