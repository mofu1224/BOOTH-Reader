"""Portable library ledger paths, with legacy Windows/POSIX path recovery."""

from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath

PREFIX = "library:/"


def library_suffix(value: str) -> tuple[str, str] | None:
    path = (
        PureWindowsPath(value)
        if "\\" in value or PureWindowsPath(value).drive
        else PurePosixPath(value)
    )
    parts = path.parts
    if len(parts) < 3 or parts[-2] != "downloads":
        return None
    directory, filename = parts[-3], parts[-1]
    if directory in {".", "..", ""} or filename in {".", "..", ""}:
        return None
    return directory, filename


def record_path(path: Path, root: Path) -> str:
    relative = path.resolve().relative_to(root.resolve())
    return PREFIX + relative.as_posix()


def resolve_record(value: str, root: Path) -> Path | None:
    if value.startswith(PREFIX):
        relative = PurePosixPath(value[len(PREFIX) :])
        if relative.is_absolute() or ".." in relative.parts or "\\" in str(relative):
            raise ValueError("Invalid portable library path")
        target = root.joinpath(*relative.parts).resolve()
        if not target.is_relative_to(root.resolve()):
            raise ValueError("Library path points outside the output folder")
        return target
    suffix = library_suffix(value)
    if suffix is None:
        return None
    target = (root / suffix[0] / "downloads" / suffix[1]).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError("Library path points outside the output folder")
    return target
