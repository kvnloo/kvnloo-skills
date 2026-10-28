"""ChatGPT adapter flows (against a fake device) and the DeepSeek calibration gate."""
from __future__ import annotations

import http.client

import pytest

from phone.adapters import chatgpt as cg
from phone.adapters.chatgpt import ChatGPT
from phone.adapters.deepseek import DeepSeek
from phone.errors import CalibrationRequired, ComposerDraftPreserved, OwnerBusy

import phone_testlib as t

pytestmark = pytest.mark.usefixtures("phone_env")


@pytest.fixture(autouse=True)
def fast_waits(monkeypatch):
    real = cg.wait_for

    def quick(pred, timeout, step=0.15):
        return real(pred, min(timeout, 0.4), 0.02)

    monkeypatch.setattr(cg, "wait_for", quick)
    import phone.device as device
    monkeypatch.setattr(device, "wait_for", quick)
    monkeypatch.setattr(cg.time, "sleep", lambda s: None)


@pytest.fixture
def dev():
    return t.FakeDevice()


@pytest.fixture
def ph(dev):
    return t.make_phone(device=dev)


GOOD = "phone (tag TEST-1). Do the thing."


# new_chat -------------------------------------------------------------------------------------

def test_new_chat_from_the_launcher_goes_through_the_menu(ph, dev):
    box = ChatGPT().new_chat(ph)
    assert dev.screen == "new" and box.exists and not (box.get_text() or "").strip()


def test_new_chat_from_a_conversation_taps_new_chat_directly(ph, dev):
    dev.screen = "chat"
    ChatGPT().new_chat(ph)
    assert dev.screen == "new"


def test_new_chat_from_search_unwinds_and_never_types_into_search(ph, dev):
    dev.screen = "search"
    ChatGPT().new_chat(ph)
    assert dev.screen == "new"
    assert "search" not in dev.texts


def test_overlays_are_dismissed_with_back(ph, dev):
    dev.screen = "menu_popup"
    ChatGPT().new_chat(ph)
    assert "back" in dev.pressed and dev.screen == "new"


def test_share_label_is_not_an_overlay_marker():
    assert "Share" not in cg.OVERLAY_MARKERS


def test_human_draft_is_preserved_and_launch_refused(ph, dev):
    dev.draft = "my own half written message"
    with pytest.raises(ComposerDraftPreserved):
        ChatGPT().new_chat(ph)
    assert dev.texts["composer"] == "my own half written message"


def test_our_own_residue_is_cleared_but_not_in_preflight(ph, dev):
    dev.draft = "phone (tag RES-1). left behind"
    ChatGPT().new_chat(ph, clear_automation_draft=True)
    assert dev.texts["composer"] == ""
    dev.screen, dev.draft = "chat", "phone (tag RES-1). left behind"
    with pytest.raises(ComposerDraftPreserved):
        ChatGPT().new_chat(ph, clear_automation_draft=False)
    assert dev.texts["composer"]


def test_work_surface_is_refused_for_typing(ph, dev):
    dev.screen = "work"
    box = dev(packageName=cg.PKG, className="android.widget.EditText")
    with pytest.raises(RuntimeError, match="Chat composer"):
        ChatGPT().send(ph, box, GOOD)


# send -----------------------------------------------------------------------------------------

def prepared(ph):
    a = ChatGPT()
    return a, a.new_chat(ph)


def test_send_taps_send_once_and_reports_sent(ph, dev):
    a, box = prepared(ph)
    rec = {}
    assert a.send(ph, box, GOOD, rec) == "sent"
    assert rec["send_attempted"] is True and dev.sent == [GOOD]


def test_preflight_never_sends_and_clears_only_its_text(ph, dev):
    a, box = prepared(ph)
    rec = {}
    assert a.send(ph, box, GOOD, rec, preflight=True) == "preflight_ready"
    assert dev.sent == [] and dev.texts["composer"] == "" and "send_attempted" not in rec


def test_missing_send_button_clears_the_typed_brief(ph, dev, monkeypatch):
    dev.hide_send = True
    ticks = iter(range(0, 10_000, 6))
    monkeypatch.setattr(cg.time, "monotonic", lambda: next(ticks))
    a, box = prepared(ph)
    with pytest.raises(RuntimeError, match="Send button not found"):
        a.send(ph, box, GOOD, {})
    assert dev.texts["composer"] == "" and dev.sent == []


