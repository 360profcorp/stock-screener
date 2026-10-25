# Long Breakout + Retest | 2017–2026 P&L diagnostic

This is a **prepared research package**, not a completed ten-year calculation. The code requires the user's `360profcorp/stock-screener` repository and the original ~10-year GitHub Actions dataset artifact; those historic bars are **not included** in the archive.

## Package content

- `PLAN.md` — frozen questions and controls: all diagnostic cuts exploratory, no new optimizations.
- `CLAUDE_TASK.md` — exact handoff / stop rules for Claude Code.
- `research/long_diagnostic/run.py` — read-only diagnostic that replays Breakout and Retest, requires equality with PR #19, reconciles daily equity to closed and open positions, labels gaps and MFE/MAE, computes post-exit close-to-close returns, and writes a `REPORT.md` plus detailed CSV and JSON outputs. It writes only to `research/results/long_diagnostic/runs/<time>`.
- `research/long_diagnostic/test_diagnostic.py` — synthetic tests for price-path bounds, after-exit coverage, open-position accounting, and grouping primitives.

## Execution from research branch

1. Branch from `research/long-crisis-v1` (NOT from `main`). The branch contains `research/crisis/run.py`, the 10-year control reference JSON, and the existing research engine.
2. Copy this package's `research/long_diagnostic/` directory into the repo. Commit `PLAN.md` **before** executing historic data; adding code/tests in same commit is fine.
3. Obtain the dataset artifact for GitHub Actions run ID `40152515701`, `shorts10y-dataset-40152515701`. Use `actions/download-artifact@v4` with explicit `run-id`, name and `github-token` in a RESEARCH-ONLY workflow, not in any production workflow.
4. From repo root:

```bash
python -m unittest research.long_diagnostic.test_diagnostic -v
python -m research.long_diagnostic.run \
  --dataset "$RUNNER_TEMP/shorts10y" \
  --reference research/results/crisis/runs/2026-10-25T0255Z/results.json
```

5. Do not accept the report unless BOTH the 10bps and 25bps control books reproduce PR #19, no missing/duplicated entries remain, and portfolio P&L reconciles to the cent. Audit extra/different features. Show charts for by-year returns, stop vs time exits, MFE/MAE, concentration in rare winners, realized gap loss and full portfolio exposure.

## Current validation level

- Pure-function unit tests passed locally, but **integration with the live GitHub research dataset has not been executed here**. Claude must run the original engine and examine the outputs; do not present synthetic tests as proof of historical performance.
- Nothing was committed to `main`, nor to any GitHub branch from this package. The GitHub connector permits read access but rejected branch creation (HTTP 403), so execution must happen through the owner's Claude Code GitHub authorization.
