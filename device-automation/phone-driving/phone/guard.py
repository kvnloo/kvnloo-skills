"""HARD install / IME / settings guard for phone driving.

Stdlib only and self-contained: `scripts/install-guard.sh` copies this exact file next to a
Python's stdlib so that raw uiautomator2 or adbutils scripts are covered too.

What it blocks (raises PhoneGuardError, never touches the device):

  * adbutils: install, install_remote, uninstall, and a few device-state calls
    (switch_airplane, switch_wifi, reboot, tcpip, root, pair).
  * adbutils and uiautomator2 `shell` calls (and `open_shell`, `_shell_v2`) whose arguments
    contain pm install/uninstall/clear/disable/grant..., cmd package ..., ime enable/set/disable/
    reset, cmd input_method ..., settings put/delete/reset, device_config and appops writes,
    setprop, service call, content writes to settings, svc toggles, locksettings, reboot, or a
    stop of a protected package (am / cmd activity force-stop, kill, stop-app; am kill-all).
    Commands are matched by basename, so `/system/bin/pm install` is the same as `pm install`.
  * the adbutils wire protocol itself (AdbConnection.send_command): shell:, shell,v2:, exec:,
    abb: and abb_exec: services go through the same shell policy, and reboot:, root:, tcpip:,
    remount:, sideload: and host:pair are refused. Lower-level helpers cannot skip the policy.
  * uiautomator2: _setup_ime, send_keys, set_input_ime, set_fastinput_ime, set_clipboard, the
    clipboard getter and setter, app_install, app_uninstall, app_uninstall_all, app_stop_all,
    app_auto_grant_permissions, freeze_rotation, set_orientation, and the clipboard and rotation
    JSON-RPC methods (checked on Device.jsonrpc_call and on the HTTP request under it).
  * subprocess.Popen and os.system when they run the adb binary with install, uninstall, pair,
    sideload, reboot, root, tcpip, abb, or a shell command that the shell policy blocks, including
    through a shell (`bash -c "adb install ..."`) or a wrapper (`timeout 5 adb install ...`).

This is a seatbelt against mistakes by agents and scripts. It is not a sandbox against someone
who deliberately works around Python (for example a different adb client). It has no environment
switch that turns it off.

Two ways it becomes active:
  * `import phone` calls install() eagerly.
  * `sitecustomize` (see scripts/install-guard.sh) calls install(eager=False): nothing is
    imported at interpreter start; the patch is applied the moment adbutils or uiautomator2 is
    first imported.

Patches carry the guard version. When an older copy (for example a stale sitecustomize copy) has
already patched a process, a newer copy adds its own checks on top instead of skipping.
"""
from __future__ import annotations

import functools
import os
import sys

GUARD_VERSION = "2"

# The first copy of this module that loads owns the shared state, so the stdlib copy and the
# phone.guard copy agree on one exception class and never patch twice.
_STATE = getattr(sys, "_phone_guard_state", None)
if _STATE is None:
    class PhoneGuardError(RuntimeError):
        """Raised instead of installing, uninstalling, or changing IME or settings on a phone."""

    _STATE = {"exc": PhoneGuardError, "patched": [], "modules": set(), "finder": None,
              "hooking": set(), "popen": False, "version": GUARD_VERSION}
    sys._phone_guard_state = _STATE  # type: ignore[attr-defined]
PhoneGuardError = _STATE["exc"]

PROTECTED_DEFAULT = ("app.dash.mobile",)

PM_MUTATING = frozenset({
    "install", "install-create", "install-write", "install-commit", "install-abandon",
    "install-existing", "uninstall", "uninstall-system-updates", "clear", "disable",
    "disable-user", "disable-until-used", "enable", "hide", "unhide", "suspend", "unsuspend",
    "grant", "revoke", "reset-permissions", "set-installer", "set-home-activity",
    "trim-caches", "default-state",
})
SETTINGS_MUTATING = frozenset({"put", "delete", "reset"})
IME_MUTATING = frozenset({"enable", "disable", "set", "reset"})
DEVICE_CONFIG_MUTATING = frozenset({"put", "delete", "reset", "override", "clear-override",
                                    "set_sync_disabled_for_tests"})
APPOPS_MUTATING = frozenset({"set", "reset", "write-settings"})
ROLE_MUTATING = frozenset({"add-role-holder", "remove-role-holder", "clear-role-holders",
                           "set-bypassing-role-qualification"})
