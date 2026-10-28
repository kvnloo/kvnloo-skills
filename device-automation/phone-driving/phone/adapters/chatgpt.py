"""ChatGPT Android adapter: the proven flow from the production launcher, ported without changes of
behaviour.

Flow per brief: open the app (owner check, agent-open ledger), reach a FRESH EMPTY composer from any
state (search, drawer, subpage; at most six attempts), set the text with set_text, wait up to 15 s for
an enabled Send control, tap Send exactly once, confirm only that the send LEFT the composer (composer
emptied or Stop appeared, polled for at most 3 s), scan the screen for rate-limit text, then restore a
fresh composer. The chat keeps running server side; results are collected elsewhere, never by the
clipboard.

Hard-won rules kept here:
  * Once a Send attempt begins an RPC failure cannot prove non-delivery: status "unconfirmed", never
    replayed. A bounded stop/start of uiautomator may repair instrumentation for the NEXT brief.
  * Briefs go to ordinary Chat only: the composer must carry the "Ask ChatGPT" description (never the
    Work or Codex surface).
  * An unknown or human draft in the fresh composer is preserved and the launch fails. Only our own
    residue (first line carries "(tag X)") is cleared.
  * Normal reply "Share" controls are NOT overlay markers: Back on those exited the app.
  * Samsung swipe-only cover: dismissed only when Android reports it non-blocking (Phone.open_app).
  * A missing Send control clears only the just-typed brief and records redacted diagnostics.
"""
from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET

from .. import activity, config, hierarchy, redact
from ..device import Phone, recoverable, wait_for
from ..errors import ComposerDraftPreserved, OwnerBusy, WrongForeground
from ..quota import QuotaPause
from .base import Adapter

PKG = "com.openai.chatgpt"
# Every launcher preamble starts "<role> (tag TAG)." within its first line; a composer holding that is
# our own unsent brief, never a human draft.
AUTOMATION_DRAFT = re.compile(r"^[^\n]{0,80}\(tag [A-Z0-9][A-Z0-9-]{2,}\)")
# Effort slider stops as fractions of a 1080x2340 screen (the slider has no per-stop nodes).
EFFORT_FRACTIONS = {"Instant": 168 / 1080, "Medium": 354 / 1080, "High": 540 / 1080,
                    "Extra High": 726 / 1080, "Pro": 909 / 1080}
EFFORT_SLIDER_Y_FRACTION = 1341 / 2340
RATE_WORDS = ("rate limit", "too many requests", "usage limit", "try again later",
              "reached the limit")
# Share also appears on normal assistant replies; it is not an overlay marker.
OVERLAY_MARKERS = ("Delete", "Archive", "Add to home", "Clear")
SEND_LABEL = re.compile(r"send(?: message| prompt)?", re.I)
DURATION_LABEL = re.compile(r"^(?:Worked|Thought) for\b")


