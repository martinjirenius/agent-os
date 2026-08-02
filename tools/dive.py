#!/usr/bin/env python3
"""Dive profile — render the session excursion stack, live or historical, ONE renderer.

Surface 3 of docs/04-surfaces.md / docs/02-git-model.md's "two sources, one renderer":
depth changes live in `.agent/stack.json` (gitignored, many writes per session); the
historical replay for a past session comes off a git note whose payload is that identical
JSON, written by `tools/git_notes.py add-profile`. If this module had a second code path that
re-derived the frame shape for history, the card would be failed by definition — so both
paths are built to go through the exact same two chokepoints:

  1. **Validation**: `read_live` and `read_historical` both hand their raw JSON to
     `git_notes.load_stack` — imported, not reimplemented (axiom 4, "one authority per
     topic"). `read_historical` gets there by writing the note's text to a throwaway file and
     calling the identical function `read_live` calls; there is exactly one piece of code on
     disk that decides whether a stack payload is well-formed, and it lives in git_notes.py,
     not here.
  2. **Rendering**: both loaders return the same `{"session": ..., "frames": [...]}` shape,
     and only one function, `render()`, ever turns that shape into text. Nothing downstream
     of `render()` knows or cares which source produced its input.

A missing live stack (the common case — most sessions end without ever pushing an excursion,
and the file is gitignored so a fresh checkout never has it) is NOT the same as a session that
ran and never dove: the former prints "no live stack found" and returns before touching
render(); the latter calls render() on an empty frame list, which prints "0 excursions" — a
session that provably surfaced. Collapsing those two into one message would misreport "session
had no dives" on a machine that simply never wrote the file.

    tools/dive.py                          # live .agent/stack.json in the cwd project
    tools/dive.py --stack-path PATH        # live stack at an explicit path
    tools/dive.py --commit SHA             # historical: the git note on SHA
    tools/dive.py --selftest
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import git_notes  # the ONE schema loader/validator, reused for both sources — not duplicated

DEFAULT_STACK_PATH = git_notes.DEFAULT_STACK_PATH
NOTES_REF = git_notes.NOTES_REF


def read_live(path: Path) -> dict | None:
    """The live source. None means "no stack file at all" — visibly different from a stack
    file that exists with zero frames. Raises SystemExit (via git_notes.load_stack) on a
    malformed file, same as every other tool in this repo — a defect in the file is not the
    same case as its absence."""
    if not path.exists():
        return None
    return git_notes.load_stack(path)


def read_historical(sha: str) -> dict | None:
    """The historical source. None means "no dive-profile note on this commit". The note's
    raw text is written to a throwaway file and handed to the SAME `git_notes.load_stack`
    that validates the live file — this is the mechanism that makes "one renderer" true for
    validation, not just for the final text: there is one function on earth that accepts or
    rejects a stack payload, and both sources reach it.
    """
    resolved = git_notes.resolve_commit_or_die(sha)
    r = subprocess.run(["git", "notes", "--ref", NOTES_REF, "show", resolved],
                        capture_output=True, text=True)
    if r.returncode != 0:
        return None
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d) / "note-stack.json"
        tmp.write_text(r.stdout)
        return git_notes.load_stack(tmp)


def _frame_line(f: dict) -> list[str]:
    status = "still open (unresolved at session end)" if f["closed"] is None else f["outcome"]
    lines = [
        f"  depth {f['depth']}  {f['question']}",
        f"           unblocks: {f['unblocks']}",
        f"           opened:   {f['opened']}",
    ]
    if f["closed"] is not None:
        lines.append(f"           closed:   {f['closed']}")
    lines.append(f"           outcome:  {status}")
    return lines


def render(profile: dict) -> str:
    """THE renderer — the only function that turns a {"session","frames"} dict into text.
    Called identically whether that dict came from read_live or read_historical."""
    session = profile["session"] or "(unset)"
    frames = profile["frames"]
    if not frames:
        return f"session {session} — 0 excursions (never left depth 0)"

    depths = [f["depth"] for f in frames]
    unresolved = [f for f in frames if f["closed"] is None]
    lines = [
        f"session {session} — {len(frames)} excursion(s), deepest depth {max(depths)}"
        + (f", {len(unresolved)} unresolved at session end" if unresolved else ""),
        "",
    ]
    for f in frames:
        lines.extend(_frame_line(f))
        lines.append("")
    return "\n".join(lines).rstrip("\n")


def cmd(args: argparse.Namespace) -> int:
    if args.commit:
        profile = read_historical(args.commit)
        if profile is None:
            print(
                f"no dive-profile note on {args.commit} — a session's profile is written by "
                f"`tools/git_notes.py add-profile` at /wrap; if this commit predates that, "
                f"there is nothing to replay."
            )
            return 0
        print(f"# dive profile — historical note on {args.commit[:9]}")
        print(render(profile))
        return 0

    path = Path(args.stack_path)
    profile = read_live(path)
    if profile is None:
        print(
            f"no live stack found at {path} — this is normal outside an active session "
            f"(.agent/stack.json is gitignored and only exists mid-session); it does NOT mean "
            f"a past session had zero dives. Pass --commit <sha> to replay a session's "
            f"historical profile from its git note instead."
        )
        return 0
    print(f"# dive profile — live {path}")
    print(render(profile))
    return 0


def _selftest() -> int:
    """Builds a throwaway git repo, proves: a missing live file is visibly distinct from an
    empty-frames session; a live stack.json and a git note carrying the identical payload
    render byte-for-byte identically through render(); a missing note is visible, not a
    crash. Portable — passes from /tmp outside any repo, since the fixture is its own."""
    import os

    cases = 0
    failures = 0

    def check(name: str, cond: bool, detail: object = "") -> None:
        nonlocal cases, failures
        cases += 1
        if not cond:
            print(f"FAIL {name}: {detail}")
            failures += 1

    stack = {
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
                "question": "is the cache shared across workers",
                "unblocks": "settles whether the stale-cache theory holds",
                "opened": "2026-08-02T14:05:00Z",
                "closed": None,
                "outcome": None,
            },
        ],
    }

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        check("missing live file returns None, not a crash",
              read_live(tmp / "absent.json") is None)

        p = tmp / "stack.json"
        p.write_text(json.dumps(stack))
        loaded = read_live(p)
        check("present live file round-trips through git_notes' validator", loaded == stack)

        rendered = render(loaded)
        check("render shows both depths", "depth 1" in rendered and "depth 2" in rendered)
        check("render shows the closed frame's outcome", "stale cache" in rendered)
        check("render marks the open frame unresolved", "still open" in rendered)

        empty = {"session": "2026-08-02-z", "frames": []}
        check("zero-frame session renders '0 excursions', distinct from a missing file",
              "0 excursions" in render(empty))

    with tempfile.TemporaryDirectory() as d2:
        repo = Path(d2) / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
        (repo / "f.txt").write_text("work")
        subprocess.run(["git", "add", "f.txt"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "some work"], cwd=repo, check=True)
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True,
                              text=True, check=True).stdout.strip()

        old_cwd = os.getcwd()
        os.chdir(repo)
        try:
            check("missing note returns None, not a crash", read_historical(sha) is None)

            stack_path = repo / "stack.json"
            stack_path.write_text(json.dumps(stack))
            rc = git_notes.main(
                ["add-profile", "--commit", sha, "--stack-path", str(stack_path)])
            check("fixture: add-profile writes the note", rc == 0)

            historical = read_historical(sha)
            check("historical note round-trips through the SAME validator as the live file",
                  historical == stack, historical)
            check("live and historical render BYTE-FOR-BYTE identically (one renderer)",
                  render(read_live(stack_path)) == render(historical))

            rc = main(["--commit", sha])
            check("CLI --commit exits 0", rc == 0)
        finally:
            os.chdir(old_cwd)

    print(f"{cases - failures}/{cases} cases pass")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--stack-path", default=str(DEFAULT_STACK_PATH))
    p.add_argument("--commit", default=None, help="render the historical note on this commit")
    args = p.parse_args(argv)
    if args.selftest:
        return _selftest()
    return cmd(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
