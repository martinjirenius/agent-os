#!/usr/bin/env python3
"""render.py — HTML primitives shared by every surface renderer: escape, theme, page skeleton.

The only authority for markup escaping and the visual theme (axiom 4). Surface renderers
import from here and build fragments; nobody else writes a `<!doctype>`, a `<style>`, or a
`<script>` tag. Two sibling projects (scoreforge, temporal-splats) each grew their own copy of
this helper set and they have already drifted — that duplication is the reason this is one
module rather than a snippet pasted per renderer.

Everything emitted here is **self-contained**: no CDN, no external font, no fetch. The page
must open from `file://` with the network off, because that is how Martin opens it. The test
asserts this rather than trusting it.

Nothing here is stored (axiom 1) and nothing is deterministic-by-accident: `page()` takes no
clock and no randomness, so identical inputs give identical bytes.
"""
from __future__ import annotations

import html
import re

# Status -> (label, css class). The renderer never invents a colour inline; a state that is
# not in this table is a bug in the model, not something to paper over with a default.
STATE_CLASS: dict[str, str] = {
    "landed": "s-landed",
    "in_progress": "s-doing",
    "frontier": "s-frontier",
    "blocked": "s-blocked",
    "pending": "s-blocked",
}

_CODE_RE = re.compile(r"`([^`]+)`")
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")


def esc(text: str) -> str:
    """HTML-escape, quotes included. Every string that came from a card, a commit message or
    project.toml goes through this — those are author-controlled, but a title containing a
    stray `<` would otherwise silently eat the rest of the page."""
    return html.escape(str(text), quote=True)


def inline(text: str) -> str:
    """Escape first, then re-introduce exactly two markdown inlines: `code` and **bold**.

    Order matters and is the whole point: escaping after substitution would let a card title
    containing markup reach the page as live HTML. The test pins the order."""
    out = esc(text)
    out = _CODE_RE.sub(r"<code>\1</code>", out)
    out = _BOLD_RE.sub(r"<strong>\1</strong>", out)
    return out


def bar_pct(value: float) -> float:
    """Clamp a percentage into [0, 100]. Projections can legitimately go negative on the low
    edge of a confidence band; a bar that renders at -12% silently disappears instead of
    pinning to the left edge, which reads as 'no data' rather than 'very soon'."""
    return max(0.0, min(100.0, float(value)))


