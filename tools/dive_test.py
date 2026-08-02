"""Colocated tests for dive.py — the dive-profile renderer.

Everything here uses a throwaway git repo (never this one's real .agent/stack.json or
refs/notes) so it never corrupts a live session and stays portable outside any repo at all.

Run: python3 -m pytest tools/dive_test.py -q
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import dive as profile_mod  # noqa: E402  (avoid shadowing the stdlib `profile` module name)
import git_notes  # noqa: E402


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
    r = _git(repo, "commit", "-q", "-m", message)
    assert r.returncode == 0, r.stderr
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


STACK = {
    "session": "2026-08-02-c",
    "frames": [
        {
            "depth": 1,
            "question": "why does X fail under load",
            "unblocks": "confirms D-03 can proceed without a rewrite",
            "opened": "2026-08-02T14:03:00Z",
            "closed": "2026-08-02T14:20:00Z",
            "outcome": "answered: stale cache, filed as B-011",
        },
        {
            "depth": 2,
            "question": "is the cache even shared across workers",
            "unblocks": "settles whether the stale-cache theory holds",
            "opened": "2026-08-02T14:05:00Z",
            "closed": None,
            "outcome": None,
        },
    ],
}


def test_read_live_missing_file_returns_none_not_crash(tmp_path):
    assert profile_mod.read_live(tmp_path / "nope.json") is None


def test_read_live_present_file_returns_validated_dict(tmp_path):
    p = tmp_path / "stack.json"
    p.write_text(json.dumps(STACK))
    assert profile_mod.read_live(p) == STACK


def test_read_live_malformed_file_states_the_fix(tmp_path):
    p = tmp_path / "stack.json"
    p.write_text(json.dumps({"session": "s"}))  # missing "frames"
    with pytest.raises(SystemExit) as exc:
        profile_mod.read_live(p)
    assert "frames" in str(exc.value)


def test_render_never_renders_missing_stack_as_zero_dives(tmp_path, capsys):
    rc = profile_mod.main(["--stack-path", str(tmp_path / "absent.json")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "no live stack" in out
    assert "0 excursion" not in out  # must not be phrased like "a session with zero dives"


def test_render_shows_empty_session_distinctly(tmp_path, capsys):
    p = tmp_path / "stack.json"
    p.write_text(json.dumps({"session": "2026-08-02-z", "frames": []}))
    rc = profile_mod.main(["--stack-path", str(p)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "no live stack" not in out
    assert "0 excursion" in out


def test_render_shows_depth_and_outcome_for_each_frame(tmp_path, capsys):
    p = tmp_path / "stack.json"
    p.write_text(json.dumps(STACK))
    rc = profile_mod.main(["--stack-path", str(p)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "depth 1" in out
    assert "depth 2" in out
    assert "stale cache" in out
    assert "still open" in out or "UNRESOLVED" in out


def test_historical_note_renders_through_the_same_render_function(tmp_path, monkeypatch):
    """The load-bearing guarantee: live stack.json and a historical git note produce
    IDENTICAL rendered text through dive.render(), because both loaders funnel through
    git_notes.load_stack for validation before render() ever sees them."""
    repo = _init_repo(tmp_path)
    sha = _commit(repo, "some work")
    monkeypatch.chdir(repo)

    rc = git_notes.main(["notes"]) if False else None  # no-op, keep flake quiet
    stack_path = tmp_path / "stack.json"
    stack_path.write_text(json.dumps(STACK))
    assert git_notes.main(["add-profile", "--commit", sha, "--stack-path", str(stack_path)]) == 0

    live = profile_mod.read_live(stack_path)
    historical = profile_mod.read_historical(sha)
    assert live == historical
    assert profile_mod.render(live) == profile_mod.render(historical)


def test_historical_missing_note_is_visible_not_a_crash(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    sha = _commit(repo, "some work")
    monkeypatch.chdir(repo)
    assert profile_mod.read_historical(sha) is None


def test_cli_commit_flag_renders_historical(tmp_path, monkeypatch, capsys):
    repo = _init_repo(tmp_path)
    sha = _commit(repo, "some work")
    monkeypatch.chdir(repo)
    stack_path = tmp_path / "stack.json"
    stack_path.write_text(json.dumps(STACK))
    git_notes.main(["add-profile", "--commit", sha, "--stack-path", str(stack_path)])

    rc = profile_mod.main(["--commit", sha])
    assert rc == 0
    out = capsys.readouterr().out
    assert "depth 1" in out
    assert "historical" in out


def test_selftest_exits_zero():
    assert profile_mod.main(["--selftest"]) == 0


def test_selftest_is_portable_outside_any_git_repo(tmp_path):
    r = subprocess.run(
        [sys.executable, str(Path(__file__).parent / "dive.py"), "--selftest"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "cases pass" in r.stdout
