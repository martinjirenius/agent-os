#!/usr/bin/env python3
"""Tests for backlog.py — colocated per CLAUDE.md, run with `pytest tools/backlog_test.py`.

Builds throwaway fixture projects under tmp_path (real files, no mocks — under-mock per
docs/03-practices.md). Never touches this repo's own backlog/: these tools ship into other
projects (D-07), and the real backlog here is live work that must not be deleted by a test
run.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import backlog


def make_fixture(tmp: Path) -> None:
    """A minimal project: caps + one real deliverable (D-01), empty backlog/."""
    (tmp / "project.toml").write_text(
        '[caps]\n'
        'wip_cards = 1\n'
        'todo_cards = 10\n'
        '\n'
        '[[deliverables]]\n'
        'id = "D-01"\n'
        'title = "a real deliverable"\n'
        'depends = []\n'
        'serves = "something"\n'
    )
    (tmp / "backlog").mkdir()


def write_card(tmp: Path, name: str, *, id: str, title: str = "t", status: str = "todo",
               serves: str = "D-01", opened: str = "2026-08-02") -> Path:
    p = tmp / "backlog" / name
    p.write_text(
        f"---\nid: {id}\ntitle: {title}\nstatus: {status}\nserves: {serves}\n"
        f"opened: {opened}\n---\n\nbody\n"
    )
    return p


# --- parse_card ---------------------------------------------------------

def test_parse_card_valid_returns_card(tmp_path: Path) -> None:
    make_fixture(tmp_path)
    p = write_card(tmp_path, "B-001.md", id="B-001")
    card = backlog.parse_card(p)
    assert isinstance(card, backlog.Card)
    assert card.id == "B-001"
    assert card.serves == "D-01"
    assert card.status == "todo"


def test_parse_card_missing_frontmatter_is_error(tmp_path: Path) -> None:
    make_fixture(tmp_path)
    p = tmp_path / "backlog" / "B-002.md"
    p.write_text("no frontmatter here\n")
    card = backlog.parse_card(p)
    assert isinstance(card, backlog.CardError)
    assert card.path == p


def test_parse_card_missing_serves_field_is_error(tmp_path: Path) -> None:
    make_fixture(tmp_path)
    p = tmp_path / "backlog" / "B-003.md"
    p.write_text("---\nid: B-003\ntitle: t\nstatus: todo\nopened: 2026-08-02\n---\nbody\n")
    card = backlog.parse_card(p)
    assert isinstance(card, backlog.CardError)
    assert "serves" in card.message


def test_parse_card_bad_status_is_error(tmp_path: Path) -> None:
    make_fixture(tmp_path)
    p = write_card(tmp_path, "B-004.md", id="B-004", status="done")
    card = backlog.parse_card(p)
    assert isinstance(card, backlog.CardError)


# --- lints ---------------------------------------------------------------

def test_check_wip_cards_pass(tmp_path: Path) -> None:
    make_fixture(tmp_path)
    write_card(tmp_path, "B-001.md", id="B-001", status="doing")
    row = backlog.check_wip_cards(tmp_path, cap=1)
    assert row.status == "PASS"


def test_check_wip_cards_fail(tmp_path: Path) -> None:
    make_fixture(tmp_path)
    write_card(tmp_path, "B-001.md", id="B-001", status="doing")
    write_card(tmp_path, "B-002.md", id="B-002", status="doing")
    row = backlog.check_wip_cards(tmp_path, cap=1)
    assert row.status == "FAIL"
    assert "B-001" in row.detail or "B-002" in row.detail


def test_check_todo_cards_fail(tmp_path: Path) -> None:
    make_fixture(tmp_path)
    for i in range(1, 4):
        write_card(tmp_path, f"B-{i:03}.md", id=f"B-{i:03}")
    row = backlog.check_todo_cards(tmp_path, cap=2)
    assert row.status == "FAIL"


def test_check_serves_pass_when_deliverable_exists(tmp_path: Path) -> None:
    make_fixture(tmp_path)
    write_card(tmp_path, "B-001.md", id="B-001", serves="D-01")
    row = backlog.check_serves(tmp_path, {"D-01"})
    assert row.status == "PASS"


def test_check_serves_fails_naming_the_card_for_nonexistent_deliverable(tmp_path: Path) -> None:
    make_fixture(tmp_path)
    write_card(tmp_path, "B-099.md", id="B-099", serves="D-99")
    row = backlog.check_serves(tmp_path, {"D-01"})
    assert row.status == "FAIL"
    assert "B-099" in row.detail
    assert "D-99" in row.detail


def test_check_serves_fails_on_malformed_card_without_crashing(tmp_path: Path) -> None:
    make_fixture(tmp_path)
    p = tmp_path / "backlog" / "B-100.md"
    p.write_text("not even frontmatter\n")
    row = backlog.check_serves(tmp_path, {"D-01"})
    assert row.status == "FAIL"
    assert "B-100" in row.detail


# --- next_id / new -------------------------------------------------------

def test_next_id_empty_backlog_is_b001(tmp_path: Path) -> None:
    make_fixture(tmp_path)
    assert backlog.next_id(tmp_path) == "B-001"


def test_next_id_skips_existing(tmp_path: Path) -> None:
    make_fixture(tmp_path)
    write_card(tmp_path, "B-001.md", id="B-001")
    write_card(tmp_path, "B-007.md", id="B-007")
    assert backlog.next_id(tmp_path) == "B-008"


def test_new_creates_card_with_schema_fields(tmp_path: Path) -> None:
    make_fixture(tmp_path)
    rc = backlog.main(["new", "--title", "do the thing", "--serves", "D-01",
                        "--root", str(tmp_path)])
    assert rc == 0
    created = list((tmp_path / "backlog").glob("B-*.md"))
    assert len(created) == 1
    text = created[0].read_text()
    assert "id: B-001" in text
    assert "status: todo" in text
    assert "serves: D-01" in text
    assert "opened:" in text


def test_new_rejects_unknown_deliverable(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    make_fixture(tmp_path)
    rc = backlog.main(["new", "--title", "x", "--serves", "D-99", "--root", str(tmp_path)])
    assert rc == 1
    assert not list((tmp_path / "backlog").glob("*.md"))


# --- close -----------------------------------------------------------------

def test_close_deletes_file_and_prints_trailers(tmp_path: Path,
                                                 capsys: pytest.CaptureFixture) -> None:
    make_fixture(tmp_path)
    write_card(tmp_path, "B-001.md", id="B-001", serves="D-01")
    rc = backlog.main(["close", "B-001", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert not (tmp_path / "backlog" / "B-001.md").exists()
    assert "Card: B-001" in out
    assert "Serves: D-01" in out
    assert "Disposition: done" in out


def test_close_non_done_requires_reason(tmp_path: Path) -> None:
    make_fixture(tmp_path)
    write_card(tmp_path, "B-001.md", id="B-001", serves="D-01")
    rc = backlog.main(["close", "B-001", "--disposition", "rejected", "--root", str(tmp_path)])
    assert rc == 1
    assert (tmp_path / "backlog" / "B-001.md").exists()


def test_close_non_done_with_reason_deletes_and_prints_reason(
        tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    make_fixture(tmp_path)
    write_card(tmp_path, "B-001.md", id="B-001", serves="D-01")
    rc = backlog.main(["close", "B-001", "--disposition", "deferred",
                        "--reason", "not worth it", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Reason: not worth it" in out


def test_close_missing_card_errors(tmp_path: Path) -> None:
    make_fixture(tmp_path)
    rc = backlog.main(["close", "B-404", "--root", str(tmp_path)])
    assert rc == 1


def test_close_malformed_card_refuses_and_does_not_delete(tmp_path: Path) -> None:
    make_fixture(tmp_path)
    p = tmp_path / "backlog" / "B-001.md"
    p.write_text("garbage\n")
    rc = backlog.main(["close", "B-001", "--root", str(tmp_path)])
    assert rc == 1
    assert p.exists()


# --- list / lint CLI ---------------------------------------------------------

def test_list_cli_prints_cards(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    make_fixture(tmp_path)
    write_card(tmp_path, "B-001.md", id="B-001", title="fix the thing")
    rc = backlog.main(["list", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "B-001" in out
    assert "fix the thing" in out


def test_lint_cli_fails_on_bad_serves(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    make_fixture(tmp_path)
    write_card(tmp_path, "B-001.md", id="B-001", serves="D-99")
    rc = backlog.main(["lint", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "FAIL" in out
    assert "B-001" in out


# --- subprocess end-to-end, no ambient git/agent-os assumptions -------------

def test_cli_end_to_end_from_subprocess(tmp_path: Path) -> None:
    make_fixture(tmp_path)
    write_card(tmp_path, "B-001.md", id="B-001")
    r = subprocess.run(
        [sys.executable, str(Path(backlog.__file__).resolve()), "list", "--root", str(tmp_path)],
        capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "B-001" in r.stdout


def test_selftest_cli() -> None:
    r = subprocess.run([sys.executable, str(Path(backlog.__file__).resolve()), "--selftest"],
                        capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "cases pass" in r.stdout


def test_lints_still_report_when_backlog_dir_is_absent(tmp_path: Path) -> None:
    """Closing the last card deletes backlog/ (git tracks no empty dirs). The rows must
    survive that, or the gate reports all-pass while the lints are not running at all."""
    (tmp_path / "project.toml").write_text(
        '[caps]\nwip_cards = 1\ntodo_cards = 10\n\n[[deliverables]]\nid = "D-01"\ntitle = "t"\n')
    assert not (tmp_path / "backlog").exists()
    rows = [
        backlog.check_wip_cards(tmp_path, 1),
        backlog.check_todo_cards(tmp_path, 10),
        backlog.check_serves(tmp_path, {"D-01"}),
    ]
    assert all(r is not None for r in rows), rows
    assert all(r.status == "PASS" for r in rows), rows
