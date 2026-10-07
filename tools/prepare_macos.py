"""Maintainer-only acquisition of publisher-verified Apple Silicon inputs."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.platforms import load_manifest  # noqa: E402


def acquire(url: str, destination: Path, *, sha256: str) -> None:
    if not url.startswith("https://"):
        raise RuntimeError("Publisher inputs require HTTPS")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if (
        destination.is_file()
        and sha256
        and hashlib.sha256(destination.read_bytes()).hexdigest() == sha256
    ):
        return
    request = urllib.request.Request(url, headers={"User-Agent": "BOOTH-Reader-maintainer"})  # noqa: S310
    part = destination.with_suffix(destination.suffix + ".part")
    try:
        with urllib.request.urlopen(request, timeout=120) as response, part.open("wb") as output:  # noqa: S310
            while data := response.read(1024 * 1024):
                output.write(data)
        data = part.read_bytes()
        if sha256 and hashlib.sha256(data).hexdigest() != sha256:
            raise RuntimeError(f"Publisher SHA-256 mismatch: {destination.name}")
        part.replace(destination)
    finally:
        part.unlink(missing_ok=True)


def main() -> None:
    from packaging.tags import compatible_tags, cpython_tags, mac_platforms, parse_tag

    from tools.gen_lock import main as gen_lock

    spec = load_manifest(ROOT, "macos-arm64")
    python = spec["python"]
    acquire(python["url"], ROOT / ".cache/downloads" / python["asset"], sha256=python["sha256"])
    platforms = list(mac_platforms((14, 0), "arm64"))
    tags = list(cpython_tags((3, 12), platforms=platforms))
    tags += list(compatible_tags((3, 12), interpreter="cp312", platforms=platforms))
    ranks = {tag: rank for rank, tag in enumerate(tags)}
    versions = re.findall(
        r"^([\w.-]+)==([^\s\\]+)", (ROOT / "requirements-portable-lock.txt").read_text(), re.M
    )
    evidence = []
    wheelhouse = ROOT / spec["wheelhouse"]
    for name, version in versions:
        url = f"https://pypi.org/pypi/{name}/{version}/json"
        with urllib.request.urlopen(url, timeout=60) as response:
            metadata = json.load(response)
        candidates = []
        for entry in metadata["urls"]:
            if not entry["filename"].endswith(".whl"):
                continue
            suffix = "-".join(entry["filename"][:-4].split("-")[-3:])
            matches = [ranks[tag] for tag in parse_tag(suffix) if tag in ranks]
            if matches:
                candidates.append((min(matches), entry["filename"], entry))
        if not candidates:
            raise RuntimeError(f"No publisher macOS arm64 wheel: {name}=={version}")
        _, filename, entry = min(candidates)
        acquire(entry["url"], wheelhouse / filename, sha256=entry["digests"]["sha256"])
        evidence.append(
            {"name": filename, "url": entry["url"], "sha256": entry["digests"]["sha256"]}
        )
        print(f"Verified {filename}", flush=True)
    gen_lock([str(wheelhouse), str(ROOT / spec["lock"])])
    destination = ROOT / "license-audit/macos-publisher-inputs.json"
    report = json.loads(destination.read_text(encoding="utf-8")) if destination.is_file() else {}
    report.update({"python": python, "wheels": evidence})
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Mac Python/wheels verified. Prepare the signature-verified browser on a Mac.")


if __name__ == "__main__":
    main()
