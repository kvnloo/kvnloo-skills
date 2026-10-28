"""Owner-activity check and the agent-open ledger.

Before claiming work and again before UI input, the driver proves the owner is not using the phone:
`dumpsys power`'s mLastUserActivityTime is compared with device uptime. Unreadable evidence is
"busy", never "free". The ledger maps packages an agent launched to the device boot id and uptime, so
a foreground app is exempt only when an agent launched it since the owner's last activity.

Rules by phone kind (ported from the production launcher):

  worker phone (default: s22)   pause when the owner touched the phone within 60 s while an app other
                                than a home launcher or the app being driven is in front, or during a
                                call. An idle home screen is not owner use.
  daily phone (default: s25)    busy when owner activity is within 60 s (or the clock is invalid), and
                                a foreground app needs an agent launch since the last owner activity.
                                An optional idle window (PHONE_IDLE_WORKER_UNTIL_<ROLE>) makes it
                                behave as a worker phone; with the `<state>/<role>-worker-off` kill
                                switch present it may still work after 120 s idle while a launcher or
                                a driven app is in front.

Everything returns a reason string when busy and None when free.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Callable

from . import adb as adbmod
from . import config

STATIC_LAUNCHERS = frozenset({
    "com.sec.android.app.launcher", "com.teslacoilsw.launcher",
    "com.google.android.apps.nexuslauncher", "com.android.launcher3",
})
WORKER_ACTIVITY_WINDOW_MS = 60_000
IDLE_WORKER_MIN_AGE_MS = 120_000

SNAPSHOT_CMD = ("cat /proc/uptime; cat /proc/sys/kernel/random/boot_id; "
                "dumpsys power | grep mLastUserActivityTime; "
                "dumpsys activity activities | grep -E 'topResumedActivity=|mResumedActivity:'")


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def parse_snapshot(stdout: str) -> dict:
    lines = stdout.splitlines()
    activity = re.search(r"mLastUserActivityTime(?:\(excludingAttention\))?=(\d+)", stdout)
    foreground = re.search(r"(?:topResumedActivity=|mResumedActivity:).*?\bu\d+\s+([^/\s]+)/", stdout)
    if not lines or not activity or not foreground or len(lines) < 2 or not lines[1].strip():
        raise RuntimeError("cannot establish owner activity and foreground; refusing UI")
    return {"uptime_ms": int(float(lines[0].split()[0]) * 1000),
            "last_user_activity_ms": int(activity[1]),
            "boot_id": lines[1].strip(), "package": foreground[1]}


def activity_snapshot(serial: str) -> dict:
    result = adbmod.run(["shell", SNAPSHOT_CMD], serial=serial, timeout=20)
    return parse_snapshot(result.stdout)


def in_call(serial: str) -> bool:
    out = adbmod.run(["shell", "dumpsys telephony.registry"], serial=serial, timeout=20).stdout
    return any(m != "0" for m in re.findall(r"mCallState=(\d)", out))


_HOME_CACHE: dict[str, frozenset] = {}


def home_packages(serial: str | None = None) -> frozenset:
    """Home launcher packages: a static list, PHONE_HOME_LAUNCHERS, and the phone's default HOME
    activity discovered at runtime (read-only)."""
    extra = {p.strip() for p in os.environ.get("PHONE_HOME_LAUNCHERS", "").split(",") if p.strip()}
    found: set[str] = set()
    if serial:
        if serial not in _HOME_CACHE:
            try:
                out = adbmod.run(["shell", "cmd package resolve-activity --brief "
                                  "-a android.intent.action.MAIN -c android.intent.category.HOME"],
                                 serial=serial, timeout=15).stdout
                m = re.findall(r"^([A-Za-z0-9_.]+)/", out, re.M)
                _HOME_CACHE[serial] = frozenset(m[-1:])
            except (OSError, subprocess.SubprocessError):
                _HOME_CACHE[serial] = frozenset()
        found = set(_HOME_CACHE[serial])
    return frozenset(STATIC_LAUNCHERS | extra | found)


# ledger -------------------------------------------------------------------------------------

def read_ledger(role: str) -> dict:
    path = config.ledger_path(role)
    if not path.exists():
        return {}
    ledger = json.loads(path.read_text())
    if not isinstance(ledger, dict):
        raise ValueError("agent launch ledger is not an object")
    return ledger


def record_agent_open(role: str, package: str, snapshot: dict) -> None:
    """Call under the host UI lock whenever an agent launches a package, with a snapshot taken
    immediately before the launch."""
    path = config.ledger_path(role)
    try:
        ledger = read_ledger(role)
    except (OSError, ValueError):
        ledger = {}
    ledger[package] = {"boot_id": snapshot["boot_id"],
                       "opened_uptime_ms": snapshot["uptime_ms"], "opened_at": now()}
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(ledger) + "\n")
    os.replace(tmp, path)


def agent_opened_packages(role: str, boot_id: str) -> set[str]:
    try:
        ledger = read_ledger(role)
    except (OSError, ValueError):
        return set()
    return {p for p, v in ledger.items()
            if isinstance(v, dict) and v.get("boot_id") == boot_id}


# policy -------------------------------------------------------------------------------------

def idle_worker_until(role: str) -> float:
    raw = os.environ.get(f"PHONE_IDLE_WORKER_UNTIL_{role.upper()}", "").strip()
    try:
        return float(raw) if raw else 0.0
    except ValueError:
        return 0.0


def worker_off_marker(role: str) -> Path:
    return config.state_dir() / f"{role}-worker-off"


def owner_busy(
    serial: str,
    role: str,
    exempt_pkgs: frozenset | set = frozenset(),
    *,
    snapshot_fn: Callable[[str], dict] = activity_snapshot,
    call_fn: Callable[[str], bool] = in_call,
    home_fn: Callable[[str | None], frozenset] = home_packages,
    clock: Callable[[], float] = time.time,
    ledger_fn: Callable[[str], dict] = read_ledger,
) -> str | None:
    """Reason the owner (or missing evidence) forbids UI use right now, else None."""
    exempt = set(exempt_pkgs)

    def call_state():
        try:
            return "phone is in a call" if call_fn(serial) else None
        except (OSError, ValueError, subprocess.SubprocessError) as e:
            return f"call state unavailable: {type(e).__name__}: {e}"

    launchers = set(home_fn(serial))
    idle_window = role not in config.worker_roles() and clock() < idle_worker_until(role)
    full_worker = role in config.worker_roles() or (
        idle_window and not worker_off_marker(role).exists())

    if full_worker:
        # Worker canon: use the phone maximally, but pause when the owner is actively using it:
        # recent user activity while an app other than a launcher or the driven app is in front.
        try:
            snap = snapshot_fn(serial)
            age = snap["uptime_ms"] - snap["last_user_activity_ms"]
            if 0 <= age < WORKER_ACTIVITY_WINDOW_MS and snap["package"] not in (launchers | exempt):
                return f"owner active in {snap['package']} within 60 s (worker phone)"
        except (OSError, ValueError, IndexError, subprocess.SubprocessError, RuntimeError) as e:
            return f"owner evidence unavailable: {type(e).__name__}: {e}"
        return call_state()

    try:
        snapshot = snapshot_fn(serial)
        ledger = ledger_fn(role)
        if not isinstance(ledger, dict):
            raise ValueError("agent launch ledger is not an object")
    except (OSError, ValueError, IndexError, subprocess.SubprocessError, RuntimeError) as e:
        return f"owner evidence unavailable: {type(e).__name__}: {e}"
    age = snapshot["uptime_ms"] - snapshot["last_user_activity_ms"]
    # Idle window with the worker kill switch set: still allowed after 120 s of quiet, but never over
    # an app in use (only a launcher or a driven app may be in front).
    if (idle_window and 0 <= age and age >= IDLE_WORKER_MIN_AGE_MS
            and snapshot["package"] in (launchers | exempt)):
        return call_state()
    if not 0 <= age or age < WORKER_ACTIVITY_WINDOW_MS:
        return "owner user activity within 60 seconds (or invalid activity clock)"
    opened = ledger.get(snapshot["package"], {})
    if not isinstance(opened, dict) or not isinstance(opened.get("opened_uptime_ms"), int):
        return "foreground agent launch evidence unavailable"
    if (opened.get("boot_id") != snapshot["boot_id"]
            or not snapshot["last_user_activity_ms"] <= opened.get("opened_uptime_ms", -1)
            <= snapshot["uptime_ms"]):
        return f"foreground {snapshot['package']} has no agent launch since owner activity"
    return None
