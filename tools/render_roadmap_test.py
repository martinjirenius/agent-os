"""Colocated tests for render_roadmap.py — built against throwaway git repos, never this one's.

Run: python3 -m pytest tools/render_roadmap_test.py -q
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import render_roadmap  # noqa: E402


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    return repo


def _commit(repo: Path, name: str, message: str) -> None:
    (repo / name).write_text(message)
    _git(repo, "add", name)
    r = _git(repo, "commit", "-q", "-m", message)
    assert r.returncode == 0, r.stderr


MANIFEST = """
[project]
name = "fixture"
kind = "tool"

[[deliverables]]
id = "D-01"
title = "one"
depends = []

[[deliverables]]
id = "D-02"
title = "two"
depends = ["D-01"]

[[deliverables]]
id = "D-03"
title = "three"
depends = ["D-02"]
"""


def _fixture(tmp_path: Path) -> Path:
    """D-01 landed. D-02 in progress (a done commit but an open card). D-03 blocked."""
    repo = _init_repo(tmp_path)
    (repo / "project.toml").write_text(MANIFEST)
    _commit(repo, "a.txt", "found it\n\nSession: 2026-08-02-a\nServes: D-01")
    _commit(repo, "b.txt",
            "B-001: x\n\nSession: 2026-08-02-b\nCard: B-001\nServes: D-02\nDisposition: done\n"
            "Chose: the narrow fix over the general one")
    _commit(repo, "c.txt",
            "B-002: y\n\nSession: 2026-08-02-b\nCard: B-002\nServes: D-02\n"
            "Question: should this ship before the pilot?")
    (repo / "backlog").mkdir()
    (repo / "backlog" / "B-002.md").write_text(
        "---\nid: B-002\ntitle: still open\nstatus: doing\nserves: D-02\nopened: 2026-08-02\n"
        "---\n\nbody\n"
    )
    return repo


def _html(tmp_path: Path) -> str:
    repo = _fixture(tmp_path)
    out = render_roadmap.build(repo)
    return out


def test_every_declared_deliverable_appears(tmp_path):
    html = _html(tmp_path)
    for did in ("D-01", "D-02", "D-03"):
        assert did in html, f"{did} vanished from the page"


def test_states_are_rendered_not_invented(tmp_path):
    html = _html(tmp_path)
    assert "s-landed" in html      # D-01
    assert "s-doing" in html       # D-02, open card
    assert "s-blocked" in html     # D-03, dependency not landed


def test_open_card_is_visible_at_zoom_2(tmp_path):
    html = _html(tmp_path)
    assert "B-002" in html
    assert "still open" in html


def test_decision_inbox_is_on_the_same_page(tmp_path):
    # "One page" is the product criterion — a question living in a separate tool is the
    # failure mode this whole card exists to fix.
    html = _html(tmp_path)
    assert "should this ship before the pilot?" in html
    assert "the narrow fix over the general one" in html


def test_insufficient_velocity_is_stated_not_faked(tmp_path):
    # Two sessions observed, three needed. The page must say so rather than draw a date.
    html = _html(tmp_path)
    assert "insufficient" in html.lower()


def test_page_is_self_contained(tmp_path):
    html = _html(tmp_path)
    for forbidden in ("http://", "https://", "<link", "cdn."):
        assert forbidden not in html, f"page reached outside itself via {forbidden!r}"


def test_titles_are_escaped(tmp_path):
    repo = _fixture(tmp_path)
    (repo / "backlog" / "B-003.md").write_text(
        "---\nid: B-003\ntitle: \"<img src=x onerror=alert(1)>\"\nstatus: todo\n"
        "serves: D-02\nopened: 2026-08-02\n---\n\nbody\n"
    )
    html = render_roadmap.build(repo)
    assert "<img src=x" not in html
    assert "&lt;img src=x" in html


def test_build_is_deterministic(tmp_path):
    repo = _fixture(tmp_path)
    assert render_roadmap.build(repo) == render_roadmap.build(repo)


def test_write_creates_out_dir_and_returns_path(tmp_path):
    repo = _fixture(tmp_path)
    path = render_roadmap.write(repo)
    assert path == repo / "out" / "roadmap.html"
    assert path.exists()
    assert path.read_text().startswith("<!doctype html>")
