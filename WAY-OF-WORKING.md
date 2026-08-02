# The way of working

One page. If you read nothing else, read this.

## The shape of it

**Product → deliverables → cards → commits → tests.** Every link is enforced by a lint, so
work that ladders up to nothing cannot survive a `/wrap`. That chain *is* the anti-drift
mechanism — not discipline, not remembering.

The plan is a **DAG**. Deliverables have dependencies; you take the next unblocked leaf, one
at a time. The roadmap is that DAG on a time axis. The board is its current frontier.

## The loop

**`/dev`** — read the handoff, run `checks.py`, state the single next action and which
deliverable it serves. Report drift rather than working around it.

**Work** — one card at a time (WIP is 1, and it is a lint). Small commits, each carrying its
trailers. Investigations push onto the excursion stack and pop with an outcome.

**`/wrap`** — update cards, delete the ones that are done, run all checks (all-PASS gates the
handoff), flush the session's dive profile to a git note, commit, overwrite the handoff.

## The four surfaces

Reports, experiments and explainers are **evidence** — they exist to make claims *checkable*,
not to be read. Martin reads four things:

1. **Product** — `docs/00-product.md` and the running demo. A walking skeleton from day one,
   stubs marked as stubs, and the demo runs in `checks.py` every session. This is also why
   `/prune` needs no judgment: code unreachable from the demo path is provably dead.
2. **Roadmap** — a generated pipeline. Measured past, velocity-projected future with a
   widening band, ghost bars where a date used to be (**slip is the headline**), and a live
   "you are here" marker showing the current deliverable *and its depth*. Zoom in for the
   frontier board, again for the evidence.
3. **Decision inbox** — `Chose:` and `Question:` items. Silence ratifies.
4. **Cross-project board** — every project's next action, blocker and rot score, on one page.

## Escalation

Three things reach Martin, and nothing else: **irreversible + external**, **product-definition
changes**, and **true forks** where the call is taste rather than evidence.

Everything else is decided, recorded as `Chose:`, and continued. **Questions batch; they never
block.** Decisions are made by default and reversed on objection — `git revert` is cheap, and
that cheapness is exactly what licenses the autonomy. Asking is the expensive option.

## Rabbit holes

A rabbit hole is an **unmanaged call stack**. Make it managed:

- **Push** requires the question *and* why it unblocks the parent. Writing that sentence is
  most of the cure — a weak link becomes obvious.
- **Depth cap 3**, budgeted in tool calls. Depth 4 forces a choice: pop and file a card,
  promote the excursion to top-level work, or escalate.
- **Pop** requires an outcome — answered, abandoned, or promoted. Findings go to the ledger;
  abandoned paths get a note so the next session doesn't re-dig. **Restate the parent's goal
  on return.**

The stack lives in `.agent/stack.json` because the agent needs to read its own depth. The
dive profile Martin looks at is a free side effect of that.

## Git is the archive

The working tree is the present tense. Everything else is history:

- Superseded things are **deleted**, with `Supersedes:` recording what and why.
- Done cards are **deleted** in the commit that lands their work.
- Hindsight attaches to the commit it corrects, as a **git note** — not as a new document.
- Landmarks are tags: `state/2026-08-02-v2-adopted`.
- Nothing is preserved in the tree for fear of losing it. `/timetravel` gets it back.

## Anti-accretion

The system's own rot is prevented the same way:

- **Closed doc schema** — a file in `docs/` that is not a defined slot fails checks.
- **Skill budget: 3 local.** A fourth means one dies or it earns promotion into the OS.
- **Retirement** — `/prune` deletes skills that have not fired in N sessions.
- **Promotion** — anything wanted by two projects moves up into the OS and deduplicates.
  The answer to "we need this here" is usually "then it belongs upstairs."

## What is tweakable, and by whom

| tier | what | changed by | frequency |
|---|---|---|---|
| Constitution | axioms, escalation policy, doc schema | Martin, deliberately | ~never |
| OS | generic skills, scripts, lints | agent proposes → all projects | monthly |
| Manifest | `project.toml` — commands, caps, deliverables | agent, freely | weekly |
| Project | ≤3 local skills, product definition | agent proposes, Martin ratifies | occasionally |
| Work | cards, commits, code | agent, autonomous | constantly |

Tweakability rises as you go down. The constitution is hard to change on purpose — that is
the difference between a constitution and a suggestion.