OVERLAY_MUTATING = frozenset({"enable", "disable", "enable-exclusive", "set-priority", "fabricate"})
# `cmd <service> <sub>` pairs that change device state (besides the services handled below).
CMD_MUTATING = {
    "package": PM_MUTATING, "settings": SETTINGS_MUTATING, "input_method": IME_MUTATING,
    "device_config": DEVICE_CONFIG_MUTATING, "appops": APPOPS_MUTATING, "role": ROLE_MUTATING,
    "overlay": OVERLAY_MUTATING, "wifi": frozenset({"set-wifi-enabled"}),
    "bluetooth_manager": frozenset({"enable", "disable"}),
}
STOP_VERBS = frozenset({"force-stop", "kill", "stop-app", "crash"})
ADB_BLOCKED_SUBCOMMANDS = frozenset({
    "install", "install-multiple", "install-multi-package", "uninstall", "pair", "sideload",
    "reboot", "root", "unroot", "remount", "tcpip", "disable-verity", "enable-verity",
    "kill-server",   # the host's one adb server: restarting it drops every wireless transport
})
ADB_BLOCKED_SERVICES = frozenset({
    "reboot", "root", "unroot", "remount", "tcpip", "sideload", "sideload-host",
    "enable-verity", "disable-verity",
})
CLIPBOARD_RPC = frozenset({"setClipboard", "getClipboard", "pasteClipboard"})
# Rotation RPCs write Settings.System (accelerometer_rotation, user_rotation).
SETTINGS_RPC = frozenset({"setOrientation", "freezeRotation"})
BLOCKED_RPC = CLIPBOARD_RPC | SETTINGS_RPC

_ADBUTILS_BLOCKED = {
    "install": "installing an app",
    "install_remote": "installing an app",
    "uninstall": "uninstalling an app",
    "switch_airplane": "changing airplane mode (a device setting)",
    "switch_wifi": "changing wifi (a device setting)",
    "reboot": "rebooting the phone",
    "tcpip": "switching adbd to tcpip",
    "root": "restarting adbd as root",
    "pair": "pairing with a phone",
}
_ADBUTILS_SHELL = ("shell", "shell2", "open_shell", "_shell_v2")
_U2_BLOCKED = {
    "freeze_rotation": "freezing rotation writes a device setting",
    "set_orientation": "setting the orientation writes a device setting",
    "send_keys": "send_keys installs or enables an IME or uses the clipboard; use "
                 "set_text on a selector (phone.Phone.type_text)",
    "_setup_ime": "installing an IME",
    "set_input_ime": "changing the input method",
    "set_fastinput_ime": "changing the input method",
    "set_clipboard": "the clipboard is not available to agents",
    "app_install": "installing an app",
    "app_uninstall": "uninstalling an app",
    "app_uninstall_all": "uninstalling apps",
    "app_stop_all": "stopping every app (this would include protected apps)",
    "app_auto_grant_permissions": "changing app permissions",
}


def _protected():
    extra = [p.strip() for p in os.environ.get("PHONE_PROTECTED_PKGS", "").split(",") if p.strip()]
    return set(PROTECTED_DEFAULT) | set(extra)


def _flatten(cmd) -> str:
    if cmd is None:
        return ""
    if isinstance(cmd, (bytes, bytearray)):
        return bytes(cmd).decode("utf-8", "replace")
    if isinstance(cmd, str):
        return cmd
    try:
        return " ".join(str(x) for x in cmd)
    except TypeError:
        return str(cmd)


def _token_variants(text: str):
    """Two tokenisations (quotes as separators, quotes deleted) so p""m style splits still match."""
    import re
    sep = re.compile(r"[\s;&|`()<>'\"$\\{}\[\],]+")
    plain = [t for t in sep.split(text) if t]
    joined = [t for t in sep.split(re.sub(r"['\"\\]", "", text)) if t]
    return plain, joined


def _next(tokens, i):
    """Index of the first non-option token after i, skipping `--user N` style pairs."""
    j = i + 1
    while j < len(tokens):
        t = tokens[j]
        if t in ("--user", "-u"):
            j += 2
            continue
        if t.startswith("-"):
            j += 1
            continue
        return j
    return None


