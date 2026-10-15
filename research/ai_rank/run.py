"""AI ranking research run (reproducible; research only).

    python -m research.ai_rank.run --dataset DIR [--out research/results/ai_rank/runs]

DIR holds the PR #5 dataset artifact (signals.csv.gz, bars.pkl.gz). Writes a new run
directory (never overwrites) with audit.json, yearly tables, model results and REPORT.md.
"""
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from research.ai_rank import pipeline as P
from research.sp1500 import engine as E
from research.sp1500 import run as RUN
from research.sp1500 import rules as R

ROOT = Path(__file__).resolve().parents[2]
UNIVERSES = ("sp500", "sp400", "sp600", "combined", "pit500")


def yearly_signal_tables(lab):
    """Signal-level (NOT portfolio): per group/strategy/year, eligible primary variant."""
    lab = lab.assign(year=lab["signal_date"].dt.year)
    rows = []
    longs = lab[(lab["direction"] == "long") & P.to_bool(lab["eligible_primary"])]
    for (g, s, y), d in longs.groupby(["group", "strategy", "year"]):
        if g not in ("sp500", "sp400", "sp600"):
            continue
        nd = d[E.non_overlapping(d)]
        st = E.trade_stats(nd, "net_r_base")
        rows.append(dict(direction="long", group=g, strategy=s, year=y, signals=len(d),
                         nonoverlap_trades=st.get("trades", 0),
                         mean_net_r=st.get("mean_r"), win_rate=st.get("win_rate")))
    shorts = lab[(lab["direction"] == "short") & P.to_bool(lab["eligible_primary"])]
    for (g, s, y), d in shorts.groupby(["group", "strategy", "year"]):
        if g not in ("sp500", "sp400", "sp600"):
            continue
        nd = d[E.non_overlapping(d)]
        st = E.trade_stats(nd, "gross_r")
        rows.append(dict(direction="short", group=g, strategy=s, year=y, signals=len(d),
                         nonoverlap_trades=st.get("trades", 0), mean_gross_r=st.get("mean_r"),
                         mean_net_r_warm=E.trade_stats(nd, "net_r_base_warm").get("mean_r"),
                         win_rate=st.get("win_rate")))
    return pd.DataFrame(rows)


def build_data(frames, tickers):
    return {t: E.arrays(frames[t]) for t in tickers if t in frames and len(frames[t]) > bt_warm()}


def bt_warm():
    import backtest as bt
    return bt.WARMUP + 2


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--out", default=str(ROOT / "research/results/ai_rank/runs"))
    ap.add_argument("--random-seeds", type=int, default=50)
    a = ap.parse_args(argv)
    t_start = time.time()
    now = datetime.now(timezone.utc)
    run_id = now.strftime("%Y-%m-%dT%H%MZ")
    out = Path(a.out) / run_id
    if out.exists():
        raise FileExistsError(out)
    manifest, log = {}, []

    def say(m):
        print(m, flush=True)
        log.append(f"{time.time() - t_start:7.1f}s {m}")

    lab, frames, spy, src = P.load(a.dataset)
    cal = pd.DatetimeIndex(spy.index)
    end = cal[-1]
    v0 = pd.Timestamp(lab["split_validation_start"].iloc[0])
    t0 = pd.Timestamp(lab["split_test_start"].iloc[0])
    say(f"dataset {len(lab)} rows, sessions {cal[0].date()}..{end.date()}, "
        f"validation {v0.date()}, test {t0.date()}")

    # 1) audit --------------------------------------------------------------------------
    aud = P.audit(lab, frames, spy)
    say(f"audit: {json.dumps(aud, default=str)[:400]}")
    blockers = []
    if aud["features_recomputed_on_truncated_bars"]["mismatches"] or \
            aud["rs_recomputed_on_truncated_closes"]["mismatches"] or \
            aud["labels"]["closed_after_data_end"] or aud["labels"]["entry_not_after_signal"]:
        blockers.append("data audit failed — model not trained")

    # 2) yearly stability: signal level + portfolio (RS-first, production config) -------------
    ys = yearly_signal_tables(lab)
    uni_tickers = sorted(set(lab.loc[lab["group"].isin(["sp500", "sp400", "sp600",
                                                        "ambiguous"]), "ticker"]) |
                         set(lab.loc[P.to_bool(lab["pit_member_sp500"]), "ticker"]))
    data = build_data(frames, uni_tickers)
    say(f"arrays for {len(data)} tickers")
    start = cal[min(260, len(cal) - 1)]
    prow = []
    for u in UNIVERSES:
        for s in P.LONGS:
            pool = P.long_pool(lab, u, (s,))
            if not len(pool):
                continue
            tickers = sorted(set(pool["ticker"]) | (set(lab.loc[lab["group"] == u, "ticker"])
                                                    if u != "pit500" else set()))
            dd = {t: data[t] for t in (tickers if u not in ("combined", "pit500") else data)
                  if t in data}
            tr = P.trades_for(pool, dd)
            S = P.summary(*P.replay(tr, dd, start, end))
            prow.append(dict(universe=u, strategy=s, signals=len(pool), **S))
    port = pd.DataFrame(prow)
    say("yearly portfolio done")

    # 3) ranker experiments ------------------------------------------------------------------
    results = {}
    if not blockers:
        for name, strategies in (("E1_retest_pit500", ("retest",)),
                                 ("E2_all_longs_pit500", tuple(P.LONGS))):
            results[name] = experiment(lab, data, cal, v0, t0, end, strategies,
                                       a.random_seeds, say)
    # 4) write --------------------------------------------------------------------------------
    files = {"audit.json": json.dumps(aud, indent=2, default=str),
             "yearly_signal_stats.csv": RUN.csv_bytes(ys),
             "portfolio_rs_first.csv": RUN.csv_bytes(port.drop(columns="yearly_return_pct")),
             "portfolio_yearly.json": json.dumps({f"{r.universe}/{r.strategy}":
                                                  r.yearly_return_pct for r in port.itertuples()},
                                                 indent=1),
             "ranker_results.json": json.dumps(results, indent=2, default=str)}
    for n, b in files.items():
        RUN.write_once(out / n, b, manifest, Path(a.out))
    info = dict(run_id=run_id, generated_at=now.isoformat(timespec="seconds"),
                dataset=src, data_end=str(end.date()), validation_start=str(v0.date()),
                test_start=str(t0.date()), blockers=blockers, log=log, git=RUN._git_rev(),
                rules_version=R.RULES_VERSION)
    rep = report(info, aud, ys, port, results)
    RUN.write_once(out / "REPORT.md", rep, manifest, Path(a.out))
    info["files"] = manifest
    RUN.write_once(out / "manifest.json", json.dumps(info, indent=2, default=str), {},
                   Path(a.out))
    say(f"done {out}")
    return 0 if not blockers else 2


