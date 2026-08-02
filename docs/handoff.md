# Handoff

Overwritten at the end of every session by `/wrap`. History: `git log -- docs/handoff.md`.

## Last session (2026-08-02, session `2026-08-02-a`)

Founded agent-os and landed **D-01's core**: the trailer schema, the rejecting `commit-msg`
hook, and `tools/git_ledger.py`. Captured the founding conversation into `CLAUDE.md`,
`WAY-OF-WORKING.md` and `docs/00`–`05`. Seeded cards B-001…B-006 and the D-01…D-08 DAG in
`project.toml`. Checks all-PASS: selftests 13/13 and 1/1, caps within limits.

## Repo state

Branch `main`, clean. `core.hooksPath = .githooks`, so the gate is live for every commit here.

## Next action

**B-001 — `/timetravel`**, and nothing before it: the no-back-compat rule is written but not yet
*safe*, because deletion is only licensed once retrieval is proven.

Next session runs **lead-and-delegate** (Opus lead, Sonnet workers, review before each new
spawn). Cards are dependency-ordered into waves that can go in parallel:

- wave 1 — B-001, B-002 (D-01)
- wave 2 — B-003, B-004 (D-02, needs wave 1)
- wave 3 — B-005, B-006 (D-04/D-03, needs wave 2)

**Workers do not commit.** The lead reviews and lands the work, so the ledger stays clean and
review is the thing that gates a commit rather than a formality after it. Every delegation
prompt must carry the card, its `Serves:` deliverable, and the acceptance check — a cold worker
has none of this session's context, only what the repo says.

## Open questions / pending decisions

None blocking. Two not needed until D-07: plugin install via local marketplace or path, and
where `~/projects/index.html` lives. Martin is away — decide under the escalation policy and
record `Chose:`.

## Gotchas

- **The repo obeys its own rules.** No `Session:` → rejected. `Card:` requires `Serves:`.
  Anything outside `docs/ backlog/ schema/` or `*.md` requires `Verified:`. Debug the gate with
  `python3 .githooks/commit-msg --selftest`.
- `lint` and `demo` in `project.toml` are **marked stubs**, empty until B-003 and D-07.
- `git_ledger.py deleted` is **untested against real data** — nothing has been deleted yet.
  B-001 closing is its first real exercise; verify it there rather than assuming.
- Existing projects are untouched. stockpilot is the pilot, at D-08.
- Founding plan: `~/.claude/plans/quiet-hugging-penguin.md`.
