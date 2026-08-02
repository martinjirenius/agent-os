# 00 — Product

## What it is

A Claude Code **plugin** that any of Martin's projects installs to get a working way of
working: the session loop, the git ledger, the lint suite, and the four oversight surfaces.

## The user path

Martin runs one command in a project. From then on:

- He starts sessions with `/dev` and ends them with `/wrap`, and never has to remember what
  the last session did.
- He opens **one page** to see what he is getting, when, what has slipped, and where the agent
  is right now — including how deep down a rabbit hole it is.
- He is asked at most a couple of questions per session, and only about things he actually
  wants control over.
- The repo does not rot: superseded work is deleted rather than maintained, and nothing is
  lost because git has it.

## The demo

```
agent-os init <project>      # install into a project
agent-os board               # render the cross-project page
```

The demo path is `init` on a scratch repo → make a card → land a commit → render the roadmap
and see the card on it. It runs in `checks.py` every session and must be green on `main`.

Until each piece is real it is a **marked stub** — visible in the output as a stub, never a
silent fake.

## Acceptance

The system works when, observably:

1. A fresh session reads `CLAUDE.md` → `WAY-OF-WORKING.md` → `docs/handoff.md` and states the
   correct next action without the previous transcript.
2. A commit that violates the trailer schema is **rejected**, not warned about.
3. Deleting a superseded file is routine, and `/timetravel` gets it back in one command.
4. `rot.py` reports a number that goes **down** over a month of sessions.
5. Martin can answer "when do I get X, and is it slipping?" from one page in under ten seconds.
6. A session's questions to Martin fit the closed escalation list, or a lint complains.

## Non-product

- **Not a team tool.** No multi-user coordination, no permissions, no review workflow. There
  is no team; designing for one is how agile ceremonies got in.
- **Not a project generator.** It does not scaffold app code or pick frameworks.
- **Not a replacement for judgment.** It makes the agent's work *checkable and reversible*; it
  does not make it correct.
- **Not portable beyond Claude Code.** It targets this harness deliberately.
