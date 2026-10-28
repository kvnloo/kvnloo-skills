"""Hierarchy parsing, text extraction and long-content stitching (pure functions)."""
from __future__ import annotations

from phone import hierarchy as h


def xml(*nodes):
    body = "".join(nodes)
    return f"<?xml version='1.0'?><hierarchy>{body}</hierarchy>"


def node(text="", desc="", top=0, left=0, bottom=None, right=100, pkg="com.example.app",
         cls="android.widget.TextView", **attrs):
    bottom = top + 40 if bottom is None else bottom
    extra = "".join(f' {k}="{v}"' for k, v in attrs.items())
    return (f'<node class="{cls}" package="{pkg}" text="{text}" content-desc="{desc}" '
            f'resource-id="" bounds="[{left},{top}][{right},{bottom}]"{extra}/>')


def test_parse_reads_labels_bounds_and_flags():
    nodes = h.parse(xml(node("Hello", top=10, clickable="true"),
                        node(desc="Send", top=60, enabled="false", focused="true"),
                        node("secret", password="true")))
    assert [n.label for n in nodes] == ["Hello", "Send", "secret"]
    assert nodes[0].clickable and not nodes[1].enabled and nodes[1].focused and nodes[2].password
    assert nodes[0].center == (50, 30)
    assert nodes[0].bounds == (0, 10, 100, 50)


def test_parse_survives_garbage():
    assert h.parse("not xml") == []
    assert h.parse(xml()) == []


def test_redacted_marker():
    assert h.redacted_marker('<hierarchy redacted="sensitive app com.x"/>') == "sensitive app com.x"
    assert h.redacted_marker(xml(node("a"))) is None


def test_text_lines_orders_visually_and_drops_consecutive_duplicates():
    nodes = h.parse(xml(node("second", top=200), node("first", top=100), node("first", top=101),
                        node(desc="Icon label", top=300), node("", "", top=400)))
    assert h.text_lines(nodes) == ["first", "second", "Icon label"]
    assert h.text_lines(nodes, include_desc=False) == ["first", "second"]
    assert h.text_lines(nodes, order="tree")[0] == "second"


def test_desc_is_used_only_when_there_is_no_text():
    nodes = h.parse(xml(node("Visible", desc="Ignored description")))
    assert h.text_lines(nodes) == ["Visible"]


def test_box_limits_to_a_container():
    nodes = h.parse(xml(node("inside", top=110, bottom=140), node("above", top=10, bottom=40),
                        node("half in", top=95, bottom=135)))
    # "half in" has 35 of its 40 px inside the box (>= half), "above" has none
    assert h.text_lines(nodes, box=(0, 100, 100, 200)) == ["half in", "inside"]


def test_find_label_prefers_exact_over_substring():
    nodes = h.parse(xml(node("Send message", top=10), node("Send", top=60), node(desc="send now", top=90)))
    assert h.find_label(nodes, "Send").label == "Send"
    assert h.find_label(nodes, "now").label == "send now"
    assert h.find_label(nodes, "absent") is None


# stitching ------------------------------------------------------------------------------------

def test_stitch_drops_the_overlap():
    acc, added, ok = h.stitch(["a", "b", "c"], ["b", "c", "d", "e"])
    assert acc == ["a", "b", "c", "d", "e"] and added == 2 and ok


def test_stitch_first_page_and_empty_page():
    assert h.stitch([], ["a", "b"]) == (["a", "b"], 2, True)
    assert h.stitch(["a"], []) == (["a"], 0, True)


def test_stitch_flags_a_gap_when_nothing_overlaps():
    acc, added, ok = h.stitch(["a", "b"], ["x", "y"])
    assert acc == ["a", "b", "x", "y"] and added == 2 and ok is False


def test_stitch_page_already_seen_adds_nothing():
    acc, added, ok = h.stitch(["a", "b", "c", "d"], ["b", "c"])
    assert acc == ["a", "b", "c", "d"] and added == 0 and ok


def test_stitch_prefers_the_longest_overlap():
    acc, added, _ = h.stitch(["x", "a", "b", "a", "b"], ["a", "b", "a", "b", "c"])
    assert acc == ["x", "a", "b", "a", "b", "c"] and added == 1


def test_a_whole_document_is_reconstructed_from_scrolled_pages():
    doc = [f"line {i:02d}" for i in range(40)]
    pages, pos = [], 0
    while True:
        pages.append(doc[pos:pos + 12])
        if pos + 12 >= len(doc):
            break
        pos += 9   # each scroll moves nine lines, three lines overlap
    acc, gaps = [], 0
    for i, page in enumerate(pages):
        acc, _added, ok = h.stitch(acc, page)
        gaps += 0 if ok or i == 0 else 1
    assert acc == doc and gaps == 0


def test_longread_text_joins_lines():
    lr = h.LongRead(lines=["a", "b"], steps=2, complete=True, reason="end of content")
    assert lr.text == "a\nb"


# sticky elements (a real finding: a fixed footer chip defeated the overlap match) ----------------

def entry(label, top):
    return (label, (0, top, 100, top + 40))


def test_sticky_footer_is_removed_and_the_scroll_is_stitched():
    footer = entry("AB", 2172)                         # fixed at the bottom of every page
    page0 = [entry("one", 227), entry("two", 348), entry("three", 474), footer]
    page1 = [entry("three", 266), entry("four", 392), footer]   # scrolled by 208 px
    lines, gaps, sticky = h.stitch_pages([page0, page1])
    assert lines == ["one", "two", "three", "four"] and gaps == 0 and sticky == ["AB"]


def test_without_sticky_removal_the_naive_stitch_reports_a_gap():
    footer = "AB"
    acc, _, _ = h.stitch([], ["one", "two", "three", footer])
    acc, _, overlapped = h.stitch(acc, ["three", "four", footer])
    assert overlapped is False


def test_a_screen_that_never_scrolled_marks_nothing_sticky():
    page = [entry("only", 100), entry("page", 200)]
    lines, gaps, sticky = h.stitch_pages([page, list(page), list(page)])
    assert lines == ["only", "page"] and gaps == 0 and sticky == []


def test_header_and_footer_with_three_pages():
    head, foot = entry("Title", 50), entry("Compose", 2200)
    p0 = [head, entry("a", 200), entry("b", 400), entry("c", 600), foot]
    p1 = [head, entry("c", 200), entry("d", 400), entry("e", 600), foot]
    p2 = [head, entry("e", 300), entry("f", 500), foot]
    lines, gaps, sticky = h.stitch_pages([p0, p1, p2])
    assert lines == list("abcdef") and gaps == 0 and sorted(sticky) == ["Compose", "Title"]


def test_a_skipped_page_is_reported_as_a_gap():
    p0 = [entry("a", 100), entry("b", 200)]
    p1 = [entry("x", 100), entry("y", 200)]            # nothing in common: content was skipped
    lines, gaps, _ = h.stitch_pages([p0, p1])
    assert lines == ["a", "b", "x", "y"] and gaps == 1


def test_text_entries_keep_bounds_and_collapse_duplicates():
    nodes = h.parse(xml(node("x", top=10), node("x", top=11), node("y", top=60)))
    assert [e[0] for e in h.text_entries(nodes)] == ["x", "y"]
    assert h.text_entries(nodes)[0][1] == (0, 10, 100, 50)
