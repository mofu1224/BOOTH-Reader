"""Create a private source candidate for remote tests, never copy user data."""

from __future__ import annotations

import argparse
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.repository_files import collect  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-mac-inputs", action="store_true")
    parser.add_argument("--source-only", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to((ROOT / ".cache").resolve()):
        raise RuntimeError("Private candidates must stay in .cache")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(args.output, "w:gz") as archive:
        for path in collect(ROOT):
            if args.source_only and path.suffix == ".chunk":
                continue
            info = archive.gettarinfo(str(path), path.relative_to(ROOT).as_posix())
            if path.suffix in {".sh", ".command"}:
                info.mode = 0o755
            with path.open("rb") as source:
                archive.addfile(info, source)
        if args.with_mac_inputs:
            inputs = list((ROOT / ".cache/wheels-macos-arm64").glob("*.whl"))
            inputs += [
                ROOT
                / ".cache/downloads/cpython-3.12.15+20261003-aarch64-apple-darwin-install_only.tar.gz",
            ]
            for path in inputs:
                archive.add(path, path.relative_to(ROOT).as_posix(), recursive=False)
    print(
        f"Private candidate: {args.output.resolve().relative_to(ROOT)} ({args.output.stat().st_size} bytes)"
    )


if __name__ == "__main__":
    main()
