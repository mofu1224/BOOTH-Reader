"""Observe a real relocated process, browser UI, writes and native module paths."""

from __future__ import annotations

import ctypes
import json
import os
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def native_modules() -> list[str]:
    """Actual loaded DLL paths, not an import-table prediction."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    process = kernel.GetCurrentProcess()
    handles = (wintypes.HMODULE * 2048)()
    needed = wintypes.DWORD()
    psapi.EnumProcessModules.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.HMODULE),
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    psapi.GetModuleFileNameExW.argtypes = [
        wintypes.HANDLE,
        wintypes.HMODULE,
        wintypes.LPWSTR,
        wintypes.DWORD,
    ]
    if not psapi.EnumProcessModules(process, handles, ctypes.sizeof(handles), ctypes.byref(needed)):
        raise ctypes.WinError(ctypes.get_last_error())
    result = []
    for handle in handles[: needed.value // ctypes.sizeof(wintypes.HMODULE)]:
        name = ctypes.create_unicode_buffer(32768)
        if psapi.GetModuleFileNameExW(process, handle, name, len(name)):
            result.append(name.value)
    return sorted(set(result))


def main() -> int:
    import uvicorn
    from playwright.sync_api import sync_playwright

    from core.auth import load_cookies, save_cookies
    from core.db import get_connection, init_db
    from core.purchases import export_csv
    from web.app import create_app

    cache = ROOT / ".cache" / "portable-probe"
    cache.mkdir(parents=True, exist_ok=True)
    db = init_db(cache / "probe.db")
    conn = get_connection(db)
    conn.execute(
        "INSERT OR IGNORE INTO items(item_id,title,shop) VALUES('probe','Portable item','shop')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO purchases(item_id,purchase_date) VALUES('probe','2026-10-01')"
    )
    conn.commit()
    conn.close()
    # Synthetic data only. Test the same OS ACL and atomic-write path as login.
    cookies = cache / "synthetic-cookies.json"
    save_cookies([{"name": "sample", "value": "synthetic-only", "domain": ".booth.pm"}], cookies)
    assert load_cookies(cookies)[0]["name"] == "sample"
    cookies.unlink()
    export_csv([{"item_id": "probe", "title": "Portable item"}], cache / "purchases.csv")
    app = create_app(db, cache / "library")
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(200):
            if server.started:
                break
            time.sleep(0.05)
        assert server.started
        port = server.servers[0].sockets[0].getsockname()[1]
        from core.browser import launch_browser

        with sync_playwright() as pw, launch_browser(pw, headless=False) as browser:
            page = browser.new_page()
            requests = []
            page.on("request", lambda req: requests.append(req.url))
            page.route(
                "**/*",
                lambda route: (
                    route.continue_()
                    if route.request.url.startswith(f"http://127.0.0.1:{port}/")
                    else route.abort()
                ),
            )
            page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
            assert page.title()
            page.screenshot(path=str(cache / "web.png"))
            # Exercise the rendered controls, including their refresh/busy logic.
            result = {}
            page.locator("#b-new-list").click()
            page.locator("#in-listname").fill("Portable probe")
            with page.expect_response(lambda response: response.url.endswith("/lists")) as reply:
                page.locator("#b-list-create").click()
            result["create"] = reply.value.status
            page.wait_for_function("document.getElementById('c-lists').textContent === '1'")
            page.wait_for_function(
                "document.getElementById('view-title').textContent === 'Portable probe'"
            )
            page.locator("#b-add-items").click()
            with page.expect_response(lambda response: response.url.endswith("/lists")) as reply:
                page.locator('[data-add-id="probe"]').click()
            result["add"] = reply.value.status
            page.wait_for_function(
                "document.querySelector('[data-view=unclassified] .count').textContent === '0'"
            )
            page.locator('[data-close="add-dialog"]').click()
            page.once("dialog", lambda dialog: dialog.accept())
            with page.expect_response(lambda response: response.url.endswith("/lists")) as reply:
                page.locator("#b-delete-list").click()
            result["delete"] = reply.value.status
            page.wait_for_function("document.getElementById('c-lists').textContent === '0'")
            page.wait_for_function(
                "document.querySelector('[data-view=unclassified] .count').textContent === '1'"
            )
            result.update(
                page.evaluate("""async () => {
                    const unclassified = await fetch('/unclassified');
                    const health = await fetch('/health');
                    return {unclassified:unclassified.status,
                            health:health.status};
                }""")
            )
            assert all(value == 200 for value in result.values()), result
            # Keep live subprocesses long enough for the OS module snapshot.
            webview_exe = ROOT / ".playwright-browsers/webview2/msedgewebview2.exe"
            report = {
                "root": str(ROOT),
                "executable": sys.executable,
                "prefix": sys.prefix,
                "base_prefix": sys.base_prefix,
                "sys_path": sys.path,
                "native_modules": native_modules(),
                "browser_executable": str(webview_exe)
                if webview_exe.is_file()
                else pw.chromium.executable_path,
                "browser_version": browser.version,
                "http": result,
                "requests": requests,
                "temp": os.environ.get("TEMP"),
            }
            (cache / "runtime.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            # Export the pinned engine's real credits page (edge:// in WebView2).
            page.unroute("**/*")
            page.goto("edge://credits/")
            (cache / "webview-credits.html").write_text(page.content(), encoding="utf-8")
            time.sleep(5)
    finally:
        server.should_exit = True
        thread.join(timeout=10)
    assert not thread.is_alive(), "server failed to stop gracefully"
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
