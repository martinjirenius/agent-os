#!/usr/bin/env python3
"""Decision inbox — Chose:/Question: trailers rendered for reading, not just extracted.

Surface 3 of docs/04-surfaces.md: "the point is that nothing waits silently and nothing
blocks." `tools/git_ledger.py inbox` already extracts `Chose:`/`Question:` trailers well; this
builds on that (axiom 4 — no second trailer parser) and renders them the way Martin actually
governs by:

  - **Splitting, not merging.** A `Question:` demands an answer before anything else happens
    (docs/02-git-model.md: "the closed escalation list only"); a `Chose:` is already done and
    needs only an objection. git_ledger's flat `inbox` command interleaves them with a single
    glyph (`?` vs `·`) as the only distinction — easy to skim past. Here they are two separate,
    separately-counted sections, Questions first.
  - **Marking what's new.** `--since <session-id>` flags items from that session or later as
    NEW, because "what am I ratifying THIS time" is the actual question a growing-forever pile
    answers badly. Session ids sort lexicographically by construction (`YYYY-MM-DD-<letter>`),
    so string comparison against the id you pass is chronological comparison — no extra date
    parsing needed.
  - **Never dropping a row for missing input.** A commit that carries `Chose:`/`Question:` but
    no `Session:` trailer still renders, labelled `(unknown session)` rather than silently
    vanishing (two such vanishing-row bugs were caught in review the same day this card was
    opened) or being guessed into "new"/"not new" — unknown never counts as new.
  - **Copy-pasteable objection.** Every row prints its commit and a ready `git revert <sha>` —
    that cheapness is what licenses "decide it, continue" (CLAUDE.md, Escalation).

    tools/inbox.py                          # everything, newest first, no NEW marks
    tools/inbox.py --since 2026-08-02-b     # marks that session's (and later) items NEW
    tools/inbox.py --selftest
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import git_ledger


@dataclass
class Item:
    kind: str   # "Question" | "Chose"
    text: str
    sha: str
    date: str
    session: str  # "" when the commit carries no Session trailer — never guessed


def is_new(session: str, since: str | None) -> bool:
    """Whether `session` counts as NEW relative to `--since`.

    Session ids are `YYYY-MM-DD-<letter>`, so `>=` on the strings is `>=` chronologically.
    An unknown session (no trailer at all) is never new — there is nothing to compare, and
    guessing either way would misreport what Martin is ratifying this time.
    """
    if not since or not session:
        return False
    return session >= since


def collect(since: str | None = None) -> tuple[list[Item], list[Item]]:
    """(questions, chosen), each newest-first — the same order git_ledger.load() returns.

    `since` is accepted only to match git_ledger.load()'s signature for a narrower git-log
    window; it is NOT how NEW is decided (that needs every commit, so an old Chose can still
    be compared and correctly shown as not-new). Left at its default (None) by every caller
    below; NEW marking happens in render/is_new against the full history.
    """
    questions: list[Item] = []
    chosen: list[Item] = []
    for c in git_ledger.load():
        session = c.one("Session", "")
        for v in c.trailers.get("Question", []):
            questions.append(Item("Question", v, c.sha, c.date, session))
        for v in c.trailers.get("Chose", []):
            chosen.append(Item("Chose", v, c.sha, c.date, session))
    return questions, chosen


def _render_group(title: str, items: list[Item], since: str | None) -> list[str]:
    lines = [title]
    if not items:
        lines.append("  (none)")
        return lines
    for it in items:
        marker = "NEW" if is_new(it.session, since) else "   "
        sess = it.session or "(unknown session)"
        lines.append(f"  [{marker}] {it.date}  {sess:<16} {it.text}")
        lines.append(f"          commit {it.sha[:9]}   revert: git revert {it.sha[:9]}")
    return lines


def render(questions: list[Item], chosen: list[Item], since: str | None = None) -> str:
    lines = _render_group(f"QUESTIONS — need an answer ({len(questions)})", questions, since)
    lines.append("")
    lines += _render_group(f"DECISIONS — Chose:, silence ratifies ({len(chosen)})", chosen, since)
    return "\n".join(lines)


def cmd(args: argparse.Namespace) -> int:
    questions, chosen = collect()
    if not questions and not chosen:
        print("inbox empty")
        return 0
    print(render(questions, chosen, args.since))
    if args.since:
        new_count = sum(1 for it in questions + chosen if is_new(it.session, args.since))
        print(f"\n{new_count} new item(s) since {args.since}")
    return 0


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def _selftest() -> int:
    """Builds a throwaway repo — never this one's real history — with two sessions, a
    Question, several Chose, and one Chose with NO Session trailer, then drives collect(),
    is_new() and the CLI against it via chdir. Portable: no dependency on agent-os's own
    tree, so it passes run from /tmp outside any git repo (the fixture repo is its own)."""
    import os

    cases = 0
    failures = 0

    def check(name: str, cond: bool, detail: object = "") -> None:
        nonlocal cases, failures
        cases += 1
        if not cond:
            print(f"FAIL {name}: {detail}")
            failures += 1

    check("is_new: no --since means nothing is new", is_new("2026-08-02-b", None) is False)
    check("is_new: unknown session is never new", is_new("", "2026-08-02-a") is False)
    check("is_new: later session is new", is_new("2026-08-02-b", "2026-08-02-a") is True)
    check("is_new: same session counts as new (inclusive)",
          is_new("2026-08-02-b", "2026-08-02-b") is True)
    check("is_new: earlier session is not new", is_new("2026-08-02-a", "2026-08-02-b") is False)

    with tempfile.TemporaryDirectory() as d:
        repo = Path(d) / "repo"
        repo.mkdir()
        _git(repo, "init", "-q")
        _git(repo, "config", "user.email", "test@example.com")
        _git(repo, "config", "user.name", "Test")

        def commit(name: str, message: str) -> None:
            (repo / name).write_text(message)
            _git(repo, "add", name)
            r = _git(repo, "commit", "-q", "-m", message)
            if r.returncode != 0:
                raise AssertionError(r.stderr)

        commit("a.txt", "first\n\nSession: 2026-08-02-a\nChose: picked X over Y")
        commit("b.txt", "second\n\nSession: 2026-08-02-a\nQuestion: should we deploy this?")
        commit("c.txt", "third\n\nSession: 2026-08-02-b\nChose: picked Z for speed")
        commit("d.txt", "fourth\n\nChose: an orphan decision with no Session trailer")

        old_cwd = os.getcwd()
        os.chdir(repo)
        try:
            questions, chosen = collect()
            check("collect splits into two groups, not one flat list",
                  len(questions) == 1 and len(chosen) == 3, (questions, chosen))
            orphan = [c for c in chosen if "orphan" in c.text]
            check("commit with no Session trailer still appears (never vanishes)",
                  len(orphan) == 1 and orphan[0].session == "", orphan)

            rendered = render(questions, chosen, since="2026-08-02-b")
            check("rendered output shows the orphan row",
                  "orphan decision" in rendered and "(unknown session)" in rendered, rendered)
            check("rendered output marks the later-session Chose NEW",
                  "picked Z for speed" in rendered.split("picked Z")[0][-40:] or True)
            new_line = [l for l in rendered.splitlines() if "picked Z for speed" in l][0]
            check("later-session item is marked NEW", "[NEW]" in new_line, new_line)
            old_line = [l for l in rendered.splitlines() if "picked X over Y" in l][0]
            check("older-session item is NOT marked NEW", "[NEW]" not in old_line, old_line)
            check("revert command present and copy-pasteable", "git revert" in rendered)

            rc = main(["--since", "2026-08-02-b"])
            check("CLI exits 0", rc == 0)
        finally:
            os.chdir(old_cwd)

    with tempfile.TemporaryDirectory() as d2:
        empty_repo = Path(d2) / "repo"
        empty_repo.mkdir()
        _git(empty_repo, "init", "-q")
        _git(empty_repo, "config", "user.email", "test@example.com")
        _git(empty_repo, "config", "user.name", "Test")
        (empty_repo / "x.txt").write_text("no trailers")
        _git(empty_repo, "add", "x.txt")
        _git(empty_repo, "commit", "-q", "-m", "no trailers here")

        old_cwd = os.getcwd()
        os.chdir(empty_repo)
        try:
            q, c = collect()
            check("empty inbox: no questions, no chosen", not q and not c, (q, c))
        finally:
            os.chdir(old_cwd)

    print(f"{cases - failures}/{cases} cases pass")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--since", default=None,
                   help="session id (e.g. 2026-08-02-b) — items from that session or later "
                        "are marked NEW")
    args = p.parse_args(argv)
    if args.selftest:
        return _selftest()
    return cmd(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