def _scan(tokens, raw):
    protected = _protected()
    # Match commands by basename: `/system/bin/pm install` is `pm install`.
    tokens = [t.rsplit("/", 1)[-1] if "/" in t and "://" not in t else t for t in tokens]
    for i, tok in enumerate(tokens):
        if tok == "pm":
            j = _next(tokens, i)
            if j is not None and tokens[j] in PM_MUTATING:
                return f"pm {tokens[j]} changes packages or permissions"
        elif tok == "cmd":
            j = _next(tokens, i)
            if j is None:
                continue
            svc = tokens[j]
            k = _next(tokens, j)
            sub = tokens[k] if k is not None else ""
            if sub in CMD_MUTATING.get(svc, ()):
                return f"cmd {svc} {sub} changes device state, packages or settings"
            if svc == "activity" and sub in STOP_VERBS | {"kill-all"} and (
                    sub == "kill-all" or any(t in protected for t in tokens[k + 1:])):
                return f"cmd activity {sub} on a protected package"
            if svc == "connectivity" and sub == "airplane-mode" and _next(tokens, k) is not None:
                return "cmd connectivity airplane-mode changes a device setting"
            if svc == "lock_settings" and sub.startswith(("set-", "clear", "remove")):
                return f"cmd lock_settings {sub} changes the lock screen"
        elif tok == "settings":
            j = _next(tokens, i)
            if j is not None and tokens[j] in SETTINGS_MUTATING:
                return f"settings {tokens[j]} changes device settings"
        elif tok == "device_config":
            j = _next(tokens, i)
            if j is not None and tokens[j] in DEVICE_CONFIG_MUTATING:
                return f"device_config {tokens[j]} changes device settings"
        elif tok == "appops":
            j = _next(tokens, i)
            if j is not None and tokens[j] in APPOPS_MUTATING:
                return f"appops {tokens[j]} changes app permissions"
        elif tok == "setprop":
            return "setprop changes device properties"
        elif tok == "service":
            j = _next(tokens, i)
            if j is not None and tokens[j] == "call":
                return "service call is a raw binder call (it can change the keyboard or settings)"
        elif tok == "ime":
            j = _next(tokens, i)
            if j is not None and tokens[j] in IME_MUTATING:
                return f"ime {tokens[j]} changes the keyboard"
        elif tok == "svc":
            rest = tokens[i + 1:i + 4]
            if any(r in ("enable", "disable", "stayon") for r in rest):
                return "svc changes a device radio or power setting"
        elif tok == "content":
            j = _next(tokens, i)
            if j is not None and tokens[j] in ("insert", "update", "delete", "call") \
                    and "content://settings" in raw:
                return "content write to the settings provider"
        elif tok in ("locksettings", "reboot"):
            return f"{tok} changes device state"
        elif tok == "wm":
            j = _next(tokens, i)
            if j is not None and tokens[j] in ("size", "density", "overscan") \
                    and _next(tokens, j) is not None:
                return f"wm {tokens[j]} with an argument changes the display"
        elif tok == "am":
            j = _next(tokens, i)
            if j is not None and tokens[j] == "kill-all":
                return "am kill-all would stop protected packages"
            if j is not None and tokens[j] in STOP_VERBS:
                if any(t in protected for t in tokens[j + 1:]):
                    return f"am {tokens[j]} on a protected package"
        # `pm clear <protected>` is already covered by PM_MUTATING ("clear").
    return None


def explain_shell(cmd):
    """Return a reason string when this device shell command must be refused, else None."""
    text = _flatten(cmd)
    for tokens in _token_variants(text):
        reason = _scan(tokens, text)
        if reason:
            return reason
    return None


def check_shell(cmd, where: str = "shell"):
    reason = explain_shell(cmd)
    if reason:
        raise PhoneGuardError(f"phone guard blocked {where}: {reason}")


def explain_service(cmd):
    """Reason to refuse an adb wire-protocol service request (what adbutils sends with
    AdbConnection.send_command), else None. Host queries, forwards and sync pass."""
    text = _flatten(cmd)
    head, sep, rest = text.partition(":")
    if not sep:
        return None
    if head == "shell" or head.startswith("shell,") or head == "exec":
        return explain_shell(rest)
    if head in ("abb", "abb_exec"):
        return explain_shell("cmd " + rest.replace("\0", " "))
    if head in ADB_BLOCKED_SERVICES:
        return f"adb service {head} changes device state"
    if head == "host" and rest.startswith("pair"):
        return "pairing with a phone"
    if head == "host" and rest == "kill":
        return "killing the host's adb server drops every wireless transport"
    return None


