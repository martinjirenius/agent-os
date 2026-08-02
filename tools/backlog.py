#!/usr/bin/env python3
"""backlog.py — cards as data; closing a card deletes the file, not a status flip.

Cards are the only mutable, hand-authored state this repo keeps for planned work
(docs/05-schema.md "Card schema"). Status is a frontmatter field, not a folder, and a done
card is deleted in the commit that lands its work (CLAUDE.md "Done cards are deleted") — the
ledger is reconstructed from `Disposition:` trailers by `git_ledger.py closed`. Nothing here
is stored beyond the working tree (axiom 1): `list`/`lint` re-parse `backlog/*.md` every run.

The one lint checks.py deliberately did not implement — every card `serves:` a deliverable
that exists in project.toml's `[[deliverables]]` — lives here, because it needs a real card
parser. A card the parser cannot read is drift, not a skip: `check_serves`, `check_wip_cards`
and `check_todo_cards` all fail loudly, naming the file, rather than silently ignoring it.

    tools/backlog.py new --title "..." --serves D-04 [--root PATH] [--body "..."]
    tools/backlog.py close B-005 [--disposition done|rejected|superseded|obsolete|deferred]
                                  [--reason "..."] [--root PATH]
    tools/backlog.py list [--root PATH]
    tools/backlog.py lint [--root PATH]
    tools/backlog.py --selftest
"""
from __future__ import annotations

import argparse
import contextlib
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import checks  # find_manifest/load_manifest/Row: one authority per topic (axiom 4)
import git_ledger  # historical Card: trailers, so a deleted id is never reissued


@contextlib.contextmanager
def _chdir(path: Path):
    """git_ledger.git_out() always runs against cwd, not an explicit root — without this,
    next_id() invoked from inside agent-os would read agent-os's OWN git history instead of
    the target project's, which is exactly the kind of ambient-path bug D-07 exists to catch."""
    old = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


REQUIRED_FIELDS = ("id", "title", "status", "serves", "opened")
VALID_STATUSES = ("todo", "doing")
DISPOSITIONS = ("done", "rejected", "superseded", "obsolete", "deferred")
ID_RE = re.compile(r"^B-(\d+)$")


@dataclass
class Card:
    path: Path
    id: str
    title: str
    status: str
    serves: str
    opened: str


@dataclass
class CardError:
    """A card file that could not be parsed — a lint failure, never a silent skip."""
    path: Path
    message: str


def parse_card(path: Path) -> Card | CardError:
    """Parse one backlog card against docs/05-schema.md's frontmatter schema.

    Never raises: an unparseable file comes back as a CardError naming the fix, since a card
    the parser cannot read is exactly the drift this tool exists to catch.
    """
    lines = path.read_text(errors="ignore").splitlines()
    if not lines or lines[0].strip() != "---":
        return CardError(path, "missing opening '---' frontmatter delimiter — add YAML "
                          "frontmatter per docs/05-schema.md 'Card schema'")
    try:
        end = lines.index("---", 1)
    except ValueError:
        return CardError(path, "missing closing '---' frontmatter delimiter — add YAML "
                          "frontmatter per docs/05-schema.md 'Card schema'")
    fields: dict[str, str] = {}
    for line in lines[1:end]:
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        fields[k.strip()] = v.strip()
    missing = [f for f in REQUIRED_FIELDS if not fields.get(f)]
    if missing:
        return CardError(path, "missing required frontmatter field(s): " +
                          ", ".join(missing) + " — see docs/05-schema.md 'Card schema'")
    if fields["status"] not in VALID_STATUSES:
        return CardError(path, f"status {fields['status']!r} must be one of "
                          f"{'|'.join(VALID_STATUSES)}")
    return Card(path=path, id=fields["id"], title=fields["title"], status=fields["status"],
                serves=fields["serves"], opened=fields["opened"])


def load_cards(backlog_dir: Path) -> list[Card | CardError]:
    """Every card in backlog_dir, parsed — the single read shared by list/lint/close."""
    if not backlog_dir.exists():
        return []
    return [parse_card(p) for p in sorted(backlog_dir.glob("*.md"))]


def _errors(cards: list[Card | CardError]) -> list[CardError]:
    return [c for c in cards if isinstance(c, CardError)]


def _malformed_detail(errs: list[CardError]) -> str:
    return ("malformed card(s) — fix frontmatter (docs/05-schema.md 'Card schema'):\n    " +
            "\n    ".join(f"{e.path.name}: {e.message}" for e in errs))


