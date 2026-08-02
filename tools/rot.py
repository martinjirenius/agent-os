#!/usr/bin/env python3
"""rot.py — the single number that must fall: repo decay as one score plus a breakdown.

Scores the working tree at a given root against the signals in docs/03-practices.md and
docs/01-design.md's measured diagnosis. Nothing is stored (axiom 1): every run re-walks the
filesystem and re-parses `git log` via git_ledger, so the score cannot go stale — it can only
be wrong, which is why every signal states its weighting and two are reported unimplemented
rather than silently scored 0.

    tools/rot.py [--root PATH]     # print total + per-signal breakdown for PATH (default .)
    tools/rot.py --selftest

Comparing over time: the score is a pure function of the tree + git history at HEAD of --root,
so it is comparable across commits of the SAME project (run, commit, run again — the delta is
the signal) but not across projects of different size, since file/line-count signals grow with
the project. To score a past commit, check it out into a worktree and rerun — this tool does
not diff history itself (git_ledger already owns that, axiom 4).

Reuses git_ledger.py's git_out/load/match_trailer (chdir'd into --root), per "one authority
per topic".
"""
from __future__ import annotations

import argparse
import contextlib
import os
import re
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import git_ledger

NOISE_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "out",
              ".agent", "dist", "build", ".pytest_cache"}
SOURCE_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".rb",
                     ".java", ".sh", ".c", ".cpp", ".h"}

# Constitution text (CLAUDE.md) and the lint catalogue (docs/03-practices.md) name these
# verbatim. Deliberately restricted to SOURCE_EXTENSIONS files only (never .md): docs that
# *describe* the policy (CLAUDE.md, 01-design.md) quote these same substrings as prose, and
# scanning prose would make every project permanently "rotten" for documenting its own rule.
COMPAT_MARKERS = ["_v2", "legacy_", "if old_format:", "backwards compat",  # compat-marker-ok
                  "back-compat", "deprecated", "TODO(old)"]  # compat-marker-ok

DEFAULT_CAPS = {"file_lines": 500, "claude_md_lines": 150, "todo_cards": 10,
                "branch_sessions": 3}

# Self-matching guard: a detector that names the strings it hunts for necessarily contains
# them in its own source (this list, its own docstrings, its own test fixtures) — and would
# flag itself on every run if it didn't escape. The escape is per LINE via a grep-able
# sentinel, not per file: exempting whole files would let real compat code accumulate inside
# them unseen, and this convention is shared with tools/checks.py so one annotation satisfies
# both scanners. Auditable with `grep -rn compat-marker-ok`.
IGNORE_SENTINEL = "compat-marker-ok"


@dataclass
class Signal:
    """One rot signal: a count, its weight, why that weight, and what to fix."""
    name: str
    status: str  # "scored" | "informational" | "unimplemented" | "unavailable"
    weight: int
    weight_reason: str
    count: int
    weighted: int
    detail: list[str] = field(default_factory=list)


@dataclass
class RotReport:
    root: str
    total: int
    signals: list[Signal]

    def to_dict(self) -> dict:
        return {"root": self.root, "total": self.total,
                "signals": [vars(s) for s in self.signals]}


@contextlib.contextmanager
def _chdir(path: Path):
    old = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


def _load_caps(root: Path) -> dict:
    toml_path = root / "project.toml"
    if not toml_path.is_file():
        return dict(DEFAULT_CAPS)
    with toml_path.open("rb") as f:
        data = tomllib.load(f)
    caps = dict(DEFAULT_CAPS)
    caps.update(data.get("caps", {}))
    return caps


def _iter_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in NOISE_DIRS]
        for name in filenames:
            yield Path(dirpath) / name


def _relpath(root: Path, p: Path) -> str:
    try:
        return str(p.relative_to(root))
    except ValueError:
        return str(p)


def _lines(p: Path) -> list[str]:
    try:
        return p.read_text(errors="ignore").splitlines()
    except OSError:
        return []


