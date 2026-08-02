#!/usr/bin/env python3
"""render_roadmap.py — the one page: pipeline, slip, you-are-here, decision inbox, as HTML.

Surface 2 of docs/04-surfaces.md, and the thing docs/00-product.md:43 measures the product by:
"Martin can answer 'when do I get X, and is it slipping?' from one page in under ten seconds."
Three zoom levels in one file — the pipeline (level 1), a deliverable's cards and commits
(level 2), a card's evidence (level 3) — drilled with `<details>`, so every level is reachable
with JavaScript switched off.

**This module computes nothing.** Every number on the page comes from roadmap.py
(`compute_statuses`, `project_sessions_out`, `ghost_history`, `detect_slip`, `current_depth`)
and inbox.py (`collect`); a second landed/frontier rule or a second trailer parser here would
be an axiom-4 defect, and the page would be free to disagree with the terminal. If a value
looks wrong, it is wrong in the model, and that is where it gets fixed.

Output is `out/roadmap.html` — gitignored, never a source of truth (axiom 1), regenerated from
git on every run. Self-contained: it opens from `file://` with the network off.

    python3 tools/render_roadmap.py           # write out/roadmap.html
    python3 tools/render_roadmap.py --stdout  # print it instead
"""
from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import backlog  # noqa: E402
import checks  # noqa: E402
import git_ledger  # noqa: E402
import inbox  # noqa: E402
import render  # noqa: E402
import render_dag  # noqa: E402
import roadmap  # noqa: E402

STATE_LABEL: dict[str, str] = {
    "landed": "landed",
    "in_progress": "in progress",
    "frontier": "frontier",
    "blocked": "blocked",
    "pending": "blocked",
}


def _track(fill_pct: float, start_pct: float = 0.0, css: str = "fill") -> str:
    """One bar segment, clamped. Percentages are of the shared sessions-out scale, so bars on
    different rows are comparable — that comparability is the whole point of a pipeline view."""
    left = render.bar_pct(start_pct)
    width = render.bar_pct(fill_pct)
    return f'<span class="{css}" style="left:{left:.1f}%;width:{width:.1f}%"></span>'


def _scale(projections: dict[str, roadmap.Projection]) -> float:
    """Right edge of the shared axis, in sessions out. Driven by the widest confident upper
    bound so no band clips; 1.0 when nothing is projectable, which keeps the axis from
    collapsing to zero width and dividing by it below."""
    highs = [p.high for p in projections.values() if p.high is not None]
    return max(highs) if highs else 1.0


def _bar_for(status: roadmap.Status, proj: roadmap.Projection, ghost: roadmap.Projection | None,
             scale: float) -> str:
    """The row's bar. Landed fills the whole track (it is measured past, not a guess); an
    unlanded deliverable shows its confidence band with the estimate marked inside it; an
    unprojectable one shows an empty track rather than a fabricated position."""
    if status.state in ("landed", "in_progress") and proj.remaining == 0:
        return f'<span class="track">{_track(100.0, 0.0, "fill")}</span>'
    if proj.insufficient or proj.estimate is None:
        return '<span class="track"></span>'
    low = (proj.low or 0.0) / scale * 100
    high = (proj.high or 0.0) / scale * 100
    parts = []
    if ghost and ghost.estimate is not None:
        # Where this used to sit. Slip is the headline, so the old position stays on the page.
        parts.append(_track(2.0, ghost.estimate / scale * 100, "gfill"))
    parts.append(_track(high - low, low, "band"))
    parts.append(_track(2.5, proj.estimate / scale * 100, "fill now"))
    return f'<span class="track">{"".join(parts)}</span>'


def _eta(proj: roadmap.Projection) -> str:
    """Sessions out, never a calendar date — no session cadence has been measured, so a date
    would be fabricated. roadmap.py made this call; the page must not quietly undo it."""
    if proj.remaining == 0:
        return "landed"
    if proj.insufficient:
        return (f"insufficient data ({proj.sessions_observed} session(s); "
                f"need {roadmap.MIN_SESSIONS_FOR_PROJECTION})")
    return f"~{proj.estimate:.1f} sessions out ({proj.low:.1f}–{proj.high:.1f})"


def _cards_for(cards: list, d_id: str) -> list:
    return [c for c in cards if isinstance(c, backlog.Card) and c.serves == d_id]


