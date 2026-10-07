"""Validate the Git clone candidate; never generate a distribution archive."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.check_release_hygiene import inspect  # noqa: E402
from tools.repository_files import (  # noqa: E402
    collect,
    require_clone_script_modes,
    require_release_clearance,
)


def main() -> int:
    privacy = inspect(ROOT, git_only=True)
    if not privacy["ok"]:
        print(json.dumps(privacy, indent=2))
        return 1
    files = collect(ROOT)
    require_clone_script_modes(files, ROOT)
    require_release_clearance(files, ROOT)
    print(json.dumps({"scope": "github-repository-clone", "files": len(files), "status": "PASS"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
