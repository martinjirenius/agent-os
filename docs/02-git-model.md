# 02 — The git model

The working tree is the present. **The history is the database, and the commit message is its
insert statement.**

## Three tiers, because granularity differs

| tier | holds | cadence | lives in |
|---|---|---|---|
| live | excursion stack, current depth | many times per session | `.agent/stack.json`, gitignored |
| durable | cards, decisions, findings, verification | per commit | **trailers** |
| rich | session dive profile, hindsight | per session | **git notes** |

Depth changes dozens of times between commits, so it cannot be a trailer. Notes are the
bridge: `/wrap` flushes the session's profile into a note on the final commit. Live profiles
read `stack.json`; historical ones replay from notes. Two sources, one renderer.

## Trailer schema

Standard git trailers — `Key: value` lines at the end of the body, parseable with
`git log --format='%(trailers:key=Card)'` and `git interpret-trailers`.

| trailer | when | feeds |
|---|---|---|
| `Session:` | **always** | grouping, velocity |
| `Card:` | card work | backlog history |
| `Serves:` | card work — **required** | product traceability, pipeline rows |
| `Verified:` | code changed — **required** | trust surface |
| `Disposition:` | card closure | closed-card ledger |
| `Reason:` | required when `Disposition` ≠ `done` | why-was-this-dropped queries |
| `Supersedes:` | deleting a replaced thing | rot tracking, `/timetravel` anchors |
| `Tests-first:` | new behavior | fail-first evidence |
| `Finding:` | a durable fact was learned | knowledge ledger, `/recall` |
| `Decision:` | a design call was made | decision log |
| `Chose:` | autonomous call under delegation | decision inbox (ratify or revert) |
| `Question:` | genuine escalation | decision inbox |
| `Depth:` | max depth reached | dive profile, rabbit-hole lint |

`Disposition:` is one of `done` · `rejected` · `superseded` · `obsolete` · `deferred`.

Required set is deliberately small — `Session:` always, `Card:`+`Serves:` on card work,
`Verified:` on code changes. Everything else is optional enrichment. A typo fix needs one
trailer; making it need six would burn the agent's budget on paperwork.

`Serves:` is the load-bearing one. It is what makes **product → deliverable → card → commit →
test** mechanically traceable, which is what lets a lint delete work that ladders up to nothing.

### Example

```
B-004: reject commits that fail the trailer schema

The hook runs the project's test command itself rather than trusting
Verified:, because a self-reported trailer is not evidence.

Session: 2026-08-02-a
Card: B-004
Serves: D-01
Verified: pytest 12 passed; bad-trailer fixture rejected with exit 1
Tests-first: commit_msg_test.py failed on the missing-Session case first
Depth: 1
```

## Enforcement

A **`commit-msg` hook that rejects**. Not a lint after the fact — a gate at write time. An
advisory schema is correct for six sessions and then quietly develops holes.

Enable with `git config core.hooksPath .githooks` (repo-local, no global install, travels with
a clone).

## Notes

`git notes` attach mutable annotations to immutable commits, on a separate ref. Two uses:

1. **Session profile** — written by `/wrap`, replayed into the dive profile.
2. **Hindsight** — when a later session learns that an earlier commit's approach was wrong, it
   annotates *that commit* rather than writing a new document:
   `git notes add -m "Superseded by D-051: fails under async cameras" <sha>`.

The correction lives where the mistake lives. This is the direct fix for "forgets old
decisions" — `git log --show-notes` is history with hindsight baked in.

## Tags

Landmarks, not releases: `state/2026-08-02-v2-adopted`. `git tag -l 'state/*'` is the timeline,
so `/timetravel` has anchors instead of hash archaeology.

## Deletion is the archive

There is no `docs/archive/`. An archive directory is a hedge born from not trusting git.

```
git log --diff-filter=D --name-only     # everything ever removed
git show <sha>^:path/to/file            # get it back
git log --diff-filter=D -- backlog/     # the closed-card ledger
```

## Branches vs excursions

Two different things, often confused:

- **Excursion** — an *investigation*. Reading, probing, hypothesizing. Produces knowledge, not
  code. A git branch is pure overhead; there is nothing to merge. Lives on the stack.
- **Branch** — a *speculative implementation*. "Rewrite the loader and see." Produces code that
  must merge or die.

The escalation between them is clean: an excursion concluding "this needs a speculative
rewrite" **becomes** a branch.

`main` is always demo-green, so unfinished work lives on a branch — which makes half-done work
*measurable* (a spur that has not rejoined, with a session count) rather than invisible.

## Gotchas

- **Do not rebase landed history.** It breaks the ledger. Amend before commit is fine.
- **Notes do not push by default.** `refs/notes/commits` needs an explicit refspec:
  `git config --add remote.origin.push 'refs/notes/*:refs/notes/*'`. stockpilot has an origin,
  so this one is real, and the failure is silent data loss.
- **`Verified:` is self-reported.** The agent writes it. The hook should run the project's test
  command and compare rather than trust the string — a self-reported trailer is not evidence,
  and this is the trust surface.
