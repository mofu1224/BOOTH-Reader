"""Apply a hash-verified ABI-compatible official SQLite DLL inside local CPython."""

from __future__ import annotations

import hashlib
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.platforms import load_manifest, python_relative  # noqa: E402

SPEC = load_manifest(ROOT)["sqlite"]
ARCHIVE = ROOT / ".cache/downloads" / SPEC.get("asset", "sqlite-bundled")
TARGET = ROOT / ".tools/python/DLLs/sqlite3.dll"


def sqlite_version() -> str:
    process = subprocess.run(
        [
            str(ROOT / ".tools/python" / python_relative()),
            "-E",
            "-s",
            "-c",
            "import sqlite3; print(sqlite3.sqlite_version)",
        ],
        capture_output=True,
        encoding="utf-8",
        check=False,
        timeout=60,
    )
    return process.stdout.strip() if process.returncode == 0 else "unusable"


def ensure_sqlite(*, offline: bool) -> None:
    if SPEC.get("bundled"):
        actual = sqlite_version()
        minimum = tuple(int(part) for part in SPEC["minimumVersion"].split("."))
        if actual == "unusable" or tuple(int(part) for part in actual.split(".")) < minimum:
            raise RuntimeError(
                f"Bundled SQLite {actual} is below required {SPEC['minimumVersion']}"
            )
        return
    if (
        TARGET.is_file()
        and hashlib.sha256(TARGET.read_bytes()).hexdigest() == SPEC["dll_sha256"]
        and sqlite_version() == SPEC["version"]
    ):
        return
    ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    valid = (
        ARCHIVE.is_file() and hashlib.sha3_256(ARCHIVE.read_bytes()).hexdigest() == SPEC["sha3_256"]
    )
    if not valid:
        if offline:
            from tools.vendor_payload import materialize

            materialize("sqlite", ROOT)
        else:
            url = SPEC["url"]
            if not url.startswith("https://www.sqlite.org/"):
                raise RuntimeError("SQLite must come from pinned official HTTPS URL")
            with urllib.request.urlopen(url, timeout=120) as response:  # noqa: S310 - official HTTPS asserted above
                data = response.read()
            if hashlib.sha3_256(data).hexdigest() != SPEC["sha3_256"]:
                raise RuntimeError("SQLite archive SHA3-256 mismatch")
            ARCHIVE.write_bytes(data)
        if hashlib.sha3_256(ARCHIVE.read_bytes()).hexdigest() != SPEC["sha3_256"]:
            raise RuntimeError("SQLite publisher SHA3-256 mismatch")
    with zipfile.ZipFile(ARCHIVE) as archive:
        # Read one fixed member rather than extracting paths from the archive.
        data = archive.read("sqlite3.dll")
    if hashlib.sha256(data).hexdigest() != SPEC["dll_sha256"]:
        raise RuntimeError("SQLite DLL SHA-256 mismatch")
    part = TARGET.with_suffix(".dll.part")
    backup = ROOT / ".cache/tmp" / f"sqlite-backup-{time.time_ns()}.dll"
    backup.parent.mkdir(parents=True, exist_ok=True)
    part.write_bytes(data)
    had_previous = TARGET.is_file()
    if had_previous:
        TARGET.replace(backup)
    try:
        part.replace(TARGET)
        if sqlite_version() != SPEC["version"]:
            raise RuntimeError("SQLite DLL failed ABI/version self-check")
    except BaseException:
        TARGET.unlink(missing_ok=True)
        if had_previous:
            backup.replace(TARGET)
        raise
    backup.unlink(missing_ok=True)
    print(
        "[portable] SQLite "
        + SPEC["version"]
        + " ready; DLL SHA-256 "
        + hashlib.sha256(data).hexdigest(),
        file=sys.stderr,
    )


if __name__ == "__main__":
    ensure_sqlite(offline="--offline" in sys.argv)
