"""Signal detection, model trades, labels and dataset splits for the S&P 1500 research.

Time conventions (all explicit):
  t0          signal session; features use bars <= t0 only (decision at t0's close)
  entry       open of the ticker's next bar after t0 (production rule); `entry_delay`
              = market sessions skipped when that bar is missing
  px_ret_h    close(t0) -> close of the market session h sessions after t0 (SPY calendar),
              signed by direction; observable on that session's date
  model trade entry open -> stop / time exit at the close of the 20th bar after entry;
              observable on the exit date; MFE/MAE measured from entry up to the exit bar
  barrier     +4R target vs stop within 20 bars after entry, stop first on a shared bar
Nothing in a row's features depends on bars after t0 (tests perturb future bars).
"""
import hashlib

import numpy as np
import pandas as pd

import backtest as bt
import core
from research.sp1500 import rules as R

FEATURES = ["rs_ref500", "rs_1500", "rs_pit500", "rs_score", "close", "adv20_usd", "atr14_pct",
            "vol_ratio", "vol10_vs_50", "ret_1d", "ret_5d", "ret_20d", "ret_63d",
            "dist_ma50", "dist_ma150", "dist_ma200", "dist_52w_high", "dist_52w_low",
            "dist_level_pct", "risk_at_close_pct", "spy_above50", "spy_above200",
            "spy_ret_20d"]


# =====================================================================
# RS: same raw score as production; percentile vs a reference set
# =====================================================================
def rs_scores(frames: dict) -> pd.DataFrame:
    closes = pd.DataFrame({t: f["Close"] for t, f in frames.items()}).sort_index()
    r = lambda n: closes / closes.shift(n) - 1
    return 0.4 * r(63) + 0.2 * r(126) + 0.2 * r(189) + 0.2 * r(252)


def rs_percentile(scores: pd.DataFrame, ref_cols=None, ref_mask=None) -> pd.DataFrame:
    """1..99 like backtest.rs_history. ref_cols=None and ref_mask=None -> rank within all
    columns (identical to rs_history); otherwise each stock is placed in the distribution of
    the reference set (count of reference scores <= own score / reference count).
    ref_mask: optional bool DataFrame (same shape) - a per-day reference set (point-in-time)."""
    if ref_cols is None and ref_mask is None:
        return (scores.rank(axis=1, pct=True) * 98 + 1).round()
    allv = scores.to_numpy()
    if ref_mask is not None:
        mk = ref_mask.reindex(index=scores.index, columns=scores.columns).fillna(False)
        ref = np.where(mk.to_numpy(dtype=bool), allv, np.nan)
    else:
        ref = scores[[c for c in ref_cols if c in scores.columns]].to_numpy()
    out = np.full(allv.shape, np.nan)
    for k in range(len(scores)):
        rv = ref[k][~np.isnan(ref[k])]
        if not len(rv):
            continue
        rv.sort()
        row = allv[k]
        ok = ~np.isnan(row)
        out[k, ok] = np.searchsorted(rv, row[ok], side="right") / len(rv)
    return pd.DataFrame(np.round(out * 98 + 1), index=scores.index, columns=scores.columns)


# =====================================================================
# Per-ticker arrays (computed once on full history — all rolling/causal)
# =====================================================================
def arrays(f: pd.DataFrame) -> dict:
    x = bt.indicators(f)
    C, H, L, V = x["C"], x["H"], x["L"], x["V"]
    s = pd.Series(C)
    prevc = np.r_[np.nan, C[:-1]]
    tr = np.nanmax(np.vstack([H - L, np.abs(H - prevc), np.abs(L - prevc)]), axis=0)
    x["atr14"] = pd.Series(tr).rolling(14).mean().values
    x["adv20"] = pd.Series(C * V).rolling(20).mean().values
    for n in (1, 5, 20, 63):
        x[f"ret_{n}"] = (s / s.shift(n) - 1).values
    x["div"] = f["Dividends"].fillna(0).values.astype(float) if "Dividends" in f else \
        np.zeros(len(f))
    return x


