"""Colocated tests for inbox.py — built against a throwaway git repo, never this one.

Run: python3 -m pytest tools/inbox_test.py -q
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import inbox  # noqa: E402


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    return repo


def _commit(repo: Path, name: str, message: str) -> str:
    (repo / name).write_text(message)
    _git(repo, "add", name)
    r = _git(repo, "commit", "-q", "-m", message)
    assert r.returncode == 0, r.stderr
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _build_fixture(tmp_path: Path) -> Path:
    """Two sessions: 2026-08-02-a (older) and 2026-08-02-b (newer), one Question, two Chose,
    and one commit with a Chose but NO Session trailer at all — the vanish-on-missing-input
    case the card calls out explicitly."""
    repo = _init_repo(tmp_path)
    _commit(repo, "a.txt", "first\n\nSession: 2026-08-02-a\nChose: picked X over Y")
    _commit(repo, "b.txt", "second\n\nSession: 2026-08-02-a\nQuestion: should we deploy this?")
    _commit(repo, "c.txt", "third\n\nSession: 2026-08-02-b\nChose: picked Z for speed")
    _commit(repo, "d.txt", "fourth\n\nChose: an orphan decision with no Session trailer")
    return repo


def test_collect_splits_questions_and_chosen_not_one_list(tmp_path, monkeypatch):
    repo = _build_fixture(tmp_path)
    monkeypatch.chdir(repo)
    questions, chosen = inbox.collect()
    assert len(questions) == 1
    assert "deploy" in questions[0].text
    assert len(chosen) == 3


def test_no_session_trailer_never_vanishes(tmp_path, monkeypatch):
    repo = _build_fixture(tmp_path)
    monkeypatch.chdir(repo)
    _, chosen = inbox.collect()
    orphan = [c for c in chosen if "orphan" in c.text]
    assert len(orphan) == 1
    assert orphan[0].session == ""
    rendered = inbox.render(*inbox.collect())
    assert "orphan decision" in rendered
    assert "(unknown session)" in rendered


def test_since_marks_only_matching_or_later_session_new(tmp_path, monkeypatch):
    repo = _build_fixture(tmp_path)
    monkeypatch.chdir(repo)
    questions, chosen = inbox.collect()
    all_items = questions + chosen
    new_texts = {it.text for it in all_items if inbox.is_new(it.session, "2026-08-02-b")}
    assert new_texts == {"picked Z for speed"}


def test_since_none_marks_nothing_new():
    assert inbox.is_new("2026-08-02-b", None) is False


def test_unknown_session_never_marked_new():
    assert inbox.is_new("", "2026-08-02-a") is False


def test_revert_command_is_copy_pasteable(tmp_path, monkeypatch):
    repo = _build_fixture(tmp_path)
    monkeypatch.chdir(repo)
    rendered = inbox.render(*inbox.collect())
    assert "git revert" in rendered


def test_empty_repo_says_inbox_empty(tmp_path, monkeypatch, capsys):
    repo = _init_repo(tmp_path)
    _commit(repo, "x.txt", "no trailers here")
    monkeypatch.chdir(repo)
    rc = inbox.main([])
    assert rc == 0
    assert "inbox empty" in capsys.readouterr().out


def test_cli_end_to_end_from_outside_the_repo_still_works_via_chdir(tmp_path, monkeypatch, capsys):
    repo = _build_fixture(tmp_path)
    monkeypatch.chdir(repo)
    rc = inbox.main(["--since", "2026-08-02-b"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "NEW" in out
    assert "new item(s) since 2026-08-02-b" in out


def test_selftest_exits_zero():
    assert inbox.main(["--selftest"]) == 0


def test_selftest_is_portable_outside_any_git_repo(tmp_path):
    """The card's hard requirement: --selftest must pass run from /tmp, outside any repo."""
    r = subprocess.run(
        [sys.executable, str(Path(__file__).parent / "inbox.py"), "--selftest"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "cases pass" in r.stdout