# --- signal: compat markers ------------------------------------------------

def _signal_compat_markers(root: Path) -> Signal:
    hits: list[str] = []
    for p in _iter_files(root):
        if p.suffix not in SOURCE_EXTENSIONS:
            continue
        for i, line in enumerate(_lines(p), start=1):
            if IGNORE_SENTINEL in line:
                continue
            for marker in COMPAT_MARKERS:
                if marker in line:
                    hits.append(f"{_relpath(root, p)}:{i}: {marker!r}")
    reason = ("unambiguous constitution violation, near-zero false-positive rate — each hit "
              "is a real no-backwards-compatibility defect, not noise")
    return Signal("compat_markers", "scored", 5, reason, len(hits), len(hits) * 5, hits[:20])


# --- signal: docs outside the closed schema ---------------------------------

_DOC_SLOT_RE = re.compile(r"^(\d{2})-.+\.md$")
_PROJECT_SPECIFIC_SLOT_CAP = 4  # docs/05-schema.md: "02-...-0N ... ≤4 slots" — schema constant


def _signal_docs_schema(root: Path) -> Signal:
    docs_dir = root / "docs"
    if not docs_dir.is_dir():
        return Signal(name="docs_outside_schema", status="unavailable", weight=8,
                      weight_reason="no docs/ dir to check", count=0, weighted=0,
                      detail=["no docs/ directory"])
    bad: list[str] = []
    project_specific: list[str] = []
    for p in sorted(docs_dir.iterdir()):
        if p.name == "handoff.md":
            continue
        if not p.is_file():
            bad.append(f"{p.name} (not a plain file — the schema only defines files)")
            continue
        m = _DOC_SLOT_RE.match(p.name)
        if not m:
            bad.append(p.name)
            continue
        if m.group(1) not in ("00", "01"):
            project_specific.append(p.name)
    overflow = max(0, len(project_specific) - _PROJECT_SPECIFIC_SLOT_CAP)
    if overflow:
        bad.append(f"{len(project_specific)} project-specific doc slots "
                   f"(cap {_PROJECT_SPECIFIC_SLOT_CAP}): {sorted(project_specific)}")
    reason = ("01-design.md's own survey found superseded-plans-kept-as-documents the single "
              "biggest observed rot mechanism (stockpilot: 20 docs, contradictory plans) — "
              "highest per-item weight here on purpose")
    return Signal("docs_outside_schema", "scored", 8, reason, len(bad), len(bad) * 8, bad)


# --- signal: CLAUDE.md over its line cap ------------------------------------

def _signal_claude_md(root: Path, cap: int) -> Signal:
    f = root / "CLAUDE.md"
    if not f.is_file():
        return Signal(name="claude_md_over_cap", status="unavailable", weight=1,
                      weight_reason="no CLAUDE.md at root", count=0, weighted=0,
                      detail=["no CLAUDE.md found"])
    n = len(_lines(f))
    over = max(0, n - cap)
    reason = ("one point per line over cap — gradual on purpose, since the measured failure "
              "(01-design.md) was rules 7-10 added one session at a time and never removed; "
              "the score should move by the same increment as the disease")
    detail = [f"CLAUDE.md: {n} lines (cap {cap})"] if over else []
    return Signal("claude_md_over_cap", "scored", 1, reason, over, over, detail)


# --- signal: source files over the line cap ---------------------------------

def _signal_source_lines(root: Path, cap: int) -> Signal:
    detail: list[str] = []
    total_over = 0
    for p in _iter_files(root):
        if p.suffix not in SOURCE_EXTENSIONS:
            continue
        n = len(_lines(p))
        over = max(0, n - cap)
        if over:
            total_over += over
            detail.append(f"{_relpath(root, p)}: {n} lines (cap {cap})")
    reason = ("one point per line over cap, matching claude_md_over_cap's rationale: "
              "granular so the score reflects how far over, not just whether")
    return Signal("source_file_over_cap", "scored", 1, reason, total_over, total_over, detail)


