"""Colocated tests for render_dag.py — layout math is pure, so it is tested without a repo.

Run: python3 -m pytest tools/render_dag_test.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import render_dag  # noqa: E402
import roadmap  # noqa: E402


def _statuses() -> list[roadmap.Status]:
    """The shape that exposed the bug: D-02 forks into D-03 and D-04, which merge into D-05.
    A vertical list renders this identically to a straight chain — the graph must not."""
    spec = [
        ("D-01", [], "landed"),
        ("D-02", ["D-01"], "landed"),
        ("D-03", ["D-02"], "landed"),
        ("D-04", ["D-02"], "landed"),
        ("D-05", ["D-03", "D-04"], "in_progress"),
        ("D-06", ["D-05"], "frontier"),
        ("D-07", ["D-06"], "blocked"),
    ]
    return [roadmap.Status(id=i, title=f"title {i}", depends=d, state=s,
                           first_date=None, last_date=None, sessions=[], open_cards=[])
            for i, d, s in spec]


def test_column_is_topological_depth():
    pos = render_dag.layout(_statuses())
    assert pos["D-01"].col == 0
    assert pos["D-02"].col == 1
    assert pos["D-03"].col == 2
    assert pos["D-04"].col == 2      # sibling of D-03, same column
    assert pos["D-05"].col == 3      # merge point, past BOTH parents
    assert pos["D-07"].col == 5


def test_siblings_get_distinct_rows():
    pos = render_dag.layout(_statuses())
    assert pos["D-03"].row != pos["D-04"].row, "the fork collapsed onto one line"


def test_single_chain_stays_on_one_row():
    chain = [roadmap.Status(id=f"D-0{i}", title="t", depends=([f"D-0{i-1}"] if i > 1 else []),
                            state="landed", first_date=None, last_date=None,
                            sessions=[], open_cards=[]) for i in range(1, 4)]
    pos = render_dag.layout(chain)
    assert {p.row for p in pos.values()} == {0}


def test_every_deliverable_is_placed():
    statuses = _statuses()
    pos = render_dag.layout(statuses)
    assert set(pos) == {s.id for s in statuses}


def test_svg_draws_one_node_per_deliverable():
    statuses = _statuses()
    svg = render_dag.svg(statuses, render_dag.layout(statuses), here_id="D-05")
    for s in statuses:
        assert f'data-node="{s.id}"' in svg, f"{s.id} missing from the graph"


def test_svg_draws_an_edge_per_dependency():
    statuses = _statuses()
    svg = render_dag.svg(statuses, render_dag.layout(statuses), here_id=None)
    # D-05 has two parents — both connectors must be drawn, or the merge is invisible.
    assert svg.count('data-edge="D-03..D-05"') == 1
    assert svg.count('data-edge="D-04..D-05"') == 1
    total = sum(len(s.depends) for s in statuses)
    assert svg.count("data-edge=") == total


def test_viewbox_contains_every_node():
    statuses = _statuses()
    pos = render_dag.layout(statuses)
    svg = render_dag.svg(statuses, pos, here_id=None)
    width, height = render_dag.extent(pos)
    assert f'viewBox="0 0 {width} {height}"' in svg
    for p in pos.values():
        assert p.x + render_dag.NODE_W <= width
        assert p.y + render_dag.NODE_H <= height


def test_here_is_marked():
    statuses = _statuses()
    svg = render_dag.svg(statuses, render_dag.layout(statuses), here_id="D-05")
    assert "n-here" in svg


def test_titles_are_escaped():
    s = [roadmap.Status(id="D-01", title="<img src=x onerror=alert(1)>", depends=[],
                        state="landed", first_date=None, last_date=None,
                        sessions=[], open_cards=[])]
    svg = render_dag.svg(s, render_dag.layout(s), here_id=None)
    assert "<img src=x" not in svg
    assert "&lt;img" in svg


def test_svg_is_deterministic():
    statuses = _statuses()
    pos = render_dag.layout(statuses)
    assert render_dag.svg(statuses, pos, "D-05") == render_dag.svg(statuses, pos, "D-05")


def test_wrap_truncates_rather_than_overflowing():
    lines = render_dag._wrap("one two three four five six seven eight", 12, 2)
    assert len(lines) <= 2
    assert lines[-1].endswith("…")
