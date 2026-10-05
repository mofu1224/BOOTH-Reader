"""Enumerate the complete clone candidate without changing the user's Git index."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from tools.check_release_hygiene import private_path

ROOT = Path(__file__).resolve().parent.parent
GATE = "license-audit/release-gate.json"
MAX_RELATIVE_PATH_UNITS = 180  # 78-unit checkout root + separator + path < MAX_PATH.


def collect(root: Path = ROOT) -> list[Path]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        capture_output=True,
        check=True,
        timeout=60,
    )
    names = sorted(set(result.stdout.decode("utf-8").rstrip("\0").split("\0")) - {""})
    manifest = root / "vendor/windows-x64/manifest.json"
    active_chunks = None
    if manifest.is_file():
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        active_chunks = {
            part["file"] for asset in payload["assets"].values() for part in asset["parts"]
        }
    files = []
    for name in names:
        path = root / name
        if private_path(name):
            raise SystemExit(
                "Clone candidate contains a private path; run check_release_hygiene.py"
            )
        if (
            name.startswith("vendor/")
            and path.suffix == ".chunk"
            and active_chunks is not None
            and path.name not in active_chunks
        ):
            raise SystemExit("Clone candidate contains an inactive vendor chunk")
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise SystemExit("Clone candidate contains a link or path outside the repository")
        if not path.exists():
            continue  # A worktree deletion is part of the candidate.
        if len(name.encode("utf-16-le")) // 2 > MAX_RELATIVE_PATH_UNITS:
            raise SystemExit(f"Clone candidate path is too long for Windows copying: {name}")
        if not path.is_file():
            raise SystemExit("Clone candidate contains a submodule or non-file entry")
        if path.stat().st_size >= 100 * 1024 * 1024:
            raise SystemExit("Clone candidate exceeds GitHub's per-file size limit")
        files.append(path)
    return files


def sha256(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def input_hashes(files: list[Path], root: Path = ROOT) -> dict[str, str]:
    selected = [path for path in files if path != root / GATE]
    if not selected:
        return {}
    names = [path.relative_to(root).as_posix() for path in selected]
    result = subprocess.run(
        ["git", "-C", str(root), "check-attr", "-z", "--stdin", "text", "eol"],
        input=("\0".join(names) + "\0").encode("utf-8"),
        capture_output=True,
        check=True,
        timeout=60,
    )
    fields = result.stdout.decode("utf-8").rstrip("\0").split("\0")
    attributes: dict[str, dict[str, str]] = {}
    for offset in range(0, len(fields), 3):
        name, key, value = fields[offset : offset + 3]
        attributes.setdefault(name, {})[key] = value
    hashes = {}
    for path, name in zip(selected, names, strict=True):
        attrs = attributes[name]
        text = attrs.get("text")
        if text == "unset":
            hashes[name] = sha256(path)
            continue
        data = path.read_bytes()
        if (
            text == "set"
            or attrs.get("eol") in {"lf", "crlf"}
            or (text == "auto" and b"\0" not in data[:8000])
        ):
            data = data.replace(b"\r\n", b"\n")
        hashes[name] = hashlib.sha256(data).hexdigest()
    return hashes


def require_release_clearance(files: list[Path], root: Path = ROOT) -> None:
    gate = root / GATE
    if not gate.is_file():
        raise SystemExit("license clearance missing")
    report = json.loads(gate.read_text(encoding="utf-8"))
    if report.get("release_status") != "READY FOR RELEASE" or report.get("blockers") != []:
        raise SystemExit("license clearance BLOCKED")
    if report.get("scope") != "github-repository-clone":
        raise SystemExit("license clearance has the wrong distribution scope")
    if input_hashes(files, root) != report.get("input_hashes"):
        raise SystemExit("license clearance stale; re-audit current Git candidate")
