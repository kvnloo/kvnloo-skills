"""The install / IME / settings guard: policy, patches, self-test, and the sitecustomize installer."""
from __future__ import annotations

import inspect
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

import phone
from phone import guard
from phone.guard import PhoneGuardError

SKILL = Path(__file__).resolve().parents[1] / "device-automation" / "phone-driving"
INSTALLER = SKILL / "scripts" / "install-guard.sh"

BLOCKED = [
    "pm install -r /sdcard/a.apk",
    ["pm", "uninstall", "com.example.app"],
    "pm uninstall --user 0 com.example.app",
    "cmd package install-existing com.example.app",
    "cmd package uninstall com.example.app",
    "ime enable com.example/.Keyboard",
    ["ime", "set", "com.example/.Keyboard"],
    "ime disable com.example/.Keyboard",
    "cmd input_method set com.example/.K",
    "settings put secure default_input_method com.example/.Keyboard",
    "settings --user 0 put global airplane_mode_on 1",
    "settings delete system foo",
    "cmd settings put global x 1",
    "sh -c 'pm install /sdcard/a.apk'",
    "echo hi; settings put system screen_off_timeout 1",
    "true && pm install x",
    "pm clear com.example.app",
    "pm disable-user com.example.app",
    "pm grant com.example.app android.permission.CAMERA",
    "svc wifi disable",
    "svc power stayon true",
    "wm density 480",
    "wm size 720x1280",
    "locksettings clear --old 1234",
    "content insert --uri content://settings/secure --bind name:s:x",
    "am force-stop app.dash.mobile",
    "p\"\"m install /sdcard/a.apk",
    # path-qualified binaries are the same commands
    "/system/bin/pm install /sdcard/a.apk",
    "/system/bin/ime set com.example/.Keyboard",
    "/system/bin/settings put secure default_input_method com.example/.Keyboard",
    "/system/bin/cmd package install-existing com.example.app",
    # other ways to stop a protected package or change settings and permissions
    "cmd activity force-stop app.dash.mobile",
    "cmd activity kill-all",
    "am stop-app app.dash.mobile",
    "am kill-all",
    "setprop persist.sys.locale en-US",
    "device_config put a b c",
    "cmd device_config delete a b",
    "appops set com.example.app CAMERA allow",
    "cmd appops reset com.example.app",
    "cmd role add-role-holder android.app.role.HOME com.example.app",
    "cmd overlay enable com.example.overlay",
    "cmd wifi set-wifi-enabled disabled",
    "cmd bluetooth_manager disable",
    "cmd connectivity airplane-mode enable",
    "cmd lock_settings set-pin 1234",
    "service call input_method 1",
]
ALLOWED = [
    "cat /proc/uptime",
    ["getprop", "ro.serialno"],
    "dumpsys power | grep mLastUserActivityTime",
    "dumpsys activity activities | grep -E 'topResumedActivity=|mResumedActivity:'",
    "settings get secure default_input_method",
    "ime list -s -a",
    "pm list packages -3",
    "pm path com.example.app",
    "monkey -p com.example.app -c android.intent.category.LAUNCHER 1",
    "am force-stop com.example.app",
    "am start -a android.intent.action.VIEW -d https://example.org",
    ["toybox", "md5sum", "/data/local/tmp/u2.jar"],
    "CLASSPATH=/data/local/tmp/u2.jar app_process / com.wetest.uia2.Main -p 9008",
    "cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.HOME",
    "wm size",
    "input keyevent WAKEUP",
    "dumpsys telephony.registry",
    "screencap -p",
    "cmd activity force-stop com.example.app",
    "cmd connectivity airplane-mode",
    "device_config get a b",
    "service list",
    "/system/bin/getprop ro.serialno",
    "content query --uri content://settings/secure --where name=default_input_method",
]


@pytest.mark.parametrize("cmd", BLOCKED)
def test_shell_policy_blocks(cmd):
    assert guard.explain_shell(cmd), cmd
    with pytest.raises(PhoneGuardError):
        guard.check_shell(cmd)


@pytest.mark.parametrize("cmd", ALLOWED)
def test_shell_policy_allows(cmd):
    assert guard.explain_shell(cmd) is None, cmd


def test_protected_packages_extend_but_never_shrink(monkeypatch):
    monkeypatch.setenv("PHONE_PROTECTED_PKGS", "org.example.keep")
    assert guard.explain_shell("am force-stop org.example.keep")
    assert guard.explain_shell("am force-stop app.dash.mobile")
    monkeypatch.setenv("PHONE_PROTECTED_PKGS", "")
    assert guard.explain_shell("am force-stop app.dash.mobile")