# --- signal: branches open too long -----------------------------------------

def _sessions_between(root: Path, rev_range: str) -> set[str]:
    with _chdir(root):
        out = git_ledger.git_out("log", rev_range, "--pretty=%(trailers:key=Session,valueonly)")
    return {line.strip() for line in out.splitlines() if line.strip()}


def _signal_stale_branches(root: Path, cap_sessions: int) -> Signal:
    reason = ("CLAUDE.md names this explicitly as a rot signal, not a WIP item — an unmerged "
              "branch is invisible half-done work, weighted heaviest of the scored signals")
    try:
        with _chdir(root):
            current = git_ledger.git_out("rev-parse", "--abbrev-ref", "HEAD").strip()
            branches = [b.strip() for b in
                       git_ledger.git_out("for-each-ref", "--format=%(refname:short)",
                                           "refs/heads/").splitlines() if b.strip()]
    except SystemExit:
        return Signal("stale_branches", "unavailable", 10, reason, 0, 0,
                      ["not a git repository"])
    detail: list[str] = []
    stale = 0
    for b in branches:
        if b == current:
            continue
        with _chdir(root):
            base = git_ledger.git_out("merge-base", current, b).strip()
        sessions = _sessions_between(root, f"{base}..{current}")
        if len(sessions) > cap_sessions:
            stale += 1
            detail.append(f"{b}: {len(sessions)} sessions have landed on {current} since it "
                          f"diverged (cap {cap_sessions})")
    return Signal("stale_branches", "scored", 10, reason, stale, stale * 10, detail)


# --- signal: stale cards -----------------------------------------------------

def _card_fields(p: Path) -> dict[str, str]:
    lines = _lines(p)
    if not lines or lines[0].strip() != "---":
        return {}
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line:
            k, v = line.split(":", 1)
            fields[k.strip()] = v.strip()
    return fields


def _signal_stale_cards(root: Path, todo_cap: int, session_cap: int) -> Signal:
    backlog_dir = root / "backlog"
    reason = ("a card stuck in `doing` past the branch-session cap is the same failure as an "
              "unmerged branch — half-done work invisible to the frontier — so it shares that "
              "weight rather than getting its own arbitrary number")
    if not backlog_dir.is_dir():
        return Signal("stale_cards", "unavailable", 6, reason, 0, 0, ["no backlog/ directory"])
    cards = sorted(backlog_dir.glob("*.md"))
    fields_by_card = {c: _card_fields(c) for c in cards}
    todo = [c for c, f in fields_by_card.items() if f.get("status") == "todo"]
    doing = [c for c, f in fields_by_card.items() if f.get("status") == "doing"]
    overflow = max(0, len(todo) - todo_cap)
    detail: list[str] = []
    stale = 0
    git_unavailable = False
    for c in doing:
        opened = fields_by_card[c].get("opened", "")
        if not opened:
            continue
        try:
            with _chdir(root):
                commits = git_ledger.load(since=opened)
        except SystemExit:
            git_unavailable = True
            continue
        sessions = {s for cm in commits for s in cm.trailers.get("Session", [])}
        if len(sessions) > session_cap:
            stale += 1
            detail.append(f"{c.name}: doing since {opened}, {len(sessions)} sessions have "
                          f"landed since (cap {session_cap})")
    if overflow:
        detail.append(f"{len(todo)} todo cards (cap {todo_cap})")
    if git_unavailable and not doing:
        return Signal("stale_cards", "unavailable", 6, reason, 0, 0, ["not a git repository"])
    count = stale + overflow
    return Signal("stale_cards", "scored", 6, reason, count, count * 6, detail)


# --- signal: net-lines trend (informational, not gated) ---------------------