def check_service(cmd):
    reason = explain_service(cmd)
    if reason:
        raise PhoneGuardError(f"phone guard blocked adb service: {reason}")


_ADB_VALUE_OPTS = frozenset({"-s", "-t", "-H", "-P", "-L", "--one-device"})


def explain_adb_argv(argv):
    """Reason to refuse an adb binary invocation, else None. argv[0] is the adb executable."""
    rest = [str(a) for a in argv[1:]]
    i = 0
    while i < len(rest):
        a = rest[i]
        if a in _ADB_VALUE_OPTS:
            i += 2
            continue
        if a in ("-a", "-d", "-e"):
            i += 1
            continue
        break
    if i >= len(rest):
        return None
    sub = rest[i]
    if sub in ADB_BLOCKED_SUBCOMMANDS:
        return f"adb {sub} is not allowed"
    if sub in ("shell", "exec-out", "exec-in"):
        return explain_shell(rest[i + 1:])
    if sub in ("abb", "abb_exec"):
        return explain_shell(["cmd", *rest[i + 1:]])
    return None


# Commands that run another command: their arguments are searched for adb or a `-c` script.
_SHELLS = frozenset({"sh", "bash", "dash", "zsh", "ksh", "mksh", "ash", "fish"})
_WRAPPERS = frozenset({"env", "timeout", "nice", "nohup", "stdbuf", "setsid", "flock", "sudo",
                       "doas", "ionice", "chrt", "taskset", "time", "unbuffer", "uv", "uvx",
                       "watch", "xargs", "busybox", "toybox"})


def _check_argv(argv):
    head = os.path.basename(argv[0])
    if head == "adb":
        reason = explain_adb_argv(argv)
        if reason:
            raise PhoneGuardError(f"phone guard blocked subprocess: {reason}")
        return
    if head not in _SHELLS and head not in _WRAPPERS:
        return
    for i in range(1, len(argv)):
        a = argv[i]
        if os.path.basename(a) == "adb":
            _check_argv(argv[i:])
            return
        if (a == "--command" or (a.startswith("-") and not a.startswith("--") and "c" in a[1:])) \
                and i + 1 < len(argv):
            _check_popen(argv[i + 1], True)


def _check_popen(args, shell):
    import re
    if isinstance(args, (bytes, bytearray)):
        args = bytes(args).decode("utf-8", "replace")
    if isinstance(args, os.PathLike):
        args = os.fspath(args)
    if isinstance(args, str):
        if "adb" not in args:
            return
        if shell:
            for m in re.finditer(r"(?:^|[\s;&|(`/])adb(?=\s|$)", args):
                tail = args[m.start():].lstrip(" ;&|(`/")
                reason = explain_adb_argv(tail.split())
                if reason:
                    raise PhoneGuardError(f"phone guard blocked subprocess: {reason}")
            return
        argv = args.split()
    else:
        try:
            argv = [os.fsdecode(a) for a in args]
        except TypeError:
            return
    if argv:
        _check_argv(argv)


def _marked(fn):
    fn.__phone_guard__ = GUARD_VERSION
    return fn


def _is_marked(fn):
    """Patched by any guard version (a blocked method stays blocked)."""
    return bool(getattr(fn, "__phone_guard__", False))


def _is_current(fn):
    """Patched by THIS guard version. Checking wrappers from an older copy are wrapped again so
    the newer checks also run."""
    return getattr(fn, "__phone_guard__", None) == GUARD_VERSION


def _patch_subprocess():
    if _STATE.get("popen_version") == GUARD_VERSION:
        return
    import subprocess
    orig_init = subprocess.Popen.__init__
    if not _is_current(orig_init):
        @functools.wraps(orig_init)
        def popen_init(self, *a, **kw):
            args = a[0] if a else kw.get("args")
            shell = kw.get("shell") or (len(a) > 8 and a[8])
            _check_popen(args, shell)
            return orig_init(self, *a, **kw)
        subprocess.Popen.__init__ = _marked(popen_init)
    orig_system = os.system
    if not _is_current(orig_system):
        @functools.wraps(orig_system)
        def system(command):
            _check_popen(command, True)
            return orig_system(command)
        os.system = _marked(system)
    _STATE["popen"] = True
    _STATE["popen_version"] = GUARD_VERSION
    _STATE["patched"].append(f"subprocess.Popen/os.system@{GUARD_VERSION}")


