from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "src" / "energytwin" / "app" / "static" / "app.js"


def run(command: list[str], *, dry_run: bool = False) -> None:
    print("$ " + " ".join(command))
    if dry_run:
        return
    completed = subprocess.run(command, cwd=ROOT)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def output(command: list[str]) -> str:
    completed = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
    return completed.stdout.strip()


def has_changes() -> bool:
    return bool(output(["git", "status", "--porcelain"]))


def has_staged_changes() -> bool:
    completed = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT)
    return completed.returncode != 0


def current_branch() -> str:
    branch = output(["git", "branch", "--show-current"])
    if not branch:
        raise SystemExit("Cannot push from a detached HEAD. Checkout a branch first.")
    return branch


def verify(args: argparse.Namespace) -> None:
    run(["python3", "-m", "unittest", "discover", "-s", "tests"], dry_run=args.dry_run)

    if not args.skip_compile:
        run(["python3", "-m", "compileall", "src", "scripts", "tests", "run.py"], dry_run=args.dry_run)

    if not args.skip_js_check and APP_JS.exists():
        if shutil.which("node"):
            run(["node", "--check", str(APP_JS.relative_to(ROOT))], dry_run=args.dry_run)
        else:
            print("Skipping JS syntax check because node is not installed.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run project checks, commit the current worktree, and optionally push the branch."
    )
    parser.add_argument("-m", "--message", required=True, help="Git commit message.")
    parser.add_argument("--push", action="store_true", help="Push the current branch after a successful commit.")
    parser.add_argument("--remote", default="origin", help="Git remote to push to. Defaults to origin.")
    parser.add_argument("--branch", help="Branch to push. Defaults to the current branch.")
    parser.add_argument("--no-stage", action="store_true", help="Commit only already-staged files.")
    parser.add_argument("--skip-compile", action="store_true", help="Skip python compileall verification.")
    parser.add_argument("--skip-js-check", action="store_true", help="Skip dashboard JavaScript syntax verification.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running them.")
    args = parser.parse_args()

    repo_root = Path(output(["git", "rev-parse", "--show-toplevel"])).resolve()
    if repo_root != ROOT:
        raise SystemExit(f"Run this script from the EnergyTwin repository. Expected {ROOT}, got {repo_root}.")

    verify(args)

    if not args.no_stage:
        if not has_changes() and not args.dry_run:
            print("No changes to commit.")
            return 0
        run(["git", "add", "-A"], dry_run=args.dry_run)

    if not args.dry_run and not has_staged_changes():
        print("No staged changes to commit.")
        return 0

    run(["git", "commit", "-m", args.message], dry_run=args.dry_run)

    if args.push:
        branch = args.branch or current_branch()
        run(["git", "push", args.remote, branch], dry_run=args.dry_run)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
