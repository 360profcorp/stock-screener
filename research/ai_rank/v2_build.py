"""AI ranking v2 — dataset build per PREREG v2.1 (NO model training in this module).

    python -m research.ai_rank.v2_build --dataset DIR [--earnings-json FILE]

Builds, for the PIT S&P 500 eligible long pool (retest = deciding task; all four long setups
kept for the secondary report):
  v1 features (pipeline.MODEL_FEATURES) + v2 features (PREREG §2):
    sess_since_earn, earn_within_5 (sensitivity only — flagged look-ahead),
    sector_rs_median, sector_ret20_median, rs_minus_sector,
    breadth_ma50, breadth_new_high, breadth_chg5
  + split (purged by label end), label_end, target (net_r_base).
Every feature uses data <= the signal-day close. Self-checks recompute samples from data cut
at the signal day and verify PIT membership against the PR #5 dataset.
Outputs: dataset_v2.csv.gz + earnings_raw.json -> dist/ai_rank_v2/<run>/ (artifact);
build_report.json + BUILD_REPORT.md -> research/results/ai_rank/v2_build/<run>/ (committed).
"""
import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from research.ai_rank import pipeline as P
from research.sp1500 import engine as E
from research.sp1500 import run as RUN
from research.sp1500 import universe as U

ROOT = Path(__file__).resolve().parents[2]
PR5_RUN = ROOT / "research/results/sp1500/runs/2026-10-15T1656Z"
V0, T0 = pd.Timestamp("2025-03-17"), pd.Timestamp("2025-12-30")     # PREREG §0
V2_FEATURES = ["sess_since_earn", "sector_rs_median", "sector_ret20_median",
               "rs_minus_sector", "breadth_ma50", "breadth_new_high", "breadth_chg5"]
SENSITIVITY_ONLY = ["earn_within_5"]                                  # PREREG §2 (P1-1)
EARN_COVERAGE_MIN = 0.80                                              # PREREG §2


# =====================================================================
# point-in-time S&P 500 membership (same construction as PR #5)
# =====================================================================
def pit_timeline(dataset_dir, end):
    src = next(Path(dataset_dir).rglob("sp500_pit_fja05680.csv"))
    snaps = U.parse_pit500(src.read_text())
    uni = pd.read_csv(PR5_RUN / "universe.csv")
    other = set(uni.loc[(uni["group"] != "sp500") & (uni["group"] != "ambiguous"), "ticker"])
    current = {t for t, gl in zip(uni["ticker"], uni["groups_listed"])
               if "sp500" in str(gl).split("|") and t not in other}
    sectors = dict(zip(uni["ticker"], uni["sector"].fillna("")))
    return U.pit_from_snapshots(snaps, current, end), sectors, \
        hashlib.sha256(src.read_bytes()).hexdigest()


# =====================================================================
# same-day RS ranks (computed on ALL eligible signals, before any closed/target filter)
# =====================================================================
def add_rs_ranks(pool: pd.DataFrame) -> pd.DataFrame:
    """rank_rs: percentile of RS among eligible signals of the SAME strategy on the same day
    (the deciding retest experiment ranks retests only among retests, as in v1).
    rank_rs_all: percentile among all eligible long setups of the day (secondary experiment)."""
    pool = pool.copy()
    pool["rank_rs"] = pool.groupby(["signal_date", "strategy"])["rs"].rank(pct=True)
    pool["rank_rs_all"] = pool.groupby("signal_date")["rs"].rank(pct=True)
    return pool


