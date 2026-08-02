---
name: dev
description: Use at the start of every session — read the handoff, run the project's checks, and state the single next action before touching anything else.
---

# /dev

Mechanism is two reads, both manifest-driven (`project.toml`'s `[commands]`/`[caps]` —
nothing below is specific to any one project):

```
cat docs/handoff.md
tools/checks.py
```

## Judgment calls this skill makes, not the script

- **Drift over repair.** If the handoff's "next action" no longer holds — the branch it named
  already merged, a check it called PASS now FAILS, a card it named is gone — say so and stop
  there. Do not quietly substitute a plan of your own; the mismatch is the first thing you
  report, because a handoff that stopped matching reality is a bug in the loop itself, not a
  bug in today's work.
- **A FAIL blocks; STUB and INFO do not.** `checks.py` renders declared stubs (e.g. `lint`,
  `demo` before they're wired up) as STUB and the rot score as INFO — neither is a failure,
  both are visible by design. Only a FAIL row is a reason to fix something before starting
  the card.
- **WIP is 1, so resuming beats picking.** If a card is already `status: doing`
  (`tools/backlog.py list`, or `backlog/*.md` directly if that tool isn't wired up in this
  project yet), that card *is* the next action — finish or park it before opening another.
  Only when nothing is `doing` do you pick the next unblocked `todo` card: one whose
  `serves:` deliverable has every entry in its `depends` already landed, per
  `[[deliverables]]` in `project.toml`.
- **State it, don't just start it.** Before writing any code, say the single next action and
  which deliverable it serves, in one sentence — that sentence is what the next `/dev` (or a
  reviewer) checks the session's work against.
