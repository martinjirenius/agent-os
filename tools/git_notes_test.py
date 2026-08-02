"""Colocated tests for git_notes.py — run against an isolated throwaway repo, never this one.

Each test builds its own tmp git repo (git init) so notes, commits and remotes created here
never touch agent-os's real object store. Run: python3 -m pytest tools/git_notes_test.py -q
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import git_notes  # noqa: E402


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True
    )


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


def _notes_show(repo: Path, sha: str) -> str:
    r = _git(repo, "notes", "--ref", git_notes.NOTES_REF, "show", sha)
    assert r.returncode == 0, r.stderr
    return r.stdout


VALID_STACK = {
    "session": "2026-08-02-a",
    "frames": [
        {
            "depth": 1,
            "question": "why does X fail under load",
            "unblocks": "confirms D-03 can proceed without a rewrite",
            "opened": "2026-08-02T14:03:00Z",
            "closed": "2026-08-02T14:20:00Z",
            "outcome": "answered: stale cache, filed as B-011",
        }
    ],
}


def test_load_stack_missing_file_states_the_fix(tmp_path):
    missing = tmp_path / "stack.json"
    with pytest.raises(SystemExit) as exc:
        git_notes.load_stack(missing)
    assert "not found" in str(exc.value)
    assert str(missing) in str(exc.value)


def test_load_stack_bad_json_states_the_fix(tmp_path):
    bad = tmp_path / "stack.json"
    bad.write_text("{not json")
    with pytest.raises(SystemExit) as exc:
        git_notes.load_stack(bad)
    assert "not valid JSON" in str(exc.value)


def test_load_stack_missing_keys_rejected(tmp_path):
    bad = tmp_path / "stack.json"
    bad.write_text(json.dumps({"session": "s"}))
    with pytest.raises(SystemExit) as exc:
        git_notes.load_stack(bad)
    assert "frames" in str(exc.value)


def test_load_stack_frame_missing_field_rejected(tmp_path):
    bad = tmp_path / "stack.json"
    payload = {"session": "s", "frames": [{"depth": 1}]}
    bad.write_text(json.dumps(payload))
    with pytest.raises(SystemExit) as exc:
        git_notes.load_stack(bad)
    assert "is missing" in str(exc.value)


def test_load_stack_valid_roundtrips(tmp_path):
    p = tmp_path / "stack.json"
    p.write_text(json.dumps(VALID_STACK))
    data = git_notes.load_stack(p)
    assert data == VALID_STACK


def test_add_profile_writes_readable_note(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    sha = _commit(repo, "some work")
    stack_path = tmp_path / "stack.json"
    stack_path.write_text(json.dumps(VALID_STACK))
    monkeypatch.chdir(repo)

    rc = git_notes.main(["add-profile", "--commit", sha, "--stack-path", str(stack_path)])
    assert rc == 0

    note = _notes_show(repo, sha)
    assert json.loads(note) == VALID_STACK


def test_add_profile_refuses_to_clobber_without_force(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    sha = _commit(repo, "some work")
    stack_path = tmp_path / "stack.json"
    stack_path.write_text(json.dumps(VALID_STACK))
    monkeypatch.chdir(repo)

    assert git_notes.main(["add-profile", "--commit", sha, "--stack-path", str(stack_path)]) == 0
    with pytest.raises(SystemExit) as exc:
        git_notes.main(["add-profile", "--commit", sha, "--stack-path", str(stack_path)])
    assert "--force" in str(exc.value)


def test_add_profile_force_overwrites(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    sha = _commit(repo, "some work")
    stack_path = tmp_path / "stack.json"
    stack_path.write_text(json.dumps(VALID_STACK))
    monkeypatch.chdir(repo)
    git_notes.main(["add-profile", "--commit", sha, "--stack-path", str(stack_path)])

    changed = json.loads(json.dumps(VALID_STACK))
    changed["session"] = "2026-08-02-b"
    stack_path.write_text(json.dumps(changed))
    rc = git_notes.main(
        ["add-profile", "--commit", sha, "--stack-path", str(stack_path), "--force"]
    )
    assert rc == 0
    assert json.loads(_notes_show(repo, sha))["session"] == "2026-08-02-b"


def test_annotate_by_sha_appends(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    sha = _commit(repo, "some work")
    monkeypatch.chdir(repo)

    assert git_notes.main(["annotate", "--sha", sha, "-m", "first note"]) == 0
    assert git_notes.main(["annotate", "--sha", sha, "-m", "second note"]) == 0
    note = _notes_show(repo, sha)
    assert "first note" in note
    assert "second note" in note


def test_annotate_force_replaces_instead_of_appending(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    sha = _commit(repo, "some work")
    monkeypatch.chdir(repo)

    git_notes.main(["annotate", "--sha", sha, "-m", "first note"])
    git_notes.main(["annotate", "--sha", sha, "-m", "replacement", "--force"])
    note = _notes_show(repo, sha)
    assert note.strip() == "replacement"


def test_annotate_resolves_commit_via_ledger_card(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    _commit(repo, "unrelated\n\nSession: s1\nCard: B-999\nServes: D-09")
    target_sha = _commit(repo, "the fix\n\nSession: s1\nCard: B-002\nServes: D-01")
    monkeypatch.chdir(repo)

    rc = git_notes.main(["annotate", "--card", "B-002", "-m", "superseded by D-051"])
    assert rc == 0
    assert "superseded by D-051" in _notes_show(repo, target_sha)


def test_annotate_ambiguous_ledger_match_lists_candidates(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    _commit(repo, "one\n\nSession: s1\nServes: D-01")
    _commit(repo, "two\n\nSession: s1\nServes: D-01")
    monkeypatch.chdir(repo)

    with pytest.raises(SystemExit) as exc:
        git_notes.main(["annotate", "--serves", "D-01", "-m", "x"])
    msg = str(exc.value)
    assert "2 commits match" in msg
    assert "--sha" in msg


def test_annotate_no_match_states_the_fix(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    _commit(repo, "irrelevant")
    monkeypatch.chdir(repo)

    with pytest.raises(SystemExit) as exc:
        git_notes.main(["annotate", "--card", "B-404", "-m", "x"])
    assert "no commit matches" in str(exc.value)


def test_configure_push_fails_loudly_with_no_remote(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    _commit(repo, "some work")
    monkeypatch.chdir(repo)

    with pytest.raises(SystemExit) as exc:
        git_notes.main(["configure-push"])
    msg = str(exc.value)
    assert "no remote" in msg
    assert "git remote add" in msg


def test_configure_push_configures_refspec_when_remote_exists(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    _commit(repo, "some work")
    other = tmp_path / "other.git"
    _git(tmp_path, "init", "-q", "--bare", str(other))
    _git(repo, "remote", "add", "origin", str(other))
    monkeypatch.chdir(repo)

    rc = git_notes.main(["configure-push"])
    assert rc == 0
    out = _git(repo, "config", "--get-all", "remote.origin.push").stdout
    assert "refs/notes/*:refs/notes/*" in out


def test_selftest_exits_zero():
    rc = git_notes.main(["--selftest"])
    assert rc == 0


def test_add_profile_refuses_a_sha_from_another_repo(tmp_path, monkeypatch):
    """A 40-hex sha from a DIFFERENT repo must not get a note attached here.

    `git rev-parse <40-hex>` echoes its input back without checking the object exists, so this
    silently polluted the real repo's refs/notes with an annotation on a commit it did not
    contain. Caught when a fixture test ran without chdir'ing into its own repo.
    """
    repo = _init_repo(tmp_path)
    _commit(repo, "some work")
    stack_path = tmp_path / "stack.json"
    stack_path.write_text(json.dumps(VALID_STACK))
    monkeypatch.chdir(repo)

    foreign = "fee93a1675afaeec1332a98eac39ad47f1578cf6"
    with pytest.raises(SystemExit) as exc:
        git_notes.main(["add-profile", "--commit", foreign, "--stack-path", str(stack_path)])
    assert "not a commit in this repository" in str(exc.value)
    assert _git(repo, "notes", "--ref", git_notes.NOTES_REF, "list").stdout.strip() == ""
