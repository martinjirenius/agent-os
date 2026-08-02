#!/usr/bin/env python3
"""Tests for checks.py — colocated per CLAUDE.md, run with `pytest tools/checks_test.py`.

Builds a throwaway fixture project per test (real files under tmp_path, not mocks —
under-mock per docs/03-practices.md) so the checks run against real I/O rather than a
fantasy. Never touches this repo's own project.toml: these tools ship into other
projects (D-07), so a suite anchored to agent-os's own paths would prove nothing about
portability.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import checks


def make_fixture(tmp: Path) -> None:
    """A minimal, fully healthy project — every check should PASS or STUB on this."""
    (tmp / "project.toml").write_text(
        '[commands]\n'
        'test = "true"\n'
        'lint = ""\n'
        '\n'
        '[caps]\n'
        'file_lines = 500\n'
        'claude_md_lines = 150\n'
        'todo_cards = 10\n'
        'wip_cards = 1\n'
        'local_skills = 3\n'
    )
    (tmp / "CLAUDE.md").write_text("# x\n" * 5)
    (tmp / "docs").mkdir()
    (tmp / "docs" / "00-product.md").write_text("ok\n")
    (tmp / "backlog").mkdir()
    (tmp / "backlog" / "B-001.md").write_text("---\nid: B-001\nstatus: todo\n---\nbody\n")
    (tmp / "skills").mkdir()
    (tmp / "tools").mkdir()
    (tmp / "tools" / "main.py").write_text("print('hi')\n")


def rows_by_name(tmp: Path, manifest: dict | None = None) -> dict[str, checks.Row]:
    m = manifest if manifest is not None else checks.load_manifest(tmp / "project.toml")
    return {r.name: r for r in checks.build_rows(tmp, m)}


def test_stub_command_renders_as_stub_not_pass(tmp_path: Path) -> None:
    make_fixture(tmp_path)
    rows = rows_by_name(tmp_path)
    assert rows["lint"].status == "STUB"


def test_passing_command_is_pass(tmp_path: Path) -> None:
    make_fixture(tmp_path)
    rows = rows_by_name(tmp_path)
    assert rows["test"].status == "PASS"


def test_failing_command_is_fail(tmp_path: Path) -> None:
    make_fixture(tmp_path)
    m = checks.load_manifest(tmp_path / "project.toml")
    m["commands"]["test"] = "false"
    rows = rows_by_name(tmp_path, m)
    assert rows["test"].status == "FAIL"


def test_clean_fixture_has_no_fail_rows(tmp_path: Path) -> None:
    make_fixture(tmp_path)
    rows = rows_by_name(tmp_path)
    assert all(r.status != "FAIL" for r in rows.values()), rows


def test_file_lines_over_cap_fails_and_names_the_file(tmp_path: Path) -> None:
    make_fixture(tmp_path)
    (tmp_path / "tools" / "big.py").write_text("x = 1\n" * 600)
    rows = rows_by_name(tmp_path)
    row = rows["file_lines <= 500"]
    assert row.status == "FAIL"
    assert "big.py" in row.detail


def test_claude_md_over_cap_fails(tmp_path: Path) -> None:
    make_fixture(tmp_path)
    (tmp_path / "CLAUDE.md").write_text("# x\n" * 200)
    rows = rows_by_name(tmp_path)
    assert rows["claude_md_lines <= 150"].status == "FAIL"


def test_todo_cards_over_cap_fails(tmp_path: Path) -> None:
    make_fixture(tmp_path)
    for i in range(2, 13):
        (tmp_path / "backlog" / f"B-{i:03}.md").write_text(
            f"---\nid: B-{i:03}\nstatus: todo\n---\nbody\n")
    rows = rows_by_name(tmp_path)
    assert rows["todo_cards <= 10"].status == "FAIL"


def test_wip_cards_over_cap_fails(tmp_path: Path) -> None:
    make_fixture(tmp_path)
    (tmp_path / "backlog" / "B-002.md").write_text("---\nid: B-002\nstatus: doing\n---\nbody\n")
    (tmp_path / "backlog" / "B-003.md").write_text("---\nid: B-003\nstatus: doing\n---\nbody\n")
    rows = rows_by_name(tmp_path)
    assert rows["wip_cards <= 1"].status == "FAIL"


def test_local_skills_over_cap_fails(tmp_path: Path) -> None:
    make_fixture(tmp_path)
    for name in ("a", "b", "c", "d"):
        sd = tmp_path / "skills" / name
        sd.mkdir()
        (sd / "SKILL.md").write_text("x\n")
    rows = rows_by_name(tmp_path)
    assert rows["local_skills <= 3"].status == "FAIL"


def test_doc_schema_rejects_undefined_file(tmp_path: Path) -> None:
    make_fixture(tmp_path)
    (tmp_path / "docs" / "notes.md").write_text("stray\n")
    rows = rows_by_name(tmp_path)
    assert rows["doc schema"].status == "FAIL"


def test_compat_marker_detected(tmp_path: Path) -> None:
    make_fixture(tmp_path)
    (tmp_path / "tools" / "old.py").write_text("def foo_v2(): pass\n")  # compat-marker-ok
    rows = rows_by_name(tmp_path)
    assert rows["compat markers"].status == "FAIL"


def test_compat_marker_scan_excludes_its_own_source(tmp_path: Path) -> None:
    make_fixture(tmp_path)
    # checks.py's own source lists the marker strings it looks for; if the scan did not
    # exempt itself it would FAIL on every single run, everywhere.
    row = checks.check_compat_markers(Path(__file__).resolve().parent.parent)
    assert row.status == "PASS", row.detail


def test_missing_cap_errors_with_a_fix(tmp_path: Path) -> None:
    make_fixture(tmp_path)
    m = checks.load_manifest(tmp_path / "project.toml")
    del m["caps"]["file_lines"]
    with pytest.raises(SystemExit, match="missing caps"):
        checks.build_rows(tmp_path, m)


def test_find_manifest_walks_up_from_a_subdirectory(tmp_path: Path) -> None:
    make_fixture(tmp_path)
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    assert checks.find_manifest(sub) == tmp_path / "project.toml"


def test_find_manifest_missing_errors_with_a_fix(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="project.toml"):
        checks.find_manifest(tmp_path)


def test_cli_end_to_end_exits_0_on_clean_fixture(tmp_path: Path) -> None:
    make_fixture(tmp_path)
    r = subprocess.run([sys.executable, str(Path(checks.__file__).resolve())],
                        cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "STUB" in r.stdout


def test_cli_end_to_end_exits_1_on_violation(tmp_path: Path) -> None:
    make_fixture(tmp_path)
    (tmp_path / "tools" / "big.py").write_text("x = 1\n" * 600)
    r = subprocess.run([sys.executable, str(Path(checks.__file__).resolve())],
                        cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "FAIL" in r.stdout


def test_selftest_cli() -> None:
    r = subprocess.run([sys.executable, str(Path(checks.__file__).resolve()), "--selftest"],
                        capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "cases pass" in r.stdout
