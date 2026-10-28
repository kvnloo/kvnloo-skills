"""Owner-activity check, agent-open ledger and snapshot parsing."""
from __future__ import annotations

import time

import pytest

from phone import activity, config

pytestmark = pytest.mark.usefixtures("phone_env")

LAUNCHER = "com.example.launcher"
APP = "com.example.chat"
OTHER = "com.example.private"
BOOT = "boot-1"


def snap(age_ms, pkg=APP, uptime=1_000_000):
    return {"uptime_ms": uptime, "last_user_activity_ms": uptime - age_ms, "boot_id": BOOT,
            "package": pkg}


def busy(role, snapshot, exempt=(), ledger=None, in_call=False, clock=time.time):
    def snapshot_fn(_s):
        if isinstance(snapshot, Exception):
            raise snapshot
        return snapshot

    return activity.owner_busy(
        "SER", role, set(exempt), snapshot_fn=snapshot_fn, call_fn=lambda _s: in_call,
        home_fn=lambda _s: frozenset({LAUNCHER}), clock=clock,
        ledger_fn=lambda _r: {} if ledger is None else ledger)


# worker phone ---------------------------------------------------------------------------------

def test_worker_free_when_owner_quiet():
    assert busy("s22", snap(5 * 60_000, OTHER)) is None


def test_worker_busy_when_owner_active_in_another_app():
    assert "owner active in" in busy("s22", snap(10_000, OTHER), exempt={APP})


def test_worker_ignores_activity_in_driven_app_and_on_home():
    assert busy("s22", snap(10_000, APP), exempt={APP}) is None
    assert busy("s22", snap(10_000, LAUNCHER), exempt={APP}) is None


def test_worker_boundary_is_60_seconds():
    assert busy("s22", snap(59_999, OTHER))
    assert busy("s22", snap(60_000, OTHER)) is None


def test_worker_pauses_during_a_call():
    assert busy("s22", snap(5 * 60_000, OTHER), in_call=True) == "phone is in a call"


def test_missing_evidence_means_busy_never_free():
    assert "owner evidence unavailable" in busy("s22", RuntimeError("no dumpsys"))
    assert "owner evidence unavailable" in busy("s25", RuntimeError("no dumpsys"))


def test_future_activity_clock_is_not_trusted_on_daily_phone():
    s = snap(-5000)
    assert "invalid activity clock" in busy("s25", s, ledger={})


# daily phone ----------------------------------------------------------------------------------

def test_daily_phone_busy_when_owner_active():
    assert "within 60 seconds" in busy("s25", snap(10_000))


def test_daily_phone_needs_an_agent_launch_since_owner_activity():
    s = snap(5 * 60_000)
    assert busy("s25", s, ledger={}) == "foreground agent launch evidence unavailable"
    opened_after = {APP: {"boot_id": BOOT, "opened_uptime_ms": s["uptime_ms"] - 1000}}
    assert busy("s25", s, ledger=opened_after) is None
    opened_before = {APP: {"boot_id": BOOT, "opened_uptime_ms": s["last_user_activity_ms"] - 1}}
    assert "no agent launch since owner activity" in busy("s25", s, ledger=opened_before)
    wrong_boot = {APP: {"boot_id": "boot-0", "opened_uptime_ms": s["uptime_ms"] - 1000}}
    assert "no agent launch since owner activity" in busy("s25", s, ledger=wrong_boot)


def test_daily_phone_idle_window_behaves_like_a_worker(monkeypatch):
    monkeypatch.setenv("PHONE_IDLE_WORKER_UNTIL_S25", str(time.time() + 3600))
    assert busy("s25", snap(5 * 60_000, OTHER)) is None
    assert "owner active in" in busy("s25", snap(10_000, OTHER))


def test_idle_window_expired_goes_back_to_strict(monkeypatch):
    monkeypatch.setenv("PHONE_IDLE_WORKER_UNTIL_S25", str(time.time() - 10))
    assert busy("s25", snap(5 * 60_000, OTHER)) == "foreground agent launch evidence unavailable"


def test_kill_switch_keeps_only_the_quiet_launcher_exception(monkeypatch, phone_env):
    monkeypatch.setenv("PHONE_IDLE_WORKER_UNTIL_S25", str(time.time() + 3600))
    marker = activity.worker_off_marker("s25")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("")
    # quiet 3 minutes with a launcher in front: still allowed
    assert busy("s25", snap(3 * 60_000, LAUNCHER)) is None
    # quiet 3 minutes with some other app in front: strict rules apply
    assert busy("s25", snap(3 * 60_000, OTHER), ledger={}) == \
        "foreground agent launch evidence unavailable"
    # only 90 s quiet: not enough for the exception
    assert "foreground agent launch evidence" in busy("s25", snap(90_000, LAUNCHER), ledger={})


# plumbing -------------------------------------------------------------------------------------

SAMPLE = ("12345.67 8901.23\n"
          "0f0e0d0c-0b0a-0908-0706-050403020100\n"
          "  mLastUserActivityTime=12000\n"
          "  topResumedActivity=ActivityRecord{abc u0 com.example.chat/.Main t5}\n")


