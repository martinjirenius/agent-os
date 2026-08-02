#!/usr/bin/env python3
"""One command, one PASS/FAIL/STUB table, exit 1 on any failure — the gate /wrap runs.

Manifest-driven, not hardcoded: the check list comes from `[commands]` in project.toml
(docs/05-schema.md, "Specialization: manifest, not forking") — this is the whole point,
since the same script installs into every project (D-07). An empty command string is a
declared stub (`lint`/`demo` in agent-os's own project.toml today) and renders as a
visible STUB row: not PASS (that would be a lie in the one table Martin trusts) and not
a crash (a stub is not a failure).

Beyond the manifest commands, a fixed set of structural checks straight out of the
constitution (CLAUDE.md) and the closed doc schema (docs/05-schema.md) turn prose caps
into exit codes: file_lines, claude_md_lines, todo_cards, wip_cards, local_skills, the
closed docs/ schema, and a compat-marker grep. Caps are read from `[caps]` in
project.toml — never hardcoded — so raising a cap is a manifest edit, not a code change.

Card-level lints that need to cross-reference project.toml's `[[deliverables]]` (every
card `Serves:` a real deliverable) are deliberately NOT here — that needs a card parser,
which is B-005's territory (backlog.py). This module only counts `status:` frontmatter,
which is trivial and needed for the todo/wip caps.

    tools/checks.py                # run every check for the project rooted here-or-above
    tools/checks.py --selftest
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path

MANIFEST_NAME = "project.toml"

# Compat markers from the constitution (CLAUDE.md "No backwards compatibility") and the  # compat-marker-ok
# lint catalogue (docs/03-practices.md "Rot"). Matched case-insensitively as substrings.
COMPAT_MARKERS = ["_v2", "legacy_", "deprecated", "back-compat", "TODO(old)", "backwards compat"]  # compat-marker-ok

# A detector that names the strings it hunts for will flag itself. The escape is per LINE,
# not per file: exempting whole files (this one, its tests) would let real compat code
# accumulate inside them unseen, and would exempt any project file that happened to share
# the name. One grep-able sentinel, auditable with `grep -rn compat-marker-ok`.
IGNORE_SENTINEL = "compat-marker-ok"

CODE_SUFFIXES = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".rb",
    ".java", ".c", ".cc", ".cpp", ".h", ".hpp", ".sh",
}
SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".pytest_cache", ".mypy_cache",
    "out", "dist", "build", "venv", ".venv",
}

REQUIRED_CAPS = ["file_lines", "claude_md_lines", "todo_cards", "wip_cards", "local_skills"]

# docs/05-schema.md: 00 and 01 are fixed OS-level slot names; 02-09 are project-specific
# canon, capped at MAX_EXTRA_DOC_SLOTS. Adding a slot is an OS-level change, not a project
# edit, so the cap is a constant here rather than a manifest knob.
DOC_SLOT_RE = re.compile(r"^(00-product|01-design|0[2-9]-[a-z0-9-]+)\.md$")
MAX_EXTRA_DOC_SLOTS = 4


@dataclass
class Row:
    name: str
    status: str  # "PASS" | "FAIL" | "STUB" | "INFO"
    detail: str = ""


def find_manifest(start: Path) -> Path:
    """Walk upward from <start> for project.toml — the same convention as looking for a
    .git directory, since checks.py is typically run from somewhere inside a project."""
    d = start.resolve()
    for candidate in (d, *d.parents):
        p = candidate / MANIFEST_NAME
        if p.exists():
            return p
    raise SystemExit(
        f"no {MANIFEST_NAME} found in {start} or any parent directory — checks.py is "
        f"manifest-driven (docs/05-schema.md); create one, e.g. by copying "
        f"schema/project.toml.example into the project root."
    )


def load_manifest(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as e:
        raise SystemExit(f"{path} is not valid TOML ({e}) — fix the syntax.")


def iter_files(root: Path, suffixes: set[str] | None = None):
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if suffixes is not None and p.suffix not in suffixes:
            continue
        yield p


def check_command(name: str, cmd: str, root: Path) -> Row:
    if cmd.strip() == "":
        return Row(name, "STUB",
                    "declared empty in project.toml — a documented stub, not a failure; "
                    "fill it in before treating this project as fully wired up")
    r = subprocess.run(cmd, shell=True, cwd=root, capture_output=True, text=True)
    if r.returncode == 0:
        return Row(name, "PASS")
    tail = (r.stdout + r.stderr).strip().splitlines()[-8:]
    return Row(name, "FAIL", f"`{cmd}` exited {r.returncode}\n" + "\n".join(tail))


def check_file_lines(root: Path, cap: int) -> Row:
    name = f"file_lines <= {cap}"
    offenders = []
    for p in iter_files(root, CODE_SUFFIXES):
        n = sum(1 for _ in p.open(errors="ignore"))
        if n > cap:
            offenders.append(f"{p.relative_to(root)} ({n} lines)")
    if offenders:
        return Row(name, "FAIL",
                    f"over the {cap}-line cap (CLAUDE.md 'Code conventions') — split the "
                    "file, exact-match edits get unreliable past this size:\n  " +
                    "\n  ".join(sorted(offenders)))
    return Row(name, "PASS")


def check_claude_md_lines(root: Path, cap: int) -> Row | None:
    p = root / "CLAUDE.md"
    if not p.exists():
        return None
    name = f"claude_md_lines <= {cap}"
    n = sum(1 for _ in p.open(errors="ignore"))
    if n > cap:
        return Row(name, "FAIL",
                    f"CLAUDE.md is {n} lines, cap is {cap} — push detail down to a doc "
                    "or skill (docs/03-practices.md 'Where a rule belongs')")
    return Row(name, "PASS")


def _card_status(p: Path) -> str | None:
    """The `status:` frontmatter value of a backlog card, or None if unparseable."""
    parts = p.read_text(errors="ignore").split("---")
    if len(parts) < 3:
        return None
    m = re.search(r"^status:\s*(\S+)", parts[1], re.MULTILINE)
    return m.group(1) if m else None


def check_todo_cards(root: Path, cap: int) -> Row | None:
    backlog = root / "backlog"
    if not backlog.exists():
        return None
    name = f"todo_cards <= {cap}"
    todo = [p for p in backlog.glob("*.md") if _card_status(p) == "todo"]
    if len(todo) > cap:
        return Row(name, "FAIL",
                    f"{len(todo)} todo cards, cap is {cap} — close or delete cards before "
                    "opening more (WAY-OF-WORKING.md 'There is no icebox')")
    return Row(name, "PASS")


def check_wip_cards(root: Path, cap: int) -> Row | None:
    backlog = root / "backlog"
    if not backlog.exists():
        return None
    name = f"wip_cards <= {cap}"
    wip = [p for p in backlog.glob("*.md") if _card_status(p) == "doing"]
    if len(wip) > cap:
        names = ", ".join(p.stem for p in wip)
        return Row(name, "FAIL",
                    f"{len(wip)} cards marked doing ({names}), WIP cap is {cap} — finish "
                    "or park one before starting another")
    return Row(name, "PASS")


def check_local_skills(root: Path, cap: int) -> Row | None:
    """Count PROJECT-LOCAL skills only — `.claude/skills/`, not the plugin payload.

    docs/05-schema.md: core and standard skills come from the plugin, "referenced, never
    copied", and a project may add 3 of its own. agent-os's own `skills/` directory is that
    plugin payload (it is authoring the OS), so counting it here would cap the OS itself at
    3 core skills while its published roster lists twelve.
    """
    skills = root / ".claude" / "skills"
    if not skills.exists():
        return None
    name = f"local_skills <= {cap}"
    found = [d for d in skills.iterdir() if d.is_dir() and (d / "SKILL.md").exists()]
    if len(found) > cap:
        return Row(name, "FAIL",
                    f"{len(found)} local skills, budget is {cap} (docs/05-schema.md) — "
                    "retire one with /prune or promote it into the OS")
    return Row(name, "PASS")


def check_doc_schema(root: Path) -> Row | None:
    docs = root / "docs"
    if not docs.exists():
        return None
    bad = []
    extra = []
    for p in docs.iterdir():
        if not p.is_file() or p.name == "handoff.md":
            continue
        if DOC_SLOT_RE.match(p.name):
            if not p.name.startswith(("00-", "01-")):
                extra.append(p.name)
            continue
        bad.append(p.name)
    if bad:
        return Row("doc schema", "FAIL",
                    "not a defined slot (docs/05-schema.md closed doc schema): " +
                    ", ".join(sorted(bad)) +
                    " — move the content into an existing slot, a card, a finding in the "
                    "ledger, or delete the file")
    if len(extra) > MAX_EXTRA_DOC_SLOTS:
        return Row("doc schema", "FAIL",
                    f"{len(extra)} project-specific doc slots, cap is {MAX_EXTRA_DOC_SLOTS} "
                    "(docs/05-schema.md): " + ", ".join(sorted(extra)))
    return Row("doc schema", "PASS")


def check_compat_markers(root: Path) -> Row:
    hits = []
    for p in iter_files(root, CODE_SUFFIXES):
        for lineno, line in enumerate(p.read_text(errors="ignore").splitlines(), 1):
            if IGNORE_SENTINEL in line:
                continue
            lowered = line.lower()
            for marker in COMPAT_MARKERS:
                if marker.lower() in lowered:
                    hits.append(f"{p.relative_to(root)}:{lineno}: {marker!r}")
    if hits:
        return Row("compat markers", "FAIL",
                    "no backwards compatibility (CLAUDE.md constitution) — delete the old "  # compat-marker-ok
                    "path in the same commit that lands the new one:\n  " +
                    "\n  ".join(sorted(hits)))
    return Row("compat markers", "PASS")


def check_rot(root: Path) -> Row | None:
    """The rot score as an INFO row — reported, never gated (docs/03-practices.md).

    Acceptance for the system is that this number FALLS over a month, which is a trend, not a
    threshold. Any absolute cutoff would be either trivially passed or permanently red, and a
    permanently red row is one nobody reads. Unimplemented signals are surfaced by name so a
    low score is never mistaken for a clean bill of health.
    """
    try:
        import rot
    except ImportError:
        return None  # rot.py is optional; a project may install checks.py without it
    report = rot.compute_rot(root)
    scored = [s for s in report.signals if s.status == "scored" and s.weighted]
    unimplemented = [s.name for s in report.signals if s.status == "unimplemented"]
    detail = f"rot: {report.total} — `tools/rot.py` for the breakdown"
    if scored:
        detail += "\n  " + "\n  ".join(f"{s.name}: {s.weighted}" for s in scored)
    if unimplemented:
        detail += f"\n  not yet measured (NOT scored 0): {', '.join(unimplemented)}"
    return Row("rot score", "INFO", detail)


def build_rows(root: Path, manifest: dict) -> list[Row]:
    """The full, deterministically ordered check list: manifest commands first (in the
    order they appear in project.toml), then the fixed structural checks."""
    rows: list[Row] = []
    for name, cmd in manifest.get("commands", {}).items():
        rows.append(check_command(name, cmd, root))

    caps = manifest.get("caps", {})
    missing = [k for k in REQUIRED_CAPS if k not in caps]
    if missing:
        raise SystemExit(
            f"project.toml is missing caps: {', '.join(missing)} — add them under [caps] "
            f"(see schema/project.toml.example); checks.py never hardcodes limits."
        )

    rows.append(check_file_lines(root, caps["file_lines"]))
    for row in (
        check_claude_md_lines(root, caps["claude_md_lines"]),
        check_todo_cards(root, caps["todo_cards"]),
        check_wip_cards(root, caps["wip_cards"]),
        check_local_skills(root, caps["local_skills"]),
        check_doc_schema(root),
    ):
        if row is not None:
            rows.append(row)
    rows.append(check_compat_markers(root))
    rot_row = check_rot(root)
    if rot_row is not None:
        rows.append(rot_row)
    return rows


def render(rows: list[Row]) -> int:
    for row in rows:
        print(f"{row.status:<4}  {row.name}")
        for line in row.detail.splitlines():
            print(f"        {line}")
    failed = [r for r in rows if r.status == "FAIL"]
    ungated = [r for r in rows if r.status in ("STUB", "INFO")]
    print()
    if failed:
        print(f"{len(failed)} check(s) failed: {', '.join(r.name for r in failed)}")
        return 1
    note = f" ({len(ungated)} not gated: {', '.join(r.name for r in ungated)})" if ungated else ""
    print(f"all {len(rows) - len(ungated)} checks pass{note}")
    return 0


def _make_selftest_fixture(tmp: Path) -> None:
    (tmp / "project.toml").write_text(
        '[commands]\n'
        'test = "true"\n'
        'lint = ""\n'
        '\n'
        '[caps]\n'
        'file_lines = 500\n'
        'claude_md_lines = 150\n'
        'todo_cards = 10\n'
        'wip_cards = 1\n'
        'local_skills = 3\n'
    )
    (tmp / "CLAUDE.md").write_text("# x\n" * 5)
    (tmp / "docs").mkdir()
    (tmp / "docs" / "00-product.md").write_text("ok\n")
    (tmp / "backlog").mkdir()
    (tmp / "backlog" / "B-001.md").write_text("---\nid: B-001\nstatus: todo\n---\nbody\n")
    (tmp / ".claude" / "skills").mkdir(parents=True)
    (tmp / "tools").mkdir()
    (tmp / "tools" / "main.py").write_text("print('hi')\n")


def _selftest() -> int:
    """Exercises build_rows against throwaway fixture projects, never this repo — these
    tools ship into other projects (D-07), so a selftest anchored to agent-os's own paths
    would prove nothing about portability. Ends with a real CLI invocation whose cwd is a
    tmpdir with no .git at all, to prove the tool works outside a git repo, not just
    outside agent-os."""
    cases = 0
    failures = 0

    def check(name: str, cond: bool, detail: object = "") -> None:
        nonlocal cases, failures
        cases += 1
        if not cond:
            print(f"FAIL {name}: {detail}")
            failures += 1

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _make_selftest_fixture(tmp)
        rows = {r.name: r for r in build_rows(tmp, load_manifest(tmp / "project.toml"))}
        check("clean fixture: command passes", rows["test"].status == "PASS")
        check("clean fixture: empty command is STUB not PASS", rows["lint"].status == "STUB")
        check("clean fixture: no FAIL rows", all(r.status != "FAIL" for r in rows.values()),
              rows)

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _make_selftest_fixture(tmp)
        m = load_manifest(tmp / "project.toml")
        m["commands"]["test"] = "false"
        rows = {r.name: r for r in build_rows(tmp, m)}
        check("failing command is FAIL", rows["test"].status == "FAIL")

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _make_selftest_fixture(tmp)
        (tmp / "tools" / "big.py").write_text("x = 1\n" * 600)
        rows = {r.name: r for r in build_rows(tmp, load_manifest(tmp / "project.toml"))}
        row = rows["file_lines <= 500"]
        check("over-long file fails and names the file",
              row.status == "FAIL" and "big.py" in row.detail, row)

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _make_selftest_fixture(tmp)
        (tmp / "CLAUDE.md").write_text("# x\n" * 200)
        rows = {r.name: r for r in build_rows(tmp, load_manifest(tmp / "project.toml"))}
        check("CLAUDE.md over cap fails", rows["claude_md_lines <= 150"].status == "FAIL")

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _make_selftest_fixture(tmp)
        for i in range(2, 13):
            (tmp / "backlog" / f"B-{i:03}.md").write_text(
                f"---\nid: B-{i:03}\nstatus: todo\n---\nbody\n")
        rows = {r.name: r for r in build_rows(tmp, load_manifest(tmp / "project.toml"))}
        check("todo cards over cap fails", rows["todo_cards <= 10"].status == "FAIL")

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _make_selftest_fixture(tmp)
        (tmp / "backlog" / "B-002.md").write_text("---\nid: B-002\nstatus: doing\n---\nbody\n")
        (tmp / "backlog" / "B-003.md").write_text("---\nid: B-003\nstatus: doing\n---\nbody\n")
        rows = {r.name: r for r in build_rows(tmp, load_manifest(tmp / "project.toml"))}
        check("wip cards over cap fails", rows["wip_cards <= 1"].status == "FAIL")

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _make_selftest_fixture(tmp)
        for name in ("a", "b", "c", "d"):
            sd = tmp / ".claude" / "skills" / name
            sd.mkdir()
            (sd / "SKILL.md").write_text("x\n")
        rows = {r.name: r for r in build_rows(tmp, load_manifest(tmp / "project.toml"))}
        check("local skills over cap fails", rows["local_skills <= 3"].status == "FAIL")

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _make_selftest_fixture(tmp)
        (tmp / "docs" / "notes.md").write_text("stray\n")
        rows = {r.name: r for r in build_rows(tmp, load_manifest(tmp / "project.toml"))}
        check("undefined doc file fails schema", rows["doc schema"].status == "FAIL")

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _make_selftest_fixture(tmp)
        (tmp / "tools" / "old.py").write_text("def foo_v2(): pass\n")  # compat-marker-ok
        rows = {r.name: r for r in build_rows(tmp, load_manifest(tmp / "project.toml"))}
        check("compat marker fails", rows["compat markers"].status == "FAIL")

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _make_selftest_fixture(tmp)
        m = load_manifest(tmp / "project.toml")
        del m["caps"]["file_lines"]
        try:
            build_rows(tmp, m)
            check("missing cap raises", False)
        except SystemExit as e:
            check("missing cap raises", "missing caps" in str(e), e)

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _make_selftest_fixture(tmp)
        sub = tmp / "a" / "b"
        sub.mkdir(parents=True)
        check("find_manifest walks up to a parent project.toml",
              find_manifest(sub) == tmp / "project.toml")

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        try:
            find_manifest(tmp)
            check("find_manifest with nothing anywhere raises", False)
        except SystemExit as e:
            check("find_manifest with nothing anywhere raises", "project.toml" in str(e), e)

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _make_selftest_fixture(tmp)
        r = subprocess.run([sys.executable, str(Path(__file__).resolve())],
                            cwd=tmp, capture_output=True, text=True)
        check("CLI end-to-end exits 0 on a clean fixture (no git, not this repo)",
              r.returncode == 0, r.stdout + r.stderr)

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _make_selftest_fixture(tmp)
        (tmp / "tools" / "big.py").write_text("x = 1\n" * 600)
        r = subprocess.run([sys.executable, str(Path(__file__).resolve())],
                            cwd=tmp, capture_output=True, text=True)
        check("CLI end-to-end exits 1 on an injected violation",
              r.returncode == 1, r.stdout + r.stderr)

    print(f"{cases - failures}/{cases} cases pass")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args(argv)
    if args.selftest:
        return _selftest()
    root = find_manifest(Path.cwd()).parent
    manifest = load_manifest(root / MANIFEST_NAME)
    return render(build_rows(root, manifest))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
