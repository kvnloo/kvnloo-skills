"""Test doubles for the phone package: a small fake uiautomator2 device that models the ChatGPT
screens the adapter navigates, and a Phone built on it. No real device, adb or network."""
from __future__ import annotations

import time
from xml.sax.saxutils import quoteattr

PKG = "com.openai.chatgpt"
LAUNCHER = "com.example.launcher"


def el(desc="", text="", cls="android.view.View", pkg=PKG, enabled=True, click=None, eid=None,
       editable=False, bounds=(0, 0, 100, 100)):
    return {"desc": desc, "text": text, "cls": cls, "pkg": pkg, "enabled": enabled, "click": click,
            "id": eid, "editable": editable, "bounds": bounds}


class FakeResult:
    def __init__(self, output=""):
        self.output = output


class FakeSel:
    def __init__(self, dev, sel):
        self.dev, self.sel = dev, sel

    def _match(self, e, d):
        for key, want in self.sel.items():
            if key == "packageName" and e["pkg"] != want:
                return False
            if key == "description" and e["desc"] != want:
                return False
            if key == "descriptionContains" and want not in e["desc"]:
                return False
            if key == "descriptionStartsWith" and not e["desc"].startswith(want):
                return False
            if key == "className" and e["cls"] != want:
                return False
            if key == "text" and self.dev.text_of(e) != want:
                return False
            if key == "textContains" and want not in self.dev.text_of(e):
                return False
            if key == "enabled" and e["enabled"] != want:
                return False
            if key == "focused" and not (want is False or e["editable"]):
                return False
        return True

    def _els(self):
        return [e for e in self.dev.elements() if self._match(e, self.dev)]

    @property
    def exists(self):
        return bool(self._els())

    def wait(self, timeout=0):
        return self.exists

    def click_exists(self, timeout=0):
        els = self._els()
        if not els:
            return False
        self.dev.click_el(els[0])
        return True

    def click(self):
        els = self._els()
        if not els:
            raise LookupError("no match")
        self.dev.click_el(els[0])

    def get_text(self):
        els = self._els()
        return self.dev.text_of(els[0]) if els else None

    def set_text(self, text):
        els = self._els()
        if not els:
            raise LookupError("no match")
        self.dev.set_text_el(els[0], text)


