"""Retain publisher-verified native package sources and locked Rust dependencies."""

from __future__ import annotations

import hashlib
import io
import json
import sys
import tarfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.license_compliance import NOTICE_RE, dump, fetch, retain  # noqa: E402


def source_package(package: dict) -> tuple[dict, list[dict]]:
    metadata = json.loads(
        fetch(f"https://pypi.org/pypi/{package['name']}/{package['version']}/json")
    )
    source = next((row for row in metadata["urls"] if row["packagetype"] == "sdist"), None)
    if source is None:
        if package["name"] != "playwright":
            raise RuntimeError(
                "No sdist: "
                + package["name"]
                + "; upstream="
                + json.dumps(metadata["info"].get("project_urls"))
            )
        reference = json.loads(
            fetch(
                f"https://api.github.com/repos/microsoft/playwright-python/git/ref/tags/v{package['version']}"
            )
        )["object"]
        if reference["type"] == "tag":
            reference = json.loads(
                fetch(
                    "https://api.github.com/repos/microsoft/playwright-python/git/tags/"
                    + reference["sha"]
                )
            )["object"]
        commit = reference["sha"]
        url = "https://api.github.com/repos/microsoft/playwright-python/tarball/" + commit
        payload = fetch(url)
        tree = json.loads(
            fetch(
                f"https://api.github.com/repos/microsoft/playwright-python/git/trees/{commit}?recursive=1"
            )
        )
        if tree.get("truncated"):
            raise RuntimeError("Upstream source tree is truncated")
        blobs = {row["path"]: row["sha"] for row in tree["tree"] if row["type"] == "blob"}
        with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
            for member in archive.getmembers():
                if member.isfile():
                    relative = member.name.split("/", 1)[-1]
                    stream = archive.extractfile(member)
                    data = stream.read()
                    git_hash = hashlib.sha1(
                        b"blob " + str(len(data)).encode() + b"\0" + data, usedforsecurity=False
                    ).hexdigest()
                    if blobs[relative] != git_hash:
                        raise RuntimeError("Git publisher source blob mismatch")
        source = {
            "url": url,
            "filename": f"playwright-python-{package['version']}-upstream.tar.gz",
            "digests": {"sha256": hashlib.sha256(payload).hexdigest()},
            "git_commit": commit,
        }
    else:
        payload = fetch(source["url"])
    if hashlib.sha256(payload).hexdigest() != source["digests"]["sha256"]:
        raise RuntimeError("Native sdist publisher SHA-256 mismatch")
    destination = ROOT / "SOURCE_OBLIGATIONS/native" / source["filename"]
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    locks, notices = [], []
    with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            stream = archive.extractfile(member)
            if stream is None:
                raise RuntimeError("Missing source member")
            if NOTICE_RE.search(Path(member.name).name):
                notices.append(
                    retain(
                        package["name"] + "-" + package["version"],
                        member.name,
                        stream.read(),
                        source["url"],
                    )
                )
            elif member.name.endswith("/Cargo.lock"):
                locks.extend(tomllib.loads(stream.read().decode())["package"])
    return {
        "name": package["name"],
        "version": package["version"],
        "native_files": package["native_files"],
        "source": destination.relative_to(ROOT).as_posix(),
        "source_url": source["url"],
        "sha256": source["digests"]["sha256"],
        "git_commit": source.get("git_commit"),
        "notices": notices,
    }, locks


def crate_source(package: dict) -> dict:
    name, version = package["name"], package["version"]
    url = f"https://static.crates.io/crates/{name}/{name}-{version}.crate"
    payload = fetch(url)
    if hashlib.sha256(payload).hexdigest() != package["checksum"]:
        raise RuntimeError("Rust Cargo.lock publisher checksum mismatch")
    destination = ROOT / "SOURCE_OBLIGATIONS/rust-lock" / f"{name}-{version}.crate"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    notices = []
    with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
        manifest = archive.extractfile(f"{name}-{version}/Cargo.toml")
        if manifest is None:
            raise RuntimeError("Missing crate manifest")
        identity = tomllib.loads(manifest.read().decode())["package"]
        for member in archive.getmembers():
            if member.isfile() and NOTICE_RE.search(Path(member.name).name):
                stream = archive.extractfile(member)
                if stream:
                    notices.append(
                        retain("rust-" + name + "-" + version, member.name, stream.read(), url)
                    )
    return {
        "name": name,
        "version": version,
        "declared_license": identity.get(
            "license", "license-file: " + identity.get("license-file", "UNSPECIFIED")
        ),
        "source": destination.relative_to(ROOT).as_posix(),
        "source_url": url,
        "sha256": package["checksum"],
        "notices": notices,
    }


def main() -> None:
    packages = json.loads((ROOT / "license-audit/packages.json").read_text(encoding="utf-8"))
    native = [package for package in packages if package["native_files"]]
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(source_package, native))
    lock = {
        (row["name"], row["version"]): row
        for _, rows in results
        for row in rows
        if row.get("source", "").startswith("registry+") and row.get("checksum")
    }
    with ThreadPoolExecutor(max_workers=8) as pool:
        crates = list(pool.map(crate_source, lock.values()))
    dump(
        ROOT / "license-audit/native-source-evidence.json",
        {
            "native_packages": [row for row, _ in results],
            "locked_rust_dependencies": crates,
            "scope": "matching native release sdists and conservative full locked Rust source closure, including inactive build/test dependencies",
        },
    )
    print(
        json.dumps(
            {
                "native_package_sources": len(results),
                "cargo_locked_crate_sources": len(crates),
                "licenses": sorted({row["declared_license"] for row in crates}),
            }
        )
    )


if __name__ == "__main__":
    main()