def _concrete_owners(cls, name):
    for klass in cls.__mro__:
        fn = vars(klass).get(name)
        if fn is None:
            continue
        if getattr(fn, "__isabstractmethod__", False):
            continue
        yield klass, fn


def _block_method(cls, name, reason):
    done = False
    for klass, fn in _concrete_owners(cls, name):
        if _is_marked(fn):
            done = True
            continue

        def blocked(*a, __name=name, __reason=reason, **kw):
            raise PhoneGuardError(f"phone guard blocked {__name}: {__reason}")
        setattr(klass, name, _marked(blocked))
        done = True
    if done:
        _STATE["patched"].append(f"{cls.__module__.split('.')[0]}.{cls.__name__}.{name}")
    return done


def _guard_shell_method(cls, name):
    done = False
    for klass, fn in _concrete_owners(cls, name):
        if _is_current(fn):
            done = True
            continue

        def make(orig, __name=name):
            @functools.wraps(orig)
            def guarded(self, *a, **kw):
                cmd = a[0] if a else kw.get("cmdargs", kw.get("command", ""))
                check_shell(cmd, f"{__name}")
                return orig(self, *a, **kw)
            return _marked(guarded)
        setattr(klass, name, make(fn))
        done = True
    if done:
        _STATE["patched"].append(f"{cls.__module__.split('.')[0]}.{cls.__name__}.{name}(shell-check)")
    return done


def _block_property(cls, name, reason):
    for klass in cls.__mro__:
        prop = vars(klass).get(name)
        if isinstance(prop, property):
            if _is_marked(prop.fget):
                return True

            def blocked(*a, __reason=reason, **kw):
                raise PhoneGuardError(f"phone guard blocked {name}: {__reason}")
            setattr(klass, name, property(_marked(blocked), _marked(blocked)))
            _STATE["patched"].append(f"uiautomator2.{klass.__name__}.{name}")
            return True
    return False


def _check_rpc(method):
    if method in BLOCKED_RPC:
        why = ("the clipboard is not available to agents" if method in CLIPBOARD_RPC
               else "it writes a device setting")
        raise PhoneGuardError(f"phone guard blocked jsonrpc {method}: {why}")


def _guard_transport(mod):
    """Check every adb service request at the wire: helpers below `shell` (open_transport,
    _shell_v2, a hand-built connection) cannot skip the shell policy."""
    conn = getattr(mod, "AdbConnection", None)
    if conn is None:
        conn = getattr(sys.modules.get("adbutils._adb"), "AdbConnection", None)
    if conn is None:
        return
    for klass, fn in list(_concrete_owners(conn, "send_command")):
        if _is_current(fn):
            continue

        def make(orig):
            @functools.wraps(orig)
            def send_command(self, cmd, *a, **kw):
                check_service(cmd)
                return orig(self, cmd, *a, **kw)
            return _marked(send_command)
        klass.send_command = make(fn)
        _STATE["patched"].append(f"adbutils.{klass.__name__}.send_command(service-check)")


def _patch_adbutils(mod):
    cls = getattr(mod, "AdbDevice", None)
    if cls is None:
        return
    for name, reason in _ADBUTILS_BLOCKED.items():
        _block_method(cls, name, reason)
    for name in _ADBUTILS_SHELL:
        _guard_shell_method(cls, name)
    client = getattr(mod, "AdbClient", None)
    if client is not None:
        _block_method(client, "pair", _ADBUTILS_BLOCKED["pair"])
        _block_method(client, "server_kill",
                      "killing the host's adb server drops every wireless transport")
    _guard_transport(mod)


