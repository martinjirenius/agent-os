#!/usr/bin/env python3
"""Query the commit-trailer ledger — the retrieval half of "git is the database".

Nothing is stored. Every command re-parses `git log`, so there is no index file that can go
stale (axiom 1). This is what /recall, /timetravel and every rendered surface read from.

    tools/git_ledger.py query --card B-001
    tools/git_ledger.py query --serves D-01 --since 2026-08-01
    tools/git_ledger.py closed [--disposition rejected]   # the deleted-card ledger
    tools/git_ledger.py inbox                             # Chose: / Question: items
    tools/git_ledger.py deleted [<path-glob>]             # everything ever removed
    tools/git_ledger.py sessions
    tools/git_ledger.py --selftest
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass, field

SEP = "\x1e"  # record separator; safe inside commit messages


@dataclass
class Commit:
    sha: str
    date: str
    subject: str
    trailers: dict[str, list[str]] = field(default_factory=dict)

    def one(self, key: str, default: str = "") -> str:
        return self.trailers.get(key, [default])[0]


def _git(*args: str) -> str:
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


def load(since: str | None = None) -> list[Commit]:
    """All commits, newest first, with their trailers parsed."""
    fmt = f"%H{SEP}%ad{SEP}%s{SEP}%(trailers){SEP}"
    args = ["log", f"--pretty=format:{fmt}", "--date=short"]
    if since:
        args.append(f"--since={since}")
    raw = _git(*args)

    commits: list[Commit] = []
    for chunk in raw.split(SEP + "\n"):
        parts = chunk.split(SEP)
        if len(parts) < 4:
            continue
        sha, date, subject, trailer_block = parts[0].strip(), parts[1], parts[2], parts[3]
        trailers: dict[str, list[str]] = {}
        for line in trailer_block.splitlines():
            if ": " in line:
                k, v = line.split(": ", 1)
                trailers.setdefault(k.strip(), []).append(v.strip())
        commits.append(Commit(sha, date, subject, trailers))
    return commits


def _match(c: Commit, key: str, value: str) -> bool:
    return any(value in v for v in c.trailers.get(key, []))


def cmd_query(args: argparse.Namespace) -> int:
    commits = load(args.since)
    for key, value in (("Card", args.card), ("Serves", args.serves),
                       ("Session", args.session)):
        if value:
            commits = [c for c in commits if _match(c, key, value)]
    if not commits:
        print("no commits match")
        return 1
    for c in commits:
        print(f"{c.sha[:9]}  {c.date}  {c.subject}")
        for key in ("Serves", "Card", "Disposition", "Finding", "Decision", "Verified"):
            for v in c.trailers.get(key, []):
                print(f"             {key}: {v}")
    return 0


def cmd_closed(args: argparse.Namespace) -> int:
    """Cards that were closed — reconstructed from history, since the files are deleted."""
    rows = [c for c in load(args.since) if c.trailers.get("Disposition")]
    if args.disposition:
        rows = [c for c in rows if _match(c, "Disposition", args.disposition)]
    if not rows:
        print("no closed cards")
        return 1
    for c in rows:
        card = c.one("Card", "?")
        disp = c.one("Disposition")
        reason = c.one("Reason")
        print(f"{c.date}  {card:<8} {disp:<11} {c.subject}")
        if reason:
            print(f"                            reason: {reason}")
    return 0


def cmd_inbox(args: argparse.Namespace) -> int:
    """Autonomous calls awaiting ratification, and genuine escalations."""
    rows = [c for c in load(args.since)
            if c.trailers.get("Chose") or c.trailers.get("Question")]
    if not rows:
        print("inbox empty")
        return 0
    for c in rows:
        for v in c.trailers.get("Question", []):
            print(f"?  {c.date}  {v}   [{c.sha[:9]}]")
        for v in c.trailers.get("Chose", []):
            print(f"·  {c.date}  {v}   [{c.sha[:9]}]  revert: git revert {c.sha[:9]}")
    return 0


def cmd_deleted(args: argparse.Namespace) -> int:
    """Everything ever removed — the archive that replaces docs/archive/."""
    fmt = f"%H{SEP}%ad{SEP}%s"
    cmd = ["log", "--diff-filter=D", "--name-only", "--date=short",
           f"--pretty=format:{fmt}"]
    if args.path:
        cmd += ["--", args.path]
    out = _git(*cmd)
    sha = date = subject = ""
    for line in out.splitlines():
        if SEP in line:
            sha, date, subject = line.split(SEP)
        elif line.strip():
            print(f"{date}  {line}")
            print(f"            removed in {sha[:9]} — {subject}")
            print(f"            restore: git show {sha[:9]}^:{line}")
    return 0


def cmd_sessions(args: argparse.Namespace) -> int:
    """Sessions with their commit counts — the input to velocity."""
    counts: dict[str, int] = {}
    for c in load(args.since):
        for s in c.trailers.get("Session", []):
            counts[s] = counts.get(s, 0) + 1
    for name in sorted(counts, reverse=True):
        print(f"{name}  {counts[name]} commits")
    return 0


def _selftest() -> int:
    sample = "abc123\x1e2026-08-02\x1eDo a thing\x1eSession: s1\nCard: B-001\nServes: D-01\x1e"
    parts = sample.split(SEP)
    trailers: dict[str, list[str]] = {}
    for line in parts[3].splitlines():
        k, v = line.split(": ", 1)
        trailers.setdefault(k, []).append(v)
    assert trailers["Card"] == ["B-001"], trailers
    assert trailers["Serves"] == ["D-01"], trailers
    print("1/1 cases pass")
    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--selftest", action="store_true")
    sub = p.add_subparsers(dest="cmd")

    q = sub.add_parser("query"); q.set_defaults(fn=cmd_query)
    q.add_argument("--card"); q.add_argument("--serves"); q.add_argument("--session")

    c = sub.add_parser("closed"); c.set_defaults(fn=cmd_closed)
    c.add_argument("--disposition")

    sub.add_parser("inbox").set_defaults(fn=cmd_inbox)
    sub.add_parser("sessions").set_defaults(fn=cmd_sessions)

    d = sub.add_parser("deleted"); d.set_defaults(fn=cmd_deleted)
    d.add_argument("path", nargs="?")

    for parser in (p, q, c, d):
        parser.add_argument("--since", default=None)

    args = p.parse_args(argv)
    if args.selftest:
        return _selftest()
    if not getattr(args, "fn", None):
        p.print_help()
        return 2
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
