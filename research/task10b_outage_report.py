"""Task 10B — run the deterministic outage scenarios and write their actual outputs.
Usage: python research/task10b_outage_report.py  ->  research/results/task10/OUTAGE_SCENARIOS.md
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import test_paper  # noqa: E402  (scenarios live next to their tests)

DESC = {
    "S1_timely": "AAA signal d0 (on time) -> fill d1 -> time exit d4; runner every evening",
    "S2_late_entry": "AAA queued on time d0; runner DOWN d1; d2 run processes d1 late",
    "S3_late_exit": "AAA filled d1 on time; runner DOWN on exit day d4; d5 run processes d4",
    "S4_late_signal": "d0 processed only at 10:00 NY on d1 (after the open): BBB late",
    "S5_mixed": "AAA timely round trip; BBB queued d4 on time, filled d5 while DOWN; "
                "CCC found during the d5 catch-up",
    "S6_late_entry_and_stop": "AAA queued d0; runner DOWN d1-d2; d3 run: late entry d1 + "
                              "late stop exit d2",
}


def main():
    S = test_paper.outage_scenarios()
    days = S.pop("_days")
    lines = ["# Task 10B — outage scenarios (actual outputs)", "",
             "Deterministic: flat 100 bars, scripted signals (rs 90, stop 95), hold 3 bars, "
             "0 bps; runs at 18:00 New York unless noted. Days: "
             + ", ".join(f"d{k}={v}" for k, v in days.items() if k < 8), ""]
    for name, (summ, st) in S.items():
        f = summ["forward"]
        g = f["genuine_forward"]
        lines += [f"## {name}", "", DESC[name], "",
                  "| field | value |", "|---|---|",
                  f"| sessions in last run | {json.dumps(summ['sessions'])} |",
                  f"| A timely: closed / open | {f['timely']['trades']['closed']} / "
                  f"{f['timely']['open_positions']} |",
                  f"| B reconstructed: closed / open | {f['reconstructed']['trades']['closed']} / "
                  f"{f['reconstructed']['open_positions']} |",
                  f"| B events | {json.dumps(f['reconstructed']['events'])} |",
                  f"| C late, never traded | {f['late_not_traded']['count']} "
                  f"{json.dumps([s['ticker'] for s in f['late_not_traded']['signals']])} |",
                  f"| genuine_forward.available | {g['available']} |",
                  f"| contaminated_since / genuine_through | {g['contaminated_since']} / "
                  f"{g['genuine_through']} |",
                  f"| genuine return % / final equity | "
                  f"{None if not g['metrics'] else round(g['metrics']['return_pct'], 4)} / "
                  f"{None if not g['metrics'] else round(g['metrics']['final_equity'], 2)} |",
                  f"| genuine reason | {g['reason']} |",
                  f"| observed contains reconstructed | "
                  f"{f['observed_portfolio']['contains_reconstructed']} |",
                  f"| late-processed sessions | {f['late_processed_sessions']} |",
                  f"| ledger | {json.dumps([{k: t[k] for k in ('ticker', 'entry_date', 'exit_date', 'reason', 'entry_processed_late', 'exit_processed_late')} for t in st['ledger']])} |",
                  f"| open positions | {json.dumps([{k: p[k] for k in ('ticker', 'entry_date', 'entry_processed_late')} for p in st['positions'].values()])} |",
                  ""]
    out = ROOT / "research" / "results" / "task10" / "OUTAGE_SCENARIOS.md"
    out.write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
