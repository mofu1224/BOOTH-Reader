"""Pinned setup, local offline repair and launch orchestration (stdlib bootstrap)."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.portable import portable_env  # noqa: E402
from tools.portable import ensure_venv, setup_marker, venv_health, venv_python  # noqa: E402

MANIFEST = json.loads((ROOT / "portable-manifest.json").read_text(encoding="utf-8"))
LOCK = ROOT / MANIFEST["lock"]
WHEELS = ROOT / MANIFEST["wheelhouse"]
SNAPSHOT = ROOT / MANIFEST["browser"]["offlineSnapshot"]
RECEIPT = SNAPSHOT.with_suffix(".json")
PIP_PATCH = Path(__file__).with_name("pip_runtime_patch.py")


def digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def locked_versions() -> dict[str, str]:
    return dict(re.findall(r"^([\w.-]+)==([^\s\\]+)", LOCK.read_text(), re.M))


def child_env() -> dict[str, str]:
    env = dict(os.environ)
    # Bootstrap and official launchers enforce local tool state, independently
    # of inherited developer settings. Application CLI path options stay valid.
    for key in list(env):
        if key.upper().startswith(("PIP_", "PYTHON")) or key.upper() in {
            "NODE_OPTIONS",
            "NODE_PATH",
            "PLAYWRIGHT_NODEJS_PATH",
            "NODE_EXTRA_CA_CERTS",
            "PLAYWRIGHT_DOWNLOAD_HOST",
            "PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST",
            "SSL_CERT_FILE",
            "SSL_CERT_DIR",
            "REQUESTS_CA_BUNDLE",
        }:
            env.pop(key)
    env.update(portable_env(ROOT))
    env["HOME"] = str(ROOT / ".cache" / "home")
    env["USERPROFILE"] = env["HOME"]
    env["APPDATA"] = str(Path(env["HOME"]) / "AppData/Roaming")
    env["LOCALAPPDATA"] = str(Path(env["HOME"]) / "AppData/Local")
    env["HOMEDRIVE"] = Path(env["HOME"]).drive
    env["HOMEPATH"] = env["HOME"][len(env["HOMEDRIVE"]) :]
    env["PLAYWRIGHT_SKIP_BROWSER_GC"] = "1"
    env["PLAYWRIGHT_NODEJS_PATH"] = str(
        ROOT / ".venv" / "Lib" / "site-packages" / "playwright" / "driver" / "node.exe"
    )
    # Never search CWD or a developer PATH for a child executable/DLL.
    system = Path(env.get("SYSTEMROOT", r"C:\Windows"))
    env["PATH"] = os.pathsep.join(
        [
            str(ROOT / ".tools" / "python"),
            str(system / "System32"),
            str(system),
        ]
    )
    for path in (
        ROOT / ".cache" / "tmp",
        ROOT / ".cache" / "home",
        WHEELS,
        Path(env["APPDATA"]),
        Path(env["LOCALAPPDATA"]),
        # Windows file dialogs expand these locations under USERPROFILE.
        *(
            Path(env["HOME"]) / name
            for name in ("Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos")
        ),
    ):
        if not path.resolve().is_relative_to(ROOT.resolve()):
            raise RuntimeError(f"Generated path escapes portable checkout: {path}")
        path.mkdir(parents=True, exist_ok=True)
    return env


def call(
    args: list[str], *, capture: bool = False, timeout: float | None = None
) -> subprocess.CompletedProcess:
    result = subprocess.run(
        args,
        cwd=ROOT,
        env=child_env(),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=capture,
        stdout=None if capture else sys.stderr,
        stderr=None if capture else sys.stderr,
        check=False,
        timeout=timeout,
    )
    if result.returncode:
        if capture:
            print(result.stdout, file=sys.stderr)
            print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"Command failed ({result.returncode}): {args[:4]}")
    return result


def environment_ready() -> bool:
    if not venv_health(ROOT)[0] or not setup_marker().is_file():
        return False
    try:
        marker = json.loads(setup_marker().read_text(encoding="utf-8"))
        if marker["lock_sha256"] != digest(LOCK) or marker["root"] != str(ROOT):
            return False
        if marker.get("pip_patch_sha256") != digest(PIP_PATCH):
            return False
        code = (
            "import importlib.metadata as m, json, re; "
            "import httpx, bs4, fastapi, uvicorn, pydantic, playwright; "
            "print(json.dumps({re.sub(r'[-_.]+','-',d.metadata['Name'].lower()):d.version "
            "for d in m.distributions()}))"
        )
        installed = json.loads(call([str(venv_python()), "-s", "-c", code], capture=True).stdout)
        return all(installed.get(name) == ver for name, ver in locked_versions().items())
    except (OSError, KeyError, ValueError, RuntimeError):
        return False


def wheelhouse_ready() -> bool:
    # pip --require-hashes performs authoritative name/version/ABI checks at
    # installation. This preflight decides whether a network download is needed.
    wanted = set(re.findall(r"--hash=sha256:([0-9a-f]{64})", LOCK.read_text()))
    available = {digest(p) for p in WHEELS.glob("*.whl")}
    return wanted <= available


def install_environment(*, offline: bool, repair: bool) -> Path:
    if environment_ready() and not repair:
        print("[portable] pinned environment already ready", file=sys.stderr)
        return venv_python()
    if not wheelhouse_ready():
        from tools.vendor_payload import restore_wheels

        try:
            restore_wheels(ROOT)
        except (OSError, ValueError, RuntimeError) as error:
            raise RuntimeError(
                "Verified wheelhouse unavailable; restore vendor/ from the repository"
            ) from error
    # Move only disposable environment state, never DB/cookies/library. Keep the
    # old environment until installation+self-check succeeds; failures roll back.
    old = ROOT / ".venv"
    backup = ROOT / ".cache" / "tmp" / f"venv-backup-{time.time_ns()}"
    had_old = old.exists()
    if had_old:
        old.rename(backup)
    try:
        python = ensure_venv(ROOT)
        call(
            [
                str(python),
                "-s",
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-deps",
                "--no-compile",
                "--find-links",
                str(WHEELS),
                "--require-hashes",
                "-r",
                str(LOCK),
            ]
        )
        from tools.pip_runtime_patch import patch_wheel, update_ensurepip

        patched = patch_wheel(ROOT)
        call(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-deps",
                "--force-reinstall",
                str(patched),
            ]
        )
        update_ensurepip(ROOT, patched)
        call([str(python), "-s", "-m", "pip", "check"])
        setup_marker().write_text(
            json.dumps(
                {
                    "root": str(ROOT),
                    "lock_sha256": digest(LOCK),
                    "pip_patch_sha256": digest(PIP_PATCH),
                }
            ),
            encoding="utf-8",
        )
        if not environment_ready():
            raise RuntimeError("Installed environment failed version/import checks")
    except BaseException:
        if old.exists():
            shutil.rmtree(old)
        if had_old:
            backup.rename(old)
        raise
    if had_old:
        shutil.rmtree(backup)
    return python


def browser_files(python: Path) -> list[Path]:
    if MANIFEST["browser"].get("engine") == "webview2":
        return [
            ROOT / ".playwright-browsers/webview2/msedgewebview2.exe",
            ROOT / ".playwright-browsers/webview2-sdk/Microsoft.Web.WebView2.Core.dll",
            ROOT / ".playwright-browsers/webview2-sdk/Microsoft.Web.WebView2.WinForms.dll",
            ROOT / ".playwright-browsers/webview2-sdk/WebView2Loader.dll",
        ]
    registry = python.parent.parent / "Lib/site-packages/playwright/driver/package/browsers.json"
    entries = json.loads(registry.read_text(encoding="utf-8"))["browsers"]
    result = []
    for entry in entries:
        if entry["name"] == "chromium":
            result.append(
                ROOT
                / ".playwright-browsers"
                / f"chromium-{entry['revision']}"
                / "chrome-win64"
                / "chrome.exe"
            )
        if entry["name"] == "chromium-headless-shell":
            result.append(
                ROOT
                / ".playwright-browsers"
                / f"chromium_headless_shell-{entry['revision']}"
                / "chrome-headless-shell-win64"
                / "chrome-headless-shell.exe"
            )
    return result


def extract_snapshot(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as bundle:
        for entry in bundle.infolist():
            target = (destination / entry.filename).resolve()
            if not target.is_relative_to(destination.resolve()) or ":" in entry.filename:
                raise RuntimeError("Unsafe browser snapshot path")
            if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise RuntimeError("Browser snapshot must not contain symlinks")
        bundle.extractall(destination)


def ensure_browser(python: Path, *, offline: bool, repair: bool = False) -> None:
    files = browser_files(python)
    if len(files) not in {2, 4}:
        raise RuntimeError("Unexpected pinned browser registry layout")
    base = ROOT / ".playwright-browsers"
    if repair or not all(p.is_file() for p in files):
        from tools.vendor_payload import materialize

        # A hung health check can leave the app's WebView2 host holding the
        # runtime binary; release it before restoring the verified snapshot.
        subprocess.run(
            ["taskkill", "/IM", "booth-webview-host.exe", "/T", "/F"],
            capture_output=True,
            timeout=30,
            check=False,
        )
        materialize("browser", ROOT)
        materialize("browser-receipt", ROOT)
        if SNAPSHOT.is_file() and RECEIPT.is_file():
            saved = json.loads(RECEIPT.read_text(encoding="utf-8"))
            if saved["sha256"] != digest(SNAPSHOT):
                raise RuntimeError("Browser snapshot SHA-256 mismatch")
            extract_snapshot(SNAPSHOT, base)
        else:
            raise RuntimeError("Restore vendor/ from the repository; browser material is missing")
    code = (
        "from playwright.sync_api import sync_playwright; "
        "from core.browser import launch_browser; "
        "p=sync_playwright().start(); "
        "a=launch_browser(p, headless=True); "
        "page=a.new_page(); page.goto('data:text/html,<title>portable</title>'); "
        "assert page.title() == 'portable'; a.close(); p.stop()"
    )
    try:
        call([str(python), "-s", "-c", code], capture=True, timeout=150)
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        if repair:
            raise
        print(
            "[portable] browser health failed; restoring verified local snapshot", file=sys.stderr
        )
        ensure_browser(python, offline=True, repair=True)
        return
    if not SNAPSHOT.is_file():
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        part = SNAPSHOT.with_suffix(".part")
        with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as bundle:
            for path in sorted(base.rglob("*")):
                # .links holds absolute package paths and is unnecessary at run time.
                if path.is_file() and ".links" not in path.relative_to(base).parts:
                    bundle.write(path, path.relative_to(base).as_posix())
        part.replace(SNAPSHOT)
        RECEIPT.write_text(
            json.dumps(
                {
                    "sha256": digest(SNAPSHOT),
                    "playwright": MANIFEST["browser"]["version"],
                    "source": MANIFEST["browser"]["source"],
                    "publisher_signed": False,
                },
                indent=2,
            ),
            encoding="utf-8",
        )


def web(python: Path, args: list[str]) -> int:
    port = next((arg for arg in args if arg != "--no-open"), "8000")
    if not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise RuntimeError("Invalid web port")
    cmd = [str(python), "-s", str(ROOT / "cli.py"), "web", "--host", "127.0.0.1", "--port", port]
    print(f"Open in your browser: http://127.0.0.1:{port}/", flush=True)
    print("Keep this terminal open. Press Ctrl+C to stop the server.", flush=True)
    return subprocess.call(cmd, cwd=ROOT, env=child_env())


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    mode = args.pop(0) if args else "setup"
    # Rebase inherited temp settings before tempfile/Node are used.
    os.environ.update(child_env())
    try:
        from tools.fetch_sqlite import ensure_sqlite

        ensure_sqlite(offline=True)
        if mode == "setup":
            flags = {"--offline", "--repair", "--recreate", "--skip-browser", "--check", "--update"}
            if set(args) - flags:
                raise RuntimeError(f"Unknown setup flags: {set(args) - flags}")
            if "--check" in args:
                return 0 if environment_ready() else 1
            repair = "--repair" in args or "--recreate" in args
            python = install_environment(offline=True, repair=repair)
            if "--skip-browser" not in args:
                ensure_browser(python, offline=True, repair=repair)
            if not (ROOT / "app.db").exists():
                call([str(python), "-s", str(ROOT / "cli.py"), "init-db"])
            print("[OK] portable setup complete")
            return 0
        with contextlib.redirect_stdout(sys.stderr):
            python = install_environment(offline=True, repair=False)
            if (
                mode == "web"
                or (mode == "cli" and args[:2] == ["auth", "login"])
                or not all(path.is_file() for path in browser_files(python))
            ):
                ensure_browser(python, offline=True)
            if not (ROOT / "app.db").exists():
                call([str(python), "-s", str(ROOT / "cli.py"), "init-db"])
        if mode == "cli":
            return subprocess.call(
                [str(python), "-s", str(ROOT / "cli.py"), *(args or ["--help"])],
                cwd=ROOT,
                env=child_env(),
            )
        if mode == "web":
            return web(python, args)
        raise RuntimeError(f"Unknown mode: {mode}")
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
