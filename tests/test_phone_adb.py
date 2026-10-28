"""Runtime discovery: candidates, identity proof, and never probing another role's phone."""
from __future__ import annotations

import subprocess

import pytest

from phone import adb, config
from phone.errors import DeviceNotConfigured, DeviceNotFound

pytestmark = pytest.mark.usefixtures("phone_env")

WORKER = "TESTHW00001"      # the worker phone's hardware serial in these tests
DAILY = "OTHERHW0002"       # the owner's daily phone

DEVICES_L = (
    "List of devices attached\n"
    f"{WORKER}              device usb:1-1 product:p model:SM_W123 device:d transport_id:1\n"
    f"{DAILY}              device usb:1-2 product:q model:SM_D456 device:e transport_id:2\n"
    "host.example:5555       device product:p model:SM_W123 device:d transport_id:3\n"
    "other.example:5556      device product:q model:SM_D456 device:e transport_id:4\n"
    "offline.example:5557    offline\n"
)
MDNS = (
    "List of discovered mdns services\n"
    f"adb-{WORKER}-AbCdEf\t_adb-tls-connect._tcp\twifi.example:41000\n"
    f"adb-{DAILY}-GhIjKl\t_adb-tls-connect._tcp\tdaily.example:41001\n"
    f"adb-{WORKER}-pairing\t_adb-tls-pairing._tcp\twifi.example:41002\n"
)


@pytest.fixture
def roles(monkeypatch):
    table = {"s22": {"serial": WORKER, "model": "SM-W123"},
             "s25": {"serial": DAILY, "model": "SM-D456"}}

    def role_hardware(role):
        if role not in table:
            raise DeviceNotConfigured(role)
        return table[role]
    monkeypatch.setattr(config, "role_hardware", role_hardware)
    return table


def test_parse_devices_and_mdns():
    rows = adb.parse_devices(DEVICES_L)
    assert [r["state"] for r in rows] == ["device", "device", "device", "device", "offline"]
    assert rows[0]["model"] == "SM_W123" and rows[4]["model"] == ""
    ad = adb.parse_mdns(MDNS)
    assert [a["type"] for a in ad] == ["_adb-tls-connect._tcp", "_adb-tls-connect._tcp",
                                       "_adb-tls-pairing._tcp"]
    assert ad[0]["endpoint"] == "wifi.example:41000"


def test_candidates_prefer_usb_then_adverts_then_model_matches(roles):
    got = adb.candidates("s22", adb.parse_devices(DEVICES_L), adb.parse_mdns(MDNS))
    assert got == [WORKER, "wifi.example:41000", "host.example:5555"]


def test_other_roles_transports_are_never_candidates(roles):
    got = adb.candidates("s22", adb.parse_devices(DEVICES_L), adb.parse_mdns(MDNS))
    assert DAILY not in got and "other.example:5556" not in got and "daily.example:41001" not in got
    other = adb.candidates("s25", adb.parse_devices(DEVICES_L), adb.parse_mdns(MDNS))
    assert WORKER not in other and "host.example:5555" not in other


def test_pairing_adverts_and_offline_transports_are_ignored(roles):
    got = adb.candidates("s22", adb.parse_devices(DEVICES_L), adb.parse_mdns(MDNS))
    assert "wifi.example:41002" not in got and "offline.example:5557" not in got


def test_without_a_model_hint_only_unknown_ip_style_transports_are_probed(roles):
    roles["s22"]["model"] = ""
    rows = adb.parse_devices(
        f"{WORKER} device model:X\nunknown.example:1 device model:Y\n{DAILY} device model:Z\n")
    assert adb.candidates("s22", rows, []) == [WORKER, "unknown.example:1"]


class FakeAdb:
    """Records every adb call and answers like a phone would."""

    def __init__(self, answers, connected_after_connect=()):
        self.calls, self.answers, self.connected_after = [], answers, set(connected_after_connect)

    def __call__(self, args, serial=None, timeout=20.0, check=True):
        self.calls.append((tuple(args), serial))
        if args[:2] == ["devices", "-l"]:
            return subprocess.CompletedProcess(args, 0, DEVICES_L, "")
        if args[0] == "mdns":
            return subprocess.CompletedProcess(args, 0, MDNS, "")
        if args[0] == "connect":
            return subprocess.CompletedProcess(args, 0, "connected", "")
        if args[:3] == ["shell", "getprop", "ro.serialno"]:
            out = self.answers.get(serial)
            return subprocess.CompletedProcess(args, 0 if out else 1, (out or "") + "\n", "")
        raise AssertionError(f"unexpected adb call {args}")


