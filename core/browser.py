"""Portable WebView2 host with Playwright's loopback CDP transport.

The WebView2 SDK's WinForms assembly targets .NET Framework 4.x, so the host is
a small exe compiled once by ``start.bat`` from ``tools/webview_host.cs`` using
the OS ``csc.exe``. Playwright talks to it over loopback CDP, which keeps the
same ``sync_playwright`` API for both login and tests.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from core.platforms import load_manifest
from core.portable import portable_env

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger("booth_reader.browser")


class HostedContext:
    def __init__(self, context: Any, viewport: dict[str, Any] | None = None) -> None:
        self.context = context
        self.viewport = viewport

    def new_page(self) -> Any:
        page = self.context.pages[0]
        if self.viewport:
            page.set_viewport_size(self.viewport)
        return page

    def __getattr__(self, name: str) -> Any:
        return getattr(self.context, name)


class HostedBrowser:
    def __init__(
        self, browser: Any, process: subprocess.Popen[Any], profile: Path, port: int
    ) -> None:
        self.browser, self.process, self.profile, self.port = browser, process, profile, port

    def new_context(self, **options: Any) -> HostedContext:
        return HostedContext(self.browser.contexts[0], options.get("viewport"))

    def new_page(self, **options: Any) -> Any:
        return self.new_context(**options).new_page()

    def __getattr__(self, name: str) -> Any:
        return getattr(self.browser, name)

    def __enter__(self) -> HostedBrowser:
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()

    def close(self) -> None:
        terminate_host(self.process)
        with contextlib.suppress(Exception):
            self.browser.close()
        remove_profile(self.profile)


def remove_profile(profile: Path) -> None:
    for attempt in range(30):
        try:
            shutil.rmtree(profile)
            return
        except FileNotFoundError:
            return
        except PermissionError:
            if attempt == 29:
                raise
            time.sleep(0.1)


def terminate_host(process: subprocess.Popen[Any]) -> None:
    system = Path(os.environ.get("SYSTEMROOT", r"C:\Windows"))
    if process.poll() is None:
        subprocess.run(  # noqa: S603 - owned child tree, fixed OS tool
            [str(system / "System32/taskkill.exe"), "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            timeout=30,
            check=False,
        )
    process.wait(timeout=30)


def webview_runtime_root() -> Path:
    return ROOT / ".playwright-browsers/webview2"


def browser_env() -> dict[str, str]:
    """Environment for the browser child: every writable location is repo-local.

    WebView2 writes crashpad and user-data state through the profile variables,
    so an inherited (or deliberately unusable) user profile would either leak
    outside the checkout or fail startup before the CDP endpoint opens.
    """
    env = dict(os.environ)
    env.update(portable_env(ROOT))
    home = ROOT / ".cache/home"
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["APPDATA"] = str(home / "AppData/Roaming")
    env["LOCALAPPDATA"] = str(home / "AppData/Local")
    for path in (home, Path(env["APPDATA"]), Path(env["LOCALAPPDATA"])):
        path.mkdir(parents=True, exist_ok=True)
    return env


def _host_intact(host: Path) -> bool:
    try:
        expected = host.with_suffix(".sha256").read_text(encoding="ascii").strip()
        return hashlib.sha256(host.read_bytes()).hexdigest() == expected
    except (OSError, UnicodeError):
        return False


def compile_host(sdk: Path) -> Path:
    source = ROOT / "tools/webview_host.cs"
    icon = ROOT / "tools/webview_host.ico"
    assemblies = [
        sdk / "Microsoft.Web.WebView2.Core.dll",
        sdk / "Microsoft.Web.WebView2.WinForms.dll",
    ]
    digest = hashlib.sha256()
    for path in [source, icon, *assemblies]:
        digest.update(path.read_bytes())
    host = sdk / f"booth-webview-host-{digest.hexdigest()[:20]}.exe"
    if _host_intact(host):
        return host
    csc = (
        Path(os.environ.get("WINDIR", r"C:\Windows"))
        / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    )
    # Never compile over an executable another login/test is already running.
    with tempfile.TemporaryDirectory(prefix=".host-build-", dir=sdk) as work:
        candidate = Path(work) / "host.exe"
        subprocess.run(  # noqa: S603 - OS compiler and pinned local sources
            [
                str(csc),
                "-nologo",
                "-target:winexe",
                f"-out:{candidate}",
                f"-win32icon:{icon}",
                *(f"-reference:{path}" for path in assemblies),
                str(source),
            ],
            capture_output=True,
            check=True,
            timeout=120,
        )
        if not _host_intact(host):
            checksum = hashlib.sha256(candidate.read_bytes()).hexdigest()
            try:
                candidate.replace(host)
            except PermissionError:
                if not _host_intact(host):
                    raise
            else:
                marker = Path(work) / "host.sha256"
                marker.write_text(checksum, encoding="ascii")
                marker.replace(host.with_suffix(".sha256"))
    return host


def launch_browser(playwright: Any, *, headless: bool = False) -> Any:
    manifest = load_manifest(ROOT)
    engine = manifest["browser"].get("engine")
    executable = manifest["browser"].get("executable")
    if executable:
        path = ROOT / ".playwright-browsers" / executable
        if not path.is_file() or not path.resolve().is_relative_to(ROOT.resolve()):
            raise RuntimeError("Bundled browser missing; run ./start.sh --repair")
        if engine == "native-webkit":
            import json

            from .native_webkit import WebKitBrowser

            receipt = ROOT / ".playwright-browsers" / manifest["browser"]["executableReceipt"]
            build = json.loads(receipt.read_text(encoding="utf-8"))
            if hashlib.sha256(path.read_bytes()).hexdigest() != build["executable_sha256"]:
                raise RuntimeError(
                    "Private WebKit host integrity mismatch; run bash ./start.sh --repair"
                )
            return WebKitBrowser(path, browser_env(), headless=headless)
        return playwright.chromium.launch(
            headless=headless, executable_path=str(path), env=browser_env()
        )
    if engine != "webview2" or not hasattr(playwright.chromium, "connect_over_cdp"):
        return playwright.chromium.launch(headless=headless)

    print(
        "[WebView2] Terms: THIRD_PARTY_TERMS.md and bundled Microsoft licenses.\n"
        "SmartScreen enabled. WebView2 may send data to Microsoft.\n"
        "https://aka.ms/privacy | https://learn.microsoft.com/en-us/microsoft-edge/privacy-whitepaper#smartscreen",
        file=sys.stderr,
        flush=True,
    )

    runtime = webview_runtime_root()
    sdk = ROOT / ".playwright-browsers/webview2-sdk"
    if not (runtime / "msedgewebview2.exe").is_file():
        raise RuntimeError("WebView2 is missing; run start.bat")
    scratch = ROOT / ".cache/tmp"
    scratch.mkdir(parents=True, exist_ok=True)
    profile = Path(tempfile.mkdtemp(prefix="webview-profile-", dir=scratch))
    from .auth import current_account, icacls

    account = current_account()
    if (
        not account
        or not icacls(profile, "/grant:r", f"{account}:(OI)(CI)F")
        or not icacls(profile, "/inheritance:r")
    ):
        remove_profile(profile)
        raise RuntimeError("Cannot restrict the temporary login profile to this account")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    print(f"[cdp] profile={profile.name} port={port}", file=sys.stderr, flush=True)
    try:
        host = compile_host(sdk)
    except (OSError, subprocess.SubprocessError) as e:
        remove_profile(profile)
        raise RuntimeError(f"WebView2 host build failed ({type(e).__name__})") from e
    host_log = scratch / f"webview-host-{port}.log"
    try:
        env = browser_env()
        args = [str(host), str(runtime), str(profile), str(port)]
        if headless:
            args.append("hidden")
        with host_log.open("w", encoding="utf-8", errors="replace") as stream:
            process = subprocess.Popen(  # noqa: S603 - owned host, fixed argv
                args,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=stream,
            )
    except BaseException:
        remove_profile(profile)
        raise
    try:
        import httpx

        endpoint = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 90
        attempt = 0
        with httpx.Client(trust_env=False, timeout=2) as client:
            while time.monotonic() < deadline:
                attempt += 1
                if process.poll() is not None:
                    raise RuntimeError(
                        "WebView2 host could not start: "
                        + host_log.read_text(encoding="utf-8", errors="replace")
                    )
                try:
                    response = client.get(endpoint + "/json/version")
                    if response.status_code == 200:
                        return HostedBrowser(
                            playwright.chromium.connect_over_cdp(endpoint), process, profile, port
                        )
                    print(
                        f"cdp probe {attempt}: status {response.status_code}",
                        file=sys.stderr,
                        flush=True,
                    )
                except httpx.HTTPError as e:
                    if attempt % 8 == 0:
                        print(
                            f"cdp probe {attempt}: {type(e).__name__}", file=sys.stderr, flush=True
                        )
                time.sleep(0.25)
        print("WebView2 startup timed out", file=sys.stderr, flush=True)
        raise RuntimeError("WebView2 startup timed out")
    except BaseException:
        terminate_host(process)
        remove_profile(profile)
        raise