def _features(x, i):
    C = x["C"][i]
    avg = x["vol20_prev"][i]
    return dict(close=C, adv20_usd=x["adv20"][i], atr14_pct=x["atr14"][i] / C,
                vol_ratio=x["V"][i] / avg if avg else np.nan,
                vol10_vs_50=x["vol10"][i] / x["vol50"][i] if x["vol50"][i] else np.nan,
                ret_1d=x["ret_1"][i], ret_5d=x["ret_5"][i], ret_20d=x["ret_20"][i],
                ret_63d=x["ret_63"][i], dist_ma50=C / x["ma50"][i] - 1,
                dist_ma150=C / x["ma150"][i] - 1, dist_ma200=C / x["ma200"][i] - 1,
                dist_52w_high=C / x["hi252"][i] - 1, dist_52w_low=C / x["lo252"][i] - 1)


def signal_id(strategy, ticker, day) -> str:
    key = f"{R.RULES_VERSION}|{pd.Timestamp(day).date()}|{ticker}|{strategy}|{R.DIRECTION[strategy]}"
    return hashlib.sha256(key.encode()).hexdigest()[:24]


# =====================================================================
# Model trade (long & short), barrier label, costs
# =====================================================================
def model_trade(x, i, direction, stop, hold=R.HOLD):
    """Trade from the next bar's open. Returns dict (status no_trade/open/closed)."""
    sgn = 1 if direction == "long" else -1
    O, H, L, C, D = x["O"], x["H"], x["L"], x["C"], x["dates"]
    last = len(C) - 1
    e = i + 1
    if e > last:
        return dict(trade_status="no_entry_bar")
    entry = O[e]
    risk = sgn * (entry - stop) / entry
    if risk <= 0:
        return dict(trade_status="no_trade_gap_through_stop", entry_date=D[e], entry=entry)
    exit_i = exit_px = reason = None
    for j in range(e, min(e + hold, last) + 1):
        hit = L[j] <= stop if sgn == 1 else H[j] >= stop
        if hit:
            px = stop if j == e else (min(O[j], stop) if sgn == 1 else max(O[j], stop))
            exit_i, exit_px, reason = j, px, "stop"
            break
    if exit_i is None and e + hold <= last:
        exit_i, exit_px, reason = e + hold, C[e + hold], "time"
    out = dict(entry_date=D[e], entry=entry, stop=stop, risk_pct=risk * 100)
    if exit_i is None:
        return dict(out, trade_status="open")
    win = slice(e, exit_i + 1)
    gross = sgn * (exit_px / entry - 1)
    mfe = (H[win].max() / entry - 1) if sgn == 1 else (1 - L[win].min() / entry)
    mae = (L[win].min() / entry - 1) if sgn == 1 else (1 - H[win].max() / entry)
    divs = float(x["div"][e + 1:exit_i + 1].sum())              # ex-dates in (entry, exit]
    days = (pd.Timestamp(D[exit_i]) - pd.Timestamp(D[e])).days
    return dict(out, trade_status="closed", exit_date=D[exit_i], exit=exit_px,
                exit_reason=reason, bars_held=exit_i - e, calendar_days=days,
                gross_ret=gross, gross_r=gross / risk, mfe_r=mfe / risk, mae_r=mae / risk,
                mfe_pct=mfe * 100, mae_pct=mae * 100, dividends_ps=divs,
                observable_trade=D[exit_i])


