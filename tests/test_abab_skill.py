"""Contract tests for the ABAB skill document."""

from __future__ import annotations

import re
from pathlib import Path

SKILL_MD = (
    Path(__file__).resolve().parents[1]
    / "research"
    / "abab-meta-research"
    / "SKILL.md"
)


def _text() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


def _frontmatter_value(name: str) -> str:
    match = re.search(rf"^{re.escape(name)}:\s*(.+)$", _text(), re.MULTILINE)
    assert match, f"missing {name}"
    return match.group(1).strip().strip('"')


def test_frontmatter_trigger():
    assert _frontmatter_value("name") == "abab-meta-research"
    d = _frontmatter_value("description")
    assert len(d) <= 60
    assert d.endswith(".")
    assert "ABAB" in d


def test_sections_in_order():
    sections = [
        "## When to Use",
        "## Prerequisites",
        "## How to Run",
        "## Quick Reference",
        "## Procedure",
        "## Pitfalls",
        "## Verification",
    ]
    pos = [_text().index(s) for s in sections]
    assert pos == sorted(pos)


def test_anti_patterns_named():
    body = _text()
    for needle in (
        "Search → summarize → search",
        "NO_UPDATE",
        "causal mechanism maps",
        "/learn",
        "Budget is a cap, not a quota",
    ):
        assert needle in body


def test_composes_instead_of_monolith():
    body = _text()
    assert "grounded-citations" in body
    assert "high-parallel-evidence-tournaments" in body
    assert "Do not duplicate" in body
