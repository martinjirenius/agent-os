# Handoff

Overwritten at the end of every session by `/wrap`. History: `git log -- docs/handoff.md`.

## Last session (2026-08-02, session `2026-08-02-c`)

- B-011: out/roadmap.html — the one page Martin opens [B-011, done]
- B-012: the map — deliverables as a DAG, not a list of rows [B-012, done]
- B-013: depth was never measured — wire the excursion stack into the loop [B-013, done]

## Repo state

Branch `main`, clean. 17 tools, 3 skills, 213 tests, gate 12/12, rot 0.

## Next action

Cross-project `~/projects/index.html` plus the dive-profile HTML — the two pieces of D-06 still unbuilt while it reads `landed`. The board needs no new data; the dive profile has a real note to render as of this session.

## Open questions / pending decisions

- Chose: the view imports the model and computes nothing — a second landed/frontier or trailer parse would be an axiom-4 defect
- Chose: sessions-out on a shared axis, not calendar dates — roadmap.py already refused to fabricate cadence and the page must not undo that
- Chose: inbox embedded in roadmap.html rather than its own page — "one page" is the product criterion
- Chose: dive flame graph and the cross-project board deferred to their own cards, not bundled into this landing
- Chose: inline SVG over a chart library — self-contained, scales, every node is a real DOM element, and it renders with JS off
- Chose: rows packed in project.toml declaration order rather than reordered for prettier edges — the author's reading order outranks cosmetics
- Chose: edge keys use `..` not `->` — `>` escapes to `&gt;` in an attribute and makes edges un-greppable in the generated page
- Chose: FAIL not INFO for untracked depth — the soft option keeps the silent lie, and the whole defect is that absence read as success
- Chose: demo.py and the init/checks fixtures now start a stack — a fixture that omits it asserts an untracked session is healthy, which is the bug
- Chose: /dev refuses on a stale stack rather than overwriting — a surviving stack means the previous session's profile was never flushed, and --force would discard the only copy

## Gotchas

- `checks.py` is 492/500 lines. The next substantive edit trips the cap — split first, characterization test first.
- **Every `Depth:` trailer before `199e030` is a claim, not a measurement.** The uniform `Depth: 1` is a typing habit. Real data starts with this session's note.
- **Absence-read-as-success has now recurred four times**, most recently inside the lint meant to catch depth problems. The three prior fixes were all local, which is why it came back. A standing lint for the pattern is a work-model call, not a session one.
- **D-06 reads `landed` while two of its four surfaces are unbuilt.** The same false-completion logic marked D-03 landed with four skills missing: an empty backlog reads as completeness because done cards are deleted.
- The plugin is still not registered in `~/.claude`, so `/dev` and `/wrap` are run by hand every session.

