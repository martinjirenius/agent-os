#!/usr/bin/env python3
"""The demo path — install agent-os into a fresh repo and prove the gate runs there.

This is the walking skeleton: the product's claim is "one command installs it into a project"
(D-07), so the demo is that install, end to end, against a throwaway git repo. It runs inside
`checks.py` every session, which is what makes the claim a test rather than a sentence.

It also defines reachability: `/prune` and rot.py's dead-code signal treat code unreachable
from this path as provably dead, so anything the demo does not touch is a candidate for
deletion rather than a mystery.

    tools/demo.py            # run it; exit 1 if the installed project's gate does not pass
    tools/demo.py --verbose  # show the installed project's full check table
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent


def run(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def demo(verbose: bool = False) -> int:
    with tempfile.TemporaryDirectory() as d:
        project = Path(d) / "fresh-project"
        project.mkdir()
        run("git", "init", "-q", ".", cwd=project)

        init = run(sys.executable, str(TOOLS / "init.py"), ".", cwd=project)
        if init.returncode != 0:
            print("FAIL: agent-os init did not succeed\n" + init.stdout + init.stderr)
            return 1

        again = run(sys.executable, str(TOOLS / "init.py"), ".", cwd=project)
        if again.returncode != 0 or "skipped" not in again.stdout:
            print("FAIL: init is not idempotent — a second run must skip, not redo\n"
                  + again.stdout + again.stderr)
            return 1

        # What /dev does first: start tracking depth. Before this step existed the demo went
        # straight from install to gate, so it modelled a session that never began — and the
        # gate passed, which is how the excursion stack shipped and never once ran.
        started = run(sys.executable, str(TOOLS / "stack.py"), "start",
                       "--session", "demo-session", cwd=project)
        if started.returncode != 0:
            print("FAIL: could not start the session stack\n" + started.stdout + started.stderr)
            return 1

        # The point of the whole deliverable: the REAL tools, not copies, run against the
        # installed project purely by standing in it.
        checks = run(sys.executable, str(TOOLS / "checks.py"), cwd=project)
        if verbose:
            print(checks.stdout)
        if checks.returncode != 0:
            print("FAIL: the installed project's gate does not pass\n"
                  + checks.stdout + checks.stderr)
            return 1

        copied = [p.name for p in project.rglob("*.py")]
        if copied:
            print(f"FAIL: init copied tools into the project ({copied}) — skills and tools "
                  "are referenced, never copied, or they fork and drift")
            return 1

        print("demo: init into a fresh repo, idempotent on rerun, gate passes there, "
              "zero tools copied")
        return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--selftest", action="store_true",
                   help="the demo IS the test; --selftest is an alias for running it")
    args = p.parse_args(argv)
    rc = demo(verbose=args.verbose)
    if args.selftest:
        print(f"{1 - rc}/1 cases pass")
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
