"""DeepSeek Android adapter: NOT CALIBRATED. It refuses to act until it is.

Written from public knowledge only; nothing here has been verified on a real device. Every operation
raises CalibrationRequired until a calibration file proves each selector on a real phone. It never
guesses and never taps a neighbour.

TODO(calibrate), on the worker phone, with read-only probing first:
  1. `phone open --role s22 com.deepseek.chat`, then `phone nodes --role s22 --pkg com.deepseek.chat`
     on each screen (home, drawer, composer with text typed, generating, finished reply).
  2. Record, per selector below, the real text/desc/resource-id. Prefer resource-id, then desc,
     then text; never coordinates.
  3. Write `<calibration dir>/deepseek.json` (see references/calibration.md) with
     {"calibrated": true, "verified_on": "<date>", "selectors": {...every key in REQUIRED...}}.
  4. Prove a preflight (type, detect Send, clear) before any real send.
  5. Learn whether reply text is exposed to accessibility. If it is not, there is no read path:
     the clipboard is blocked by the guard.

Public-knowledge guesses (UNVERIFIED, kept as a starting point for step 1 only): package
com.deepseek.chat; a composer with a "Message DeepSeek" style hint; a Send control; a New chat
control; DeepThink and Search toggles; a Stop control while generating.
"""
from __future__ import annotations

import json
import time

from .. import config
from ..device import Phone, wait_for
from ..errors import CalibrationRequired, ComposerDraftPreserved, OwnerBusy
from ..quota import QuotaPause
from .base import Adapter

PKG = "com.deepseek.chat"  # UNVERIFIED

# Selector names the generic flow needs. Each maps to phone selector keywords (see device.SEL_MAP).
REQUIRED = ("composer", "send_button", "new_chat", "stop_button")
UNVERIFIED_HINTS = {  # public-knowledge guesses; DO NOT USE until calibrated
    "composer": {"cls": "android.widget.EditText"},
    "send_button": {"desc": "Send"},
    "new_chat": {"desc": "New chat"},
    "stop_button": {"desc_contains": "Stop"},
}


class DeepSeek(Adapter):
    name = "deepseek"
    package = PKG
    cooldown_s = 5.0

    def __init__(self, calibration: dict | None = None):
        self.quota = QuotaPause("deepseek")
        self._calibration = calibration

    # calibration -----------------------------------------------------------------------------

    def calibration(self) -> dict:
        if self._calibration is not None:
            return self._calibration
        path = config.calibration_dir() / "deepseek.json"
        try:
            self._calibration = json.loads(path.read_text())
        except (OSError, ValueError):
            self._calibration = {}
        return self._calibration

    def selectors(self) -> dict:
        cal = self.calibration()
        sel = cal.get("selectors") or {}
        missing = [k for k in REQUIRED if not isinstance(sel.get(k), dict) or not sel[k]]
        if cal.get("calibrated") is not True or missing:
            raise CalibrationRequired(
                "deepseek adapter is not calibrated on a real device"
                + (f" (missing selectors: {', '.join(missing)})" if missing else "")
                + ". Probe with `phone nodes`, then write deepseek.json as described in "
                  "references/calibration.md. Refusing to guess.")
        return sel

    # flow ------------------------------------------------------------------------------------

    def new_chat(self, ph: Phone, clear_automation_draft: bool = False):
        sel = self.selectors()
        ph.open_app(self.package)
        d = ph.d
        for _ in range(6):
            if not d(packageName=self.package).exists:
                d.app_start(self.package)
                wait_for(lambda: d(packageName=self.package).exists, 4)
            opened = ph.find(pkg=self.package, **sel["new_chat"]).click_exists(timeout=1.5)
            box = ph.find(pkg=self.package, **sel["composer"])
            if opened and wait_for(lambda: box.exists, 4):
                if (box.get_text() or "").strip():
                    raise ComposerDraftPreserved("fresh composer contains an unsent draft; preserved")
                return box
            d.press("back")
        raise RuntimeError("fresh composer not found")

    def send(self, ph: Phone, box, text: str, receipt: dict | None = None,
             preflight: bool = False, **_kw) -> str:
        sel = self.selectors()
        reason = ph.owner_busy(extra_exempt={self.package})
        if reason:
            raise OwnerBusy(reason)
        box.click()
        box.set_text(text)
        if not wait_for(lambda: (box.get_text() or "").strip()[:40] == text.strip()[:40], 2):
            raise RuntimeError("composer text mismatch")
        btn = ph.find(pkg=self.package, enabled=True, **sel["send_button"])
        if not wait_for(lambda: btn.exists, 15):
            if (box.get_text() or "") == text:
                box.set_text("")
            raise RuntimeError("Send button not found")
        if preflight:
            if (box.get_text() or "") != text:
                raise RuntimeError("preflight text changed; preserving composer")
            box.set_text("")
            return "preflight_ready"
        if receipt is not None:
            receipt["send_attempted"] = True
        btn.click()
        stop = ph.find(pkg=self.package, **sel["stop_button"])
        left = wait_for(lambda: stop.exists or (box.exists and not (box.get_text() or "").strip()), 3)
        return "sent" if left else "unconfirmed"

    def launch(self, ph: Phone, tag: str, text: str, *, preflight: bool = False, **_kw) -> dict:
        self.selectors()
        t0 = time.time()
        rec = {"tag": tag, "device": ph.role, "transport": ph.device_id(), "send_attempted": False}
        try:
            box = ph.run_recoverable(lambda: self.new_chat(ph))
            rec["status"] = self.send(ph, box, text, rec, preflight=preflight)
        except Exception as e:  # noqa: BLE001
            rec["status"] = ("unconfirmed" if rec["send_attempted"] else
                             "owner_busy" if isinstance(e, OwnerBusy) else "failed")
            rec["error"], rec["error_class"] = str(e), type(e).__name__
        rec["secs"] = round(time.time() - t0, 2)
        return rec

    def is_generating(self, ph: Phone) -> bool:
        sel = self.selectors()
        return bool(ph.find(pkg=self.package, **sel["stop_button"]).exists)

    def state(self, ph: Phone) -> dict:
        self.selectors()
        return {"app": self.name, "running": self.is_generating(ph)}

    def read(self, ph: Phone, long: bool = False) -> dict:
        self.selectors()
        st = self.state(ph)
        if long:
            res = ph.read_long()
            st.update(text=res.text, complete=res.complete, steps=res.steps, reason=res.reason)
        else:
            st["text"] = ph.screen_text(include_desc=False)
        return st

    def restore(self, ph: Phone) -> None:
        self.new_chat(ph)
