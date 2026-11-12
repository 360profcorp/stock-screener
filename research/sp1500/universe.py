"""S&P Composite 1500 universe: S&P 500 + MidCap 400 + SmallCap 600.

Sources, in order (every attempt is recorded in the snapshot):
  1. iShares ETF holdings CSV (dated "as of"): IVV (500), IJH (400), IJR (600)
  2. Wikipedia constituent lists (retrieval time only; change tables are dated)
Overlaps (a ticker in two lists) are resolved only with DATED evidence:
  - holdings as-of dates (the newer list wins), else
  - the latest dated change-table event (added / removed) naming the ticker;
  otherwise the ticker stays flagged `ambiguous` (kept, counted once, excluded from
  single-group comparisons).
Point-in-time membership is reconstructed from dated change tables where they exist
(S&P 500 on Wikipedia); groups without one carry `survivorship_bias=True`.
"""
import hashlib
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

UA = {"User-Agent": "Mozilla/5.0 (research; stock-screener)"}
GROUPS = ("sp500", "sp400", "sp600")
ISHARES = {
    "sp500": "https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf/"
             "1467271812596.ajax?fileType=csv&fileName=IVV_holdings&dataType=fund",
    "sp400": "https://www.ishares.com/us/products/239763/ishares-core-sp-midcap-etf/"
             "1467271812596.ajax?fileType=csv&fileName=IJH_holdings&dataType=fund",
    "sp600": "https://www.ishares.com/us/products/239774/ishares-core-sp-smallcap-etf/"
             "1467271812596.ajax?fileType=csv&fileName=IJR_holdings&dataType=fund",
}
WIKI = {
    "sp500": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
    "sp400": "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies",
    "sp600": "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies",
}


def norm_ticker(t) -> str:
    """Yahoo style: BRK.B -> BRK-B, strip spaces."""
    return str(t).strip().upper().replace(".", "-").replace(" ", "")


# ---------------------------------------------------------------- iShares holdings
def parse_ishares(text: str) -> tuple:
    """Return (DataFrame[ticker, name, sector], as_of date or None) from an iShares CSV."""
    lines = text.splitlines()
    as_of = None
    for ln in lines[:12]:
        m = re.search(r"as of[^A-Za-z0-9]*([A-Za-z]{3,9} \d{1,2}, \d{4})", ln, re.I)
        if m:
            as_of = pd.to_datetime(m.group(1)).date()
            break
    start = next((k for k, ln in enumerate(lines)
                  if ln.lstrip('\ufeff\xa0 "').startswith("Ticker")), None)
    if start is None:
        raise ValueError("no Ticker header in iShares file; starts with "
                         + repr(text[:160]))
    body = "\n".join([lines[start].lstrip('\ufeff\xa0 ')] + lines[start + 1:])
    df = pd.read_csv(io.StringIO(body), on_bad_lines="skip")
    if "Asset Class" in df:
        df = df[df["Asset Class"].astype(str).str.strip() == "Equity"]
    df = df[df["Ticker"].notna() & (df["Ticker"].astype(str).str.strip() != "-")]
    out = pd.DataFrame({"ticker": df["Ticker"].map(norm_ticker),
                        "name": df.get("Name", ""),
                        "sector": df.get("Sector", "")})
    return out.drop_duplicates("ticker").reset_index(drop=True), as_of


# ---------------------------------------------------------------- Wikipedia
def describe_tables(html: str) -> list:
    """Diagnostics: columns and first row of every HTML table (for the snapshot)."""
    out = []
    try:
        for t in pd.read_html(io.StringIO(html)):
            cols = [" ".join(map(str, c)) if isinstance(c, tuple) else str(c) for c in t.columns]
            out.append(dict(columns=cols, rows=len(t),
                            first=[str(v)[:40] for v in t.iloc[0].tolist()] if len(t) else []))
    except Exception as e:
        out.append(dict(error=f"{type(e).__name__}: {e}"[:200]))
    return out


