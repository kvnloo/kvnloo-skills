"""phone: the command line for agents. Use it instead of writing raw uiautomator2 code.

Every command that touches a phone takes the host UI lock itself (or proves an ancestor holds it),
checks that the owner is not using the phone, and returns redacted content. Output is one JSON object
per command, except `text` and `read-long`, which print the text (use --json to wrap it).

Exit codes: 0 ok, 1 failed, 2 usage, 3 refused (owner busy, lock busy, quota, cooldown, claimed, role
not allowed, guard, redactor or calibration missing).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import adapters, adb as adbmod, config, guard, lock as lockmod, receipts
from .device import Phone
from .errors import PhoneError, PhoneGuardError

EXIT_OK, EXIT_FAILED, EXIT_USAGE, EXIT_REFUSED = 0, 1, 2, 3
REFUSAL_CLASSES = ("OwnerBusy", "LockError", "RoleNotAllowed", "RedactorUnavailable",
                   "CalibrationRequired", "WrongForeground", "DeviceLocked", "SensitiveTarget",
                   "DeviceNotConfigured", "PhoneGuardError", "ComposerDraftPreserved")


def emit(obj: dict) -> None:
    print(json.dumps(obj, default=str))


def selector_args(p: argparse.ArgumentParser, prefix: str = "") -> None:
    g = p.add_argument_group("selector")
    g.add_argument(f"--{prefix}text", dest=f"{prefix}text")
    g.add_argument(f"--{prefix}text-contains", dest=f"{prefix}text_contains")
    g.add_argument(f"--{prefix}desc", dest=f"{prefix}desc")
    g.add_argument(f"--{prefix}desc-contains", dest=f"{prefix}desc_contains")
    g.add_argument(f"--{prefix}id", dest=f"{prefix}res_id", help="resource-id")


def selector_from(args, prefix: str = "") -> dict:
    keys = ("text", "text_contains", "desc", "desc_contains", "res_id")
    return {k: getattr(args, f"{prefix}{k}") for k in keys if getattr(args, f"{prefix}{k}", None)}


def add_role(p: argparse.ArgumentParser, required: bool = True) -> None:
    p.add_argument("--role", choices=config.ROLES, required=required,
                   help="which phone (the s22 is the worker phone)")
    p.add_argument("--lock-wait", type=float, default=120.0,
                   help="seconds to wait for the host UI lock")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="phone", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("devices", help="roles, configured?, visible transports (no serials by default)")
    p.add_argument("--role", choices=config.ROLES)
    p.add_argument("--probe", action="store_true",
                   help="prove the role's identity through adb (needs --role; touches that phone)")
    p.add_argument("--show-serial", action="store_true")

    p = sub.add_parser("lock-status", help="who holds the host UI lock, quota pause, receipts path")
    p.add_argument("--role", choices=config.ROLES)

    p = sub.add_parser("open", help="open an app (owner check, agent-open ledger)")
    add_role(p)
    p.add_argument("pkg")

    p = sub.add_parser("tap", help="tap by label or selector, never by coordinates")
    add_role(p)
    p.add_argument("label", nargs="?", help="text or description; exact match preferred")
    p.add_argument("--pkg", help="assert the foreground package")
    selector_args(p)

    p = sub.add_parser("type", help="set_text into the focused field (never IME, clipboard, send_keys)")
    add_role(p)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--value", help="text to type (visible in the process list; prefer --file/--stdin)")
    g.add_argument("--file")
    g.add_argument("--stdin", action="store_true")
    selector_args(p)

    p = sub.add_parser("text", help="screen text, or one node's text with a selector (redacted)")
    add_role(p)
    p.add_argument("--pkg", help="assert the foreground package and keep only its text")
    p.add_argument("--json", action="store_true")
    selector_args(p)

    p = sub.add_parser("read-long", help="scroll a container and stitch its text (redacted)")
    add_role(p)
    p.add_argument("--max-steps", type=int, default=30)
    p.add_argument("--from-top", action="store_true")
    p.add_argument("--json", action="store_true")
    selector_args(p, "container-")

    p = sub.add_parser("nodes", help="labelled nodes with tap centres (redacted), for calibration")
    add_role(p)
    p.add_argument("--pkg", help="assert the foreground package and keep only its nodes")

    p = sub.add_parser("ocr", help="text read by OCR from a redacted screenshot (fallback)")
    add_role(p)

    p = sub.add_parser("shot", help="redacted screenshot")
    add_role(p)
    p.add_argument("out")

    for name, helptext in (("home", "press HOME"), ("back", "press BACK")):
        p = sub.add_parser(name, help=helptext)
        add_role(p)

    p = sub.add_parser("scroll")
    add_role(p)
    p.add_argument("direction", choices=("up", "down", "left", "right"))

    p = sub.add_parser("restore", help="leave the phone tidy: app fresh screen, then home")
    add_role(p)
    p.add_argument("--adapter", choices=adapters.names())

    p = sub.add_parser("chat", help="app adapter operations: chat ADAPTER send|read|state")
    p.add_argument("adapter", choices=adapters.names())
    csub = p.add_subparsers(dest="chat_cmd", required=True)
    for action in ("send", "read", "state"):
        c = csub.add_parser(action)
        add_role(c)
        if action == "send":
            c.add_argument("--tag", required=True)
            g = c.add_mutually_exclusive_group(required=True)
            g.add_argument("--value")
            g.add_argument("--file")
            g.add_argument("--stdin", action="store_true")
            c.add_argument("--effort")
            c.add_argument("--preflight-only", action="store_true",
                           help="prove readiness; never taps Send, claims nothing")
            c.add_argument("--i-mean-it", action="store_true",
                           help="required for a real send: this posts a message")
        if action == "read":
            c.add_argument("--long", action="store_true", help="scroll and stitch the whole page")
            c.add_argument("--from-top", action="store_true", help="with --long: start at the top")
            c.add_argument("--title", help="open the chat with this exact title first (by search)")

    sub.add_parser("selftest", help="prove the install/IME/settings guard is active")

    p = sub.add_parser("receipts", help="recent receipts")
    p.add_argument("--limit", type=int, default=10)
    return ap


def read_value(args) -> str:
    if getattr(args, "stdin", False):
        return sys.stdin.read()
    if getattr(args, "file", None):
        return Path(args.file).read_text()
    return args.value


# command handlers -----------------------------------------------------------------------------

def cmd_devices(args):
    rows = adbmod.visible_roles()
    if args.role:
        rows = [r for r in rows if r["role"] == args.role]
    if args.probe:
        if not args.role:
            raise SystemExit("--probe needs --role")
        config.require_role_allowed(args.role)
        t = adbmod.discover(args.role)
        for r in rows:
            r["identity_proven"] = True
            r["connected_via"] = t.kind
            if args.show_serial:
                r["serial"] = t.serial
    return {"ok": True, "guard": guard.status()["version"], "roles": rows}


def cmd_lock_status(args):
    from .quota import QuotaPause
    roles = [args.role] if args.role else list(config.ROLES)
    out = {"ok": True, "roles": {r: lockmod.lock_status(r) for r in roles},
           "quota": {a: QuotaPause(a).status() for a in adapters.names()},
           "receipts": str(config.receipts_path())}
    return out


def cmd_open(args):
    with Phone(args.role, lock_wait=args.lock_wait) as ph:
        ph.open_app(args.pkg)
        return {"ok": True, "opened": args.pkg}


def cmd_tap(args):
    sel = selector_from(args)
    if not args.label and not sel:
        raise SystemExit("tap needs a label or a selector")
    with Phone(args.role, lock_wait=args.lock_wait) as ph:
        rec = ph.tap(args.label, pkg=args.pkg, **sel)
        return {"ok": True, "tapped": args.label or sel, "at": rec.get("at_xy")}


def cmd_type(args):
    value = read_value(args)
    with Phone(args.role, lock_wait=args.lock_wait) as ph:
        res = ph.type_text(value, **selector_from(args))
        return {"ok": res["verified"], **res}


def cmd_text(args):
    sel = selector_from(args)
    with Phone(args.role, lock_wait=args.lock_wait) as ph:
        text = ph.get_text(**sel) if sel else ph.screen_text(pkg=args.pkg)
        if args.json:
            return {"ok": True, "text": text, "redaction": ph.last_redaction}
        sys.stdout.write(text + ("\n" if not text.endswith("\n") else ""))
        return None


def cmd_read_long(args):
    container = selector_from(args, "container_") or None
    with Phone(args.role, lock_wait=args.lock_wait) as ph:
        res = ph.read_long(container, max_steps=args.max_steps, start_at_top=args.from_top)
        if args.json:
            return {"ok": res.complete, "text": res.text, "steps": res.steps,
                    "complete": res.complete, "reason": res.reason, "gaps": res.gaps,
                    "sticky": res.sticky}
        sys.stdout.write(res.text + "\n")
        sys.stderr.write(json.dumps({"steps": res.steps, "complete": res.complete,
                                     "reason": res.reason, "gaps": res.gaps,
                                     "sticky_lines": len(res.sticky or [])}) + "\n")
        return None


def cmd_nodes(args):
    with Phone(args.role, lock_wait=args.lock_wait) as ph:
        ph.precheck(pkg=args.pkg, allow_home=args.pkg is None)
        rows = []
        for n in ph.nodes(pkg=args.pkg):
            if n.text or n.desc:
                rows.append({"xy": list(n.center), "clickable": n.clickable, "text": n.text[:70],
                             "desc": n.desc[:60], "id": n.res_id, "cls": n.cls.rsplit(".", 1)[-1],
                             "pkg": n.pkg})
        return {"ok": True, "redaction": ph.last_redaction, "nodes": rows}


def cmd_ocr(args):
    with Phone(args.role, lock_wait=args.lock_wait) as ph:
        sys.stdout.write(ph.ocr_text())
        return None


def cmd_shot(args):
    with Phone(args.role, lock_wait=args.lock_wait) as ph:
        return {"ok": True, **ph.screenshot(Path(args.out))}


def cmd_home(args):
    with Phone(args.role, lock_wait=args.lock_wait) as ph:
        ph.home()
        return {"ok": True}


def cmd_back(args):
    with Phone(args.role, lock_wait=args.lock_wait) as ph:
        ph.back()
        return {"ok": True}


def cmd_scroll(args):
    with Phone(args.role, lock_wait=args.lock_wait) as ph:
        ph.precheck()
        ph.scroll(args.direction)
        return {"ok": True}


def cmd_restore(args):
    adapter = adapters.get(args.adapter) if args.adapter else None
    with Phone(args.role, lock_wait=args.lock_wait) as ph:
        rec = ph.restore(adapter)
        return {"ok": True, "adapter_restore_error": rec.get("adapter_restore_error")}


def cmd_chat(args):
    adapter = adapters.get(args.adapter)
    if args.chat_cmd == "send":
        from .dispatch import dispatch_one
        if not args.preflight_only and not args.i_mean_it:
            raise SystemExit("a real send posts a message: pass --i-mean-it (or --preflight-only)")
        row = dispatch_one(adapter, args.role, args.tag, read_value(args),
                           effort=args.effort, preflight=args.preflight_only,
                           lock_wait=args.lock_wait)
        row["ok"] = row["status"] in ("sent", "preflight_ready")
        return row
    with Phone(args.role, lock_wait=args.lock_wait, exempt_pkgs={adapter.package}) as ph:
        ph.precheck(pkg=adapter.package if not getattr(args, "title", None) else None,
                    allow_home=bool(getattr(args, "title", None)))
        if args.chat_cmd == "state":
            return {"ok": True, **adapter.state(ph)}
        return {"ok": True, **adapter.read(ph, long=args.long, title=args.title,
                                           from_top=args.from_top)}


def cmd_selftest(_args):
    results = guard.selftest()
    failed = [r for r in results if not r[1]]
    return {"ok": not failed, "passed": len(results) - len(failed), "total": len(results),
            "failed": [{"check": n, "detail": d} for n, ok, d in failed],
            "guard": guard.status()}


def cmd_receipts(args):
    return {"ok": True, "receipts": receipts.read(limit=args.limit)}


HANDLERS = {"devices": cmd_devices, "lock-status": cmd_lock_status, "open": cmd_open,
            "tap": cmd_tap, "type": cmd_type, "text": cmd_text, "read-long": cmd_read_long,
            "nodes": cmd_nodes, "ocr": cmd_ocr, "shot": cmd_shot, "home": cmd_home, "back": cmd_back,
            "scroll": cmd_scroll, "restore": cmd_restore, "chat": cmd_chat,
            "selftest": cmd_selftest, "receipts": cmd_receipts}


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = HANDLERS[args.cmd](args)
    except SystemExit as e:
        if isinstance(e.code, str):
            emit({"ok": False, "error_class": "UsageError", "error": e.code})
            return EXIT_USAGE
        raise
    except (PhoneError, PhoneGuardError, ValueError, LookupError, PermissionError) as e:
        name = type(e).__name__
        emit({"ok": False, "error_class": name, "error": str(e)[:400]})
        return EXIT_REFUSED if name in REFUSAL_CLASSES else EXIT_FAILED
    except Exception as e:  # noqa: BLE001
        emit({"ok": False, "error_class": type(e).__name__, "error": str(e)[:400]})
        return EXIT_FAILED
    if result is None:
        return EXIT_OK
    emit(result)
    status = result.get("status")
    if status in ("owner_busy", "quota_paused", "cooling_down", "already_claimed", "lock_busy"):
        return EXIT_REFUSED
    return EXIT_OK if result.get("ok", True) else EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
