"""At-most-once claim semantics for sends.

A send cannot be made exactly-once across an Android tap and a host crash, so the driver chooses
"never twice" over "always delivered":

  * A tag is claimed BEFORE any UI send, atomically, under a flock. Claimed and launched tags are
    excluded from every later claim, including duplicate tags under different filenames.
  * `sent`, `unconfirmed` and `rate_limited` go to launched.txt (rate limit is detected after the
    send attempt). `unconfirmed` also goes to unconfirmed.txt: a transport loss or missing receipt
    is conservatively "maybe sent".
  * A `failed` claim stays claimed and is never retried automatically. Only `owner_busy` (the driver
    refused before touching the UI) un-claims the tag so it stays eligible.
  * Claims are durable audit evidence. Never rename an old claim back or delete one during a run. A
    person inspects uncertain claims and, only if truly lost, enqueues a NEW tag.

Two shapes are supported, both under one `.queue-claims.lock`:
  * single tag:  claim_tag(tag, device) / finalize(rows)
  * queue dir:   claim_next(device, ready) over `queue/*.json` files renamed to
                 `*.json.claimed-<device>` before the send.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

_TAG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}")


class ClaimStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.queue = self.root / "queue"
        self.launched_file = self.root / "launched.txt"
        self.unconfirmed_file = self.root / "unconfirmed.txt"
        self.dispatches_file = self.root / "dispatches.jsonl"
        self.lock_file = self.root / ".queue-claims.lock"
        self.claims = self.root / "claims"

    @contextmanager
    def locked(self):
        self.root.mkdir(parents=True, exist_ok=True)
        with self.lock_file.open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    # state ---------------------------------------------------------------------------------

    def launched(self) -> set[str]:
        return set(self.launched_file.read_text().split()) if self.launched_file.exists() else set()

    def claimed_tags(self) -> set[str]:
        tags = set()
        if self.queue.exists():
            for p in self.queue.glob("*.json.claimed-*"):
                try:
                    tags.add(json.loads(p.read_text())["tag"])
                except (OSError, ValueError, KeyError):
                    continue
        if self.claims.exists():
            tags |= {p.name.rsplit(".claimed-", 1)[0] for p in self.claims.glob("*.claimed-*")}
        return tags

    # single tag ----------------------------------------------------------------------------

    def claim_tag(self, tag: str, device: str) -> bool:
        """Atomically claim a tag. False when it is already launched or claimed."""
        if not _TAG.fullmatch(tag):
            raise ValueError("tag must match [A-Za-z0-9][A-Za-z0-9._-]{0,79}")
        with self.locked():
            if tag in self.launched() or tag in self.claimed_tags():
                return False
            self.claims.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.claims / f"{tag}.claimed-{device}",
                         os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            os.close(fd)
            return True

    def release_tag(self, tag: str, device: str) -> None:
        """Un-claim a tag the driver refused before touching the UI (owner_busy only)."""
        p = self.claims / f"{tag}.claimed-{device}"
        with self.locked():
            if p.exists():
                p.unlink()

    # queue dir -----------------------------------------------------------------------------

    def claim_next(self, device: str, ready: Callable[[], str | None] | None = None,
                   required=("tag",), dry: bool = False):
        """Claim the next eligible brief. Returns (brief|None, reason|None).

        `ready` runs under the claims lock before the claim and returns a refusal reason (owner
        busy, device unreachable) or None. A refusal leaves the brief eligible."""
        with self.locked():
            launched = self.launched()
            claimed = self.claimed_tags()
            for path in sorted(self.queue.glob("*.json")) if self.queue.exists() else []:
                brief = json.loads(path.read_text())
                if set(required) - brief.keys():
                    continue
                if brief["tag"] in launched or brief["tag"] in claimed:
                    continue
                if ready and not dry:
                    reason = ready()
                    if reason:
                        return None, reason
                if not dry:
                    path.rename(path.with_name(path.name + f".claimed-{device}"))
                return brief, None
        return None, None

    # results -------------------------------------------------------------------------------

    def finalize(self, rows: list[dict], device: str) -> None:
        """Record receipts and update launched.txt / unconfirmed.txt under the claims lock."""
        with self.locked():
            with self.dispatches_file.open("a") as log:
                for row in rows:
                    if row["status"] == "owner_busy":
                        # refused before touching the UI: the tag stays eligible
                        for claim in (self.queue.glob(f"*.json.claimed-{device}")
                                      if self.queue.exists() else []):
                            try:
                                if json.loads(claim.read_text())["tag"] == row["tag"]:
                                    claim.rename(claim.with_name(
                                        claim.name.removesuffix(f".claimed-{device}")))
                            except (OSError, ValueError, KeyError):
                                continue
                        single = self.claims / f"{row['tag']}.claimed-{device}"
                        if single.exists():
                            single.unlink()
                    log.write(json.dumps(row, default=str) + "\n")
            with self.launched_file.open("a") as done, self.unconfirmed_file.open("a") as unsure:
                for row in rows:
                    if row["status"] in ("sent", "unconfirmed", "rate_limited"):
                        done.write(row["tag"] + "\n")
                    if row["status"] == "unconfirmed":
                        unsure.write(row["tag"] + "\n")
