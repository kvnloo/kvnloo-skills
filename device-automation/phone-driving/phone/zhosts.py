"""Minimal reader for a private z0-hosts overlay (stdlib only, Python 3.11+).

Vendored subset of the reference reader in the z0-hosts template. Host-specific values (device
serials, models) live in the private overlay and are read at runtime. Nothing from it is ever
copied into this public repo or printed by default.

Lookup, as in the template: $Z0_HOSTS_DIR (default ~/.config/z0-hosts), host directory chosen by
$Z0_HOST_ID or by matching host.toml `match_hostnames` against the Tailscale Self.HostName or the
OS hostname, then `hosts/<host_id>/devices.toml`.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import tomllib
from pathlib import Path


def hosts_dir() -> Path:
    return Path(os.environ.get("Z0_HOSTS_DIR") or Path.home() / ".config" / "z0-hosts")


def _load(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text())
    except (FileNotFoundError, NotADirectoryError, PermissionError, tomllib.TOMLDecodeError):
        return {}


def _tailscale_hostname() -> str | None:
    exe = shutil.which("tailscale")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "status", "--json"], capture_output=True, text=True,
                             timeout=5, check=True)
        return (json.loads(out.stdout).get("Self") or {}).get("HostName")
    except (subprocess.SubprocessError, OSError, json.JSONDecodeError):
        return None


def host_id(root: Path | None = None) -> str:
    if os.environ.get("Z0_HOST_ID"):
        return os.environ["Z0_HOST_ID"]
    root = root or hosts_dir()
    hosts = root / "hosts"
    dirs = sorted(p for p in hosts.glob("*/") if p.is_dir()) if hosts.is_dir() else []
    for name in filter(None, [_tailscale_hostname(), socket.gethostname()]):
        for d in dirs:
            if name in (_load(d / "host.toml").get("match_hostnames") or []):
                return d.name
    return "default"


def overlay(component: str, root: Path | None = None) -> dict:
    root = root or hosts_dir()
    return _load(root / "hosts" / host_id(root) / f"{component}.toml")


def phone_entry(role: str, root: Path | None = None) -> dict:
    """The devices.toml table for a phone whose name or alias is `role`, else {}."""
    for name, entry in overlay("devices", root).items():
        if not isinstance(entry, dict) or entry.get("kind") != "phone":
            continue
        if name == role or role in (entry.get("aliases") or []):
            return entry
    return {}
