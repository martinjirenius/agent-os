# 01 — Design: the diagnosis and why each decision was made

The rules exist because of measurements. A rule with a reason gets followed; a bare rule gets
rationalized around. This file is the reasons.

## The measured problem

Read-only survey of all five projects, 2026-08-02:

| | files | files ever deleted | del ratio | docs/ | CLAUDE.md |
|---|---|---|---|---|---|
| temporal-splats | 1833 | 30 | 0.02 | 18 | 170 |
| scoreforge | 126 | **0** | 0.05 | 6 | 145 |
| stockpilot | 201 | 22 | 0.26 | **20** | **586** |

**1. Git is a save button, not a memory system.** 586 commits across five projects and
**zero tags, zero notes, zero branches**. Nothing has ever been retrieved from history. The
entire archive capability sat unused, which is why everything had to be kept in the tree.

**2. The rot is in the process layer, not the source code.** This corrected the initial
hypothesis. Compat markers (`_v2`, `legacy`, `deprecated`, back-compat branches) total 11, 0
and 4 across the three main repos — the code is *clean*. The hoarding is elsewhere:

- **Superseded plans kept as documents.** stockpilot's `docs/` holds four phase plans,
  `cleanup-plan.md`, `next-session.md` and two `handoff-*.md`. To a cold agent every one of
  them reads as authoritative, and they contradict each other.
- **Rules that accrete and never retire.** scoreforge's audit session added CLAUDE.md rules
  7–10. Nothing has ever been removed from a CLAUDE.md.

So "the agent always tries to be backwards compatible" is real but one step removed from how
it feels: the agent preserves *superseded intent as documents*, and those documents then issue
contradictory instructions next session. That single mechanism produces all three complaints —
"forgets old documents", "doesn't follow skills", "maintains stuff we overruled".

**3. scoreforge has deleted zero files in 51 commits.** Not one. Entropy is monotonic because
no session is ever graded on shrinkage.

**4. The agent is already inventing the missing schema.** Commit bodies contain organically
grown trailers: `Verified:`, `Next:`, `Adopted:`, `Notebook:`, `Why:`, `Tests-first:`,
`Suite:`, and `Martin: "WHEN WILL I SEE SOME RESULTS? AND I ONLY LOOK IN THE SCENE INSPECTOR."`
It is reaching for structure that does not exist. Formalizing it costs nothing and yields a
database.

**5. Skills are forked, not shared.** `/dev`, `/wrap`, `/recall`, `/report`, `/explainer`,
`/narrate` exist as drifting copies across two repos — the rot problem wearing a different hat,
and the reason skills are parameterized by a manifest rather than copied.

## Why each decision

**Why the axioms are the axioms.** All four were already latent in temporal-splats' best
tooling and just never stated: `knowledge.py` ("nothing is stored; every command re-parses the
sources, so there is no index file to go stale") is axiom 1; `checks.py` ("prose reminders
don't hold — measured: rule 8(b) existed as prose and was not followed") is axiom 2. The
working system had the right instincts; it lacked the statement and the generalization.

**Why deletion needs `/timetravel` to ship with it.** The agent hoards because deleting feels
lossy and irreversible. You cannot instruct fearless deletion without providing a proven undo —
the rule and the retrieval tool are one change, not two. Same for characterization tests: they
are the net that makes deleting an old code path a safe act rather than a brave one.

**Why commits carry the ledger.** One write serves both consumers. The agent introspects on
the same records that render Martin's pipeline, so there is no separate tracking system to fall
out of sync — that would be a second authority (axiom 4).

**Why the `commit-msg` hook rejects rather than warns.** An advisory schema is right for six
sessions and then drifts. A typo'd `Serve:` would silently drop a commit out of the pipeline
forever, and nobody would notice. Load-bearing data needs a gate at write time.

**Why done cards are deleted.** A done card duplicates git history. Keeping it violates axiom 4
and makes the backlog grow without bound. Deleting it means **the backlog contains only the
future** — structurally incapable of accumulating.

**Why there is no icebox.** It is where decisions go to not be made, and unlike a query it is
passively always in view, costing attention forever. The fair objection — "an idea I can't see
is one I'll never act on" — is answered by the tier above: work genuinely intended becomes a
deliverable. Anything not worth a roadmap slot is deleted with a reason. The forced choice is
the point; a third tier is where hoarding hides.

**Why not agile.** Kanban and agile solve *human team* problems: coordination across people,
information hiding, unpredictable individual velocity, morale, long customer feedback loops.
Solo plus a machine has none of them. What survives the filter — WIP limits (for agent context,
not human focus), small batches, working-software-first, retrospectives — is kept. Sprints,
points, ceremonies and the board-as-communication-device are dropped. The better model is a
**build system**: a DAG, and an agent taking unblocked leaves.

**Why escalation is inverted.** Martin's own estimate is that 95% of his answers are "do what
you recommend". A gate that is waved through 95% of the time is not a safety mechanism, it is a
tax — and temporal-splats' approval-stamp apparatus is process built to compensate for a trust
problem that reversibility solves better. Since `git revert` is cheap, decide-and-record
dominates block-and-ask. Reversibility is what licenses the autonomy, and it is the same
property that licenses aggressive deletion — one architectural idea, two payoffs.

**Why the excursion stack.** Everything else here addresses drift *across* sessions. Rabbit
holes are drift *within* one, and they are a call stack that nothing is managing: implicit, no
depth budget, no return discipline, no carry-back of what depth 3 learned. The fix is to make
the stack a file the agent can read, which also makes the dive profile free.

**Why evidence stopped being Martin's homework.** Reports and explainers were built for a good
reason — "if you can't explain it, you don't know it well enough" forces the agent to make its
reasoning checkable. But making Martin the reviewer does not scale past a few sessions. Their
function is to be *checkable*, not read. He spot-checks; the surfaces do the rest.

**Why generated surfaces are gitignored.** Committing them creates a second authority that can
disagree with its source. scoreforge and stockpilot currently commit `roadmap.html` and
`backlog.html`; that changes.
