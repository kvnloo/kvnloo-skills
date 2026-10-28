"""One send, end to end, with every guard the production queue launcher has.

Order (each step can refuse before the UI is touched):
  1. quota pause (account wide, fail closed)
  2. host UI lock (shared lock first, then the host lock, /proc/locks proof)
  3. quota pause again, then per-phone cooldown (real sends only)
  4. discover; owner-activity check over adb; only then connect uiautomator2 (refusal leaves
     the tag eligible)
  5. claim the tag (atomic, before any UI send)             <- at-most-once starts here
  6. reserve the cooldown BEFORE transport
  7. adapter.launch (the UI work); a crash after the claim is "unconfirmed", never retried
  8. a rate limit extends the account-wide pause (never shortens it)
  9. receipts and claim bookkeeping

--preflight-only runs 4 and 7 with preflight=True: nothing is claimed, no cooldown is reserved, and
Send is never tapped.
"""
from __future__ import annotations

import time
from pathlib import Path

from . import config, lock as lockmod, receipts
from .claims import ClaimStore
from .device import Phone
from .errors import LockError, OwnerBusy, PhoneError
from .quota import DEFAULT_PAUSE_SECONDS

REFUSALS = ("owner_busy", "quota_paused", "cooling_down", "already_claimed", "lock_busy")


def _row(adapter, role, tag, status, **extra) -> dict:
    return {"tag": tag, "device": role, "adapter": adapter.name, "status": status,
            "send_attempted": False, **extra}


def claim_store(adapter, root: Path | None = None) -> ClaimStore:
    return ClaimStore(root or config.state_dir() / "claims" / adapter.name)


def dispatch_one(adapter, role: str, tag: str, text: str, *, effort: str | None = None,
                 preflight: bool = False, store: ClaimStore | None = None,
                 lock_wait: float = 120.0) -> dict:
    config.require_role_allowed(role)
    adapter.validate_tag(tag)
    text = adapter.prepare_text(tag, text)
    store = store or claim_store(adapter)
    quota = adapter.quota

    def refuse(status, reason):
        row = _row(adapter, role, tag, status, error=reason)
        receipts.write({"action": "chat_send", **row})
        return row

    if quota is not None:
        q = quota.status()
        if q["paused"]:
            return refuse("quota_paused", q["reason"])
    try:
        ui_lock = lockmod.UILock(role, wait=lock_wait)
        ui_lock.__enter__()
    except LockError as e:
        return refuse("lock_busy", str(e))
    try:
        if quota is not None:
            q = quota.status()
            if q["paused"]:
                return refuse("quota_paused", q["reason"])
        cooldown = adapter.cooldown(role)
        if not preflight:
            c = cooldown.cooling()
            if c["cooling"]:
                return refuse("cooling_down", c["reason"])
        try:
            # connect() checks the owner over adb BEFORE uiautomator starts (as burst.py did).
            ph = Phone(role, lock=False, exempt_pkgs={adapter.package}).connect()
        except OwnerBusy as e:
            return refuse("owner_busy", str(e))
        except (PhoneError, OSError) as e:
            return refuse("failed", f"{type(e).__name__}: {e}")
        reason = ph.owner_busy(extra_exempt={adapter.package})
        if reason:
            return refuse("owner_busy", reason)
        started = time.time()
        if not preflight:
            if not store.claim_tag(tag, role):
                return refuse("already_claimed", "tag already launched or claimed")
            cooldown.reserve(started)
        try:
            rec = adapter.launch(ph, tag, text, effort=effort, preflight=preflight)
        except Exception as e:  # noqa: BLE001 - after the claim, never auto-retry
            rec = {"tag": tag, "status": "unconfirmed" if not preflight else "failed",
                   "error": f"no receipt: {type(e).__name__}: {e}"[:300],
                   "error_class": type(e).__name__, "send_attempted": not preflight}
        row = {**rec, "device": role, "adapter": adapter.name, "transport": ph.device_id(),
               "dispatch_t0": started, "dispatch_end": time.time()}
        if row["status"] == "rate_limited" and quota is not None:
            # No reset time is supplied by the app: use the operator's fallback pause.
            quota.extend(max(row.get("t0", started), started) + DEFAULT_PAUSE_SECONDS)
        if not preflight:
            store.finalize([row], role)
        receipts.write({"action": "chat_preflight" if preflight else "chat_send", **row})
        return row
    finally:
        ui_lock.release()
