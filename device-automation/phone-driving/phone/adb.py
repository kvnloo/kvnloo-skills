"""adb helpers: one local adb server, runtime discovery of a role's phone, identity proof.

Phones are driven only through THIS host's adb server. ADB_SERVER_SOCKET is dropped so a forwarded
socket can never redirect a call to another machine's server.

Discovery (no port scans, no hardcoded addresses, no pairing):
  1. read `adb devices -l` and `adb mdns services`;
  2. candidates = transports whose serial equals the role's hardware serial (USB), mDNS adverts whose
     name embeds that serial, and other transports whose reported model matches the role's model;
  3. a transport that is another role's phone is never probed;
  4. an advertised endpoint that is not connected is connected with `adb connect` (existing
     pairing only);
  5. identity is proven with `getprop ro.serialno` before the transport is used.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass

from . import config
from .errors import DeviceNotFound


def run(args: list[str], serial: str | None = None, timeout: float = 20.0,
        check: bool = True) -> subprocess.CompletedProcess:
    cmd = [config.adb_path(), "-P", config.adb_port()]
    if serial:
        cmd += ["-s", serial]
    return subprocess.run(cmd + list(args), capture_output=True, text=True, timeout=timeout,
                          check=check, stdin=subprocess.DEVNULL, env=config.adb_env())


@dataclass(frozen=True)
class Transport:
    serial: str          # the adb transport id used to reach the phone (never printed by default)
    hardware: str        # the proven hardware serial
    kind: str            # "usb" or "wireless"


def _norm(model: str) -> str:
    return re.sub(r"[^a-z0-9]", "", model.lower())


def parse_devices(output: str) -> list[dict]:
    """Parse `adb devices -l` into [{"serial", "state", "model"}]."""
    rows = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) < 2 or fields[0] == "List":
            continue
        info = dict(f.split(":", 1) for f in fields[2:] if ":" in f)
        rows.append({"serial": fields[0], "state": fields[1], "model": info.get("model", "")})
    return rows


def parse_mdns(output: str) -> list[dict]:
    """Parse `adb mdns services` into [{"name", "type", "endpoint"}]."""
    rows = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[1].startswith("_adb"):
            rows.append({"name": fields[0], "type": fields[1], "endpoint": fields[-1]})
    return rows


def devices() -> list[dict]:
    return parse_devices(run(["devices", "-l"]).stdout)


def mdns_services() -> list[dict]:
    try:
        return parse_mdns(run(["mdns", "services"], check=False).stdout)
    except (OSError, subprocess.SubprocessError):
        return []


def candidates(role: str, rows: list[dict], adverts: list[dict]) -> list[str]:
    """Ordered transport candidates for a role, never including another role's phone."""
    hw = config.role_hardware(role)
    hardware, model = hw["serial"], _norm(hw["model"])
    others = config.other_role_serials(role)
    connected = [r for r in rows if r["state"] == "device"]
    out: list[str] = []
    for r in connected:
        s = r["serial"]
        if s in others or any(s.startswith(f"adb-{o}-") for o in others):
            continue
        if s == hardware or s.startswith(f"adb-{hardware}-"):
            out.append(s)
    for a in adverts:
        if a["type"] == "_adb-tls-connect._tcp" and a["name"].startswith(f"adb-{hardware}-"):
            out.append(a["endpoint"])
    for r in connected:
        s = r["serial"]
        if s in out or s in others or any(s.startswith(f"adb-{o}-") for o in others):
            continue
        if model and _norm(r["model"]) == model:
            out.append(s)
        elif not model and ":" in s and "." in s:
            out.append(s)  # an ip:port transport with no model hint: identity probe decides
    return list(dict.fromkeys(sorted(out, key=lambda c: c != hardware)))


def discover(role: str) -> Transport:
    hardware = config.role_hardware(role)["serial"]
    rows = devices()
    connected = {r["serial"] for r in rows if r["state"] == "device"}
    for cand in candidates(role, rows, mdns_services()):
        if cand not in connected:
            run(["connect", cand], timeout=15, check=False)
        ident = run(["shell", "getprop", "ro.serialno"], serial=cand, timeout=15, check=False)
        if ident.returncode == 0 and ident.stdout.strip() == hardware:
            return Transport(serial=cand, hardware=hardware,
                             kind="usb" if cand == hardware else "wireless")
    raise DeviceNotFound(f"{role}: no authenticated adb transport for this role on this host")


def visible_roles() -> list[dict]:
    """Summary per role without probing any phone: configured?, visible transports, kind."""
    out = []
    try:
        rows, adverts = devices(), mdns_services()
    except (OSError, subprocess.SubprocessError, FileNotFoundError) as e:
        return [{"role": r, "error": f"adb unavailable: {type(e).__name__}"} for r in config.ROLES]
    for role in config.ROLES:
        entry = {"role": role, "allowed": role in config.allowed_roles()}
        try:
            hw = config.role_hardware(role)
        except Exception as e:  # noqa: BLE001
            entry.update({"configured": False, "note": str(e)[:160]})
            out.append(entry)
            continue
        entry["configured"] = True
        entry["model"] = hw["model"] or None
        kinds = []
        for r in rows:
            if r["serial"] == hw["serial"] or r["serial"].startswith(f"adb-{hw['serial']}-"):
                kinds.append(("usb" if r["serial"] == hw["serial"] else "wireless", r["state"]))
        for a in adverts:
            if a["name"].startswith(f"adb-{hw['serial']}-"):
                kinds.append(("wireless-advertised", "mdns"))
        entry["transports"] = [{"kind": k, "state": s} for k, s in kinds]
        out.append(entry)
    return out
