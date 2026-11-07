"""Exception types. PhoneGuardError lives in guard.py (shared with the stdlib copy)."""
from __future__ import annotations

from .guard import PhoneGuardError

__all__ = [
    "PhoneError", "PhoneGuardError", "LockError", "OwnerBusy", "DeviceNotConfigured",
    "DeviceNotFound", "RoleNotAllowed", "RedactorUnavailable", "CalibrationRequired",
    "WrongForeground", "DeviceLocked", "SensitiveTarget", "GenerationTimeout", "RestoreError",
    "ComposerDraftPreserved",
]


class PhoneError(RuntimeError):
    """Base class for phone driver errors."""


class LockError(PhoneError):
    """The exclusive host UI lock is not held, or could not be taken in time."""


class OwnerBusy(PhoneError):
    """The owner is using the phone (or evidence is missing). Nothing was touched."""


class DeviceNotConfigured(PhoneError):
    """No serial is known for this role; set it in the environment or the z0-hosts overlay."""


class DeviceNotFound(PhoneError):
    """The role's phone is not reachable through this host's adb server."""


class RoleNotAllowed(PhoneError):
    """This role is not enabled for driving on this host."""


class RedactorUnavailable(PhoneError):
    """Screen content cannot be returned because the redactor is missing or failed."""


class CalibrationRequired(PhoneError):
    """An adapter has not been calibrated on a real device; it refuses to guess."""


class WrongForeground(PhoneError):
    """The foreground app is not the one an agent opened (or the one named by --pkg)."""


class DeviceLocked(PhoneError):
    """Keyguard or cover blocks the app. A person must unlock; the driver never does."""


class SensitiveTarget(PhoneError):
    """Refused to type into a password field or a sensitive app."""


class GenerationTimeout(PhoneError):
    """The app was still generating when the wait ended."""


class RestoreError(PhoneError):
    """The phone could not be returned to its home screen."""


class ComposerDraftPreserved(PhoneError):
    """The fresh composer holds an unsent draft that is not ours. It was left untouched."""