def _patch_u2(mod):
    cls = getattr(mod, "Device", None)
    if cls is None:
        return
    for name, reason in _U2_BLOCKED.items():
        _block_method(cls, name, reason)
    _block_property(cls, "clipboard", "the clipboard is not available to agents")
    _guard_shell_method(cls, "shell")
    for klass, fn in list(_concrete_owners(cls, "jsonrpc_call")):
        if _is_current(fn):
            continue

        def make(orig):
            @functools.wraps(orig)
            def jsonrpc_call(self, method, *a, **kw):
                _check_rpc(method)
                return orig(self, method, *a, **kw)
            return _marked(jsonrpc_call)
        klass.jsonrpc_call = make(fn)
        _STATE["patched"].append(f"uiautomator2.{klass.__name__}.jsonrpc_call(rpc-check)")
    # The module-level HTTP helper under jsonrpc_call: core._jsonrpc_call(...) called directly
    # must not reach the clipboard or rotation RPCs either.
    core = sys.modules.get(f"{mod.__name__}.core")
    http = getattr(core, "_http_request", None)
    if http is not None and not _is_current(http):
        @functools.wraps(http)
        def _http_request(dev, device_port, method, path, data=None, *a, **kw):
            if isinstance(data, dict):
                _check_rpc(data.get("method"))
            return http(dev, device_port, method, path, data, *a, **kw)
        core._http_request = _marked(_http_request)
        _STATE["patched"].append("uiautomator2.core._http_request(rpc-check)")


def _module_key(name):
    return f"{name}@{GUARD_VERSION}"


def _patch_module(name, module):
    if _module_key(name) in _STATE["modules"]:
        return
    if name == "adbutils":
        _patch_adbutils(module)
    elif name == "uiautomator2":
        _patch_u2(module)
    _STATE["modules"].add(_module_key(name))


def _ready(name, module):
    return hasattr(module, "AdbDevice" if name == "adbutils" else "Device")


