"""Colocated tests for roadmap.py — built against throwaway git repos, never this one's.

Run: python3 -m pytest tools/roadmap_test.py -q
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import git_ledger  # noqa: E402
import roadmap  # noqa: E402


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


MANIFEST = """
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


def _deliverables():
    import tomllib
    return roadmap.load_deliverables(tomllib.loads(MANIFEST))


# ---------------------------------------------------------------------------
# pure computation: levels, exact matching, statuses
# ---------------------------------------------------------------------------

def test_level_is_topological_depth():
    ds = _deliverables()
    by_id = {d.id: d for d in ds}
    assert roadmap.level("D-01", by_id) == 0
    assert roadmap.level("D-02", by_id) == 1
    assert roadmap.level("D-03", by_id) == 2


def test_level_detects_cycles_and_states_the_fix():
    by_id = {
        "D-01": roadmap.Deliverable("D-01", "one", ["D-02"]),
        "D-02": roadmap.Deliverable("D-02", "two", ["D-01"]),
    }
    with pytest.raises(SystemExit) as exc:
        roadmap.level("D-01", by_id)
    assert "cycle" in str(exc.value).lower()


def test_exact_serves_does_not_collide_D1_with_D10():
    c = git_ledger.Commit("sha", "2026-08-02", "subj", {"Serves": ["D-1"]})
    assert roadmap.exact_serves(c, "D-1") is True
    assert roadmap.exact_serves(c, "D-10") is False


def test_distinct_sessions_sorted_chronologically():
    commits = [
        git_ledger.Commit("s1", "2026-08-02", "x", {"Session": ["2026-08-02-b"]}),
        git_ledger.Commit("s2", "2026-08-02", "x", {"Session": ["2026-08-02-a"]}),
        git_ledger.Commit("s3", "2026-08-02", "x", {}),  # no session — must not vanish silently
    ]
    assert roadmap.distinct_sessions(commits) == ["2026-08-02-a", "2026-08-02-b"]


# ---------------------------------------------------------------------------
# status computation against a fixture repo
# ---------------------------------------------------------------------------

def _fixture_landed_in_progress_blocked(tmp_path: Path) -> Path:
    """D-01 landed in session a (no card ever opened for it). D-02 has one closed card
    (B-001) and one still-open card (B-002) — so it must render 'in progress', not landed,
    even though it has a Disposition:done commit in its history. D-03 has zero commits and
    zero cards: not started, and depends on D-02 (not landed) so it is blocked."""
    repo = _init_repo(tmp_path)
    (repo / "project.toml").write_text(MANIFEST)
    _commit(repo, "a.txt", "found it\n\nSession: 2026-08-02-a\nServes: D-01")
    _commit(repo, "b.txt",
            "B-001: x\n\nSession: 2026-08-02-b\nCard: B-001\nServes: D-02\nDisposition: done")
    (repo / "backlog").mkdir()
    (repo / "backlog" / "B-002.md").write_text(
        "---\nid: B-002\ntitle: y\nstatus: todo\nserves: D-02\nopened: 2026-08-02\n---\n\nbody\n"
    )
    return repo


def test_landed_requires_commits_and_no_open_card(tmp_path, monkeypatch):
    repo = _fixture_landed_in_progress_blocked(tmp_path)
    monkeypatch.chdir(repo)
    ds = _deliverables()
    statuses = roadmap.compute_statuses(git_ledger.load(), ds, repo / "backlog")
    by_id = {s.id: s for s in statuses}
    assert by_id["D-01"].state == "landed"
    assert by_id["D-02"].state == "in_progress"  # has commits, but B-002 still open
    assert by_id["D-03"].state == "blocked"      # no commits, depends on D-02 (not landed)