def parse_wiki(html: str) -> tuple:
    """(constituents DataFrame[ticker, name, sector], changes DataFrame[date, added, removed])."""
    tables = pd.read_html(io.StringIO(html))
    cons, changes = None, None
    for t in tables:
        cols = [" ".join(map(str, c)) if isinstance(c, tuple) else str(c) for c in t.columns]
        low = [c.lower() for c in cols]
        if cons is None and any(c in ("symbol", "ticker symbol", "ticker") for c in low):
            t.columns = cols
            sym = cols[low.index(next(c for c in low if c in ("symbol", "ticker symbol",
                                                                  "ticker")))]
            name = next((c for c in cols if c.lower() in ("security", "company")), None)
            sec = next((c for c in cols if "gics sector" in c.lower()), None)
            cons = pd.DataFrame({"ticker": t[sym].map(norm_ticker),
                                 "name": t[name] if name else "",
                                 "sector": t[sec] if sec else ""})
        elif changes is None and any("date" in c for c in low) and \
                any("added" in c for c in low) and any("removed" in c for c in low):
            t.columns = cols
            dcol = next(c for c in cols if "date" in c.lower())
            add = next(c for c in cols if "added" in c.lower() and
                       ("ticker" in c.lower() or "symbol" in c.lower()))
            rem = next(c for c in cols if "removed" in c.lower() and
                       ("ticker" in c.lower() or "symbol" in c.lower()))
            dates = t[dcol].astype(str).str.replace(r"\[.*?\]", "", regex=True).str.strip()
            changes = pd.DataFrame({"date": pd.to_datetime(dates, errors="coerce",
                                                           format="mixed"),
                                    "added": t[add].map(lambda v: norm_ticker(v)
                                                        if isinstance(v, str) else None),
                                    "removed": t[rem].map(lambda v: norm_ticker(v)
                                                          if isinstance(v, str) else None)})
            changes = changes.dropna(subset=["date"])
    if cons is None:
        raise ValueError("no constituents table")
    return cons.drop_duplicates("ticker").reset_index(drop=True), changes


# ---------------------------------------------------------------- overlap resolution
EVIDENCE_CSV = Path(__file__).with_name("membership_evidence.csv")
PIT500_API = "https://api.github.com/repos/fja05680/sp500/contents"


def load_evidence(path=EVIDENCE_CSV) -> pd.DataFrame:
    """Hand-checked dated index announcements (S&P DJI press releases) with source URLs."""
    if not Path(path).exists():
        return pd.DataFrame(columns=["effective_date", "ticker", "index", "action", "source"])
    ev = pd.read_csv(path)
    ev["effective_date"] = pd.to_datetime(ev["effective_date"])
    return ev


def resolve_overlaps(lists: dict, as_of: dict, changes: dict, evidence=None) -> pd.DataFrame:
    """
    lists: {group: set(tickers)}; as_of: {group: date|None}; changes: {group: DataFrame|None};
    evidence: optional DataFrame from load_evidence() (dated press releases).
    Returns DataFrame[ticker, groups_listed, group, resolution, evidence].
    """
    rows = []
    allt = sorted(set().union(*lists.values()))
    for t in allt:
        listed = [g for g in GROUPS if t in lists.get(g, set())]
        if len(listed) == 1:
            rows.append((t, listed[0], listed[0], "single", ""))
            continue
        # 1) dated holdings: newest as-of wins if dates differ
        dates = {g: as_of.get(g) for g in listed}
        if all(dates.values()) and len(set(dates.values())) > 1:
            g = max(listed, key=lambda k: dates[k])
            rows.append((t, "|".join(listed), g, "holdings_as_of",
                         json.dumps({k: str(v) for k, v in dates.items()})))
            continue
        # 2) latest dated change event naming the ticker
        ev = []
        for g in listed:
            ch = changes.get(g)
            if ch is None or not len(ch):
                continue
            for r in ch.itertuples():
                if r.added == t:
                    ev.append((r.date, g, "added"))
                if r.removed == t:
                    ev.append((r.date, g, "removed"))
        src = "change_table"
        if evidence is not None and len(evidence):
            pr = evidence[(evidence["ticker"] == t) & evidence["index"].isin(listed)]
            for r in pr.itertuples():
                ev.append((pd.Timestamp(r.effective_date), r.index, r.action))
            if len(pr):
                src = "press_release"
        if ev:
            d, g, kind = max(ev)
            target = g if kind == "added" else next((x for x in listed if x != g), None)
            if target:
                rows.append((t, "|".join(listed), target, src,
                             json.dumps([(str(a.date()), b, c) for a, b, c in sorted(ev)])))
                continue
        rows.append((t, "|".join(listed), "ambiguous", "unresolved", ""))
    return pd.DataFrame(rows, columns=["ticker", "groups_listed", "group", "resolution",
                                       "evidence"])


