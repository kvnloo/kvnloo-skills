"""App adapter contract.

An adapter knows ONE app's screens: how to reach a fresh composer, how to send, how to tell that the
app is still generating, how to read what is on screen, and how to leave the app tidy. It is driven
through a `phone.Phone` (lock, owner checks, redaction, receipts) and never opens its own adb or
uiautomator2 connection.

Adapters fail loudly rather than guess: when a selector is missing they raise, they do not tap a
neighbour.
"""
from __future__ import annotations

from ..quota import Cooldown, QuotaPause


class Adapter:
    name: str = ""
    package: str = ""
    cooldown_s: float = 5.0
    quota: QuotaPause | None = None

    def cooldown(self, role: str) -> Cooldown:
        return Cooldown(self.name, role, self.cooldown_s)

    def validate_tag(self, tag: str) -> None:
        """Raise ValueError when a tag cannot be recognised later as our own residue."""

    def prepare_text(self, tag: str, text: str) -> str:
        """Return the text to send (adapters may add the marker their residue check needs)."""
        return text

    # navigation and sending
    def new_chat(self, ph, **kw):
        raise NotImplementedError

    def send(self, ph, box, text, receipt=None, preflight=False, **kw):
        raise NotImplementedError

    def launch(self, ph, tag, text, **kw) -> dict:
        """One brief, end to end, returning a receipt dict with a status."""
        raise NotImplementedError

    # observation
    def is_generating(self, ph) -> bool:
        raise NotImplementedError

    def state(self, ph) -> dict:
        raise NotImplementedError

    def read(self, ph, long: bool = False) -> dict:
        raise NotImplementedError

    def restore(self, ph) -> None:
        raise NotImplementedError

    def rate_limit_hits(self, hierarchy_lower: str, own_text_lower: str) -> list[str]:
        return []
