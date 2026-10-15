"""S&P 1500 / shorts / AI-dataset research run (research only; no broker, no paper state).

    python -m research.sp1500.run [--period 5y] [--max-tickers N]

Writes a NEW run directory research/results/sp1500/runs/<run_id>/ (never overwrites one) with
the universe snapshot, coverage, summary tables, REPORT.md and a manifest of sha256 checksums.
Large files (full signal dataset, raw source pages, raw bars) go to --dataset-dir, which the
workflow uploads as an artifact; their checksums are in the committed manifest.
"""
import argparse
import gzip
import hashlib
import io
import json
import pickle
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import backtest as bt
import core
import portfolio_bt as pf
from research.sp1500 import data as D
from research.sp1500 import engine as E
from research.sp1500 import rules as R
from research.sp1500 import universe as U

ROOT = Path(__file__).resolve().parents[2]
LONGS = list(R.LONG_RULES)
SHORTS = list(R.SHORT_RULES)
GROUPS = ["sp500", "sp400", "sp600"]


# ---------------------------------------------------------------- write-once helpers
def sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def write_once(path: Path, data, manifest: dict, root: Path):
    """Create `path`; refuse to replace an existing file with different content."""
    b = data if isinstance(data, bytes) else data.encode()
    if path.exists():
        if path.read_bytes() != b:
            raise FileExistsError(f"refusing to overwrite research output {path}")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as f:
            f.write(b)
    manifest[str(path.relative_to(root))] = sha_bytes(b)


def csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode()


def md_table(df: pd.DataFrame, floatfmt="{:.2f}") -> str:
    if df is None or not len(df):
        return "_(none)_\n"
    cols = list(df.columns)
    out = ["| " + " | ".join(map(str, cols)) + " |", "|" + "---|" * len(cols)]
    for r in df.itertuples(index=False):
        cells = []
        for v in r:
            if isinstance(v, (float, np.floating)):
                cells.append("" if not np.isfinite(v) else floatfmt.format(v))
            else:
                cells.append(str(v))
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- data end / calendar
def completed_end(spy: pd.DataFrame, now_utc: datetime) -> pd.Timestamp:
    """Last SPY session that is complete at `now_utc` (today counts only after 18:00 NY)."""
    ny = pd.Timestamp(now_utc).tz_convert("America/New_York")
    today = pd.Timestamp(ny.date())
    idx = pd.DatetimeIndex(spy.index)
    ok = idx[idx < today] if ny.hour < 18 else idx[idx <= today]
    return ok[-1]


# ---------------------------------------------------------------- statistics helpers
def stat_rows(df, keys, col, extra=None):
    out = []
    for k, d in df.groupby(keys, dropna=False):
        k = k if isinstance(k, tuple) else (k,)
        st = E.trade_stats(d, col)
        row = dict(zip(keys, k))
        row.update(detected=len(d), mature_trades=st.get("trades", 0))
        for c in ("win_rate", "mean_r", "median_r", "mean_r_ex_top5", "profit_factor",
                  "se_mean_r", "stopped_pct", "avg_bars"):
            row[c] = st.get(c, np.nan)
        if extra:
            row.update(extra)
        out.append(row)
    return pd.DataFrame(out)


def portfolio(sig: pd.DataFrame, data: dict, mode: str, rs_col: str, market_ok,
              tickers=None, start=None, end=None):
    """Production portfolio engine on research signals: simulate(next open, 20d, 3% stop,
    RS>=85, SPY>MA50) + RS-first ordering + replay (Task 10 config)."""
    s = sig[(sig["strategy"] == mode)]
    if tickers is not None:
        s = s[s["ticker"].isin(tickers)]
    if not len(s):
        return None
    raw = pd.DataFrame(dict(ticker=s["ticker"], mode=s["strategy"], i=s["i"],
                            date=pd.to_datetime(s["signal_date"]), close=s["close"],
                            level=s["level"], stop_base=s["stop_base"], rs=s[rs_col],
                            vol_ratio=s["vol_ratio"]))
    tr = bt.simulate(raw, data, mode, hold=R.HOLD, stop_buf=R.LONG_STOP_BUF_PCT,
                     min_rs=R.MIN_RS_LONG, min_vol=0.0, max_risk=0.0, market_ok=market_ok,
                     entry_at="open", one_per_ticker=False, include_open=True)
    if not len(tr):
        return None
    tr = tr.sort_values(["date", "rs", "ticker"], ascending=[True, False, True],
                        kind="stable").reset_index(drop=True)
    # whole group as the price calendar + fixed window -> equal periods across groups
    use = {t: data[t] for t in (tickers if tickers is not None else data) if t in data}
    curve, ex, m = pf.replay(tr, use, initial_cash=10000., risk_fraction=.01, max_positions=5,
                             max_new_per_day=3, max_position_fraction=.20, cost_bps=10.,
                             start=start, end=end, open_at_end="mark")
    return dict(candidates=len(tr), executed=m["executed_trades"], closed=m["closed_trades"],
                open_end=m["open_positions_end"], final_equity=m["final_equity"],
                return_pct=m["return_pct"], cagr_pct=m["cagr_pct"],
                max_dd_pct=m["max_drawdown_pct"], first=str(curve["date"].iloc[0].date()),
                last=str(curve["date"].iloc[-1].date()))


