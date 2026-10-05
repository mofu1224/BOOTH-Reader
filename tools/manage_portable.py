"""Pinned setup, local offline repair and launch orchestration (stdlib bootstrap)."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
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
SETUP_FLAGS = {"--offline", "--repair", "--recreate", "--skip-browser", "--check", "--update"}
RESTORE_FLAGS = {"--repair", "--recreate", "--update"}
RESTORE_HINT_MARKERS = ("同梱", "vendor", "ブラウザ", "wheelhouse", "wheel")
LAUNCHER_REDIRECTS = {
    "repair": ("setup", "--repair"),
    "update": ("setup", "--update"),
    "help": ("cli", "--help"),
    "--help": ("cli", "--help"),
    "-h": ("cli", "--help"),
    "-?": ("cli", "--help"),
    "/?": ("cli", "--help"),
    "?": ("cli", "--help"),
    "version": ("cli", "--version"),
    "--version": ("cli", "--version"),
}
DEFAULT_WEB_PORT = 8000
WEB_PORT_SCAN_LIMIT = 20
BROWSER_WAIT_SECONDS = 60


def resolve_mode(args: list[str]) -> tuple[str, list[str]]:
    """Route the single launcher's arguments to an internal mode.

    ``start.bat`` forwards every argument unchanged, so the setup/browser
    logic itself decides what has to run. Empty or numeric input opens the
    Web UI, setup flags repair it, and anything else is a CLI command.
    Common Windows spellings (``/?``, ``-?``, ``version``) are accepted so a
    user who does not know the interface still lands on the help text.
    """
    if not args:
        return "web", []
    head = args[0].lower()
    if head in {"web", "cli", "setup"}:
        return head, args[1:]
    if head in LAUNCHER_REDIRECTS:
        mode, flag = LAUNCHER_REDIRECTS[head]
        return mode, [flag, *args[1:]]
    if head in SETUP_FLAGS:
        return "setup", args
    if head.isdecimal() or head in {"--no-open", "--port"}:
        return "web", args
    return "cli", args


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
        print("[portable] 準備済み", file=sys.stderr)
        return venv_python()
    if not wheelhouse_ready():
        from tools.vendor_payload import restore_wheels

        try:
            restore_wheels(ROOT)
        except (OSError, ValueError, RuntimeError) as error:
            raise RuntimeError(
                "同梱の依存パッケージ (vendor/) が欠損・破損。再クローンしてください。"
                "app.db・data・BOOTH-Reader-Library は保持してください。"
            ) from error
    # Move only disposable environment state, never DB/cookies/library. Keep the
    # old environment until installation+self-check succeeds; failures roll back.
    old = ROOT / ".venv"
    backup = ROOT / ".cache" / "tmp" / f"venv-backup-{time.time_ns()}"
    had_old = old.exists()
    if had_old:
        try:
            old.rename(backup)
        except OSError as error:
            raise RuntimeError(
                ".venv が使用中です。BOOTH-ReaderをCtrl+Cで終了してから再実行してください。"
                "DB・Cookie・購入物は保持します。"
            ) from error
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
            raise RuntimeError(
                "固定環境の検証に失敗しました。もう一度 start.bat --repair を実行してください。"
            )
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
                raise RuntimeError("同梱ブラウザーの内容が不正です (不正なパス)")
            if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise RuntimeError("同梱ブラウザーの内容が不正です (シンボリックリンク)")
        bundle.extractall(destination)


def ensure_browser(python: Path, *, offline: bool, repair: bool = False) -> None:
    files = browser_files(python)
    if len(files) not in {2, 4}:
        raise RuntimeError(
            "同梱ブラウザーの構成が想定と異なります。リポジトリを git clone し直してください。"
        )
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
                raise RuntimeError("同梱ブラウザーのハッシュ不一致。再クローンしてください。")
            extract_snapshot(SNAPSHOT, base)
        else:
            raise RuntimeError(
                "同梱ブラウザー (vendor/) がありません。再クローンしてください。"
                "app.db・data・BOOTH-Reader-Library は保持してください。"
            )
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
            "[portable] ブラウザー起動失敗。同梱原本から復元します",
            file=sys.stderr,
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


def parse_web_args(args: list[str]) -> tuple[int, bool]:
    port = "8000"
    open_browser = True
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--no-open":
            open_browser = False
            index += 1
        elif arg == "--port":
            if index + 1 >= len(args):
                raise RuntimeError("ポート番号がありません (例: start.bat --port 8000)")
            port = args[index + 1]
            index += 2
        elif arg.isdecimal():
            port = arg
            index += 1
        else:
            raise RuntimeError(
                f"web起動のオプションが不明です: {arg} (使い方: start.bat [ポート番号] [--no-open])"
            )
    if not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise RuntimeError("ポート番号は1〜65535で指定してください")
    return int(port), open_browser


def existing_web_instance(port: int) -> bool:
    """True when a BOOTH-Reader Web UI already answers on the loopback port."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as response:
            if response.status != 200:
                return False
            payload = json.loads(response.read(4096))
    except (OSError, ValueError, AttributeError):
        return False
    return payload.get("ok") is True and "transport" in payload


