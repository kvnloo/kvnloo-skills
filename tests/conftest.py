"""Shared fixtures for the phone-driving tests. Other test modules are unaffected."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[1] / "device-automation" / "phone-driving"
sys.path.insert(0, str(SKILL))
sys.path.insert(0, str(Path(__file__).resolve().parent))


@pytest.fixture
def phone_env(tmp_path, monkeypatch):
    """Isolate every path the phone package writes, and drop host-specific settings."""
    monkeypatch.setenv("PHONE_LOCK_DIR", str(tmp_path / "lock"))
    monkeypatch.setenv("PHONE_SHARED_LOCK_DIR", str(tmp_path / "shared"))
    monkeypatch.setenv("PHONE_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("PHONE_REDACTION", "off")
    for var in ("PHONE_ALLOW_ROLES", "PHONE_WORKER_ROLES", "PHONE_IDLE_WORKER_UNTIL_S25",
                "PHONE_IDLE_WORKER_UNTIL_S22", "PHONE_HOME_LAUNCHERS", "PHONE_RECEIPTS",
                "PHONE_SCREEN_SAFE", "PHONE_CALIBRATION_DIR"):
        monkeypatch.delenv(var, raising=False)
    (tmp_path / "lock").mkdir()
    return tmp_path