def test_send_without_confirmation_is_unconfirmed_not_failed(ph, dev, monkeypatch):
    dev.stop_after_send = False
    original = dev.click_el

    def swallow(e):
        if e["click"] == "SEND":
            dev.sent.append(dev.texts["composer"])   # delivered, but the UI shows nothing
            return
        original(e)
    monkeypatch.setattr(dev, "click_el", swallow)
    a, box = prepared(ph)
    assert a.send(ph, box, GOOD, {}) == "unconfirmed"


def test_owner_activity_before_send_aborts_without_sending(dev):
    ph = t.make_phone(device=dev, busy=[None, None, "owner active in x within 60 s"])
    a = ChatGPT()
    box = a.new_chat(ph)
    with pytest.raises(OwnerBusy):
        a.send(ph, box, GOOD, {})
    assert dev.sent == []


# launch ---------------------------------------------------------------------------------------

def test_launch_success_restores_a_fresh_composer(ph, dev):
    rec = ChatGPT().launch(ph, "TEST-1", GOOD)
    assert rec["status"] == "sent" and rec["send_attempted"] is True
    assert dev.sent == [GOOD] and dev.screen == "new" and "restore_error" not in rec
    assert rec["tag"] == "TEST-1" and rec["device"] == "s22" and "t0" in rec and "secs" in rec
    assert GOOD not in str(rec)


def test_launch_owner_busy_before_ui_touches_nothing(dev):
    ph = t.make_phone(device=dev, busy="owner user activity within 60 seconds")
    rec = ChatGPT().launch(ph, "TEST-2", GOOD)
    assert rec["status"] == "owner_busy" and rec["send_attempted"] is False
    assert dev.sent == [] and dev.started == []


def test_launch_failure_before_send_is_failed_and_leaves_no_residue(ph, dev, monkeypatch):
    dev.hide_send = True
    ticks = iter(range(0, 10_000, 6))
    monkeypatch.setattr(cg.time, "monotonic", lambda: next(ticks))
    rec = ChatGPT().launch(ph, "TEST-3", GOOD)
    assert rec["status"] == "failed" and rec["send_attempted"] is False
    assert "Send button not found" in rec["error"]
    assert dev.texts["composer"] == "" and dev.sent == []


def test_launch_detects_rate_limit_and_does_not_restore(ph, dev):
    dev.extra_text_after_send = "You've reached the limit. Try again later."
    rec = ChatGPT().launch(ph, "TEST-4", GOOD)
    assert rec["status"] == "rate_limited"
    assert set(rec["rate_words"]) == {"reached the limit", "try again later"}
    assert dev.screen == "chat"


def test_rate_words_in_our_own_text_do_not_count(ph, dev):
    own = "phone (tag TEST-5). Summarise the usage limit docs."
    dev.extra_text_after_send = "usage limit"
    rec = ChatGPT().launch(ph, "TEST-5", own)
    assert rec["status"] == "sent"


def test_recoverable_failure_before_send_restarts_once_and_retries(ph, dev):
    dev.fail_calls = [http.client.RemoteDisconnected("Remote end closed connection")]
    rec = ChatGPT().launch(ph, "TEST-6", GOOD)
    assert rec["status"] == "sent" and dev.restarts == 1
    assert "RemoteDisconnected" in rec["recovery_error"] and rec["restarted"] is True
    assert dev.sent == [GOOD]


def test_unrecoverable_failure_is_not_retried(ph, dev):
    dev.fail_calls = [ValueError("boom")]
    rec = ChatGPT().launch(ph, "TEST-7", GOOD)
    assert rec["status"] == "failed" and dev.restarts == 0 and dev.sent == []


def test_rpc_failure_after_send_is_unconfirmed_and_never_replayed(ph, dev, monkeypatch):
    original = dev.elements
    state = {"boom": [http.client.RemoteDisconnected("Remote end closed connection")]}

    def boom_after_send():
        if dev.sent and state["boom"]:
            raise state["boom"].pop(0)
        return original()
    monkeypatch.setattr(dev, "elements", boom_after_send)
    rec = ChatGPT().launch(ph, "TEST-8", GOOD)
    assert rec["status"] == "unconfirmed" and rec["send_attempted"] is True
    assert rec["recovered_after_send"] is True and dev.restarts == 1
    assert dev.sent == [GOOD]            # exactly one send, never replayed


