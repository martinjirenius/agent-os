---
name: dev
description: Use at the start of every session — read the handoff, run the project's checks, and state the single next action before touching anything else.
---

# /dev

Mechanism is two reads and one write, all manifest-driven (`project.toml`'s
`[commands]`/`[caps]` — nothing below is specific to any one project):

```
cat docs/handoff.md
tools/stack.py start --session <YYYY-MM-DD-letter>   # begin tracking depth
tools/checks.py
```

The session id is today's date plus the next unused letter — `tools/git_ledger.py sessions`
lists the ones already taken.

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
- **`start` refusing means the last session never wrapped.** A stack belonging to a different
  session survived, so that session's dive profile was never flushed to a note and is about to
  be lost. Recover it (`tools/git_notes.py add-profile --commit <that session's last commit>`)
  before passing `--force`. Do not reach for `--force` first: it discards the only record that
  session's depth ever existed.
- **Push before you dive, not after.** The moment a question needs its own investigation,
  `tools/stack.py push --question ... --unblocks ...`, and `pop --outcome ...` on the way back.
  Depth left untracked makes `Depth:` a guess and the dive profile a flat line — and the gate
  cannot tell an honest depth-0 session from an unmeasured one except by the stack file
  existing, which is exactly why `start` is above.
- **State it, don't just start it.** Before writing any code, say the single next action and
  which deliverable it serves, in one sentence — that sentence is what the next `/dev` (or a
  reviewer) checks the session's work against.
