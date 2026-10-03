"""Portable environment defaults.

Every path BOOTH-Reader owns is resolved from the repository location, never
from a user profile, a system directory or a process-wide global install.
This module is the single place that defines those locations:

* ``PLAYWRIGHT_BROWSERS_PATH`` -- bundled WebView2 files (default:
  ``<repo>/.playwright-browsers`` instead of ``%USERPROFILE%``)
* ``PIP_CACHE_DIR`` / ``UV_CACHE_DIR`` -- package caches (``<repo>/.cache``)
* pytest / ruff / mypy caches -- ``<repo>/.cache`` (mirrors ``pyproject.toml``)

Values already present in the environment win over these defaults, so an
explicit override is always honoured. Nothing here touches the registry,
the system PATH or any persistent machine state.

The module uses only the standard library so ``tools/`` scripts and any
interpreter (including a bare system Python during bootstrap) can import it.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

# Directory names owned by the portable layout. Kept in one place so the
# batch launchers, the audit script and the tests agree on them.
VENV_DIR_NAME = ".venv"
TOOLS_PYTHON_DIR_NAME = ".tools"
BROWSERS_DIR_NAME = ".playwright-browsers"
CACHE_DIR_NAME = ".cache"


def repo_root(start: str | Path | None = None) -> Path:
    """Return the repository root: the directory holding ``cli.py``.

    ``cli.py`` lives at the root by contract (see ``web/cli_bridge.py`` and
    ``tools/repository_files.py``), so walking up from any file inside the repo
    finds it. Falls back to the current working directory when the marker
    cannot be found (for example inside a bare test sandbox).
    """
    here = Path(start).resolve() if start is not None else Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "cli.py").is_file():
            return candidate
    # Installed wheels still anchor to this module's location, never CWD.
    return Path(__file__).resolve().parent.parent


def browsers_path(root: str | Path | None = None) -> Path:
    """Where the bundled browser lives (inside the repo)."""
    return repo_root(root) / BROWSERS_DIR_NAME


def effective_browsers_path(root: str | Path | None = None) -> Path:
    """The browser directory actually in effect (explicit setting wins)."""
    explicit = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "").strip()
    return Path(explicit) if explicit else browsers_path(root)


def cache_dir(root: str | Path | None = None) -> Path:
    """Top of the repo-local cache tree (pip / uv / pytest / ruff / mypy)."""
    return repo_root(root) / CACHE_DIR_NAME


def portable_env(root: str | Path | None = None) -> dict[str, str]:
    """Environment defaults that keep every tool inside the repository."""
    base = repo_root(root)
    cache = base / CACHE_DIR_NAME
    return {
        # Browser binary: repo-local instead of %USERPROFILE%\AppData\Local.
        "PLAYWRIGHT_BROWSERS_PATH": str(base / BROWSERS_DIR_NAME),
        # Package caches: repo-local instead of %LOCALAPPDATA%.
        "PIP_CACHE_DIR": str(cache / "pip"),
        "UV_CACHE_DIR": str(cache / "uv"),
        # Tool caches: ruff/mypy honour these directly; pytest's cache_dir
        # is pinned in pyproject.toml (no env override exists for it).
        "RUFF_CACHE_DIR": str(cache / "ruff"),
        "MYPY_CACHE_DIR": str(cache / "mypy"),
        "TEMP": str(cache / "tmp"),
        "TMP": str(cache / "tmp"),
        "TMPDIR": str(cache / "tmp"),
        "XDG_CACHE_HOME": str(cache / "xdg"),
        "PIP_CONFIG_FILE": os.devnull,
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PYTHONNOUSERSITE": "1",
        # Japanese output stays readable on every console.
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
    }


def apply_portable_env(root: str | Path | None = None) -> dict[str, str]:
    """Fill unset variables from :func:`portable_env` and ensure directories.

    Returns the mapping of variables this call defaulted (explicitly set
    values are left untouched and not reported).
    """
    applied: dict[str, str] = {}
    for key, value in portable_env(root).items():
        if key in (
            "PYTHONUTF8",
            "PYTHONIOENCODING",
            "PIP_CONFIG_FILE",
            "PIP_DISABLE_PIP_VERSION_CHECK",
            "PYTHONNOUSERSITE",
        ):
            # Console encoding has no directory to create; just default it.
            if not os.environ.get(key):
                os.environ[key] = value
                applied[key] = value
            continue
        if not os.environ.get(key):
            os.environ[key] = value
            applied[key] = value
    for directory in (
        browsers_path(root),
        cache_dir(root),
        cache_dir(root) / "pip",
        cache_dir(root) / "uv",
        cache_dir(root) / "tmp",
    ):
        # A read-only checkout can still run from existing content;
        # directory creation is best-effort here.
        with contextlib.suppress(OSError):
            directory.mkdir(parents=True, exist_ok=True)
    return applied
