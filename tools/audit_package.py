"""Verify final archives, checksums, and runtime agreement with the tested candidate."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import tarfile
import zipfile
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument(
        "--candidate",
        type=Path,
        help="tested candidate ZIP; otherwise compare to current source tree",
    )
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    checksums = {}
    for line in (args.directory / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        expected, name = line.split(None, 1)
        name = name.strip()
        path = args.directory / name
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == expected, f"checksum mismatch: {name}"
        checksums[name] = actual
    launcher = next(
        p for p in args.directory.glob("BOOTH-Reader-*.zip") if not p.name.endswith("-offline.zip")
    )
    candidate_context = (
        zipfile.ZipFile(args.candidate) if args.candidate else contextlib.nullcontext(None)
    )
    with zipfile.ZipFile(launcher) as final, candidate_context as candidate:
        assert final.testzip() is None
        names = final.namelist()
        assert all(".." not in Path(n).parts and not n.startswith("/") for n in names)
        assert all(not n.lower().endswith((".db", ".part", ".tmp", ".pyc", ".env")) for n in names)
        assert all(
            not set(Path(n).parts)
            & {"data", ".venv", ".tools", ".cache", ".playwright-browsers", "BOOTH-Reader-Library"}
            for n in names
        )
        compared = []
        for name in names:
            if name.startswith(("core/", "web/", "tests/", "tools/", "third_party/")) or name in {
                "cli.py",
                "conftest.py",
                "pyproject.toml",
                "requirements.txt",
                "requirements-lock.txt",
                "requirements-portable-lock.txt",
                "portable-manifest.json",
                "setup.bat",
                "cli.bat",
                "start-web.bat",
            }:
                expected = (
                    candidate.read(name)
                    if candidate
                    else (Path(__file__).resolve().parent.parent / name).read_bytes()
                )
                assert final.read(name) == expected, f"source changed: {name}"
                compared.append(name)
        assert "audit/11-final-quality-report.md" in names
    wheel = next(args.directory.glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        assert archive.testzip() is None
        assert "tools/portable.py" in archive.namelist()
        assert any(n.endswith("/licenses/LICENSE") for n in archive.namelist())
    sdist = next(args.directory.glob("*.tar.gz"))
    with tarfile.open(sdist) as archive:
        members = archive.getmembers()
        assert all(not member.issym() and not member.islnk() for member in members)
        assert any(member.name.endswith("/setup.bat") for member in members)
        assert any(member.name.endswith("/tools/portable.py") for member in members)
    report = {
        "checksums": checksums,
        "source_files_identical": len(compared),
        "comparison": "tested candidate" if args.candidate else "current source tree",
        "launcher_entries": len(names),
        "wheel_sdist_required_files": "present",
        "user_data_and_runtime_binaries": "excluded",
        "zip_crc": "ok",
    }
    offline_files = list(args.directory.glob("*-offline.zip"))
    if offline_files:
        root = Path(__file__).resolve().parent.parent
        manifest = json.loads((root / "portable-manifest.json").read_text(encoding="utf-8"))
        with zipfile.ZipFile(offline_files[0]) as archive:
            assert archive.testzip() is None
            entries = archive.namelist()
            assert all(".." not in Path(n).parts and not n.startswith("/") for n in entries)
            assert all(
                not set(Path(n).parts) & {"data", ".venv", ".tools", "BOOTH-Reader-Library"}
                for n in entries
            )
            for spec, algorithm in (
                (manifest["python"], "sha256"),
                (manifest["sqlite"], "sha3_256"),
            ):
                with archive.open(".cache/downloads/" + spec["asset"]) as stream:
                    checksum = hashlib.new(algorithm)
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        checksum.update(block)
                    assert checksum.hexdigest() == spec[algorithm]
            browser = manifest["browser"]["offlineSnapshot"]
            receipt = json.loads(
                archive.read(str(Path(browser).with_suffix(".json")).replace("\\", "/"))
            )
            with archive.open(browser) as stream:
                checksum = hashlib.sha256()
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    checksum.update(block)
                assert checksum.hexdigest() == receipt["sha256"]
            wheels = [n for n in entries if n.startswith(".cache/wheels/") and n.endswith(".whl")]
            import re

            hashes = set(
                re.findall(
                    r"--hash=sha256:([0-9a-f]{64})",
                    (root / "requirements-portable-lock.txt").read_text(),
                )
            )
            assert len(wheels) == len(hashes)
            assert {hashlib.sha256(archive.read(n)).hexdigest() for n in wheels} == hashes
            report["offline_materials"] = {
                "wheel_count": len(wheels),
                "python_sqlite_browser_hashes": "verified",
                "user_data": "excluded",
                "zip_crc": "ok",
            }
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