def _detail(status: roadmap.Status, proj: roadmap.Projection,
            slip: tuple[roadmap.Projection, roadmap.Projection] | None,
            commits: list[git_ledger.Commit], cards: list) -> str:
    """Zoom levels 2 and 3: the deliverable's open cards, and the commits that serve it with
    their card and disposition — the evidence, inline, so drilling never leaves the page."""
    out: list[str] = []
    out.append(f'<p class="kv">depends: {render.esc(", ".join(status.depends) or "nothing")}'
               f' &middot; eta: {render.esc(_eta(proj))}</p>')
    if slip:
        old, new = slip
        out.append(f'<p class="slip">slipped: was ~{old.estimate:.1f} sessions out, '
                   f'now ~{new.estimate:.1f}</p>')
    if status.first_date:
        out.append(f'<p class="kv">measured: {render.esc(status.first_date)} → '
                   f'{render.esc(status.last_date or status.first_date)} across '
                   f'{len(status.sessions)} session(s)</p>')

    open_cards = _cards_for(cards, status.id)
    out.append("<p class=\"kv\">open cards</p>")
    if open_cards:
        out.append("<ul>" + "".join(
            f"<li><code>{render.esc(c.id)}</code> {render.inline(c.title)} "
            f'<span class="kv">({render.esc(c.status)})</span></li>' for c in open_cards
        ) + "</ul>")
    else:
        out.append('<p class="empty">none — nothing open against this deliverable.</p>')

    serving = [c for c in commits if roadmap.exact_serves(c, status.id)]
    out.append('<p class="kv">commits</p>')
    if serving:
        rows = []
        for c in serving:
            card = c.trailers.get("Card", [""])[0]
            disp = c.trailers.get("Disposition", [""])[0]
            tail = " ".join(x for x in (f"[{card}]" if card else "", disp) if x)
            rows.append(f"<li><code>{render.esc(c.sha[:9])}</code> {render.inline(c.subject)}"
                        f' <span class="kv">{render.esc(tail)}</span></li>')
        out.append("<ul>" + "".join(rows) + "</ul>")
    else:
        out.append('<p class="empty">none yet.</p>')
    return "".join(out)


def _row(status: roadmap.Status, proj: roadmap.Projection, ghost: roadmap.Projection | None,
         slip, scale: float, commits: list[git_ledger.Commit], cards: list,
         is_here: bool) -> str:
    cls = render.STATE_CLASS.get(status.state, "s-blocked")
    label = STATE_LABEL.get(status.state, status.state)
    here = '<span class="pill here-tag">you are here</span>' if is_here else ""
    return (
        f'<details class="row" data-row="{render.esc(status.id)}">'
        '<summary>'
        '<span class="chev">&#9656;</span>'
        f'<span class="did">{render.esc(status.id)}</span>'
        f'<span class="dtitle">{render.inline(status.title)}</span>'
        f"{here}"
        f'<span class="pill {cls}">{render.esc(label)}</span>'
        f"{_bar_for(status, proj, ghost, scale)}"
        "</summary>"
        f'<div class="detail">{_detail(status, proj, slip, commits, cards)}</div>'
        "</details>"
    )


def _legend() -> str:
    """Names the four colours once. Without it the map's bands are decoration."""
    swatches = "".join(
        f'<span><i class="dot" style="background:var(--{var})"></i>{label}</span>'
        for var, label in (("landed", "landed"), ("doing", "in progress"),
                           ("frontier", "frontier — unblocked, not started"),
                           ("blocked", "blocked by a dependency"))
    )
    return (f'<p class="legend">{swatches}</p>'
            '<p class="sub">columns are dependency depth; click a node to drill to its row</p>')


def _here_block(statuses: list[roadmap.Status], depth: int, depth_note: str,
                cards: list, warnings: list[str]) -> str:
    """"You are here" — current deliverable, WIP card, depth. docs/04-surfaces.md: "Being on
    D-03 but three levels down for forty calls is exactly the thing worth seeing."""
    current = next((s for s in statuses if s.state == "in_progress"),
                   next((s for s in statuses if s.state == "frontier"), None))
    wip = [c for c in cards if isinstance(c, backlog.Card) and c.status == "doing"]
    rows = [
        ("deliverable", f"{current.id} — {render.inline(current.title)}" if current
         else '<span class="empty">nothing in progress or unblocked</span>'),
        ("wip card", ", ".join(f"<code>{render.esc(c.id)}</code> {render.inline(c.title)}"
                               for c in wip)
         or '<span class="empty">none</span>'),
        ("depth", f"{depth} &middot; {render.esc(depth_note)}"),
    ]
    if warnings:
        rows.append(("warnings", "<br>".join(render.esc(w) for w in warnings)))
    body = "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in rows)
    return f'<div class="here"><dl>{body}</dl></div>'


