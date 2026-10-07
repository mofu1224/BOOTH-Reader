"""Maintainer-only macOS build; recipients restore this MIT host without a compiler."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.platforms import load_manifest  # noqa: E402


def main() -> None:
    if sys.platform != "darwin":
        raise RuntimeError("Build the macOS host on a Mac")
    destination = ROOT / ".playwright-browsers/native-webkit/booth-webkit-host"
    destination.parent.mkdir(parents=True, exist_ok=True)
    source = ROOT / "tools/webkit_host.swift"
    module_cache = ROOT / ".cache/swift-modules"
    module_cache.mkdir(parents=True, exist_ok=True)
    (ROOT / ".cache/tmp").mkdir(parents=True, exist_ok=True)
    (ROOT / ".cache/home").mkdir(parents=True, exist_ok=True)
    args = [
        "/usr/bin/swiftc",
        "-swift-version",
        "5",
        "-target",
        "arm64-apple-macos14.0",
        "-O",
        "-module-cache-path",
        str(module_cache),
        "-framework",
        "AppKit",
        "-framework",
        "WebKit",
        str(source),
        "-o",
        str(destination),
    ]
    result = subprocess.run(args, capture_output=True, text=True, timeout=180)
    if result.returncode:
        print(result.stderr, file=sys.stderr)
        raise RuntimeError("Native WebKit host compilation failed")
    subprocess.run(
        ["/usr/bin/codesign", "--verify", "--strict", str(destination)],
        check=True,
        capture_output=True,
    )
    linked = subprocess.check_output(["/usr/bin/otool", "-L", str(destination)], text=True)
    dependencies = "\n".join(linked.splitlines()[1:])
    if str(ROOT) in dependencies or "/Library/Developer/" in dependencies:
        raise RuntimeError("Host links against a maintainer-local runtime")
    version = subprocess.check_output(["/usr/bin/swiftc", "--version"], text=True).strip()
    receipt = {
        "source": "tools/webkit_host.swift",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "executable_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        "compiler": version,
        "target": "arm64-apple-macos14.0",
        "linked_libraries": linked.splitlines()[1:],
        "license": "MIT (first-party host); OS WebKit/AppKit/Swift libraries not redistributed",
    }
    (destination.parent / "build.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    spec = load_manifest(ROOT)
    snapshot = ROOT / spec["browser"]["offlineSnapshot"]
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(snapshot, "w:gz") as archive:
        archive.add(destination.parent, "native-webkit")
    receipt["sha256"] = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    snapshot.with_suffix(".json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
