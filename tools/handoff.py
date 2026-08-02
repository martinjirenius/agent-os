#!/usr/bin/env python3
"""handoff.py — assemble the /wrap handoff draft: gather a session's commits, render it.

The mechanism half of /wrap's "overwrite the handoff" step (docs/02-git-model.md,
docs/05-schema.md: handoff.md is closed-schema, <=40 lines, overwritten every session, never
appended to). Nothing here is stored — it re-derives from git_ledger.py the same way every
other surface does (axiom 1), so there is no second index to go stale.

Two things this script deliberately does NOT decide, because they are judgment, not
mechanism, and the skill that drives this script supplies them instead:

  - the single next action (which unblocked card/deliverable comes next) — that needs
    priorities and the DAG in project.toml, not just this session's commits
  - gotchas worth flagging to the next session — that needs judgment about what surprised
    this session, not a trailer grep

Both are left as a `--next-action`/`--gotchas` override, defaulting to a placeholder the
skill's caller is expected to replace before writing docs/handoff.md.

    tools/handoff.py render --session 2026-08-02-a [--root .] \\
        [--next-action "..."] [--gotchas "..."]
    tools/handoff.py --selftest
"""
from __future__ import annotations

import argparse
import contextlib
import os
import sys
from pathlib import Path

import git_ledger
from git_ledger import Commit

NEXT_ACTION_PLACEHOLDER = "<FILL IN — the single next action and which deliverable it serves>"
GOTCHAS_PLACEHOLDER = "None noted this session."


@contextlib.contextmanager
def _chdir(path: Path):
    """Reused from rot.py's pattern: git_ledger's subprocess calls have no --root of their
    own, so operating on an arbitrary root means chdir'ing into it for the duration."""
    old = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


def session_commits(commits: list[Commit], session: str) -> list[Commit]:
    """This session's commits, oldest first — narrative order for a handoff, whereas
    git_ledger.load() returns newest-first (log order)."""
    matches = [c for c in commits if git_ledger.match_trailer(c, "Session", session)]
    return list(reversed(matches))


def collect_trailer(commits: list[Commit], key: str) -> list[str]:
    """Every value of `key` across commits, first-seen order, duplicates dropped."""
    seen: list[str] = []
    for c in commits:
        for v in c.trailers.get(key, []):
            if v not in seen:
                seen.append(v)
    return seen


def repo_state(root: Path) -> tuple[str, bool]:
    """(branch, is_clean) for root — a plain git status, nothing derived from it."""
    with _chdir(root):
        branch = git_ledger.git_out("rev-parse", "--abbrev-ref", "HEAD").strip()
        dirty = git_ledger.git_out("status", "--porcelain").strip()
    return branch, not dirty


def render(
    session: str,
    commits: list[Commit],
    branch: str,
    clean: bool,
    next_action: str = NEXT_ACTION_PLACEHOLDER,
    gotchas: str = GOTCHAS_PLACEHOLDER,
) -> str:
    """Render the handoff draft. Pure function of its arguments — no I/O — so the CLI below
    is a thin wrapper over it and everything interesting here is unit-testable directly."""
    date = "-".join(session.split("-")[:3]) or session
    lines = [
        "# Handoff",
        "",
        "Overwritten at the end of every session by `/wrap`. History: "
        "`git log -- docs/handoff.md`.",
        "",
        f"## Last session ({date}, session `{session}`)",
        "",
    ]
    if commits:
        for c in commits:
            card = c.one("Card")
            disp = c.one("Disposition")
            tag = ""
            if card:
                tag = f" [{card}" + (f", {disp}" if disp else "") + "]"
            lines.append(f"- {c.subject}{tag}")
    else:
        lines.append(f"No commits recorded for session `{session}`.")

    lines += [
        "",
        "## Repo state",
        "",
        f"Branch `{branch}`, {'clean' if clean else 'dirty'}.",
        "",
        "## Next action",
        "",
        next_action,
        "",
        "## Open questions / pending decisions",
        "",
    ]
    question = collect_trailer(commits, "Question")
    chose = collect_trailer(commits, "Chose")
    if question or chose:
        lines += [f"- Question: {q}" for q in question]
        lines += [f"- Chose: {c}" for c in chose]
    else:
        lines.append("None recorded this session.")

    lines += [
        "",
        "## Gotchas",
        "",
        gotchas,
        "",
    ]
    return "\n".join(lines)