CSS = """
:root {
  --bg: #fbfbfa; --fg: #1a1a19; --muted: #6b6b66; --line: #e3e3df;
  --card: #ffffff; --accent: #3a6ea5; --shadow: 0 1px 2px rgba(0,0,0,.06);
  --landed: #3f8f5f; --doing: #c07c2c; --frontier: #3a6ea5; --blocked: #9a9a94;
  --ghost: #d8d8d2;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #16161a; --fg: #e6e6e1; --muted: #9a9a94; --line: #2c2c32;
    --card: #1e1e23; --accent: #7aa8d8; --shadow: none;
    --landed: #5fb381; --doing: #d9a05b; --frontier: #7aa8d8; --blocked: #6b6b72;
    --ghost: #33333a;
  }
}
:root[data-theme="dark"] {
  --bg: #16161a; --fg: #e6e6e1; --muted: #9a9a94; --line: #2c2c32;
  --card: #1e1e23; --accent: #7aa8d8; --shadow: none;
  --landed: #5fb381; --doing: #d9a05b; --frontier: #7aa8d8; --blocked: #6b6b72;
  --ghost: #33333a;
}
:root[data-theme="light"] {
  --bg: #fbfbfa; --fg: #1a1a19; --muted: #6b6b66; --line: #e3e3df;
  --card: #ffffff; --accent: #3a6ea5; --shadow: 0 1px 2px rgba(0,0,0,.06);
  --landed: #3f8f5f; --doing: #c07c2c; --frontier: #3a6ea5; --blocked: #9a9a94;
  --ghost: #d8d8d2;
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 2rem 1.5rem 4rem; background: var(--bg); color: var(--fg);
  font: 15px/1.55 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
}
.wrap { max-width: 60rem; margin: 0 auto; }
h1 { font-size: 1.4rem; margin: 0 0 .25rem; letter-spacing: -.01em; }
h2 { font-size: .8rem; text-transform: uppercase; letter-spacing: .08em;
     color: var(--muted); margin: 2.5rem 0 .75rem; font-weight: 600; }
.sub { color: var(--muted); font-size: .85rem; margin: 0 0 .35rem; }
code { font: 12.5px/1.4 ui-monospace, SFMono-Regular, Menlo, monospace;
       background: color-mix(in srgb, var(--muted) 14%, transparent);
       padding: .1em .35em; border-radius: 3px; }

/* You are here ------------------------------------------------------------ */
.here { background: var(--card); border: 1px solid var(--line); border-left: 3px solid var(--accent);
        border-radius: 6px; padding: .9rem 1.1rem; margin: 1.25rem 0 0; box-shadow: var(--shadow); }
.here dl { display: grid; grid-template-columns: auto 1fr; gap: .3rem 1rem; margin: 0; }
.here dt { color: var(--muted); font-size: .8rem; }
.here dd { margin: 0; font-size: .88rem; }

/* Pipeline ---------------------------------------------------------------- */
.pipe { display: flex; flex-direction: column; gap: .3rem; }
.row { background: var(--card); border: 1px solid var(--line); border-radius: 6px;
       box-shadow: var(--shadow); overflow: hidden; }
.row > summary { display: flex; align-items: center; gap: .75rem; padding: .6rem .9rem;
                 cursor: pointer; list-style: none; }
.row > summary::-webkit-details-marker { display: none; }
.row > summary:hover { background: color-mix(in srgb, var(--accent) 7%, transparent); }
.row[open] > summary { border-bottom: 1px solid var(--line); }
.chev { color: var(--muted); font-size: .7rem; width: .7rem; flex: none;
        transition: transform .12s ease; }
.row[open] .chev { transform: rotate(90deg); }
.did { font: 600 12px ui-monospace, monospace; color: var(--muted); flex: none; }
.dtitle { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pill { font-size: .68rem; text-transform: uppercase; letter-spacing: .06em; font-weight: 600;
        padding: .16em .5em; border-radius: 100px; flex: none; color: #fff; }
.s-landed  { background: var(--landed); }
.s-doing   { background: var(--doing); }
.s-frontier{ background: var(--frontier); }
.s-blocked { background: var(--blocked); }
.here-tag { background: var(--accent); }

/* Bars -------------------------------------------------------------------- */
.track { position: relative; height: 8px; background: color-mix(in srgb, var(--muted) 16%, transparent);
         border-radius: 100px; width: 11rem; flex: none; overflow: hidden; }
.fill { position: absolute; top: 0; bottom: 0; border-radius: 100px; background: var(--frontier); }
.fill.now { background: var(--doing); }
.gfill { position: absolute; top: 0; bottom: 0; border-radius: 100px; background: var(--ghost); }
.band { position: absolute; top: 0; bottom: 0; border-radius: 100px;
        background: color-mix(in srgb, var(--frontier) 28%, transparent); }

/* Detail (zoom 2 + 3) ------------------------------------------------------ */
.detail { padding: .8rem .9rem 1rem 2.4rem; font-size: .87rem; }
.detail .kv { color: var(--muted); }
.detail ul { margin: .35rem 0 .75rem; padding-left: 1.1rem; }
.detail li { margin: .15rem 0; }
.empty { color: var(--muted); font-style: italic; }
.slip { color: var(--doing); font-weight: 600; }

/* Inbox ------------------------------------------------------------------- */
.item { background: var(--card); border: 1px solid var(--line); border-radius: 6px;
        padding: .65rem .9rem; margin-bottom: .35rem; box-shadow: var(--shadow); }
.item.q { border-left: 3px solid var(--doing); }
.meta { color: var(--muted); font-size: .78rem; margin-top: .3rem; }
.foot { color: var(--muted); font-size: .78rem; margin-top: 3rem;
        border-top: 1px solid var(--line); padding-top: .8rem; }
.scroll { overflow-x: auto; }
@media (max-width: 34rem) { .track { display: none; } }
"""

# The only JS on the page. Three-zoom-level drilling is <details>/<summary>, which needs no
# script at all; this exists solely for the theme toggle and expand-all, so a browser with JS
# off still gets every level by clicking. Progressive enhancement is not decoration here — it
# is what keeps the page readable when it is opened from a file:// URL years from now.
JS = """
(function () {
  var root = document.documentElement;
  var btn = document.getElementById('theme');
  if (btn) {
    btn.addEventListener('click', function () {
      var dark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      var cur = root.getAttribute('data-theme') || (dark ? 'dark' : 'light');
      root.setAttribute('data-theme', cur === 'dark' ? 'light' : 'dark');
    });
  }
  var all = document.getElementById('expand');
  if (all) {
    all.addEventListener('click', function () {
      var rows = document.querySelectorAll('details.row');
      var anyClosed = Array.prototype.some.call(rows, function (r) { return !r.open; });
      Array.prototype.forEach.call(rows, function (r) { r.open = anyClosed; });
    });
  }
})();
"""


def page(title: str, body: str) -> str:
    """Wrap a body fragment in the one page skeleton. Deterministic: no clock, no randomness.

    A caller wanting a generated-at stamp passes it in the body, so the untestable part stays
    the caller's problem and this stays byte-identical for identical inputs."""
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{esc(title)}</title>\n"
        f"<style>{CSS}</style>\n"
        "</head>\n<body>\n"
        f'<div class="wrap">\n{body}\n</div>\n'
        f"<script>{JS}</script>\n"
        "</body>\n</html>\n"
    )