# =====================================================================
# breadth and sector (cross-sectional, PIT members, causal)
# =====================================================================
def market_tables(frames, mask, sectors):
    """Per day: breadth_ma50, breadth_new_high, breadth_chg5; per (day, sector):
    sector_rs_median, sector_ret20_median. Only PIT members with a bar that day count."""
    closes = pd.DataFrame({t: f["Close"] for t, f in frames.items()}).sort_index()
    mask = mask.reindex(index=closes.index, columns=closes.columns).fillna(False)
    ma50 = closes.rolling(50).mean()
    hi252 = closes.rolling(252).max()
    valid = mask & closes.notna()
    above = (closes > ma50) & ma50.notna() & valid
    newhi = (closes >= hi252) & hi252.notna() & valid
    n50 = (valid & ma50.notna()).sum(axis=1)
    n252 = (valid & hi252.notna()).sum(axis=1)
    br = pd.DataFrame({"breadth_ma50": above.sum(axis=1) / n50.replace(0, np.nan),
                       "breadth_new_high": newhi.sum(axis=1) / n252.replace(0, np.nan),
                       "breadth_members": valid.sum(axis=1)})
    br["breadth_chg5"] = br["breadth_ma50"] - br["breadth_ma50"].shift(5)
    score = E.rs_scores(frames).reindex(index=closes.index, columns=closes.columns)
    ret20 = closes / closes.shift(20) - 1
    sec = pd.Series(sectors).reindex(closes.columns).fillna("")
    rows = []
    for s in sorted(set(sec) - {""}):
        cols = list(sec.index[sec == s])
        m = mask[cols] & closes[cols].notna()
        rows.append(pd.DataFrame({"sector": s,
                                  "sector_rs_median": score[cols].where(m).median(axis=1),
                                  "sector_ret20_median": ret20[cols].where(m).median(axis=1),
                                  "sector_members": m.sum(axis=1)}))
    st = pd.concat(rows)
    st.index.name = "date"
    st = st.reset_index()
    return br, st, score


# =====================================================================
# earnings dates
# =====================================================================
def fetch_earnings(tickers, retries=3, pause=1.0, fetcher=None, log=print):
    """{ticker: [YYYY-MM-DD, ...]} past and scheduled report dates (New York date)."""
    if fetcher is None:
        import yfinance as yf

        def fetcher(t):
            df = yf.Ticker(t).get_earnings_dates(limit=60)
            if df is None or df.empty:
                return []
            idx = df.index
            idx = idx.tz_convert("America/New_York") if idx.tz is not None else idx
            return sorted({d.strftime("%Y-%m-%d") for d in idx})
    out, failed = {}, {}
    for k, t in enumerate(tickers):
        for a in range(retries + 1):
            try:
                out[t] = fetcher(t)
                break
            except Exception as e:                       # 429 / not found: recorded
                failed[t] = f"{type(e).__name__}: {str(e)[:80]}"
                time.sleep(pause * (2 ** a))
        else:
            out[t] = None
        if out.get(t) is not None:
            failed.pop(t, None)
        if k % 100 == 0:
            log(f"earnings {k}/{len(tickers)}")
        time.sleep(pause * 0.3)
    return out, failed


def earnings_features(pool, earn, calendar):
    """sess_since_earn: sessions since the last report date <= signal day (0 = same day:
    the decision is taken after the close, a same-day report is already public).
    earn_within_5 (SENSITIVITY ONLY): a report date in (signal day, +5 sessions]."""
    cal = pd.DatetimeIndex(calendar)
    pos = {d: k for k, d in enumerate(cal)}
    since, within, last_used = [], [], []
    for t, d in zip(pool["ticker"], pool["signal_date"]):
        ds = earn.get(t)
        if not ds:
            since.append(np.nan); within.append(np.nan); last_used.append(None)
            continue
        dates = pd.DatetimeIndex(pd.to_datetime(ds))
        past = dates[dates <= d]
        if len(past):
            lp = past.max()
            k_last = cal.searchsorted(lp)                 # session on/after the report date
            since.append(float(pos[d] - k_last) if d in pos else np.nan)
            last_used.append(str(lp.date()))
        else:
            since.append(np.nan); last_used.append(None)
        k = pos.get(d)
        hi = cal[min(k + 5, len(cal) - 1)] if k is not None else d
        within.append(float(((dates > d) & (dates <= hi)).any()))
    return pd.DataFrame({"sess_since_earn": since, "earn_within_5": within,
                         "earn_last_date_used": last_used}, index=pool.index)


