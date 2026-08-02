#!/usr/bin/env python3
"""Recover any prior state — a deleted file, a file as of a date, or a file as it stood
before a card/deliverable/tag landed. The mechanism behind /timetravel (docs/02-git-model.md
"Deletion is the archive"): nothing is preserved in the tree for fear of losing it, because
this script gets it back on request.

    tools/timetravel.py find <path-fragment>          # a. deleted file, partial/fuzzy path
    tools/timetravel.py at <path> <date>               # b. a file as of a date (YYYY-MM-DD)
    tools/timetravel.py before <anchor> <path>         # c. a file before <anchor> changed it
                                                        #    anchor: B-0NN | D-0N | state/* tag
                                                        #            | YYYY-MM-DD
    tools/timetravel.py --selftest

Reuses git_ledger.py for trailer parsing and the deleted-file query (axiom 4: one
authority per topic) rather than re-walking `git log` a second way.
"""
from __future__ import annotations

import argparse
import difflib
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import git_ledger

CARD_RE = re.compile(r"^B-\d+$")
DELIVERABLE_RE = re.compile(r"^D-\d+$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def find_deleted(query: str) -> list[git_ledger.Deletion]:
    """Deleted files matching <query> — substring first, then fuzzy over the full path list.

    "Fuzzy" is difflib against every path ever deleted, so a misremembered directory or a
    typo still surfaces a candidate rather than a flat "no such thing".
    """
    rows = git_ledger.deleted()
    q = query.lower()
    hits = [d for d in rows if q in d.path.lower()]
    if hits:
        return hits
    close = difflib.get_close_matches(query, [d.path for d in rows], n=5, cutoff=0.6)
    return [d for d in rows if d.path in close]


def _commit_at_or_before(date: str) -> str:
    """The sha of the newest commit on HEAD at or before <date>, or "" if none exists."""
    out = git_ledger.git_out("rev-list", "-1", f"--before={date}T23:59:59", "HEAD").strip()
    return out


def show_as_of(path: str, date: str) -> str:
    """The content of <path> as it stood at or before <date>.

    Raises SystemExit with a fix-shaped message if the date predates the repo, or the path
    did not exist yet / no longer existed at that point in history.
    """
    if not DATE_RE.match(date):
        raise SystemExit(f"'{date}' is not a date — use YYYY-MM-DD, e.g. 2026-08-02")
    sha = _commit_at_or_before(date)
    if not sha:
        raise SystemExit(f"no commit exists at or before {date} — the repo did not exist "
                          "yet; try a later date or `git log --format=%ad --date=short` "
                          "for the earliest one")
    return _show(sha, path)


def _show(sha: str, path: str) -> str:
    r = subprocess.run(["git", "show", f"{sha}:{path}"], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"'{path}' does not exist at {sha[:9]} — it may not have been "
                          f"created yet, or was deleted earlier; try "
                          f"`tools/timetravel.py find {Path(path).name}` to see when it "
                          "existed")
    return r.stdout


def resolve_anchor(anchor: str) -> str:
    """The commit sha that <anchor> refers to — the reference point `before` steps back from.

    B-0NN / D-0N resolve to the MOST RECENT commit carrying that Card:/Serves: trailer (the
    latest change under that id, which is what "undo this" means in practice); a `state/*`
    tag or any other git tag resolves to the commit it points at; a bare date resolves via
    the same at-or-before rule as `at`.
    """
    if CARD_RE.match(anchor) or DELIVERABLE_RE.match(anchor):
        key = "Card" if CARD_RE.match(anchor) else "Serves"
        commits = [c for c in git_ledger.load() if git_ledger.match_trailer(c, key, anchor)]
        if not commits:
            flag = "--card" if key == "Card" else "--serves"
            raise SystemExit(
                f"no commit carries {key}: {anchor} — check the id, or run "
                f"`tools/git_ledger.py query {flag} {anchor}` to confirm it ever landed"
            )
        return commits[0].sha  # load() is newest-first: [0] is the most recent
    if DATE_RE.match(anchor):
        sha = _commit_at_or_before(anchor)
        if not sha:
            raise SystemExit(f"no commit exists at or before {anchor} — try a later date")
        return sha
    tag_sha = subprocess.run(["git", "rev-list", "-n1", anchor],
                              capture_output=True, text=True)
    if tag_sha.returncode == 0 and tag_sha.stdout.strip():
        return tag_sha.stdout.strip()
    raise SystemExit(f"'{anchor}' is not a recognized anchor — expected a card (B-001), "
                      "a deliverable (D-01), a state/* tag, or a YYYY-MM-DD date; "
                      "`git tag -l 'state/*'` lists the tag anchors")


def show_before(anchor: str, path: str) -> str:
    """The content of <path> immediately before <anchor>'s most recent change."""
    sha = resolve_anchor(anchor)
    parent = subprocess.run(["git", "rev-parse", f"{sha}^"], capture_output=True, text=True)
    if parent.returncode != 0:
        raise SystemExit(f"{sha[:9]} ({anchor}) is the first commit in this repo — there is "
                          "no earlier state to show")
    return _show(parent.stdout.strip(), path)


def cmd_find(args: argparse.Namespace) -> int:
    rows = find_deleted(args.query)
    if not rows:
        print(f"no deleted file matches '{args.query}' — nothing matching that has ever "
              "been removed from this repo (`tools/git_ledger.py deleted` lists everything "
              "that has)")
        return 1
    for d in rows:
        print(f"{d.date}  {d.path}")
        print(f"            removed in {d.sha[:9]} — {d.subject}")
        print(f"            restore: git show {d.sha[:9]}^:{d.path}")
    return 0


def cmd_at(args: argparse.Namespace) -> int:
    sys.stdout.write(show_as_of(args.path, args.date))
    return 0


def cmd_before(args: argparse.Namespace) -> int:
    sys.stdout.write(show_before(args.anchor, args.path))
    return 0


def build_scratch_repo(path: Path) -> None:
    """Build a real throwaway git repo with a known history — the shared fixture.

    Deliberately a real repo rather than mocked git output (under-mock, docs/03-practices.md),
    and deliberately NOT this repo: these tools ship into other projects (D-07), so a selftest
    anchored to agent-os's own shas and tags would fail on every install. Dates are injected so
    the date-based modes are deterministic.

        2026-01-01  notes.txt = "original"   Card: B-100  Serves: D-01
        2026-01-02  notes.txt = "changed"    Card: B-100  Serves: D-01   tag: v1
        2026-01-03  notes.txt deleted
    """
    def run(*args: str, date: str | None = None) -> None:
        env = None
        if date:
            env = {**os.environ, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
        subprocess.run(["git", *args], cwd=path, env=env,
                       capture_output=True, text=True, check=True)

    run("init", "-q")
    run("config", "user.email", "test@example.com")
    run("config", "user.name", "Test")

    (path / "notes.txt").write_text("original\n")
    run("add", "notes.txt")
    run("commit", "-qm", "add notes\n\nSession: t\nCard: B-100\nServes: D-01",
        date="2026-01-01T10:00:00")

    (path / "notes.txt").write_text("changed\n")
    run("add", "notes.txt")
    run("commit", "-qm", "change notes\n\nSession: t\nCard: B-100\nServes: D-01",
        date="2026-01-02T10:00:00")
    run("tag", "v1")

    run("rm", "-q", "notes.txt")
    run("commit", "-qm", "remove notes\n\nSession: t", date="2026-01-03T10:00:00")


def _selftest() -> int:
    """Exercise all three retrieval modes against a real (throwaway) git repo.

    Portable by construction: it builds its own history, so it passes identically in agent-os
    and in every project these tools are installed into.
    """
    cases = 0
    failures = 0

    def check(name: str, cond: bool, detail: object = "") -> None:
        nonlocal cases, failures
        cases += 1
        if not cond:
            print(f"FAIL {name}: {detail}")
            failures += 1

    old_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        build_scratch_repo(Path(tmp))
        os.chdir(tmp)
        try:
            # --- mode (a): find a deleted file ---
            rows = find_deleted("note")  # partial path, not exact
            check("find: fuzzy match on a real deleted file",
                  len(rows) == 1 and rows[0].path == "notes.txt", rows)
            restored = _show(f"{rows[0].sha}^", "notes.txt") if rows else ""
            check("find: the printed restore target actually has content",
                  restored == "changed\n", repr(restored))
            check("find: no false positive on an absent path",
                  find_deleted("nonexistent-xyz") == [])

            # --- mode (b): a file as of a date ---
            check("at: returns the content of that day",
                  show_as_of("notes.txt", "2026-01-01") == "original\n")
            try:
                show_as_of("notes.txt", "2020-01-01")
                check("at: a date predating the repo raises", False, "did not raise")
            except SystemExit as e:
                check("at: a date predating the repo raises", "no commit exists" in str(e), e)

            # --- mode (c): what did X look like before <anchor> ---
            check("before: card anchor shows the pre-change version",
                  show_before("B-100", "notes.txt") == "original\n")
            check("before: tag anchor shows the pre-change version",
                  show_before("v1", "notes.txt") == "original\n")
            check("before: deliverable anchor resolves like a card anchor",
                  show_before("D-01", "notes.txt") == "original\n")
            try:
                resolve_anchor("B-999")
                check("before: an unlanded card anchor errors", False, "did not raise")
            except SystemExit as e:
                check("before: an unlanded card anchor errors", "no commit carries" in str(e), e)
            try:
                resolve_anchor("not-an-anchor-at-all")
                check("before: garbage anchor errors", False, "did not raise")
            except SystemExit as e:
                check("before: garbage anchor errors", "not a recognized anchor" in str(e), e)
        finally:
            os.chdir(old_cwd)

    print(f"{cases - failures}/{cases} cases pass")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--selftest", action="store_true")
    sub = p.add_subparsers(dest="cmd")

    f = sub.add_parser("find"); f.set_defaults(fn=cmd_find)
    f.add_argument("query")

    a = sub.add_parser("at"); a.set_defaults(fn=cmd_at)
    a.add_argument("path"); a.add_argument("date")

    b = sub.add_parser("before"); b.set_defaults(fn=cmd_before)
    b.add_argument("anchor"); b.add_argument("path")

    args = p.parse_args(argv)
    if args.selftest:
        return _selftest()
    if not getattr(args, "fn", None):
        p.print_help()
        return 2
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
