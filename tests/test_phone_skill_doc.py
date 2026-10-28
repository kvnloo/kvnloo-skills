"""SKILL.md contract and the public-repo hygiene scan (no host-specific values anywhere)."""
from __future__ import annotations

import os
import re
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1] / "device-automation" / "phone-driving"
SKILL_MD = SKILL_DIR / "SKILL.md"
TESTS = Path(__file__).resolve().parent


def text() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


def frontmatter(name: str) -> str:
    m = re.search(rf"^{re.escape(name)}:\s*(.+)$", text(), re.MULTILINE)
    assert m, f"missing {name}"
    return m.group(1).strip().strip('"')


def test_frontmatter():
    assert frontmatter("name") == "phone-driving"
    d = frontmatter("description")
    assert len(d) <= 60 and d.endswith(".")
    assert frontmatter("license") == "MIT"


def test_required_sections_in_order():
    sections = ["## When to Use", "## Safety Rules", "## Prerequisites", "## How to Run",
                "## Commands", "## Examples", "## Adapters", "## Guard", "## Pitfalls"]
    pos = [text().find(s) for s in sections]
    assert all(p >= 0 for p in pos), [s for s, p in zip(sections, pos, strict=True) if p < 0]
    assert pos == sorted(pos)


def test_safety_rules_are_stated_plainly():
    body = text()
    for must in ("never write raw uiautomator2", "host UI lock", "owner", "set_text",
                 "never install", "S25", "--i-mean-it", "redact", "PhoneGuardError",
                 "never use the clipboard"):
        assert must.lower() in body.lower(), must


def test_every_cli_command_is_documented():
    from phone import cli
    sub = next(a for a in cli.build_parser()._actions if a.dest == "cmd")
    for name in sub.choices:
        assert f"phone {name}" in text() or f"`{name}`" in text(), name


# Patterns are assembled from pieces so this file does not match itself.
FORBIDDEN = {
    "ipv4": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "tailnet name": re.compile(r"\.ts" + r"\.net\b|\btail[0-9a-f]{6,}\b"),
    "home path": re.compile(r"/ho" + r"me/[A-Za-z0-9_.-]+"),
    "mnt path": re.compile(r"/m" + r"nt/[A-Za-z0-9_.-]+"),
    "mdns serial": re.compile(r"\badb-[A-Z0-9]{8,}-"),
    "samsung serial": re.compile(r"\b[RS][0-9A-Z]{2}[A-Z0-9]{3}[0-9][A-Z0-9]{4}\b"),
    "token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}|\bsk-[A-Za-z0-9]{20,}"),
}


def public_files():
    for root in (SKILL_DIR, TESTS):
        for p in sorted(root.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts and p.suffix not in (".pyc", ".png"):
                if root is TESTS and not p.name.startswith(("test_phone", "phone_test", "conftest")):
                    continue
                yield p


def test_no_host_specific_values_in_the_public_tree():
    hits = []
    for p in public_files():
        if p.name == "test_phone_skill_doc.py":
            continue
        body = p.read_text(encoding="utf-8", errors="replace")
        for label, rx in FORBIDDEN.items():
            for m in rx.finditer(body):
                if label == "ipv4" and m.group().startswith(("0.0.", "127.")):
                    continue
                hits.append(f"{p.name}: {label}")
    assert not hits, sorted(set(hits))


def test_owner_denylist_if_provided():
    """PHONE_PUBLIC_DENYLIST names a private file of literals (one per line) that must not appear."""
    path = os.environ.get("PHONE_PUBLIC_DENYLIST")
    if not path:
        return
    literals = [ln.strip() for ln in Path(path).read_text().splitlines() if ln.strip()]
    hits = []
    for p in public_files():
        body = p.read_text(encoding="utf-8", errors="replace")
        hits += [f"{p.name}: denylist entry #{i}" for i, lit in enumerate(literals) if lit in body]
    assert not hits, hits
