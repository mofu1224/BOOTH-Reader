"""Git-owned bootstrap materials; all reconstruction stays inside this checkout."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.platforms import TARGETS, load_manifest, target_id  # noqa: E402

VENDOR = ROOT / "vendor" / target_id()
MANIFEST = VENDOR / "manifest.json"
CHUNK_SIZE = 40 * 1024 * 1024


def sha(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def owned(path: Path, root: Path = ROOT) -> Path:
    if not path.resolve().is_relative_to(root.resolve()):
        raise RuntimeError(f"Path escapes portable checkout: {path}")
    return path


def materialize(name: str, root: Path = ROOT, *, target: str | None = None) -> Path:
    """Restore a cache asset from Git blobs, validating before publishing it."""
    target = target_id() if target is None else target
    if target not in TARGETS:
        raise ValueError(f"Unsupported portable target: {target}")
    vendor = root / "vendor" / target
    manifest = json.loads((vendor / "manifest.json").read_text(encoding="utf-8"))
    spec = manifest["assets"][name]
    destination = owned(root / spec["destination"], root)
    if destination.is_file() and sha(destination) == spec["sha256"]:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    scratch = owned(root / ".cache/tmp", root)
    scratch.mkdir(parents=True, exist_ok=True)
    fd, filename = tempfile.mkstemp(prefix="vendor-", dir=scratch)
    import os

    os.close(fd)
    temporary = Path(filename)
    try:
        with temporary.open("wb") as output:
            for part in spec["parts"]:
                source = owned(vendor / part["file"], vendor)
                if sha(source) != part["sha256"]:
                    raise RuntimeError(f"Vendored chunk hash mismatch: {source.name}")
                with source.open("rb") as stream:
                    shutil.copyfileobj(stream, output, 1024 * 1024)
        if temporary.stat().st_size != spec["size"] or sha(temporary) != spec["sha256"]:
            raise RuntimeError(f"Vendored asset hash mismatch: {name}")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def restore_wheels(root: Path = ROOT) -> None:
    archive = materialize("wheels", root)
    runtime = load_manifest(root)
    wanted = set(re.findall(r"--hash=sha256:([0-9a-f]{64})", (root / runtime["lock"]).read_text()))
    destination = owned(root / runtime["wheelhouse"], root)
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        entries = bundle.namelist()
        if len(entries) != len(wanted) or any(
            Path(name).name != name or not name.endswith(".whl") for name in entries
        ):
            raise RuntimeError("Invalid vendored wheel archive layout")
        verified = set()
        for name in entries:
            data = bundle.read(name)
            digest = hashlib.sha256(data).hexdigest()
            if digest not in wanted:
                raise RuntimeError(f"Wheel is not in portable lock: {name}")
            verified.add(digest)
            path = owned(destination / name, root)
            if not path.is_file() or sha(path) != digest:
                path.write_bytes(data)
        if verified != wanted:
            raise RuntimeError("Incomplete vendored wheel closure")


def build(target: str | None = None) -> None:
    """Maintainer operation: package already verified materials, no downloads."""
    target = target_id() if target is None else target
    runtime = load_manifest(ROOT, target)
    vendor = ROOT / "vendor" / target
    vendor.mkdir(parents=True, exist_ok=True)
    scratch = ROOT / ".cache/tmp"
    scratch.mkdir(parents=True, exist_ok=True)
    wheel_archive = scratch / "vendor-wheels.zip"
    wheels = sorted((ROOT / runtime["wheelhouse"]).glob("*.whl"))
    hashes = set(re.findall(r"--hash=sha256:([0-9a-f]{64})", (ROOT / runtime["lock"]).read_text()))
    if {sha(path) for path in wheels} != hashes or len(wheels) != len(hashes):
        raise RuntimeError("Wheelhouse does not exactly match the portable lock")
    with zipfile.ZipFile(wheel_archive, "w", zipfile.ZIP_STORED) as archive:
        for path in wheels:
            archive.writestr(zipfile.ZipInfo(path.name), path.read_bytes())
    python_archive = ROOT / ".cache/downloads" / runtime["python"]["asset"]
    if sha(python_archive) != runtime["python"]["sha256"]:
        raise RuntimeError("Python publisher hash mismatch")
    browser = ROOT / runtime["browser"]["offlineSnapshot"]
    receipt = browser.with_suffix(".json")
    if sha(browser) != json.loads(receipt.read_text(encoding="utf-8"))["sha256"]:
        raise RuntimeError("Browser snapshot hash mismatch")
    sources = {
        "python": python_archive,
        "wheels": wheel_archive,
        "browser": browser,
        "browser-receipt": receipt,
    }
    if not runtime["sqlite"].get("bundled"):
        sqlite_archive = ROOT / ".cache/downloads" / runtime["sqlite"]["asset"]
        if (
            hashlib.sha3_256(sqlite_archive.read_bytes()).hexdigest()
            != runtime["sqlite"]["sha3_256"]
        ):
            raise RuntimeError("SQLite publisher hash mismatch")
        sources["sqlite"] = sqlite_archive
    manifest: dict[str, Any] = {
        "schema": 1,
        "target": target,
        "lock_sha256": sha(ROOT / runtime["lock"]),
        "assets": {},
    }
    try:
        for name, source in sources.items():
            digest = sha(source)
            parts = []
            with source.open("rb") as stream:
                for index in range((source.stat().st_size + CHUNK_SIZE - 1) // CHUNK_SIZE):
                    data = stream.read(CHUNK_SIZE)
                    filename = f"{name}-{digest[:16]}-{index:03d}.chunk"
                    part = vendor / filename
                    part_hash = hashlib.sha256(data).hexdigest()
                    if part.exists() and sha(part) != part_hash:
                        raise RuntimeError(f"Refusing to overwrite changed vendor file: {filename}")
                    if not part.exists():
                        part.write_bytes(data)
                    parts.append({"file": filename, "sha256": part_hash, "size": len(data)})
            destination = (
                ".cache/vendor/wheels.zip"
                if name == "wheels"
                else source.relative_to(ROOT).as_posix()
            )
            manifest["assets"][name] = {
                "destination": destination,
                "sha256": digest,
                "size": source.stat().st_size,
                "parts": parts,
            }
        (vendor / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
    finally:
        wheel_archive.unlink(missing_ok=True)
    print(f"Vendored {len(wheels)} wheels, Python, SQLite and browser; all chunks <=40 MiB")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["build", "verify"])
    parser.add_argument("--target", choices=["windows-x64", "macos-arm64", "all"])
    args = parser.parse_args()
    if args.action == "build":
        targets = list(TARGETS) if args.target == "all" else [args.target or target_id()]
        for target in targets:
            build(target)
    else:
        targets = (
            ["windows-x64", "macos-arm64"] if args.target == "all" else [args.target or target_id()]
        )
        for target in targets:
            vendor = ROOT / "vendor" / target
            manifest = json.loads((vendor / "manifest.json").read_text(encoding="utf-8"))
            runtime = load_manifest(ROOT, target)
            if manifest["lock_sha256"] != sha(ROOT / runtime["lock"]):
                raise RuntimeError("Vendored payload does not match current lock")
            for spec in manifest["assets"].values():
                digest = hashlib.sha256()
                for part in spec["parts"]:
                    path = owned(vendor / part["file"], vendor)
                    if path.stat().st_size != part["size"] or sha(path) != part["sha256"]:
                        raise RuntimeError(f"Invalid vendor part: {path.name}")
                    digest.update(path.read_bytes())
                if digest.hexdigest() != spec["sha256"]:
                    raise RuntimeError("Invalid joined asset digest")
            print(f"Vendor integrity ({target}): PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
