"""Screen redaction. Screen content an agent can see goes through the host's redactor first.

The redactor is a separate tool (`phone-screen-safe`, found through PHONE_SCREEN_SAFE or PATH) that
masks secrets and PII in hierarchy XML and screenshots and blacks out sensitive apps. This module loads
it by file path and fails closed:

  PHONE_REDACTION=required (default)  no redactor, or a redactor error, means no content is returned.
  PHONE_REDACTION=off                 owner decision only; content is returned as captured.

Raw captures stay in memory. Only redacted results are written to disk or printed.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import shutil
from pathlib import Path

from .errors import RedactorUnavailable

_CACHE: dict = {}


def policy() -> str:
    value = os.environ.get("PHONE_REDACTION", "required").strip().lower()
    return "off" if value == "off" else "required"


def _find() -> str | None:
    explicit = os.environ.get("PHONE_SCREEN_SAFE")
    if explicit:
        return explicit if Path(explicit).is_file() else None
    return shutil.which("phone-screen-safe")


def load(path: str | None = None):
    """Load the redactor module from a file path, or return None when it is not available."""
    path = path or _find()
    if not path:
        return None
    if path in _CACHE:
        return _CACHE[path]
    try:
        loader = importlib.machinery.SourceFileLoader("phone_screen_safe", path)
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
    except Exception:  # noqa: BLE001 - a broken redactor must never degrade to "no redaction"
        _CACHE[path] = None
        return None
    _CACHE[path] = module
    return module


class Redactor:
    """Thin facade over the loaded redactor, or a pass-through when policy is off."""

    def __init__(self, module=None):
        self.module = module

    @property
    def active(self) -> bool:
        return self.module is not None

    def hierarchy(self, d) -> str:
        if self.module is None:
            return d.dump_hierarchy()
        return self.module.safe_hierarchy(d)

    def xml(self, xml: str) -> str:
        if self.module is None:
            return xml
        return self.module.redact_xml(xml)[0]

    def mask(self, text: str) -> str:
        if self.module is None or not text:
            return text
        return self.module.mask(text)

    def screenshot(self, d, path) -> int:
        """Write a redacted screenshot. Returns the redactor's code (3 = fully blacked out)."""
        if self.module is None:
            d.screenshot().save(str(path), "PNG")
            return 0
        return int(self.module.safe_screenshot(d, path) or 0)

    def sensitive_package(self, pkg: str) -> bool:
        fn = getattr(self.module, "sensitive_package", None) if self.module else None
        return bool(fn and pkg and fn(pkg))


def get(optional: bool = False) -> Redactor:
    """The redactor for this policy. Raises RedactorUnavailable when required and missing, unless
    optional=True (used only for diagnostics that tolerate a pass-through)."""
    if policy() == "off":
        return Redactor(None)
    module = load()
    if module is None:
        if optional:
            return Redactor(None)
        raise RedactorUnavailable(
            "no screen redactor available, so no screen content can be returned. Set "
            "PHONE_SCREEN_SAFE to the phone-screen-safe tool (needs tesseract). The owner can "
            "set PHONE_REDACTION=off to accept unredacted capture.")
    return Redactor(module)
