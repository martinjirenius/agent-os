#!/usr/bin/env python3
"""render_dag.py — the deliverable DAG as an inline SVG map: columns are dependency depth.

docs/04-surfaces.md:20 asks for "deliverables as a DAG flowing left to right over time", and a
vertical list of rows is not that: it renders a straight chain and a forking graph identically,
so the one thing worth seeing — where work splits and where it merges — is exactly what a list
hides. agent-os's own plan forks at D-02 (into D-03 and D-04) and merges at D-05; on a list
that shape is invisible.

Layout is layered and deterministic, in two pure functions so the geometry is testable without
a browser or a repo:

  - `layout()`  — column = `roadmap.level()` (topological depth, imported not reimplemented:
                  axiom 4), row = first free slot in that column, scanning declaration order.
  - `svg()`     — nodes and cubic-bezier edges at those coordinates.

Emitted as inline SVG rather than a canvas or a chart library: it stays self-contained, it
scales without blurring, every node is a real DOM element a click handler can find, and it
still renders with JavaScript off.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import render  # noqa: E402
import roadmap  # noqa: E402

NODE_W = 168
NODE_H = 58
H_GAP = 54
V_GAP = 20
PAD = 12
TITLE_CHARS = 24


@dataclass
class Pos:
    col: int
    row: int
    x: int
    y: int


def _wrap(text: str, width: int, max_lines: int) -> list[str]:
    """Greedy word wrap with an ellipsis on overflow. SVG `<text>` does not wrap, so this is
    done here rather than hoped for; truncating visibly beats a title running off the node."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word
        if len(lines) == max_lines:
            break
    if current and len(lines) < max_lines:
        lines.append(current)
    consumed = sum(len(line.split()) for line in lines)
    if consumed < len(words) and lines:
        lines[-1] = lines[-1][: max(0, width - 1)].rstrip() + "…"
    return lines


def layout(statuses: list[roadmap.Status]) -> dict[str, Pos]:
    """Assign every deliverable a column (dependency depth) and a row (first free slot).

    Column comes straight from `roadmap.level`, so the map and the terminal agree on what
    depends on what. Rows are packed per column in declaration order — project.toml's order is
    a deliberate reading order, and reordering nodes for prettier edges would trade the
    author's intent for cosmetics."""
    by_id = {s.id: roadmap.Deliverable(s.id, s.title, s.depends) for s in statuses}
    used: dict[int, int] = {}
    pos: dict[str, Pos] = {}
    for s in statuses:
        col = roadmap.level(s.id, by_id)
        row = used.get(col, 0)
        used[col] = row + 1
        pos[s.id] = Pos(col=col, row=row,
                        x=PAD + col * (NODE_W + H_GAP),
                        y=PAD + row * (NODE_H + V_GAP))
    return pos


def extent(pos: dict[str, Pos]) -> tuple[int, int]:
    """(width, height) of the canvas, with padding on the far edges too."""
    if not pos:
        return (PAD * 2, PAD * 2)
    width = max(p.x for p in pos.values()) + NODE_W + PAD
    height = max(p.y for p in pos.values()) + NODE_H + PAD
    return width, height


def _edge(a: Pos, b: Pos, key: str) -> str:
    """A cubic bezier from the right edge of the parent to the left edge of the child. The
    control points are pulled horizontally so lines leave and arrive flat — that reads as a
    road merging rather than a wire, which is the whole point of drawing it."""
    x1, y1 = a.x + NODE_W, a.y + NODE_H // 2
    x2, y2 = b.x, b.y + NODE_H // 2
    dx = max(24, (x2 - x1) // 2)
    return (f'<path class="edge" data-edge="{render.esc(key)}" '
            f'd="M{x1},{y1} C{x1 + dx},{y1} {x2 - dx},{y2} {x2},{y2}" />')


def _node(s: roadmap.Status, p: Pos, is_here: bool) -> str:
    cls = render.STATE_CLASS.get(s.state, "s-blocked")
    here = " n-here" if is_here else ""
    lines = _wrap(s.title, TITLE_CHARS, 2)
    text = "".join(
        f'<tspan x="{p.x + 11}" dy="{13 if i else 0}">{render.esc(line)}</tspan>'
        for i, line in enumerate(lines)
    )
    return (
        f'<g class="node {cls}{here}" data-node="{render.esc(s.id)}" tabindex="0">'
        f'<rect x="{p.x}" y="{p.y}" width="{NODE_W}" height="{NODE_H}" rx="7" />'
        f'<rect class="edgeband" x="{p.x}" y="{p.y}" width="4" height="{NODE_H}" />'
        f'<text class="nid" x="{p.x + 11}" y="{p.y + 18}">{render.esc(s.id)}</text>'
        f'<text class="ntitle" x="{p.x + 11}" y="{p.y + 34}">{text}</text>'
        f"<title>{render.esc(f'{s.id} — {s.title} ({s.state})')}</title>"
        "</g>"
    )


def svg(statuses: list[roadmap.Status], pos: dict[str, Pos], here_id: str | None) -> str:
    """The map. Edges are drawn first so nodes paint over them, never the reverse."""
    if not statuses:
        return '<p class="empty">no deliverables to map.</p>'
    width, height = extent(pos)
    by_id = {s.id: s for s in statuses}
    edges = [
        # Separator is `..`, not `->`: the key lands in an attribute, and `>` would be
        # escaped to `&gt;`, making the edge un-greppable in the generated page.
        _edge(pos[dep], pos[s.id], f"{dep}..{s.id}")
        for s in statuses for dep in s.depends
        if dep in pos and dep in by_id
    ]
    nodes = [_node(s, pos[s.id], s.id == here_id) for s in statuses]
    return (
        f'<div class="scroll map"><svg viewBox="0 0 {width} {height}" width="{width}" '
        f'height="{height}" role="img" aria-label="deliverable dependency map">'
        f'{"".join(edges)}{"".join(nodes)}</svg></div>'
    )


def build(statuses: list[roadmap.Status], here_id: str | None) -> str:
    """Convenience: layout + svg in one call, for renderers that need no custom geometry."""
    return svg(statuses, layout(statuses), here_id)
