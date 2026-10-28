"""One send end to end (dispatch order and at-most-once bookkeeping) and the CLI contract."""
from __future__ import annotations

import io
import json
import time

import pytest

from phone import cli, config, dispatch, lock as lockmod, receipts
from phone.adapters.base import Adapter
from phone.errors import LockError, OwnerBusy
from phone.quota import QuotaPause

pytestmark = pytest.mark.usefixtures("phone_env")


class FakeAdapter(Adapter):
    name = "fake"
    package = "com.example.app"
    cooldown_s = 5.0

    def __init__(self, status="sent", crash=False):
        self.quota = QuotaPause("fake")
        self.status, self.crash = status, crash
        self.launched = []

    def launch(self, ph, tag, text, **kw):
        self.launched.append((tag, kw))
        if self.crash:
            raise RuntimeError("transport lost after send")
        return {"tag": tag, "status": self.status, "t0": time.time(),
                "send_attempted": kw.get("preflight") is not True}


class FakePh:
    busy = None

    def __init__(self, *a, **kw):
        pass

    def connect(self):
        return self

    def owner_busy(self, extra_exempt=()):
        return FakePh.busy

    def device_id(self):
        return "abcd1234"


@pytest.fixture(autouse=True)
def fake_phone(monkeypatch):
    FakePh.busy = None
    monkeypatch.setattr(dispatch, "Phone", FakePh)


def run(adapter, tag="TAG-1", store=None, **kw):
    return dispatch.dispatch_one(adapter, "s22", tag, "hello", lock_wait=0.5,
                                 store=store or dispatch.claim_store(adapter), **kw)


def test_success_claims_reserves_cooldown_and_records(phone_env):
    a = FakeAdapter()
    row = run(a)
    assert row["status"] == "sent" and row["transport"] == "abcd1234" and row["adapter"] == "fake"
    store = dispatch.claim_store(a)
    assert store.launched() == {"TAG-1"}
    assert a.cooldown("s22").cooling()["cooling"] is True
    assert receipts.read()[-1]["action"] == "chat_send"
    assert "hello" not in config.receipts_path().read_text()
    assert not lockmod.lock_status("s22")["host"]["held"]      # lock released


def test_a_tag_is_never_sent_twice(phone_env):
    a = FakeAdapter()
    assert run(a)["status"] == "sent"
    a.cooldown("s22").path.write_text("0\n")                   # cooldown over
    again = run(a)
    assert again["status"] == "already_claimed" and len(a.launched) == 1


def test_cooldown_blocks_a_second_real_send(phone_env):
    a = FakeAdapter()
    run(a, "TAG-1")
    second = run(a, "TAG-2")
    assert second["status"] == "cooling_down" and len(a.launched) == 1
    assert dispatch.claim_store(a).claim_tag("TAG-2", "s22") is True   # nothing was claimed


def test_quota_pause_refuses_before_any_ui(phone_env):
    a = FakeAdapter()
    a.quota.extend(time.time() + 3600)
    row = run(a)
    assert row["status"] == "quota_paused" and a.launched == []


def test_owner_busy_refuses_and_leaves_the_tag_claimable(phone_env):
    a = FakeAdapter()
    FakePh.busy = "owner user activity within 60 seconds"
    row = run(a)
    assert row["status"] == "owner_busy" and a.launched == []
    assert dispatch.claim_store(a).claim_tag("TAG-1", "s22") is True
    assert a.cooldown("s22").cooling()["cooling"] is False