class FakeDevice:
    serial = "FAKE-SERIAL"

    def __init__(self):
        self.screen = "launcher"
        self.texts: dict = {}
        self.sent: list = []
        self.started: list = []
        self.pressed: list = []
        self.draft = ""            # text already in the fresh composer when it opens
        self.send_enabled_delay = 0.0
        self.hide_send = False
        self.stop_after_send = True
        self.fail_calls: list = []  # exceptions to raise from the next dump_hierarchy calls
        self.restarts = 0
        self.extra_text_after_send = ""  # appended to the chat screen after send (rate limit text)
        self.titles = ["Existing chat one", "Another chat"]  # openable through search

    # screens ---------------------------------------------------------------------------------
    def elements(self):
        s = self.screen
        if s == "launcher":
            return [el(text="Gmail", pkg=LAUNCHER)]
        if s == "chat":
            els = [el(desc="Menu", click="drawer"), el(desc="New chat", click="new")]
            if self.sent and self.stop_after_send:
                els.append(el(desc="Stop streaming", click=None))
            if self.extra_text_after_send:
                els.append(el(text=self.extra_text_after_send, cls="android.widget.TextView"))
            return els
        if s == "drawer":
            return [el(desc="New chat", click="new"), el(desc="Search", click="search"),
                    el(text="Recents", cls="android.widget.TextView")]
        if s == "search":
            els = [el(cls="android.widget.EditText", eid="search", editable=True),
                   el(desc="Clear", click=None)]
            query = self.texts.get("search", "")
            els += [el(text=t, cls="android.widget.TextView", click="chat")
                    for t in self.titles if query and t == query]
            return els
        if s == "menu_popup":
            return [el(text="Delete", click=None), el(text="Archive", click=None)]
        if s == "new":
            els = [el(desc="Menu", click="drawer"), el(desc="Ask ChatGPT"),
                   el(cls="android.widget.EditText", eid="composer", editable=True),
                   el(desc="Adjust effort. Extra High selected.", click=None)]
            if (self.texts.get("composer", "").strip() and not self.hide_send
                    and time.time() >= self.send_enabled_delay):
                els.append(el(desc="Send", click="SEND"))
            return els
        if s == "work":
            return [el(desc="Menu", click="drawer"), el(desc="Start a task")]
        raise KeyError(s)

    def text_of(self, e):
        if e["id"]:
            return self.texts.get(e["id"], e["text"])
        return e["text"]

    def click_el(self, e):
        target = e["click"]
        if target == "SEND":
            self.sent.append(self.texts.get("composer", ""))
            self.texts["composer"] = ""
            self.screen = "chat"
        elif target == "new":
            self.screen = "new"
            self.texts["composer"] = self.draft
        elif target:
            self.screen = target

    def set_text_el(self, e, text):
        self.texts[e["id"]] = text

    # u2 surface ------------------------------------------------------------------------------
    def __call__(self, **sel):
        return FakeSel(self, sel)

    def press(self, key):
        self.pressed.append(key)
        if key == "home":
            self.screen = "launcher"
        elif key == "back":
            self.screen = {"search": "drawer", "drawer": "new", "menu_popup": "chat",
                           "chat": "new", "work": "new"}.get(self.screen, self.screen)

    def app_start(self, pkg):
        self.started.append(pkg)
        if self.screen == "launcher":
            self.screen = "new"

    def screen_on(self):
        pass

    def window_size(self):
        return (1080, 2340)

    def click(self, x, y):
        self.pressed.append(("click", x, y))

    def swipe_ext(self, *a, **kw):
        self.pressed.append(("swipe", a))

    def shell(self, cmd, *a, **kw):
        return FakeResult("showing=false\ninputRestricted=false\n")

    def stop_uiautomator(self):
        self.restarts += 1

    def start_uiautomator(self):
        pass

    def dump_hierarchy(self):
        if self.fail_calls:
            raise self.fail_calls.pop(0)
        nodes = []
        for e in self.elements():
            l, t, r, b = e["bounds"]
            nodes.append(
                "<node class=%s package=%s text=%s content-desc=%s enabled=%s clickable=%s "
                "focused=%s password=\"false\" resource-id=\"\" bounds=\"[%d,%d][%d,%d]\"/>" % (
                    quoteattr(e["cls"]), quoteattr(e["pkg"]), quoteattr(self.text_of(e)),
                    quoteattr(e["desc"]), quoteattr("true" if e["enabled"] else "false"),
                    quoteattr("true" if e["click"] else "false"),
                    quoteattr("false"), l, t, r, b))
        return "<?xml version='1.0'?><hierarchy>" + "".join(nodes) + "</hierarchy>"


def make_phone(role="s22", device: FakeDevice | None = None, busy=None, shots_ok=False):
    """A real phone.Phone wired to a FakeDevice. owner_busy returns `busy` (a reason or None)."""
    from phone import Phone, adb as adbmod
    from phone.errors import RedactorUnavailable

    ph = Phone.__new__(Phone)
    ph.role = role
    ph.use_lock = False
    ph.lock_wait = 1
    ph.driving = {PKG}
    ph.audit = False
    ph._serial_override = None
    ph.transport = adbmod.Transport("FAKE-SERIAL", "FAKE-SERIAL", "usb")
    ph.d = device or FakeDevice()
    ph._lock = None
    ph.last_redaction = None
    ph.busy_reasons = [busy] if not isinstance(busy, list) else list(busy)

    def owner_busy(extra_exempt=()):
        if ph.busy_reasons:
            return ph.busy_reasons.pop(0) if len(ph.busy_reasons) > 1 else ph.busy_reasons[0]
        return None

    def open_app(pkg):
        reason = owner_busy({pkg})
        if reason:
            from phone.errors import OwnerBusy
            raise OwnerBusy(reason)
        ph.d.app_start(pkg)
        ph.driving.add(pkg)

    def screenshot(path):
        if not shots_ok:
            raise RedactorUnavailable("test: no redactor")
        from pathlib import Path
        Path(path).write_bytes(b"\x89PNG\r\n\x1a\n")
        return {"path": str(path), "redactor_code": 0, "blank": False}

    ph.owner_busy = owner_busy
    ph.open_app = open_app
    ph.screenshot = screenshot
    return ph
