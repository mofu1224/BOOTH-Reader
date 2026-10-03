"""Retired archive builder. Distribution uses the complete Git repository."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools import repository_files  # noqa: E402


def collect() -> list[Path]:
    return repository_files.collect(ROOT)


def sha256(path: Path) -> str:
    return repository_files.sha256(path)


def require_release_clearance(files: list[Path]) -> None:
    repository_files.require_release_clearance(files, ROOT)


def main(_argv: list[str] | None = None) -> int:
    raise SystemExit(
        "Archive distribution is retired. Use tools/check_distribution.py and tools/verify_clone.py."
    )


if __name__ == "__main__":
    raise SystemExit(main())