def barrier(x, i, direction, stop, target_r=R.BARRIER_TARGET_R, hold=R.HOLD):
    """+target_r R vs stop within `hold` bars from the entry bar; stop first on a shared bar."""
    sgn = 1 if direction == "long" else -1
    O, H, L, D = x["O"], x["H"], x["L"], x["dates"]
    last = len(O) - 1
    e = i + 1
    if e > last:
        return dict(barrier="no_entry_bar")
    entry = O[e]
    risk = sgn * (entry - stop)
    if risk <= 0:
        return dict(barrier="no_trade_gap_through_stop")
    target = entry + sgn * target_r * risk
    for j in range(e, min(e + hold, last) + 1):
        s_hit = L[j] <= stop if sgn == 1 else H[j] >= stop
        t_hit = H[j] >= target if sgn == 1 else L[j] <= target
        if s_hit and t_hit:
            return dict(barrier="ambiguous_same_bar", barrier_r=-1.0, observable_barrier=D[j])
        if s_hit:
            return dict(barrier="stop", barrier_r=-1.0, observable_barrier=D[j])
        if t_hit:
            return dict(barrier="target", barrier_r=target_r, observable_barrier=D[j])
    if e + hold <= last:
        return dict(barrier="none", barrier_r=0.0, observable_barrier=D[e + hold])
    return dict(barrier="immature")


def apply_costs(row: dict) -> dict:
    """Net R under slippage / borrow scenarios (shorts pay dividends; borrow per APR)."""
    if row.get("trade_status") != "closed":
        return row
    entry, ex, risk = row["entry"], row["exit"], row["risk_pct"] / 100
    short = row["direction"] == "short"
    div = row["dividends_ps"] / entry if short else 0.0
    for name, bps in R.SLIPPAGE_SCENARIOS_BPS.items():
        cost = bps / 1e4 * (entry + ex) / entry
        if not short:
            row[f"net_r_{name}"] = (row["gross_ret"] - cost) / risk
            continue
        for bname, apr in R.BORROW_SCENARIOS_APR.items():
            key = f"net_r_{name}_{bname}"
            if apr is None:
                row[key] = None                                     # unknown borrow: no net
            else:
                borrow = apr * max(1, row["calendar_days"]) / 365
                row[key] = (row["gross_ret"] - cost - borrow - div) / risk
    return row


# =====================================================================
# Detection over the full history
# =====================================================================
def pit_mask(timeline, index, columns) -> pd.DataFrame:
    """bool DataFrame: ticker was an S&P 500 member on that day (None if no timeline)."""
    from research.sp1500 import universe as U
    if timeline is None:
        return None
    cols = list(columns)
    out = np.zeros((len(index), len(cols)), dtype=bool)
    pos = {c: k for k, c in enumerate(cols)}
    for r, day in enumerate(index):
        for t in U.member_on(timeline, day):
            k = pos.get(t)
            if k is not None:
                out[r, k] = True
    return pd.DataFrame(out, index=index, columns=cols)


