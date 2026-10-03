"""Verify retained notices and corresponding sources against immutable evidence."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.repository_files import sha256  # noqa: E402

EVIDENCE = (
    "license-evidence.json",
    "packages.json",
    "pbs-correspondence.json",
    "native-source-evidence.json",
    "pathspec-source.json",
    "vendored-certifi-source.json",
    "upstream-evidence.json",
    "public-profile-legal-evidence.json",
)


def inspect(root: Path = ROOT) -> dict[str, Any]:
    references: dict[str, str] = {}

    def add(name: Any, digest: Any) -> None:
        if not isinstance(name, str) or not name.startswith(
            ("THIRD_PARTY_LICENSES/", "SOURCE_OBLIGATIONS/", "license-audit/evidence/")
        ):
            return
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Invalid license/source evidence digest")
        if name in references and references[name] != digest:
            raise ValueError("Conflicting retained evidence")
        references[name] = digest

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            add(value.get("path"), value.get("sha256"))
            add(value.get("source"), value.get("sha256"))
            add(value.get("source_path"), value.get("source_sha256"))
            add(value.get("archive"), value.get("sha256"))
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    for name in EVIDENCE:
        walk(json.loads((root / "license-audit" / name).read_text(encoding="utf-8")))
    if not references:
        raise ValueError("No retained license/source evidence")
    failures = []
    for name, expected in references.items():
        path = root / name
        if (
            not path.resolve().is_relative_to(root.resolve())
            or not path.is_file()
            or path.is_symlink()
            or sha256(path) != expected
        ):
            failures.append(name)
    # Every retained hash-named original is independently checked, including
    # notices retained by earlier audits but still present in the Git clone.
    notice_count = 0
    for path in (root / "THIRD_PARTY_LICENSES").rglob("*"):
        if path.is_file() and re.match(r"^[0-9a-f]{12}-", path.name):
            notice_count += 1
            if sha256(path)[:12] != path.name[:12]:
                failures.append(path.relative_to(root).as_posix())
    return {
        "scope": "retained-license-and-source-integrity",
        "evidence_references": len(references),
        "hash_named_notices": notice_count,
        "failures": sorted(set(failures)),
        "ok": not failures,
    }


def main() -> int:
    report = inspect()
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
