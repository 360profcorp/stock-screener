"""Commit and push state/trader.enc from a bot run without losing a concurrent app save.

    python scripts/save_trader_state.py BASE_ENC "commit message"

BASE_ENC: copy of state/trader.enc at checkout (before the bot ran). If the remote file
changed meanwhile (the app saved a Schwab login or a plan approval), the three versions are
decrypted and merged with vault.merge_states; any other conflict fails loudly (exit 1) and
nothing is overwritten."""
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import vault  # noqa: E402

PATH = vault.STATE_PATH


def git(*a, check=True):
    return subprocess.run(["git", *a], check=check, capture_output=True, text=True)


def main(base_file, msg, attempts=4):
    pw = os.environ["STATE_PASSWORD"]
    base = vault.decrypt(Path(base_file).read_bytes(), pw)
    ours_blob = Path(PATH).read_bytes()
    if ours_blob == Path(base_file).read_bytes():
        print("state unchanged — nothing to save")
        return 0
    ours = vault.decrypt(ours_blob, pw)
    for k in range(attempts):
        git("fetch", "origin", "main")
        remote = git("show", f"origin/main:{PATH}", check=False)
        theirs_blob = subprocess.run(["git", "show", f"origin/main:{PATH}"],
                                     capture_output=True).stdout if remote.returncode == 0 else None
        if theirs_blob is not None and theirs_blob != Path(base_file).read_bytes():
            theirs = vault.decrypt(theirs_blob, pw)
            state = vault.merge_states(base, ours, theirs)     # StateConflict -> exit 1
            print("remote state changed during the run — merged app fields")
        else:
            state = ours
        git("reset", "-q", "origin/main")          # index = remote; only the state file is added
        vault.save_file(PATH, state, pw)
        git("add", PATH)
        if git("diff", "--cached", "--quiet", check=False).returncode == 0:
            print("nothing to commit")
            return 0
        git("commit", "-q", "-m", msg)
        if git("push", "origin", "HEAD:main", check=False).returncode == 0:
            print("state saved")
            return 0
        base_blob = theirs_blob if theirs_blob is not None else Path(base_file).read_bytes()
        Path(base_file).write_bytes(base_blob)
        base = vault.decrypt(base_blob, pw) if theirs_blob is not None else base
        ours = state
        time.sleep(3 * (k + 1))
    print("could not push state after retries", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
