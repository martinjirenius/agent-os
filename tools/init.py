#!/usr/bin/env python3
"""agent-os init — install project.toml, the commit-msg gate and the directory skeleton into
a project; skills and tools stay in the plugin and are never copied (docs/05-schema.md
"Specialization: manifest, not forking" — a copied skill is a forked skill, and forked skills
drift).

Everything a project needs from agent-os beyond this one-time install is reached, not copied:
`tools/*.py` scripts are invoked by their path inside the agent-os checkout / plugin
installation with the target project as `cwd` (`find_manifest` in checks.py walks upward from
`cwd` for `project.toml` — it does not need to live next to the tools that read it), and
skills are the plugin payload declared once in `.claude-plugin/plugin.json`. Running this
script does not require agent-os's own tools/ to be copied anywhere; it only touches the
target project.

    tools/init.py <path>       # install into <path>, an existing git repository
    tools/init.py --selftest
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

# Sibling of tools/ in whatever checkout this script runs from (agent-os repo or a plugin
# install) — never hardcoded to a particular absolute path, so this keeps working wherever
# the plugin ends up installed.
SOURCE_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_TEMPLATE = SOURCE_ROOT / "schema" / "project.toml.example"
HOOK_SOURCE = SOURCE_ROOT / ".githooks" / "commit-msg"

GITIGNORE_LINES = ["out/", ".agent/", "__pycache__/", "*.pyc"]

_KEY_VAL_RE = re.compile(r'^(?P<indent>\s*)(?P<key>[\w-]+)(?P<sep>\s*=\s*)"[^"]*"(?P<rest>.*)$')


@dataclass
class Step:
    """One unit of init's work. `status` is "created", "skipped" (already in the desired
    state) or "error" (init could not proceed and did nothing further)."""
    name: str
    status: str
    detail: str = ""


def exit_code(steps: list[Step]) -> int:
    return 1 if any(s.status == "error" for s in steps) else 0


def is_git_repo(target: Path) -> bool:
    r = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"],
                        cwd=target, capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip() == "true"


def render_manifest(project_name: str) -> str:
    """schema/project.toml.example, specialized for a fresh project.

    Two changes beyond the project name, both `Chose:`-worthy and recorded in the card
    report rather than silently baked in:

    - `[commands]` values are blanked to "". checks.py renders an empty command as a
      declared STUB, not a failure (tools/checks.py docstring); the template's own commands
      (`pytest`, a `temporal_splats` demo module, ...) belong to temporal-splats, not to
      whatever project is being initialized, and copying them verbatim would make every
      fresh project's checks.py lie about having a working test/lint/demo command.
    - `[[deliverables]]` entries are dropped. The template's D-01/D-02 describe
      temporal-splats' own plan; carrying them into every new project's manifest would seed
      a DAG that describes nothing real. checks.py and backlog.py both treat zero
      deliverables and zero cards as a clean PASS (docs/05-schema.md), so this is a valid
      empty starting state, not a hole.
    """
    lines = MANIFEST_TEMPLATE.read_text().splitlines()
    out: list[str] = []
    section = ""
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[["):
            section = "deliverables"
            continue
        if stripped.startswith("[") and not stripped.startswith("[["):
            section = stripped.strip("[]")
        if section == "deliverables":
            continue

        m = _KEY_VAL_RE.match(line)
        if section == "project" and m and m.group("key") == "name":
            out.append(f'{m.group("indent")}{m.group("key")}{m.group("sep")}'
                       f'"{project_name}"{m.group("rest")}')
            continue
        if section == "commands" and m:
            out.append(f'{m.group("indent")}{m.group("key")}{m.group("sep")}""{m.group("rest")}')
            continue
        out.append(line)

    text = "\n".join(out).rstrip("\n")
    text += (
        "\n\n# No deliverables yet — add [[deliverables]] entries as work is planned\n"
        "# (schema/project.toml.example shows the shape).\n"
    )
    return text


def install_manifest(target: Path) -> Step:
    dest = target / "project.toml"
    if dest.exists():
        return Step("project.toml", "skipped",
                     f"{dest} already exists — never overwritten; edit it directly, or "
                     "remove it first if you want it regenerated from the template")
    dest.write_text(render_manifest(target.name))
    return Step("project.toml", "created",
                f"written from {MANIFEST_TEMPLATE} — commands stubbed, deliverables cleared")


def install_hook(target: Path) -> list[Step]:
    """The commit-msg gate must travel with the project (CLAUDE.md 'Session protocol'):
    trailers are load-bearing data, so the gate that enforces their schema at write time is
    part of what `init` installs, not something a project opts into later."""
    steps: list[Step] = []
    hooks_dir = target / ".githooks"
    dest_hook = hooks_dir / "commit-msg"
    if dest_hook.exists():
        steps.append(Step("commit-msg hook file", "skipped",
                          f"{dest_hook} already exists — left untouched"))
    else:
        hooks_dir.mkdir(exist_ok=True)
        shutil.copy2(HOOK_SOURCE, dest_hook)
        dest_hook.chmod(dest_hook.stat().st_mode | 0o111)
        steps.append(Step("commit-msg hook file", "created", f"copied from {HOOK_SOURCE}"))

    current = subprocess.run(["git", "config", "--get", "core.hooksPath"],
                              cwd=target, capture_output=True, text=True).stdout.strip()
    if current == ".githooks":
        steps.append(Step("core.hooksPath", "skipped", "already set to .githooks"))
    elif current:
        steps.append(Step("core.hooksPath", "skipped",
                          f"already set to '{current}' — not overriding; set it to "
                          ".githooks manually to turn on the agent-os gate"))
    else:
        subprocess.run(["git", "config", "core.hooksPath", ".githooks"], cwd=target, check=True)
        steps.append(Step("core.hooksPath", "created", "set to .githooks"))
    return steps


def create_skeleton(target: Path) -> list[Step]:
    """The directories the tools expect (docs/05-schema.md doc slots, backlog/ cards) plus
    out/ ignored — never skills/, which stays in the plugin (docs/05-schema.md 'referenced,
    never copied')."""
    steps: list[Step] = []
    for name in ("docs", "backlog"):
        d = target / name
        if d.exists():
            steps.append(Step(f"{name}/", "skipped", "already exists"))
        else:
            d.mkdir()
            steps.append(Step(f"{name}/", "created", ""))

    gitignore = target / ".gitignore"
    existing = gitignore.read_text().splitlines() if gitignore.exists() else []
    missing = [w for w in GITIGNORE_LINES if w not in existing]
    if not missing:
        steps.append(Step(".gitignore", "skipped", "out/ and friends already ignored"))
    else:
        with gitignore.open("a") as f:
            if existing:
                f.write("\n")
            f.write("\n".join(missing) + "\n")
        steps.append(Step(".gitignore", "created", f"added: {', '.join(missing)}"))
    return steps


def run_init(target: Path) -> list[Step]:
    target = Path(target).resolve()
    if not target.exists():
        return [Step("target directory", "error",
                     f"{target} does not exist — create it first (mkdir -p {target})")]
    if not is_git_repo(target):
        return [Step("git repository", "error",
                     f"{target} is not a git repository — run `git init` in it first, then "
                     "re-run agent-os init")]
    steps = [Step("git repository", "skipped", "already a git repo")]
    steps.append(install_manifest(target))
    steps.extend(install_hook(target))
    steps.extend(create_skeleton(target))
    return steps


def render(steps: list[Step]) -> None:
    for s in steps:
        print(f"{s.status:<8} {s.name}")
        for line in s.detail.splitlines():
            print(f"         {line}")


def _selftest() -> int:
    cases = 0
    failures = 0

    def check(name: str, cond: bool, detail: object = "") -> None:
        nonlocal cases, failures
        cases += 1
        if not cond:
            print(f"FAIL {name}: {detail}")
            failures += 1

    def make_git_repo(tmp: Path, name: str = "project") -> Path:
        repo = tmp / name
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=repo, check=True)
        return repo

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        target = tmp / "not_a_repo"
        target.mkdir()
        steps = run_init(target)
        check("refuses a non-git directory", exit_code(steps) == 1)
        check("refusal names the fix", any("git init" in s.detail for s in steps), steps)

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        steps = run_init(tmp / "nope")
        check("refuses a missing directory", exit_code(steps) == 1)

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        repo = make_git_repo(tmp)
        steps = run_init(repo)
        check("clean install exits 0", exit_code(steps) == 0, steps)
        text = (repo / "project.toml").read_text()
        check("manifest carries the target's own name", f'name = "{repo.name}"' in text, text)
        check("manifest drops the template's own project name",
              "temporal-splats" not in text, text)
        check("manifest stubs commands instead of copying pytest et al.",
              "pytest" not in text and 'test  = ""' in text, text)
        check("manifest drops the template's deliverables",
              "temporal_splats" not in text and "D-01" not in text, text)
        hook = repo / ".githooks" / "commit-msg"
        check("hook file installed", hook.exists())
        check("hook file matches the source", hook.read_text() == HOOK_SOURCE.read_text())
        cfg = subprocess.run(["git", "config", "--get", "core.hooksPath"],
                              cwd=repo, capture_output=True, text=True).stdout.strip()
        check("core.hooksPath set to .githooks", cfg == ".githooks")
        check("docs/ created", (repo / "docs").is_dir())
        check("backlog/ created", (repo / "backlog").is_dir())
        check("out/ gitignored", "out/" in (repo / ".gitignore").read_text())
        check("skills/ never copied", not (repo / "skills").exists())
        check("no .claude/skills copied either", not (repo / ".claude").exists())

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        repo = make_git_repo(tmp)
        (repo / "project.toml").write_text("# hand-written\n")
        steps = run_init(repo)
        manifest_step = next(s for s in steps if s.name == "project.toml")
        check("existing manifest is never overwritten", manifest_step.status == "skipped")
        check("existing manifest content untouched",
              (repo / "project.toml").read_text() == "# hand-written\n")

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        repo = make_git_repo(tmp)
        subprocess.run(["git", "config", "core.hooksPath", "custom"], cwd=repo, check=True)
        run_init(repo)
        cfg = subprocess.run(["git", "config", "--get", "core.hooksPath"],
                              cwd=repo, capture_output=True, text=True).stdout.strip()
        check("existing core.hooksPath is not overridden", cfg == "custom")

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        repo = make_git_repo(tmp)
        (repo / ".githooks").mkdir()
        (repo / ".githooks" / "commit-msg").write_text("#!/bin/sh\n# custom\n")
        run_init(repo)
        check("existing hook file is not overwritten",
              (repo / ".githooks" / "commit-msg").read_text() == "#!/bin/sh\n# custom\n")

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        repo = make_git_repo(tmp)
        first = run_init(repo)
        second = run_init(repo)
        check("first run is all created (or skipped for git repo)",
              exit_code(first) == 0, first)
        check("second run is safe (exit 0)", exit_code(second) == 0, second)
        check("second run reports everything as skipped",
              all(s.status == "skipped" for s in second), second)

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        repo = make_git_repo(tmp)
        steps = run_init(repo)
        check("end-to-end: init succeeds before checks.py runs", exit_code(steps) == 0, steps)
        checks_py = Path(__file__).resolve().parent / "checks.py"
        r = subprocess.run([sys.executable, str(checks_py)], cwd=repo,
                            capture_output=True, text=True)
        check("checks.py runs clean against a just-initialized project (no copying needed)",
              r.returncode == 0 and "FAIL" not in r.stdout, r.stdout + r.stderr)

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        repo = make_git_repo(tmp)
        init_py = Path(__file__).resolve()
        r = subprocess.run([sys.executable, str(init_py), str(repo)],
                            cwd="/tmp", capture_output=True, text=True)
        check("CLI end-to-end succeeds with an unrelated cwd (portability)",
              r.returncode == 0, r.stdout + r.stderr)
        check("CLI end-to-end actually wrote the manifest",
              (repo / "project.toml").exists())

    print(f"{cases - failures}/{cases} cases pass")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--selftest", action="store_true")
    p.add_argument("path", nargs="?", help="directory to install into (must be a git repo)")
    args = p.parse_args(argv)
    if args.selftest:
        return _selftest()
    if not args.path:
        p.print_help()
        return 2
    steps = run_init(Path(args.path))
    render(steps)
    return exit_code(steps)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
