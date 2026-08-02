"""Colocated tests for stack.py — run against throwaway stack files, never this repo's own
.agent/stack.json (which would corrupt a live session's dive profile).

Run: python3 -m pytest tools/stack_test.py -q
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import stack  # noqa: E402
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


# --- pure push/pop logic -----------------------------------------------------

def test_push_requires_question():
    empty = {"session": "s1", "frames": []}
    with pytest.raises(SystemExit) as exc:
        stack.push(empty, "", "unblocks parent", cap=3, now="t0")
    assert "--question" in str(exc.value)


def test_push_requires_unblocks():
    empty = {"session": "s1", "frames": []}
    with pytest.raises(SystemExit) as exc:
        stack.push(empty, "why does X fail", "", cap=3, now="t0")
    assert "--unblocks" in str(exc.value)


def test_push_records_question_and_unblocks():
    empty = {"session": "s1", "frames": []}
    s = stack.push(empty, "why does X fail", "confirms D-03", cap=3, now="t0")
    frame = s["frames"][-1]
    assert frame["question"] == "why does X fail"
    assert frame["unblocks"] == "confirms D-03"
    assert frame["depth"] == 1
    assert frame["closed"] is None
    assert frame["outcome"] is None


def test_push_to_depth_four_refused_naming_three_exits():
    s = {"session": "s1", "frames": []}
    s = stack.push(s, "q1", "u1", cap=3, now="t0")
    s = stack.push(s, "q2", "u2", cap=3, now="t1")
    s = stack.push(s, "q3", "u3", cap=3, now="t2")
    with pytest.raises(SystemExit) as exc:
        stack.push(s, "q4", "u4", cap=3, now="t3")
    msg = str(exc.value)
    assert "depth 4 exceeds the cap of 3" in msg
    assert "pop and file a card" in msg
    assert "promote the excursion" in msg
    assert "escalate" in msg


def test_pop_requires_outcome():
    s = stack.push({"session": "s1", "frames": []}, "q", "u", cap=3, now="t0")
    with pytest.raises(SystemExit) as exc:
        stack.pop(s, "not-a-real-outcome", None, now="t1")
    assert "--outcome" in str(exc.value)


def test_pop_with_no_open_frame_refused():
    empty = {"session": "s1", "frames": []}
    with pytest.raises(SystemExit) as exc:
        stack.pop(empty, "answered", None, now="t0")
    assert "no open excursion" in str(exc.value)


def test_pop_closes_frame_and_restates_parent_goal():
    s = {"session": "s1", "frames": []}
    s = stack.push(s, "parent question", "unblocks top", cap=3, now="t0")
    s = stack.push(s, "child question", "unblocks parent", cap=3, now="t1")
    s, parent_goal = stack.pop(s, "answered", "stale cache", now="t2")
    assert parent_goal == "parent question"
    child = s["frames"][-1]
    assert child["closed"] == "t2"
    assert child["outcome"] == "answered: stale cache"


def test_pop_last_frame_returns_no_parent_goal():
    s = stack.push({"session": "s1", "frames": []}, "q", "u", cap=3, now="t0")
    s, parent_goal = stack.pop(s, "abandoned", None, now="t1")
    assert parent_goal is None
    assert s["frames"][-1]["outcome"] == "abandoned"


# --- lint: never silently vanish --------------------------------------------

def test_check_stack_empty_missing_file_is_pass_not_none(tmp_path):
    row = stack.check_stack_empty(tmp_path)
    assert row is not None
    assert row.status == "PASS"
    assert row.name  # a real Row, not a stand-in


def test_check_stack_empty_with_open_frame_fails(tmp_path):
    path = tmp_path / ".agent" / "stack.json"
    s = stack.push({"session": "s1", "frames": []}, "q", "u", cap=3, now="t0")
    stack.save_stack(path, s)
    row = stack.check_stack_empty(tmp_path)
    assert row.status == "FAIL"
    assert "q" in row.detail


def test_check_stack_empty_all_closed_passes(tmp_path):
    path = tmp_path / ".agent" / "stack.json"
    s = stack.push({"session": "s1", "frames": []}, "q", "u", cap=3, now="t0")
    s, _ = stack.pop(s, "answered", None, now="t1")
    stack.save_stack(path, s)
    row = stack.check_stack_empty(tmp_path)
    assert row.status == "PASS"


# --- CLI end to end -----------------------------------------------------------

def test_cli_push_refused_without_reason(tmp_path):
    stack_path = tmp_path / "stack.json"
    r = subprocess.run(
        [sys.executable, str(Path(__file__).parent / "stack.py"),
         "push", "--question", "why", "--session", "s1", "--stack-path", str(stack_path)],
        capture_output=True, text=True,
    )
    assert r.returncode != 0
    assert "--unblocks" in (r.stdout + r.stderr)
    assert not stack_path.exists()


def test_cli_push_to_depth_four_refused(tmp_path):
    stack_path = tmp_path / "stack.json"
    exe = [sys.executable, str(Path(__file__).parent / "stack.py")]
    for i in range(3):
        r = subprocess.run(exe + ["push", "--question", f"q{i}", "--unblocks", f"u{i}",
                                   "--session", "s1", "--stack-path", str(stack_path)],
                            capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
    r = subprocess.run(exe + ["push", "--question", "q4", "--unblocks", "u4",
                               "--stack-path", str(stack_path)],
                        capture_output=True, text=True)
    assert r.returncode != 0
    out = r.stdout + r.stderr
    assert "exceeds the cap of 3" in out
    assert "pop and file a card" in out


def test_cli_pop_refused_without_outcome(tmp_path):
    stack_path = tmp_path / "stack.json"
    exe = [sys.executable, str(Path(__file__).parent / "stack.py")]
    subprocess.run(exe + ["push", "--question", "q", "--unblocks", "u",
                           "--session", "s1", "--stack-path", str(stack_path)],
                   capture_output=True, text=True)
    r = subprocess.run(exe + ["pop", "--stack-path", str(stack_path)],
                        capture_output=True, text=True)
    assert r.returncode != 0
    assert "--outcome" in (r.stdout + r.stderr)


def test_cli_pop_restates_parent_goal(tmp_path):
    stack_path = tmp_path / "stack.json"
    exe = [sys.executable, str(Path(__file__).parent / "stack.py")]
    subprocess.run(exe + ["push", "--question", "parent q", "--unblocks", "top",
                           "--session", "s1", "--stack-path", str(stack_path)],
                   capture_output=True, text=True)
    subprocess.run(exe + ["push", "--question", "child q", "--unblocks", "parent q",
                           "--stack-path", str(stack_path)],
                   capture_output=True, text=True)
    r = subprocess.run(exe + ["pop", "--outcome", "answered", "--stack-path", str(stack_path)],
                        capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "parent q" in r.stdout


def test_cli_selftest_runs_from_outside_repo(tmp_path):
    r = subprocess.run(
        [sys.executable, str(Path(__file__).parent / "stack.py"), "--selftest"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "cases pass" in r.stdout


# --- integration: git_notes.py add-profile accepts our schema unchanged ------

def test_stack_written_by_cli_accepted_by_git_notes_add_profile(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    sha = _commit(repo, "some work")
    stack_path = tmp_path / "stack.json"
    exe = [sys.executable, str(Path(__file__).parent / "stack.py")]
    subprocess.run(exe + ["push", "--question", "why does X fail under load",
                           "--unblocks", "confirms D-03 can proceed without a rewrite",
                           "--session", "2026-08-02-a", "--stack-path", str(stack_path)],
                   capture_output=True, text=True, check=True)
    r = subprocess.run(exe + ["pop", "--outcome", "answered", "--note", "stale cache",
                               "--stack-path", str(stack_path)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr

    monkeypatch.chdir(repo)  # git_notes runs git in the cwd; without this it writes
                             # the note into whatever repo pytest was launched from
    rc = git_notes.main([
        "add-profile", "--commit", sha, "--stack-path", str(stack_path),
    ])
    assert rc == 0

    note = subprocess.run(
        ["git", "-C", str(repo), "notes", "--ref", git_notes.NOTES_REF, "show", sha],
        capture_output=True, text=True,
    )
    assert note.returncode == 0, note.stderr
    payload = json.loads(note.stdout)
    assert payload["session"] == "2026-08-02-a"
    assert payload["frames"][0]["outcome"] == "answered: stale cache"
    assert payload["frames"][0]["question"] == "why does X fail under load"


def test_selftest_exits_zero():
    assert stack.main(["--selftest"]) == 0


# ---------------------------------------------------------------------------
# start: a session that never dives must still be recordable
# ---------------------------------------------------------------------------

def test_start_creates_a_depth_zero_stack(tmp_path):
    """The bug this fixes: the file only came into existence on the first push, so a session
    that legitimately stayed at depth 0 was indistinguishable from one never tracked at all."""
    path = tmp_path / ".agent" / "stack.json"
    stack.start(path, "2026-08-02-c", now="t0")
    assert path.exists()
    state = json.loads(path.read_text())
    assert state["session"] == "2026-08-02-c"
    assert state["frames"] == []


def test_start_is_idempotent_for_the_same_session(tmp_path):
    path = tmp_path / ".agent" / "stack.json"
    stack.start(path, "s1", now="t0")
    stack.push_cmd_free_marker = True
    stack.start(path, "s1", now="t0")  # re-running /dev must not wipe the session's frames
    assert json.loads(path.read_text())["session"] == "s1"


def test_start_preserves_frames_when_rerun(tmp_path):
    path = tmp_path / ".agent" / "stack.json"
    stack.start(path, "s1", now="t0")
    state = stack.load_stack(path)
    stack.push(state, "why", "unblocks parent", cap=3, now="t0")
    stack.save_stack(path, state)
    stack.start(path, "s1", now="t1")
    assert len(stack.load_stack(path)["frames"]) == 1, "re-running start ate a live excursion"


def test_start_refuses_a_stale_session_naming_the_fix(tmp_path):
    path = tmp_path / ".agent" / "stack.json"
    stack.start(path, "2026-08-01-a", now="t0")
    with pytest.raises(SystemExit) as exc:
        stack.start(path, "2026-08-02-c", now="t1")
    msg = str(exc.value)
    assert "2026-08-01-a" in msg and "--force" in msg


def test_start_force_replaces_a_stale_session(tmp_path):
    path = tmp_path / ".agent" / "stack.json"
    stack.start(path, "old", now="t0")
    stack.start(path, "new", now="t1", force=True)
    assert stack.load_stack(path)["session"] == "new"


# ---------------------------------------------------------------------------
# the lint that would have caught the whole thing
# ---------------------------------------------------------------------------

def test_check_stack_tracked_fails_when_depth_was_never_measured(tmp_path):
    row = stack.check_stack_tracked(tmp_path)
    assert row.status == "FAIL"
    assert "stack.py start" in row.detail, "the lint must name its own fix"


def test_check_stack_tracked_passes_once_started(tmp_path):
    stack.start(tmp_path / ".agent" / "stack.json", "s1", now="t0")
    assert stack.check_stack_tracked(tmp_path).status == "PASS"


def test_check_stack_tracked_always_emits_a_row(tmp_path):
    # Absence read as success is the bug that recurred three times; both branches emit.
    for started in (False, True):
        if started:
            stack.start(tmp_path / ".agent" / "stack.json", "s1", now="t0")
        assert stack.check_stack_tracked(tmp_path).name == "depth tracked this session"


# ---------------------------------------------------------------------------
# max_depth: what makes the Depth: trailer evidence instead of a claim
# ---------------------------------------------------------------------------

def test_max_depth_counts_closed_frames_too(tmp_path):
    state = stack.empty_stack("s1")
    stack.push(state, "q1", "u1", cap=3, now="t0")
    stack.push(state, "q2", "u2", cap=3, now="t0")
    stack.pop(state, "answered", None, now="t1")
    stack.pop(state, "answered", None, now="t1")
    # Surfaced back to 0, but the session DID reach 2 — that is the number worth reporting.
    assert stack.open_frames(state) == []
    assert stack.max_depth(state) == 2


def test_max_depth_of_a_quiet_session_is_zero(tmp_path):
    assert stack.max_depth(stack.empty_stack("s1")) == 0