class ChatGPT(Adapter):
    name = "chatgpt"
    package = PKG
    cooldown_s = 5.0  # measured: 21 sends from one phone in 85 s, none rate limited

    def __init__(self):
        self.quota = QuotaPause("chatgpt")

    TAG = re.compile(r"[A-Z0-9][A-Z0-9-]{2,}")

    def validate_tag(self, tag: str) -> None:
        if not self.TAG.fullmatch(tag):
            raise ValueError("chatgpt tags must match [A-Z0-9][A-Z0-9-]{2,} so an unsent brief left "
                             "in the composer is recognised as ours")

    def prepare_text(self, tag: str, text: str) -> str:
        """The first line must carry "(tag TAG)" so our own residue can be told from a human draft."""
        if AUTOMATION_DRAFT.match(text) and f"(tag {tag})" in text.split("\n", 1)[0]:
            return text
        return f"phone (tag {tag}).\n\n{text}"

    # navigation ------------------------------------------------------------------------------

    def dismiss_overlays(self, ph: Phone) -> None:
        """Close popups/menus/search that swallow taps (chat overflow menu, drawer search)."""
        d = ph.d
        for _ in range(4):
            if not any(d(text=m).exists or d(description=m).exists for m in OVERLAY_MARKERS):
                return
            d.press("back")
            time.sleep(0.4)

    def new_chat(self, ph: Phone, clear_automation_draft: bool = True):
        """Reach a fresh empty composer, including from search, drawers and subpages."""
        ph.open_app(PKG)
        d = ph.d
        for _ in range(6):
            if not d(packageName=PKG).exists:
                d.app_start(PKG)
                wait_for(lambda: d(packageName=PKG).exists, 4)
            self.dismiss_overlays(ph)
            opened = d(packageName=PKG, description="New chat").click_exists(timeout=1.5)
            if not opened and d(packageName=PKG, description="Menu").click_exists(timeout=.5):
                opened = d(packageName=PKG, description="New chat").click_exists(timeout=2)
            box = d(packageName=PKG, className="android.widget.EditText")
            if opened and wait_for(lambda: d(packageName=PKG, description="Ask ChatGPT").exists
                                   and box.exists, 4):
                draft = box.get_text() or ""
                if draft.strip():
                    if clear_automation_draft and AUTOMATION_DRAFT.match(draft):
                        # Our own brief left behind by an earlier failed send: never sent, safe to clear.
                        box.set_text("")
                        wait_for(lambda: not (box.get_text() or "").strip(), 2)
                    else:
                        # New chat can retain a human draft. Never discard or send it.
                        raise ComposerDraftPreserved(
                            "fresh composer contains an unsent draft; preserved")
            if wait_for(lambda: d(packageName=PKG, description="Ask ChatGPT").exists
                        and box.exists and not (box.get_text() or "").strip(), 4):
                return box
            if not opened:
                # Search/keyboard, drawers and settings hide New chat. Unwind one layer rather than
                # typing into an unrelated EditText or tapping a recent conversation whose title
                # happens to be "New chat".
                d.press("back")
                wait_for(lambda: d(packageName=PKG, description="New chat").exists, 1)
        raise RuntimeError("fresh composer not found")

    def set_effort(self, ph: Phone, name: str) -> None:
        """Select an effort level on the fresh-chat composer; the selection persists for later chats."""
        if name not in EFFORT_FRACTIONS:
            raise ValueError(f"effort must be one of {sorted(EFFORT_FRACTIONS)}")
        d = ph.d
        if d(descriptionStartsWith=f"Adjust effort. {name} selected").exists:
            return
        if not d(descriptionStartsWith="Adjust effort").click_exists(timeout=3):
            raise RuntimeError("effort control not found")
        time.sleep(1.2)
        w, h = d.window_size()
        d.click(round(EFFORT_FRACTIONS[name] * w), round(EFFORT_SLIDER_Y_FRACTION * h))
        time.sleep(1.0)
        d.press("back")
        if not wait_for(lambda: d(descriptionStartsWith=f"Adjust effort. {name} selected").exists, 3):
            raise RuntimeError(f"effort {name} not confirmed")

    def restore(self, ph: Phone) -> None:
        """Leave ChatGPT on a fresh composer: no sidebar, search sheet or draft of ours."""
        self.new_chat(ph, clear_automation_draft=True)

    def drawer(self, ph: Phone) -> None:
        """Open the side drawer (its Search control is the proof), unwinding search and keyboards
        first. Never swipes over a keyboard."""
        ph.open_app(PKG)
        d = ph.d
        for _ in range(5):
            if d(packageName=PKG, description="Search").exists:
                return
            d(packageName=PKG, description="Clear").click_exists(timeout=1)
            if d(packageName=PKG, description="Menu").click_exists(timeout=2):
                if wait_for(lambda: d(packageName=PKG, description="Search").exists, 3):
                    return
            else:
                d.press("back")
                time.sleep(0.8)
        raise RuntimeError("drawer not reachable")

    def open_title(self, ph: Phone, title: str) -> bool:
        """Open an existing chat by its exact title through the drawer's Search box (reading only:
        nothing is sent). Returns False when the title is not found; the phone is then left on the
        search screen (call restore)."""
        if not title.strip():
            raise ValueError("title must not be empty")
        self.drawer(ph)
        d = ph.d
        if not d(packageName=PKG, description="Search").click_exists(timeout=4):
            return False
        box = d(packageName=PKG, className="android.widget.EditText")
        if not wait_for(lambda: box.exists, 5):
            return False
        if d(packageName=PKG, description="Ask ChatGPT").exists:
            raise RuntimeError("the composer, not the search box, has the focus; refusing to type")
        box.set_text(title)
        # Match the result row, never the search box that now holds the same text.
        hits = d(packageName=PKG, text=title, className="android.widget.TextView")
        if not wait_for(lambda: hits.exists, 5):
            return False
        hits.click()
        return wait_for(lambda: not d(packageName=PKG, description="Search").exists, 5)

    # sending ---------------------------------------------------------------------------------

    def send(self, ph: Phone, box, text: str, receipt: dict | None = None,
             preflight: bool = False, **_kw) -> str:
        d = ph.d
        # The effort sheet's Back dismissal leaves the composer unfocused; ChatGPT then shows Voice
        # instead of Send. Focus it first. Screencap first (redacted, local only, overwritten).
        try:
            shots = config.state_dir() / "prelaunch"
            shots.mkdir(parents=True, exist_ok=True)
            ph.screenshot(shots / f"{ph.role}-latest.png")
        except Exception as e:  # noqa: BLE001 - evidence capture must not change the outcome
            if receipt is not None:
                receipt["prelaunch_shot_error"] = f"{type(e).__name__}: {e}"
        reason = ph.owner_busy(extra_exempt={PKG})
        if reason:
            raise OwnerBusy(reason)
        # Briefs go to ordinary ChatGPT chats, never the Work/Codex Cloud surface. Only the Chat
        # composer carries "Ask ChatGPT".
        if not d(packageName=PKG, description="Ask ChatGPT").exists:
            raise RuntimeError(
                "not on the ordinary Chat composer (Work/Codex surface?); refusing to type")
        box.click()
        box.set_text(text)
        if not wait_for(lambda: (box.get_text() or "").strip()[:40] == text.strip()[:40], 2):
            raise RuntimeError("composer text mismatch")
        # Refresh Compose accessibility before deciding readiness. Match normalized labels locally,
        # then select the exact raw description from that hierarchy.
        send_btn = None
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            for node in ET.fromstring(d.dump_hierarchy()).iter("node"):
                raw = node.get("content-desc", "")
                label = re.sub(r"\s+", " ", raw).strip()
                if (node.get("package") == PKG and node.get("enabled") == "true"
                        and SEND_LABEL.fullmatch(label)):
                    send_btn = d(packageName=PKG, description=raw)
                    break
            if send_btn is not None:
                break
            time.sleep(0.2)
        if send_btn is None:
            try:
                red = redact.get()
                diag = config.state_dir() / "diag"
                diag.mkdir(parents=True, exist_ok=True)
                (diag / f"send-missing-{ph.role}.xml").write_text(red.hierarchy(d))
                red.screenshot(d, diag / f"send-missing-{ph.role}.png")
            except Exception:  # noqa: BLE001 - diagnostics must not mask the real failure
                pass
            # Leave no residue: an unsent brief in the composer blocks every later launch.
            if (box.get_text() or "") == text:
                box.set_text("")
            raise RuntimeError("Send button not found")
        reason = ph.owner_busy(extra_exempt={PKG})
        if reason:
            raise OwnerBusy(reason)
        if preflight:
            # Readiness only: never click Send, and remove only our exact inserted text.
            if (box.get_text() or "") != text:
                raise RuntimeError("preflight text changed; preserving composer")
            box.set_text("")
            if not wait_for(lambda: not (box.get_text() or "").strip(), 2):
                raise RuntimeError("preflight text did not clear")
            return "preflight_ready"
        # Once a Send attempt begins, an RPC failure cannot establish non-delivery. Never retry this
        # phase, even when instrumentation is recoverable.
        if receipt is not None:
            receipt["send_attempted"] = True
        send_btn.click()
        left = wait_for(lambda: d(packageName=PKG, descriptionContains="Stop").exists
                        or (box.exists and not (box.get_text() or "").strip()), 3)
        return "sent" if left else "unconfirmed"

    def rate_limit_hits(self, hierarchy_lower: str, own_text_lower: str) -> list[str]:
        return [w for w in RATE_WORDS if w in hierarchy_lower and w not in own_text_lower]

    def launch(self, ph: Phone, tag: str, text: str, *, effort: str | None = None,
               preflight: bool = False, **_kw) -> dict:
        """One brief, end to end. Returns the receipt: status is one of sent, unconfirmed, failed,
        owner_busy, rate_limited, or (preflight) preflight_ready. Never raises for a UI failure."""
        d = ph.d
        t0 = time.time()
        rec = {"tag": tag, "at": activity.now(), "t0": t0, "device": ph.role,
               "transport": ph.device_id(), "send_attempted": False}
        info: dict = {}
        try:
            def prepare():
                box = self.new_chat(ph, clear_automation_draft=not preflight)
                if effort:
                    self.set_effort(ph, effort)
                    rec["effort"] = effort
                    box = d(packageName=PKG, className="android.widget.EditText")
                return box

            box = ph.run_recoverable(prepare, info=info)
            rec["status"] = self.send(ph, box, text, rec, preflight=preflight)
            if preflight:
                rec["fresh_composer"] = True
                rec["send_button_detected"] = True
        except Exception as e:  # noqa: BLE001
            rec["status"] = ("unconfirmed" if rec["send_attempted"] else
                             "owner_busy" if isinstance(e, OwnerBusy) else "failed")
            rec["error"] = str(e)
            rec["error_class"] = type(e).__name__
            if rec["send_attempted"] and recoverable(e) and not info.get("restarted"):
                try:
                    ph.restart_uiautomator()
                    rec["recovered_after_send"] = True
                except Exception as recovery:  # noqa: BLE001
                    rec["recovery_error"] = f"{type(recovery).__name__}: {recovery}"
        rec.update({k: v for k, v in info.items() if k not in rec})
        if preflight:
            try:
                # On any preflight failure, never clear a changed or unknown draft.
                box = d(packageName=PKG, className="android.widget.EditText")
                if box.exists and (box.get_text() or "") == text:
                    box.set_text("")
            except Exception as e:  # noqa: BLE001
                rec["preflight_cleanup_error"] = f"{type(e).__name__}: {e}"
        rec["secs"] = round(time.time() - t0, 2)
        raw = ""
        try:
            raw = d.dump_hierarchy()
        except Exception as e:  # noqa: BLE001
            rec["inspection_error"] = f"{type(e).__name__}: {e}"
        hits = self.rate_limit_hits(raw.lower(), text.lower())
        if hits:
            rec["status"] = "rate_limited"
            # Keep the evidence: a reply's own progress line (e.g. a GitHub connector "rate limit")
            # can match too, and the pause must be auditable.
            rec["rate_words"] = hits
            try:
                ev = config.state_dir() / "rate-evidence"
                ev.mkdir(parents=True, exist_ok=True)
                red = redact.get()
                (ev / f"{tag}.xml").write_text(red.xml(raw))
                red.screenshot(d, ev / f"{tag}.png")
            except Exception as e:  # noqa: BLE001 - evidence capture must not change the outcome
                rec["rate_evidence_error"] = f"{type(e).__name__}: {e}"
        if rec["status"] not in ("rate_limited", "owner_busy"):
            try:
                self.new_chat(ph, clear_automation_draft=not preflight)
            except Exception as e:  # noqa: BLE001
                rec["restore_error"] = f"{type(e).__name__}: {e}"
        return rec

    # observation -----------------------------------------------------------------------------

    def is_generating(self, ph: Phone) -> bool:
        return bool(ph.d(packageName=PKG, descriptionContains="Stop").exists)

    def state(self, ph: Phone) -> dict:
        """running | idle plus the last "Worked for"/"Thought for" label, from the hierarchy."""
        nodes = [n for n in hierarchy.parse(ph.d.dump_hierarchy()) if n.pkg == PKG]
        if not nodes:
            raise WrongForeground("ChatGPT is not in the foreground")
        labels = [n.label for n in nodes if n.label]
        durations = [n.text for n in nodes if DURATION_LABEL.match(n.text)]
        return {"app": self.name, "foreground": bool(nodes),
                "running": any("Stop" in n.desc for n in nodes),
                "composer": any(n.desc == "Ask ChatGPT" for n in nodes),
                "duration": durations[-1] if durations else None,
                "labelled_nodes": len(labels)}

    def read(self, ph: Phone, long: bool = False, title: str | None = None,
             from_top: bool = False) -> dict:
        """State plus the visible text of the current screen (redacted). With `title` it first
        opens that chat by search; otherwise it does not navigate. `long` scrolls and stitches.
        Reply bodies that the app does not expose to accessibility are NOT recoverable here: the
        clipboard path is blocked by the guard, so collect results server side."""
        if title is not None and not self.open_title(ph, title):
            raise LookupError("no chat with that exact title was found")
        st = self.state(ph)
        if long:
            res = ph.read_long(start_at_top=from_top)
            st.update(text=res.text, complete=res.complete, steps=res.steps, reason=res.reason,
                      gaps=res.gaps)
        else:
            st["text"] = ph.screen_text(include_desc=False)
        return st