def experiment(lab, data, cal, v0, t0, end, strategies, n_random, say):
    pool = P.long_pool(lab, "pit500", strategies)
    pool["split"], pool["label_end"] = P.splits_at(pool, cal, v0, t0)
    trades = P.trades_for(pool, data)
    key = ["ticker", "signal_date", "mode"]
    feats = pool.rename(columns={"strategy": "mode"})[key + P.MODEL_FEATURES + [
        P.TARGET, "split", "trade_status"]]
    for m in P.LONGS:
        feats[f"is_{m}"] = (feats["mode"] == m).astype(float)
    fcols = P.MODEL_FEATURES + ([f"is_{m}" for m in P.LONGS] if len(strategies) > 1 else [])
    trades = trades.drop(columns=[c for c in feats.columns if c in trades and c not in key]) \
        .merge(feats, on=key, how="left", validate="many_to_one")
    assert trades[fcols[0]].notna().all(), "trade without features"
    lab_ok = feats[(feats["trade_status"] == "closed") & feats[P.TARGET].notna()]
    tr_rows = lab_ok[lab_ok["split"] == "train"]
    dev_rows = lab_ok[lab_ok["split"].isin(["train", "validation"])]
    in_val = (trades["date"] >= v0) & (trades["date"] < t0)
    in_test = trades["date"] >= t0
    res = dict(strategies=list(strategies), signals=len(pool),
               split_counts=pool["split"].value_counts().to_dict(),
               train_labels=len(tr_rows), dev_labels=len(dev_rows),
               trades_validation=int(in_val.sum()), trades_test=int(in_test.sum()))
    # validation: RS-first, random, every grid model (fit on train only)
    base_v = P.summary(*P.replay(trades[in_val], data, v0, cal[cal < t0][-1]))
    rnd_v = [P.summary(*P.replay(trades[in_val], data, v0, cal[cal < t0][-1], seed=k))
             ["return_pct"] for k in range(min(n_random, 20))]
    grid = []
    for kind, params in P.GRID:
        pred, _ = P.fit_predict(kind, params, tr_rows[fcols], tr_rows[P.TARGET],
                                trades.loc[in_val, fcols])
        S = P.summary(*P.replay(trades[in_val], data, v0, cal[cal < t0][-1], score=pred))
        ic, n_ic = P.daily_ic(trades[in_val].assign(**{P.TARGET: trades.loc[in_val, "r"]}),
                              pred, P.TARGET)
        grid.append(dict(kind=kind, params=params, val_return_pct=S["return_pct"],
                         val_max_dd_pct=S["max_dd_pct"], val_daily_ic=ic, ic_days=n_ic))
    best = max(grid, key=lambda g: (g["val_return_pct"], g["val_daily_ic"] or -9))
    say(f"{strategies}: best on validation {best}")
    res.update(validation=dict(rs_first=base_v, random_return_pct=dict(
        median=float(np.median(rnd_v)), p10=float(np.percentile(rnd_v, 10)),
        p90=float(np.percentile(rnd_v, 90))), grid=grid, chosen=best))
    # test: refit on train + validation, evaluate ONCE
    pred, model = P.fit_predict(best["kind"], best["params"], dev_rows[fcols],
                                dev_rows[P.TARGET], trades.loc[in_test, fcols])
    base_t = P.summary(*P.replay(trades[in_test], data, t0, end))
    mod_t = P.summary(*P.replay(trades[in_test], data, t0, end, score=pred))
    rnd_t = [P.summary(*P.replay(trades[in_test], data, t0, end, seed=k))["return_pct"]
             for k in range(n_random)]
    ic, n_ic = P.daily_ic(trades[in_test].assign(**{P.TARGET: trades.loc[in_test, "r"]}),
                          pred, P.TARGET)
    res["test"] = dict(rs_first=base_t, model=mod_t, model_daily_ic=ic, ic_days=n_ic,
                       random_return_pct=dict(median=float(np.median(rnd_t)),
                                              p10=float(np.percentile(rnd_t, 10)),
                                              p90=float(np.percentile(rnd_t, 90))),
                       model_rank_among_random=float((np.array(rnd_t) < mod_t["return_pct"])
                                                     .mean()))
    if best["kind"] == "ridge":
        coef = model[-1].coef_
        res["ridge_coefficients"] = dict(sorted(zip(fcols, map(float, coef)),
                                                key=lambda kv: -abs(kv[1]))[:10])
    # walk-forward inside the development period (secondary, uses validation-era data)
    wf = []
    for y in sorted({d.year for d in trades["date"] if d < t0})[1:]:
        ys, ye = pd.Timestamp(f"{y}-01-01"), min(pd.Timestamp(f"{y}-12-31"), t0 - pd.Timedelta(days=1))
        trn = lab_ok[(pd.to_datetime(feats.loc[lab_ok.index, "signal_date"]) < ys) &
                     (pool.loc[lab_ok.index, "label_end"] < ys)]
        win = (trades["date"] >= ys) & (trades["date"] <= ye)
        if len(trn) < 500 or win.sum() < 20:
            continue
        p, _ = P.fit_predict(best["kind"], best["params"], trn[fcols], trn[P.TARGET],
                             trades.loc[win, fcols])
        a_ = P.summary(*P.replay(trades[win], data, ys, ye))
        b_ = P.summary(*P.replay(trades[win], data, ys, ye, score=p))
        wf.append(dict(year=y, train_labels=len(trn), rs_first_return_pct=a_["return_pct"],
                       model_return_pct=b_["return_pct"], rs_first_dd=a_["max_dd_pct"],
                       model_dd=b_["max_dd_pct"]))
    res["walk_forward_dev"] = wf
    return res


