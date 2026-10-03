"""Clone release candidate verification and a reusable CLI roundtrip probe."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
RESULTS: list[tuple[str, str, str]] = []


def record(name: str, status: str, detail: str = "") -> None:
    RESULTS.append((name, status, detail))
    print(f"[{status}] {name}" + (f"\n        {detail}" if detail else ""))


def run(cmd: list[str], cwd: Path, timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        env=dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8"),
    )


def gate_startup(python: Path, work: Path) -> None:
    db = str(work / "app.db")
    for argv in (
        ["--version"],
        ["init-db", "--db", db],
        ["--db", db, "unclassified", "--sort", "newest"],
        ["--db", db, "purchases", "list"],
        ["--db", db, "downloads", "list"],
        ["--db", db, "lists", "list"],
        ["--db", db, "doctor"],
    ):
        proc = run([str(python), "cli.py", *argv], work)
        record(f"startup: {' '.join(argv)}", "PASS" if proc.returncode == 0 else "FAIL")


if __name__ == "__main__":
    from tools.verify_clone import main

    raise SystemExit(main())