def _inbox_block(questions: list[inbox.Item], chosen: list[inbox.Item]) -> str:
    """The decision inbox, on the same page. docs/04-surfaces.md: "nothing waits silently and
    nothing blocks." A question living in a separate tool is exactly the silence to avoid."""
    out: list[str] = []
    out.append(f"<h2>Questions — need an answer ({len(questions)})</h2>")
    if questions:
        for q in questions:
            out.append(f'<div class="item q">{render.inline(q.text)}'
                       f'<div class="meta">{render.esc(q.date)} &middot; '
                       f'{render.esc(q.session or "no session")} &middot; '
                       f'<code>{render.esc(q.sha[:9])}</code></div></div>')
    else:
        out.append('<p class="empty">none — nothing is blocked on you.</p>')

    out.append(f"<h2>Decisions — silence ratifies ({len(chosen)})</h2>")
    if chosen:
        for c in chosen:
            out.append(f'<div class="item">{render.inline(c.text)}'
                       f'<div class="meta">{render.esc(c.date)} &middot; '
                       f'{render.esc(c.session or "no session")} &middot; '
                       f'<code>{render.esc(c.sha[:9])}</code> &middot; '
                       f'revert: <code>git revert {render.esc(c.sha[:9])}</code></div></div>')
    else:
        out.append('<p class="empty">none.</p>')
    return "".join(out)


def build(root: Path, now: datetime.datetime | None = None) -> str:
    """The whole page as a string. Deterministic for a given repo state: `now` is injected and
    omitted entirely when absent, so tests compare bytes without pinning a clock."""
    manifest = checks.load_manifest(checks.find_manifest(root))
    deliverables = roadmap.load_deliverables(manifest)
    backlog_dir = root / "backlog"
    with backlog._chdir(root):
        commits = git_ledger.load()
        questions, chosen = inbox.collect()

    if not deliverables:
        body = ("<h1>Roadmap</h1><p class='sub'>no <code>[[deliverables]]</code> declared in "
                "project.toml — nothing to render.</p>")
        return render.page("Roadmap", body)

    statuses = roadmap.compute_statuses(commits, deliverables, backlog_dir)
    cards = backlog.load_cards(backlog_dir)
    warnings = roadmap.card_warnings(backlog_dir)
    depth, depth_note = roadmap.current_depth(root / ".agent" / "stack.json")

    projections = {s.id: roadmap.project_sessions_out(s.id, commits, deliverables, backlog_dir)
                   for s in statuses}
    slips: dict[str, tuple] = {}
    ghosts: dict[str, roadmap.Projection | None] = {}
    for s in statuses:
        history = roadmap.ghost_history(s.id, commits, deliverables, backlog_dir)
        slips[s.id] = roadmap.detect_slip(history)
        confident = [p for _, p in history if not p.insufficient and p.estimate is not None]
        ghosts[s.id] = confident[0] if len(confident) > 1 else None
    scale = _scale(projections)

    here_id = next((s.id for s in statuses if s.state == "in_progress"),
                   next((s.id for s in statuses if s.state == "frontier"), None))
    sessions = roadmap.distinct_sessions(commits)

    parts = [
        "<h1>Roadmap</h1>",
        f'<p class="sub">{render.esc(manifest.get("project", {}).get("name", root.name))} '
        f"&middot; {len(sessions)} session(s) observed &middot; generated from git trailers, "
        "never a source of truth</p>",
        '<p class="sub"><button id="theme">theme</button> '
        '<button id="expand">expand all</button></p>',
        _here_block(statuses, depth, depth_note, cards, warnings),
        "<h2>Map</h2>",
        render_dag.build(statuses, here_id),
        _legend(),
        "<h2>Pipeline</h2>",
        '<div class="pipe">',
    ]
    for s in statuses:
        parts.append(_row(s, projections[s.id], ghosts[s.id], slips[s.id], scale,
                          commits, cards, s.id == here_id))
    parts.append("</div>")
    parts.append(_inbox_block(questions, chosen))
    stamp = f" &middot; {now:%Y-%m-%d %H:%M}" if now else ""
    parts.append(f'<p class="foot">out/roadmap.html — regenerate with '
                 f"<code>python3 tools/render_roadmap.py</code>{stamp}</p>")
    return render.page(f"Roadmap — {manifest.get('project', {}).get('name', root.name)}",
                       "".join(parts))


def write(root: Path, now: datetime.datetime | None = None) -> Path:
    """Render to out/roadmap.html, creating out/ if needed. Returns the path written."""
    out_dir = root / "out"
    out_dir.mkdir(exist_ok=True)
    path = out_dir / "roadmap.html"
    path.write_text(build(root, now), encoding="utf-8")
    return path


def cmd(args: argparse.Namespace) -> int:
    root = backlog.project_root(Path(args.root) if args.root else Path.cwd())
    now = None if args.no_stamp else datetime.datetime.now()
    if args.stdout:
        print(build(root, now))
        return 0
    path = write(root, now)
    print(f"wrote {path}")
    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--root", default=None, help="project root (default: cwd, walking up)")
    p.add_argument("--stdout", action="store_true", help="print the page instead of writing it")
    p.add_argument("--no-stamp", action="store_true", help="omit the generated-at footer stamp")
    return cmd(p.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
