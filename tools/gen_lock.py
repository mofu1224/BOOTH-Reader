"""Generate hash-pinned requirements from a pip-download wheel directory."""

from __future__ import annotations

import argparse
import hashlib
import re
import zipfile
from email.parser import Parser
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheels", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    packages: dict[str, tuple[str, set[str]]] = {}
    for wheel in sorted(args.wheels.glob("*.whl")):
        with zipfile.ZipFile(wheel) as archive:
            metadata_files = [
                n
                for n in archive.namelist()
                if n.endswith(".dist-info/METADATA") and len(n.split("/")) == 2
            ]
            if len(metadata_files) != 1:
                raise SystemExit(f"invalid wheel metadata: {wheel.name}")
            metadata = Parser().parsestr(archive.read(metadata_files[0]).decode("utf-8"))
        name = metadata.get("Name", "")
        version = metadata.get("Version", "")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name) or not re.fullmatch(
            r"[A-Za-z0-9.!+_-]+", version
        ):
            raise SystemExit(f"invalid package identity: {wheel.name}")
        name = re.sub(r"[-_.]+", "-", name).lower()
        if name in packages and packages[name][0] != version:
            raise SystemExit(f"multiple versions downloaded: {name}")
        packages.setdefault(name, (version, set()))[1].add(
            hashlib.sha256(wheel.read_bytes()).hexdigest()
        )
    if not packages:
        raise SystemExit("no wheels found")
    lines = ["# Generated from downloaded wheels by tools/gen_lock.py; do not hand-edit.", ""]
    for name, (version, hashes) in sorted(packages.items()):
        lines.append(f"{name}=={version} \\")
        values = sorted(hashes)
        lines.extend(
            f"    --hash=sha256:{digest}" + (" \\" if i < len(values) - 1 else "")
            for i, digest in enumerate(values)
        )
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"locked {len(packages)} packages: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
