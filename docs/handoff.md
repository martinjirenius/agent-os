# Handoff

Overwritten at the end of every session by `/wrap`. History: `git log -- docs/handoff.md`.

## Last session (2026-08-02, session `2026-08-02-b`)

Ran lead-and-delegate: Opus lead, Sonnet workers, review before each land. **D-01 through D-07
all landed** — B-001…B-010 closed, backlog empty. `main` clean, `checks.py` 11 rows all-PASS,
172 tests, rot 0. `demo` is no longer a stub: `tools/demo.py` installs agent-os into a fresh
repo and runs the real un-copied gate there, so the product claim is a test.

## Repo state

Branch `main`, clean. 13 tools, 3 skills (`dev`, `wrap`, `timetravel`), `.claude-plugin/`
manifest. Nothing installed anywhere — `~/.claude` and all five sibling projects untouched.

## Next action

**D-08, pilot on stockpilot** — the only unlanded deliverable, and the one that tests the
system against a real codebase instead of its author. **Blocked on Martin**: it writes outside
this repo, which was explicitly out of scope while he was away.

## Open questions / pending decisions

- **Ratify or revert this session's `Chose:` items** — `tools/inbox.py --since 2026-08-02-b`.
  Silence ratifies. One real `Question:` is on `961cf4e` (B-010).
- **D-07 is code-complete but not installed.** Registering the plugin in `~/.claude` needs a
  go-ahead. Until then no project actually references these skills.
- Three files sit within 20 lines of the 500 cap: `rot.py` 492, `checks.py` 487,
  `backlog.py` 480. The next substantive edit to any of them trips the gate. Split before
  extending, characterization test first.

## Gotchas

- **Absence read as success — four bugs of this shape in one session.** A lint returning no
  row for missing input; card lints vanishing when `backlog/` was deleted; `git rev-parse`
  accepting a sha that does not exist; a module name shadowing the stdlib so a missing file
  failed as `AttributeError`. Every one reported healthy while doing nothing. This deserves a
  standing lint, not four individual fixes — it is the most valuable finding of the session.
- **A test that drives a git-running tool must `chdir` into its fixture.** One did not and
  wrote a note into this repo's real `refs/notes`, annotating a commit not in this repo.
  Cleaned; `add-profile`/`annotate` now use `rev-parse --verify <rev>^{commit}`.
- **Parallel workers must have declared file ownership.** Two workers editing
  `git_ledger.py` collided mid-flight in wave 1. Waves 2+ used an explicit read-only list and
  had no collisions; workers reported wiring needs instead of doing them.
- Velocity data is 2 sessions, so `roadmap.py` refuses to project and says so. Do not
  "fix" that by lowering the threshold.
- `skills_never_fired` and dead-code-from-demo are still `unimplemented`, deliberately not
  scored 0.