@pytest.mark.parametrize("argv,blocked", [
    (["adb", "install", "a.apk"], True),
    (["adb", "-s", "X", "install", "-r", "a.apk"], True),
    (["/opt/sdk/platform-tools/adb", "uninstall", "com.example.app"], True),
    (["adb", "pair", "host:1234"], True),
    (["adb", "shell", "pm", "install", "a.apk"], True),
    (["adb", "-s", "X", "shell", "settings", "put", "global", "a", "1"], True),
    (["adb", "exec-out", "ime", "set", "x"], True),
    (["adb", "reboot"], True),
    (["adb", "devices", "-l"], False),
    (["adb", "mdns", "services"], False),
    (["adb", "connect", "host:1234"], False),
    (["adb", "-s", "X", "shell", "getprop", "ro.serialno"], False),
    (["adb", "-P", "1", "shell", "cmd package resolve-activity --brief"], False),
    (["ls", "-l"], False),
    (["adb", "abb", "package", "install-create"], True),
    (["adb", "kill-server"], True),
    (["adb", "-s", "X", "abb_exec", "input_method", "set", "x"], True),
])
def test_adb_argv_policy(argv, blocked):
    assert bool(guard.explain_adb_argv(argv)) is blocked


@pytest.mark.parametrize("argv,blocked", [
    (["bash", "-c", "adb install a.apk"], True),
    (["/bin/sh", "-lc", "cd /x && ~/sdk/platform-tools/adb -s X uninstall com.example.app"], True),
    (["timeout", "5", "adb", "install", "a.apk"], True),
    (["env", "A=1", "nice", "-n", "5", "/opt/sdk/platform-tools/adb", "shell", "ime", "set", "x"], True),
    (["flock", "-w", "120", "/tmp/s22-ui.lock", "-c", "adb shell settings put global a 1"], True),
    (["flock", "/tmp/s22-ui.lock", "adb", "shell", "getprop", "ro.serialno"], False),
    (["bash", "-c", "adb devices -l"], False),
    (["git", "commit", "-m", "adb install docs"], False),       # not a command runner
    (["grep", "-r", "adb", "install"], False),
])
def test_subprocess_argv_through_shells_and_wrappers(argv, blocked):
    if blocked:
        with pytest.raises(PhoneGuardError):
            guard._check_popen(argv, False)
    else:
        guard._check_popen(argv, False)


@pytest.mark.parametrize("svc,blocked", [
    ("shell:pm install /sdcard/a.apk", True),
    ("shell,v2:/system/bin/ime set com.example/.K", True),
    ("shell,v2,raw:settings put global a 1", True),
    ("exec:cmd package install -S 123", True),
    ("abb_exec:package\0install-create", True),
    ("abb:input_method\0set\0x", True),
    ("reboot:", True),
    ("root:", True),
    ("tcpip:5555", True),
    ("host:pair:123456:host", True),
    ("host:kill", True),
    ("shell:getprop ro.serialno", False),
    ("shell,v2:dumpsys power", False),
    ("host:devices-l", False),
    ("host:tport:serial:X", False),
    ("sync:", False),
    ("tcp:9008", False),
])
def test_wire_protocol_service_policy(svc, blocked):
    assert bool(guard.explain_service(svc)) is blocked, svc


def test_subprocess_and_os_system_are_guarded(tmp_path):
    guard.install(eager=False)
    with pytest.raises(PhoneGuardError):
        subprocess.Popen(["adb", "install", "a.apk"])
    with pytest.raises(PhoneGuardError):
        subprocess.run("adb shell pm install a.apk", shell=True)
    with pytest.raises(PhoneGuardError):
        os.system("adb uninstall com.example.app")
    # an unrelated command still runs
    assert subprocess.run([sys.executable, "-c", "print(1)"], capture_output=True).returncode == 0


def test_selftest_passes_everywhere_it_can_run():
    results = guard.selftest()
    failed = [r for r in results if not r[1]]
    assert not failed, failed
    try:
        import uiautomator2  # noqa: F401
        floor = 45
    except ImportError:
        floor = 30      # the policy checks run without the libraries
    assert len(results) >= floor


def test_import_phone_activates_the_guard():
    assert phone.PhoneGuardError is guard.PhoneGuardError
    st = guard.status()
    assert st["popen"] is True
    assert guard.PhoneGuardError is sys._phone_guard_state["exc"]


def test_install_is_idempotent():
    first = guard.status()["patched"]
    guard.install(eager=True)
    guard.install(eager=True)
    assert guard.status()["patched"] == first


def _bare(cls):
    return object.__new__(cls)