def report(info, aud, ys, port, results):
    L = [f"# AI ranking research v1 — run `{info['run_id']}`", "",
         f"Dataset: PR #5 run (rules `{info['rules_version']}`), data end {info['data_end']}. "
         f"Validation from {info['validation_start']}, test from {info['test_start']}. "
         "Research only — no model is connected to the bot.", ""]
    if info["blockers"]:
        L += ["## Blockers", ""] + [f"- {b}" for b in info["blockers"]] + [""]
    L += ["## 1. Dataset audit", "", "```json", json.dumps(aud, indent=1, default=str), "```",
          "", "## 2. Portfolio (RS-first, frozen paper config) by universe and strategy", "",
          RUN.md_table(port.drop(columns="yearly_return_pct")), "", "Yearly portfolio returns, %:", ""]
    yr = pd.DataFrame({f"{r.universe}/{r.strategy}": r.yearly_return_pct
                       for r in port.itertuples()}).T
    L += [RUN.md_table(yr.reset_index().rename(columns={"index": "book"})), "",
          "## 3. Signal-level stability by year (non-overlapping, NOT portfolio)", "",
          RUN.md_table(ys), ""]
    for name, r in results.items():
        L += [f"## 4. Ranker {name}", "", "```json", json.dumps(r, indent=1, default=str)[:12000],
              "```", ""]
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