def _signal_net_lines(root: Path) -> Signal:
    reason = ("docs/03-practices.md lists net-lines as 'reported, not gated' — size alone is "
              "not decay (a growing product legitimately grows), so it carries zero weight "
              "and exists only to show growth behind the scored signals")
    try:
        with _chdir(root):
            out = git_ledger.git_out("log", "--shortstat", "--pretty=%H")
    except SystemExit:
        return Signal("net_lines_trend", "unavailable", 0, reason, 0, 0,
                      ["not a git repository"])
    ins = dele = 0
    for line in out.splitlines():
        m = re.search(r"(\d+) insertion", line)
        if m:
            ins += int(m.group(1))
        m = re.search(r"(\d+) deletion", line)
        if m:
            dele += int(m.group(1))
    net = ins - dele
    return Signal("net_lines_trend", "informational", 0, reason, net, 0,
                 [f"+{ins} -{dele} = net {net:+d} lines across all history"])


# --- signals not implemented: explicit, not silently zero -------------------

def _signal_unimplemented(name: str, reason: str) -> Signal:
    return Signal(name, "unimplemented", 0, reason, 0, 0, [reason])


def compute_rot(root: str | os.PathLike[str] = ".") -> RotReport:
    """The rot score for the project at `root`: a total plus every signal that fed it.

    This is the function checks.py should import and call: `rot.compute_rot(project_root)`.
    """
    root = Path(root).resolve()
    caps = _load_caps(root)
    signals = [
        _signal_compat_markers(root),
        _signal_docs_schema(root),
        _signal_claude_md(root, caps["claude_md_lines"]),
        _signal_source_lines(root, caps["file_lines"]),
        _signal_stale_branches(root, caps["branch_sessions"]),
        _signal_stale_cards(root, caps["todo_cards"], caps["branch_sessions"]),
        _signal_net_lines(root),
        _signal_unimplemented(
            "skills_never_fired",
            "needs D-03: /dev and /wrap must emit a skill-invocation record before this can "
            "be computed — no data source exists yet, so it is reported unimplemented rather "
            "than scored 0 (a silent 0 would look identical to 'no stale skills')."),
        _signal_unimplemented(
            "dead_code_unreachable_from_demo",
            "needs D-07: project.toml's `demo` command is currently a stub, so there is no "
            "working demo path to compute reachability from — reported unimplemented rather "
            "than scored 0 for the same reason."),
    ]
    total = sum(s.weighted for s in signals if s.status == "scored")
    return RotReport(root=str(root), total=total, signals=signals)


def _print_report(report: RotReport) -> None:
    print(f"rot: {report.total}   ({report.root})")
    print(f"{'signal':<32} {'status':<14} {'count':>6} {'weight':>7} {'weighted':>9}")
    for s in report.signals:
        print(f"{s.name:<32} {s.status:<14} {s.count:>6} {s.weight:>7} {s.weighted:>9}")
        for line in s.detail[:5]:
            print(f"    {line}")
        if len(s.detail) > 5:
            print(f"    ... and {len(s.detail) - 5} more")


def _run_git(cwd: Path, *args: str, date: str | None = None) -> None:
    env = {**os.environ, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date} if date else None
    subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=True)


def _init_repo(tmp: Path) -> None:
    _run_git(tmp, "init", "-q")
    _run_git(tmp, "config", "user.email", "test@example.com")
    _run_git(tmp, "config", "user.name", "Test")
    (tmp / "project.toml").write_text(
        "[caps]\nfile_lines = 500\nclaude_md_lines = 150\ntodo_cards = 10\n"
        "branch_sessions = 3\n")


def _build_clean_fixture(tmp: Path) -> None:
    """A small, fully healthy project — every scored signal should be 0 on this."""
    _init_repo(tmp)
    (tmp / "CLAUDE.md").write_text("# clean\n" * 5)
    (tmp / "docs").mkdir()
    (tmp / "docs" / "00-product.md").write_text("ok\n")
    (tmp / "backlog").mkdir()
    (tmp / "tools").mkdir()
    (tmp / "tools" / "main.py").write_text("print('hi')\n")
    _run_git(tmp, "add", "-A")
    _run_git(tmp, "commit", "-qm", "init\n\nSession: s1", date="2026-08-01T10:00:00")