def test_lock_busy_is_a_refusal_not_a_hang(phone_env):
    import subprocess
    import sys
    holder = subprocess.Popen(
        [sys.executable, "-c",
         "import fcntl, sys, time\n"
         "f = open(sys.argv[1], 'a'); fcntl.flock(f, fcntl.LOCK_EX)\n"
         "print('held', flush=True); time.sleep(4)", str(config.lock_path("s22"))],
        stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "held"
        a = FakeAdapter()
        row = run(a)
    finally:
        holder.kill()
        holder.wait()
    assert row["status"] == "lock_busy" and a.launched == []


def test_rate_limit_extends_the_account_wide_pause_by_three_hours(phone_env):
    a = FakeAdapter(status="rate_limited")
    before = time.time()
    row = run(a)
    assert row["status"] == "rate_limited"
    st = a.quota.status()
    assert st["paused"] and 3 * 3600 - 5 <= st["resume_epoch"] - before <= 3 * 3600 + 30
    assert dispatch.claim_store(a).launched() == {"TAG-1"}      # recorded as launched


def test_a_crash_after_the_claim_is_unconfirmed_and_never_retried(phone_env):
    a = FakeAdapter(crash=True)
    row = run(a)
    assert row["status"] == "unconfirmed" and "no receipt" in row["error"]
    store = dispatch.claim_store(a)
    assert store.launched() == {"TAG-1"} and store.unconfirmed_file.read_text().split() == ["TAG-1"]
    a.cooldown("s22").path.write_text("0\n")
    assert run(FakeAdapter())["status"] == "already_claimed"


def test_preflight_claims_nothing_and_reserves_no_cooldown(phone_env):
    a = FakeAdapter()
    row = run(a, preflight=True)
    assert a.launched[0][1]["preflight"] is True
    assert dispatch.claim_store(a).launched() == set() and dispatch.claim_store(a).claim_tag("TAG-1", "s22")
    assert a.cooldown("s22").cooling()["cooling"] is False
    assert receipts.read()[-1]["action"] == "chat_preflight" and row["tag"] == "TAG-1"


def test_s25_is_refused_unless_the_owner_enables_it(phone_env):
    from phone.errors import RoleNotAllowed
    with pytest.raises(RoleNotAllowed):
        dispatch.dispatch_one(FakeAdapter(), "s25", "TAG-1", "x")


# cli ------------------------------------------------------------------------------------------

def call(argv, monkeypatch=None):
    out, err = io.StringIO(), io.StringIO()
    import sys
    old = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    try:
        code = cli.main(argv)
    finally:
        sys.stdout, sys.stderr = old
    return code, out.getvalue(), err.getvalue()


def test_real_send_requires_i_mean_it(monkeypatch):
    called = []
    monkeypatch.setattr("phone.dispatch.dispatch_one", lambda *a, **k: called.append(1) or {})
    code, out, _ = call(["chat", "chatgpt", "send", "--role", "s22", "--tag", "ABC-1", "--value", "x"])
    assert code == cli.EXIT_USAGE and "--i-mean-it" in out and not called


def test_preflight_only_does_not_need_the_flag(monkeypatch):
    seen = {}

    def fake(adapter, role, tag, text, **kw):
        seen.update(kw, role=role)
        return {"status": "preflight_ready", "tag": tag}
    monkeypatch.setattr("phone.dispatch.dispatch_one", fake)
    code, out, _ = call(["chat", "chatgpt", "send", "--role", "s22", "--tag", "ABC-1",
                         "--value", "x", "--preflight-only"])
    assert code == 0 and seen["preflight"] is True and json.loads(out)["ok"] is True


@pytest.mark.parametrize("status,code", [
    ("sent", 0), ("preflight_ready", 0), ("owner_busy", 3), ("quota_paused", 3),
    ("cooling_down", 3), ("already_claimed", 3), ("lock_busy", 3),
    ("failed", 1), ("unconfirmed", 1), ("rate_limited", 1)])
def test_send_exit_codes(monkeypatch, status, code):
    monkeypatch.setattr("phone.dispatch.dispatch_one",
                        lambda *a, **k: {"status": status, "tag": "ABC-1"})
    got, out, _ = call(["chat", "chatgpt", "send", "--role", "s22", "--tag", "ABC-1",
                        "--value", "x", "--i-mean-it"])
    assert got == code, (status, out)


def test_refusals_and_failures_map_to_exit_codes(monkeypatch):
    def raiser(exc):
        def f(_args):
            raise exc
        return f
    monkeypatch.setitem(cli.HANDLERS, "home", raiser(OwnerBusy("owner active")))
    code, out, _ = call(["home", "--role", "s22"])
    assert code == cli.EXIT_REFUSED and json.loads(out)["error_class"] == "OwnerBusy"
    monkeypatch.setitem(cli.HANDLERS, "home", raiser(LockError("busy")))
    assert call(["home", "--role", "s22"])[0] == cli.EXIT_REFUSED
    monkeypatch.setitem(cli.HANDLERS, "home", raiser(RuntimeError("rpc died")))
    code, out, _ = call(["home", "--role", "s22"])
    assert code == cli.EXIT_FAILED and json.loads(out)["ok"] is False


def test_tap_needs_a_label_or_selector():
    code, out, _ = call(["tap", "--role", "s22"])
    assert code == cli.EXIT_USAGE and "label or a selector" in out


def test_selftest_command_reports_the_guard():
    code, out, _ = call(["selftest"])
    body = json.loads(out)
    assert code == 0 and body["ok"] and body["passed"] == body["total"] and body["total"] >= 30


def test_devices_never_prints_serials_by_default(monkeypatch):
    monkeypatch.setattr("phone.adb.visible_roles", lambda: [
        {"role": "s22", "allowed": True, "configured": True, "model": "SM-X",
         "transports": [{"kind": "usb", "state": "device"}]}])
    code, out, _ = call(["devices"])
    assert code == 0 and "serial" not in out and json.loads(out)["roles"][0]["role"] == "s22"


def test_lock_status_does_not_require_a_phone():
    code, out, _ = call(["lock-status", "--role", "s22"])
    body = json.loads(out)
    assert code == 0 and body["roles"]["s22"]["host"]["held"] is False
    assert set(body["quota"]) == {"chatgpt", "deepseek"}


def test_receipts_command_returns_recent_rows():
    receipts.write({"action": "x", "status": "ok"})
    receipts.write({"action": "y", "status": "ok"})
    code, out, _ = call(["receipts", "--limit", "1"])
    assert code == 0 and [r["action"] for r in json.loads(out)["receipts"]] == ["y"]


def test_roles_are_validated_by_argparse():
    with pytest.raises(SystemExit) as e:
        call(["home", "--role", "pixel"])
    assert e.value.code == 2


def test_receipts_hold_digests_not_text(phone_env):
    rec = receipts.write({"action": "type_text", **receipts.text_digest("super secret"),
                          "device": receipts.device_digest("SERIAL123")})
    body = config.receipts_path().read_text()
    assert "super secret" not in body and "SERIAL123" not in body
    assert rec["chars"] == 12 and len(rec["sha256_8"]) == 8 and len(rec["device"]) == 8
