"""Turn observed receipts into a compact durable report without overstating scope."""

from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    receipt = json.loads((ROOT / "audit/portable-verification.json").read_text(encoding="utf-8"))
    observed_root = Path(receipt["runtime_probe"]["root"])
    system = Path(os.environ["SYSTEMROOT"])
    module_paths = {path for process in receipt["process_modules"] for path in process["modules"]}
    local = sorted(path for path in module_paths if Path(path).is_relative_to(observed_root))
    os_modules = sorted(path for path in module_paths if Path(path).is_relative_to(system))
    host = sorted(set(module_paths) - set(local) - set(os_modules))
    with zipfile.ZipFile(ROOT / receipt["evidence_archive"]) as archive:
        junit = next(n for n in archive.namelist() if n.endswith("/.cache/junit.xml"))
        tree = ET.fromstring(archive.read(junit))  # noqa: S314 - our own generated synthetic test report
        testcases = tree.findall(".//testcase")
        tests = {
            "total": len(testcases),
            "failed": len(tree.findall(".//failure")),
            "errors": len(tree.findall(".//error")),
            "skipped": len(tree.findall(".//skipped")),
        }
        (ROOT / "audit/junit-portable.xml").write_bytes(archive.read(junit))
    summary = {
        "target": "Windows 11 x64 / CPython 3.12.13 / Playwright 1.63.0",
        "verification_status": receipt["status"],
        "regression": tests,
        "latest_gate_results": {row["name"]: row["returncode"] for row in receipt["checks"]},
        "local_native_modules": local,
        "os_native_modules": os_modules,
        "host_injected_or_integrated_modules": host,
        "python_access": receipt["python_access_summary"],
        "source_db_unchanged": receipt["source_db_unchanged"],
        "old_checkout_missing": not receipt["old_copy_exists"],
        "owned_copies_removed": receipt.get("owned_copies_removed", False),
        "evidence_archive": receipt["evidence_archive"],
        "not_tested": [
            "live BOOTH login/download",
            "another physical PC",
            "Windows 10",
            "kernel-wide native file/registry/network access",
            "public binary redistribution license closure",
        ],
    }
    (ROOT / "audit/portable-summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "regression": tests,
                "module_counts": {"local": len(local), "OS": len(os_modules), "host": len(host)},
                "host_modules": host,
                "python_external_paths": summary["python_access"]["external_paths"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
