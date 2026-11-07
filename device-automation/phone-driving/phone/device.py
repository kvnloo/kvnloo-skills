"""Phone: one locked, owner-checked, redacting session on one phone.

    from phone import Phone
    with Phone("s22") as ph:                     # takes the host UI lock, discovers, connects
        ph.open_app("com.example.app")           # owner check, agent-open ledger, wake, launch
        ph.tap(text="New chat")
        ph.type_text("hello")                    # set_text only; never IME, clipboard or send_keys
        print(ph.screen_text())                  # redacted
        ph.restore()                             # back to the home screen

Every screen read and every input first proves the owner is not using the phone and that the
foreground is an app an agent opened. Content returned to callers is redacted. Typed text is
never logged: receipts carry only a length and a short hash.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
import time
from contextlib import contextmanager

from pathlib import Path

from . import activity, adb as adbmod, config, hierarchy, lock as lockmod, receipts, redact
from .errors import (DeviceLocked, GenerationTimeout, OwnerBusy, RedactorUnavailable, RestoreError,
                     SensitiveTarget, WrongForeground)

SEL_MAP = {
    "text": "text", "text_contains": "textContains", "text_starts": "textStartsWith",
    "desc": "description", "desc_contains": "descriptionContains",
    "desc_starts": "descriptionStartsWith", "res_id": "resourceId", "cls": "className",
    "pkg": "packageName", "focused": "focused", "clickable": "clickable", "enabled": "enabled",
    "instance": "instance",
}
SYSTEM_PKGS = frozenset({"com.android.systemui"})
RECOVERABLE_WORDS = ("remotedisconnected", "nullpointerexception", "sharedmemory",
                     "connection aborted", "connection reset", "uiautomation not connected")


def u2_selector(**kw) -> dict:
    """Map phone selector names to uiautomator2 keyword arguments, rejecting unknown names."""
    unknown = set(kw) - set(SEL_MAP)
    if unknown:
        raise ValueError(f"unknown selector keys {sorted(unknown)}; use {sorted(SEL_MAP)}")
    return {SEL_MAP[k]: v for k, v in kw.items() if v is not None}


def wait_for(pred, timeout: float, step: float = 0.15) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(step)
    return False


def recoverable(error: BaseException) -> bool:
    detail = f"{type(error).__name__}: {error}".lower()
    return any(word in detail for word in RECOVERABLE_WORDS)


class Phone:
    def __init__(self, role: str, *, lock: bool = True, lock_wait: float = 120.0,
                 exempt_pkgs=(), audit: bool = True, serial: str | None = None):
        config.require_role_allowed(role)
        self.role = role
        self.use_lock = lock
        self.lock_wait = lock_wait
        self.driving: set[str] = set(exempt_pkgs)
        self.audit = audit
        self._serial_override = serial
        self.transport = None
        self.d = None
        self._lock: lockmod.UILock | None = None
        self.last_redaction: str | None = None

    # lifecycle -------------------------------------------------------------------------------

    def __enter__(self):
        try:
            if self.use_lock:
                self._lock = lockmod.UILock(self.role, wait=self.lock_wait).__enter__()
            self.connect()
        except BaseException:
            self.close()
            raise
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def close(self):
        if self._lock is not None:
            self._lock.release()
            self._lock = None
        self.d = None

    def connect(self):
        """Prove the lock, discover the transport, check the owner over adb, and only then start
        uiautomator2 and probe the hierarchy RPC. As in the production launcher, a busy owner means
        the instrumentation is never started and their screen is never dumped (raises OwnerBusy).
        An explicit `serial` is used only after proving it is this role's phone."""
        lockmod.require_ui_lock(self.role)
        if self._serial_override:
            self.transport = adbmod.prove(self.role, self._serial_override)
        else:
            self.transport = adbmod.discover(self.role)
        self.require_idle()
        import adbutils
        import uiautomator2 as u2
        client = adbutils.AdbClient(host="localhost", port=int(config.adb_port()))
        self.d = u2.connect(client.device(self.transport.serial))
        self.healthy()
        return self

    @property
    def serial(self) -> str:
        return self.transport.serial

    def device_id(self) -> str:
        return receipts.device_digest(self.transport.serial)

    def require_lock(self):
        lockmod.require_ui_lock(self.role)

    # health and recovery ---------------------------------------------------------------------

    def healthy(self):
        # Probe the hierarchy RPC that navigation needs. deviceInfo initialises WindowManager paths
        # that fail on some phones (ApplicationSharedMemory) while hierarchy RPCs are fine.
        self.d.dump_hierarchy()

    def restart_uiautomator(self):
        """Recover the instrumentation. The server resources already exist: never install,
        reinstall, or change settings."""
        self.d.stop_uiautomator()
        self.d.start_uiautomator()
        self.healthy()

    def run_recoverable(self, fn, attempts: int = 2, info: dict | None = None):
        """Run fn after a health probe; on a recoverable RPC failure restart uiautomator once and
        retry. Only for work that is safe to repeat (never the Send tap itself)."""
        for attempt in range(attempts):
            try:
                self.healthy()
                return fn()
            except Exception as e:  # noqa: BLE001
                if attempt + 1 >= attempts or not recoverable(e):
                    raise
                if info is not None:
                    info["recovery_error"] = f"{type(e).__name__}: {e}"
                    info["restarted"] = True
                self.restart_uiautomator()

    def _retry_read(self, fn):
        """Run an idempotent read; on a recoverable RPC failure restart uiautomator once and retry."""
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            if not recoverable(e):
                raise
            self.restart_uiautomator()
            return fn()

    # owner checks ----------------------------------------------------------------------------

    def snapshot(self) -> dict:
        return activity.activity_snapshot(self.serial)

    def _exempt(self, snap: dict, extra=()) -> set[str]:
        """Packages whose foreground use is the agent's, not the owner's: the ones this session
        drives, the caller's target, and ones an agent opened or drove in the last few minutes
        (activity.AGENT_SESSION_IDLE_MS). An app an agent opened hours ago is NOT exempt: the owner
        may be using it now."""
        return (set(self.driving) | set(extra)
                | activity.agent_opened_packages(self.role, snap["boot_id"], snap["uptime_ms"]))

    def owner_busy(self, extra_exempt=()) -> str | None:
        try:
            snap = self.snapshot()
        except Exception as e:  # noqa: BLE001 - missing evidence means busy, never free
            return f"owner evidence unavailable: {type(e).__name__}: {e}"
        return activity.owner_busy(self.serial, self.role, self._exempt(snap, extra_exempt),
                                   snapshot_fn=lambda _s: snap)

    def require_idle(self, extra_exempt=()):
        reason = self.owner_busy(extra_exempt)
        if reason:
            raise OwnerBusy(reason)

    def precheck(self, *, pkg: str | None = None, allow_home: bool = False) -> dict:
        """Owner check plus foreground check from ONE snapshot. Returns the snapshot.

        Passes only when the owner is not using the phone and the foreground app is the one named
        by `pkg`, or one this session drives or an agent recently opened or drove, or (allow_home) a
        home launcher. A pass refreshes the agent session of the foreground app."""
        self.require_lock()
        try:
            snap = self.snapshot()
        except Exception as e:  # noqa: BLE001 - missing evidence means busy, never free
            raise OwnerBusy(f"owner evidence unavailable: {type(e).__name__}: {e}") from e
        exempt = self._exempt(snap, {pkg} if pkg else ())
        reason = activity.owner_busy(self.serial, self.role, exempt, snapshot_fn=lambda _s: snap)
        if reason:
            raise OwnerBusy(reason)
        fg = snap["package"]
        home = activity.home_packages(self.serial)
        ok = (fg == pkg) if pkg else (fg in exempt or (allow_home and fg in home))
        if not ok:
            raise WrongForeground(
                f"foreground app {fg} was not opened by an agent recently; open it with open_app, "
                "or pass pkg to assert it is the intended target")
        if fg not in home:
            activity.touch_agent_session(self.role, fg, snap)
        return snap

    # audit -----------------------------------------------------------------------------------

    @contextmanager
    def _audited(self, action: str, **fields):
        t0 = time.time()
        rec = {"role": self.role, "action": action, "device": self.device_id()
               if self.transport else None, **fields}
        try:
            yield rec
        except BaseException as e:
            rec.update(status="failed", error_class=type(e).__name__, error=str(e)[:300])
            raise
        else:
            rec.setdefault("status", "ok")
        finally:
            rec["secs"] = round(time.time() - t0, 2)
            if self.audit:
                receipts.write(rec)

    def receipt(self, action: str, status: str, **fields) -> dict:
        return receipts.write({"role": self.role, "action": action, "status": status,
                               "device": self.device_id() if self.transport else None, **fields})

    # app control -----------------------------------------------------------------------------

    def open_app(self, pkg: str) -> dict:
        """Launch an app the way the production launcher does: owner check, snapshot, wake, launch,
        record the agent open, then wait for the app to be in front. A swipe-only cover is dismissed
        only when Android reports it non-blocking; a credential keyguard is never touched."""
        with self._audited("open_app", pkg=pkg):
            self.require_lock()
            self.require_idle(extra_exempt={pkg})
            if "package:" not in self.d.shell(["pm", "path", pkg]).output:
                raise LookupError(f"package {pkg} is not installed on this phone")
            snap = self.snapshot()
            self.d.screen_on()
            self.d.app_start(pkg)
            activity.record_agent_open(self.role, pkg, snap)
            self.driving.add(pkg)
            wait_for(lambda: self.d(packageName=pkg).exists, 4)
            if not self.d(packageName=pkg).exists:
                policy = {line.strip() for line in
                          self.d.shell("dumpsys window policy").output.splitlines()}
                if {"showing=false", "inputRestricted=false"} <= policy:
                    self.d.swipe_ext("up", scale=0.7)
                    wait_for(lambda: self.d(packageName=pkg).exists, 3)
                else:
                    raise DeviceLocked("device locked or obscured; manual unlock required")
            return snap

    def foreground(self) -> str:
        return self.snapshot()["package"]

    def home(self):
        with self._audited("home"):
            self.precheck(allow_home=True)
            self.d.press("home")

    def back(self):
        with self._audited("back"):
            self.precheck()
            self.d.press("back")

    def restore(self, adapter=None) -> dict:
        """Leave the phone as found: the adapter returns its app to a fresh home screen (never
        discarding a draft that is not ours), then the HOME key returns to the launcher."""
        with self._audited("restore", adapter=getattr(adapter, "name", None)) as rec:
            self.precheck(allow_home=True)
            if adapter is not None:
                try:
                    adapter.restore(self)
                except OwnerBusy:
                    raise
                except Exception as e:  # noqa: BLE001
                    rec["adapter_restore_error"] = f"{type(e).__name__}: {e}"[:300]
            self.d.press("home")
            home = activity.home_packages(self.serial)
            if not wait_for(lambda: self.snapshot()["package"] in home, 5, step=0.5):
                raise RestoreError("home launcher did not come to the front")
            return rec

    # selectors and input ---------------------------------------------------------------------

    def find(self, **sel):
        """A uiautomator2 selector built from text/desc/res_id keywords (see SEL_MAP)."""
        mapped = u2_selector(**sel)
        if not mapped:
            raise ValueError("a selector needs at least one of " + ", ".join(sorted(SEL_MAP)))
        return self.d(**mapped)

    def exists(self, **sel) -> bool:
        return bool(self.find(**sel).exists)

    def nodes(self, pkg: str | None = None, include_system: bool = False) -> list:
        """Hierarchy nodes of the current screen, redacted. `pkg` keeps one package's nodes; by
        default the system UI (status bar, navigation) is left out."""
        xml = self._retry_read(lambda: redact.get().hierarchy(self.d))
        self.last_redaction = hierarchy.redacted_marker(xml)
        nodes = hierarchy.parse(xml)
        if pkg:
            return [n for n in nodes if n.pkg == pkg]
        return nodes if include_system else [n for n in nodes if n.pkg not in SYSTEM_PKGS]

    def tap(self, label: str | None = None, *, pkg: str | None = None, timeout: float = 3.0,
            **sel) -> dict:
        """Tap by accessibility label (exact match preferred) or by selector, never by remembered
        coordinates. Refuses unless the foreground is an agent-opened app (or `pkg`)."""
        with self._audited("tap", label=label, selector=sel or None) as rec:
            self.precheck(pkg=pkg)
            if label is not None and not sel:
                raw = hierarchy.parse(self.d.dump_hierarchy())
                node = hierarchy.find_label(raw, label)
                if node is None:
                    raise LookupError(f"no node labelled {label!r}")
                x, y = node.center
                self.d.click(x, y)
                rec["at_xy"] = [x, y]
                return rec
            if not sel:
                raise ValueError("tap needs a label or a selector")
            if not self.find(**sel).click_exists(timeout=timeout):
                raise LookupError(f"no node matches {sel}")
            return rec

    def tap_fraction(self, fx: float, fy: float, *, pkg: str | None = None) -> dict:
        """Tap a position given as fractions of the screen. Only for controls with no label (a
        slider stop); calibrate on the target app, never reuse across apps."""
        with self._audited("tap_fraction", fx=fx, fy=fy) as rec:
            self.precheck(pkg=pkg)
            w, h = self.d.window_size()
            self.d.click(round(fx * w), round(fy * h))
            return rec

    def scroll(self, direction: str = "down", scale: float = 0.7, box: tuple | None = None):
        """Reveal content in `direction` ("down" reveals content below). Wraps the swipe."""
        flip = {"down": "up", "up": "down", "left": "right", "right": "left"}
        if direction not in flip:
            raise ValueError("direction must be up, down, left or right")
        self.d.swipe_ext(flip[direction], scale=scale, box=box)

    def type_text(self, text: str, *, verify: bool = True, **sel) -> dict:
        """Put text into a field with set_text ONLY. Never an IME, the clipboard, or send_keys (the
        guard blocks all three). Targets the focused editable field unless a selector is given.
        Refuses password fields and sensitive apps. Returns {"chars", "verified"} and never the text."""
        with self._audited("type_text", **receipts.text_digest(text)) as rec:
            snap = self.precheck()
            red = redact.get(optional=True)
            if red.sensitive_package(snap["package"]):
                raise SensitiveTarget(f"refusing to type into sensitive app {snap['package']}")
            box = self.find(**sel) if sel else self.d(focused=True, className="android.widget.EditText")
            if not box.exists:
                box = self.d(className="android.widget.EditText")
            if not box.exists:
                raise LookupError("no editable field found")
            try:
                b = box.info["bounds"]
                target = (b["left"], b["top"], b["right"], b["bottom"])
            except Exception:  # noqa: BLE001 - no bounds: only the focus rule below applies
                target = None
            for n in hierarchy.parse(self.d.dump_hierarchy()):
                # The fallback field may be unfocused: match the target by bounds as well.
                if n.password and (n.focused or n.bounds == target):
                    raise SensitiveTarget("refusing to type into a password field")
            box.click()
            box.set_text(text)
            ok = True
            if verify:
                want = text.strip()[:40]
                ok = wait_for(lambda: (box.get_text() or "").strip()[:40] == want, 2)
            rec["verified"] = ok
            return {"chars": len(text), "verified": ok}

    def get_text(self, *, raw: bool = False, **sel) -> str:
        """Text of one selector's node (redacted unless raw=True, which needs PHONE_REDACTION=off)."""
        with self._audited("get_text", selector=sel):
            self.precheck(allow_home=True)
            value = self.find(**sel).get_text() or ""
            if raw:
                if redact.policy() != "off":
                    raise PermissionError("raw text needs PHONE_REDACTION=off (owner decision)")
                return value
            return redact.get().mask(value)

    def screen_text(self, *, include_desc: bool = True, order: str = "visual",
                    pkg: str | None = None, include_system: bool = False) -> str:
        """Visible text of the current screen from dump_hierarchy, redacted. `pkg` asserts the
        foreground package and keeps only its nodes."""
        with self._audited("screen_text"):
            self.precheck(pkg=pkg, allow_home=pkg is None)
            nodes = self.nodes(pkg=pkg, include_system=include_system)
            return "\n".join(hierarchy.text_lines(nodes, include_desc=include_desc, order=order))

    def read_long(self, container: dict | None = None, *, max_steps: int = 30,
                  pause: float = 0.7, start_at_top: bool = False, include_desc: bool = False,
                  scale: float = 0.7) -> hierarchy.LongRead:
        """Scroll a container and stitch what was read, dropping the overlap between pages.

        container: selector keywords for the scrollable node (default: the whole screen).
        Ends when a scroll no longer changes the screen, or after max_steps (complete=False).
        A page with no overlap with the previous one is counted in `gaps` (content may have been
        skipped) and makes the read incomplete.

        Owner activity and the foreground are re-checked before EVERY swipe (not just once), so a
        long read stops (OwnerBusy / WrongForeground) the moment the owner picks up the phone or
        another app comes to the front; it never swipes inside an app it did not start in."""
        with self._audited("read_long", container=container) as rec:
            pinned = self.precheck(allow_home=True)["package"]

            def swipe(direction):
                self.precheck(pkg=pinned)
                self.scroll(direction, scale, box)
                time.sleep(pause)

            box = None
            if container:
                el = self.find(**container)
                if not el.exists:
                    raise LookupError(f"container not found: {container}")
                b = el.info["bounds"]
                box = (b["left"], b["top"], b["right"], b["bottom"])
            if start_at_top:
                prev = None
                for _ in range(15):
                    page = hierarchy.text_entries(self.nodes(), box=box, include_desc=include_desc)
                    if page == prev:
                        break
                    prev = page
                    swipe("up")
            pages: list[list[tuple]] = []
            reason, complete, steps = "max_steps", False, 0
            for steps in range(1, max_steps + 1):
                nodes = self.nodes()
                if self.last_redaction:
                    reason = f"redacted: {self.last_redaction}"
                    break
                page = hierarchy.text_entries(nodes, box=box, include_desc=include_desc)
                if pages and page == pages[-1]:
                    reason, complete = "end of content", True
                    break
                pages.append(page)
                swipe("down")
            lines, gaps, sticky = hierarchy.stitch_pages(pages)
            complete = complete and gaps == 0
            result = hierarchy.LongRead(lines=lines, steps=steps, complete=complete,
                                        reason=reason, gaps=gaps, sticky=sticky)
            rec.update(lines=len(lines), steps=steps, complete=complete, gaps=gaps, reason=reason,
                       sticky=len(sticky))
            return result

    def ocr_text(self, *, psm: int = 6) -> str:
        """Text read with tesseract from a REDACTED screenshot: a fallback for screens whose text is
        not in the accessibility tree. Returns "" when the redactor blacked the frame out."""
        with self._audited("ocr") as rec:
            self.precheck(allow_home=True)
            exe = shutil.which("tesseract")
            if not exe:
                raise RedactorUnavailable("tesseract not found")
            red = redact.get()
            with tempfile.TemporaryDirectory(prefix="phone-ocr-") as tmp:
                png = Path(tmp) / "screen.png"
                code = red.screenshot(self.d, png)
                rec["redactor_code"] = code
                if code == 3:
                    return ""
                out = subprocess.run([exe, str(png), "stdout", "--psm", str(psm)],
                                     capture_output=True, text=True, timeout=120)
            if out.returncode != 0:
                raise RuntimeError("tesseract failed")
            return out.stdout

    def screenshot(self, path) -> dict:
        """Write a redacted screenshot (fails closed without a redactor). Raw pixels stay in memory."""
        with self._audited("screenshot") as rec:
            self.precheck(allow_home=True)
            code = redact.get().screenshot(self.d, path)
            rec.update(redactor_code=code, blank=code == 3)
            return {"path": str(path), "redactor_code": code, "blank": code == 3}

    # waiting ---------------------------------------------------------------------------------

    def wait_idle(self, timeout: float = 10.0, stable_for: float = 1.0, poll: float = 0.4) -> bool:
        """Wait until the hierarchy stops changing for `stable_for` seconds."""
        deadline = time.time() + timeout
        last, since = None, time.time()
        while time.time() < deadline:
            digest = hashlib.sha1(self.d.dump_hierarchy().encode()).hexdigest()
            if digest != last:
                last, since = digest, time.time()
            elif time.time() - since >= stable_for:
                return True
            time.sleep(poll)
        return False

    def wait_generation_done(self, adapter, timeout: float = 600.0, poll: float = 2.0,
                             quiet_polls: int = 2) -> bool:
        """Wait until the adapter's app reports it is no longer generating for `quiet_polls`
        polls in a row. Re-checks owner activity every ~10 polls. Raises GenerationTimeout."""
        deadline = time.time() + timeout
        quiet, n = 0, 0
        while time.time() < deadline:
            n += 1
            if n % 10 == 0:
                self.require_idle(extra_exempt={adapter.package})
            quiet = 0 if adapter.is_generating(self) else quiet + 1
            if quiet >= quiet_polls:
                return True
            time.sleep(poll)
        raise GenerationTimeout(f"{adapter.name} still generating after {timeout:.0f}s")
