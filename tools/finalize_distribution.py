"""Bind reviewed cross-platform redistribution evidence to the complete candidate."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.check_license_evidence import inspect as inspect_evidence  # noqa: E402
from tools.check_release_hygiene import inspect as inspect_privacy  # noqa: E402
from tools.repository_files import collect, input_hashes, require_clone_script_modes  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviewed", action="store_true", required=True)
    parser.add_argument(
        "--report",
        default="audit/22-portable-distribution-1.2.0.md",
        help="release verification report bound to this candidate",
    )
    args = parser.parse_args()
    if not args.reviewed:
        raise RuntimeError("Review the corresponding-source and notice conditions first")
    evidence = json.loads(
        (ROOT / "license-audit/macos-distribution-evidence.json").read_text(encoding="utf-8")
    )
    if evidence["python"]["matched_files"] != 1653 or len(evidence["packages"]) != 62:
        raise RuntimeError("Incomplete Mac distribution evidence")
    if any(row["upstream_license"] in {"NOT VERIFIED", ""} for row in evidence["packages"]):
        raise RuntimeError("Unknown Mac redistribution classification")
    if not inspect_evidence(ROOT)["ok"] or not inspect_privacy(ROOT, git_only=True)["ok"]:
        raise RuntimeError("Candidate evidence/privacy check failed")
    report_path = ROOT / "license-audit/31-cross-platform-clone-distribution.md"
    if not report_path.is_file():
        raise RuntimeError("Cross-platform redistribution review missing")
    release_report = ROOT / args.report
    if not release_report.is_file():
        raise RuntimeError(f"Release verification report missing: {args.report}")
    files = collect(ROOT)
    require_clone_script_modes(files, ROOT)
    gate_path = ROOT / "license-audit/release-gate.json"
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    hashes = input_hashes(files, ROOT)
    gate.update(
        {
            "release_status": "READY FOR RELEASE",
            "scope": "github-repository-clone",
            "latest_report": args.report,
            "license_report": "license-audit/31-cross-platform-clone-distribution.md",
            "blockers": [],
            "input_count": len(hashes),
            "input_hashes": hashes,
            "date": date.today().isoformat(),
            "supported_targets": ["windows-x64", "macos-arm64"],
            "product_readiness": "Repository-clone distribution; validation coverage is documented separately; uncommitted changes are not in HEAD",
        }
    )
    gate_path.write_text(json.dumps(gate, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Redistribution review bound to {len(files)} candidate files")


if __name__ == "__main__":
    main()
