#!/usr/bin/env python3
"""Excursion stack — push/pop the investigation call stack and keep depth honest.

A rabbit hole is an UNMANAGED call stack (WAY-OF-WORKING.md "Rabbit holes"). This makes it
managed: the agent can read its own depth, and the dive profile Martin reads is a free side
effect rather than a separate thing to maintain.

Two rules carry the whole feature, and both are refusals rather than reminders:

  - `push` demands the question AND why answering it unblocks the parent. Writing that
    sentence is most of the cure — a weak link becomes obvious while you type it. A push
    helper that accepts a bare question has removed the only part that works.
  - `pop` demands an outcome and restates the parent's goal on the way out, because
    returning without that restatement is exactly how the original thread gets lost.

The file is `.agent/stack.json` — the live tier of docs/02-git-model.md's three tiers,
gitignored, rewritten many times per session. Its schema is FIXED by `tools/git_notes.py`,
which copies it verbatim onto a git note at /wrap so one renderer can read both the live and
the historical profile. This module conforms to that schema; it does not own it.

    tools/stack.py push --question "..." --unblocks "..." [--session ID]
    tools/stack.py pop --outcome answered|abandoned|promoted [--note "..."]
    tools/stack.py status
    tools/stack.py --selftest
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import checks  # Row/find_manifest/load_manifest: one authority per topic (axiom 4)

DEFAULT_STACK_PATH = Path(".agent") / "stack.json"
OUTCOMES = ("answered", "abandoned", "promoted")

# Used only when no project.toml can be found (a scratch dir, or a project that has not been
# initialised yet). Inside a real project the cap always comes from [caps].excursion_depth.
FALLBACK_DEPTH_CAP = 3


def now_iso() -> str:
    """Wall clock, isolated in one place so every caller can inject a fixed value instead."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def empty_stack(session: str) -> dict:
    return {"session": session, "frames": []}


def load_stack(path: Path, session: str = "") -> dict:
    if not path.exists():
        return empty_stack(session)
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise SystemExit(
            f"{path} is not valid JSON ({e}) — delete it to start a fresh stack, or fix the "
            f"syntax by hand if an excursion in progress is worth keeping."
        )


