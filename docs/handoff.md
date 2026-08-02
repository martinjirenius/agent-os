# Handoff

Overwritten at the end of every session by `/wrap`. History: `git log -- docs/handoff.md`.

## Last session (2026-08-02)

Founded agent-os and landed **D-01's core**: the trailer schema, the rejecting `commit-msg`
hook, and `tools/git_ledger.py`. Captured the full design from the founding conversation into
`CLAUDE.md`, `WAY-OF-WORKING.md` and `docs/00`–`05` — the diagnosis, the four axioms, the
constitution, the git model, the work model, the surfaces and the governance tiers. Seeded six
cards and the D-01…D-08 deliverable DAG in `project.toml`.

## Repo state

Branch `main`, first commit. Clean. `core.hooksPath` is set to `.githooks`, so the gate is live
for anyone committing here.

## Next action

**B-001 — `/timetravel`.** First move: a thin skill over `git_ledger.py deleted` plus
`git show <sha>^:<path>`, covering three cases — find a deleted file, see a file as of a date,
and what did this look like before decision D-nnn.

Do this before anything else. The no-back-compat rule is written but not yet *safe*: deletion
is only licensed once retrieval is proven, and nothing else in the DAG should land first.

## Open questions / pending decisions

None blocking. Two things Martin has not yet been asked and does not need to be until D-07:
whether the plugin installs via a local marketplace or a path, and where `~/projects/index.html`
should live.

## Gotchas

- **The repo obeys its own rules.** A commit without `Session:` is rejected. `Card:` requires
  `Serves:`. Touching anything outside `docs/ backlog/ schema/` or `*.md` requires `Verified:`.
  Run `python3 .githooks/commit-msg --selftest` (13 cases) if the gate seems wrong.
- `lint` and `demo` in `project.toml` are **marked stubs**, empty on purpose until B-003 and
  D-07. They are visible stubs, not silent fakes.
- Existing projects are **untouched**. Nothing has been migrated; D-08 is the pilot, and
  stockpilot is the target because its rot is in docs, which is the real disease.
- The plan this came from: `~/.claude/plans/quiet-hugging-penguin.md`.