def test_discover_proves_identity_and_never_touches_the_other_phone(roles, monkeypatch):
    fake = FakeAdb({WORKER: WORKER})
    monkeypatch.setattr(adb, "run", fake)
    t = adb.discover("s22")
    assert t.serial == WORKER and t.kind == "usb" and t.hardware == WORKER
    touched = {serial for _args, serial in fake.calls if serial}
    assert touched == {WORKER}


def test_discover_falls_back_to_wireless_and_connects_with_existing_pairing(roles, monkeypatch):
    fake = FakeAdb({"wifi.example:41000": WORKER})
    monkeypatch.setattr(adb, "run", fake)
    t = adb.discover("s22")
    assert t.serial == "wifi.example:41000" and t.kind == "wireless"
    assert (("connect", "wifi.example:41000"), None) in fake.calls
    assert not any(a[0] in ("pair",) for a, _ in fake.calls)
    assert DAILY not in {s for _a, s in fake.calls if s}


def test_a_transport_with_the_wrong_identity_is_rejected(roles, monkeypatch):
    fake = FakeAdb({WORKER: "SOMETHINGELSE", "wifi.example:41000": "NOPE", "host.example:5555": "NOPE"})
    monkeypatch.setattr(adb, "run", fake)
    with pytest.raises(DeviceNotFound):
        adb.discover("s22")


def test_unconfigured_role_fails_loudly_without_touching_adb(monkeypatch):
    monkeypatch.delenv("PHONE_SERIAL_S22", raising=False)
    monkeypatch.setenv("Z0_HOSTS_DIR", "/nonexistent-overlay")
    calls = []
    monkeypatch.setattr(adb, "run", lambda *a, **k: calls.append(a))
    with pytest.raises(DeviceNotConfigured, match="PHONE_SERIAL_S22"):
        adb.discover("s22")
    assert calls == []


def test_serial_from_environment_wins(monkeypatch):
    monkeypatch.setenv("PHONE_SERIAL_S22", "FROMENV0001")
    assert config.role_hardware("s22")["serial"] == "FROMENV0001"


def test_overlay_serial_is_read_by_alias(tmp_path, monkeypatch):
    monkeypatch.delenv("PHONE_SERIAL_S22", raising=False)
    hosts = tmp_path / "hosts" / "box"
    hosts.mkdir(parents=True)
    (hosts / "host.toml").write_text('match_hostnames = ["box"]\n')
    (hosts / "devices.toml").write_text(
        '[worker-phone]\nkind = "phone"\naliases = ["s22"]\nserial = "OVERLAY0001"\n'
        'model = "SM-W123"\n[other]\nkind = "node"\naliases = ["s22"]\n')
    monkeypatch.setenv("Z0_HOSTS_DIR", str(tmp_path))
    monkeypatch.setenv("Z0_HOST_ID", "box")
    assert config.role_hardware("s22") == {"serial": "OVERLAY0001", "model": "SM-W123"}


def test_adb_is_pinned_to_the_local_server(monkeypatch):
    monkeypatch.setenv("ADB_SERVER_SOCKET", "tcp:elsewhere.example:1")
    monkeypatch.setenv("ANDROID_ADB_SERVER_HOST", "elsewhere.example")
    env = config.adb_env()
    assert "ADB_SERVER_SOCKET" not in env and "ANDROID_ADB_SERVER_HOST" not in env
    assert env["ANDROID_ADB_SERVER_PORT"] == config.adb_port()


def test_s25_is_not_enabled_by_default(monkeypatch):
    from phone.errors import RoleNotAllowed
    config.require_role_allowed("s22")
    with pytest.raises(RoleNotAllowed):
        config.require_role_allowed("s25")
    monkeypatch.setenv("PHONE_ALLOW_ROLES", "s22,s25")
    config.require_role_allowed("s25")
