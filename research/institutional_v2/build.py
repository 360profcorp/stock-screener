"""Build the v2 SEC tables (CORRECTION_V2.md) in the PR #20 table format.

    python -m research.institutional_v2.build --src V2SRC --acc V2ACC --old OLD_SEC_DIR \
        --features PR20_RUN_DIR --out TABLES_DIR --commit COMMIT_DIR

TABLES_DIR/v2/    f13_breadth.csv.gz, form4_buys.csv.gz, form4_filings.csv.gz, sources.json,
                  lags.json  (input of research/institutional/run.py)
TABLES_DIR/sens/  the same, but rows excluded by the registry keep their PR #20 value
                  (sensitivity only, never a decision input)
COMMIT_DIR/       security_sets.csv.gz, cik_map.csv.gz, registry_f2.csv, registry_cik.csv,
                  acceptance_13f.json, form4_acceptance.csv, build.json
"""
import argparse
import json
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd

from research.institutional_v2 import mapping as M
from research.institutional_v2.accept import FastFetcher, parse_index_accepted

FTD_URL = "https://www.sec.gov/files/data/fails-deliver-data/"
EDGAR_CO = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK="
F1_DAYS = 90


def load(src, acc):
    s = Path(src)
    ftd = pd.read_csv(s / "ftd.csv.gz", dtype=str, parse_dates=["date"])
    sub = pd.read_csv(s / "f345_sub.csv.gz", dtype=str, parse_dates=["filing_date"])
    buys = pd.read_csv(s / "f345_buys.csv.gz", dtype=str, parse_dates=["trans_date"])
    lists = pd.read_csv(s / "lists13f.csv.gz", dtype=str)
    edgar = json.loads((s / "edgar_names.json").read_text())
    fl = pd.read_csv(s / "f13_filings.csv.gz", dtype={"cik": str, "acc": str}, parse_dates=["filing_date", "period"])
    h = np.load(s / "f13_hold.npz", allow_pickle=False)
    syms = json.loads((s / "study_symbols.json").read_text())
    pit = pd.read_csv(s / "sp500_pit.csv")
    A = pd.read_csv(Path(acc) / "acceptance.csv.gz", dtype={"acc": str, "cik": str}, parse_dates=["accepted_et"])
    return ftd, sub, buys, lists, edgar, fl, h, syms, pit, A


def nsym(t):
    return str(t).strip().upper().replace(".", "-").replace("/", "-")


def membership(pit):
    pit = pit.copy()
    pit["date"] = pd.to_datetime(pit["date"])
    pit = pit.sort_values("date")
    return [(d, {nsym(t) for t in str(s).split(",") if t.strip()}) for d, s in zip(pit["date"], pit["tickers"])]


def member_between(snaps, sym, lo, hi):
    """Was `sym` an index member under any snapshot in force during [lo, hi]? (the last
    snapshot on or before lo, and every snapshot inside the window)"""
    before = None
    for d, s in snaps:
        if d <= lo:
            before = s
        elif d <= hi:
            if sym in s:
                return True
        else:
            break
    return bool(before and sym in before)


