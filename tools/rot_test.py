#!/usr/bin/env python3
"""Tests for rot.py — colocated per CLAUDE.md, run with `pytest tools/rot_test.py`.

Builds real throwaway git repos under tmp_path (not mocks — under-mock per
docs/03-practices.md) so every signal runs against real files and real `git log`, never
against this repo's own paths (these tools ship into other projects, D-07).
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

import rot


def _git(cwd: Path, *args: str, date: str | None = None) -> None:
    env = None
    if date:
        env = {**os.environ, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
    subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=True)


def make_clean_repo(tmp: Path) -> None:
    """A small, fully healthy project — every scored signal should be 0 on this."""
    _git(tmp, "init", "-q")
    _git(tmp, "config", "user.email", "test@example.com")
    _git(tmp, "config", "user.name", "Test")

    (tmp / "project.toml").write_text(
        "[caps]\n"
        "file_lines = 500\n"
        "claude_md_lines = 150\n"
        "todo_cards = 10\n"
        "branch_sessions = 3\n"
    )
    (tmp / "CLAUDE.md").write_text("# clean\n" * 5)
    (tmp / "docs").mkdir()
    (tmp / "docs" / "00-product.md").write_text("ok\n")
    (tmp / "docs" / "handoff.md").write_text("ok\n")
    (tmp / "backlog").mkdir()
    (tmp / "backlog" / "B-001.md").write_text(
        "---\nid: B-001\nstatus: todo\nopened: 2026-08-02\n---\nbody\n"
    )
    (tmp / "tools").mkdir()
    (tmp / "tools" / "main.py").write_text("print('hi')\n")
    _git(tmp, "add", "-A")
    _git(tmp, "commit", "-qm", "init\n\nSession: s1", date="2026-08-01T10:00:00")


@pytest.fixture()
def clean(tmp_path: Path) -> Path:
    make_clean_repo(tmp_path)
    return tmp_path


def test_clean_repo_scores_zero(clean: Path) -> None:
    report = rot.compute_rot(clean)
    assert report.total == 0


def test_compat_marker_raises_score(clean: Path) -> None:
    before = rot.compute_rot(clean).total
    (clean / "tools" / "old.py").write_text(
        "def foo_v2():\n    return 1\n")  # compat-marker-ok
    after_report = rot.compute_rot(clean)
    assert after_report.total > before
    sig = {s.name: s for s in after_report.signals}["compat_markers"]
    assert sig.count == 1
    assert sig.status == "scored"


def test_compat_scanner_respects_the_ignore_sentinel_on_its_own_files(
        clean: Path, tmp_path: Path) -> None:
    """Self-matching guard: rot.py's own source (and its test file) contain the literal
    marker strings as data — e.g. the string "_v2" inside COMPAT_MARKERS itself, and inside  # compat-marker-ok
    this very docstring/test. Every such line is annotated with the shared "compat-marker-ok"
    sentinel (the same convention tools/checks.py uses), so a copy of these two files dropped
    into a project's tools/ dir must not self-flag, or the scanner would always report itself
    as rot."""
    this_file = Path(rot.__file__)
    test_file = this_file.parent / "rot_test.py"
    (clean / "tools" / this_file.name).write_text(this_file.read_text())
    (clean / "tools" / test_file.name).write_text(test_file.read_text())
    report = rot.compute_rot(clean)
    sig = {s.name: s for s in report.signals}["compat_markers"]
    assert sig.count == 0, sig.detail


def test_docs_outside_schema_raises_score(clean: Path) -> None:
    before = rot.compute_rot(clean).total
    (clean / "docs" / "notes-from-last-week.md").write_text("stray\n")
    after = rot.compute_rot(clean)
    assert after.total > before
    sig = {s.name: s for s in after.signals}["docs_outside_schema"]
    assert sig.count == 1


def test_claude_md_over_cap_raises_score(clean: Path) -> None:
    before = rot.compute_rot(clean).total
    (clean / "CLAUDE.md").write_text("# x\n" * 200)
    after = rot.compute_rot(clean)
    sig = {s.name: s for s in after.signals}["claude_md_over_cap"]
    assert sig.count == 50  # 200 - 150 cap
    assert after.total > before


def test_source_file_over_cap_raises_score(clean: Path) -> None:
    before = rot.compute_rot(clean).total
    (clean / "tools" / "huge.py").write_text("x = 1\n" * 600)
    after = rot.compute_rot(clean)
    sig = {s.name: s for s in after.signals}["source_file_over_cap"]
    assert sig.count == 100  # 600 - 500 cap
    assert after.total > before


def test_stale_doing_card_raises_score(clean: Path) -> None:
    before = rot.compute_rot(clean).total
    (clean / "backlog" / "B-002.md").write_text(
        "---\nid: B-002\nstatus: doing\nopened: 2026-01-01\n---\nstuck\n"
    )
    _git(clean, "add", "-A")
    # Four sessions land on main after the card opened, well past branch_sessions=3.
    for i, s in enumerate(["s2", "s3", "s4", "s5"]):
        (clean / "tools" / f"drip{i}.py").write_text("x = 1\n")
        _git(clean, "add", "-A")
        _git(clean, "commit", "-qm", f"drip {i}\n\nSession: {s}",
             date=f"2026-02-0{i + 1}T10:00:00")
    after = rot.compute_rot(clean)
    sig = {s.name: s for s in after.signals}["stale_cards"]
    assert sig.count == 1
    assert after.total > before


def test_stale_branch_raises_score(clean: Path) -> None:
    before = rot.compute_rot(clean).total
    _git(clean, "checkout", "-qb", "spike")
    _git(clean, "checkout", "-q", "-")
    for i, s in enumerate(["s2", "s3", "s4", "s5"]):
        (clean / "tools" / f"trunk{i}.py").write_text("x = 1\n")
        _git(clean, "add", "-A")
        _git(clean, "commit", "-qm", f"trunk {i}\n\nSession: {s}",
             date=f"2026-02-0{i + 1}T10:00:00")
    after = rot.compute_rot(clean)
    sig = {s.name: s for s in after.signals}["stale_branches"]
    assert sig.count == 1
    assert after.total > before


def test_net_lines_is_informational_not_scored(clean: Path) -> None:
    report = rot.compute_rot(clean)
    sig = {s.name: s for s in report.signals}["net_lines_trend"]
    assert sig.status == "informational"
    assert sig.weight == 0
    assert sig.weighted == 0


def test_unimplemented_signals_are_reported_not_scored_zero(clean: Path) -> None:
    report = rot.compute_rot(clean)
    by_name = {s.name: s for s in report.signals}
    for name in ("skills_never_fired", "dead_code_unreachable_from_demo"):
        sig = by_name[name]
        assert sig.status == "unimplemented"
        assert sig.weighted == 0
        assert sig.detail  # must explain why, not just sit silent


def test_non_git_root_degrades_git_signals_without_crashing(tmp_path: Path) -> None:
    (tmp_path / "project.toml").write_text("[caps]\nfile_lines = 500\n")
    report = rot.compute_rot(tmp_path)
    by_name = {s.name: s for s in report.signals}
    assert by_name["stale_branches"].status == "unavailable"
    assert by_name["stale_cards"].status in ("unavailable", "scored")
    assert report.total >= 0


def test_missing_project_toml_uses_documented_defaults(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "x.py").write_text("print(1)\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init\n\nSession: s1", date="2026-08-01T10:00:00")
    report = rot.compute_rot(tmp_path)  # must not raise despite no project.toml
    assert report.total == 0


def test_selftest_passes() -> None:
    assert rot._selftest() == 0