def equivalence(frames500: dict, sig: pd.DataFrame) -> dict:
    """Retest detections of the research engine for the S&P 500 group (RS vs the 500
    reference) must equal production backtest.find_signals on the same 500 frames."""
    ref, _ = bt.find_signals(frames500, lookback=3, modes=["retest"])
    ref = ref.assign(date=pd.to_datetime(ref["date"])).set_index(["ticker", "date"]).sort_index()
    mine = sig[(sig["strategy"] == "retest") & sig["ticker"].isin(frames500)]
    mine = mine.assign(date=pd.to_datetime(mine["signal_date"])) \
        .set_index(["ticker", "date"]).sort_index()
    same_keys = list(ref.index) == list(mine.index)
    res = dict(production_rows=len(ref), research_rows=len(mine), same_keys=same_keys)
    if same_keys and len(ref):
        res["level_equal"] = bool(np.allclose(ref["level"], mine["level"]))
        res["stop_base_equal"] = bool(np.allclose(ref["stop_base"], mine["stop_base"]))
        a, b = ref["rs"].to_numpy(float), mine["rs_ref500"].to_numpy(float)
        res["rs_equal"] = bool(np.array_equal(np.isnan(a), np.isnan(b)) and
                               np.allclose(a[~np.isnan(a)], b[~np.isnan(b)]))
    else:
        res["only_production"] = len(ref.index.difference(mine.index))
        res["only_research"] = len(mine.index.difference(ref.index))
    res["ok"] = bool(same_keys and res.get("level_equal", True) and
                     res.get("stop_base_equal", True) and res.get("rs_equal", True))
    return res


