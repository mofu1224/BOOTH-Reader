"""Bind Mac deliverables to publisher evidence, notices and corresponding sources."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.license_report import notice_label  # noqa: E402
from tools.prepare_macos import acquire  # noqa: E402
from tools.vendor_payload import materialize  # noqa: E402

FULL = {
    "url": "https://github.com/astral-sh/python-build-standalone/releases/download/20261003/cpython-3.12.15%2B20261003-aarch64-apple-darwin-pgo%2Blto-full.tar.zst",
    "asset": "cpython-3.12.15+20261003-aarch64-apple-darwin-pgo+lto-full.tar.zst",
    "sha256": "a23a0baff73a5f10c820841cc1889a5b7fc12048fe8c0622f6a481ab82ea367b",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    archive = ROOT / ".cache/downloads" / FULL["asset"]
    acquire(FULL["url"], archive, sha256=FULL["sha256"])
    native_sources = json.loads(
        (ROOT / "license-audit/native-source-evidence.json").read_text(encoding="utf-8")
    )
    package_sources = {entry["name"]: entry for entry in native_sources["native_packages"]}
    notices = []
    tmp = ROOT / ".cache/tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    system_tar = (
        Path(os.environ.get("SYSTEMROOT", "")) / "System32/tar.exe"
        if sys.platform == "win32"
        else Path("/usr/bin/tar")
    )
    with tempfile.TemporaryDirectory(prefix="mac-pbs-evidence-", dir=tmp) as work:
        directory = Path(work)
        exclusions = []
        if sys.platform == "win32":
            listing = subprocess.check_output(
                [str(system_tar), "-tvf", str(archive)], text=True, timeout=90
            )
            for line in listing.splitlines():
                if line.startswith("l"):
                    match = re.search(r"\s(python/.+?) -> ", line)
                    if not match:
                        raise RuntimeError("Unexpected PBS symlink listing")
                    exclusions.extend(["--exclude", match[1]])
        result = subprocess.run(
            [
                str(system_tar),
                "-xf",
                str(archive),
                "-C",
                str(directory),
                *exclusions,
                "python/PYTHON.json",
                "python/install",
                "python/licenses",
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode:
            print(result.stderr, file=sys.stderr)
            raise RuntimeError("PBS full archive extraction failed")
        metadata = json.loads((directory / "python/PYTHON.json").read_text(encoding="utf-8"))
        matched = 0
        with tarfile.open(materialize("python", ROOT, target="macos-arm64")) as original:
            for member in original.getmembers():
                if not member.isfile():
                    continue
                source = original.extractfile(member)
                assert source is not None
                target = directory / "python/install" / member.name.removeprefix("python/")
                if not target.is_file() or hashlib.sha256(source.read()).hexdigest() != digest(
                    target
                ):
                    raise RuntimeError(
                        f"Mac CPython publisher full/install-only mismatch: {member.name}"
                    )
                matched += 1
        for path in sorted((directory / "python/licenses").rglob("*")):
            if not path.is_file():
                continue
            data = path.read_bytes()
            sha = hashlib.sha256(data).hexdigest()
            name = re.sub(r"[^A-Za-z0-9._-]", "_", path.name)[:65]
            destination = ROOT / "THIRD_PARTY_LICENSES/macos/CPython-3.12.15" / f"{sha[:12]}-{name}"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            notices.append(
                {
                    "path": destination.relative_to(ROOT).as_posix(),
                    "sha256": sha,
                    "source": FULL["url"],
                }
            )
        pbs = {
            "full_archive": FULL,
            "matched_files": matched,
            "metadata": metadata,
            "notices": notices,
        }
    packages = []
    certifi_sources = {}

    def collect_certifi(name: str, data: bytes) -> None:
        if "/_vendor/certifi/" in name and not name.endswith("/"):
            certifi_sources[name] = data

    with tarfile.open(materialize("python", ROOT, target="macos-arm64")) as python_archive:
        for member in python_archive.getmembers():
            if not member.isfile():
                continue
            stream = python_archive.extractfile(member)
            assert stream is not None
            if "/_vendor/certifi/" in member.name:
                collect_certifi(member.name, stream.read())
            elif member.name.endswith(".whl"):
                with zipfile.ZipFile(io.BytesIO(stream.read())) as bundled:
                    for name in bundled.namelist():
                        if "/_vendor/certifi/" in name and not name.endswith("/"):
                            collect_certifi("ensurepip/" + name, bundled.read(name))
    old_packages = {
        entry["name"]: entry
        for entry in json.loads((ROOT / "license-audit/packages.json").read_text(encoding="utf-8"))
    }
    mac_inputs = json.loads(
        (ROOT / "license-audit/macos-publisher-inputs.json").read_text(encoding="utf-8")
    )
    published = {entry["name"]: entry for entry in mac_inputs["wheels"]}
    with zipfile.ZipFile(materialize("wheels", ROOT, target="macos-arm64")) as wheelhouse:
        for filename in sorted(wheelhouse.namelist()):
            data = wheelhouse.read(filename)
            if hashlib.sha256(data).hexdigest() != published[filename]["sha256"]:
                raise RuntimeError("Mac wheel does not match publisher evidence")
            name = re.sub(r"[-_.]+", "-", filename.split("-")[0]).lower()
            version = filename.split("-")[1]
            if old_packages[name]["version"] != version:
                raise RuntimeError("Mac package version differs from reviewed release")
            with zipfile.ZipFile(io.BytesIO(data)) as wheel:
                if name == "pip":
                    for path in wheel.namelist():
                        if "/_vendor/certifi/" in path and not path.endswith("/"):
                            collect_certifi("pip-wheel/" + path, wheel.read(path))
                original_notices = [
                    path
                    for path in wheel.namelist()
                    if not path.endswith("/")
                    and re.search(r"license|copying|notice|copyright", Path(path).name, re.I)
                ]
                binaries = [
                    path
                    for path in wheel.namelist()
                    if not path.endswith("/")
                    and (
                        path.endswith((".so", ".dylib"))
                        or wheel.read(path)[:4]
                        in {
                            b"\xcf\xfa\xed\xfe",
                            b"\xfe\xed\xfa\xcf",
                            b"\xca\xfe\xba\xbe",
                            b"\xbe\xba\xfe\xca",
                        }
                    )
                ]
                if not original_notices and name != "packageurl-python":
                    raise RuntimeError(f"Mac package lacks notices: {filename}")
                source = package_sources.get(name)
                if binaries and source:
                    source_path = ROOT / source["source"]
                    if digest(source_path) != source["sha256"]:
                        raise RuntimeError("Corresponding source evidence mismatch")
                if binaries and not source:
                    raise RuntimeError(f"No retained matching source for native wheel: {name}")
                license_label = notice_label(old_packages[name])
                if license_label in {"NOT VERIFIED", "", "原文metadata参照"}:
                    raise RuntimeError(f"No reviewed license classification: {name}")
                packages.append(
                    {
                        "name": name,
                        "version": version,
                        "wheel": filename,
                        "sha256": published[filename]["sha256"],
                        "upstream_license": license_label,
                        "notices": original_notices,
                        "native_files": binaries,
                        "source_path": source["source"] if source else None,
                        "source_sha256": source["sha256"] if source else None,
                    }
                )
    browser = materialize("browser", ROOT, target="macos-arm64")
    with tarfile.open(browser) as archive:
        allowed = {"native-webkit", "native-webkit/booth-webkit-host", "native-webkit/build.json"}
        if {member.name for member in archive.getmembers()} != allowed:
            raise RuntimeError("Mac payload contains unexpected third-party browser files")
        stream = archive.extractfile("native-webkit/build.json")
        assert stream is not None
        host = json.load(stream)
        if digest(ROOT / host["source"]) != host["source_sha256"]:
            raise RuntimeError("Native host does not match retained MIT source")
        if any(
            not line.strip().startswith(("/usr/lib/", "/System/Library/"))
            for line in host["linked_libraries"]
        ):
            raise RuntimeError("Native host has a non-OS external library")
    certifi_path = ROOT / "SOURCE_OBLIGATIONS/macos-vendored-certifi-source.tar.gz"
    with tarfile.open(certifi_path, "w:gz") as source_archive:
        for name, data in sorted(certifi_sources.items()):
            member = tarfile.TarInfo(name)
            member.size = len(data)
            source_archive.addfile(member, io.BytesIO(data))
    certifi_evidence = {
        "archive": certifi_path.relative_to(ROOT).as_posix(),
        "sha256": digest(certifi_path),
        "files": [
            {"path": name, "sha256": hashlib.sha256(data).hexdigest()}
            for name, data in sorted(certifi_sources.items())
        ],
    }
    report = {
        "target": "macos-arm64",
        "python": pbs,
        "packages": packages,
        "host": host,
        "vendored_certifi_source": certifi_evidence,
        "excluded": [
            "Google Chrome",
            "Chrome for Testing",
            "Firefox",
            "Playwright WebKit test driver",
            "FFmpeg",
        ],
        "scope": "delivered vendor payload only; generated test tools are not redistributed",
    }
    mac_inputs["browser"] = {
        "engine": "native-webkit",
        "host_source": host["source"],
        "source_sha256": host["source_sha256"],
        "executable_sha256": host["executable_sha256"],
        "snapshot_sha256": digest(browser),
        "license": "MIT; OS frameworks not redistributed",
    }
    (ROOT / "license-audit/macos-publisher-inputs.json").write_text(
        json.dumps(mac_inputs, indent=2) + "\n", encoding="utf-8"
    )
    destination = ROOT / "license-audit/macos-distribution-evidence.json"
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "matched_python_files": matched,
                "packages": len(packages),
                "python_notices": len(notices),
                "browser": "first-party MIT host + OS-only frameworks",
            }
        )
    )


if __name__ == "__main__":
    main()