class _PatchFinder:
    """meta_path finder that patches adbutils and uiautomator2 right after they are imported."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname not in ("adbutils", "uiautomator2") or fullname in _STATE["hooking"]:
            return None
        _STATE["hooking"].add(fullname)
        spec = None
        try:
            for finder in list(sys.meta_path):
                if finder is self:
                    continue
                find = getattr(finder, "find_spec", None)
                if find is None:
                    continue
                spec = find(fullname, path, target)
                if spec is not None:
                    break
        finally:
            _STATE["hooking"].discard(fullname)
        if spec is None or spec.loader is None:
            return None
        loader = spec.loader
        orig_exec = loader.exec_module

        def exec_module(module, __orig=orig_exec, __name=fullname):
            __orig(module)
            _patch_module(__name, module)
        try:
            loader.exec_module = exec_module
        except (AttributeError, TypeError):
            class _Wrap:
                def __init__(self, inner):
                    self._inner = inner

                def create_module(self, s):
                    fn = getattr(self._inner, "create_module", None)
                    return fn(s) if fn else None

                def exec_module(self, module):
                    self._inner.exec_module(module)
                    _patch_module(fullname, module)

                def __getattr__(self, n):
                    return getattr(self._inner, n)
            spec.loader = _Wrap(loader)
        return spec


def install(eager: bool = True):
    """Apply the guard now to anything importable, and hook what is not yet imported.

    eager=True imports adbutils and uiautomator2 when available (used by `import phone`).
    eager=False only patches modules already imported and hooks the rest (used by sitecustomize,
    so interpreter start stays cheap).
    """
    _patch_subprocess()
    for name in ("adbutils", "uiautomator2"):
        if _module_key(name) in _STATE["modules"]:
            continue
        module = sys.modules.get(name)
        if module is None and eager:
            try:
                import importlib
                module = importlib.import_module(name)
            except ImportError:
                module = None
        if module is not None and _ready(name, module):
            _patch_module(name, module)
    pending = [n for n in ("adbutils", "uiautomator2") if _module_key(n) not in _STATE["modules"]]
    if pending and _STATE.get("finder_version") != GUARD_VERSION:
        # An older copy's finder may be registered already; ours goes in front of it.
        finder = _PatchFinder()
        sys.meta_path.insert(0, finder)
        _STATE["finder"] = finder
        _STATE["finder_version"] = GUARD_VERSION
    return status()


def status():
    return {"version": GUARD_VERSION, "first_loaded": _STATE["version"],
            "patched": list(_STATE["patched"]), "modules": sorted(_STATE["modules"]),
            "hooked": _STATE["finder"] is not None, "popen": _STATE["popen"]}


BLOCKED_SAMPLES = (
    "pm install -r /sdcard/a.apk",
    ["pm", "uninstall", "com.example.app"],
    "cmd package install-existing com.example.app",
    "ime enable com.example/.Keyboard",
    ["ime", "set", "com.example/.Keyboard"],
    "settings put secure default_input_method com.example/.Keyboard",
    "settings --user 0 put global airplane_mode_on 1",
    "sh -c 'pm install /sdcard/a.apk'",
    "echo hi; settings put system screen_off_timeout 1",
    "pm clear com.example.app",
    "svc wifi disable",
    "wm density 480",
    "am force-stop app.dash.mobile",
    "p\"\"m install /sdcard/a.apk",
    "/system/bin/pm install /sdcard/a.apk",
    "/system/bin/ime set com.example/.Keyboard",
    "/system/bin/settings put secure default_input_method com.example/.Keyboard",
    "cmd activity force-stop app.dash.mobile",
    "am stop-app app.dash.mobile",
    "am kill-all",
    "setprop persist.sys.locale en-US",
    "device_config put a b c",
    "appops set com.example.app CAMERA allow",
    "service call input_method 1",
)
ALLOWED_SAMPLES = (
    "cat /proc/uptime",
    ["getprop", "ro.serialno"],
    "dumpsys power | grep mLastUserActivityTime",
    "settings get secure default_input_method",
    "ime list -s -a",
    "pm list packages -3",
    "pm path com.example.app",
    "monkey -p com.example.app -c android.intent.category.LAUNCHER 1",
    "am force-stop com.example.app",
    ["toybox", "md5sum", "/data/local/tmp/u2.jar"],
    "CLASSPATH=/data/local/tmp/u2.jar app_process / com.wetest.uia2.Main -p 9008",
    "cmd package resolve-activity --brief -a android.intent.action.MAIN",
    "wm size",
    "cmd activity force-stop com.example.app",
    "getprop ro.product.model",
    "dumpsys window policy",
)


def selftest():
    """Prove the guard is active. Returns a list of (name, ok, detail). No device is touched."""
    results = []

    def blocked(name, fn):
        try:
            fn()
        except PhoneGuardError:
            results.append((name, True, "blocked"))
        except Exception as e:  # noqa: BLE001
            results.append((name, False, f"raised {type(e).__name__} instead: {e}"))
        else:
            results.append((name, False, "NOT blocked"))

    def allowed(name, fn):
        try:
            fn()
        except PhoneGuardError as e:
            results.append((name, False, f"wrongly blocked: {e}"))
        except Exception:  # noqa: BLE001
            results.append((name, True, "allowed"))
        else:
            results.append((name, True, "allowed"))

    for cmd in BLOCKED_SAMPLES:
        blocked(f"policy blocks {_flatten(cmd)[:48]}", lambda c=cmd: check_shell(c))
    for cmd in ALLOWED_SAMPLES:
        allowed(f"policy allows {_flatten(cmd)[:48]}", lambda c=cmd: check_shell(c))
    blocked("adb argv install", lambda: _check_popen(["adb", "-s", "X", "install", "a.apk"], False))
    blocked("adb argv shell settings put",
            lambda: _check_popen(["adb", "shell", "settings", "put", "global", "a", "1"], False))
    blocked("adb shell string pm install", lambda: _check_popen("adb shell pm install a.apk", True))
    blocked("bash -c adb install", lambda: _check_popen(["bash", "-c", "adb install a.apk"], False))
    blocked("timeout adb install", lambda: _check_popen(["timeout", "5", "adb", "install", "a"], False))
    blocked("adb abb package install", lambda: _check_popen(["adb", "abb", "package", "install"],
                                                             False))
    allowed("adb argv devices", lambda: _check_popen(["adb", "devices", "-l"], False))
    for svc in ("shell:pm install /sdcard/a.apk", "shell,v2:ime set com.example/.K",
                "exec:cmd package install -S 1", "abb_exec:package\0install-create",
                "reboot:", "tcpip:5555", "host:pair:123456:host"):
        blocked(f"adb service {svc[:28]!r}", lambda s=svc: check_service(s))
    for svc in ("shell:getprop ro.serialno", "host:devices-l", "sync:", "tcp:9008"):
        allowed(f"adb service {svc[:28]!r}", lambda s=svc: check_service(s))

    import subprocess
    blocked("subprocess.Popen adb install", lambda: subprocess.Popen(["adb", "install", "a.apk"]))
    blocked("os.system adb uninstall", lambda: os.system("adb uninstall com.example.app"))

    adbutils = sys.modules.get("adbutils")
    if adbutils is None:
        try:
            import adbutils  # noqa: F811
        except ImportError:
            adbutils = None
    if adbutils is not None and hasattr(adbutils, "AdbDevice"):
        dev = object.__new__(adbutils.AdbDevice)
        blocked("adbutils.install", lambda: dev.install("a.apk"))
        blocked("adbutils.install_remote", lambda: dev.install_remote("/sdcard/a.apk"))
        blocked("adbutils.uninstall", lambda: dev.uninstall("com.example.app"))
        blocked("adbutils.shell pm install", lambda: dev.shell(["pm", "install", "/sdcard/a.apk"]))
        blocked("adbutils.shell2 settings put", lambda: dev.shell2("settings put global a 1"))
        blocked("adbutils._shell_v2 pm install", lambda: dev._shell_v2("pm install /sdcard/a.apk"))
        conn_cls = getattr(adbutils, "AdbConnection", None) or getattr(
            sys.modules.get("adbutils._adb"), "AdbConnection", None)
        if conn_cls is not None:
            conn = object.__new__(conn_cls)
            blocked("adbutils.AdbConnection shell,v2 ime set",
                    lambda: conn.send_command("shell,v2:ime set com.example/.K"))
            blocked("adbutils.AdbConnection abb_exec install",
                    lambda: conn.send_command("abb_exec:package\0install"))
        else:
            results.append(("adbutils.AdbConnection", False, "not found; wire check missing"))
    else:
        results.append(("adbutils", True, "not installed here; guard will hook it on import"))

    u2 = sys.modules.get("uiautomator2")
    if u2 is None:
        try:
            import uiautomator2 as u2  # noqa: F811
        except ImportError:
            u2 = None
    if u2 is not None and hasattr(u2, "Device"):
        try:
            d = object.__new__(u2.Device)
        except TypeError as e:
            results.append(("uiautomator2.Device", False, f"cannot build probe instance: {e}"))
            d = None
        if d is not None:
            blocked("u2._setup_ime", lambda: d._setup_ime())
            blocked("u2.send_keys", lambda: d.send_keys("x"))
            blocked("u2.set_input_ime", lambda: d.set_input_ime(True))
            blocked("u2.set_fastinput_ime", lambda: d.set_fastinput_ime(True))
            blocked("u2.clipboard getter", lambda: d.clipboard)
            blocked("u2.clipboard setter", lambda: setattr(d, "clipboard", "x"))
            blocked("u2.set_clipboard", lambda: d.set_clipboard("x"))
            blocked("u2.app_install", lambda: d.app_install("a.apk"))
            blocked("u2.app_uninstall", lambda: d.app_uninstall("com.example.app"))
            blocked("u2.app_stop_all", lambda: d.app_stop_all())
            blocked("u2.shell pm install", lambda: d.shell(["pm", "install", "a.apk"]))
            blocked("u2.shell ime set", lambda: d.shell("ime set com.example/.K"))
            blocked("u2.jsonrpc setClipboard",
                    lambda: u2.Device.jsonrpc_call(d, "setClipboard", ["a", "b"]))
            blocked("u2.jsonrpc freezeRotation",
                    lambda: u2.Device.jsonrpc_call(d, "freezeRotation", [True]))
            blocked("u2.freeze_rotation", lambda: d.freeze_rotation(True))
            core = sys.modules.get("uiautomator2.core")
            if core is not None and hasattr(core, "_jsonrpc_call"):
                blocked("u2.core._jsonrpc_call setClipboard",
                        lambda: core._jsonrpc_call(None, 0, "setClipboard", ["a", "b"], 1, False))
            else:
                results.append(("uiautomator2.core", False, "not found; HTTP rpc check missing"))
    else:
        results.append(("uiautomator2", True, "not installed here; guard will hook it on import"))
    return results


def _main(argv):
    if argv and argv[0] not in ("selftest", "status"):
        print("usage: python -m phone.guard [selftest|status]")
        return 2
    install(eager=True)
    if argv and argv[0] == "status":
        import json
        print(json.dumps(status(), indent=2))
        return 0
    results = selftest()
    failed = [r for r in results if not r[1]]
    for name, ok, detail in results:
        print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if not ok else ""))
    print(f"{len(results) - len(failed)}/{len(results)} guard checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
