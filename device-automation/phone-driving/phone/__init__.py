"""phone: safe, locked, owner-aware phone driving over uiautomator2.

Importing this package activates the install/IME/settings guard (phone.guard). Order matters:
adbutils is pinned to this host's local adb server BEFORE it is imported, then the guard patches
adbutils and uiautomator2.

    uv run --with 'uiautomator2>=3.7,<3.8' python -c "import phone; ..."
"""
from . import config as _config

_config.prepare_environment()

from . import guard as _guard  # noqa: E402

_guard.install(eager=True)

from .errors import *  # noqa: E402,F401,F403
from .device import Phone, wait_for  # noqa: E402,F401
from .guard import PhoneGuardError, selftest as guard_selftest  # noqa: E402,F401
from . import adapters  # noqa: E402,F401

__version__ = "0.1.0"
