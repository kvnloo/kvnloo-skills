"""Host UI lock proof, at-most-once claims, quota pause and cooldown."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import time

import pytest

from phone import config, lock as lockmod
from phone.claims import ClaimStore
from phone.errors import LockError
from phone.quota import Cooldown, QuotaPause

pytestmark = pytest.mark.usefixtures("phone_env")


# lock -----------------------------------------------------------------------------------------

def test_proof_fails_without_the_lock_and_passes_with_it():
    with pytest.raises(LockError):
        lockmod.require_ui_lock("s22")
    with lockmod.UILock("s22", wait=2) as lk:
        assert lk.inherited is False
        lockmod.require_ui_lock("s22")
        status = lockmod.lock_status("s22")
        assert status["host"]["held"] and status["host"]["holders"][0]["is_ancestor"]
        assert status["shared"]["held"]
    with pytest.raises(LockError):
        lockmod.require_ui_lock("s22")
    assert not lockmod.lock_status("s22")["host"]["held"]


def test_an_unrelated_process_times_out_instead_of_sharing():
    holder = subprocess.Popen(
        [sys.executable, "-c",
         "import fcntl, sys, time\n"
         "f = open(sys.argv[1], 'a'); fcntl.flock(f, fcntl.LOCK_EX)\n"
         "print('held', flush=True); time.sleep(5)", str(config.lock_path("s22"))],
        stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "held"
        t0 = time.time()
        with pytest.raises(LockError, match="busy"):
            lockmod.UILock("s22", wait=0.6).__enter__()
        assert 0.5 <= time.time() - t0 < 3
        assert lockmod.lock_status("s22")["host"]["held"] is True
        assert lockmod.lock_status("s22")["host"]["holders"][0]["is_ancestor"] is False
        with pytest.raises(LockError):
            lockmod.require_ui_lock("s22")     # someone else holding it is not proof for us
    finally:
        holder.kill()
        holder.wait()


def test_a_child_inherits_the_proof_through_its_ancestor():
    code = textwrap.dedent("""
        import sys
        sys.path.insert(0, %r)
        from phone import lock
        lock.require_ui_lock("s22")
        with lock.UILock("s22", wait=0.5) as lk:
            print("inherited" if lk.inherited else "took-own")
    """) % str(config.__file__.rsplit("/phone/", 1)[0])
    with lockmod.UILock("s22", wait=2):
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                             env=os.environ)
    assert out.stdout.strip() == "inherited", out.stdout + out.stderr


def _hold(path, seconds=5):
    path.parent.mkdir(parents=True, exist_ok=True)
    holder = subprocess.Popen(
        [sys.executable, "-c",
         "import fcntl, sys, time\n"
         "f = open(sys.argv[1], 'a'); fcntl.flock(f, fcntl.LOCK_EX)\n"
         f"print('held', flush=True); time.sleep({seconds})", str(path)],
        stdout=subprocess.PIPE, text=True)
    assert holder.stdout.readline().strip() == "held"
    return holder


def test_an_inherited_host_lock_still_respects_a_screen_test_holding_the_shared_lock():
    """`flock /tmp/s22-ui.lock phone ...` must not drive the screen while a test worker holds only
    the shared lock (launch_queue.py took the shared lock first for exactly this reason)."""
    import fcntl
    host = config.lock_path("s22")
    with host.open("a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)                   # "an ancestor" (this process) holds host
        worker = _hold(config.shared_lock_path("s22"))
        try:
            with pytest.raises(LockError, match="busy"):
                lockmod.UILock("s22", wait=0.6).__enter__()
        finally:
            worker.kill()
            worker.wait()
        with lockmod.UILock("s22", wait=2) as lk:    # free again: shared taken, host inherited
            assert lk.inherited is True
            assert lockmod.lock_status("s22")["shared"]["holders"][0]["is_ancestor"] is True
        assert not lockmod.lock_status("s22")["shared"]["held"]


def test_proof_parses_proc_locks_like_the_kernel_prints_it(tmp_path):
    path = tmp_path / "x.lock"
    path.write_text("")
    st = path.stat()
    line = "1: FLOCK  ADVISORY  WRITE %d %02x:%02x:%d 0 EOF" % (
        4242, os.major(st.st_dev), os.minor(st.st_dev), st.st_ino)
    assert lockmod.holds_lock(path, {4242}, proc_locks=line)
    assert not lockmod.holds_lock(path, {1}, proc_locks=line)
    shared = line.replace("WRITE", "READ ")
    assert not lockmod.holds_lock(path, {4242}, proc_locks=shared)
    other_inode = "1: FLOCK  ADVISORY  WRITE 4242 %02x:%02x:%d 0 EOF" % (
        os.major(st.st_dev), os.minor(st.st_dev), st.st_ino + 1)
    assert not lockmod.holds_lock(path, {4242}, proc_locks=other_inode)


def test_lock_paths_follow_the_production_naming():
    assert config.lock_path("s22").name == "s22-ui.lock"
    assert config.shared_lock_path("s25").name == "s25-ui.lock"
    assert config.ledger_path("s22").name == "s22-agent-opened.json"


# claims ---------------------------------------------------------------------------------------

def test_claim_is_atomic_and_exclusive(tmp_path):
    store = ClaimStore(tmp_path / "c")
    assert store.claim_tag("ALPHA-1", "s22") is True
    assert store.claim_tag("ALPHA-1", "s22") is False
    assert store.claim_tag("ALPHA-1", "s25") is False
    assert store.claim_tag("BETA-2", "s22") is True


def test_bad_tags_are_rejected(tmp_path):
    store = ClaimStore(tmp_path / "c")
    for bad in ("", "../x", "a b", "-x", "x" * 81):
        with pytest.raises(ValueError):
            store.claim_tag(bad, "s22")


def test_finalize_routes_statuses_like_the_queue_launcher(tmp_path):
    store = ClaimStore(tmp_path / "c")
    for tag in ("T-SENT", "T-UNC", "T-LIM", "T-FAIL", "T-BUSY"):
        assert store.claim_tag(tag, "s22")
    rows = [{"tag": "T-SENT", "status": "sent"}, {"tag": "T-UNC", "status": "unconfirmed"},
            {"tag": "T-LIM", "status": "rate_limited"}, {"tag": "T-FAIL", "status": "failed"},
            {"tag": "T-BUSY", "status": "owner_busy"}]
    store.finalize(rows, "s22")
    assert store.launched() == {"T-SENT", "T-UNC", "T-LIM"}
    assert store.unconfirmed_file.read_text().split() == ["T-UNC"]
    # a failed claim stays claimed (never auto-retried); owner_busy un-claims
    assert store.claim_tag("T-FAIL", "s22") is False
    assert store.claim_tag("T-BUSY", "s22") is True
    assert len(store.dispatches_file.read_text().splitlines()) == 5


def test_queue_claim_renames_before_send_and_skips_launched(tmp_path):
    store = ClaimStore(tmp_path / "run")
    store.queue.mkdir(parents=True)
    for i, tag in enumerate(("A-1", "B-2", "C-3")):
        (store.queue / f"{i}.json").write_text(json.dumps({"tag": tag, "task": "t"}))
    (store.queue / "dup.json").write_text(json.dumps({"tag": "A-1", "task": "same tag again"}))
    (store.queue / "bad.json").write_text(json.dumps({"task": "no tag"}))
    brief, reason = store.claim_next("s22")
    assert brief["tag"] == "A-1" and reason is None
    assert (store.queue / "0.json.claimed-s22").exists() and not (store.queue / "0.json").exists()
    brief, _ = store.claim_next("s25")
    assert brief["tag"] == "B-2"            # A-1 (and its duplicate file) are excluded
    store.launched_file.write_text("C-3\n")
    brief, reason = store.claim_next("s22")
    assert brief is None and reason is None  # nothing eligible


def test_not_ready_refusal_leaves_the_brief_eligible(tmp_path):
    store = ClaimStore(tmp_path / "run")
    store.queue.mkdir(parents=True)
    (store.queue / "0.json").write_text(json.dumps({"tag": "A-1"}))
    brief, reason = store.claim_next("s22", ready=lambda: "owner active")
    assert brief is None and reason == "owner active"
    assert (store.queue / "0.json").exists()
    dry, _ = store.claim_next("s22", dry=True)
    assert dry["tag"] == "A-1" and (store.queue / "0.json").exists()


def test_owner_busy_row_restores_a_queue_claim(tmp_path):
    store = ClaimStore(tmp_path / "run")
    store.queue.mkdir(parents=True)
    (store.queue / "0.json").write_text(json.dumps({"tag": "A-1"}))
    store.claim_next("s22")
    store.finalize([{"tag": "A-1", "status": "owner_busy"}], "s22")
    assert (store.queue / "0.json").exists() and not list(store.queue.glob("*.claimed-*"))


# quota and cooldown ---------------------------------------------------------------------------

def test_quota_pause_extends_never_shortens():
    q = QuotaPause("chatgpt")
    assert q.status()["paused"] is False
    future = time.time() + 1000
    assert q.extend(future)["paused"] is True
    assert q.extend(time.time() + 10)["resume_epoch"] == pytest.approx(future)
    assert q.path.name == "chatgpt-quota-pause"


def test_quota_pause_unreadable_fails_closed():
    q = QuotaPause("chatgpt")
    q.path.write_text("not a number")
    st = q.status()
    assert st["paused"] is True and "unreadable" in st["reason"]
    assert q.path.read_text() == "not a number"      # never overwritten while unreadable
    for bad in ("-5", "inf", "nan"):
        q.path.write_text(bad)
        assert q.status()["paused"] is True


def test_quota_pause_expires():
    q = QuotaPause("chatgpt")
    q.extend(time.time() - 1)
    assert q.status()["paused"] is False
    assert q.status(clock=lambda: 0)["paused"] is True


def test_cooldown_reserve_and_fail_closed():
    c = Cooldown("chatgpt", "s22", 5)
    assert c.cooling()["cooling"] is False
    c.reserve(time.time())
    assert c.cooling()["cooling"] is True
    assert c.cooling(clock=lambda: time.time() + 6)["cooling"] is False
    c.path.write_text("garbage")
    assert c.cooling()["cooling"] is True
    assert c.path.name == "chatgpt-last-dispatch-s22"
