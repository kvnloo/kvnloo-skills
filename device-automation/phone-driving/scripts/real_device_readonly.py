#!/usr/bin/env python3
"""Real-device checks that only READ, plus an optional ChatGPT preflight that never sends.

    scripts/phone-run python scripts/real_device_readonly.py --role s22
    scripts/phone-run python scripts/real_device_readonly.py --role s22 --preflight-only

Default mode changes nothing on the phone: it does not open, tap, type or scroll. It proves the guard,
the lock proof, discovery, the instrumentation, the owner-activity check, the redacted screen readers
and the receipts. `--with-scroll` additionally runs a 3-step read_long (scroll gestures, no taps).

`--preflight-only` runs only the ChatGPT preflight: fresh composer, readiness text typed with
set_text, an enabled Send control detected, the exact text cleared, composer restored. It NEVER taps
Send and claims nothing. It does open ChatGPT (agent-open ledger) and returns the phone to its home
screen at the end. The s25 is the owner's daily phone: this script refuses it unless the owner enabled
that role with PHONE_ALLOW_ROLES.

Exit code 0 when nothing failed (skips for a busy owner are not failures), 1 otherwise. Nothing
secret is printed: no serials, no addresses, no screen content.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import phone  # noqa: E402  (imports activate the guard)
from phone import activity, adb as adbmod, config, guard, lock as lockmod, receipts  # noqa: E402
from phone import redact  # noqa: E402
from phone.errors import OwnerBusy, RedactorUnavailable  # noqa: E402

RESULTS: list[dict] = []


def check(name, status, detail=""):
    RESULTS.append({"check": name, "status": status, "detail": str(detail)[:300]})
    mark = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP", "warn": "WARN"}[status]
    print(f"{mark} {name}" + (f"  ({str(detail)[:200]})" if detail else ""), flush=True)


def guarded(name, fn):
    try:
        out = fn()
        check(name, "pass", out if isinstance(out, str) else "")
        return out
    except Exception as e:  # noqa: BLE001
        check(name, "fail", f"{type(e).__name__}: {e}")
        return None


def run_readonly(role: str, with_scroll: bool) -> None:
    results = guard.selftest()
    bad = [n for n, ok, _d in results if not ok]
    check("guard selftest", "fail" if bad else "pass", f"{len(results) - len(bad)}/{len(results)}"
          + (f"; failed: {bad[:3]}" if bad else ""))
    try:
        config.require_role_allowed(role)
        hw = config.role_hardware(role)
        check("role configured and allowed", "pass", f"model={hw['model'] or 'unknown'}")
    except Exception as e:  # noqa: BLE001
        check("role configured and allowed", "fail", f"{type(e).__name__}: {e}")
        return
    t = guarded("adb discovery with identity proof", lambda: f"kind={adbmod.discover(role).kind}")
    if t is None:
        return
    before = lockmod.lock_status(role)["host"]
    check("lock free before session", "pass" if not before["held"] else "warn",
          "held by another process" if before["held"] else "")
    try:
        ph = phone.Phone(role, lock_wait=180)
        ph.__enter__()
    except OwnerBusy as e:
        # connect() checks the owner over adb before uiautomator starts: nothing was touched.
        check("take lock and connect", "skip", f"owner busy before uiautomator started: {e}")
        return
    except Exception as e:  # noqa: BLE001
        check("take lock and connect", "fail", f"{type(e).__name__}: {e}")
        return
    try:
        check("take lock and connect", "pass")
        during = lockmod.lock_status(role)["host"]
        check("lock held by this session (/proc/locks proof)",
              "pass" if any(h["is_ancestor"] for h in during["holders"]) else "fail")
        guarded("require_ui_lock proof", lambda: lockmod.require_ui_lock(role) or "")
        guarded("hierarchy RPC healthy", lambda: ph.healthy() or "")
        guarded("activity snapshot parses", lambda: ph.snapshot() and "ok")
        busy = ph.owner_busy()
        if busy:
            check("owner idle", "skip", busy)
            for name in ("screen_text", "nodes", "screenshot", "read_long"):
                check(name, "skip", "owner busy; nothing touched")
        else:
            check("owner idle", "pass")
            run_screen_checks(ph, with_scroll)
        run_guard_on_live_device(ph)
        guarded("receipts write and read back", lambda: receipt_roundtrip(role))
    finally:
        ph.close()
    after = lockmod.lock_status(role)["host"]
    check("lock released on exit", "pass" if not any(h["is_ancestor"] for h in after["holders"]) else "fail")


def run_screen_checks(ph, with_scroll: bool) -> None:
    try:
        red = redact.get()
        check("redactor available", "pass" if red.active else "warn",
              "pass-through (PHONE_REDACTION=off)" if not red.active else "")
    except RedactorUnavailable:
        check("redactor available", "warn", "missing: screen readers must fail closed")
        for name in ("screen_text", "nodes", "screenshot", "read_long"):
            try:
                {"screen_text": ph.screen_text, "nodes": ph.nodes,
                 "screenshot": lambda: ph.screenshot(Path(tempfile.gettempdir()) / "x.png"),
                 "read_long": lambda: ph.read_long(max_steps=1)}[name]()
                check(name + " fails closed", "fail", "returned content without a redactor")
            except RedactorUnavailable:
                check(name + " fails closed", "pass")
        return

    def screen_text():
        text = ph.screen_text()
        return f"{len(text.splitlines())} lines, redaction_marker={ph.last_redaction}"
    guarded("screen_text (redacted)", screen_text)

    def nodes():
        n = ph.nodes()
        labelled = [x for x in n if x.text or x.desc]
        return f"{len(n)} nodes, {len(labelled)} labelled"
    guarded("nodes (redacted)", nodes)

    def shot():
        with tempfile.TemporaryDirectory(prefix="phone-shot-") as tmp:
            res = ph.screenshot(Path(tmp) / "shot.png")
            data = Path(res["path"]).read_bytes()
            if data[:8] != b"\x89PNG\r\n\x1a\n":
                raise AssertionError("not a PNG")
            return f"png {len(data)} bytes, redactor_code={res['redactor_code']}"
    guarded("screenshot (redacted, temp dir)", shot)

    if with_scroll:
        def long():
            res = ph.read_long(max_steps=3)
            return f"{len(res.lines)} lines in {res.steps} steps, complete={res.complete}"
        guarded("read_long (3 steps)", long)
    else:
        check("read_long", "skip", "pass --with-scroll to run (scroll gestures)")


def run_guard_on_live_device(ph) -> None:
    def blocked(name, fn):
        try:
            fn()
        except phone.PhoneGuardError:
            check(f"live device blocks {name}", "pass")
        except Exception as e:  # noqa: BLE001
            check(f"live device blocks {name}", "fail", f"{type(e).__name__}: {e}")
        else:
            check(f"live device blocks {name}", "fail", "NOT blocked")
    blocked("send_keys", lambda: ph.d.send_keys("x"))
    blocked("clipboard read", lambda: ph.d.clipboard)
    blocked("clipboard write", lambda: setattr(ph.d, "clipboard", "x"))
    blocked("set_input_ime", lambda: ph.d.set_input_ime(True))
    blocked("shell settings put", lambda: ph.d.shell("settings put global x 1"))
    blocked("shell pm install", lambda: ph.d.shell(["pm", "install", "/sdcard/x.apk"]))
    blocked("adb_device.install", lambda: ph.d.adb_device.install("/nonexistent.apk"))
    blocked("adb_device.uninstall", lambda: ph.d.adb_device.uninstall("com.example.nothing"))


def receipt_roundtrip(role: str) -> str:
    with tempfile.TemporaryDirectory(prefix="phone-rcpt-") as tmp:
        path = Path(tmp) / "r.jsonl"
        receipts.write({"role": role, "action": "selfcheck", "status": "ok",
                        **receipts.text_digest("not stored")}, path)
        rows = receipts.read(path)
        assert rows and rows[-1]["action"] == "selfcheck" and "not stored" not in path.read_text()
    return "ok"


def run_preflight(role: str) -> None:
    from phone.dispatch import dispatch_one
    adapter = phone.adapters.get("chatgpt")
    tag = f"PREFLIGHT-{int(time.time()) % 100000:05d}"
    text = f"phone (tag {tag}). Readiness check, never sent."
    # One lock hold for the whole check: the nested sessions inherit it, so no other driver can
    # slip in between the preflight and the verification.
    try:
        outer = lockmod.UILock(role, wait=180).__enter__()
    except Exception as e:  # noqa: BLE001
        check("chatgpt preflight", "skip", f"{type(e).__name__}: {e}")
        return
    try:
        row = dispatch_one(adapter, role, tag, text, preflight=True, lock_wait=180)
        status = row.get("status")
        check("chatgpt preflight", "pass" if status == "preflight_ready" else
              ("skip" if status in ("owner_busy", "quota_paused", "lock_busy") else "fail"),
              f"status={status} send_attempted={row.get('send_attempted')} "
              f"{row.get('error', '')}".strip())
        check("preflight never sends", "fail" if row.get("send_attempted") else "pass")
        if status != "preflight_ready":
            return
        try:
            with phone.Phone(role, lock_wait=180, exempt_pkgs={adapter.package}) as ph:
                box = ph.d(packageName=adapter.package, className="android.widget.EditText")
                empty = (not box.exists) or not (box.get_text() or "").strip()
                check("composer left empty", "pass" if empty else "fail")
                ph.restore(adapter)
                home = activity.home_packages(ph.serial)
                fg = ph.snapshot()["package"]
                check("restored to home screen", "pass" if fg in home else "fail",
                      "" if fg in home else "foreground differs")
        except (OwnerBusy, phone.WrongForeground) as e:
            check("restore to home", "skip", f"{type(e).__name__}: left untouched")
        except Exception as e:  # noqa: BLE001
            check("restore to home", "fail", f"{type(e).__name__}: {e}")
    finally:
        outer.release()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--role", required=True, choices=config.ROLES)
    ap.add_argument("--with-scroll", action="store_true")
    ap.add_argument("--preflight-only", action="store_true",
                    help="only the ChatGPT preflight (opens ChatGPT; never sends)")
    args = ap.parse_args(argv)
    if args.preflight_only:
        results = guard.selftest()
        bad = [n for n, ok, _d in results if not ok]
        check("guard selftest", "fail" if bad else "pass", f"{len(results) - len(bad)}/{len(results)}")
        if not bad:
            run_preflight(args.role)
    else:
        run_readonly(args.role, args.with_scroll)
    failed = [r for r in RESULTS if r["status"] == "fail"]
    print(json.dumps({"role": args.role, "passed": sum(r["status"] == "pass" for r in RESULTS),
                      "failed": len(failed), "skipped": sum(r["status"] == "skip" for r in RESULTS),
                      "warnings": sum(r["status"] == "warn" for r in RESULTS)}))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
