#!/usr/bin/env python3
"""Git notes helpers — session dive profile and hindsight annotation on commits.

Bridges the granularity gap docs/02-git-model.md describes: excursion depth changes many
times per session (too fine for a trailer), and hindsight corrects a commit made sessions ago
(too displaced for a trailer). Both live on `refs/notes/commits`, a ref separate from the
commits themselves, so nothing here is destructive to history.

    tools/git_notes.py add-profile [--commit HEAD] [--stack-path .agent/stack.json] [--force]
    tools/git_notes.py annotate (--sha SHA | --card ID | --serves ID) -m "message" [--force]
    tools/git_notes.py configure-push
    tools/git_notes.py --selftest

## The `.agent/stack.json` schema this reads (live tier; D-05 owns writing it)

    {
      "session": "2026-08-02-a",
      "frames": [
        {
          "depth": 1,
          "question": "why does X fail under load",
          "unblocks": "confirms D-03 can proceed without a rewrite",
          "opened": "2026-08-02T14:03:00Z",
          "closed": "2026-08-02T14:20:00Z",
          "outcome": "answered: stale cache, filed as B-011"
        }
      ]
    }

`add-profile` copies this JSON verbatim onto the note. That is deliberate: docs/02's "two
sources, one renderer" only holds if the renderer's input shape is identical whether it reads
`.agent/stack.json` live or a historical note via `git notes show`. Anything that transforms
the shape on the way into the note would need a second reader for history — a second renderer
is the failure mode this format avoids. `closed`/`outcome` are `null` for a frame still open
when the profile is flushed; a renderer treats that as "unresolved at session end".
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from git_ledger import Commit, load, match_trailer, git_out as ledger_git

NOTES_REF = "refs/notes/commits"
DEFAULT_STACK_PATH = ".agent/stack.json"
REQUIRED_FRAME_KEYS = {"depth", "question", "unblocks", "opened", "closed", "outcome"}


def resolve_commit_or_die(rev: str) -> str:
    """Resolve <rev> to a commit that EXISTS in the repo we are standing in.

    Plain `git rev-parse <40-hex>` echoes the input straight back without checking that the
    object exists, so a sha belonging to a different repository resolved "successfully" and
    a note was attached to it — polluting this repo's refs/notes with an annotation on a
    commit it does not contain. `--verify <rev>^{commit}` is what actually checks.
    """
    r = subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}"],
                       capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        raise SystemExit(
            f"{rev!r} is not a commit in this repository — notes attach to commits that exist "
            f"here. Check you are in the right repo (`git rev-parse --show-toplevel`) and that "
            f"the sha is one of its commits."
        )
    return r.stdout.strip()


def _note_exists(sha: str) -> bool:
    r = subprocess.run(
        ["git", "notes", "--ref", NOTES_REF, "show", sha],
        capture_output=True, text=True,
    )
    return r.returncode == 0


def load_stack(path: Path) -> dict:
    """Read and validate a stack.json payload. Raises SystemExit with a fix on any defect."""
    if not path.exists():
        raise SystemExit(
            f"{path} not found — the excursion stack is written live during a session "
            f"(docs/02-git-model.md, 'live' tier) and is gitignored, so it only exists mid-"
            f"session. Run a session that pushes/pops the stack first, or pass --stack-path "
            f"to point at a fixture."
        )
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise SystemExit(f"{path} is not valid JSON ({e}) — fix the file or regenerate it.")

    if "session" not in data or "frames" not in data:
        raise SystemExit(
            f"{path} is missing 'session' or 'frames' — schema is "
            f'{{"session": "<id>", "frames": [...]}}; see the module docstring in '
            f"tools/git_notes.py for the full shape."
        )
    for i, frame in enumerate(data["frames"]):
        missing = REQUIRED_FRAME_KEYS - frame.keys()
        if missing:
            raise SystemExit(
                f"{path} frame {i} is missing {sorted(missing)} — every frame needs "
                f"{sorted(REQUIRED_FRAME_KEYS)}."
            )
    return data


def cmd_add_profile(args: argparse.Namespace) -> int:
    stack = load_stack(Path(args.stack_path))
    if args.session and stack["session"] != args.session:
        raise SystemExit(
            f"--session {args.session!r} does not match {args.stack_path}'s session "
            f"{stack['session']!r} — pass the matching session id or omit --session."
        )

    sha = resolve_commit_or_die(args.commit)
    payload = json.dumps(stack, indent=2, sort_keys=True)

    if _note_exists(sha) and not args.force:
        raise SystemExit(
            f"commit {sha[:9]} already has a note — pass --force to overwrite the session "
            f"profile, or check `git log --show-notes -1 {sha[:9]}` if this looks like a "
            f"duplicate /wrap."
        )

    cmd = ["notes", "--ref", NOTES_REF, "add"]
    if _note_exists(sha):
        cmd.append("-f")
    cmd += ["-m", payload, sha]
    ledger_git(*cmd)
    print(f"profile for session {stack['session']} written to {sha[:9]}")

    if args.clear:
        # The flush is a MOVE, not a copy: the live tier exists to become the note. Leaving
        # the file behind means the next /dev finds a stack belonging to a finished session
        # and refuses to start. Only reached once the note is written, so a refused or failed
        # flush never deletes the only copy of the profile.
        Path(args.stack_path).unlink()
        print(f"cleared {args.stack_path} — the profile now lives on the note")
    return 0


def _resolve_commit(args: argparse.Namespace) -> str:
    """Resolve the annotate target: a raw --sha, or a ledger lookup by --card/--serves."""
    if args.sha:
        return resolve_commit_or_die(args.sha)

    if not (args.card or args.serves):
        raise SystemExit(
            "annotate needs a target: --sha <sha>, --card <id> or --serves <id> — the agent "
            "rarely knows the sha, so --card/--serves resolve it through the ledger."
        )

    commits: list[Commit] = load()
    if args.card:
        commits = [c for c in commits if match_trailer(c, "Card", args.card)]
    if args.serves:
        commits = [c for c in commits if match_trailer(c, "Serves", args.serves)]

    if not commits:
        raise SystemExit(
            f"no commit matches card={args.card!r} serves={args.serves!r} — run "
            f"`tools/git_ledger.py query --card {args.card or ''} --serves {args.serves or ''}` "
            f"to find the right id."
        )
    if len(commits) > 1 and not args.latest:
        listing = "\n".join(f"  {c.sha[:9]}  {c.date}  {c.subject}" for c in commits)
        raise SystemExit(
            f"{len(commits)} commits match — pass --sha <sha> to pick one, or --latest for "
            f"the most recent:\n{listing}"
        )
    return commits[0].sha


def cmd_annotate(args: argparse.Namespace) -> int:
    sha = _resolve_commit(args)
    if _note_exists(sha) and args.force:
        ledger_git("notes", "--ref", NOTES_REF, "add", "-f", "-m", args.message, sha)
    else:
        # append is the safe default: a raw `notes add` fails on an existing note, and
        # hindsight commonly stacks (a second correction on a commit already annotated)
        # so refusing outright would just push everyone to --force out of habit. append
        # never destroys; --force is the explicit, deliberate override to replace instead.
        ledger_git("notes", "--ref", NOTES_REF, "append", "-m", args.message, sha)
    print(f"annotated {sha[:9]}")
    return 0


def resolve_remote(remotes: list[str], requested: str | None) -> str:
    """Pick which remote gets the notes refspec. Never guesses between several."""
    if not remotes:
        raise SystemExit(
            "no remote configured — notes on refs/notes/* are not covered by a plain "
            "`git push` even when one exists, and with no remote at all there is nothing to "
            "wire up. Add one first: `git remote add origin <url>`, then rerun "
            "`tools/git_notes.py configure-push`."
        )
    if requested:
        if requested not in remotes:
            raise SystemExit(
                f"no remote named {requested!r} — this repo has {remotes}. Rerun with "
                f"`--remote {remotes[0]}`."
            )
        return requested
    if "origin" in remotes:
        return "origin"
    if len(remotes) == 1:
        return remotes[0]
    raise SystemExit(
        f"several remotes and none named 'origin' ({remotes}) — configuring the wrong one "
        f"loses notes silently, so pick explicitly: `tools/git_notes.py configure-push "
        f"--remote {remotes[0]}`."
    )


def cmd_configure_push(args: argparse.Namespace) -> int:
    remote = resolve_remote(ledger_git("remote").split(), args.remote)
    key = f"remote.{remote}.push"
    refspec = "refs/notes/*:refs/notes/*"

    existing = subprocess.run(
        ["git", "config", "--get-all", key], capture_output=True, text=True
    ).stdout.split()
    if refspec in existing:
        print(f"already configured: {key} = {refspec}")
        return 0

    ledger_git("config", "--add", key, refspec)
    print(f"configured: refs/notes/* now pushes to {remote} with a plain `git push`")
    return 0


def _selftest() -> int:
    import tempfile

    cases = 0
    cases += 1  # 1: valid stack round-trips
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "stack.json"
        payload = {
            "session": "s1",
            "frames": [{
                "depth": 1, "question": "q", "unblocks": "u",
                "opened": "t0", "closed": "t1", "outcome": "answered",
            }],
        }
        p.write_text(json.dumps(payload))
        assert load_stack(p) == payload

    cases += 1  # 2: missing file states the fix
    with tempfile.TemporaryDirectory() as dm:
        try:
            load_stack(Path(dm) / "absent.json")
            raise AssertionError("expected SystemExit")
        except SystemExit as e:
            assert "not found" in str(e), e

    cases += 1  # 3: missing frame key rejected
    with tempfile.TemporaryDirectory() as d2:
        p2 = Path(d2) / "stack.json"
        p2.write_text(json.dumps({"session": "s1", "frames": [{"depth": 1}]}))
        try:
            load_stack(p2)
            raise AssertionError("expected SystemExit")
        except SystemExit as e:
            assert "missing" in str(e), e

    cases += 1  # 4: ledger resolution picks the matching commit among fixtures
    fixture = [
        Commit("aaa", "2026-08-01", "one", {"Serves": ["D-01"]}),
        Commit("bbb", "2026-08-02", "two", {"Card": ["B-002"], "Serves": ["D-01"]}),
    ]
    matches = [c for c in fixture if match_trailer(c, "Card", "B-002")]
    assert len(matches) == 1 and matches[0].sha == "bbb"

    cases += 1  # 5: never guess a remote — silent notes loss is the failure mode
    assert resolve_remote(["origin", "fork"], None) == "origin"
    assert resolve_remote(["fork"], None) == "fork"
    for bad, want in ((["a", "b"], "pick explicitly"), ([], "no remote configured")):
        try:
            resolve_remote(bad, None)
            raise AssertionError("expected SystemExit")
        except SystemExit as e:
            assert want in str(e), e

    print(f"{cases}/{cases} cases pass")
    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--selftest", action="store_true")
    sub = p.add_subparsers(dest="cmd")

    ap = sub.add_parser("add-profile"); ap.set_defaults(fn=cmd_add_profile)
    ap.add_argument("--commit", default="HEAD")
    ap.add_argument("--stack-path", default=DEFAULT_STACK_PATH)
    ap.add_argument("--session", default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--clear", action="store_true",
                    help="delete the live stack once the note is written (what /wrap does)")

    an = sub.add_parser("annotate"); an.set_defaults(fn=cmd_annotate)
    an.add_argument("--sha")
    an.add_argument("--card")
    an.add_argument("--serves")
    an.add_argument("--latest", action="store_true")
    an.add_argument("-m", "--message", required=True)
    an.add_argument("--force", action="store_true")

    cp = sub.add_parser("configure-push"); cp.set_defaults(fn=cmd_configure_push)
    cp.add_argument("--remote", default=None)

    args = p.parse_args(argv)
    if args.selftest:
        return _selftest()
    if not getattr(args, "fn", None):
        p.print_help()
        return 2
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
