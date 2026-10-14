"""
Encrypted bot state (Schwab token, plan, positions, trade history).

The repository is public, so the state is stored as ONE encrypted file: state/trader.enc.
The key is derived from STATE_PASSWORD (a password only you know), which lives in
GitHub → Settings → Secrets and in Streamlit → Settings → Secrets. Without it the
file is unreadable noise.
"""
import base64
import json
import time

import requests
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

STATE_PATH = "state/trader.enc"
REPO = "360profcorp/stock-screener"


def empty_state() -> dict:
    return {"token": None, "plan": None, "positions": [], "closed": [], "log": [],
            "last_execute": None, "mode": None, "updated": None}


def _fernet(password: str) -> Fernet:
    if not password:
        raise ValueError("STATE_PASSWORD is empty")
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=b"visar-trader-v1",
                     iterations=390_000)
    return Fernet(base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8"))))


def encrypt(state: dict, password: str) -> bytes:
    state = {**state, "updated": time.time()}
    return _fernet(password).encrypt(json.dumps(state, default=str).encode("utf-8"))


def decrypt(blob: bytes, password: str) -> dict:
    try:
        data = json.loads(_fernet(password).decrypt(blob))
    except InvalidToken as e:
        raise ValueError("wrong STATE_PASSWORD (or damaged state file)") from e
    return {**empty_state(), **data}


def load_file(path: str, password: str) -> dict:
    try:
        with open(path, "rb") as f:
            return decrypt(f.read(), password)
    except FileNotFoundError:
        return empty_state()


def save_file(path: str, state: dict, password: str) -> None:
    import os
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        f.write(encrypt(state, password))


def log(state: dict, text: str, keep: int = 200) -> None:
    state.setdefault("log", []).append({"t": time.strftime("%Y-%m-%d %H:%M"), "msg": text})
    state["log"] = state["log"][-keep:]


class GitHubStore:
    """Read/write the encrypted state in the repo through the GitHub API (used by the app)."""

    def __init__(self, password: str, token: str | None = None, repo: str = REPO,
                 path: str = STATE_PATH):
        self.password, self.token, self.repo, self.path = password, token, repo, path

    def _headers(self):
        h = {"Accept": "application/vnd.github+json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def get(self):
        """Returns (state, sha). sha is None if the file doesn't exist yet."""
        r = requests.get(f"https://api.github.com/repos/{self.repo}/contents/{self.path}",
                         headers=self._headers(), params={"ref": "main"}, timeout=20)
        if r.status_code == 404:
            return empty_state(), None
        r.raise_for_status()
        j = r.json()
        return decrypt(base64.b64decode(j["content"]), self.password), j["sha"]

    def put(self, state: dict, sha: str | None, message: str) -> str:
        if not self.token:
            raise PermissionError("GH_TOKEN is not set — the app can't save changes")
        body = {"message": message, "branch": "main",
                "content": base64.b64encode(encrypt(state, self.password)).decode()}
        if sha:
            body["sha"] = sha
        r = requests.put(f"https://api.github.com/repos/{self.repo}/contents/{self.path}",
                         headers=self._headers(), json=body, timeout=20)
        if r.status_code == 409:
            raise RuntimeError("state changed in the meantime — reload and try again")
        r.raise_for_status()
        return r.json()["content"]["sha"]