def deliverable_ids(manifest: dict) -> set[str]:
    """The set of `[[deliverables]]` ids declared in project.toml — what `serves:` may point
    at. Read fresh from the manifest every call; never cached (axiom 1)."""
    return {d["id"] for d in manifest.get("deliverables", []) if "id" in d}


def check_wip_cards(root: Path, cap: int) -> checks.Row | None:
    """WIP <= cap. checks.Row-compatible. An absent backlog/ means zero cards, NOT no row."""
    backlog_dir = root / "backlog"
    name = f"wip_cards <= {cap}"
    cards = load_cards(backlog_dir)
    errs = _errors(cards)
    wip = [c for c in cards if isinstance(c, Card) and c.status == "doing"]
    problems = []
    if errs:
        problems.append(_malformed_detail(errs))
    if len(wip) > cap:
        names = ", ".join(c.path.stem for c in wip)
        problems.append(f"{len(wip)} cards marked doing ({names}), WIP cap is {cap} — finish "
                         "or park one before starting another")
    return checks.Row(name, "FAIL" if problems else "PASS", "\n".join(problems))


def check_todo_cards(root: Path, cap: int) -> checks.Row | None:
    """todo <= cap. checks.Row-compatible. An absent backlog/ means zero cards, NOT no row."""
    backlog_dir = root / "backlog"
    name = f"todo_cards <= {cap}"
    cards = load_cards(backlog_dir)
    errs = _errors(cards)
    todo = [c for c in cards if isinstance(c, Card) and c.status == "todo"]
    problems = []
    if errs:
        problems.append(_malformed_detail(errs))
    if len(todo) > cap:
        problems.append(f"{len(todo)} todo cards, cap is {cap} — close or delete cards "
                         "before opening more (WAY-OF-WORKING.md 'There is no icebox')")
    return checks.Row(name, "FAIL" if problems else "PASS", "\n".join(problems))


def check_serves(root: Path, deliverable_ids_set: set[str]) -> checks.Row | None:
    """Every card `serves:` a deliverable that exists in project.toml's `[[deliverables]]`.

    The load-bearing lint (docs/02-git-model.md "Serves: is the load-bearing one") — checks.py
    delegates it here because it needs the full card parser above.

    These three lints always return a Row, even with no backlog/ directory at all. They
    briefly returned None in that case, and closing the last card in this repo deleted the
    directory (git does not track empty ones), so all three rows silently disappeared and the
    gate reported "all checks pass" while the load-bearing lint was not running. Axiom 1: an
    index that is silently incomplete is worse than none, because it answers "no such thing"
    with false confidence. Zero cards is a PASS you can see, not an absence of evidence.
    """
    backlog_dir = root / "backlog"
    name = "cards serve an existing deliverable"
    cards = load_cards(backlog_dir)
    errs = _errors(cards)
    bad = [c for c in cards if isinstance(c, Card) and c.serves not in deliverable_ids_set]
    problems = []
    if errs:
        problems.append(_malformed_detail(errs))
    if bad:
        problems.append(
            "card serves a deliverable that does not exist in project.toml [[deliverables]] "
            "(docs/05-schema.md 'serves: D-01  # must exist') — fix the id or add the "
            "deliverable:\n    " +
            "\n    ".join(f"{c.path.name}: serves {c.serves!r}" for c in bad))
    return checks.Row(name, "FAIL" if problems else "PASS", "\n".join(problems))


def project_root(start: Path) -> Path:
    """Walk upward for project.toml — same convention checks.py uses, reused here."""
    return checks.find_manifest(start).parent


def next_id(root: Path) -> str:
    """The next free B-NNN id: max of every id ever seen (on disk, and in git history via
    `Card:` trailers) plus one, so a deleted card's id is never reissued to a new card."""
    seen: set[int] = set()
    backlog_dir = root / "backlog"
    if backlog_dir.exists():
        for p in backlog_dir.glob("B-*.md"):
            m = ID_RE.match(p.stem)
            if m:
                seen.add(int(m.group(1)))
    try:
        with _chdir(root):
            history = git_ledger.load()
        for commit in history:
            for v in commit.trailers.get("Card", []):
                m = ID_RE.match(v.strip())
                if m:
                    seen.add(int(m.group(1)))
    except SystemExit:
        pass  # not a git repo (or git unavailable) — fall back to what's on disk
    return f"B-{max(seen, default=0) + 1:03d}"


