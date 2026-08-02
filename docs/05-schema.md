# 05 — Schemas: doc slots, budgets, tiers

## The closed doc schema

A project may have **exactly** these files in `docs/`. `checks.py` fails on anything else —
that is what stops a project from growing to twenty documents nobody can rank.

| slot | contents | churn |
|---|---|---|
| `00-product.md` | what it is, the demo, acceptance, non-product | rare, Martin ratifies |
| `01-design.md` | the diagnosis and why each decision was made | rare |
| `02-…` … `0N-…` | project-specific canon (formulation, architecture) | as needed, ≤4 slots |
| `handoff.md` | overwritten every `/wrap`, ≤40 lines | every session |

Adding a slot is an **OS-level change**, not a project-level one. New knowledge goes into an
existing slot, a report, or the findings ledger — never a new top-level document.

Everything that used to become a document instead becomes: a **card** (work), a **finding**
(fact), a **decision trailer** (choice), a **skill** (procedure), or a **deletion** (obsolete).

## Card schema

One file per card in `backlog/`, status as a **field**. The backlog holds only the future —
closed cards are deleted in the commit that lands their work and reconstructed with
`git_ledger.py closed`.

```markdown
---
id: B-001
title: one line, the outcome not the activity
status: todo | doing        # doing is capped at 1
serves: D-01                # must exist in project.toml
opened: 2026-08-02
---

Why this is worth doing, then the concrete first move. Short — git keeps the history, so
rewrite the body rather than appending to it.
```

## Skill budget

- Core and standard skills come from the **plugin** — referenced, never copied. Forked skills
  drift; there are already three diverging copies of `/wrap` in the wild.
- A project may add **3 local skills**. A fourth means one dies or it earns promotion.
- **Retirement**: `/prune` deletes skills that have not fired in N sessions. The rule "doing
  something twice earns a skill" has needed a counterpart from the start.
- **Promotion**: anything wanted by two projects moves up into the OS and deduplicates. The
  answer to "we need this here" is usually "then it belongs upstairs."

## Skill roster

**Core** (every project): `/product` `/dev` `/wrap` `/recall` `/supersede` `/prune` `/timetravel`
**Standard** (most): `/report` `/explainer` `/verify-page` `/delegate` `/process-audit`
**Optional**: `/narrate` `/exp`

Project-specific procedures (temporal-splats' `sanity`, `claim-state`, `adopt-piece`) stay
local and are never hoisted.

## Specialization: manifest, not forking

Skills are **generic procedures parameterized by a project manifest**. `/dev` is byte-identical
everywhere and reads `project.toml` for what to run. See `schema/project.toml.example`.

## Tweakability tiers

| tier | what | changed by | frequency |
|---|---|---|---|
| Constitution | axioms, escalation policy, doc schema, caps | Martin, deliberately | ~never |
| OS | generic skills, scripts, lints | agent proposes → all projects | monthly |
| Manifest | commands, caps, deliverables | agent, freely | weekly |
| Project | ≤3 local skills, product definition | agent proposes, Martin ratifies product | occasionally |
| Work | cards, commits, code | agent, autonomous | constantly |

Tweakability rises going down. The constitution is hard to change **on purpose** — that is the
difference between a constitution and a suggestion, and its absence is why CLAUDE.md files grew
rules 7–10 in a single session and never lost any.