@pytest.mark.parametrize("call", [
    lambda d: d.send_keys("x"),
    lambda d: d._setup_ime(),
    lambda d: d.set_input_ime(True),
    lambda d: d.set_fastinput_ime(True),
    lambda d: d.clipboard,
    lambda d: setattr(d, "clipboard", "x"),
    lambda d: d.set_clipboard("x"),
    lambda d: d.app_install("a.apk"),
    lambda d: d.app_uninstall("com.example.app"),
    lambda d: d.app_uninstall_all(),
    lambda d: d.app_stop_all(),
    lambda d: d.app_auto_grant_permissions("com.example.app"),
    lambda d: d.shell(["pm", "install", "a.apk"]),
    lambda d: d.shell("ime set com.example/.K"),
    lambda d: d.shell("settings put global a 1"),
    lambda d: d.hide_keyboard(),
    lambda d: d.send_action("search"),
])
def test_uiautomator2_device_is_guarded(call):
    u2 = pytest.importorskip("uiautomator2")
    d = _bare(u2.Device)
    with pytest.raises(PhoneGuardError):
        call(d)


def test_uiautomator2_clipboard_rpc_is_guarded():
    u2 = pytest.importorskip("uiautomator2")
    d = _bare(u2.Device)
    for method in ("setClipboard", "getClipboard", "pasteClipboard"):
        with pytest.raises(PhoneGuardError):
            u2.Device.jsonrpc_call(d, method, ["a", "b"])


def test_uiautomator2_rotation_and_raw_rpc_are_guarded():
    u2 = pytest.importorskip("uiautomator2")
    import uiautomator2.core as core
    d = _bare(u2.Device)
    for call in (lambda: d.freeze_rotation(True), lambda: d.set_orientation("left"),
                 lambda: u2.Device.jsonrpc_call(d, "setOrientation", ["left"]),
                 lambda: u2.Device.jsonrpc_call(d, "freezeRotation", [True])):
        with pytest.raises(PhoneGuardError):
            call()
    # the module-level helper under jsonrpc_call cannot reach these RPCs either
    for method in ("setClipboard", "getClipboard", "freezeRotation"):
        with pytest.raises(PhoneGuardError):
            core._jsonrpc_call(None, 0, method, ["a"], 1, False)


def test_adbutils_wire_level_shell_cannot_skip_the_policy():
    adbutils = pytest.importorskip("adbutils")
    from adbutils._adb import AdbConnection
    sent = []

    class Conn:
        def send_command(self, cmd):
            sent.append(cmd)

        def check_okay(self):
            raise EOFError("test transport")

        def close(self):
            pass

    conn = _bare(AdbConnection)
    for cmd in ("shell:pm install /sdcard/a.apk", "shell,v2:ime set x/.K", "exec:cmd package install",
                "abb_exec:package\0install"):
        with pytest.raises(PhoneGuardError):
            conn.send_command(cmd)
    dev = _bare(adbutils.AdbDevice)
    with pytest.raises(PhoneGuardError):
        dev._shell_v2("pm install /sdcard/a.apk")
    dev.open_transport = lambda *a, **k: Conn()
    with pytest.raises(EOFError):                       # a read-only command still goes through
        dev._shell_v2("getprop ro.serialno")
    assert sent == ["shell,v2:getprop ro.serialno"]


def test_a_newer_guard_wraps_an_older_copys_checks():
    class Dev:
        def shell(self, cmd):
            return "ran"
    inner = Dev.shell

    def older(self, cmd):            # what guard version 1 left behind: a weaker check
        return inner(self, cmd)
    older.__phone_guard__ = True
    Dev.shell = older
    guard._guard_shell_method(Dev, "shell")
    with pytest.raises(PhoneGuardError):
        Dev().shell("/system/bin/pm install a.apk")
    assert Dev().shell("getprop x") == "ran"
    guard._guard_shell_method(Dev, "shell")             # idempotent for the current version
    assert Dev.shell.__wrapped__ is older


def test_adbutils_device_is_guarded():
    adbutils = pytest.importorskip("adbutils")
    dev = _bare(adbutils.AdbDevice)
    for call in (lambda: dev.install("a.apk"), lambda: dev.install_remote("/sdcard/a.apk"),
                 lambda: dev.uninstall("com.example.app"),
                 lambda: dev.shell(["pm", "install", "x"]), lambda: dev.shell2("settings put a b 1"),
                 lambda: dev.switch_airplane(True)):
        with pytest.raises(PhoneGuardError):
            call()


def test_type_text_uses_set_text_only():
    import ast
    import textwrap as tw
    tree = ast.parse(tw.dedent(inspect.getsource(phone.Phone.type_text)))
    fn = tree.body[0]
    body = fn.body[1:] if ast.get_docstring(fn) else fn.body   # skip the docstring
    names = set()
    for stmt in body:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Attribute):
                names.add(node.attr)
            elif isinstance(node, ast.Name):
                names.add(node.id)
    assert "set_text" in names
    banned = {"send_keys", "clipboard", "set_clipboard", "set_input_ime", "set_fastinput_ime",
              "send_action", "_setup_ime", "shell"}
    assert not (names & banned), names & banned