def port_listening(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.25)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def find_existing_web_instance(preferred: int) -> int | None:
    """An already-running instance near the preferred port, fallback included."""
    for candidate in range(preferred, min(preferred + WEB_PORT_SCAN_LIMIT, 65536)):
        if port_listening(candidate) and existing_web_instance(candidate):
            return candidate
    return None


def pick_free_port(preferred: int) -> int:
    """The preferred port, or the next free one when something else holds it."""
    for candidate in range(preferred, min(preferred + WEB_PORT_SCAN_LIMIT, 65536)):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", candidate))
            except OSError:
                continue
        return candidate
    raise RuntimeError(f"No free port found near {preferred}")


def open_web_browser(url: str) -> None:
    with contextlib.suppress(OSError, webbrowser.Error):
        webbrowser.open(url)


def schedule_web_browser(port: int) -> None:
    """Open the default browser once the server actually answers."""
    threading.Thread(target=_open_when_ready, args=(port,), daemon=True).start()


def _open_when_ready(port: int) -> None:
    deadline = time.monotonic() + BROWSER_WAIT_SECONDS
    while time.monotonic() < deadline:
        if existing_web_instance(port):
            open_web_browser(f"http://127.0.0.1:{port}/")
            return
        time.sleep(0.25)


def web(python: Path, args: list[str]) -> int:
    port, open_browser = parse_web_args(args)
    running = find_existing_web_instance(port)
    if running is not None:
        url = f"http://127.0.0.1:{running}/"
        print(f"[OK] すでに起動しています: {url}", flush=True)
        print("このウィンドウは閉じて構いません。", flush=True)
        if open_browser:
            open_web_browser(url)
        return 0
    served = pick_free_port(port)
    url = f"http://127.0.0.1:{served}/"
    if served != port:
        print(f"[portable] ポート {port} 使用中 → {served}", flush=True)
    cmd = [
        str(python),
        "-s",
        str(ROOT / "cli.py"),
        "web",
        "--host",
        "127.0.0.1",
        "--port",
        str(served),
    ]
    print(f"Web UI: {url}", flush=True)
    print("この画面は閉じず、Ctrl+Cで終了。", flush=True)
    print(f"保存先: {ROOT / 'BOOTH-Reader-Library'}", flush=True)
    if open_browser:
        schedule_web_browser(served)
    return subprocess.call(cmd, cwd=ROOT, env=child_env())


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    # bootstrap.ps1 always forwards its mode first; only "auto" needs routing.
    mode = args.pop(0) if args else "auto"
    if mode == "auto":
        mode, args = resolve_mode(args)
    if mode == "web":
        print(
            "[portable] 準備確認中 (初回は時間がかかります)",
            file=sys.stderr,
            flush=True,
        )
    # Rebase inherited temp settings before tempfile/Node are used.
    os.environ.update(child_env())
    try:
        from tools.fetch_sqlite import ensure_sqlite

        ensure_sqlite(offline=True)
        if mode == "setup":
            unknown = set(args) - SETUP_FLAGS
            if unknown:
                raise RuntimeError(
                    "セットアップのオプションが不明です: "
                    f"{', '.join(sorted(unknown))} "
                    "(--repair / --recreate / --update / --check / --skip-browser)"
                )
            if "--check" in args:
                ready = environment_ready()
                print(
                    "[OK] 準備済み。start.bat で起動"
                    if ready
                    else "[portable] まだ準備されていません。 start.bat で自動準備。",
                    file=sys.stderr,
                )
                return 0 if ready else 1
            if RESTORE_FLAGS & set(args):
                running = find_existing_web_instance(DEFAULT_WEB_PORT)
                if running is not None:
                    raise RuntimeError(
                        f"起動中です (http://127.0.0.1:{running}/)。Ctrl+Cで終了後、再実行してください。"
                        "DB・Cookie・購入物は保持します。"
                    )
            repair = "--repair" in args or "--recreate" in args
            python = install_environment(offline=True, repair=repair)
            if "--skip-browser" not in args:
                ensure_browser(python, offline=True, repair=repair)
            if not (ROOT / "app.db").exists():
                call([str(python), "-s", str(ROOT / "cli.py"), "init-db"])
            print("[OK] 準備完了 (DB・Cookie・購入物は保持)")
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
        raise RuntimeError(f"内部モードが不明です: {mode}")
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        if any(marker in str(error) for marker in RESTORE_HINT_MARKERS):
            print(
                "[ヒント] vendor欠損・破損は別フォルダーへ再クローン。"
                "app.db・data・BOOTH-Reader-Library は保持してください。",
                file=sys.stderr,
            )
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