# ---------------------------------------------------------------- point-in-time
def pit_members(current: set, changes: pd.DataFrame, start, end) -> dict:
    """{date_str: set} membership at each change boundary, walking changes backwards from
    `current`. Use member_on(...) for a given day."""
    if changes is None or not len(changes):
        return None
    ch = changes[(changes["date"] > pd.Timestamp(start))].sort_values("date", ascending=False)
    cur = set(current)
    timeline = [(pd.Timestamp(end) + pd.Timedelta(days=1), set(cur))]
    for d, grp in ch.groupby("date", sort=False):
        added = set(grp["added"].dropna())
        removed = set(grp["removed"].dropna())
        cur = (cur - added) | removed            # membership just before date d
        timeline.append((d, set(cur)))
    return timeline                               # newest first: (boundary_date, members_before)


def parse_pit500(text: str) -> pd.DataFrame:
    """fja05680/sp500 'Historical Components & Changes' CSV: date, comma-separated tickers."""
    df = pd.read_csv(io.StringIO(text))
    df["date"] = pd.to_datetime(df["date"])
    df["members"] = df["tickers"].map(lambda s: {norm_ticker(t) for t in str(s).split(",")
                                                 if t.strip()})
    return df[["date", "members"]].sort_values("date").reset_index(drop=True)


def pit_from_snapshots(snaps: pd.DataFrame, current: set, end) -> list:
    """member_on()-compatible timeline from dated full-membership snapshots; after the last
    snapshot the current list applies (changes after it are therefore approximate)."""
    if snaps is None or not len(snaps):
        return None
    last = snaps.iloc[-1]
    tl = [(pd.Timestamp(end) + pd.Timedelta(days=1), set(current)),
          (last["date"] + pd.Timedelta(days=1), set(last["members"]))]
    for k in range(len(snaps) - 1, 0, -1):
        tl.append((snaps.iloc[k]["date"], set(snaps.iloc[k - 1]["members"])))
    return tl


def fetch_pit500(session=None, timeout=30) -> dict:
    """Newest 'S&P 500 Historical Components & Changes(MM-DD-YYYY).csv' (community dataset,
    not S&P). Never raises; the attempt is recorded."""
    s = session or requests.Session()
    rec = dict(group="sp500", source="pit_fja05680", url=PIT500_API, ok=False)
    try:
        r = s.get(PIT500_API, headers=UA, timeout=timeout)
        rec["http"] = r.status_code
        files = [f for f in r.json() if "Historical Components" in f.get("name", "")
                 and f["name"].endswith(".csv")]

        def stamp(f):
            m = re.search(r"(\d{2})-(\d{2})-(\d{4})", f["name"])
            return (m.group(3), m.group(1), m.group(2)) if m else ("0",)
        f = max(files, key=stamp)
        rec["url"] = f["download_url"]
        r = s.get(f["download_url"], headers=UA, timeout=timeout)
        rec["http"] = r.status_code
        rec["sha256"] = hashlib.sha256(r.content).hexdigest()
        rec["_raw"] = r.content
        snaps = parse_pit500(r.text)
        rec.update(ok=len(snaps) > 100, rows=len(snaps), first=str(snaps["date"].iloc[0].date()),
                   last=str(snaps["date"].iloc[-1].date()), _snaps=snaps)
    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    return rec


def member_on(timeline, day) -> set:
    """Members on `day` from a pit_members timeline (None -> unavailable)."""
    if timeline is None:
        return None
    day = pd.Timestamp(day)
    members = timeline[0][1]
    for d, before in timeline[1:]:
        if day < d:
            members = before
        else:
            break
    return members