def detect(frames: dict, spy: pd.DataFrame, meta: pd.DataFrame, ref500: list,
           pit500=None, strategies=None, start_i=bt.WARMUP) -> tuple:
    """
    frames: {ticker: OHLCV(+Dividends)}; meta: DataFrame[ticker, group, sector];
    ref500: tickers forming the production RS reference; pit500: universe.pit timeline.
    Returns (signals DataFrame, data {ticker: arrays}).
    """
    strategies = strategies or list(R.LONG_RULES) + list(R.SHORT_RULES)
    scores = rs_scores(frames)
    rs_ref = rs_percentile(scores, ref500)
    rs_all = rs_percentile(scores)
    pmask = pit_mask(pit500, scores.index, scores.columns)
    rs_pit = rs_percentile(scores, ref_mask=pmask) if pmask is not None else None
    reg = core.market_regime(spy)
    spy_c = reg["close"]
    spy_r20 = spy_c / spy_c.shift(20) - 1
    cal = pd.DatetimeIndex(spy.index)
    m = meta.set_index("ticker")
    rows, data = [], {}
    for t, f in frames.items():
        if len(f) < start_i + 2:
            continue
        x = arrays(f)
        data[t] = x
        dates = pd.DatetimeIndex(x["dates"])
        rr = rs_ref[t].reindex(dates).values if t in rs_ref else np.full(len(dates), np.nan)
        ra = rs_all[t].reindex(dates).values if t in rs_all else np.full(len(dates), np.nan)
        sc = scores[t].reindex(dates).values if t in scores else np.full(len(dates), np.nan)
        rp = rs_pit[t].reindex(dates).values if rs_pit is not None else \
            np.full(len(dates), np.nan)
        pm = pmask[t].reindex(dates).values if pmask is not None else None
        a50 = reg["above50"].reindex(dates).values
        a200 = reg["above200"].reindex(dates).values
        sr20 = spy_r20.reindex(dates).values
        group = m.at[t, "group"] if t in m.index else "unknown"
        sector = m.at[t, "sector"] if t in m.index else ""
        for i in range(start_i, len(dates)):
            for s in strategies:
                rule = R.LONG_RULES.get(s) or R.SHORT_RULES[s]
                hit = rule(x, i)
                if hit is None:
                    continue
                direction = R.DIRECTION[s]
                sgn = 1 if direction == "long" else -1
                level, stop_base = float(hit[0]), float(hit[1])
                stop = stop_base * (1 - sgn * R.STOP_BUF[s] / 100)
                C = x["C"][i]
                day = dates[i]
                pit = None if pm is None else bool(pm[i])
                row = dict(signal_id=signal_id(s, t, day), ticker=t, group=group,
                           sector=sector, strategy=s, direction=direction,
                           rules_version=R.RULES_VERSION, signal_date=day, i=i,
                           level=level, stop_base=stop_base, stop=stop,
                           rs_ref500=rr[i], rs_1500=ra[i], rs_pit500=rp[i], rs_score=sc[i],
                           spy_above50=a50[i], spy_above200=a200[i], spy_ret_20d=sr20[i],
                           dist_level_pct=(C / level - 1) * 100,
                           risk_at_close_pct=sgn * (C - stop) / C * 100,
                           pit_member_sp500=pit, **_features(x, i))
                rows.append(row)
    sig = pd.DataFrame(rows)
    return sig, data


# =====================================================================
# Filters / rejection reasons (pre-registered)
# =====================================================================
def rejection_reasons(sig: pd.DataFrame, rs_col="rs_ref500", market="primary") -> pd.Series:
    long = sig["direction"] == "long"
    reasons = pd.Series([[] for _ in range(len(sig))], index=sig.index)

    def add(mask, why):
        for k in sig.index[mask.fillna(True) if hasattr(mask, "fillna") else mask]:
            reasons.at[k].append(why)
    rs = sig[rs_col]
    add(long & ~(rs >= R.MIN_RS_LONG), "rs")
    add(~long & ~(rs <= R.MAX_RS_SHORT), "rs")
    add(~long & ((sig["close"] < R.MIN_PRICE) | ~(sig["adv20_usd"] >= R.MIN_ADV_USD)),
        "liquidity")
    if market == "primary":
        up = sig["spy_above50"].astype("boolean")
        add(long & (up != True), "market")                     # noqa: E712
        add(~long & (up != False), "market")                   # noqa: E712
    add(~(sig["risk_at_close_pct"] > 0), "invalid_stop")
    return reasons.map(lambda r: "|".join(r))