def test_preflight_launch_reports_readiness_and_never_sends(ph, dev):
    rec = ChatGPT().launch(ph, "TEST-9", GOOD, preflight=True)
    assert rec["status"] == "preflight_ready" and rec["send_attempted"] is False
    assert rec["fresh_composer"] and rec["send_button_detected"] and dev.sent == []
    assert dev.texts["composer"] == ""


# effort, state, tags --------------------------------------------------------------------------

def test_effort_stops_scale_to_the_screen_and_match_the_proven_pixels(ph, dev):
    assert round(cg.EFFORT_FRACTIONS["High"] * 1080) == 540
    assert [round(f * 1080) for f in cg.EFFORT_FRACTIONS.values()] == [168, 354, 540, 726, 909]
    assert round(cg.EFFORT_SLIDER_Y_FRACTION * 2340) == 1341
    ChatGPT().new_chat(ph)
    with pytest.raises(RuntimeError, match="not confirmed"):
        ChatGPT().set_effort(ph, "High")
    assert ("click", 540, 1341) in dev.pressed


def test_effort_already_selected_does_nothing(ph, dev):
    ChatGPT().new_chat(ph)
    before = list(dev.pressed)
    ChatGPT().set_effort(ph, "Extra High")
    assert dev.pressed == before


def test_unknown_effort_is_rejected(ph):
    with pytest.raises(ValueError):
        ChatGPT().set_effort(ph, "Turbo")


def test_state_reports_running_and_composer(ph, dev):
    a = ChatGPT()
    a.new_chat(ph)
    assert a.state(ph)["composer"] is True and a.state(ph)["running"] is False
    a.send(ph, dev(packageName=cg.PKG, className="android.widget.EditText"), GOOD, {})
    st = a.state(ph)
    assert st["running"] is True and a.is_generating(ph) is True


def test_tags_and_text_preparation():
    a = ChatGPT()
    with pytest.raises(ValueError):
        a.validate_tag("lower-case")
    a.validate_tag("OK-1")
    assert a.prepare_text("OK-1", "do it").startswith("phone (tag OK-1).")
    assert cg.AUTOMATION_DRAFT.match(a.prepare_text("OK-1", "do it"))
    already = "worker (tag OK-1). do it"
    assert a.prepare_text("OK-1", already) == already
    assert a.prepare_text("OK-2", already).startswith("phone (tag OK-2).")


def test_quota_and_cooldown_names_match_the_production_files(phone_env):
    a = ChatGPT()
    assert a.quota.path.name == "chatgpt-quota-pause"
    assert a.cooldown("s22").path.name == "chatgpt-last-dispatch-s22"
    assert a.cooldown_s == 5


# deepseek -------------------------------------------------------------------------------------

def test_deepseek_refuses_everything_until_calibrated(ph):
    a = DeepSeek()
    for call in (lambda: a.selectors(), lambda: a.new_chat(ph), lambda: a.state(ph),
                 lambda: a.is_generating(ph), lambda: a.read(ph), lambda: a.launch(ph, "X-1", "t")):
        with pytest.raises(CalibrationRequired):
            call()


def test_deepseek_uncalibrated_flag_or_missing_keys_still_refuse():
    sel = {k: {"desc": "x"} for k in ("composer", "send_button", "new_chat", "stop_button")}
    with pytest.raises(CalibrationRequired):
        DeepSeek({"calibrated": False, "selectors": sel}).selectors()
    partial = dict(sel)
    del partial["stop_button"]
    with pytest.raises(CalibrationRequired, match="stop_button"):
        DeepSeek({"calibrated": True, "selectors": partial}).selectors()
    assert DeepSeek({"calibrated": True, "selectors": sel}).selectors() == sel


def test_deepseek_hints_are_not_used_as_selectors():
    from phone.adapters import deepseek
    assert deepseek.UNVERIFIED_HINTS
    with pytest.raises(CalibrationRequired):
        DeepSeek().selectors()


# open_app, state and OCR ----------------------------------------------------------------------

def test_state_refuses_when_chatgpt_is_not_in_front(ph, dev):
    from phone.errors import WrongForeground
    dev.screen = "launcher"
    with pytest.raises(WrongForeground):
        ChatGPT().state(ph)


