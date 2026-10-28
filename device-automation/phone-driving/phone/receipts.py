"""Receipts: an append-only JSONL audit trail of what the driver did.

A receipt records the role, action, status, timing, and error class. It never holds typed text,
screen content, serials, or addresses; text is represented by its length and a short hash, and a
device by a short hash of its transport id.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import time

from . import config


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def text_digest(text: str) -> dict:
    return {"chars": len(text), "sha256_8": hashlib.sha256(text.encode()).hexdigest()[:8]}


def device_digest(serial: str) -> str:
    return hashlib.sha256(serial.encode()).hexdigest()[:8]


def write(record: dict, path=None) -> dict:
    """Append one receipt (adds `at` and `pid`). Never raises: an audit failure must not change the
    outcome of the action it describes; the failure is returned in the record instead."""
    rec = {"at": now(), "pid": os.getpid(), **record}
    path = path or config.receipts_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(rec, default=str) + "\n"
        with path.open("a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.write(line)
            fcntl.flock(f, fcntl.LOCK_UN)
    except OSError as e:
        rec["receipt_error"] = f"{type(e).__name__}: {e}"
    return rec


def read(path=None, limit: int | None = None) -> list[dict]:
    path = path or config.receipts_path()
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows[-limit:] if limit else rows