def test_parse_snapshot():
    s = activity.parse_snapshot(SAMPLE)
    assert s["uptime_ms"] == 12_345_670
    assert s["last_user_activity_ms"] == 12000
    assert s["boot_id"].startswith("0f0e0d0c")
    assert s["package"] == "com.example.chat"


def test_parse_snapshot_accepts_the_excluding_attention_form():
    s = activity.parse_snapshot(SAMPLE.replace("mLastUserActivityTime=",
                                               "mLastUserActivityTime(excludingAttention)="))
    assert s["last_user_activity_ms"] == 12000


@pytest.mark.parametrize("text", ["", "1 2\nboot\n", SAMPLE.replace("topResumedActivity", "nothing"),
                                  SAMPLE.replace("mLastUserActivityTime", "nothing")])
def test_parse_snapshot_refuses_incomplete_evidence(text):
    with pytest.raises(RuntimeError):
        activity.parse_snapshot(text)


def test_ledger_roundtrip_and_boot_scoping(phone_env):
    s = snap(1000)
    activity.record_agent_open("s22", APP, s)
    ledger = activity.read_ledger("s22")
    assert ledger[APP]["boot_id"] == BOOT and ledger[APP]["opened_uptime_ms"] == s["uptime_ms"]
    assert activity.agent_opened_packages("s22", BOOT) == {APP}
    assert activity.agent_opened_packages("s22", "other-boot") == set()
    assert config.ledger_path("s22").name == "s22-agent-opened.json"
    assert not list(config.lock_dir().glob("*.tmp*"))


def test_ledger_corruption_is_not_trusted(phone_env):
    config.ledger_path("s25").write_text("[1, 2]")
    assert activity.agent_opened_packages("s25", BOOT) == set()
    reason = activity.owner_busy(
        "SER", "s25", set(), snapshot_fn=lambda _s: snap(5 * 60_000),
        call_fn=lambda _s: False, home_fn=lambda _s: frozenset(),
        ledger_fn=activity.read_ledger)
    assert reason and "owner evidence unavailable" in reason


def test_static_launchers_and_env_extension(monkeypatch):
    monkeypatch.setenv("PHONE_HOME_LAUNCHERS", "org.example.home, org.example.home2")
    got = activity.home_packages(None)
    assert {"org.example.home", "org.example.home2"} <= got
    assert activity.STATIC_LAUNCHERS <= got


# the app being driven -------------------------------------------------------------------------

def test_an_app_opened_long_ago_is_no_longer_the_driven_app(phone_env):
    t0 = 1_000_000
    activity.record_agent_open("s22", APP, {"boot_id": BOOT, "uptime_ms": t0})
    assert activity.agent_opened_packages("s22", BOOT, t0 + 60_000) == {APP}
    late = t0 + activity.AGENT_SESSION_IDLE_MS + 1
    assert activity.agent_opened_packages("s22", BOOT, late) == set()
    assert activity.agent_opened_packages("s22", BOOT) == {APP}        # boot scoping alone


def test_driving_an_app_keeps_its_session_but_not_its_open_time(phone_env):
    t0 = 1_000_000
    activity.record_agent_open("s22", APP, {"boot_id": BOOT, "uptime_ms": t0})
    later = t0 + 2 * activity.AGENT_SESSION_IDLE_MS
    activity.touch_agent_session("s22", APP, {"boot_id": BOOT, "uptime_ms": later})
    assert activity.agent_opened_packages("s22", BOOT, later + 60_000) == {APP}
    assert activity.read_ledger("s22")[APP]["opened_uptime_ms"] == t0   # daily rule unchanged
    activity.touch_agent_session("s22", OTHER, {"boot_id": BOOT, "uptime_ms": later})
    activity.touch_agent_session("s22", APP, {"boot_id": "other-boot", "uptime_ms": 5})
    assert set(activity.read_ledger("s22")) == {APP}                      # nothing invented
    assert activity.read_ledger("s22")[APP]["last_agent_uptime_ms"] == later


def test_owner_in_an_app_an_agent_left_alone_is_busy_on_the_worker(phone_env, monkeypatch):
    """burst.py exempted only the app it drove. An app an agent opened earlier in the boot and then
    left must not hide the owner using it now."""
    import subprocess

    from phone import adb as adbmod
    from phone_testlib import make_phone
    monkeypatch.setattr(adbmod, "run", lambda *a, **k: subprocess.CompletedProcess(
        a, 0, "mCallState=0\n", ""))
    t0 = 1_000_000
    activity.record_agent_open("s22", OTHER, {"boot_id": BOOT, "uptime_ms": t0})
    ph = make_phone()
    del ph.owner_busy                                   # the real Phone.owner_busy
    ph.driving = set()
    stale = t0 + activity.AGENT_SESSION_IDLE_MS + 30_000
    ph.snapshot = lambda: snap(10_000, OTHER, uptime=stale)
    assert "owner active in" in ph.owner_busy()
    fresh = t0 + 60_000
    ph.snapshot = lambda: snap(10_000, OTHER, uptime=fresh)
    assert ph.owner_busy() is None                      # still being driven by the agent