# --- sitecustomize installer ---------------------------------------------------------------------


def run_installer(*args, env=None):
    return subprocess.run(["bash", str(INSTALLER), *args], capture_output=True, text=True,
                          env={**os.environ, **(env or {})})


def test_installer_dry_run_writes_nothing(tmp_path):
    r = run_installer("--target-dir", str(tmp_path))
    assert r.returncode == 0, r.stderr
    assert "DRY RUN" in r.stdout
    assert list(tmp_path.iterdir()) == []


def test_installer_status_does_not_write(tmp_path):
    r = run_installer("--status", "--target-dir", str(tmp_path))
    assert r.returncode == 0 and "[absent]" in r.stdout and list(tmp_path.iterdir()) == []


def test_installer_apply_then_hook_blocks_raw_scripts(tmp_path):
    r = run_installer("--apply", "--target-dir", str(tmp_path))
    assert r.returncode == 0, r.stderr + r.stdout
    assert (tmp_path / "_phone_guard.py").read_text() == (SKILL / "phone" / "guard.py").read_text()
    assert (tmp_path / "sitecustomize.py").read_text().startswith("# phone-guard-sitecustomize")
    again = run_installer("--apply", "--target-dir", str(tmp_path))
    assert "already current" in again.stdout
    # A raw script that never imports `phone`: the hook alone must block installs.
    script = textwrap.dedent("""
        import sys
        assert hasattr(sys, "_phone_guard_state"), "guard hook not loaded"
        import adbutils
        dev = object.__new__(adbutils.AdbDevice)
        try:
            dev.install("a.apk")
        except Exception as e:
            print(type(e).__name__)
        else:
            print("NOT BLOCKED")
    """)
    adbutils_present = subprocess.run([sys.executable, "-c", "import adbutils"],
                                      capture_output=True).returncode == 0
    env = {**os.environ, "PYTHONPATH": str(tmp_path)}
    if adbutils_present:
        out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env=env)
        assert out.stdout.strip() == "PhoneGuardError", out.stdout + out.stderr
    st = subprocess.run([sys.executable, "-c",
                         "import sys; print(hasattr(sys,'_phone_guard_state'))"],
                        capture_output=True, text=True, env=env)
    assert st.stdout.strip() == "True", st.stderr
    # the installed copy passes its own policy self-test
    st = subprocess.run([sys.executable, "-m", "_phone_guard", "selftest"], capture_output=True,
                        text=True, env=env)
    assert st.returncode == 0, st.stdout + st.stderr


def test_installer_foreign_sitecustomize_needs_force_and_is_chained(tmp_path):
    (tmp_path / "sitecustomize.py").write_text("import builtins; builtins.FOREIGN_RAN = True\n")
    skipped = run_installer("--apply", "--target-dir", str(tmp_path))
    assert "SKIP" in skipped.stdout
    assert not (tmp_path / "_phone_guard.py").exists()
    forced = run_installer("--apply", "--force", "--target-dir", str(tmp_path))
    assert forced.returncode == 0, forced.stderr
    assert (tmp_path / "sitecustomize.py.phoneguard-orig").exists()
    env = {**os.environ, "PYTHONPATH": str(tmp_path)}
    out = subprocess.run([sys.executable, "-c",
                          "import builtins, sys; print(getattr(builtins,'FOREIGN_RAN',False), "
                          "hasattr(sys,'_phone_guard_state'))"],
                         capture_output=True, text=True, env=env)
    assert out.stdout.strip() == "True True", out.stdout + out.stderr


def test_installer_uninstall_restores(tmp_path):
    (tmp_path / "sitecustomize.py").write_text("X = 1\n")
    run_installer("--apply", "--force", "--target-dir", str(tmp_path))
    gone = run_installer("--apply", "--uninstall", "--target-dir", str(tmp_path))
    assert gone.returncode == 0, gone.stderr
    assert (tmp_path / "sitecustomize.py").read_text() == "X = 1\n"
    assert not (tmp_path / "_phone_guard.py").exists()


def test_installer_never_touches_unwritable_dir_without_sudo(tmp_path):
    ro = tmp_path / "ro"
    ro.mkdir()
    ro.chmod(0o555)
    try:
        if os.access(ro, os.W_OK):
            pytest.skip("running as a user that can write read-only dirs")
        r = run_installer("--apply", "--target-dir", str(ro))
        assert r.returncode != 0 and "--sudo" in r.stderr
    finally:
        ro.chmod(0o755)
