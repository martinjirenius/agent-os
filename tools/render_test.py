"""Colocated tests for render.py — the HTML primitives every surface renderer shares.

Run: python3 -m pytest tools/render_test.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import render  # noqa: E402


def test_esc_neutralises_markup():
    assert render.esc("<script>alert(1)</script>") == "&lt;script&gt;alert(1)&lt;/script&gt;"
    assert render.esc('a "b" & c') == "a &quot;b&quot; &amp; c"


def test_inline_renders_code_and_bold_but_escapes_first():
    # The escape must happen before the markdown substitution, or a card title containing
    # markup would reach the page as live HTML.
    assert render.inline("`git log`") == "<code>git log</code>"
    assert render.inline("**slip**") == "<strong>slip</strong>"
    assert "<em>" not in render.inline("<em>raw</em>")
    assert render.inline("<em>raw</em>").startswith("&lt;em&gt;")


def test_page_is_self_contained():
    html = render.page("T", "<p>body</p>")
    assert html.startswith("<!doctype html>")
    assert "<title>T</title>" in html
    assert "<p>body</p>" in html
    # No external fetches of any kind: the page must open from file://.
    for forbidden in ("http://", "https://", "//cdn", "<link", "src="):
        assert forbidden not in html, f"page reached outside itself via {forbidden!r}"


def test_page_embeds_css_and_js_inline():
    html = render.page("T", "")
    assert "<style>" in html and "</style>" in html
    assert "<script>" in html and "</script>" in html


def test_page_is_deterministic():
    # Same inputs, same bytes — no clock, no randomness anywhere in the skeleton.
    assert render.page("T", "<p>x</p>") == render.page("T", "<p>x</p>")


def test_bar_clamps_out_of_range_fractions():
    assert render.bar_pct(-5.0) == 0.0
    assert render.bar_pct(500.0) == 100.0
    assert render.bar_pct(50.0) == 50.0
