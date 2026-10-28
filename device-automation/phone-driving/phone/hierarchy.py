"""Accessibility hierarchy parsing, text extraction, and long-content stitching. Pure functions."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass


@dataclass(frozen=True)
class Node:
    text: str
    desc: str
    res_id: str
    cls: str
    pkg: str
    bounds: tuple  # (left, top, right, bottom)
    clickable: bool = False
    enabled: bool = True
    focused: bool = False
    password: bool = False
    scrollable: bool = False

    @property
    def center(self) -> tuple:
        l, t, r, b = self.bounds
        return ((l + r) // 2, (t + b) // 2)

    @property
    def label(self) -> str:
        return self.text or self.desc


_BOUNDS = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")


def parse_bounds(value: str) -> tuple:
    m = _BOUNDS.fullmatch(value or "")
    return tuple(int(x) for x in m.groups()) if m else (0, 0, 0, 0)


def parse(xml: str) -> list[Node]:
    out = []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return out
    for n in root.iter("node"):
        out.append(Node(
            text=n.get("text", "") or "", desc=n.get("content-desc", "") or "",
            res_id=n.get("resource-id", "") or "", cls=n.get("class", "") or "",
            pkg=n.get("package", "") or "", bounds=parse_bounds(n.get("bounds", "")),
            clickable=n.get("clickable") == "true", enabled=n.get("enabled", "true") == "true",
            focused=n.get("focused") == "true", password=n.get("password") == "true",
            scrollable=n.get("scrollable") == "true"))
    return out


def redacted_marker(xml: str) -> str | None:
    """The redactor returns <hierarchy redacted="..."/> for sensitive apps and fail-closed dumps."""
    m = re.search(r'<hierarchy[^>]*\bredacted="([^"]*)"', xml or "")
    return m.group(1) if m else None


def inside(node: Node, box: tuple | None, min_fraction: float = 0.5) -> bool:
    """True when at least min_fraction of the node's area lies inside box."""
    if box is None:
        return True
    l, t, r, b = node.bounds
    area = max(0, r - l) * max(0, b - t)
    if area == 0:
        return box[0] <= l <= box[2] and box[1] <= t <= box[3]
    il, it = max(l, box[0]), max(t, box[1])
    ir, ib = min(r, box[2]), min(b, box[3])
    return max(0, ir - il) * max(0, ib - it) >= min_fraction * area


def text_entries(nodes: list[Node], *, box: tuple | None = None, include_desc: bool = True,
                 order: str = "visual") -> list[tuple]:
    """Visible (label, bounds) pairs, one per labelled node, optionally limited to a box.

    order="visual" sorts by (top, left); "tree" keeps hierarchy order. Consecutive duplicate labels
    collapse. A node's content description is used only when it has no text of its own."""
    picked = []
    for n in nodes:
        if not inside(n, box):
            continue
        label = n.text.strip() or (n.desc.strip() if include_desc else "")
        if label:
            picked.append((n.bounds[1], n.bounds[0], label, n.bounds))
    if order == "visual":
        picked.sort(key=lambda x: (x[0], x[1]))
    entries: list[tuple] = []
    for _, _, label, bounds in picked:
        if not entries or entries[-1][0] != label:
            entries.append((label, bounds))
    return entries


def text_lines(nodes: list[Node], **kw) -> list[str]:
    """Visible text, one line per labelled node. See text_entries for the options."""
    return [label for label, _ in text_entries(nodes, **kw)]


def find_label(nodes: list[Node], label: str) -> Node | None:
    """cgdrv rule: an exact match on text or description wins, else the first case-insensitive
    substring match over text plus description."""
    labelled = [n for n in nodes if n.text or n.desc]
    exact = [n for n in labelled if label in (n.text, n.desc)]
    part = [n for n in labelled if label.lower() in (n.text + " " + n.desc).lower()]
    return (exact or part or [None])[0]


# stitching -------------------------------------------------------------------------------------

def stitch(acc: list[str], page: list[str]) -> tuple[list[str], int, bool]:
    """Append `page` to `acc`, dropping the overlap between acc's tail and page's head.

    Returns (lines, added, overlapped). `overlapped` is False when acc is non-empty and no overlap was
    found, which means a scroll may have skipped content. A page already contained in acc's recent
    tail adds nothing."""
    if not page:
        return acc, 0, True
    if not acc:
        return list(page), len(page), True
    window = acc[-(len(page) * 2 + 8):]
    for start in range(len(window) - len(page) + 1):
        if window[start:start + len(page)] == page:
            return acc, 0, True
    for k in range(min(len(acc), len(page)), 0, -1):
        if acc[-k:] == page[:k]:
            return acc + page[k:], len(page) - k, True
    return acc + page, len(page), False


def sticky_entries(pages: list[list[tuple]]) -> set:
    """(label, bounds) pairs that stay put while the rest of the page scrolls: headers, footers,
    floating buttons. Only consecutive pages that actually differ count as evidence, so a screen
    that did not scroll at all marks nothing as sticky."""
    sticky: set = set()
    for prev, cur in zip(pages, pages[1:], strict=False):
        if cur != prev:
            sticky |= set(prev) & set(cur)
    return sticky


def stitch_pages(pages: list[list[tuple]]) -> tuple[list[str], int, list[str]]:
    """Stitch scrolled pages of (label, bounds) entries into one list of lines.

    Sticky entries are removed from the body (they would otherwise sit in the middle of the text and
    defeat the overlap match) and returned separately. Returns (lines, gaps, sticky_lines); `gaps` counts
    pages that share nothing with the text before them, meaning a scroll may have skipped content."""
    sticky = sticky_entries(pages)
    acc: list[str] = []
    gaps = 0
    for i, page in enumerate(pages):
        body = [label for label, bounds in page if (label, bounds) not in sticky]
        acc, _added, overlapped = stitch(acc, body)
        if i > 0 and not overlapped:
            gaps += 1
    seen, sticky_lines = set(), []
    for page in pages:
        for label, bounds in page:
            if (label, bounds) in sticky and (label, bounds) not in seen:
                seen.add((label, bounds))
                sticky_lines.append(label)
    return acc, gaps, sticky_lines


@dataclass
class LongRead:
    lines: list
    steps: int
    complete: bool
    reason: str
    gaps: int = 0
    sticky: list | None = None

    @property
    def text(self) -> str:
        return "\n".join(self.lines)
