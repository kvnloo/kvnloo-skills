"""Runtime configuration. Every host-specific value comes from the environment, the private
z0-hosts overlay, or discovery. Defaults are neutral.

Environment (all optional):
  PHONE_SERIAL_S22 / PHONE_SERIAL_S25   hardware serial for a role (else the z0-hosts overlay)
  PHONE_ADB                             adb binary (else ~/android/sdk, ~/Android/Sdk, ANDROID_HOME,
                                        then PATH; see adb_path). Use the same build as the running
                                        server: two builds restart each other's server
  PHONE_ADB_PORT                        local adb server port (default: the adb default)
  PHONE_LOCK_DIR                        directory of the host UI locks (default /tmp, so every
                                        tool on the host agrees on one lock path per phone)
  PHONE_SHARED_LOCK_DIR                 optional second lock taken first (default ~/tmp); "off"
                                        disables it
  PHONE_STATE_DIR                       receipts, claims, diagnostics (default XDG state dir)
  PHONE_RECEIPTS                        receipts JSONL path
  PHONE_ALLOW_ROLES                     comma list of roles that may be driven (default s22)
  PHONE_WORKER_ROLES                    roles that are dedicated worker phones (default s22)
  PHONE_IDLE_WORKER_UNTIL_<ROLE>        epoch until which a non-worker role may work while idle
  PHONE_HOME_LAUNCHERS                  extra home launcher packages, comma separated
  PHONE_PROTECTED_PKGS                  extra packages the guard protects from stop or clear
  PHONE_SCREEN_SAFE                     path to the phone-screen-safe redactor
  PHONE_REDACTION                       required (default) or off
  PHONE_CALIBRATION_DIR                 adapter calibration JSON files
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from .errors import DeviceNotConfigured, RoleNotAllowed
from . import zhosts

ROLES = ("s22", "s25")
ADB_DEFAULT_PORT = "5037"  # the standard adb server port, not a host assignment


def check_role(role: str) -> str:
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}, got {role!r}")
    return role


def allowed_roles() -> set[str]:
    raw = os.environ.get("PHONE_ALLOW_ROLES", "s22")
    return {r.strip() for r in raw.split(",") if r.strip()}


def require_role_allowed(role: str) -> None:
    check_role(role)
    if role not in allowed_roles():
        raise RoleNotAllowed(
            f"role {role} is not enabled for driving here. The s25 is the owner's daily phone; "
            "only the owner enables it (PHONE_ALLOW_ROLES).")


def worker_roles() -> set[str]:
    raw = os.environ.get("PHONE_WORKER_ROLES", "s22")
    return {r.strip() for r in raw.split(",") if r.strip()}


def lock_dir() -> Path:
    return Path(os.environ.get("PHONE_LOCK_DIR") or "/tmp")


def shared_lock_dir() -> Path | None:
    raw = os.environ.get("PHONE_SHARED_LOCK_DIR")
    if raw is not None and raw.strip().lower() in ("", "off", "none"):
        return None
    return Path(raw) if raw else Path.home() / "tmp"


def lock_path(role: str) -> Path:
    return lock_dir() / f"{check_role(role)}-ui.lock"


def shared_lock_path(role: str) -> Path | None:
    base = shared_lock_dir()
    return base / f"{check_role(role)}-ui.lock" if base else None


def ledger_path(role: str) -> Path:
    return lock_dir() / f"{check_role(role)}-agent-opened.json"


def state_dir() -> Path:
    raw = os.environ.get("PHONE_STATE_DIR")
    if raw:
        return Path(raw)
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "phone"


def receipts_path() -> Path:
    return Path(os.environ.get("PHONE_RECEIPTS") or state_dir() / "receipts.jsonl")


def calibration_dir() -> Path:
    return Path(os.environ.get("PHONE_CALIBRATION_DIR") or state_dir() / "calibration")


def adb_path() -> str:
    """The adb binary. Two adb builds sharing one server port restart each other's server and drop
    every wireless transport, so the choice is stable and does NOT follow ANDROID_HOME first (build
    shells often point it at another SDK): PHONE_ADB, then the host's driver SDK `~/android/sdk`,
    then `~/Android/Sdk`, then ANDROID_HOME / ANDROID_SDK_ROOT, then PATH."""
    explicit = os.environ.get("PHONE_ADB")
    if explicit:
        return explicit
    candidates = [Path.home() / rel / "platform-tools" / "adb" for rel in ("android/sdk", "Android/Sdk")]
    candidates += [Path(os.environ[var]) / "platform-tools" / "adb"
                   for var in ("ANDROID_HOME", "ANDROID_SDK_ROOT") if os.environ.get(var)]
    for cand in candidates:
        if cand.is_file():
            return str(cand)
    found = shutil.which("adb")
    if found:
        return found
    raise FileNotFoundError("adb not found: set PHONE_ADB or ANDROID_HOME")


def adb_port() -> str:
    return os.environ.get("PHONE_ADB_PORT") or ADB_DEFAULT_PORT


def adb_env(base: dict | None = None) -> dict:
    """Environment that pins every adb call to THIS host's local adb server."""
    env = dict(os.environ if base is None else base)
    env["ANDROID_ADB_SERVER_PORT"] = adb_port()
    env.pop("ADB_SERVER_SOCKET", None)
    env.pop("ANDROID_ADB_SERVER_HOST", None)
    try:
        exe = adb_path()
        env["ADBUTILS_ADB_PATH"] = exe
        env["PATH"] = str(Path(exe).parent) + os.pathsep + env.get("PATH", "")
    except FileNotFoundError:
        pass
    return env


def prepare_environment() -> None:
    """Call before adbutils is imported: pin it to the local adb server."""
    os.environ.update({k: v for k, v in adb_env().items()
                       if k in ("ANDROID_ADB_SERVER_PORT", "ADBUTILS_ADB_PATH")})
    os.environ.pop("ADB_SERVER_SOCKET", None)
    os.environ.pop("ANDROID_ADB_SERVER_HOST", None)


def role_hardware(role: str) -> dict:
    """{"serial": ..., "model": ...} for a role from env, else the private overlay."""
    check_role(role)
    serial = os.environ.get(f"PHONE_SERIAL_{role.upper()}", "").strip()
    entry = zhosts.phone_entry(role)
    serial = serial or str(entry.get("serial") or "").strip()
    if not serial:
        raise DeviceNotConfigured(
            f"no serial known for role {role}: set PHONE_SERIAL_{role.upper()} or add a phone "
            f"entry with alias {role!r} and a serial to the private z0-hosts devices.toml")
    return {"serial": serial, "model": str(entry.get("model") or "")}


def other_role_serials(role: str) -> set[str]:
    """Hardware serials of the other roles, when known. Used to never probe another phone."""
    out = set()
    for other in ROLES:
        if other == role:
            continue
        try:
            out.add(role_hardware(other)["serial"])
        except DeviceNotConfigured:
            pass
    return out
