#!/usr/bin/env python3
"""Tests for timetravel.py — colocated per CLAUDE.md, run with `pytest tools/timetravel_test.py`.

Builds one real, throwaway git repo per test module (not fixtures/mocks — under-mock per
docs/03-practices.md) with deterministic commit dates (clock injected via
GIT_AUTHOR_DATE/GIT_COMMITTER_DATE, per the determinism lint) and exercises the actual git
subprocess calls timetravel.py makes.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

import git_ledger
import timetravel


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A real repo: notes.txt created, edited, then deleted, across three dated commits.

    The same builder `timetravel.py --selftest` uses — one authority for the fixture history
    (axiom 4), so the two suites can never drift into testing different worlds.
    """
    timetravel.build_scratch_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    return tmp_path


# --- mode (a): find a deleted file ---

def test_find_deleted_exact_match(repo: Path) -> None:
    rows = timetravel.find_deleted("notes.txt")
    assert len(rows) == 1
    assert rows[0].path == "notes.txt"


def test_find_deleted_fuzzy_match(repo: Path) -> None:
    rows = timetravel.find_deleted("note")  # partial, not exact
    assert any(d.path == "notes.txt" for d in rows)


def test_find_deleted_no_match(repo: Path) -> None:
    assert timetravel.find_deleted("nonexistent-xyz") == []


# --- mode (b): a file as of a date ---

def test_show_as_of_returns_content_at_that_date(repo: Path) -> None:
    assert timetravel.show_as_of("notes.txt", "2026-01-01") == "original\n"
    assert timetravel.show_as_of("notes.txt", "2026-01-02") == "changed\n"


def test_show_as_of_before_repo_existed_raises(repo: Path) -> None:
    with pytest.raises(SystemExit, match="no commit exists"):
        timetravel.show_as_of("notes.txt", "2020-01-01")


def test_show_as_of_bad_date_format_raises(repo: Path) -> None:
    with pytest.raises(SystemExit, match="not a date"):
        timetravel.show_as_of("notes.txt", "not-a-date")


def test_show_as_of_missing_path_raises_with_fix(repo: Path) -> None:
    with pytest.raises(SystemExit, match="does not exist"):
        timetravel.show_as_of("nope.txt", "2026-01-02")


# --- anchor resolution, feeding mode (c) ---

def test_resolve_anchor_card(repo: Path) -> None:
    commits = git_ledger.load()
    latest_for_card = [c for c in commits
                        if git_ledger.match_trailer(c, "Card", "B-100")][0]
    assert timetravel.resolve_anchor("B-100") == latest_for_card.sha


def test_resolve_anchor_deliverable(repo: Path) -> None:
    commits = git_ledger.load()
    latest_for_d = [c for c in commits
                    if git_ledger.match_trailer(c, "Serves", "D-01")][0]
    assert timetravel.resolve_anchor("D-01") == latest_for_d.sha


def test_resolve_anchor_tag(repo: Path) -> None:
    tag_sha = subprocess.run(["git", "rev-list", "-n1", "v1"],
                              capture_output=True, text=True).stdout.strip()
    assert timetravel.resolve_anchor("v1") == tag_sha


def test_resolve_anchor_date(repo: Path) -> None:
    assert timetravel.resolve_anchor("2026-01-02") == timetravel._commit_at_or_before(
        "2026-01-02")


def test_resolve_anchor_unknown_card_raises(repo: Path) -> None:
    with pytest.raises(SystemExit, match="no commit carries"):
        timetravel.resolve_anchor("B-999")


def test_resolve_anchor_garbage_raises(repo: Path) -> None:
    with pytest.raises(SystemExit, match="not a recognized anchor"):
        timetravel.resolve_anchor("not-an-anchor-at-all")


# --- mode (c): what did X look like before <anchor> ---

def test_show_before_card_anchor_gives_prior_version(repo: Path) -> None:
    assert timetravel.show_before("B-100", "notes.txt") == "original\n"


def test_show_before_tag_anchor_gives_prior_version(repo: Path) -> None:
    assert timetravel.show_before("v1", "notes.txt") == "original\n"


def test_show_before_root_commit_raises(repo: Path) -> None:
    commits = git_ledger.load()
    root_sha = commits[-1].sha
    with pytest.raises(SystemExit, match="first commit"):
        timetravel.show_before(root_sha, "notes.txt")
