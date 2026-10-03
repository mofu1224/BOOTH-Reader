"""Retain publisher-hash-verified MPL pathspec source and match every shipped .py."""

from __future__ import annotations

import io
import json
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.license_compliance import digest, dump, fetch, retain  # noqa: E402


def main() -> int:
    from tools.manage_portable import LOCK, WHEELS

    name, version = "pathspec", "1.1.1"
    metadata_url = f"https://pypi.org/pypi/{name}/{version}/json"
    metadata = json.loads(fetch(metadata_url))
    wheel = WHEELS / f"{name}-{version}-py3-none-any.whl"
    original = wheel.read_bytes()
    published = next(row for row in metadata["urls"] if row["filename"] == wheel.name)
    if (
        digest(original) != published["digests"]["sha256"]
        or digest(original) not in LOCK.read_text()
    ):
        raise RuntimeError("Wheel is not publisher/lock hash verified")
    source = next(row for row in metadata["urls"] if row["packagetype"] == "sdist")
    payload = fetch(source["url"])
    if digest(payload) != source["digests"]["sha256"]:
        raise RuntimeError("Source hash mismatch")
    matched = []
    with (
        tarfile.open(fileobj=io.BytesIO(payload)) as archive,
        zipfile.ZipFile(io.BytesIO(original)) as binary,
    ):
        members = {row.name.split("/", 1)[-1]: row for row in archive.getmembers() if row.isfile()}
        for path in binary.namelist():
            if path.startswith("pathspec/") and path.endswith(".py"):
                stream = archive.extractfile(members[path])
                if stream is None or stream.read() != binary.read(path):
                    raise RuntimeError("Source does not match shipped pathspec file")
                matched.append({"path": path, "sha256": digest(binary.read(path))})
        if not matched:
            raise RuntimeError("No preferred-source Python files verified")
        license_member = next(row for row in archive.getmembers() if row.name.endswith("/LICENSE"))
        stream = archive.extractfile(license_member)
        if stream is None:
            raise RuntimeError("Missing source license")
        notice = retain(f"{name}-{version}", license_member.name, stream.read(), source["url"])
    destination = ROOT / "SOURCE_OBLIGATIONS" / source["filename"]
    destination.write_bytes(payload)
    report = {
        "component": name,
        "version": version,
        "license": "MPL-2.0",
        "metadata_url": metadata_url,
        "wheel_sha256": digest(original),
        "source_url": source["url"],
        "source_path": destination.relative_to(ROOT).as_posix(),
        "source_sha256": digest(payload),
        "matched_source_files": matched,
        "notice": notice,
        "scope": "this exact pathspec wheel only; not whole-folder release clearance",
    }
    dump(ROOT / "license-audit/pathspec-source.json", report)
    print(
        json.dumps(
            {"component": name, "source_files_byte_identical": len(matched), "status": "PASS"}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
