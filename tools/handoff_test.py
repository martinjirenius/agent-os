"""Colocated tests for handoff.py — run against an isolated throwaway repo, never this one.

Each test that touches git builds its own tmp git repo (git init) so nothing here reads or
writes agent-os's real object store. Run: python3 -m pytest tools/handoff_test.py -q
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import handoff  # noqa: E402
from git_ledger import Commit  # noqa: E402


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    return repo


def _commit(repo: Path, message: str) -> str:
    (repo / "f.txt").write_text(message)
    _git(repo, "add", "f.txt")
    r = _git(repo, "commit", "-q", "-m", message, "--no-verify")
    assert r.returncode == 0, r.stderr
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def test_session_commits_filters_to_session_and_orders_oldest_first():
    fixture = [
        Commit("a", "2026-08-02", "third", {"Session": ["2026-08-02-a"]}),
        Commit("b", "2026-08-01", "other-session", {"Session": ["2026-08-01-a"]}),
        Commit("c", "2026-08-02", "first", {"Session": ["2026-08-02-a"]}),
    ]
    mine = handoff.session_commits(fixture, "2026-08-02-a")
    assert [c.sha for c in mine] == ["c", "a"]


def test_collect_trailer_dedups_preserving_first_seen_order():
    fixture = [
        Commit("a", "2026-08-02", "x", {"Chose": ["pick A", "pick B"]}),
        Commit("b", "2026-08-02", "y", {"Chose": ["pick A"]}),
    ]
    assert handoff.collect_trailer(fixture, "Chose") == ["pick A", "pick B"]


def test_render_lists_commits_oldest_first_with_card_and_disposition():
    commits = [
        Commit("a", "2026-08-02", "first", {}),
        Commit("b", "2026-08-02", "second", {"Card": ["B-002"], "Disposition": ["done"]}),
    ]
    text = handoff.render("2026-08-02-a", commits, "main", True)
    assert text.index("first") < text.index("second")
    assert "[B-002, done]" in text


def test_render_no_commits_says_so_plainly():
    text = handoff.render("2026-08-03-a", [], "main", True)
    assert "No commits recorded for session `2026-08-03-a`." in text


def test_render_surfaces_chose_and_question_trailers():
    commits = [Commit("a", "2026-08-02", "x", {"Chose": ["use X"], "Question": ["ok Y?"]})]
    text = handoff.render("2026-08-02-a", commits, "main", True)
    assert "Chose: use X" in text
    assert "Question: ok Y?" in text


def test_render_no_chose_or_question_says_so_plainly():
    text = handoff.render("2026-08-02-a", [], "main", True)
    assert "None recorded this session." in text


def test_render_dirty_repo_says_dirty():
    text = handoff.render("2026-08-02-a", [], "main", False)
    assert "Branch `main`, dirty." in text


def test_render_defaults_are_placeholders_the_caller_must_replace():
    text = handoff.render("2026-08-02-a", [], "main", True)
    assert handoff.NEXT_ACTION_PLACEHOLDER in text
    assert handoff.GOTCHAS_PLACEHOLDER in text


def test_render_honors_next_action_and_gotchas_overrides():
    text = handoff.render("2026-08-02-a", [], "main", True,
                           next_action="ship the thing", gotchas="watch the hook")
    assert "ship the thing" in text
    assert "watch the hook" in text
    assert handoff.NEXT_ACTION_PLACEHOLDER not in text


def test_repo_state_reports_real_branch_and_clean(tmp_path):
    repo = _init_repo(tmp_path)
    _commit(repo, "one\n\nSession: 2026-08-02-a\n")
    branch, clean = handoff.repo_state(repo)
    assert branch
    assert clean is True


def test_repo_state_reports_dirty_with_uncommitted_changes(tmp_path):
    repo = _init_repo(tmp_path)
    _commit(repo, "one\n\nSession: 2026-08-02-a\n")
    (repo / "untracked.txt").write_text("x")
    _, clean = handoff.repo_state(repo)
    assert clean is False


def test_cli_render_end_to_end_reads_the_fixture_repo(tmp_path):
    repo = _init_repo(tmp_path)
    _commit(repo, "do the work\n\nSession: 2026-08-02-z\nCard: B-999\nServes: D-99\n")

    r = subprocess.run(
        [sys.executable, str(Path(handoff.__file__).resolve()),
         "render", "--session", "2026-08-02-z", "--root", str(repo)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "do the work" in r.stdout
    assert "[B-999]" in r.stdout


def test_cli_render_unknown_session_has_no_commits(tmp_path):
    repo = _init_repo(tmp_path)
    _commit(repo, "unrelated\n\nSession: 2026-08-01-a\n")

    r = subprocess.run(
        [sys.executable, str(Path(handoff.__file__).resolve()),
         "render", "--session", "2026-08-02-nope", "--root", str(repo)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "No commits recorded for session `2026-08-02-nope`." in r.stdout
