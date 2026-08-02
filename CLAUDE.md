# CLAUDE.md — agent-os

The shared operating system for Martin's projects. **agent-os is its own first user**: every
rule here is one this repo obeys. If a rule is too annoying to follow here, it is too annoying
to ship.

New session: read `WAY-OF-WORKING.md` (one page, the whole system), then `docs/handoff.md`.

## Axioms

1. **Derive, don't store.** Anything generatable is generated. Generated artifacts cannot rot
   silently; hand-maintained ones do, and an index that is silently incomplete is worse than
   no index — it answers "no such thing" with false confidence.
2. **If it can be a script, it must be a script.** Prose is advisory; exit codes bind.
3. **The tree is the present, git is the past.** Nothing in the working tree exists to
   preserve a former state.
4. **One authority per topic.** Duplicates are deleted, never synced.

## Constitution

Changing anything in this section is a deliberate act, never a session decision.

**No backwards compatibility.** This repo has exactly one consumer: itself. There is no
deprecation period. The old path is deleted in the same commit that lands the new one.
`*_v2`, `legacy_*`, `if old_format:`, and re-export stubs are defects — do not write them,
and delete them when found. **Deletion is non-destructive: git has it.** Retrieve with
`/timetravel`. Before any refactor, write the characterization test first — that is the net
that makes fearless deletion safe.

**Escalation is a closed list.** Only three things reach Martin:

1. Irreversible *and* external — deploy, publish, spend money, touch real accounts or data.
2. Changes to what the product **is** (`docs/00-product.md`).
3. True forks — comparable paths where the call is taste or priority, not evidence.

Everything else: decide it, record `Chose:` with the rationale, continue. **Questions never
block — they batch** into the decision inbox. Silence ratifies; objection reverts (`git
revert` is cheap, which is what licenses the autonomy). Asking is the expensive option, not
the safe one. More than two escalations in a session trips `/process-audit`.

**`main` is always demo-green.** Unfinished work lives on a branch. A branch open more than
three sessions is a rot signal, not a work-in-progress.

**Depth cap 3.** Investigations are a stack (`.agent/stack.json`). Pushing requires stating
the question *and* why answering it unblocks the parent. Depth 4 is not allowed — pop and
file a card, promote the excursion to top-level work, or escalate. Popping requires an
outcome and a restatement of the parent's goal.

**Caps, all lint-enforced:** source file 500 lines · this file 150 lines · todo 10 cards ·
WIP 1 card · local skills 3.

## Session protocol

`/dev` → work → `/wrap`. A session that ends without `/wrap` leaves a stale handoff, and the
next `/dev` will say so.

Every commit carries trailers (`docs/02-git-model.md`). They are load-bearing: the ledger,
the roadmap, the decision inbox and the dive profile are all generated from them. The
`commit-msg` hook rejects non-conforming commits — that is deliberate.

## Work model

The plan is a **DAG**, not a backlog: deliverables have dependencies, and work is the next
unblocked leaf. This is a build system, not agile — there is no team to coordinate.

- Card status is a **field**, not a folder.
- **Done cards are deleted** in the same commit that lands the work. A done card duplicates
  git history (axiom 4). The closed backlog is a query:
  `git log --diff-filter=D -- backlog/`.
- **There is no icebox.** It is where decisions go to not be made, and it is passively always
  in view. Deferred work is `Disposition: deferred` + `Reason:`, and becomes a query.
- Two tiers only: **cards** (now) and **deliverables** (planned). Every card `Serves:` a
  deliverable; a deliverable serves the product. Work that ladders up to nothing is deleted.

## Where a rule belongs

Push every rule as far up this list as it will go — lint, then script, then doc, then skill,
and only then this file:

| form | nature | context cost |
|---|---|---|
| lint | deterministic, runs unasked | zero |
| script | deterministic, on request | zero |
| doc | rare reference, reached by pointer | only when read |
| skill | judgment, at a specific trigger | only when triggered |
| CLAUDE.md | needed every session | **always** |

**One skill = one trigger.** Skills are thin orchestration over fat scripts; a fat skill means
mechanism and judgment are tangled. A doc containing steps, or the phrase "remember to", is a
skill or a lint that has not been written yet.

## Code conventions

Written for a maintainer that reads by grep and edits by exact match:

- **≤500 lines per file** — context cost, and exact-match edits get unreliable in big files.
- **Grep-ability is architectural.** No metaprogramming, no string-built identifiers, no
  dynamic dispatch that defeats search.
- A module docstring's **first line is its index entry** — write it for the index.
- Colocate tests with source. Flat beats deep. Types everywhere. No hidden global state.
- Error messages state the fix; the agent reads them as instructions.

Tests: **fail-first is mandatory and demonstrated** (record the failing output before the
fix). Characterization tests precede refactors. The demo path is a test. Under-mock — an
over-mocked test passes against a fantasy. Determinism is a lint: seeds pinned, clock
injected, no network in unit tests.

## Map

- `WAY-OF-WORKING.md` — the loop, the surfaces, the escalation policy. Start here.
- `docs/00-product.md` — what this is and what "working" means.
- `docs/01-design.md` — the diagnosis and why each decision was made.
- `docs/02-git-model.md` — trailer schema, notes, tags, branches vs excursions.
- `docs/03-practices.md` — lint catalogue, skill sizing, testing.
- `docs/04-surfaces.md` — the four surfaces Martin reads.
- `docs/05-schema.md` — doc slots, skill budget, tweakability tiers.
- `docs/handoff.md` — overwritten every `/wrap`. History: `git log -- docs/handoff.md`.
- `backlog/` — only the future.
- `out/` — generated surfaces, gitignored. Never a source of truth.