# =====================================================================
# Labels (observable only) and chronological splits
# =====================================================================
def add_outcomes(sig: pd.DataFrame, data: dict, calendar, data_end) -> pd.DataFrame:
    cal = pd.DatetimeIndex(calendar)
    end = pd.Timestamp(data_end)
    pos = {d: k for k, d in enumerate(cal)}
    out = []
    for r in sig.to_dict("records"):
        x = data[r["ticker"]]
        sgn = 1 if r["direction"] == "long" else -1
        r.update(model_trade(x, r["i"], r["direction"], r["stop"]))
        r.update(barrier(x, r["i"], r["direction"], r["stop"]))
        k0 = pos.get(pd.Timestamp(r["signal_date"]))
        if r.get("entry_date") is not None and k0 is not None:
            ke = pos.get(pd.Timestamp(r["entry_date"]))
            r["entry_delay_sessions"] = (ke - k0 - 1) if ke is not None else None
        dates = pd.DatetimeIndex(x["dates"])
        idx = {d: j for j, d in enumerate(dates)}
        c0 = x["C"][r["i"]]
        for h in R.LABEL_HORIZONS:
            if k0 is None or k0 + h >= len(cal) or cal[k0 + h] > end:
                r[f"px_ret_{h}"], r[f"px_ret_{h}_observable"] = None, None
                r[f"px_ret_{h}_status"] = "immature"
                continue
            d = cal[k0 + h]
            j = idx.get(d)
            if j is None:
                r[f"px_ret_{h}"], r[f"px_ret_{h}_observable"] = None, str(d.date())
                r[f"px_ret_{h}_status"] = "missing_bar"
            else:
                r[f"px_ret_{h}"] = sgn * (x["C"][j] / c0 - 1)
                r[f"px_ret_{h}_observable"] = str(d.date())
                r[f"px_ret_{h}_status"] = "mature"
        h_end = cal[min(k0 + R.HOLD, len(cal) - 1)] if k0 is not None else None
        r["horizon_end"] = h_end
        out.append(apply_costs(r))
    return pd.DataFrame(out)


def assign_splits(df: pd.DataFrame, calendar, frac=(0.6, 0.2), purge=R.HOLD,
                  embargo=5) -> pd.DataFrame:
    """Chronological train/validation/test by signal date; rows whose 20-session horizon reaches
    the next split start are 'purged'; the first `embargo` sessions of val/test are 'embargo'."""
    cal = pd.DatetimeIndex(calendar)
    days = sorted(pd.to_datetime(df["signal_date"]).unique())
    if len(days) < 10:
        return df.assign(split="insufficient")
    v0 = pd.Timestamp(days[int(len(days) * frac[0])])
    t0 = pd.Timestamp(days[int(len(days) * (frac[0] + frac[1]))])
    pos = {d: k for k, d in enumerate(cal)}

    def shift(d, n):
        k = pos.get(pd.Timestamp(d))
        return cal[min(k + n, len(cal) - 1)] if k is not None else pd.Timestamp(d)
    sd = pd.to_datetime(df["signal_date"])
    hend = sd.map(lambda d: shift(d, purge))
    split = np.where(sd < v0, "train", np.where(sd < t0, "validation", "test")).astype(object)
    split[(split == "train") & (hend >= v0)] = "purged"
    split[(split == "validation") & (hend >= t0)] = "purged"
    split[(split == "validation") & (sd < shift(v0, embargo))] = "embargo"
    split[(split == "test") & (sd < shift(t0, embargo))] = "embargo"
    return df.assign(split=split, split_validation_start=v0, split_test_start=t0)


# =====================================================================
# Statistics (signal level)
# =====================================================================
def trade_stats(df: pd.DataFrame, col: str) -> dict:
    if not len(df) or col not in df or "trade_status" not in df:
        return dict(trades=0)
    d = df[(df["trade_status"] == "closed") & df[col].notna()]
    if not len(d):
        return dict(trades=0)
    r = d[col].astype(float)
    wins, losses = r[r > 0], r[r <= 0]
    return dict(trades=len(r), win_rate=100 * len(wins) / len(r), mean_r=r.mean(),
                median_r=r.median(),
                mean_r_ex_top5=r.nsmallest(max(len(r) - 5, 0)).mean() if len(r) > 5 else np.nan,
                profit_factor=wins.sum() / -losses.sum() if losses.sum() < 0 else np.inf,
                stopped_pct=100 * (d["exit_reason"] == "stop").mean(),
                avg_bars=d["bars_held"].mean(),
                se_mean_r=r.std(ddof=1) / np.sqrt(len(r)) if len(r) > 1 else np.nan)
