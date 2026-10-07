"""Supported portable targets and their checkout-relative runtime layout."""

from __future__ import annotations

import json
import platform
import sys
from pathlib import Path
from typing import Any

TARGETS = ("windows-x64", "macos-arm64")


def target_id(system: str | None = None, machine: str | None = None) -> str:
    system = sys.platform if system is None else system
    machine = (platform.machine() if machine is None else machine).lower()
    if system == "win32" and machine in {"amd64", "x86_64"}:
        return "windows-x64"
    if system == "darwin" and machine in {"arm64", "aarch64"}:
        return "macos-arm64"
    raise RuntimeError(f"Unsupported platform: {system}/{machine}; use Windows x64 or Mac arm64")


def manifest_path(root: Path, target: str | None = None) -> Path:
    target = target_id() if target is None else target
    if target not in TARGETS:
        raise ValueError(f"Unsupported portable target: {target}")
    return root / (
        "portable-manifest.json" if target == "windows-x64" else "portable/macos-arm64.json"
    )


def load_manifest(root: Path, target: str | None = None) -> dict[str, Any]:
    return dict(json.loads(manifest_path(root, target).read_text(encoding="utf-8")))


def python_relative(target: str | None = None) -> Path:
    target = target_id() if target is None else target
    return Path("python.exe" if target == "windows-x64" else "bin/python3")


def venv_relative(target: str | None = None) -> Path:
    target = target_id() if target is None else target
    return Path("Scripts/python.exe" if target == "windows-x64" else "bin/python3")


def site_packages(root: Path, target: str | None = None) -> Path:
    target = target_id() if target is None else target
    if target == "windows-x64":
        return root / ".venv/Lib/site-packages"
    return root / f".venv/lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages"


def launcher_name() -> str:
    return "start.bat" if target_id() == "windows-x64" else "bash ./start.sh"
