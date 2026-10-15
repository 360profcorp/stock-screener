#!/usr/bin/env bash
# Commit and push paper state with retries (Task 10B, P1-3).
#  - never resolves a conflict automatically: if the remote changed the same files since this
#    run started, the rebase stops, the job FAILS (exit 2) and nothing is overwritten
#  - retries transient push failures (network / remote moved without conflict), 5 attempts
# Usage: scripts/persist_state.sh "<commit message>" <path> [<path> ...]
set -uo pipefail
msg="$1"; shift
branch="$(git symbolic-ref --short -q HEAD || echo "${GITHUB_REF_NAME:-}")"
[ -n "$branch" ] || { echo "::error::cannot determine the branch"; exit 1; }
git add -- "$@" 2>/dev/null || true
if git diff --cached --quiet; then echo "nothing to persist"; exit 0; fi
git commit -q -m "$msg" || { echo "::error::commit failed"; exit 1; }
summary() { [ -n "${GITHUB_STEP_SUMMARY:-}" ] && echo "$1" >> "$GITHUB_STEP_SUMMARY"; return 0; }
for attempt in 1 2 3 4 5; do
  if git ls-remote --exit-code --heads origin "$branch" >/dev/null 2>&1; then
    if ! git pull --rebase -q origin "$branch"; then
      git rebase --abort 2>/dev/null || true
      echo "::error::CONFLICT: remote paper state changed since this run started. Nothing was overwritten. Inspect both versions; restore from the run artifact only with 'paper_run.py restore' (it refuses stale backups)."
      summary "### ❌ Paper state NOT saved — conflicting remote change"
      exit 2
    fi
  fi
  if git push -q origin "HEAD:$branch"; then echo "persisted on attempt $attempt"; exit 0; fi
  echo "::warning::push attempt $attempt failed; retrying"
  sleep $((attempt * 10))
done
echo "::error::push failed after 5 attempts — state is only in the run artifact backup"
summary "### ❌ Paper state NOT pushed after 5 attempts — download the paper-state artifact"
exit 1
