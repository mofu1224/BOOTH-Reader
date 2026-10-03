"""Shared portable-environment helpers for the setup/repair flow.

Standard-library only; the pinned local Python runs this before third-party
dependencies are installed. The batch launchers delegate
their environment decisions to this module instead of reimplementing them::

    .tools/python/python.exe tools/portable.py ensure
    .tools/python/python.exe tools/portable.py python
    .tools/python/python.exe tools/portable.py env

Only ``ensure`` writes anything. Everything else is read-only.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.portable import (  # noqa: E402
    BROWSERS_DIR_NAME,
    CACHE_DIR_NAME,
    TOOLS_PYTHON_DIR_NAME,
    VENV_DIR_NAME,
    apply_portable_env,
    portable_env,
)

SETUP_MARKER = ".setup-ok"


def venv_dir(root: Path = ROOT) -> Path:
    return root / VENV_DIR_NAME


def venv_python(root: Path = ROOT) -> Path:
    return venv_dir(root) / "Scripts" / "python.exe"


def tools_python(root: Path = ROOT) -> Path:
    """Bundled interpreter (``tools/fetch_python.py``), when present."""
    return root / TOOLS_PYTHON_DIR_NAME / "python" / "python.exe"


def candidate_pythons(root: Path = ROOT) -> list[list[str]]:
    """Only the pinned repo-local interpreter can create a portable venv."""
    bundled = tools_python(root)
    candidates: list[list[str]] = []
    if bundled.is_file():
        candidates.append([str(bundled)])
    return candidates


def venv_health(root: Path = ROOT) -> tuple[bool, str]:
    """Check the repo-local venv. Returns ``(ok, reason)``.

    A venv moved with the repository is detected here: ``sys.prefix`` must
    resolve inside the current checkout, otherwise the environment is stale
    and needs recreation (``pyvenv.cfg`` records absolute paths).
    """
    exe = venv_python(root)
    if not exe.is_file():
        return False, f"missing {exe.relative_to(root)}"
    # Inspect BEFORE execution: the Windows redirector otherwise launches the
    # old checkout's interpreter when that checkout still happens to exist.
    home = venv_base_home(root)
    if home is None or home.resolve() != tools_python(root).parent.resolve():
        return False, "venv base is missing or belongs to a different location"
    prefix = _venv_prefix(exe)
    if prefix is None:
        return False, "venv python would not start or reports no prefix"
    try:
        prefix.relative_to(root.resolve())
    except ValueError:
        return False, f"sys.prefix points outside the repo ({prefix})"
    if not (venv_dir(root) / "pyvenv.cfg").is_file():
        return False, "pyvenv.cfg missing"
    return True, f"ok ({prefix})"


def _venv_prefix(exe: Path) -> Path | None:
    """Ask a venv python for its ``sys.prefix``. ``None`` when unusable."""
    try:
        proc = subprocess.run(
            [str(exe), "-c", "import sys; print(sys.prefix)"],
            capture_output=True,
            text=True,
            timeout=60,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    try:
        return Path(proc.stdout.strip()).resolve()
    except OSError:
        return None


def venv_base_home(root: Path = ROOT) -> Path | None:
    """The base interpreter a venv was created from (``pyvenv.cfg``: ``home``)."""
    cfg = venv_dir(root) / "pyvenv.cfg"
    try:
        for line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() == "home":
                return Path(value.strip())
    except OSError:
        return None
    return None


def _is_outside_repo(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return False
    except (OSError, ValueError):
        return True


def _needs_rebase(root: Path = ROOT) -> bool:
    """True when the venv base lives outside the repo but bundled is available."""
    from tools.fetch_python import usable as bundled_usable

    if not bundled_usable():
        return False
    home = venv_base_home(root)
    return home is not None and _is_outside_repo(home, root)


def ensure_venv(root: Path = ROOT, recreate: bool = False) -> Path:
    """Create ``.venv`` when missing or stale. Idempotent; returns its python.

    A healthy venv whose base interpreter lives *outside* the repository is
    rebased onto the bundled interpreter (``tools/fetch_python.py``): it runs
    here, but it would break on any machine without that exact system Python.
    """
    ok, reason = venv_health(root)
    if ok and not recreate:
        if _needs_rebase(root):
            print(f"[portable] venv base is outside the repo; rebasing ({reason}) ...")
            recreate = True
        else:
            print(f"[portable] venv ok: {reason}")
            return venv_python(root)
    if venv_dir(root).exists() and (not ok or recreate):
        print(f"[portable] rebuilding venv ({reason}) ...")
        shutil.rmtree(venv_dir(root), ignore_errors=True)
    else:
        print("[portable] creating venv ...")
    last_error = ""
    for candidate in candidate_pythons(root):
        try:
            proc = subprocess.run(
                [*candidate, "-E", "-s", "-m", "venv", str(venv_dir(root))],
                capture_output=True,
                text=True,
                timeout=600,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as e:
            last_error = f"{' '.join(candidate)}: {type(e).__name__}: {e}"
            continue
        if proc.returncode == 0 and venv_python(root).is_file():
            print(f"[portable] venv created with {' '.join(candidate)}")
            return venv_python(root)
        last_error = (proc.stderr or proc.stdout)[-500:]
    raise SystemExit(
        "Could not create .venv. Run setup.bat to prepare pinned local Python. "
        f"\nLast error: {last_error}"
    )


def run(
    cmd: list[str],
    root: Path = ROOT,
    timeout: int = 900,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a child process with the portable environment applied."""
    env = dict(os.environ)
    for key, value in portable_env(root).items():
        env.setdefault(key, value)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        cmd,
        cwd=root,
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )


def setup_marker(root: Path = ROOT) -> Path:
    return venv_dir(root) / SETUP_MARKER


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if not args or args[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    command = args[0]
    if command == "python":
        print(ensure_venv() if "--ensure" in args else venv_python())
        return 0
    if command == "ensure":
        ensure_venv(recreate="--recreate" in args or "--repair" in args)
        return 0
    if command == "health":
        ok, reason = venv_health()
        print(("OK " if ok else "STALE ") + reason)
        return 0 if ok else 1
    if command == "env":
        apply_portable_env()
        for key in (
            "PLAYWRIGHT_BROWSERS_PATH",
            "PIP_CACHE_DIR",
            "UV_CACHE_DIR",
            "RUFF_CACHE_DIR",
            "MYPY_CACHE_DIR",
            "PYTHONUTF8",
            "PYTHONIOENCODING",
        ):
            print(f"{key}={os.environ.get(key, '')}")
        print(f"BOOTH_READER_VENV={venv_python()}")
        print(f"BOOTH_READER_BROWSERS={ROOT / BROWSERS_DIR_NAME}")
        print(f"BOOTH_READER_CACHE={ROOT / CACHE_DIR_NAME}")
        return 0
    print(f"unknown command: {command}\n{__doc__}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
