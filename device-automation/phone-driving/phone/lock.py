"""Host UI lock discipline.

One exclusive flock per phone, `<lock dir>/<role>-ui.lock`, shared by every tool on the host
(the queue launcher, test workers, this package). UI access requires a /proc/locks proof that the
exclusive lock is owned by this process or a live ancestor, so `flock -w 120 FILE phone ...`
and `with Phone.session(...)` both qualify, and a process that forgot the lock cannot touch the UI.

Order, as in the production launcher: the optional shared lock first (bounded wait), then the host
lock. Never wrap a tool that takes these locks itself in another flock on the same path.
"""
from __future__ import annotations

import fcntl
import os
import time
from pathlib import Path

from . import config
from .errors import LockError


def _ancestors() -> set[int]:
    ancestors: set[int] = set()
    pid = os.getpid()
    while pid and pid not in ancestors:
        ancestors.add(pid)
        try:
            fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
            pid = int(fields[1])
        except (OSError, IndexError, ValueError):
            break
    return ancestors


def _lock_entries(path: Path, proc_locks: str | None = None) -> list[dict]:
    """Exclusive flock entries on this file from /proc/locks: [{"pid": int}, ...]."""
    try:
        stat = path.stat()
    except OSError:
        return []
    text = proc_locks if proc_locks is not None else Path("/proc/locks").read_text()
    out = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 8 or fields[1:4] != ["FLOCK", "ADVISORY", "WRITE"]:
            continue
        try:
            major, minor, inode = fields[5].split(":")
            if (int(inode) == stat.st_ino and int(major, 16) == os.major(stat.st_dev)
                    and int(minor, 16) == os.minor(stat.st_dev)):
                out.append({"pid": int(fields[4])})
        except ValueError:
            continue
    return out


def holds_lock(path: Path, pids: set[int] | None = None, proc_locks: str | None = None) -> bool:
    pids = _ancestors() if pids is None else pids
    return any(e["pid"] in pids for e in _lock_entries(path, proc_locks))


def require_ui_lock(role: str) -> None:
    """Raise LockError unless an exclusive flock on the role's host lock is owned by this process
    or a live ancestor (proved through /proc/locks, not assumed)."""
    path = config.lock_path(role)
    if not path.exists():
        raise LockError(f"exclusive {path} must be held by this tool or an ancestor "
                        "(lock file does not exist)")
    if not holds_lock(path):
        raise LockError(f"exclusive {path} must be held by this tool or an ancestor")


def lock_status(role: str) -> dict:
    """Who holds the role's locks, from /proc/locks only (no probing, no lock taken)."""
    out = {}
    for label, path in (("host", config.lock_path(role)), ("shared", config.shared_lock_path(role))):
        if path is None:
            out[label] = {"enabled": False}
            continue
        holders = _lock_entries(path)
        info = {"enabled": True, "exists": path.exists(), "held": bool(holders), "holders": []}
        for h in holders:
            comm = "unknown"
            try:
                comm = Path(f"/proc/{h['pid']}/comm").read_text().strip()
            except OSError:
                pass
            info["holders"].append({"pid": h["pid"], "comm": comm,
                                    "is_ancestor": h["pid"] in _ancestors()})
        out[label] = info
    return out


class UILock:
    """Context manager taking the shared lock then the host lock, then proving ownership.

    If an ancestor already holds the host lock, nothing is taken (inherited=True)."""

    def __init__(self, role: str, wait: float = 120.0, use_shared: bool = True):
        self.role = config.check_role(role)
        self.wait = wait
        self.use_shared = use_shared
        self.inherited = False
        self._files: list = []

    def _take(self, path: Path, deadline: float, blocking_poll: float = 0.25):
        path.parent.mkdir(parents=True, exist_ok=True)
        f = path.open("a")
        while True:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._files.append(f)
                return
            except BlockingIOError:
                if time.time() >= deadline:
                    f.close()
                    raise LockError(f"{path} busy for {self.wait:.0f}s; another driver holds this "
                                    "phone's UI lock")
                time.sleep(blocking_poll)

    def __enter__(self):
        host = config.lock_path(self.role)
        if host.exists() and holds_lock(host):
            self.inherited = True
            return self
        deadline = time.time() + self.wait
        shared = config.shared_lock_path(self.role) if self.use_shared else None
        try:
            if shared is not None:
                self._take(shared, deadline)
            self._take(host, deadline)
            require_ui_lock(self.role)
        except BaseException:
            self.release()
            raise
        return self

    def release(self):
        while self._files:
            f = self._files.pop()
            try:
                fcntl.flock(f, fcntl.LOCK_UN)
            finally:
                f.close()

    def __exit__(self, *exc):
        self.release()
        return False
