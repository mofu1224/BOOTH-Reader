"""Exercise batch forwarding and manually opened WebUI in an owned copy."""

from __future__ import annotations

import ctypes
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    if not (ROOT.parent / "OWNED-BY-PORTABILITY-TEST.txt").is_file():
        raise SystemExit("Run this probe only in verify_portable.py's isolated copy")
    # Sweep leftovers from previous probes inside this owned copy only.
    for name in ("msedgewebview2.exe", "booth-webview-host.exe"):
        subprocess.run(
            ["taskkill", "/IM", name, "/T", "/F"], capture_output=True, timeout=30, check=False
        )
    cmd = Path(os.environ["SYSTEMROOT"]) / "System32/cmd.exe"
    env = dict(os.environ)
    for key in ("PYTHONHOME", "PYTHONPATH", "PIP_TARGET"):
        env[key] = str(ROOT.parent / "poison")
    env["PATH"] = str(Path(os.environ["SYSTEMROOT"]) / "System32")
    env["PYTHONUTF8"] = "1"

    def command(script: str, arguments: str) -> str:
        return f'"{cmd}" /d /s /c ""{ROOT / script}" {arguments}"'

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    cache = (ROOT / ".cache").resolve()
    (cache / "tmp").mkdir(parents=True, exist_ok=True)
    env["TMP"] = str(cache / "tmp")
    env["TEMP"] = str(cache / "tmp")

    def watchdog() -> None:
        time.sleep(360)
        managed = cache / "managed-web.log"
        print("--- probe watchdog: no completion within 360s ---", file=sys.stderr)
        if managed.is_file():
            tail = managed.read_text(encoding="utf-8", errors="replace").splitlines()[-60:]
            for line in tail:
                print(line, file=sys.stderr)
        os._exit(97)

    threading.Thread(target=watchdog, daemon=True).start()
    server = None
    browser = None
    with (cache / "managed-web.log").open("w", encoding="utf-8") as log:
        server = subprocess.Popen(
            command("start.bat", f"{port} --no-open"),
            cwd=ROOT.parent,
            env=env,
            stdout=log,
            stderr=log,
        )
        try:
            for _ in range(1800):
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1):
                        break
                except OSError as error:
                    if server.poll() is not None:
                        managed = cache / "managed-web.log"
                        detail = ""
                        if managed.is_file():
                            detail = "\n".join(
                                managed.read_text(encoding="utf-8", errors="replace").splitlines()[
                                    -15:
                                ]
                            )
                        raise RuntimeError(
                            f"managed web launcher stopped early (exit {server.poll()})\n{detail}"
                        ) from error
                    time.sleep(0.1)
            user = ctypes.WinDLL("user32", use_last_error=True)
            browser = subprocess.Popen(
                [
                    str(ROOT / ".venv/Scripts/python.exe"),
                    "-c",
                    "from contextlib import suppress\n"
                    "import sys\n"
                    "from playwright.sync_api import sync_playwright\n"
                    "from core.browser import launch_browser\n"
                    "p = sync_playwright().start()\n"
                    "b = launch_browser(p, headless=True)\n"
                    "print('CDP-PORT %d' % b.port, flush=True)\n"
                    "page = b.new_page(no_viewport=True)\n"
                    f"page.goto('http://127.0.0.1:{port}/')\n"
                    "assert 'BOOTH-Reader' in page.title()\n"
                    "print('PAGE-READY', flush=True)\n"
                    "sys.stdin.readline()\n"
                    "with suppress(Exception):\n"
                    "    b.close()\n"
                    "with suppress(Exception):\n"
                    "    p.stop()\n",
                ],
                cwd=ROOT,
                env=env | {"PYTHONHOME": "", "PYTHONPATH": ""},
                stdout=subprocess.PIPE,
                stderr=log,
                stdin=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )
            announcement = browser.stdout.readline().strip()
            assert announcement.startswith("CDP-PORT "), announcement
            cdp = int(announcement.split()[1])
            deadline = time.time() + 90
            while time.time() < deadline:
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{cdp}/json/version", timeout=2):
                        break
                except OSError:
                    if browser.poll() is not None:
                        raise RuntimeError("managed browser stopped before ready") from None
                    time.sleep(0.2)
            # Close only after the page finished loading; closing the window
            # mid-navigation aborts goto and looks like a browser crash.
            ready = browser.stdout.readline().strip()
            assert ready == "PAGE-READY", ready
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.QueryFullProcessImageNameW.argtypes = [
                wintypes.HANDLE,
                wintypes.DWORD,
                wintypes.LPWSTR,
                ctypes.POINTER(wintypes.DWORD),
            ]
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
            user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
            user.PostMessageW.argtypes = [
                wintypes.HWND,
                wintypes.UINT,
                wintypes.WPARAM,
                wintypes.LPARAM,
            ]
            closed = []

            @callback_type
            def close_window(window: int, param: int) -> bool:
                title = ctypes.create_unicode_buffer(1024)
                user.GetWindowTextW(window, title, len(title))
                if "BOOTH-Reader" not in title.value:
                    return True
                pid = wintypes.DWORD()
                user.GetWindowThreadProcessId(window, ctypes.byref(pid))
                process = kernel.OpenProcess(0x1000, False, pid.value)
                if not process:
                    return True
                try:
                    name = ctypes.create_unicode_buffer(32768)
                    length = wintypes.DWORD(len(name))
                    kernel.QueryFullProcessImageNameW(process, 0, name, ctypes.byref(length))
                    if Path(name.value).is_relative_to(ROOT):
                        user.PostMessageW(window, 0x0010, 0, 0)  # WM_CLOSE: normal browser shutdown
                        closed.append(pid.value)
                finally:
                    kernel.CloseHandle(process)
                return True

            for _ in range(600):
                user.EnumWindows(close_window, 0)
                if closed:
                    break
                time.sleep(0.1)
            # The managed browser must also close cleanly on request.
            browser.stdin.write("CLOSE\n")
            browser.stdin.flush()
            assert browser.wait(timeout=30) == 0
            assert server.poll() is None, "server stopped when browser closed"
            subprocess.run(["taskkill", "/PID", str(server.pid), "/T", "/F"], check=True)
            server.wait(timeout=30)
            with socket.socket() as sock:
                assert sock.connect_ex(("127.0.0.1", port)) != 0, (
                    "server leaked after terminal shutdown"
                )
        finally:
            if sys.exc_info()[0] is not None:
                managed = cache / "managed-web.log"
                if managed.is_file():
                    tail = managed.read_text(encoding="utf-8", errors="replace").splitlines()[-60:]
                    print("--- managed-web.log tail ---", file=sys.stderr)
                    for line in tail:
                        print(line, file=sys.stderr)
            if browser is not None and browser.poll() is None:
                browser.kill()
                browser.wait(timeout=10)
            if server is not None and server.poll() is None:
                subprocess.run(
                    ["taskkill", "/PID", str(server.pid), "/T", "/F"],
                    capture_output=True,
                    timeout=30,
                    check=False,
                )
                server.wait(timeout=10)
    cli = subprocess.run(
        command("start.bat", "cli lists list --json"),
        cwd=ROOT.parent,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    assert "lists" in json.loads(cli.stdout), cli.stdout
    report = {
        "batch_cli_json": "PASS",
        "manual_browser_open_close": "PASS",
        "server_port_closed": "PASS",
        "outside_cwd": str(ROOT.parent),
        "port": port,
    }
    (cache / "launcher-probe.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
