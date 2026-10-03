"""Check Git privacy and whole-folder release blockers without printing private paths."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
PRIVATE_ROOTS = {"data", "booth-reader-library", ".private", "private", "backups"}
LOCAL_ROOTS = {
    ".cache",
    ".tools",
    ".venv",
    ".playwright",
    ".playwright-browsers",
    ".verify-venv",
    "venv",
    "__pycache__",
}
LOCAL_RECEIPTS = {
    "local-inventory.json",
    "distribution-inventory.json",
    "package-reconciliation.json",
    "final-package-result.json",
    "clean-candidate-result.json",
    "public-clean-test.json",
    "creation-session-evidence.json",
    "project-generation-models.json",
}


def private_path(name: str) -> bool:
    path = PurePosixPath(name.replace("\\", "/"))
    lower = path.name.lower()
    if {part.lower() for part in path.parts} & (PRIVATE_ROOTS | LOCAL_ROOTS):
        return True
    if (
        lower == ".env"
        or lower.startswith((".env.", "cookies", ".cookies-"))
        or (lower.endswith(".json") and ("cookie" in lower or "storage-state" in lower))
        or (
            lower.endswith((".bak", ".backup"))
            and any(extension in lower for extension in (".db", ".sqlite"))
        )
    ):
        return True
    if path.suffix.lower() in {".db", ".sqlite", ".sqlite3", ".csv", ".log", ".har"}:
        return True
    if any(extension + "-" in lower for extension in (".db", ".sqlite", ".sqlite3")):
        return True
    if path.parts and path.parts[0] == "audit" and path.suffix in {".json", ".xml", ".png"}:
        return True
    return bool(path.parts and path.parts[0] == "license-audit" and path.name in LOCAL_RECEIPTS)


def git_paths(root: Path, *args: str) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, check=True, timeout=60
    )
    return result.stdout.decode("utf-8", errors="replace").split("\0")[:-1]


def inspect(root: Path, *, git_only: bool = False) -> dict:
    tracked = git_paths(root, "ls-files", "-z")
    eligible = git_paths(root, "ls-files", "--others", "--exclude-standard", "-z")
    tracked_private = sum(private_path(name) for name in tracked)
    eligible_private = sum(private_path(name) for name in eligible)
    history = subprocess.run(
        ["git", "-C", str(root), "rev-list", "--objects", "--all"],
        capture_output=True,
        check=True,
        timeout=60,
    )
    historic_private = sum(
        private_path(line.split(" ", 1)[1])
        for line in history.stdout.decode("utf-8", errors="replace").splitlines()
        if " " in line
    )
    report = {
        "scope": "git-path-privacy" if git_only else "whole-folder-path-privacy",
        "tracked_private_paths": tracked_private,
        "eligible_private_paths": eligible_private,
        "historical_private_objects": historic_private,
        "git_privacy_ok": not (tracked_private or eligible_private or historic_private),
        "content_secret_scan": "not performed; path checks only",
    }
    if git_only:
        report["ok"] = report["git_privacy_ok"]
        return report
    # Never enumerate purchase filenames, user profiles or cookie contents.
    personal_roots = sum(
        path.is_dir() and path.name.lower() in PRIVATE_ROOTS for path in root.iterdir()
    )
    personal_files = sum(private_path(path.name) for path in root.iterdir() if path.is_file())
    local_roots = sum((root / name).exists() for name in LOCAL_ROOTS)
    gate = root / "license-audit/release-gate.json"
    evidence = json.loads(gate.read_text(encoding="utf-8")) if gate.is_file() else {}
    cleared = (
        evidence.get("release_status") == "READY FOR RELEASE" and evidence.get("blockers") == []
    )
    report.update(
        personal_data_roots=personal_roots,
        personal_root_files=personal_files,
        local_generated_roots=local_roots,
        license_status=evidence.get("release_status", "MISSING"),
        license_blockers=[row["id"] for row in evidence.get("blockers", [])],
        license_evidence_freshness="not verified by this privacy check",
        ok=False,
    )
    report["folder_privacy_ok"] = not (personal_roots or personal_files or local_roots)
    report["license_clearance_declared"] = cleared
    # This result covers privacy paths only, never redistribution permission.
    report["ok"] = report["git_privacy_ok"] and report["folder_privacy_ok"]
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--git-only", action="store_true", help="check Git privacy paths only")
    args = parser.parse_args(argv)
    report = inspect(ROOT, git_only=args.git_only)
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