def cmd_render(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    with _chdir(root):
        commits = git_ledger.load()
    branch, clean = repo_state(root)
    mine = session_commits(commits, args.session)
    print(render(args.session, mine, branch, clean, args.next_action, args.gotchas))
    return 0


def _selftest() -> int:
    import subprocess
    import tempfile

    cases = 0
    failures = 0

    def check(name: str, cond: bool, detail: object = "") -> None:
        nonlocal cases, failures
        cases += 1
        if not cond:
            print(f"FAIL {name}: {detail}")
            failures += 1

    fixture = [
        Commit("aaa", "2026-08-02", "third",
               {"Session": ["2026-08-02-a"], "Chose": ["use X"]}),
        Commit("bbb", "2026-08-02", "second",
               {"Session": ["2026-08-02-a"], "Card": ["B-002"], "Disposition": ["done"]}),
        Commit("ccc", "2026-08-01", "unrelated", {"Session": ["2026-08-01-a"]}),
        Commit("ddd", "2026-08-02", "first", {"Session": ["2026-08-02-a"]}),
    ]

    mine = session_commits(fixture, "2026-08-02-a")
    check("session_commits filters and reverses to oldest-first",
          [c.sha for c in mine] == ["ddd", "bbb", "aaa"], mine)

    check("collect_trailer dedups and preserves order",
          collect_trailer(fixture, "Session") == ["2026-08-02-a", "2026-08-01-a"],
          collect_trailer(fixture, "Session"))

    check("collect_trailer on an absent key is empty",
          collect_trailer(fixture, "Finding") == [])

    text = render("2026-08-02-a", mine, "main", True)
    check("render lists commits in narrative order",
          text.index("first") < text.index("second") < text.index("third"), text)
    check("render tags a card with its disposition",
          "[B-002, done]" in text, text)
    check("render surfaces a Chose: trailer under open questions",
          "Chose: use X" in text, text)
    check("render defaults next action to the placeholder",
          NEXT_ACTION_PLACEHOLDER in text, text)
    check("render states the branch and clean/dirty status",
          "Branch `main`, clean." in text, text)

    empty_text = render("2026-08-03-a", [], "main", False,
                         next_action="do the thing", gotchas="watch out for Y")
    check("render with no commits says so plainly",
          "No commits recorded for session `2026-08-03-a`." in empty_text, empty_text)
    check("render with no Chose/Question says so plainly",
          "None recorded this session." in empty_text, empty_text)
    check("render honors --next-action override",
          "do the thing" in empty_text, empty_text)
    check("render honors --gotchas override",
          "watch out for Y" in empty_text, empty_text)
    check("render dirty repo says dirty",
          "Branch `main`, dirty." in empty_text, empty_text)

    # End-to-end via a throwaway git repo, run with cwd there — proves this reads real repo
    # state (branch, trailers) rather than the fixtures above, without touching agent-os.
    with tempfile.TemporaryDirectory() as d:
        repo = Path(d) / "repo"
        repo.mkdir()

        def git(*a: str) -> subprocess.CompletedProcess:
            return subprocess.run(["git", "-C", str(repo), *a],
                                   capture_output=True, text=True)

        git("init", "-q")
        git("config", "user.email", "test@example.com")
        git("config", "user.name", "Test")
        (repo / "f.txt").write_text("x")
        git("add", "f.txt")
        msg = "do the work\n\nSession: 2026-08-02-z\nCard: B-999\nServes: D-99\n"
        r = git("commit", "-q", "-m", msg, "--no-verify")
        check("fixture repo commit succeeds", r.returncode == 0, r.stderr)

        branch, clean = repo_state(repo)
        check("repo_state reports a real branch name", bool(branch), branch)
        check("repo_state reports clean on a fresh commit", clean is True)

        r = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()),
             "render", "--session", "2026-08-02-z", "--root", str(repo)],
            capture_output=True, text=True,
        )
        check("CLI end-to-end exits 0 outside agent-os, no ambient repo needed",
              r.returncode == 0, r.stdout + r.stderr)
        check("CLI end-to-end output carries the fixture's own commit",
              "do the work" in r.stdout and "B-999" in r.stdout, r.stdout)

    print(f"{cases - failures}/{cases} cases pass")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--selftest", action="store_true")
    sub = p.add_subparsers(dest="cmd")

    r = sub.add_parser("render")
    r.set_defaults(fn=cmd_render)
    r.add_argument("--session", required=True)
    r.add_argument("--root", default=".")
    r.add_argument("--next-action", default=NEXT_ACTION_PLACEHOLDER)
    r.add_argument("--gotchas", default=GOTCHAS_PLACEHOLDER)

    args = p.parse_args(argv)
    if args.selftest:
        return _selftest()
    if not getattr(args, "fn", None):
        p.print_help()
        return 2
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
