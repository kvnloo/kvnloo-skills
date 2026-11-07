"""Account-wide quota pause and per-phone dispatch cooldown (file based, fail closed).

Quota pause: one file per app account, `<lock dir>/<app>-quota-pause`, holding a Unix resume epoch,
updated under a companion `.lock` flock. Concurrent phones may extend a pause, never shorten it.
Unreadable or invalid contents are treated as paused. Nobody clears the file to get around a limit:
a later reset time shown by the provider may be written, an earlier one never replaces a later one.

Cooldown: `<lock dir>/<app>-last-dispatch-<role>` holds the epoch of the last dispatch. It is reserved
BEFORE transport, so an ambiguous send never accelerates a retry.
"""
from __future__ import annotations

import fcntl
import os
import time
from pathlib import Path

from . import config

DEFAULT_PAUSE_SECONDS = 3 * 3600  # the operator's fallback when the app gives no reset time


def _valid(value: float) -> bool:
    return 0 <= value < float("inf")


class QuotaPause:
    def __init__(self, app: str, directory: Path | None = None):
        base = directory or config.lock_dir()
        self.path = base / f"{app}-quota-pause"
        self.lock_path = Path(str(self.path) + ".lock")

    def status(self, resume_at: float | None = None, clock=time.time) -> dict:
        """Read (and optionally extend) the pause. Returns
        {"paused": bool, "resume_epoch": float, "reason": str}."""
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                resume = float(self.path.read_text()) if self.path.exists() else 0.0
                if not _valid(resume):
                    raise ValueError("invalid resume epoch")
            except (OSError, ValueError):
                return {"paused": True, "resume_epoch": 0.0, "reason": "pause file unreadable"}
            if resume_at is not None:
                resume = max(resume, resume_at)
                tmp = self.path.with_name(self.path.name + f".tmp{os.getpid()}")
                tmp.write_text(str(resume) + "\n")
                os.replace(tmp, self.path)
        paused = clock() < resume
        return {"paused": paused, "resume_epoch": resume,
                "reason": f"quota paused until epoch {resume:.0f}" if paused else ""}

    def paused(self, resume_at: float | None = None) -> bool:
        return self.status(resume_at)["paused"]

    def extend(self, resume_at: float) -> dict:
        return self.status(resume_at)


class Cooldown:
    def __init__(self, app: str, role: str, interval: float, directory: Path | None = None):
        base = directory or config.lock_dir()
        self.path = base / f"{app}-last-dispatch-{role}"
        self.interval = interval

    def cooling(self, clock=time.time) -> dict:
        try:
            last = float(self.path.read_text()) if self.path.exists() else 0.0
            if not 0 <= last < float("inf"):
                raise ValueError("invalid dispatch epoch")
        except (OSError, ValueError):
            return {"cooling": True, "until_epoch": 0.0, "reason": "dispatch marker unreadable"}
        until = last + self.interval
        if clock() < until:
            return {"cooling": True, "until_epoch": until,
                    "reason": f"cooling down until epoch {until:.0f}"}
        return {"cooling": False, "until_epoch": until, "reason": ""}

    def reserve(self, when: float | None = None) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(str(time.time() if when is None else when) + "\n")
