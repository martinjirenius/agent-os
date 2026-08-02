#!/usr/bin/env python3
"""roadmap.py — the deliverable DAG on a time axis: measured past, honest (or refused) future.

Surface 2 of docs/04-surfaces.md. Nothing is stored (axiom 1): every run re-parses git
trailers via git_ledger.py and re-reads backlog/*.md via backlog.py — no index to go stale.

**Landed** = a deliverable has a commit whose `Serves:` names it AND no card currently open in
backlog/ still serves it (a Disposition:done commit does not land a deliverable if another
open card still serves it — closure is card-level, the deliverable inherits it only when
nothing is left open). **Frontier** = not landed, every `depends` IS landed. **Blocked** = not
landed, at least one dependency is not.

**Projection is in SESSIONS-OUT, never calendar dates.** No project here has an established
session cadence — daily, or three in one afternoon — so turning a sessions-out estimate into a
date would fabricate a cadence nobody measured: the exact confident-looking lie this surface
exists to prevent (WAY-OF-WORKING.md "slip is the headline"). `MIN_SESSIONS_FOR_PROJECTION`
gates any number at all: below it, the tool states how little data it has instead of guessing.

**Ghost bars** re-run the identical projection as of each earlier session (`ghost_history`)
and diff consecutive non-insufficient estimates (`detect_slip`) — slip is discovered by
recomputation, never by diffing a stored value, so it stays true to axiom 1.

    tools/roadmap.py                # the pipeline: every deliverable, landed/current/blocked
    tools/roadmap.py --board        # zoom in: the unblocked frontier only
    tools/roadmap.py --root PATH    # run against a project other than the cwd's
    tools/roadmap.py --selftest
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import backlog  # Card/CardError/load_cards/project_root/_chdir — one authority per topic
import checks  # find_manifest/load_manifest
import git_ledger  # Commit/load — the retrieval half; never re-walk git log here
import stack  # load_stack/open_frames — the one schema for .agent/stack.json

MIN_SESSIONS_FOR_PROJECTION = 3
# Two data points define a slope with zero information about whether it holds; three is the
# minimum that can show a slope is even roughly consistent. Below this, printing a date is a
# lie dressed as arithmetic (the card's explicit failure mode) — refuse instead.


@dataclass
class Deliverable:
    id: str
    title: str
    depends: list[str]


@dataclass
class Status:
    id: str
    title: str
    depends: list[str]
    state: str  # "landed" | "in_progress" | "frontier" | "blocked"
    first_date: str | None
    last_date: str | None
    sessions: list[str]
    open_cards: list[str]


@dataclass
class Projection:
    insufficient: bool
    sessions_observed: int
    remaining: int
    estimate: float | None = None
    low: float | None = None
    high: float | None = None


def load_deliverables(manifest: dict) -> list[Deliverable]:
    """`[[deliverables]]` from project.toml, in the order the manifest declares them —
    the DAG this whole module renders."""
    return [Deliverable(d["id"], d.get("title", d["id"]), list(d.get("depends", [])))
            for d in manifest.get("deliverables", [])]


def level(d_id: str, by_id: dict[str, Deliverable], _seen: frozenset[str] = frozenset()) -> int:
    """Topological depth: 0 for no dependencies, else 1 + the deepest dependency. Used to
    estimate how many landings stand between "now" and a not-yet-landed deliverable, without
    assuming project.toml happens to list deliverables in dependency order."""
    if d_id in _seen:
        raise SystemExit(
            f"dependency cycle involving {d_id} in project.toml [[deliverables]] — break the "
            f"cycle before a roadmap can be drawn; a DAG with a cycle has no topological depth."
        )
    d = by_id.get(d_id)
    if d is None or not d.depends:
        return 0
    return 1 + max(level(dep, by_id, _seen | {d_id}) for dep in d.depends)


def exact_serves(c: git_ledger.Commit, d_id: str) -> bool:
    """Exact `Serves:` match. git_ledger.match_trailer does substring matching, which would
    let 'D-1' match a commit serving 'D-10' — deliberately NOT reused here for that reason."""
    return d_id in c.trailers.get("Serves", [])


def distinct_sessions(commits: list[git_ledger.Commit]) -> list[str]:
    """Every session id seen, oldest first. Session ids are `YYYY-MM-DD-<letter>`, so plain
    string sort is chronological (same trick tools/inbox.py's is_new relies on). Commits
    without a Session trailer are excluded from the ORDER but never hidden elsewhere — a
    missing trailer here just means that one commit can't anchor a session boundary."""
    seen = {s for c in commits for s in c.trailers.get("Session", [])}
    return sorted(seen)


def card_warnings(backlog_dir: Path) -> list[str]:
    """Malformed cards, named — never silently dropped from the picture (axiom: a row must
    never vanish on bad input)."""
    if not backlog_dir.exists():
        return []
    return [f"{c.path.name}: {c.message}" for c in backlog.load_cards(backlog_dir)
            if isinstance(c, backlog.CardError)]


def _open_card_ids(backlog_dir: Path) -> dict[str, list[str]]:
    """deliverable id -> list of open card ids currently serving it. Malformed cards are
    reported via card_warnings, not counted here (their `serves` cannot be trusted)."""
    result: dict[str, list[str]] = {}
    if not backlog_dir.exists():
        return result
    for c in backlog.load_cards(backlog_dir):
        if isinstance(c, backlog.Card):
            result.setdefault(c.serves, []).append(c.id)
    return result


def compute_statuses(commits: list[git_ledger.Commit], deliverables: list[Deliverable],
                      backlog_dir: Path) -> list[Status]:
    """One Status per declared deliverable — every id in project.toml appears exactly once,
    landed or not, with data or without. Order matches project.toml (a stable reading order),
    never dropped for lack of commits or cards."""
    open_by_deliverable = _open_card_ids(backlog_dir)
    landed: set[str] = set()
    rows: dict[str, Status] = {}
    for d in deliverables:
        touching = [c for c in commits if exact_serves(c, d.id)]
        sessions = sorted({s for c in touching for s in c.trailers.get("Session", [])})
        open_cards = open_by_deliverable.get(d.id, [])
        has_commits = bool(touching)
        is_landed = has_commits and not open_cards
        if is_landed:
            landed.add(d.id)
        rows[d.id] = Status(
            id=d.id, title=d.title, depends=d.depends,
            state="landed" if is_landed else ("in_progress" if has_commits else "pending"),
            first_date=min((c.date for c in touching), default=None),
            last_date=max((c.date for c in touching), default=None),
            sessions=sessions, open_cards=open_cards,
        )
    # second pass: a "pending" deliverable is frontier if every dependency landed, else blocked
    for d in deliverables:
        row = rows[d.id]
        if row.state == "pending":
            row.state = "frontier" if all(dep in landed for dep in d.depends) else "blocked"
    return list(rows.values())


def project_sessions_out(target: str, commits: list[git_ledger.Commit],
                          deliverables: list[Deliverable], backlog_dir: Path) -> Projection:
    """How many sessions out `target` lands, or a refusal if there isn't enough velocity data.
    Velocity = deliverables landed / sessions observed; remaining = topological levels between
    the furthest-landed deliverable and `target`. The band widens with `remaining`."""
    sessions = distinct_sessions(commits)
    statuses = compute_statuses(commits, deliverables, backlog_dir)
    by_id = {d.id: d for d in deliverables}
    landed_ids = [s.id for s in statuses if s.state == "landed"]

    if target in landed_ids:
        return Projection(insufficient=False, sessions_observed=len(sessions), remaining=0,
                           estimate=0.0, low=0.0, high=0.0)

    max_landed_level = max((level(i, by_id) for i in landed_ids), default=-1)
    remaining = max(1, level(target, by_id) - max_landed_level)

    if len(sessions) < MIN_SESSIONS_FOR_PROJECTION or not landed_ids:
        return Projection(insufficient=True, sessions_observed=len(sessions), remaining=remaining)

    velocity = len(landed_ids) / len(sessions)  # deliverables per session
    estimate = remaining / velocity
    # Band widens linearly with distance: at remaining=1 the spread is small, at remaining=5
    # it is wide — a heuristic, not a statistical model (there is no distribution to fit from
    # 3 sessions), stated plainly so nobody mistakes the width for a confidence interval.
    spread = estimate * (0.25 + 0.15 * remaining)
    return Projection(insufficient=False, sessions_observed=len(sessions), remaining=remaining,
                       estimate=estimate, low=max(0.0, estimate - spread), high=estimate + spread)


def ghost_history(target: str, commits: list[git_ledger.Commit],
                   deliverables: list[Deliverable], backlog_dir: Path) -> list[tuple[str, Projection]]:
    """Re-run project_sessions_out as of each session boundary — "what did we believe back
    then" — to notice slip. Commits without a Session trailer have no boundary to sit at, so
    they're excluded here (they remain fully visible in the current-state computation)."""
    sessions = distinct_sessions(commits)
    history: list[tuple[str, Projection]] = []
    for i, session_id in enumerate(sessions):
        allowed = set(sessions[: i + 1])
        subset = [c for c in commits if any(s in allowed for s in c.trailers.get("Session", []))]
        history.append((session_id, project_sessions_out(target, subset, deliverables, backlog_dir)))
    return history


def detect_slip(history: list[tuple[str, Projection]]) -> tuple[Projection, Projection] | None:
    """A consecutive pair of confident projections where the estimate grew (moved further
    away). None if nothing comparable exists, or the estimate held or improved."""
    confident = [(sid, p) for sid, p in history if not p.insufficient]
    for (_, old), (_, new) in zip(confident, confident[1:]):
        if new.estimate is not None and old.estimate is not None and new.estimate > old.estimate:
            return old, new
    return None


def current_depth(stack_path: Path) -> tuple[int, str]:
    """(depth, note). A missing .agent/stack.json is the expected case outside an active
    session — depth defaults to 0 and the note says so explicitly, per the card: 'usually will
    not exist — treat as depth 0, visibly.'"""
    if not stack_path.exists():
        return 0, f"no live stack at {stack_path} — depth 0 (default, not measured)"
    state = stack.load_stack(stack_path)
    depth = len(stack.open_frames(state))
    return depth, f"live stack at {stack_path}, session {state['session'] or '(unset)'}"


def render_projection(p: Projection, d_id: str) -> str:
    if p.insufficient:
        return (f"insufficient data to project {d_id} "
                f"({p.sessions_observed} session(s) of velocity; need "
                f"{MIN_SESSIONS_FOR_PROJECTION})")
    if p.remaining == 0:
        return "landed"
    return (f"~{p.estimate:.1f} sessions out (range {p.low:.1f}-{p.high:.1f}, "
            f"{p.sessions_observed} session(s) of velocity)")


def render_ghost(slip: tuple[Projection, Projection], d_id: str) -> str:
    old, new = slip
    return (f"GHOST {d_id}: was ~{old.estimate:.1f} sessions out, now ~{new.estimate:.1f} "
            f"— slipped {new.estimate - old.estimate:.1f} sessions")


def _row_line(s: Status) -> str:
    if s.state == "landed":
        return f" {s.id:<5} landed        {s.last_date}                      {s.title}"
    if s.state == "in_progress":
        open_str = ", ".join(s.open_cards) or "(none open, but not yet landed)"
        return f" {s.id:<5} in progress   started {s.first_date}   open: {open_str:<10} {s.title}"
    if s.state == "frontier":
        return f" {s.id:<5} frontier      depends landed              {s.title}"
    unmet = ", ".join(dep for dep in s.depends) or "(none)"
    return f" {s.id:<5} blocked       depends: {unmet:<20} {s.title}"


def render_pipeline(statuses: list[Status], commits: list[git_ledger.Commit],
                     deliverables: list[Deliverable], backlog_dir: Path,
                     depth: int, depth_note: str, warnings: list[str]) -> str:
    sessions = distinct_sessions(commits)
    lines = [
        "ROADMAP — deliverable DAG on a time axis (generated from git trailers; never a "
        "source of truth)",
        f"data: {len(sessions)} session(s) observed ({', '.join(sessions) or 'none'}) — "
        f"projections are in SESSIONS-OUT, not calendar dates: no session cadence has been "
        f"measured, so converting to a date would fabricate one",
        f"you are here: {depth_note}, depth {depth}",
        "",
    ]
    frontier = [s for s in statuses if s.state in ("frontier", "in_progress")]
    here = frontier[0].id if frontier else "(none — everything landed or nothing started)"
    lines[2] += f", current deliverable {here}"

    for s in statuses:
        marker = "  <-- YOU ARE HERE" if s.id == here else ""
        lines.append(_row_line(s) + marker)
        if s.state in ("frontier", "blocked"):
            lines.append("        " + render_projection(
                project_sessions_out(s.id, commits, deliverables, backlog_dir), s.id))
        history = ghost_history(s.id, commits, deliverables, backlog_dir)
        slip = detect_slip(history)
        if slip:
            lines.append("        " + render_ghost(slip, s.id))

    if warnings:
        lines.append("")
        lines.append(f"WARNING — {len(warnings)} card(s) could not be read (never silently "
                      f"skipped):")
        for w in warnings:
            lines.append(f"  {w}")
    return "\n".join(lines)


def render_board(statuses: list[Status]) -> str:
    frontier = [s for s in statuses if s.state == "frontier" or s.state == "in_progress"]
    if not frontier:
        return "FRONTIER — no unblocked deliverables (everything is either landed or blocked)"
    lines = ["FRONTIER — unblocked leaves of the DAG (depends all landed, not yet landed "
             "themselves)", ""]
    for s in frontier:
        lines.append(f" {s.id}  {s.title}")
        dep_str = ", ".join(s.depends) if s.depends else "(none)"
        lines.append(f"        depends: {dep_str}")
        if s.open_cards:
            lines.append(f"        open cards: {', '.join(s.open_cards)}")
        else:
            lines.append("        open cards: none yet")
    return "\n".join(lines)


def cmd(args: argparse.Namespace) -> int:
    root = backlog.project_root(Path(args.root) if args.root else Path.cwd())
    manifest = checks.load_manifest(checks.find_manifest(root))
    deliverables = load_deliverables(manifest)
    if not deliverables:
        print("no [[deliverables]] declared in project.toml — nothing to render")
        return 0
    backlog_dir = root / "backlog"
    with backlog._chdir(root):
        commits = git_ledger.load()
    statuses = compute_statuses(commits, deliverables, backlog_dir)
    warnings = card_warnings(backlog_dir)
    stack_path = Path(args.stack_path) if args.stack_path else root / ".agent" / "stack.json"
    depth, depth_note = current_depth(stack_path)

    if args.board:
        print(render_board(statuses))
    else:
        print(render_pipeline(statuses, commits, deliverables, backlog_dir, depth, depth_note,
                               warnings))
    return 0


def _selftest() -> int:
    """Builds throwaway git repos — never this one's real history — to prove: landed vs
    in-progress vs blocked classification, a refused projection under MIN_SESSIONS_FOR_
    PROJECTION, a numeric widening-band projection once there is enough data, a ghost bar on
    a deliverable whose projection slipped, depth defaulting visibly to 0, and both CLI modes.
    Portable: no dependency on agent-os's own tree, so it passes from /tmp outside any repo."""
    import os
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

    def git(repo: Path, *a: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True)

    def commit(repo: Path, name: str, message: str) -> None:
        (repo / name).write_text(message)
        git(repo, "add", name)
        r = git(repo, "commit", "-q", "-m", message)
        if r.returncode != 0:
            raise AssertionError(r.stderr)

    def init_repo(tmp: Path) -> Path:
        repo = tmp / "repo"
        repo.mkdir()
        git(repo, "init", "-q")
        git(repo, "config", "user.email", "t@example.com")
        git(repo, "config", "user.name", "T")
        return repo

    three = [
        {"id": "D-01", "title": "one", "depends": []},
        {"id": "D-02", "title": "two", "depends": ["D-01"]},
        {"id": "D-03", "title": "three", "depends": ["D-02"]},
    ]
    deliverables = load_deliverables({"deliverables": three})
    by_id = {d.id: d for d in deliverables}
    check("level: root is 0", level("D-01", by_id) == 0)
    check("level: chain depth counts", level("D-03", by_id) == 2)
    cyclic = {"D-01": Deliverable("D-01", "a", ["D-02"]),
              "D-02": Deliverable("D-02", "b", ["D-01"])}
    try:
        level("D-01", cyclic)
        check("cycle raises", False, "did not raise")
    except SystemExit as e:
        check("cycle raises naming the fix", "cycle" in str(e).lower(), e)
    c = git_ledger.Commit("sha", "2026-08-02", "s", {"Serves": ["D-1"]})
    check("exact_serves: no D-1/D-10 collision",
          exact_serves(c, "D-1") is True and exact_serves(c, "D-10") is False)

    def write_manifest(repo: Path, deliv: list[dict]) -> None:
        lines = []
        for dd in deliv:
            lines.append("[[deliverables]]")
            lines.append(f'id = "{dd["id"]}"')
            lines.append(f'title = "{dd["title"]}"')
            lines.append("depends = [" + ", ".join(f'"{x}"' for x in dd["depends"]) + "]")
            lines.append("")
        (repo / "project.toml").write_text("\n".join(lines))

    with tempfile.TemporaryDirectory() as d:
        repo = init_repo(Path(d))
        write_manifest(repo, three)
        commit(repo, "a.txt", "one\n\nSession: 2026-08-02-a\nServes: D-01")
        commit(repo, "b.txt",
               "B-001\n\nSession: 2026-08-02-b\nCard: B-001\nServes: D-02\nDisposition: done")
        (repo / "backlog").mkdir()
        (repo / "backlog" / "B-002.md").write_text(
            "---\nid: B-002\ntitle: y\nstatus: todo\nserves: D-02\nopened: 2026-08-02\n---\n\nx\n"
        )
        old = os.getcwd()
        os.chdir(repo)
        try:
            commits = git_ledger.load()
            statuses = compute_statuses(commits, deliverables, repo / "backlog")
            by = {s.id: s for s in statuses}
            check("landed: commits + no open card", by["D-01"].state == "landed")
            check("in_progress: commits but an open card remains",
                  by["D-02"].state == "in_progress")
            check("blocked: no commits, dependency not landed", by["D-03"].state == "blocked")
            (repo / "backlog" / "B-999.md").write_text("not frontmatter at all")
            warnings = card_warnings(repo / "backlog")
            check("malformed card is reported, not skipped",
                  any("B-999" in w for w in warnings), warnings)
            p = project_sessions_out("D-03", commits, deliverables, repo / "backlog")
            check("insufficient sessions refuses a number", p.insufficient and p.estimate is None)
            rendered = render_projection(p, "D-03")
            check("refusal names the deliverable and session count",
                  "insufficient data to project D-03" in rendered and "2 session" in rendered,
                  rendered)
            check("CLI pipeline exits 0", main([]) == 0)
            check("CLI board exits 0", main(["--board"]) == 0)
        finally:
            os.chdir(old)

    with tempfile.TemporaryDirectory() as d2:
        repo = init_repo(Path(d2))
        five = [
            {"id": "D-01", "title": "one", "depends": []},
            {"id": "D-02", "title": "two", "depends": ["D-01"]},
            {"id": "D-03", "title": "three", "depends": ["D-02"]},
            {"id": "D-04", "title": "four", "depends": ["D-03"]},
            {"id": "D-05", "title": "five", "depends": ["D-04"]},
        ]
        write_manifest(repo, five)
        commit(repo, "a.txt", "one\n\nSession: 2026-08-02-a\nServes: D-01")
        commit(repo, "b.txt", "two\n\nSession: 2026-08-02-b\nServes: D-02")
        commit(repo, "c.txt", "three\n\nSession: 2026-08-02-c\nServes: D-03")
        commit(repo, "d.txt", "stall\n\nSession: 2026-08-02-d\nServes: D-03")
        big = load_deliverables({"deliverables": five})
        old = os.getcwd()
        os.chdir(repo)
        try:
            commits = git_ledger.load()
            p = project_sessions_out("D-05", commits, big, repo / "backlog")
            check("enough sessions gives a widening band, not a bare number",
                  not p.insufficient and p.low < p.estimate < p.high, p)
            history = ghost_history("D-05", commits, big, repo / "backlog")
            slip = detect_slip(history)
            check("a stalled session produces a detectable ghost (slip)", slip is not None,
                  history)
            if slip:
                text = render_ghost(slip, "D-05")
                check("ghost text says 'was' and shows both numbers",
                      "was" in text and "now" in text, text)
            depth, note = current_depth(repo / ".agent" / "stack.json")
            check("missing stack defaults to depth 0, visibly",
                  depth == 0 and "0" not in "" and "default" in note, (depth, note))
        finally:
            os.chdir(old)

    print(f"{cases - failures}/{cases} cases pass")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--board", action="store_true", help="show only the unblocked frontier")
    p.add_argument("--root", default=None, help="project root (default: cwd, walking up)")
    p.add_argument("--stack-path", default=None, help="override .agent/stack.json location")
    args = p.parse_args(argv)
    if args.selftest:
        return _selftest()
    return cmd(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