# ---------------------------------------------------------------- fetch + snapshot
def fetch_all(session=None, timeout=30) -> dict:
    """Download all sources; never raises — failures are recorded."""
    s = session or requests.Session()
    out = {"retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "attempts": []}
    for g in GROUPS:
        for kind, url in (("ishares", ISHARES[g]), ("wikipedia", WIKI[g])):
            rec = dict(group=g, source=kind, url=url, ok=False)
            try:
                r = s.get(url, headers=UA, timeout=timeout)
                rec["http"] = r.status_code
                if r.status_code == 200:
                    rec["sha256"] = hashlib.sha256(r.content).hexdigest()
                    rec["_raw"] = r.content                  # saved verbatim in the snapshot
                    if kind == "ishares":
                        df, as_of = parse_ishares(r.text)
                        rec.update(ok=len(df) > 50, rows=len(df), as_of=str(as_of),
                                   _df=df, _as_of=as_of)
                    else:
                        rec["tables"] = describe_tables(r.text)
                        df, ch = parse_wiki(r.text)
                        rec.update(ok=len(df) > 50, rows=len(df), _df=df, _changes=ch,
                                   change_rows=0 if ch is None else len(ch))
            except Exception as e:                       # recorded, not raised
                rec["error"] = f"{type(e).__name__}: {str(e)[:200]}"
            out["attempts"].append(rec)
    out["attempts"].append(fetch_pit500(s, timeout))
    return out


def align_share_class(tickers, reference) -> dict:
    """iShares writes share classes without a separator (BRKB, BFB); map such a ticker to the
    reference spelling (BRK-B) when the reference list has exactly that form. {old: new}."""
    ref = set(reference)
    out = {}
    for t in tickers:
        if t in ref or len(t) < 3:
            continue
        cand = f"{t[:-1]}-{t[-1]}"
        if cand in ref:
            out[t] = cand
    return out


def removed_since(changes: pd.DataFrame, start, current: set) -> list:
    """Tickers removed from the index on/after `start` and not in it now (for PIT tests)."""
    if changes is None or not len(changes):
        return []
    ch = changes[changes["date"] >= pd.Timestamp(start)]
    return sorted(set(ch["removed"].dropna()) - set(current))


def build_universe(fetched: dict) -> tuple:
    """(universe DataFrame, meta dict). Prefers dated iShares lists, else Wikipedia."""
    lists, as_of, changes, names, sectors, source = {}, {}, {}, {}, {}, {}
    for g in GROUPS:
        ish = next((a for a in fetched["attempts"] if a["group"] == g and "_df" in a and
                    a["source"] == "ishares" and a["ok"]), None)
        wik = next((a for a in fetched["attempts"] if a["group"] == g and "_df" in a and
                    a["source"] == "wikipedia" and a["ok"]), None)
        pick = ish or wik
        if pick is None:
            continue
        df = pick["_df"].copy()
        if ish and wik:
            df["ticker"] = df["ticker"].replace(align_share_class(df["ticker"],
                                                                  wik["_df"]["ticker"]))
        lists[g] = set(df["ticker"])
        as_of[g] = pick.get("_as_of")
        source[g] = pick["source"]
        changes[g] = wik.get("_changes") if wik else None
        wsec = dict(zip(wik["_df"]["ticker"], wik["_df"]["sector"])) if wik else {}
        for r in df.itertuples():
            names.setdefault(r.ticker, r.name)
            sectors.setdefault(r.ticker, wsec.get(r.ticker) or r.sector)  # GICS name if known
    evidence = load_evidence()
    res = resolve_overlaps(lists, as_of, changes, evidence)
    res["name"] = res["ticker"].map(names)
    res["sector"] = res["ticker"].map(sectors)
    meta = dict(retrieved_at=fetched["retrieved_at"],
                sources={g: dict(source=source.get(g), as_of=str(as_of.get(g)),
                                 count=len(lists.get(g, ())),
                                 has_change_table=changes.get(g) is not None)
                         for g in GROUPS},
                overlaps=res[res["resolution"] != "single"].to_dict("records"),
                survivorship_bias={g: True for g in GROUPS},   # current lists
                change_table={g: changes.get(g) is not None for g in GROUPS},
                attempts=[{k: v for k, v in a.items() if not k.startswith("_")}
                          for a in fetched["attempts"]],
                missing_groups=[g for g in GROUPS if g not in lists])
    return res, meta, changes