# ---------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", default="5y")
    ap.add_argument("--out", default=str(ROOT / "research/results/sp1500/runs"))
    ap.add_argument("--dataset-dir", default=str(ROOT / "dist/sp1500"))
    ap.add_argument("--cache", default=str(ROOT / ".cache/sp1500"))
    ap.add_argument("--max-tickers", type=int, default=0, help="smoke runs only")
    a = ap.parse_args(argv)
    t_start = time.time()
    now = datetime.now(timezone.utc)
    run_id = now.strftime("%Y-%m-%dT%H%MZ")
    out = Path(a.out) / run_id
    dsd = Path(a.dataset_dir) / run_id
    if out.exists():
        raise FileExistsError(f"run {out} exists; runs are never overwritten")
    manifest, dmanifest, blockers, log = {}, {}, [], []

    def say(msg):
        print(msg, flush=True)
        log.append(f"{time.time() - t_start:7.1f}s {msg}")

    # 1) universe snapshot ------------------------------------------------------------------
    fetched = U.fetch_all()
    uni, umeta, changes = U.build_universe(fetched)
    for att in fetched["attempts"]:
        if att.get("_raw"):
            name = f"sources/{att['group']}_{att['source']}" + \
                (".csv" if att["source"] == "ishares" else ".html")
            write_once(dsd / name, att["_raw"], dmanifest, dsd.parent)
    if umeta["missing_groups"]:
        blockers.append(f"membership unavailable for {umeta['missing_groups']}")
    say(f"universe: {len(uni)} tickers; sources "
        f"{ {g: v['source'] for g, v in umeta['sources'].items()} }")
    ch500 = changes.get("sp500")
    cur500 = set(uni.loc[uni["group"] == "sp500", "ticker"])
    listed500 = set(t for t, gl in zip(uni["ticker"], uni["groups_listed"]) if "sp500" in gl)

    # 2) prices ------------------------------------------------------------------------------
    start_hint = pd.Timestamp(now.date()) - pd.DateOffset(years=int(a.period.rstrip("y")))
    removed = U.removed_since(ch500, start_hint, set(uni["ticker"]))
    tickers = list(uni["ticker"]) + removed
    if a.max_tickers:
        tickers = tickers[:a.max_tickers]
    frames, rep = D.download(tickers + ["SPY"], period=a.period, cache_dir=a.cache,
                             asof=str(now.date()), log=say)
    spy = frames.pop("SPY", None)
    if spy is None:
        raise SystemExit("SPY unavailable - no calendar, no run (nothing substituted)")
    end = completed_end(spy, now)
    spy = spy.loc[:end]
    frames = {t: f.loc[:end] for t, f in frames.items() if len(f.loc[:end])}
    cal = pd.DatetimeIndex(spy.index)
    rep = rep[rep["ticker"] != "SPY"]
    meta = pd.concat([uni[["ticker", "group", "sector"]],
                      pd.DataFrame(dict(ticker=removed, group="sp500_removed", sector=""))],
                     ignore_index=True)
    cov = D.coverage(rep, meta, cal)
    miss = D.missing_sessions(frames, cal)
    say(f"prices: {len(frames)}/{len(tickers)} tickers, sessions {cal[0].date()}..{end.date()}")
    with io.BytesIO() as b:
        pickle.dump(dict(frames=frames, spy=spy), b)
        write_once(dsd / "bars.pkl.gz", gzip.compress(b.getvalue(), mtime=0), dmanifest,
                   dsd.parent)

    # 3) detection + outcomes ------------------------------------------------------------------
    pit = U.pit_members(cur500 | (listed500 & set(uni.loc[uni["group"] == "ambiguous",
                                                        "ticker"])),
                        ch500, cal[0], end) if ch500 is not None else None
    ref500 = sorted(cur500 & set(frames))
    sig, data = E.detect(frames, spy, meta, ref500, pit500=pit)
    say(f"detections: {len(sig)}")
    variants = {"primary": ("rs_ref500", "primary"), "off": ("rs_ref500", "off"),
                "rs1500_primary": ("rs_1500", "primary"), "pit_primary": ("rs_pit500", "primary")}
    for v, (rc, mk) in variants.items():
        sig[f"reject_{v}"] = E.rejection_reasons(sig, rs_col=rc, market=mk)
        sig[f"eligible_{v}"] = sig[f"reject_{v}"] == ""
    lab = E.add_outcomes(sig, data, cal, end)
    lab = E.assign_splits(lab, cal)
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    prices_sha = sha_bytes(json.dumps(rep.set_index("ticker")["sha256"].dropna().to_dict(),
                                      sort_keys=True).encode())
    lab = lab.assign(generated_at=generated, data_version=prices_sha[:16],
                     dataset_kind="historical_current_constituents",
                     borrow_status=np.where(lab["direction"] == "short", "unknown",
                                            "not_applicable"),
                     executable=np.where(lab["direction"] == "short", False, True))
    say(f"outcomes: {len(lab)} rows")
    gz = gzip.compress(csv_bytes(lab), mtime=0)
    write_once(dsd / "signals.csv.gz", gz, dmanifest, dsd.parent)

    # 4) statistics ------------------------------------------------------------------------------
    cur = lab[lab["group"].isin(GROUPS + ["ambiguous"])]
    longs = cur[cur["direction"] == "long"]
    shorts = cur[cur["direction"] == "short"]

    def by_group(df, elig, col):
        parts = [stat_rows(df[df[elig] & (df["group"] == g)], ["strategy"], col,
                           dict(group=g)) for g in GROUPS]
        parts.append(stat_rows(df[df[elig]], ["strategy"], col, dict(group="combined")))
        return pd.concat([p for p in parts if len(p)], ignore_index=True)

    long_ref = by_group(longs, "eligible_primary", "net_r_base")
    long_1500 = by_group(longs, "eligible_rs1500_primary", "net_r_base")
    long_slip = pd.concat([stat_rows(longs[longs["eligible_primary"]], ["strategy"],
                                     f"net_r_{s}", dict(slippage=s))
                           for s in R.SLIPPAGE_SCENARIOS_BPS], ignore_index=True)
    # PIT vs current S&P 500 (the production universe definition)
    l_all = lab[lab["direction"] == "long"]
    pit_cmp = pd.concat([
        stat_rows(l_all[l_all["eligible_primary"] & (l_all["group"] == "sp500")], ["strategy"],
                  "net_r_base", dict(universe="current_sp500_rs_ref500")),
        stat_rows(l_all[l_all["eligible_pit_primary"] & (l_all["pit_member_sp500"] == True)],  # noqa
                  ["strategy"], "net_r_base", dict(universe="pit_sp500_rs_pit500")),
    ], ignore_index=True) if pit is not None else pd.DataFrame()
    # shorts: cost scenarios
    srows = []
    for mk in ("primary", "off"):
        el = shorts[shorts[f"eligible_{mk}"]]
        for g in GROUPS + ["combined"]:
            d = el if g == "combined" else el[el["group"] == g]
            for s in SHORTS:
                ds = d[d["strategy"] == s]
                row = dict(market=mk, group=g, strategy=s, detected=len(ds))
                st = E.trade_stats(ds, "gross_r")
                row.update(mature_trades=st.get("trades", 0), gross_mean_r=st.get("mean_r"),
                           gross_win=st.get("win_rate"))
                for b in ("gc", "warm", "hot", "htb"):
                    row[f"net_base_{b}"] = E.trade_stats(ds, f"net_r_base_{b}").get("mean_r")
                row["net_stress_hot"] = E.trade_stats(ds, "net_r_stress_hot").get("mean_r")
                row["gap_no_trade"] = int((ds["trade_status"] == "no_trade_gap_through_stop")
                                          .sum()) if len(ds) else 0
                row["ambiguous_bar"] = int((ds["barrier"] == "ambiguous_same_bar").sum()) \
                    if len(ds) else 0
                row["div_paid_trades"] = int((ds["dividends_ps"].fillna(0) > 0).sum()) \
                    if len(ds) else 0
                srows.append(row)
    short_tbl = pd.DataFrame(srows)
    # price-move labels (signal close origin), eligible primary
    px = []
    for (s, g), d in cur[cur["eligible_primary"]].groupby(["strategy", "group"]):
        row = dict(strategy=s, group=g, eligible=len(d))
        for h in R.LABEL_HORIZONS:
            m = d[d[f"px_ret_{h}_status"] == "mature"][f"px_ret_{h}"].astype(float)
            row[f"n_{h}"] = len(m)
            row[f"mean_{h}_pct"] = 100 * m.mean() if len(m) else np.nan
        px.append(row)
    px_tbl = pd.DataFrame(px)
    counts = (lab.groupby(["group", "strategy"]).agg(
        detected=("signal_id", "size"), eligible_primary=("eligible_primary", "sum"),
        eligible_off=("eligible_off", "sum"),
        closed=("trade_status", lambda s: int((s == "closed").sum())),
        open=("trade_status", lambda s: int((s == "open").sum())),
        px20_mature=("px_ret_20_status", lambda s: int((s == "mature").sum())))
        .reset_index())
    rej = (lab.assign(r=lab["reject_primary"].replace("", "eligible").str.split("|"))
           .explode("r").groupby(["direction", "r"]).size().rename("n").reset_index())
    splits = lab.groupby("split").size().rename("rows").reset_index()

    # 5) portfolio backtests (long only; production engine) ---------------------------------
    market_ok = core.market_regime(spy)["above50"]
    prow = []
    for rs_col in ("rs_ref500", "rs_1500"):
        for mode in LONGS:
            for g in GROUPS + ["combined"]:
                tick = set(uni["ticker"]) if g == "combined" else \
                    set(uni.loc[uni["group"] == g, "ticker"])
                r = portfolio(sig, data, mode, rs_col, market_ok, tick,
                              start=cal[min(bt.WARMUP, len(cal) - 1)], end=end)
                if r:
                    prow.append(dict(rs=rs_col, strategy=mode, group=g, **r))
    port_tbl = pd.DataFrame(prow)
    say("portfolio backtests done")

    # 6) equivalence with production ------------------------------------------------------------
    fr500 = {t: frames[t] for t in ref500}
    eq = equivalence(fr500, sig) if fr500 else dict(ok=False, note="no S&P 500 frames")
    if not eq["ok"]:
        blockers.append(f"equivalence with backtest.find_signals failed: {eq}")
    say(f"equivalence: {eq}")

    # 7) write committed outputs ----------------------------------------------------------------
    root = Path(a.out)
    files = {
        "universe.csv": csv_bytes(uni),
        "universe_meta.json": json.dumps(umeta, indent=2, default=str),
        "coverage.csv": csv_bytes(cov),
        "download_report.csv": csv_bytes(rep),
        "missing_sessions.csv": csv_bytes(miss),
        "counts.csv": csv_bytes(counts),
        "rejections.csv": csv_bytes(rej),
        "long_rs_ref500.csv": csv_bytes(long_ref),
        "long_rs_1500.csv": csv_bytes(long_1500),
        "long_slippage.csv": csv_bytes(long_slip),
        "long_pit_vs_current.csv": csv_bytes(pit_cmp),
        "short_cost_scenarios.csv": csv_bytes(short_tbl),
        "price_move_labels.csv": csv_bytes(px_tbl),
        "portfolio_long.csv": csv_bytes(port_tbl),
        "splits.csv": csv_bytes(splits),
        "equivalence.json": json.dumps(eq, indent=2, default=str),
    }
    for name, b in files.items():
        write_once(out / name, b, manifest, root)
    info = dict(run_id=run_id, rules_version=R.RULES_VERSION, generated_at=generated,
                data_end=str(end.date()), first_session=str(cal[0].date()),
                period=a.period, prices_sha256=prices_sha, git=_git_rev(),
                python=platform.python_version(), pandas=pd.__version__,
                blockers=blockers, log=log, dataset_files=dmanifest,
                pit_sp500=pit is not None, removed_sp500_requested=len(removed),
                removed_sp500_with_data=int(sum(t in frames for t in removed)))
    report = build_report(info, umeta, uni, cov, miss, counts, rej, long_ref, long_1500,
                          long_slip, pit_cmp, short_tbl, px_tbl, port_tbl, splits, eq, lab)
    write_once(out / "REPORT.md", report, manifest, root)
    info["files"] = manifest
    write_once(out / "manifest.json", json.dumps(info, indent=2, default=str), {}, root)
    say(f"done: {out}")
    return 0 if not blockers else 2


