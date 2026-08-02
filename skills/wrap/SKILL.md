---
name: wrap
description: Use at the end of every session — close cards, gate the handoff behind all-PASS checks, flush the dive profile, and overwrite docs/handoff.md.
---

# /wrap

Mechanism: `tools/checks.py` gates it, `tools/handoff.py render` assembles the draft,
`tools/git_notes.py add-profile` flushes the dive profile. Manifest-driven — nothing below is
specific to any one project.

```
tools/backlog.py close <id> --disposition done     # closure is deletion; prints its trailers
tools/checks.py                                    # must be all-PASS or /wrap stops here
tools/handoff.py render --session <id> \
    --next-action "..." --gotchas "..."            # judgment goes in as flags
git commit ...                                     # trailers below
tools/stack.py status --max-depth                  # the Depth: trailer value, measured
tools/git_notes.py add-profile --commit HEAD --clear   # flush the profile, free the stack
```

## Judgment calls this skill makes, not the scripts

- **All-PASS is a hard gate, not a suggestion.** A FAIL row from `checks.py` means /wrap does
  not finish this session — fix it, or leave the session unwrapped and say so plainly, rather
  than overwriting a green handoff with one written against a red repo. STUB and INFO rows
  (declared stubs, the rot score) never block; only FAIL does.
- **Close cards before running the gate, not after.** `tools/backlog.py close <id>` deletes
  the card and prints the trailers the commit must carry; closure *is* deletion, in the same
  commit that lands the work, because a done card left on disk duplicates the git history
  that already records it. Do not hand-edit a card to `status: done` — that status does not
  exist. The card lints read whatever is left in `backlog/`, so the gate only means something
  once the closed cards are actually gone.
- **`tools/handoff.py render` supplies the mechanical sections; you supply the judgment
  ones.** It gathers this session's commits (by `Session:` trailer) and renders them, but
  "Next action" and "Gotchas" come out as placeholders on purpose — fill them from what this
  session actually learned, not from the previous handoff's leftovers. The result is
  overwritten, never appended to; keep it inside the line cap by trimming narrative, not by
  adding sections.
- **A missing `.agent/stack.json` is a failed session, not expected degradation.** This skill
  used to say the opposite, and that sentence is why the excursion stack shipped, passed every
  gate, and never once ran: no stack meant no note, an empty dive profile, and a `Depth:`
  trailer nobody measured — all reported as healthy. `/dev` now starts the stack and
  `checks.py` fails without it, so if `add-profile` says "not found" at /wrap, depth was never
  tracked this session. Say so in the handoff rather than skipping past it.
- **The flush is a move.** `--clear` deletes the live stack once the note is written, because
  the live tier exists to become the note. Skip it and the next `/dev` finds a stack from a
  finished session and refuses to start.
- **The commit's trailers, exactly:** `Session:` always — the id already in use this session
  (check `git log` if unsure; /wrap's commit never mints a new one). `Card:` + `Serves:` if a
  card closed here. `Disposition:` on every closed card — `done`, or another value plus
  `Reason:` if it didn't finish as scoped. `Verified:` whenever the commit touches anything
  outside `docs/ backlog/ schema/` or `*.md` — say what you ran and what it said, since the
  commit-msg hook rejects an unverified code change outright rather than warning about it.
  That rejection, if it happens, is the check that /wrap actually did its job — don't route
  around it by dropping a trailer, fix what it's complaining about. `Depth:` comes from
  `tools/stack.py status --max-depth`, never from memory — a recalled depth is a claim, and
  docs/02-git-model.md already refuses to trust self-reported trailers.
