"""REPORT.md for a Retest M robustness run (tables only, from results.json + coverage.json + repro.json).

    python -m research.retest_robustness.report --run DIR --coverage FILE --repro FILE
"""
import argparse
import json
from pathlib import Path


def f(x, d=2, pct=False):
    if x is None:
        return "—"
    if isinstance(x, str):
        return x
    return f"{x:.{d}f}" + (" %" if pct else "")


def build(res, cov, rep):
    L = [f"# Retest M (Retest + SPY > MA200) — independent check 2007-06 → 2016-10\n",
         f"**Verdict: {res['verdict']}**\n"]
    L.append("## Gates\n")
    L.append(f"- Reproduction of PR #19 (retest M and C, 12 books): **{'passed' if rep['passed'] else 'FAILED'}**")
    L.append(f"- Coverage ≥ 85 % every year: **{'passed' if cov['coverage_gate_passed'] else 'FAILED'}** "
             f"({cov['with_data']} of {cov['tickers_ever_member']} members with data)\n")
    L.append("| Year | Coverage | Stayed members | Removed members |\n|---|---:|---:|---:|")
    for y, v in cov["coverage_by_year"].items():
        L.append(f"| {y} | {f(v['coverage_pct'], 1, True)} | {f(v['stayed_cov_pct'], 1, True)} | {f(v['removed_cov_pct'], 1, True)} |")
    if "books" not in res:
        L.append(f"\n{res.get('reason', '')}")
        return "\n".join(L)
    L.append("\n## Books (each $10,000; costs per side)\n")
    L.append("| Window | Costs | Return | CAGR | Max DD | PF | Closed trades | Win rate | Calmar |\n|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for k, v in res["books"].items():
        w, c = k.split("|")
        L.append(f"| {w} | {c} | {f(v['return_pct'], 1, True)} | {f(v['cagr_pct'], 2, True)} | {f(v['max_dd_pct'], 1, True)} | "
                 f"{f(v['profit_factor'])} | {v['closed_trades']} | {f((v['win_rate'] or 0) * 100, 1, True)} | {f(v['calmar'])} |")
    L.append("\n## Benchmarks (ETF 2 bps, dividends v2)\n")
    L.append("| Window | SPY total | SPY price | 50/50 SPY/BIL | 50/50 SPY/cash |\n|---|---|---|---|---|")
    for w, b in res["benchmarks"].items():
        cell = lambda x: f"{f(x['cagr_pct'], 2, True)} / {f(x['max_dd_pct'], 1, True)}"      # noqa: E731
        L.append(f"| {w} | {cell(b['SPY100'])} | {cell(b['SPY_price'])} | {cell(b['SPY50_BIL50'])} | {cell(b['SPY50_CASH50'])} |")
    L.append("\n(CAGR / max DD)\n")
    L.append("## Criteria (§7)\n")
    for k, v in res["criteria"].items():
        L.append(f"- {k}: {'yes' if v else 'no'}")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--coverage", required=True)
    ap.add_argument("--repro", required=True)
    a = ap.parse_args(argv)
    res = json.loads((Path(a.run) / "results.json").read_text())
    txt = build(res, json.loads(Path(a.coverage).read_text()), json.loads(Path(a.repro).read_text()))
    print(txt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