def _build_dirty_fixture(tmp: Path) -> None:
    """The same fixture, deliberately rotted: a compat marker, a stray doc, both scored."""
    _init_repo(tmp)
    (tmp / "CLAUDE.md").write_text("# x\n" * 5)
    (tmp / "docs").mkdir()
    (tmp / "docs" / "00-product.md").write_text("ok\n")
    (tmp / "docs" / "stray-notes.md").write_text("a superseded plan kept around\n")
    (tmp / "backlog").mkdir()
    (tmp / "tools").mkdir()
    (tmp / "tools" / "old.py").write_text(
        "def foo_v2():\n    return 1  # legacy_ path\n")  # compat-marker-ok
    _run_git(tmp, "add", "-A")
    _run_git(tmp, "commit", "-qm", "init\n\nSession: s1", date="2026-08-01T10:00:00")


def _selftest() -> int:
    """Builds a clean and a deliberately-dirty throwaway repo and checks the score moves the
    right way, plus the self-matching guard. Portable by construction (tempfile), exercised
    from any cwd — it never reads or writes this repo."""
    cases = 0
    failures = 0

    def check(name: str, cond: bool, detail: object = "") -> None:
        nonlocal cases, failures
        cases += 1
        if not cond:
            print(f"FAIL {name}: {detail}")
            failures += 1

    with tempfile.TemporaryDirectory() as clean_dir, tempfile.TemporaryDirectory() as dirty_dir:
        clean_root = Path(clean_dir)
        _build_clean_fixture(clean_root)
        clean_report = compute_rot(clean_root)
        check("clean fixture scores zero", clean_report.total == 0, clean_report.to_dict())

        dirty_root = Path(dirty_dir)
        _build_dirty_fixture(dirty_root)
        dirty_report = compute_rot(dirty_root)
        check("dirty fixture scores above zero", dirty_report.total > 0, dirty_report.total)
        check("dirty fixture scores above clean fixture",
              dirty_report.total > clean_report.total,
              (dirty_report.total, clean_report.total))

        by_name = {s.name: s for s in dirty_report.signals}
        check("compat_markers found the injected marker",
              by_name["compat_markers"].count >= 1, by_name["compat_markers"].detail)
        check("docs_outside_schema found the stray doc",
              by_name["docs_outside_schema"].count == 1, by_name["docs_outside_schema"].detail)

        # self-matching guard: copy rot.py + rot_test.py (which legitimately contain the
        # marker literals as data) into the dirty fixture's tools/ dir and confirm they are
        # excluded while a third, unrelated file with the same literal is still caught.
        this_file = Path(__file__).resolve()
        test_file = this_file.parent / "rot_test.py"
        (dirty_root / "tools" / this_file.name).write_text(this_file.read_text())
        if test_file.is_file():
            (dirty_root / "tools" / test_file.name).write_text(test_file.read_text())
        before = by_name["compat_markers"].count
        after_self_copy = compute_rot(dirty_root)
        after_sig = {s.name: s for s in after_self_copy.signals}["compat_markers"]
        check("copying rot.py/rot_test.py into the scanned tree does not self-flag",
              after_sig.count == before, (after_sig.count, before, after_sig.detail))

        by_name2 = {s.name: s for s in dirty_report.signals}
        check("net_lines_trend is informational and unweighted",
              by_name2["net_lines_trend"].status == "informational"
              and by_name2["net_lines_trend"].weighted == 0)
        check("skills_never_fired is unimplemented, not scored 0",
              by_name2["skills_never_fired"].status == "unimplemented")
        check("dead_code_unreachable_from_demo is unimplemented, not scored 0",
              by_name2["dead_code_unreachable_from_demo"].status == "unimplemented")

    print(f"{cases - failures}/{cases} cases pass")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--root", default=".")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args(argv)
    if args.selftest:
        return _selftest()
    report = compute_rot(args.root)
    _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
