---
name: timetravel
description: Use when something that used to exist is gone and you need it back — a deleted file, an earlier version of a file, or "what did this look like before <card/deliverable/tag/date> changed it." This is the retrieval half of the no-backwards-compatibility rule; reach for it instead of hedging a deletion "just in case."
---

# /timetravel

Nothing in this repo is kept around "just in case" (`docs/02-git-model.md` — "Deletion is the
archive"). That is only safe because retrieval is one command, not an archaeology project.
All three retrieval modes are one script: `tools/timetravel.py`.

```
tools/timetravel.py find <path-fragment>      # a deleted file, by partial/fuzzy path
tools/timetravel.py at <path> <date>           # a file as of a date (YYYY-MM-DD)
tools/timetravel.py before <anchor> <path>     # a file before <anchor> last changed it
                                                #   anchor: B-0NN | D-0N | state/* tag | date
```

Run whichever mode matches the question — don't guess at git plumbing by hand; the script
already resolves anchors, walks history, and prints a ready-to-use `restore:` command.

## Judgment calls this skill makes, not the script

- **Which mode fits "before X" when X is ambiguous.** If the user names a card or deliverable
  that has landed multiple times, `before` resolves to its *most recent* change — that is
  "undo the last thing that touched this," which is what "before" means in practice. If they
  actually want an earlier landing, give them the anchor's other commits
  (`tools/git_ledger.py query --card <id>`) and let them pick a date or sha instead.
- **When the answer is "nothing to find."** An empty result from `find` is not a bug to
  route around — it means the file was never deleted, or deleted from a state before the
  repo existed. Say that plainly rather than fuzzy-matching harder.
- **Restoring vs. viewing.** This skill's job is to show the prior content and print the
  restore command — it does not run the restore. Applying it (overwriting the working tree)
  is a separate, deliberate step the caller takes.