def main(argv=None):
    ap = argparse.ArgumentParser()
    for k in ("--src", "--acc", "--old", "--features", "--out", "--commit"):
        ap.add_argument(k, required=True)
    a = ap.parse_args(argv)
    t0 = time.time()
    out, com = Path(a.out), Path(a.commit)
    for d in (out / "v2", out / "sens", com):
        d.mkdir(parents=True, exist_ok=True)
    ftd, sub, buys, lists, edgar, fl, h, syms, pit, A = load(a.src, a.acc)
    recs, names = M.SymbolRecords(ftd), M.ListNames(lists)
    snaps = membership(pit)
    S = dict()

    # ---------------------------------------------------------------- 13F acceptance (§3)
    fl["idx"] = np.arange(len(fl))
    fl = fl.merge(A[["acc", "accepted_et", "edgar_filing_date"]], on="acc", how="left")
    fl["usable_from"] = fl["period"] + pd.Timedelta(days=M.DEADLINE + 1)
    fl["ok"] = fl["accepted_et"].notna() & (fl["accepted_et"] < fl["usable_from"])
    late = fl[fl["accepted_et"].notna() & ~fl["ok"]]
    S["acceptance_13f"] = dict(counted_filings=int(len(fl)), with_timestamp=int(fl["accepted_et"].notna().sum()),
                               without_timestamp=int(fl["accepted_et"].isna().sum()),
                               accepted_on_or_after_usable_from=int(len(late)), used=int(fl["ok"].sum()),
                               edgar_filing_date_differs=int((fl["edgar_filing_date"].notna() &
                                                              (pd.to_datetime(fl["edgar_filing_date"]) != fl["filing_date"])).sum()))
    late.head(2000)[["acc", "cik", "filing_date", "period", "accepted_et", "usable_from", "zip"]].to_csv(
        com / "acceptance_13f_excluded_late.csv", index=False)
    fl[fl["accepted_et"].isna()].head(2000)[["acc", "cik", "filing_date", "period", "zip"]].to_csv(
        com / "acceptance_13f_no_timestamp.csv", index=False)
    fl = fl.sort_values("idx").reset_index(drop=True)
    acc_i, cus_i, cusips = h["acc"], h["cusip"], list(h["cusips"])
    cidx = {c: i for i, c in enumerate(cusips)}
    fidx = {c: i for i, c in enumerate(sorted(set(fl["cik"])))}
    f_of = fl["cik"].map(fidx).values.astype("int64")
    p_of = fl["period"].values
    ok_of = fl["ok"].values
    periods = sorted(pd.Timestamp(p) for p in set(fl["period"]) if pd.Timestamp(p) >= pd.Timestamp("2015-12-31"))
    filers = {p: np.unique(f_of[(p_of == np.datetime64(p)) & ok_of]) for p in periods}
    keep = ok_of[acc_i]
    per_h = {}
    for p in periods:
        m = keep & (p_of[acc_i] == np.datetime64(p))
        f, c = f_of[acc_i[m]], cus_i[m].astype("int64")
        o = np.lexsort((f, c))
        f, c = f[o], c[o]
        b = np.flatnonzero(np.diff(c)) + 1
        per_h[p] = {int(c[s]): np.unique(f[s:e]) for s, e in zip(np.r_[0, b], np.r_[b, len(c)]) if e > s}
    fh = pd.Series(p_of[acc_i]).groupby(cus_i).min()
    first_hold = {cusips[int(ci)]: pd.Timestamp(v) for ci, v in fh.items()}
    first_seen = {c: min(recs.first.get(c, pd.Timestamp.max), first_hold.get(c, pd.Timestamp.max)) for c in cusips}

    # ---------------------------------------------------------------- F2 rows (§1)
    rows, sets_, reg = [], [], []
    for sym in syms:
        for q1, q in zip(periods[:-1], periods[1:]):
            if (q - q1).days > 100:
                continue
            r = M.classify_row(sym, q1, q, recs, names, first_seen)
            if r["status"] == "no_symbol_record":
                continue
            use_lo, use_hi = q + pd.Timedelta(days=M.DEADLINE + 1), q + pd.Timedelta(days=M.DEADLINE + 1 + M.USE_DAYS)
            mem = member_between(snaps, sym, use_lo, use_hi)
            ev = "; ".join(f"{c} {v[0].date()}..{v[1].date()} n={v[2]}" for c, v in sorted(r["evidence"].items()))
            nm = "; ".join(f"{c}={n} [{src}]" for c, (n, src) in sorted(r["names"].items()))
            common = np.intersect1d(filers.get(q, np.array([], "int64")), filers.get(q1, np.array([], "int64")))
            hq = hq1 = None
            if r["status"] == "ok":
                si = [cidx[c] for c in r["cusips"] if c in cidx]
                hq, hq1 = M.holders(si, per_h.get(q, {}), common), M.holders(si, per_h.get(q1, {}), common)
                if hq or hq1:
                    rows.append(dict(ticker=sym, period=q.date(), usable_from=use_lo.date(), holders_q=hq,
                                     holders_q1=hq1, common_filers=int(len(common)),
                                     breadth_change=(hq - hq1) / hq1 if hq1 else np.nan))
            sets_.append(dict(ticker=sym, period=q.date(), status=r["status"], member_in_use_window=mem,
                              cusips=",".join(r["cusips"]), names=nm, ftd_evidence=ev, holders_q=hq, holders_q1=hq1))
            if r["status"] in ("several_issuers", "new_cusip"):
                files = sorted({f for v in r["evidence"].values() for f in v[3] if isinstance(f, str) and f})
                srcs = [FTD_URL + f for f in files[:6]] + sorted({src for _, src in r["names"].values() if src})
                reg.append(dict(kind="F2 security set", ticker=sym, period=q.date(), status=r["status"],
                                member_in_use_window=mem, cusips=",".join(r["cusips"]),
                                new_cusips=",".join(r.get("new", [])),
                                first_seen=",".join(f"{c}:{first_seen.get(c).date()}" for c in r.get("new", [])),
                                names=nm, ftd_evidence=ev, sources=" | ".join(srcs),
                                verification="excluded; not assigned automatically; pending review"))
    B2 = pd.DataFrame(rows)
    SS = pd.DataFrame(sets_)
    SS.to_csv(com / "security_sets.csv.gz", index=False)
    pd.DataFrame(reg).to_csv(com / "registry_f2.csv", index=False)
    S["f2_rows"] = dict(rows=int(len(B2)), sets_by_status=SS["status"].value_counts().to_dict(),
                        member_sets_by_status=SS[SS["member_in_use_window"]]["status"].value_counts().to_dict())
    print("F2 done", round(time.time() - t0), flush=True)

    # ---------------------------------------------------------------- CIK map (§2)
    sub["q"] = sub["filing_date"].dt.to_period("Q")
    sub["issuer_cik"] = sub["issuer_cik"].astype(str)
    cand = {}
    for (s_, q_, c_), n in sub.groupby(["sym", "q", "issuer_cik"]).size().items():
        cand.setdefault((s_, q_), {})[c_] = int(n)
    f4names = {}
    for c_, q_, n_ in sub[["issuer_cik", "q", "issuer_name"]].drop_duplicates().itertuples(index=False):
        f4names.setdefault((c_, q_), set()).add(n_)
    quarters = pd.period_range("2015Q3", "2026Q4", freq="Q")
    cmap, regc = [], []
    for sym in syms:
        qs = {q_ for (s_, q_) in cand if s_ == sym}
        for k in quarters:
            if not any((k + d) in qs for d in range(-2, 3)):
                continue
            r = M.assign_cik(sym, k, cand, recs, names, edgar, f4names)
            lo, hi = k.start_time, k.end_time.normalize() + pd.Timedelta(days=F1_DAYS)
            mem = member_between(snaps, sym, lo, hi)
            cs = "; ".join(f"{c}({n}) {sorted(M.cik_names(c, edgar, f4names, k.end_time.normalize()))[:2]}"
                           for c, n in sorted(r["candidates"].items(), key=lambda x: -x[1])[:5])
            cmap.append(dict(ticker=sym, quarter=str(k), status=r["status"], cik=r["cik"], member=mem,
                             candidates=cs, security_names="; ".join(f"{c}={n}" for c, n in
                                                                     sorted((r.get("security_names") or {}).items()))))
            if r["status"] != "ok" and mem:
                regc.append(dict(kind="F1 issuer", ticker=sym, quarter=str(k), status=r["status"], member=mem,
                                 candidates=cs, confirmed=",".join(r.get("confirmed", [])),
                                 security_names=cmap[-1]["security_names"],
                                 sources=" | ".join(EDGAR_CO + c for c in list(r["candidates"])[:5]),
                                 verification="excluded; not assigned automatically; pending review"))
    CM = pd.DataFrame(cmap)
    CM.to_csv(com / "cik_map.csv.gz", index=False)
    pd.DataFrame(regc).to_csv(com / "registry_cik.csv", index=False)
    S["cik_map"] = dict(rows=int(len(CM)), by_status=CM["status"].value_counts().to_dict(),
                        member_by_status=CM[CM["member"]]["status"].value_counts().to_dict())
    print("CIK done", round(time.time() - t0), flush=True)

    # ---------------------------------------------------------------- Form 4 attribution
    okm = CM[CM["status"] == "ok"]
    owner = {}
    for t_, k_, c_ in okm[["ticker", "quarter", "cik"]].itertuples(index=False):
        owner.setdefault((str(c_), k_), []).append(t_)
    s4 = sub[sub["doc_type"] == "4"].copy()
    s4["k"] = s4["q"].astype(str)
    s4["tickers"] = [owner.get((c_, k_), []) for c_, k_ in zip(s4["issuer_cik"], s4["k"])]
    s4 = s4.explode("tickers").dropna(subset=["tickers"]).rename(columns={"tickers": "ticker"})
    fil = s4.groupby(["ticker", "filing_date"]).size().rename("n").reset_index()
    by = buys.merge(s4[["acc", "ticker", "filing_date", "issuer_cik"]], on="acc")
    by = by.rename(columns={"acc": "ACCESSION_NUMBER"})[["ticker", "filing_date", "owner_cik", "trans_date",
                                                         "ACCESSION_NUMBER", "issuer_cik"]]

    # acceptance of every purchase used by an F1 value (§3)
    fe = pd.concat([pd.read_csv(Path(a.features) / f"features_{st}.csv", usecols=["ticker", "signal_date"],
                                parse_dates=["signal_date"]) for st in ("breakout", "retest")]).drop_duplicates()
    sd = {t_: np.sort(g["signal_date"].values.astype("datetime64[ns]")) for t_, g in fe.groupby("ticker")}
    first_use = []
    for fd, t_ in zip(by["filing_date"], by["ticker"]):
        x = sd.get(t_)
        k_ = np.searchsorted(x, np.datetime64(fd), side="right") if x is not None else 0
        first_use.append(pd.Timestamp(x[k_]) if x is not None and k_ < len(x) and
                         (pd.Timestamp(x[k_]) - fd).days <= F1_DAYS else pd.NaT)
    by["first_use"] = first_use
    used = by.dropna(subset=["first_use"]).drop_duplicates("ACCESSION_NUMBER")
    F = FastFetcher()
    chk = []
    for r in used.itertuples(index=False):
        url = (f"https://www.sec.gov/Archives/edgar/data/{int(r.issuer_cik)}/"
               f"{r.ACCESSION_NUMBER.replace('-', '')}/{r.ACCESSION_NUMBER}-index.htm")
        b = F.get(url)
        acc_t, fdi = parse_index_accepted(b.decode("utf-8", "replace")) if b else (None, None)
        chk.append(dict(ACCESSION_NUMBER=r.ACCESSION_NUMBER, ticker=r.ticker, filing_date=r.filing_date.date(),
                        first_use=r.first_use.date(), accepted_et=acc_t, index_filing_date=fdi, url=url))
    CK = pd.DataFrame(chk, columns=["ACCESSION_NUMBER", "ticker", "filing_date", "first_use", "accepted_et",
                                    "index_filing_date", "url"])
    CK.to_csv(com / "form4_acceptance.csv", index=False)
    acc_map = dict(zip(CK["ACCESSION_NUMBER"], pd.to_datetime(CK["accepted_et"])))
    by["accepted_et"] = by["ACCESSION_NUMBER"].map(acc_map)
    # rule: usable on d only if filing date < d and accepted < 00:00 ET of d
    #       <=> d > max(filing date, acceptance date); store that date for run.py's filing-date test
    by["effective_date"] = [max(fd, at.normalize()) if pd.notna(at) else fd
                            for fd, at in zip(by["filing_date"], by["accepted_et"])]
    unver = by["first_use"].notna() & by["accepted_et"].isna()
    S["form4_acceptance"] = dict(used_purchase_filings=int(len(used)), fetched=int(CK["accepted_et"].notna().sum()),
                                 unverifiable_rows_excluded=int(unver.sum()),
                                 accepted_after_filing_date=int((by["accepted_et"].notna() &
                                                                 (by["accepted_et"].dt.normalize() > by["filing_date"])).sum()))
    by = by[~unver]
    buys_v2 = by.assign(filing_date=by["effective_date"])[["ticker", "filing_date", "owner_cik", "trans_date",
                                                          "ACCESSION_NUMBER"]].drop_duplicates()

    # ---------------------------------------------------------------- write v2 + sensitivity
    lags = dict(form4_filing_minus_transaction_days=describe((by["filing_date"] - by["trans_date"]).dt.days),
                f13_filing_minus_period_end_days=describe((fl.loc[fl["ok"], "filing_date"] -
                                                           fl.loc[fl["ok"], "period"]).dt.days))
    info = dict(version="v2", study_tickers=len(syms), f13_breadth_rows=int(len(B2)), form4_buy_rows=int(len(buys_v2)),
                form4_filing_days=int(len(fil)), **{k: v for k, v in S.items() if not isinstance(v, dict)})
    write(out / "v2", B2, buys_v2, fil, info, lags)
    old_b = pd.read_csv(Path(a.old) / "f13_breadth.csv.gz", parse_dates=["period", "usable_from"])
    old_4 = pd.read_csv(Path(a.old) / "form4_buys.csv.gz", dtype={"owner_cik": str}, parse_dates=["filing_date", "trans_date"])
    old_f = pd.read_csv(Path(a.old) / "form4_filings.csv.gz", parse_dates=["filing_date"])
    regf = SS[SS["status"].isin(["several_issuers", "new_cusip"])][["ticker", "period"]].astype(str)
    key = set(zip(regf["ticker"], regf["period"]))
    add = old_b[[(t_, str(p_.date())) in key for t_, p_ in zip(old_b["ticker"], old_b["period"])]]
    Bs = pd.concat([B2.assign(period=pd.to_datetime(B2["period"]), usable_from=pd.to_datetime(B2["usable_from"])), add])
    regk = set(zip(CM.loc[CM["status"] != "ok", "ticker"], CM.loc[CM["status"] != "ok", "quarter"]))
    o4 = old_4[[(t_, str(fd.to_period("Q"))) in regk for t_, fd in zip(old_4["ticker"], old_4["filing_date"])]]
    of = old_f[[(t_, str(fd.to_period("Q"))) in regk for t_, fd in zip(old_f["ticker"], old_f["filing_date"])]]
    write(out / "sens", Bs, pd.concat([buys_v2, o4[buys_v2.columns]]).drop_duplicates(),
          pd.concat([fil, of]).groupby(["ticker", "filing_date"])["n"].sum().reset_index(),
          dict(info, version="v2-sensitivity", note="registry exclusions keep their PR #20 value"), lags)
    S["sensitivity_added"] = dict(f2_rows=int(len(add)), form4_rows=int(len(o4)))
    S["runtime_sec"] = round(time.time() - t0)
    (com / "build.json").write_text(json.dumps(S, indent=1, default=str))
    print(json.dumps(S, indent=1, default=str))
    return 0


def describe(s):
    s = pd.Series(s).dropna()
    if not len(s):
        return {}
    q = s.quantile([.01, .5, .9, .99]).round(1).to_dict()
    return dict(n=int(len(s)), min=float(s.min()), p01=q[.01], median=q[.5], p90=q[.9], p99=q[.99],
                max=float(s.max()), negative=int((s < 0).sum()))


def write(d, B, buys, fil, info, lags):
    B = B.copy()
    B["period"] = pd.to_datetime(B["period"]).dt.date
    B["usable_from"] = pd.to_datetime(B["usable_from"]).dt.date
    B.to_csv(d / "f13_breadth.csv.gz", index=False)
    buys.to_csv(d / "form4_buys.csv.gz", index=False)
    fil.to_csv(d / "form4_filings.csv.gz", index=False)
    (d / "sources.json").write_text(json.dumps(dict(info=info), indent=1, default=str))
    (d / "lags.json").write_text(json.dumps(lags, indent=1, default=str))


if __name__ == "__main__":
    raise SystemExit(main())