# =====================================================================
# self-checks (leakage)
# =====================================================================
def self_checks(pool, frames, mask, sectors, br, sample_days=3):
    """Recompute breadth / sector features from data CUT at the signal day for a few dates
    and compare with the full-history tables; verify PIT membership vs PR #5 flags."""
    out = {}
    days = pd.DatetimeIndex(sorted(pool["signal_date"].unique()))
    pick = days[[len(days) // 5, len(days) // 2, -10]][:sample_days]
    bad = 0
    for d in pick:
        cut = {t: f.loc[:d] for t, f in frames.items() if len(f.loc[:d])}
        b2, s2, _ = market_tables(cut, mask.loc[:d], sectors)
        for c in ("breadth_ma50", "breadth_new_high", "breadth_chg5"):
            a, b = br.loc[d, c], b2.loc[d, c]
            bad += not ((pd.isna(a) and pd.isna(b)) or np.isclose(a, b))
        rows = pool[pool["signal_date"] == d]
        for r in rows.itertuples():
            m = s2[(s2["date"] == d) & (s2["sector"] == sectors.get(r.ticker, ""))]
            if len(m):
                bad += not np.isclose(m["sector_rs_median"].iloc[0], r.sector_rs_median,
                                      equal_nan=True)
    out["cut_at_signal_day_recompute"] = dict(days=[str(x.date()) for x in pick],
                                              mismatches=int(bad))
    out["pit_membership_vs_pr5"] = dict(
        rows=len(pool), mismatches=int((~pool["_pit_rebuilt"]).sum()))
    out["earnings_last_date_after_signal"] = int(sum(
        1 for a, d in zip(pool["earn_last_date_used"], pool["signal_date"])
        if pd.notna(a) and pd.Timestamp(a) > d))
    return out


# =====================================================================
def build(dataset_dir, earnings_json=None, fetcher=None, log=print):
    lab, frames, spy, src = P.load(dataset_dir)
    cal = pd.DatetimeIndex(spy.index)
    end = cal[-1]
    v0 = pd.Timestamp(lab["split_validation_start"].iloc[0])
    t0 = pd.Timestamp(lab["split_test_start"].iloc[0])
    assert (v0, t0) == (V0, T0), f"split boundaries {v0.date()} / {t0.date()} != PREREG"
    tl, sectors, pit_sha = pit_timeline(dataset_dir, end)
    closes_idx = pd.DataFrame({t: f["Close"] for t, f in frames.items()}).sort_index().index
    mask = E.pit_mask(tl, closes_idx, list(frames))
    br, st, score = market_tables(frames, mask, sectors)
    log(f"market tables: {len(br)} days, {st['sector'].nunique()} sectors")
    pool = P.long_pool(lab, "pit500", tuple(P.LONGS))
    pool = add_rs_ranks(pool)
    pool["split"], pool["label_end"] = P.splits_at(pool, cal, v0, t0)
    pool["_pit_rebuilt"] = [bool(mask.at[d, t]) if t in mask.columns else False
                            for t, d in zip(pool["ticker"], pool["signal_date"])]
    pool["sector"] = pool["ticker"].map(sectors).fillna("")
    pool = pool.join(br[["breadth_ma50", "breadth_new_high", "breadth_chg5", "breadth_members"]],
                     on="signal_date")
    pool = pool.merge(st, left_on=["signal_date", "sector"], right_on=["date", "sector"],
                      how="left").drop(columns="date")
    pool["rs_minus_sector"] = pool["rs_score"] - pool["sector_rs_median"]
    tick = sorted(set(pool["ticker"]))
    if earnings_json and Path(earnings_json).exists():
        raw = json.loads(Path(earnings_json).read_text())
        earn, failed = raw["dates"], raw.get("failed", {})
    else:
        earn, failed = fetch_earnings(tick, fetcher=fetcher, log=log)
    pool = pool.join(earnings_features(pool, earn, cal))
    checks = self_checks(pool, frames, mask, sectors, br)
    v1 = P.long_pool(lab, "pit500", ("retest",)).set_index(["ticker", "signal_date"])["rank_rs"]
    mine = pool[pool["strategy"] == "retest"].set_index(["ticker", "signal_date"])["rank_rs"]
    checks["rank_rs_retest_vs_v1"] = dict(
        rows=len(mine), same_index=bool(mine.sort_index().index.equals(v1.sort_index().index)),
        mismatches=int((~np.isclose(mine.sort_index().values, v1.sort_index().values)).sum())
        if len(mine) == len(v1) else -1)
    retest_dev = pool[(pool["strategy"] == "retest") & pool["split"].isin(["train", "validation"])]
    cov = float(retest_dev["sess_since_earn"].notna().mean()) if len(retest_dev) else 0.0
    feats = P.MODEL_FEATURES + V2_FEATURES
    if cov < EARN_COVERAGE_MIN:
        feats = [f for f in feats if f != "sess_since_earn"]
    report = dict(
        prereg="v2.1", data_end=str(end.date()), validation_start=str(v0.date()),
        test_start=str(t0.date()), dataset=src, pit_source_sha256=pit_sha,
        rows_all_long=len(pool), rows_retest=int((pool["strategy"] == "retest").sum()),
        splits_retest=pool[pool["strategy"] == "retest"]["split"].value_counts().to_dict(),
        nonoverlap_retest=int(E.non_overlapping(pool[pool["strategy"] == "retest"]).sum()),
        earnings=dict(tickers=len(tick), with_dates=int(sum(bool(earn.get(t)) for t in tick)),
                      failed=len(failed), coverage_retest_dev=round(cov, 4),
                      coverage_rule=f">= {EARN_COVERAGE_MIN:.0%} of eligible retest signals "
                                    "(train + validation) with sess_since_earn defined",
                      group_kept=cov >= EARN_COVERAGE_MIN),
        sectors=dict(signals_without_sector=int((pool["sector"] == "").sum()),
                     n_sectors=int(st["sector"].nunique())),
        breadth=dict(min_members=int(br["breadth_members"].min()),
                     median_members=float(br["breadth_members"].median())),
        missing_share={f: round(float(pool[f].isna().mean()), 4) for f in feats + SENSITIVITY_ONLY},
        deciding_features=feats, sensitivity_only=SENSITIVITY_ONLY,
        rank_features=dict(deciding_retest="rank_rs (same strategy, same day)",
                           secondary_all_longs="rank_rs_all (all long setups, same day)"),
        self_checks=checks,
        stop_before_training="BUILD ONLY — no model trained (PREREG v2.1: Muse's data audit first)")
    keep = ["ticker", "signal_date", "strategy", "sector", "split", "label_end", "trade_status",
            "exit_date", "entry_date", P.TARGET, "rs", "i", "rank_rs_all"] + P.MODEL_FEATURES + \
        V2_FEATURES + \
        SENSITIVITY_ONLY + ["earn_last_date_used", "breadth_members", "sector_members"]
    return pool[keep], report, dict(dates=earn, failed=failed)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--earnings-json")
    ap.add_argument("--out", default=str(ROOT / "research/results/ai_rank/v2_build"))
    ap.add_argument("--dist", default=str(ROOT / "dist/ai_rank_v2"))
    a = ap.parse_args(argv)
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%MZ")
    data, rep, raw = build(a.dataset, a.earnings_json)
    man = {}
    gz = __import__("gzip").compress(RUN.csv_bytes(data), mtime=0)
    RUN.write_once(Path(a.dist) / run_id / "dataset_v2.csv.gz", gz, man, Path(a.dist))
    RUN.write_once(Path(a.dist) / run_id / "earnings_raw.json",
                   json.dumps(raw, sort_keys=True, indent=0), man, Path(a.dist))
    rep["files_sha256"] = man
    rep["git"] = RUN._git_rev()
    out = Path(a.out) / run_id
    RUN.write_once(out / "build_report.json", json.dumps(rep, indent=2, default=str), {},
                   Path(a.out))
    md = ["# AI ranking v2 — data build (PREREG v2.1)", "",
          "**Build only. No model was trained.** Next: ChatGPT + Muse review.", "",
          "```json", json.dumps(rep, indent=1, default=str), "```", ""]
    RUN.write_once(out / "BUILD_REPORT.md", "\n".join(md), {}, Path(a.out))
    print(json.dumps({k: rep[k] for k in ("rows_retest", "splits_retest", "earnings",
                                          "self_checks")}, default=str))
    ok = (rep["self_checks"]["cut_at_signal_day_recompute"]["mismatches"] == 0 and
          rep["self_checks"]["rank_rs_retest_vs_v1"]["mismatches"] == 0 and
          rep["self_checks"]["pit_membership_vs_pr5"]["mismatches"] == 0 and
          rep["self_checks"]["earnings_last_date_after_signal"] == 0)
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
