# 04 — Surfaces

All four are **generated** into `out/` and gitignored. They are renderings of the ledger, never
sources of truth.

## 1. Product

`docs/00-product.md` plus the running demo. A **walking skeleton from day one**: the demo path
exists before the features do, stubs are visibly marked as stubs, and `checks.py` runs the demo
every session.

Two payoffs beyond "you can see it work": code unreachable from the demo path is **provably**
dead, so `/prune` deletes it without a judgment call; and a stub that has been a stub for
fifteen sessions is visible rot.

## 2. Roadmap

One page, three zoom levels.

**Level 1 — the pipeline.** Deliverables as a DAG flowing left to right over time.

- **Past is measured**, not claimed: first commit touching a deliverable → the commit that
  closed it, from `Serves:` trailers.
- **Future is projected from measured velocity** (cards closed per session), with a confidence
  band that widens with distance. No hand-entered dates — an agent's duration estimate is
  fiction, but its throughput is data.
- **Ghost bars** show where each date used to be. **Slip is the headline**: a deliverable that
  has moved right five sessions running is the most valuable signal on the page, and no status
  report would ever tell you.
- **"You are here"** — current deliverable, current card, branch, uncommitted files, minutes
  since last commit, **and current depth**. Being on D-03 but three levels down for forty
  calls is exactly the thing worth seeing.

**Level 2 — the frontier.** Click a deliverable: its cards, current WIP, recent closures.

**Level 3 — the evidence.** Click a card: its commits, tests, report, experiment.

Martin lives at level 1 and drills only when something looks wrong.

## 3. Dive profile

X is tool calls, Y is depth. The agent's path descends and surfaces.

```
depth 0  ──┐              ┌───┐                    ┌──────
depth 1    └──┐        ┌──┘   └──┐            ┌────┘
depth 2       └──┐  ┌──┘         └──┐    ┌────┘
depth 3          └──┘   (abandoned)   └────┘
              ↑                     ↑
         healthy dive          rabbit hole
```

Read at a glance: frequent surfacing is healthy; a long flat run at depth 3 is a rabbit hole;
never returning to 0 means lost; **a session that never surfaced above depth 2 did not advance
its deliverable**, whatever the commit log claims.

Yields a metric — *percentage of session at depth ≤ 1* — used both as a health score on the
roadmap and as a lint threshold. Aggregate view is a **flame graph**: "60% of this session's
calls were inside one excursion that was abandoned" is a sentence currently impossible to
discover.

## 4. Decision inbox

`Chose:` and `Question:` trailers, newest first, with the commit each belongs to.

- `Chose:` items are **already done**. Silence ratifies; objection is `git revert`.
- `Question:` items are the closed escalation list only.

The point is that nothing waits silently and nothing blocks. If this list is long, that is
itself the signal — more than two escalations in a session trips `/process-audit`.

## 5. Cross-project board

`~/projects/index.html` — every project's next action, current deliverable, blocker, open
branches, and rot score, on one page.

Martin has five projects and currently zero views across them. Highest-value new surface in
the design, and cheapest: it is a loop over each project's ledger.