def cmd_new(args: argparse.Namespace) -> int:
    root = project_root(Path(args.root) if args.root else Path.cwd())
    manifest = checks.load_manifest(checks.find_manifest(root))
    d_ids = deliverable_ids(manifest)
    if args.serves not in d_ids:
        known = ", ".join(sorted(d_ids)) or "none defined"
        print(f"error: {args.serves!r} is not a deliverable in project.toml [[deliverables]] "
              f"— add it there first, or pick one of: {known}", file=sys.stderr)
        return 1
    backlog_dir = root / "backlog"
    backlog_dir.mkdir(exist_ok=True)
    new_id = next_id(root)
    path = backlog_dir / f"{new_id}.md"
    body = args.body or "First move: TBD."
    path.write_text(
        f"---\nid: {new_id}\ntitle: {args.title}\nstatus: todo\nserves: {args.serves}\n"
        f"opened: {date.today().isoformat()}\n---\n\n{body}\n"
    )
    print(f"created {path}")
    return 0


def cmd_close(args: argparse.Namespace) -> int:
    root = project_root(Path(args.root) if args.root else Path.cwd())
    path = root / "backlog" / f"{args.id}.md"
    if not path.exists():
        print(f"error: no such card {path} — check the id with `backlog.py list`",
              file=sys.stderr)
        return 1
    card = parse_card(path)
    if isinstance(card, CardError):
        print(f"error: {path.name} is malformed ({card.message}) — fix it before closing, "
              "or delete it by hand if abandoning it", file=sys.stderr)
        return 1
    if args.disposition != "done" and not args.reason:
        print(f"error: Disposition: {args.disposition} requires --reason "
              "(docs/02-git-model.md trailer schema: 'Reason: required when Disposition "
              "!= done')", file=sys.stderr)
        return 1
    path.unlink()  # closure is deletion (CLAUDE.md "Done cards are deleted") — no commit here
    print(f"deleted {path}")
    print("commit this deletion with the trailers:")
    print(f"Card: {card.id}")
    print(f"Serves: {card.serves}")
    print(f"Disposition: {args.disposition}")
    if args.reason:
        print(f"Reason: {args.reason}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    root = project_root(Path(args.root) if args.root else Path.cwd())
    cards = load_cards(root / "backlog")
    if not cards:
        print("backlog empty")
        return 0
    exit_code = 0
    for c in cards:
        if isinstance(c, CardError):
            print(f"MALFORMED  {c.path.name}  {c.message}")
            exit_code = 1
        else:
            print(f"{c.id:<8} {c.status:<6} serves={c.serves:<6} {c.title}")
    return exit_code


def cmd_lint(args: argparse.Namespace) -> int:
    root = project_root(Path(args.root) if args.root else Path.cwd())
    manifest = checks.load_manifest(checks.find_manifest(root))
    caps = manifest.get("caps", {})
    rows = [r for r in (
        check_wip_cards(root, caps.get("wip_cards", 1)),
        check_todo_cards(root, caps.get("todo_cards", 10)),
        check_serves(root, deliverable_ids(manifest)),
    ) if r is not None]
    for row in rows:
        print(f"{row.status:<4}  {row.name}")
        for line in row.detail.splitlines():
            print(f"        {line}")
    return 1 if any(r.status == "FAIL" for r in rows) else 0


def _selftest() -> int:
    """Exercises the module against throwaway fixture projects, never this repo's own
    backlog/ (which is live work) — portable by construction, exercised from a tmpdir with
    no .git at all to prove it works outside a git repo, not just outside agent-os."""
    cases = 0
    failures = 0

    def check(name: str, cond: bool, detail: object = "") -> None:
        nonlocal cases, failures
        cases += 1
        if not cond:
            print(f"FAIL {name}: {detail}")
            failures += 1

    def fixture(tmp: Path) -> None:
        (tmp / "project.toml").write_text(
            '[caps]\nwip_cards = 1\ntodo_cards = 10\n\n'
            '[[deliverables]]\nid = "D-01"\ntitle = "x"\ndepends = []\nserves = "y"\n'
        )
        (tmp / "backlog").mkdir()

    def write_card(tmp: Path, name: str, id: str, status: str = "todo",
                    serves: str = "D-01") -> Path:
        p = tmp / "backlog" / name
        p.write_text(f"---\nid: {id}\ntitle: t\nstatus: {status}\nserves: {serves}\n"
                      "opened: 2026-08-02\n---\nbody\n")
        return p

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        fixture(tmp)
        write_card(tmp, "B-001.md", "B-001")
        card = parse_card(tmp / "backlog" / "B-001.md")
        check("parse_card reads a well-formed card", isinstance(card, Card), card)

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        fixture(tmp)
        (tmp / "backlog" / "B-002.md").write_text("not a card\n")
        card = parse_card(tmp / "backlog" / "B-002.md")
        check("parse_card flags missing frontmatter as CardError, not a crash",
              isinstance(card, CardError), card)

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        fixture(tmp)
        write_card(tmp, "B-001.md", "B-001", status="doing")
        write_card(tmp, "B-002.md", "B-002", status="doing")
        row = check_wip_cards(tmp, cap=1)
        check("wip_cards over cap fails", row is not None and row.status == "FAIL", row)

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        fixture(tmp)
        for i in range(1, 4):
            write_card(tmp, f"B-{i:03}.md", f"B-{i:03}")
        row = check_todo_cards(tmp, cap=2)
        check("todo_cards over cap fails", row is not None and row.status == "FAIL", row)

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        fixture(tmp)
        write_card(tmp, "B-099.md", "B-099", serves="D-99")
        row = check_serves(tmp, {"D-01"})
        check("serves lint fails naming the card for a nonexistent deliverable",
              row is not None and row.status == "FAIL" and "B-099" in row.detail
              and "D-99" in row.detail, row)

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        fixture(tmp)
        (tmp / "backlog" / "B-100.md").write_text("garbage\n")
        row = check_serves(tmp, {"D-01"})
        check("serves lint fails (not crashes) on a malformed card, naming it",
              row is not None and row.status == "FAIL" and "B-100" in row.detail, row)

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        fixture(tmp)
        write_card(tmp, "B-001.md", "B-001")
        write_card(tmp, "B-007.md", "B-007")
        check("next_id skips past existing ids", next_id(tmp) == "B-008", next_id(tmp))

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        fixture(tmp)
        rc = main(["new", "--title", "do the thing", "--serves", "D-01", "--root", str(tmp)])
        created = list((tmp / "backlog").glob("B-*.md"))
        check("new creates exactly one card with the schema fields",
              rc == 0 and len(created) == 1 and "serves: D-01" in created[0].read_text(),
              created)

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        fixture(tmp)
        rc = main(["new", "--title", "x", "--serves", "D-99", "--root", str(tmp)])
        check("new rejects a nonexistent deliverable and writes nothing",
              rc == 1 and not list((tmp / "backlog").glob("*.md")), rc)

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        fixture(tmp)
        write_card(tmp, "B-001.md", "B-001")
        rc = main(["close", "B-001", "--root", str(tmp)])
        check("close deletes the file", rc == 0 and not (tmp / "backlog" / "B-001.md").exists())

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        fixture(tmp)
        write_card(tmp, "B-001.md", "B-001")
        rc = main(["close", "B-001", "--disposition", "rejected", "--root", str(tmp)])
        check("close without --reason for a non-done disposition refuses and keeps the file",
              rc == 1 and (tmp / "backlog" / "B-001.md").exists())

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        fixture(tmp)
        (tmp / "backlog" / "B-001.md").write_text("garbage\n")
        rc = main(["close", "B-001", "--root", str(tmp)])
        check("close refuses a malformed card and does not delete it",
              rc == 1 and (tmp / "backlog" / "B-001.md").exists())

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        fixture(tmp)
        r = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                             "list", "--root", str(tmp)],
                            capture_output=True, text=True)
        check("CLI list end-to-end runs clean on an empty backlog (no git, not this repo)",
              r.returncode == 0 and "backlog empty" in r.stdout, r.stdout + r.stderr)

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        fixture(tmp)
        write_card(tmp, "B-099.md", "B-099", serves="D-99")
        r = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                             "lint", "--root", str(tmp)],
                            capture_output=True, text=True)
        check("CLI lint end-to-end exits 1 and names the offending card",
              r.returncode == 1 and "B-099" in r.stdout, r.stdout + r.stderr)

    print(f"{cases - failures}/{cases} cases pass")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--selftest", action="store_true")
    sub = p.add_subparsers(dest="cmd")

    n = sub.add_parser("new"); n.set_defaults(fn=cmd_new)
    n.add_argument("--title", required=True)
    n.add_argument("--serves", required=True)
    n.add_argument("--body", default=None)
    n.add_argument("--root", default=None)

    c = sub.add_parser("close"); c.set_defaults(fn=cmd_close)
    c.add_argument("id")
    c.add_argument("--disposition", choices=DISPOSITIONS, default="done")
    c.add_argument("--reason", default=None)
    c.add_argument("--root", default=None)

    li = sub.add_parser("list"); li.set_defaults(fn=cmd_list)
    li.add_argument("--root", default=None)

    lt = sub.add_parser("lint"); lt.set_defaults(fn=cmd_lint)
    lt.add_argument("--root", default=None)

    args = p.parse_args(argv)
    if args.selftest:
        return _selftest()
    if not getattr(args, "fn", None):
        p.print_help()
        return 2
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
