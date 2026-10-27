"""CLI for the 50 % SPY / 50 % BIL paper book (paper_etf.py). Paper only: no broker, no orders.

    python etf5050_run.py daily      # process every closed session since the last run
    python etf5050_run.py status     # print the summary
"""
import json
import sys
import time

import paper_etf as P


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else "status"
    if cmd == "daily":
        err = None
        for attempt in range(3):                     # transient Yahoo failures only
            try:
                bars = P.download()
                if all(len(bars[s]) > 20 for s in P.SYMS):
                    break
                err = "empty download"
            except Exception as e:                   # noqa: BLE001
                err = f"{type(e).__name__}: {e}"
            time.sleep(10 * (attempt + 1))
        else:
            raise SystemExit(f"price download failed: {err}")
        st = P.run_daily(bars=bars)
        print(json.dumps(P.summary(st), indent=1, default=str))
        return 0
    s = P.load()
    print(json.dumps(P.summary(s), indent=1, default=str) if s else "not activated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