def _git_rev():
    try:
        import subprocess
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                       text=True).strip()
    except Exception:
        return None


def build_report(info, umeta, uni, cov, miss, counts, rej, long_ref, long_1500, long_slip,
                 pit_cmp, short_tbl, px_tbl, port_tbl, splits, eq, lab) -> str:
    keep = ["group", "strategy", "detected", "mature_trades", "win_rate", "mean_r",
            "median_r", "mean_r_ex_top5", "profit_factor", "se_mean_r"]
    src = pd.DataFrame([dict(group=g, **v) for g, v in umeta["sources"].items()])
    sb = ", ".join(f"{g}: {'YES' if v else 'no'}" for g, v in umeta["survivorship_bias"].items())
    ov = pd.DataFrame(umeta["overlaps"])
    L = [f"# S&P 1500 / shorts / AI dataset — research run `{info['run_id']}`", "",
         f"Rules `{info['rules_version']}` (pre-registered in `research/sp1500/RULES.md`, "
         f"not tuned). Code `{info['git']}`. Data end **{info['data_end']}** "
         f"(first session {info['first_session']}, Yahoo `period={info['period']}`, "
         "`auto_adjust=False` + dividends).", "",
         "**Research only.** Nothing here changes the Retest RS-first paper bot, its data or "
         "schedules. Short results are *preliminary, not executable* (borrow, locate and "
         "recall are not observable). Signal-level statistics are hypothetical one-trade-per-"
         "signal outcomes and are **not** portfolio returns.", ""]
    if info["blockers"]:
        L += ["## Blockers", ""] + [f"- {b}" for b in info["blockers"]] + [""]
    L += ["## 1. Universe and sources", "", md_table(src),
          f"Retrieved {umeta['retrieved_at']}. Survivorship bias (current membership only, no "
          f"dated change table): {sb}. Point-in-time S&P 500: "
          f"{'reconstructed from the dated Wikipedia change table' if info['pit_sp500'] else 'unavailable'}"
          f"; removed members requested {info['removed_sp500_requested']}, with Yahoo data "
          f"{info['removed_sp500_with_data']} (delisted names are mostly missing — the PIT "
          "test still carries survivorship in that part).", "",
          "Overlaps (ticker listed in two indices):", "",
          md_table(ov[["ticker", "groups_listed", "group", "resolution", "evidence"]])
          if len(ov) else "_(none)_\n",
          "## 2. Price coverage", "", md_table(cov, "{:.1f}"),
          f"Tickers with missing sessions inside their own data span: {len(miss)} "
          f"(total {int(miss['missing_sessions'].sum()) if len(miss) else 0} ticker-sessions). "
          "Missing bars are never filled; labels on them stay empty (`missing_bar`).", "",
          "## 3. Signal counts (all detections incl. rejected)", "", md_table(counts),
          "Rejection reasons (primary variant, a signal can have several):", "",
          md_table(rej),
          "## 4. Long strategies — signal level, RS vs S&P 500 reference (production meaning)",
          "", "Net R after 10 bps/side, next-open entry, stop or 20 sessions. Mature (closed) "
          "trades only.", "", md_table(long_ref[keep]),
          "### RS base change: percentile vs the full 1500", "", md_table(long_1500[keep]),
          "### Slippage sensitivity (combined universe, RS vs 500)", "",
          md_table(long_slip[["slippage", "strategy", "mature_trades", "mean_r",
                              "profit_factor"]]),
          "### Point-in-time S&P 500 vs current S&P 500", "",
          md_table(pit_cmp[["universe", "strategy", "detected", "mature_trades", "mean_r",
                            "profit_factor", "se_mean_r"]]) if len(pit_cmp) else
          "_PIT unavailable_\n",
          "## 5. Long portfolio backtests (production engine, separate from signal stats)", "",
          "`backtest.simulate(entry_at='open')` + RS-first order + `portfolio_bt.replay` with "
          "the frozen paper config ($10k, 1 % risk, 5 positions, 3 new/day, 20 % cap, 10 bps).",
          "", md_table(port_tbl),
          "## 6. Short hypotheses — preliminary, cost scenarios", "",
          "R per trade: gross, then net of 10 bps/side slippage+commission, dividends paid and "
          "borrow at GC 0.25 % / warm 3 % / hot 10 % / HTB 30 % APR; `net_stress_hot` = 50 "
          "bps/side + 10 %. Unknown borrow → no net figure. `gap_no_trade`: opened at/above the "
          "stop (skipped).", "", md_table(short_tbl),
          "## 7. Price-move labels (signal-close origin, eligible, %, signed by direction)", "",
          md_table(px_tbl),
          "## 8. Equivalence with production", "",
          f"`backtest.find_signals` (retest, S&P 500 frames) vs research engine: `{eq}`", "",
          "## 9. AI dataset readiness", "",
          f"Rows {len(lab)} (every detection, rejected ones with reasons for 4 variants). "
          "Columns: id, ticker, group, sector, strategy, direction, dates, rules/data version, "
          "generation time, decision-time features, price-move labels (with observable date "
          "and status), model trade (net R by scenario, MFE/MAE, barrier), split. Historical "
          "kind only; forward paper data is not mixed in.", "", md_table(splits),
          "Split: chronological 60/20/20 by signal date, 20-session purge before each "
          "boundary and 5-session embargo after it. No model was trained.", "",
          "## 10. Limitations", "",
          "- Membership is today's (except reconstructed PIT S&P 500); delisted stocks are "
          "largely absent from Yahoo → survivorship bias, likely optimistic for longs and "
          "pessimistic for shorts.",
          "- Yahoo daily bars, split-adjusted; vendor revisions possible (bars + checksums "
          "saved in the artifact).",
          "- Daily candles: intrabar order unknown; shared stop/target bars resolved as stop.",
          "- Shorts: no borrow availability / fee / recall data; uptick rules and halts not "
          "modelled; not executable.",
          "- Overlapping signals in signal-level stats are not independent; standard errors "
          "are understated.",
          "- Immature signals (last ~20 sessions) are excluded from outcome statistics.",
          "- Artifact retention is limited (90 days) — download the dataset if it must be "
          "kept.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    sys.exit(main())
