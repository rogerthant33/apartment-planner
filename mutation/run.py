"""Mutation-test the committed HEAD in a throwaway git worktree.

cosmic-ray rewrites source files in place while it runs, so it never touches
the working tree you're editing. Surviving mutants are written to
mutation/last-report.txt.

Usage: uv run python mutation/run.py [config]   (default: mutation/pure.toml)
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SESSION = "mutation/session.sqlite"


def main() -> int:
    config = sys.argv[1] if len(sys.argv) > 1 else "mutation/pure.toml"
    # Inner `uv run` calls must use the worktree's environment, not ours.
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}

    def run(*args: str, cwd: Path) -> str:
        return subprocess.run(
            args, cwd=cwd, env=env, check=True, capture_output=True, text=True
        ).stdout

    tmp = Path(tempfile.mkdtemp(prefix="ap-mutation-"))
    worktree = tmp / "repo"
    run("git", "worktree", "add", "--detach", str(worktree), "HEAD", cwd=ROOT)
    try:
        run("uv", "sync", "--quiet", cwd=worktree)
        cosmic = ("uv", "run", "--no-sync")
        run(*cosmic, "cosmic-ray", "init", config, SESSION, cwd=worktree)
        run(*cosmic, "cr-filter-pragma", SESSION, cwd=worktree)
        run(*cosmic, "cosmic-ray", "exec", config, SESSION, cwd=worktree)
        report = run(*cosmic, "cr-report", "--show-diff", "--surviving-only", SESSION, cwd=worktree)
    finally:
        run("git", "worktree", "remove", "--force", str(worktree), cwd=ROOT)
        shutil.rmtree(tmp, ignore_errors=True)

    (ROOT / "mutation" / "last-report.txt").write_text(report, encoding="utf-8")
    summary = report.strip().splitlines()[-3:]
    print("\n".join(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
