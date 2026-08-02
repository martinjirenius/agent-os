#!/usr/bin/env python3
"""Tests for init.py — colocated per CLAUDE.md, run with `pytest tools/init_test.py`.

Builds throwaway git repos under tmp_path (real git, no mocks — under-mock per
docs/03-practices.md). Never touches this repo: init.py ships into other projects (D-07),
so every fixture here is its own real `git init`, never agent-os itself.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import init


def make_git_repo(tmp: Path) -> Path:
    repo = tmp / "project"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, check=True)
    return repo


# --- refusals ------------------------------------------------------------

def test_refuses_non_git_directory(tmp_path: Path) -> None:
    target = tmp_path / "not_a_repo"
    target.mkdir()
    steps = init.run_init(target)
    assert any(s.status == "error" for s in steps)
    assert init.exit_code(steps) == 1
    assert any("git init" in s.detail for s in steps)


def test_refuses_missing_directory(tmp_path: Path) -> None:
    steps = init.run_init(tmp_path / "does_not_exist")
    assert init.exit_code(steps) == 1
    assert any(s.status == "error" for s in steps)


# --- manifest --------------------------------------------------------------

def test_writes_project_toml_from_template(tmp_path: Path) -> None:
    repo = make_git_repo(tmp_path)
    steps = init.run_init(repo)
    assert init.exit_code(steps) == 0
    manifest = repo / "project.toml"
    assert manifest.exists()
    text = manifest.read_text()
    assert f'name = "{repo.name}"' in text
    assert "temporal-splats" not in text  # the template's own project name, not carried over


def test_never_overwrites_existing_manifest(tmp_path: Path) -> None:
    repo = make_git_repo(tmp_path)
    (repo / "project.toml").write_text("# hand-written, do not touch\n")
    steps = init.run_init(repo)
    manifest_step = next(s for s in steps if s.name == "project.toml")
    assert manifest_step.status == "skipped"
    assert (repo / "project.toml").read_text() == "# hand-written, do not touch\n"


def test_fresh_manifest_stubs_commands_not_temporal_splats_commands(tmp_path: Path) -> None:
    repo = make_git_repo(tmp_path)
    init.run_init(repo)
    text = (repo / "project.toml").read_text()
    assert 'test  = ""' in text or 'test = ""' in text
    assert "pytest" not in text
    assert "temporal_splats" not in text


def test_fresh_manifest_still_has_required_caps(tmp_path: Path) -> None:
    import tomllib
    repo = make_git_repo(tmp_path)
    init.run_init(repo)
    m = tomllib.loads((repo / "project.toml").read_text())
    for cap in ("file_lines", "claude_md_lines", "todo_cards", "wip_cards", "local_skills"):
        assert cap in m["caps"]


# --- commit-msg hook ---------------------------------------------------------

def test_installs_hook_and_sets_hookspath(tmp_path: Path) -> None:
    repo = make_git_repo(tmp_path)
    init.run_init(repo)
    hook = repo / ".githooks" / "commit-msg"
    assert hook.exists()
    assert hook.read_text() == init.HOOK_SOURCE.read_text()
    cfg = subprocess.run(["git", "config", "--get", "core.hooksPath"],
                          cwd=repo, capture_output=True, text=True).stdout.strip()
    assert cfg == ".githooks"


def test_does_not_override_existing_hookspath(tmp_path: Path) -> None:
    repo = make_git_repo(tmp_path)
    subprocess.run(["git", "config", "core.hooksPath", "custom-hooks"], cwd=repo, check=True)
    init.run_init(repo)
    cfg = subprocess.run(["git", "config", "--get", "core.hooksPath"],
                          cwd=repo, capture_output=True, text=True).stdout.strip()
    assert cfg == "custom-hooks"


def test_does_not_overwrite_existing_hook_file(tmp_path: Path) -> None:
    repo = make_git_repo(tmp_path)
    (repo / ".githooks").mkdir()
    (repo / ".githooks" / "commit-msg").write_text("#!/bin/sh\n# custom\n")
    init.run_init(repo)
    assert (repo / ".githooks" / "commit-msg").read_text() == "#!/bin/sh\n# custom\n"


# --- skeleton ----------------------------------------------------------------

def test_creates_docs_and_backlog_dirs(tmp_path: Path) -> None:
    repo = make_git_repo(tmp_path)
    init.run_init(repo)
    assert (repo / "docs").is_dir()
    assert (repo / "backlog").is_dir()


def test_gitignores_out_dir(tmp_path: Path) -> None:
    repo = make_git_repo(tmp_path)
    init.run_init(repo)
    text = (repo / ".gitignore").read_text()
    assert "out/" in text


def test_does_not_copy_skills_directory(tmp_path: Path) -> None:
    repo = make_git_repo(tmp_path)
    init.run_init(repo)
    assert not (repo / "skills").exists()
    assert not (repo / ".claude" / "skills" / "dev").exists()


# --- idempotency ---------------------------------------------------------

def test_running_twice_is_safe_and_reports_skips(tmp_path: Path) -> None:
    repo = make_git_repo(tmp_path)
    first = init.run_init(repo)
    assert init.exit_code(first) == 0
    second = init.run_init(repo)
    assert init.exit_code(second) == 0
    assert all(s.status in ("skipped", "created") for s in second)
    # nothing that was created the first time should be re-created the second time
    assert all(s.status == "skipped" for s in second if s.name == "project.toml")


# --- end to end: the real proof, checks.py runs against an init'd project ----

def test_end_to_end_checks_py_runs_against_installed_project(tmp_path: Path) -> None:
    repo = make_git_repo(tmp_path)
    steps = init.run_init(repo)
    assert init.exit_code(steps) == 0

    checks_py = Path(__file__).resolve().parent / "checks.py"
    r = subprocess.run([sys.executable, str(checks_py)], cwd=repo,
                        capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "FAIL" not in r.stdout


def test_cli_end_to_end_from_outside_repo(tmp_path: Path) -> None:
    """Proves init.py works when invoked with an unrelated cwd, e.g. from /tmp."""
    repo = make_git_repo(tmp_path)
    init_py = Path(__file__).resolve().parent / "init.py"
    r = subprocess.run([sys.executable, str(init_py), str(repo)],
                        cwd="/tmp", capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (repo / "project.toml").exists()