def test_no_deliverable_row_vanishes_even_with_zero_data(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    _commit(repo, "x.txt", "nothing to do with deliverables")
    monkeypatch.chdir(repo)
    ds = _deliverables()
    statuses = roadmap.compute_statuses(git_ledger.load(), ds, repo / "backlog")
    assert {s.id for s in statuses} == {"D-01", "D-02", "D-03"}
    # D-01 has no depends and no commits -> it is the frontier, not "blocked", and not dropped
    assert dict((s.id, s.state) for s in statuses)["D-01"] == "frontier"


def test_malformed_card_is_reported_not_silently_skipped(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    _commit(repo, "x.txt", "seed")
    (repo / "backlog").mkdir()
    (repo / "backlog" / "B-999.md").write_text("not even frontmatter")
    monkeypatch.chdir(repo)
    warnings = roadmap.card_warnings(repo / "backlog")
    assert any("B-999" in w for w in warnings)


# ---------------------------------------------------------------------------
# projection: honesty about confidence
# ---------------------------------------------------------------------------

def test_insufficient_sessions_refuses_to_project_a_number(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    _commit(repo, "a.txt", "one\n\nSession: 2026-08-02-a\nServes: D-01")
    monkeypatch.chdir(repo)
    ds = _deliverables()
    commits = git_ledger.load()
    p = roadmap.project_sessions_out("D-03", commits, ds, repo / "backlog")
    assert p.insufficient is True
    assert p.sessions_observed == 1
    assert p.estimate is None
    text = roadmap.render_projection(p, "D-03")
    assert "insufficient data to project D-03" in text
    assert "1 session" in text


def _fixture_three_sessions(tmp_path: Path) -> Path:
    """Enough sessions to clear MIN_SESSIONS_FOR_PROJECTION, landing one deliverable each
    session, so a numeric (still-hedged) projection becomes possible for what's left."""
    repo = _init_repo(tmp_path)
    _commit(repo, "a.txt", "one\n\nSession: 2026-08-02-a\nServes: D-01")
    _commit(repo, "b.txt", "two\n\nSession: 2026-08-02-b\nServes: D-02")
    _commit(repo, "c.txt", "three\n\nSession: 2026-08-02-c\nServes: D-03")
    return repo


def test_enough_sessions_yields_a_widening_band_not_a_bare_date(tmp_path, monkeypatch):
    repo = _fixture_three_sessions(tmp_path)
    monkeypatch.chdir(repo)
    ds = _deliverables()
    commits = git_ledger.load()
    p = roadmap.project_sessions_out("D-03", commits, ds, repo / "backlog")
    assert p.insufficient is False
    assert p.low is not None and p.high is not None
    assert p.low <= p.estimate <= p.high
    assert p.sessions_observed >= roadmap.MIN_SESSIONS_FOR_PROJECTION


# ---------------------------------------------------------------------------
# ghost bars: slip is the headline
# ---------------------------------------------------------------------------

def test_ghost_bar_appears_when_projection_moves_later(tmp_path, monkeypatch):
    """Simulate slip: as of session c, D-05 looked close; a session d adds no landings at
    all (a stall), so the same deliverable's projected sessions-out grows. That growth must
    render as a visible ghost (old estimate struck through, not silently replaced)."""
    repo = _init_repo(tmp_path)
    _commit(repo, "a.txt", "one\n\nSession: 2026-08-02-a\nServes: D-01")
    _commit(repo, "b.txt", "two\n\nSession: 2026-08-02-b\nServes: D-02")
    _commit(repo, "c.txt", "three\n\nSession: 2026-08-02-c\nServes: D-03")
    _commit(repo, "d.txt", "stall\n\nSession: 2026-08-02-d\nServes: D-03")
    monkeypatch.chdir(repo)
    ds = roadmap.load_deliverables({"deliverables": [
        {"id": "D-01", "title": "one", "depends": []},
        {"id": "D-02", "title": "two", "depends": ["D-01"]},
        {"id": "D-03", "title": "three", "depends": ["D-02"]},
        {"id": "D-04", "title": "four", "depends": ["D-03"]},
        {"id": "D-05", "title": "five", "depends": ["D-04"]},
    ]})
    commits = git_ledger.load()
    history = roadmap.ghost_history("D-05", commits, ds, repo / "backlog")
    assert len(history) >= 2
    slip = roadmap.detect_slip(history)
    assert slip is not None
    old, new = slip
    assert new.estimate >= old.estimate
    text = roadmap.render_ghost(slip, "D-05")
    assert "was" in text.lower()


# ---------------------------------------------------------------------------
# you-are-here depth
# ---------------------------------------------------------------------------

def test_depth_defaults_to_zero_and_says_so_when_stack_missing(tmp_path):
    depth, note = roadmap.current_depth(tmp_path / "nope" / "stack.json")
    assert depth == 0
    assert "default" in note.lower() or "not found" in note.lower() or "no live" in note.lower()


# ---------------------------------------------------------------------------
# CLI, selftest, portability
# ---------------------------------------------------------------------------

def test_cli_pipeline_runs_against_a_real_repo(tmp_path, monkeypatch, capsys):
    repo = _fixture_landed_in_progress_blocked(tmp_path)
    monkeypatch.chdir(repo)
    rc = roadmap.main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "D-01" in out and "D-02" in out and "D-03" in out
    assert "landed" in out


def test_cli_board_shows_only_the_frontier(tmp_path, monkeypatch, capsys):
    repo = _fixture_landed_in_progress_blocked(tmp_path)
    monkeypatch.chdir(repo)
    rc = roadmap.main(["--board"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "D-02" in out  # in-progress deliverable is the current frontier
    assert "D-03" not in out  # blocked, must not appear on the frontier board


def test_selftest_exits_zero():
    assert roadmap.main(["--selftest"]) == 0


def test_selftest_is_portable_outside_any_git_repo(tmp_path):
    r = subprocess.run(
        [sys.executable, str(Path(__file__).parent / "roadmap.py"), "--selftest"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "cases pass" in r.stdout
