# 03 — Practices: lints, skills, tests

## The lint catalogue

The meta-rule: **anything that has had to be said twice becomes a lint.** All of these run
behind one `checks.py` — one command, one PASS/FAIL table, exit 1.

**Structure**
- file line cap (500), function length, nesting depth
- CLAUDE.md line cap (150)
- one concept per file; filename matches the concept

**Rot**
- compat markers: `_v2`, `legacy`, `deprecated`, `back-compat`, `TODO(old)`
- dead code (vulture / ts-prune / knip)
- docs not referenced from canon; files in `docs/` outside the schema
- code unreachable from the demo path
- branches open more than 3 sessions
- skills that have not fired in N sessions
- net-lines trend (reported, not gated)

**Process**
- WIP ≤ 1 card; todo ≤ 10 cards
- every card `Serves:` a deliverable that serves the product
- commit trailer schema validity
- index freshness (`--check`)
- more than 2 escalations in a session
- depth > 3, or sustained time at depth 3

**Standard**
- typecheck, format, import hygiene, demo path runs

## Skill sizing

**One skill = one trigger.** Two distinct trigger conditions means two skills; two skills that
always fire together are one skill. The unit is the trigger, not the topic.

Both failure modes are real: too many skills and none fire, because trigger matching gets
ambiguous; too few and each loads a pile of irrelevant content that dilutes the relevant part.
Seven to twelve, with sharp non-overlapping triggers, is the working range.

**Skills are thin orchestration over fat scripts.** A skill that is 200 lines of prose
checklist is a script that has not been written. If a skill feels slim, that is usually correct
— it means the mechanism migrated to where it belongs and only the judgment stayed.

Descriptions are written as **triggers**, not summaries: "before trusting a metric…", "when
Martin says something is off…". A description that describes the topic will not fire.

## Testing, when the maintainer is an agent

Tests are the agent's only ground truth. It will confabulate success; a suite will not.

- **Fail-first is mandatory and demonstrated.** Record the failing output before the fix
  (`Tests-first:`). This kills the most common agent failure: a test that passes vacuously and
  proves nothing.
- **Characterization tests before refactors.** This is what makes the no-back-compat rule safe
  — the old path can be deleted fearlessly precisely because a test pins the behavior being
  kept. The rule and the net ship together.
- **The demo path is a test**, run every session.
- **Under-mock.** Agents over-mock and end up testing a fantasy. Prefer real I/O against small
  fixtures.
- **Determinism is a lint**: seeds pinned, clock injected, no network in unit tests.
- No card closes without a test that would have failed before it.

## Code written for an agent maintainer

Each rule with its reason, because a bare rule gets rationalized around:

- **≤500 lines per file** — context cost, and exact-match edit reliability degrades in large
  files. This is the real reason, not aesthetics.
- **Grep-ability is an architectural property.** No metaprogramming, no dynamic dispatch that
  defeats search, no identifiers built from strings. If `grep` cannot find it, neither can the
  maintainer.
- **A module docstring's first line is its index entry** — write it for the index, not for a
  reader. The index is generated from it.
- **Names are the index.** Agents navigate by name before structure.
- **Colocate tests with source** — one directory listing shows both.
- **Flat beats deep.** Every directory level costs an exploration turn.
- **Types are compressed context.** Annotate everything.
- **No hidden global state.** Agents reason badly across invisible coupling.
- **Error messages state the fix.** The agent reads them as instructions and acts literally.