def save_stack(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def open_frames(state: dict) -> list[dict]:
    """Frames not yet popped, shallowest first — the live part of the stack."""
    return [f for f in state["frames"] if f["closed"] is None]


def depth_cap(root: Path) -> int:
    """`[caps].excursion_depth` from the project manifest, or the fallback outside a project."""
    try:
        manifest_path = checks.find_manifest(root)
    except SystemExit:
        return FALLBACK_DEPTH_CAP
    caps = checks.load_manifest(manifest_path).get("caps", {})
    return int(caps.get("excursion_depth", FALLBACK_DEPTH_CAP))


def push(state: dict, question: str, unblocks: str, cap: int, now: str) -> dict:
    """Open an excursion. Refuses without both halves of the justification, and past the cap."""
    if not question.strip():
        raise SystemExit(
            "an excursion needs a question — pass --question. Naming what you are trying to "
            "find out is what stops this becoming an open-ended dig."
        )
    if not unblocks.strip():
        raise SystemExit(
            "an excursion needs --unblocks: why does answering this let the PARENT task "
            "continue? Writing that sentence is most of the cure — if it is hard to write, "
            "the excursion probably is not worth taking."
        )

    new_depth = len(open_frames(state)) + 1
    if new_depth > cap:
        raise SystemExit(
            f"depth {new_depth} exceeds the cap of {cap} — this is a rabbit hole, and there "
            f"are exactly three ways out:\n"
            f"  1. pop and file a card  — `tools/stack.py pop --outcome promoted`, then "
            f"`tools/backlog.py new`\n"
            f"  2. promote the excursion to top-level work — it is not a detour, it is the job\n"
            f"  3. escalate to Martin — only if it is irreversible+external, a product change, "
            f"or a true fork\n"
            f"Going deeper is not one of them."
        )

    state["frames"].append({
        "depth": new_depth,
        "question": question,
        "unblocks": unblocks,
        "opened": now,
        "closed": None,
        "outcome": None,
    })
    return state


def pop(state: dict, outcome: str, note: str | None, now: str) -> tuple[dict, str | None]:
    """Close the deepest open excursion. Returns the state and the PARENT's question.

    The parent goal comes back so the caller can restate it — returning from a dive without
    restating what you were originally doing is how the thread gets lost.
    """
    if outcome not in OUTCOMES:
        raise SystemExit(
            f"--outcome must be one of {', '.join(OUTCOMES)} (got {outcome!r}) — a pop "
            f"without an outcome leaves no record of whether the question was settled, and "
            f"the next session re-digs the same hole."
        )
    live = open_frames(state)
    if not live:
        raise SystemExit(
            "no open excursion to pop — `tools/stack.py status` shows the current depth."
        )

    frame = live[-1]
    frame["closed"] = now
    frame["outcome"] = f"{outcome}: {note}" if note else outcome
    parent = open_frames(state)
    return state, (parent[-1]["question"] if parent else None)


def check_stack_empty(root: Path) -> checks.Row:
    """Lint: no excursion left open. ALWAYS returns a Row, even with no stack file at all.

    A missing file means depth 0, which is a PASS you can see — not a row that vanishes. A
    lint that renders nothing for a missing input is indistinguishable from one that passed,
    and the gate then reports all-clear while it is not running (axiom 1).
    """
    state = load_stack(root / DEFAULT_STACK_PATH)
    live = open_frames(state)
    if not live:
        return checks.Row("excursion stack empty", "PASS")
    listing = "\n  ".join(f"depth {f['depth']}: {f['question']}" for f in live)
    return checks.Row(
        "excursion stack empty", "FAIL",
        f"{len(live)} excursion(s) still open — pop each with an outcome before wrapping, or "
        f"the session ends with a lost thread:\n  " + listing)


def _resolve_path(args: argparse.Namespace) -> Path:
    return Path(args.stack_path) if args.stack_path else DEFAULT_STACK_PATH


def cmd_push(args: argparse.Namespace) -> int:
    path = _resolve_path(args)
    state = load_stack(path, args.session or "")
    if args.session:
        state["session"] = args.session
    if not state["session"]:
        raise SystemExit(
            "no session id — pass --session on the first push of a session (e.g. 2026-08-02-a); "
            "the dive profile is grouped by it."
        )
    state = push(state, args.question, args.unblocks, depth_cap(Path.cwd()), now_iso())
    save_stack(path, state)
    frame = state["frames"][-1]
    print(f"depth {frame['depth']}: {frame['question']}")
    print(f"  unblocks: {frame['unblocks']}")
    return 0


def cmd_pop(args: argparse.Namespace) -> int:
    path = _resolve_path(args)
    state = load_stack(path)
    state, parent_goal = pop(state, args.outcome or "", args.note, now_iso())
    save_stack(path, state)
    closed = state["frames"][-1]
    print(f"popped depth {closed['depth']}: {closed['outcome']}")
    if parent_goal:
        print(f"back to: {parent_goal}")
    else:
        print("back to: top level — no parent excursion")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    state = load_stack(_resolve_path(args))
    live = open_frames(state)
    print(f"session {state['session'] or '(unset)'} — depth {len(live)}")
    for f in live:
        print(f"  {f['depth']}: {f['question']}  (unblocks: {f['unblocks']})")
    return 0


def _selftest() -> int:
    cases = 0
    failures = 0

    def check(name: str, cond: bool, detail: object = "") -> None:
        nonlocal cases, failures
        cases += 1
        if not cond:
            print(f"FAIL {name}: {detail}")
            failures += 1

    s = empty_stack("s1")
    for bad, want in ((("", "u"), "--question"), (("q", ""), "--unblocks")):
        try:
            push(s, bad[0], bad[1], cap=3, now="t0")
            check(f"push refused without {want}", False, "did not raise")
        except SystemExit as e:
            check(f"push refused without {want}", want in str(e), e)

    s = push(s, "q1", "u1", cap=3, now="t0")
    check("push records depth 1", s["frames"][0]["depth"] == 1)
    check("frame matches git_notes' fixed schema",
          set(s["frames"][0]) == {"depth", "question", "unblocks", "opened", "closed", "outcome"},
          set(s["frames"][0]))

    s = push(s, "q2", "u2", cap=3, now="t1")
    s = push(s, "q3", "u3", cap=3, now="t2")
    try:
        push(s, "q4", "u4", cap=3, now="t3")
        check("depth 4 refused", False, "did not raise")
    except SystemExit as e:
        msg = str(e)
        check("depth 4 refused naming all three exits",
              "pop and file a card" in msg and "promote the excursion" in msg
              and "escalate" in msg, msg)

    s, parent = pop(s, "answered", "found it", now="t4")
    check("pop closes the deepest frame", s["frames"][-1]["outcome"] == "answered: found it")
    check("pop restates the parent's goal", parent == "q2", parent)

    try:
        pop(s, "nonsense", None, now="t5")
        check("pop refused without a valid outcome", False, "did not raise")
    except SystemExit as e:
        check("pop refused without a valid outcome", "--outcome" in str(e), e)

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        row = check_stack_empty(root)
        check("lint emits a PASS row when no stack file exists (never None)",
              row is not None and row.status == "PASS", row)

        save_stack(root / DEFAULT_STACK_PATH,
                   push(empty_stack("s1"), "open one", "u", cap=3, now="t0"))
        row = check_stack_empty(root)
        check("lint FAILs on an unpopped excursion and names it",
              row.status == "FAIL" and "open one" in row.detail, row)

    print(f"{cases - failures}/{cases} cases pass")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--selftest", action="store_true")
    sub = p.add_subparsers(dest="cmd")

    pu = sub.add_parser("push"); pu.set_defaults(fn=cmd_push)
    pu.add_argument("--question", default="")
    pu.add_argument("--unblocks", default="")
    pu.add_argument("--session", default=None)
    pu.add_argument("--stack-path", default=None)

    po = sub.add_parser("pop"); po.set_defaults(fn=cmd_pop)
    po.add_argument("--outcome", default=None)
    po.add_argument("--note", default=None)
    po.add_argument("--stack-path", default=None)

    st = sub.add_parser("status"); st.set_defaults(fn=cmd_status)
    st.add_argument("--stack-path", default=None)

    args = p.parse_args(argv)
    if args.selftest:
        return _selftest()
    if not getattr(args, "fn", None):
        p.print_help()
        return 2
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
