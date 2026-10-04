"""Fetch the bundled Windows Python into ``.tools/python``.

The repository stays usable without a system-wide Python install: a pinned
``python-build-standalone`` release (CPython 3.12, ``install_only``) is
downloaded over TLS, verified against a pinned SHA-256, and extracted inside
the repo. ``tools/portable.py`` then prefers it as the base interpreter for
``.venv``. The official setup uses OS-only ``tools/bootstrap.ps1`` first;
this standard-library helper remains available for developer tooling.

Usage:
    python tools/fetch_python.py           # fetch when missing (idempotent)
    python tools/fetch_python.py --check   # exit 0 when usable, 1 otherwise
    python tools/fetch_python.py --force   # re-download and re-extract

Only ``.tools/`` and ``.cache/downloads/`` are written. Nothing outside the
repository is touched. When download fails the helper exits non-zero. Official
launchers never fall back to a system interpreter.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Pinned distribution. Update the three values together from
# https://github.com/astral-sh/python-build-standalone/releases and keep the
# digest in sync with the asset's published sha256.
_PYTHON: dict[str, str] = json.loads((ROOT / "portable-manifest.json").read_text(encoding="utf-8"))[
    "python"
]
PBS_RELEASE = _PYTHON["release"]
PBS_PYTHON_VERSION = _PYTHON["version"]
PBS_ASSET = _PYTHON["asset"]
PBS_URL = _PYTHON["url"]
PBS_SHA256 = _PYTHON["sha256"]
PBS_SIZE = int(_PYTHON.get("size", 45842109))

TARGET_DIR = ROOT / ".tools" / "python"
TARGET_EXE = TARGET_DIR / "python.exe"
DOWNLOAD_DIR = ROOT / ".cache" / "downloads"
ARCHIVE = DOWNLOAD_DIR / PBS_ASSET

CHUNK = 1 << 20


def bundled_version() -> str | None:
    """``X.Y.Z`` reported by the bundled interpreter, or ``None``."""
    if not TARGET_EXE.is_file():
        return None
    try:
        proc = subprocess.run(
            [str(TARGET_EXE), "--version"],
            capture_output=True,
            text=True,
            timeout=120,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    parts = (proc.stdout or proc.stderr).strip().split()
    return parts[1] if len(parts) == 2 and parts[0] == "Python" else None


def usable() -> bool:
    """True when the bundled interpreter runs and can create venvs."""
    if bundled_version() != PBS_PYTHON_VERSION:
        return False
    try:
        proc = subprocess.run(
            [str(TARGET_EXE), "-c", "import ensurepip, venv; print('ok')"],
            capture_output=True,
            text=True,
            timeout=120,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0 and "ok" in proc.stdout


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def download() -> Path:
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    if _PYTHON.get("derived"):
        from tools.vendor_payload import materialize

        return materialize("python", ROOT)
    if ARCHIVE.is_file():
        try:
            if ARCHIVE.stat().st_size == PBS_SIZE and sha256_of(ARCHIVE) == PBS_SHA256:
                print(f"[fetch] reusing cached {PBS_ASSET}")
                return ARCHIVE
        except OSError:
            pass
        ARCHIVE.unlink(missing_ok=True)
    print(f"[fetch] downloading {PBS_ASSET} ({PBS_SIZE / 1024**2:.1f} MiB) ...")
    tmp = ARCHIVE.with_suffix(ARCHIVE.suffix + ".part")
    if urllib.parse.urlsplit(PBS_URL).scheme != "https":
        raise SystemExit("[fetch] refusing non-HTTPS distribution URL")
    # The URL is a pinned module constant and its scheme is asserted above.
    request = urllib.request.Request(PBS_URL, headers={"User-Agent": "BOOTH-Reader-setup"})  # noqa: S310 - HTTPS asserted above
    try:
        with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
            total = int(response.headers.get("Content-Length") or PBS_SIZE)
            received = 0
            with tmp.open("wb") as fh:
                while True:
                    block = response.read(CHUNK)
                    if not block:
                        break
                    fh.write(block)
                    received += len(block)
                    percent = min(100, received * 100 // max(1, total))
                    print(f"\r[fetch] {percent:3d}% ({received // 1024**2} MiB)", end="")
        print()
    except Exception as e:  # network errors are all equally fatal here
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)
        raise SystemExit(f"[fetch] download failed ({type(e).__name__}: {e})") from e
    actual = sha256_of(tmp)
    if actual != PBS_SHA256:
        tmp.unlink(missing_ok=True)
        raise SystemExit(
            "[fetch] SHA-256 mismatch: the download is corrupt or was tampered "
            f"with.\nexpected {PBS_SHA256}\nactual   {actual}"
        )
    tmp.replace(ARCHIVE)
    print("[fetch] SHA-256 verified")
    return ARCHIVE


def extract(archive: Path) -> None:
    print(f"[fetch] extracting to {TARGET_DIR.relative_to(ROOT)} ...")
    # Portable: scratch space lives inside the repo (.cache/tmp), never in
    # %TEMP%. The directory is removed afterwards; a crash leaves at most a
    # repo-local leftover that start.bat can safely delete on the next run.
    tmp_base = ROOT / ".cache" / "tmp"
    tmp_base.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="booth-python-", dir=str(tmp_base)))
    try:
        with tarfile.open(archive, "r:gz") as tar:
            # "data" filter: refuse absolute paths, .. escapes and devices.
            tar.extractall(scratch, filter="data")
        inner = scratch / "python"
        if not (inner / "python.exe").is_file():
            raise SystemExit("[fetch] unexpected archive layout (no python/python.exe)")
        if TARGET_DIR.exists():
            shutil.rmtree(TARGET_DIR, ignore_errors=True)
        TARGET_DIR.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(inner), str(TARGET_DIR))
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    if not usable():
        raise SystemExit("[fetch] extracted interpreter failed its self-check")
    print(f"[fetch] bundled Python {PBS_PYTHON_VERSION} ready")


def main(argv: list[str] | None = None) -> int:
    args = set(argv if argv is not None else sys.argv[1:])
    if "--check" in args:
        print(f"bundled python: {bundled_version() or 'missing'} (want {PBS_PYTHON_VERSION})")
        return 0 if usable() else 1
    if usable() and "--force" not in args:
        print(f"[fetch] bundled Python {PBS_PYTHON_VERSION} already present")
        return 0
    try:
        archive = download()
    except SystemExit as e:
        print(e, file=sys.stderr)
        print("[fetch] pinned local interpreter unavailable", file=sys.stderr)
        return 1
    try:
        extract(archive)
    except SystemExit as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