def test_open_app_refuses_an_uninstalled_package_before_any_input(dev):
    from phone import Phone
    from phone.errors import OwnerBusy  # noqa: F401
    ph = t.make_phone(device=dev)
    ph.open_app = Phone.open_app.__get__(ph)          # the real method
    ph.require_lock = lambda: None
    dev.shell = lambda cmd, *a, **k: t.FakeResult("")  # `pm path` prints nothing: not installed
    ph._audited = lambda *a, **k: __import__("contextlib").nullcontext({})
    with pytest.raises(LookupError, match="not installed"):
        ph.open_app("com.example.missing")
    assert dev.started == [] and dev.pressed == []


def test_ocr_reads_a_redacted_screenshot_and_cleans_up(dev, monkeypatch, tmp_path):
    import subprocess
    from phone import Phone, device as devmod
    ph = t.make_phone(device=dev)
    ph.precheck = lambda **kw: {}
    seen = {}

    class Red:
        def screenshot(self, d, path):
            seen["path"] = path
            path.write_bytes(b"\x89PNG")
            return 0

    monkeypatch.setattr(devmod.redact, "get", lambda optional=False: Red())
    monkeypatch.setattr(devmod.shutil, "which", lambda name: "/usr/bin/tesseract")
    monkeypatch.setattr(devmod.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        a[0], 0, stdout="hello from the screen\n", stderr=""))
    assert Phone.ocr_text(ph) == "hello from the screen\n"
    assert not seen["path"].exists()                  # the temp capture is gone


def test_ocr_returns_nothing_for_a_blacked_out_frame(dev, monkeypatch):
    from phone import Phone, device as devmod
    ph = t.make_phone(device=dev)
    ph.precheck = lambda **kw: {}

    class Red:
        def screenshot(self, d, path):
            return 3

    monkeypatch.setattr(devmod.redact, "get", lambda optional=False: Red())
    monkeypatch.setattr(devmod.shutil, "which", lambda name: "/usr/bin/tesseract")
    assert Phone.ocr_text(ph) == ""


def test_ocr_without_tesseract_fails_closed(dev, monkeypatch):
    from phone import Phone, device as devmod
    from phone.errors import RedactorUnavailable
    ph = t.make_phone(device=dev)
    ph.precheck = lambda **kw: {}
    monkeypatch.setattr(devmod.shutil, "which", lambda name: None)
    with pytest.raises(RedactorUnavailable):
        Phone.ocr_text(ph)


def test_an_empty_selector_is_refused_not_matched_to_everything(ph):
    with pytest.raises(ValueError, match="needs at least one"):
        ph.find()
    with pytest.raises(ValueError, match="unknown selector"):
        ph.find(colour="red")
    assert ph.find(desc="Menu") is not None


# open a chat by title (reading only) ---------------------------------------------------------

def test_open_title_goes_through_the_drawer_search(ph, dev):
    dev.screen = "new"
    assert ChatGPT().open_title(ph, "Existing chat one") is True
    assert dev.screen == "chat" and dev.sent == []
    assert dev.texts["search"] == "Existing chat one"
    assert "composer" not in dev.texts or dev.texts["composer"] == ""   # never typed into the composer


def test_open_title_from_the_launcher_and_from_search(ph, dev):
    assert ChatGPT().open_title(ph, "Another chat") is True and dev.screen == "chat"
    dev.screen = "search"
    dev.texts["search"] = ""
    assert ChatGPT().open_title(ph, "Another chat") is True


def test_open_title_unknown_title_returns_false_and_sends_nothing(ph, dev):
    assert ChatGPT().open_title(ph, "No such chat") is False
    assert dev.screen == "search" and dev.sent == []


def test_open_title_refuses_when_the_composer_has_focus(ph, dev, monkeypatch):
    a = ChatGPT()
    monkeypatch.setattr(a, "drawer", lambda _ph: None)
    dev.screen = "new"                      # composer screen: Ask ChatGPT visible, no Search
    dev.elements_orig = dev.elements
    monkeypatch.setattr(dev, "elements", lambda: dev.elements_orig() + [t.el(desc="Search", click="new")])
    with pytest.raises(RuntimeError, match="composer"):
        a.open_title(ph, "Existing chat one")
    assert dev.texts.get("composer", "") == ""


def test_open_title_rejects_an_empty_title(ph):
    with pytest.raises(ValueError):
        ChatGPT().open_title(ph, "  ")


def test_read_with_a_missing_title_is_a_lookup_error(ph, dev):
    with pytest.raises(LookupError, match="exact title"):
        ChatGPT().read(ph, title="No such chat")
