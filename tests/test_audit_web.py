"""Web job lifecycle, configured paths, and actual browser interaction."""

import socket
import threading
import time

import pytest
import uvicorn
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright

from core.browser import launch_browser
from web import cli_bridge as bridge
from web.app import create_app


def test_a05_download_uses_configured_library(seeded_db, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(bridge, "get_auth_status", lambda b: {"ok": True})
    monkeypatch.setattr(
        bridge.Bridge,
        "run_blocking",
        lambda b, argv, timeout: calls.append(argv) or bridge.CliResult(0, "ok", ""),
    )
    root = tmp_path / "chosen library"
    with TestClient(create_app(seeded_db, root)) as client:
        assert client.post("/download", json={"item_id": "id0"}).status_code == 200
    assert calls and "--output-dir" in calls[0] and str(root) in calls[0]


def test_a05_active_download_rejects_duplicate_and_cleanup(seeded_db, tmp_path, monkeypatch):
    started = threading.Event()
    finish = threading.Event()
    monkeypatch.setattr(bridge, "get_auth_status", lambda b: {"ok": True})

    def block(*args, **kwargs):
        started.set()
        assert finish.wait(10)
        return {"ok": True}

    monkeypatch.setattr(bridge, "run_download_blocking", block)
    with TestClient(create_app(seeded_db, tmp_path / "lib")) as client:
        thread = threading.Thread(target=lambda: client.post("/download", json={"item_id": "id0"}))
        thread.start()
        try:
            assert started.wait(5)
            assert client.post("/download", json={"item_id": "id0"}).status_code == 409
            assert client.post("/downloads/cleanup").status_code == 409
            assert client.get("/health").json()["download"]["running"] is True
        finally:
            finish.set()
            thread.join(10)
        assert not thread.is_alive()


def test_a05_background_failure_is_observable(seeded_db, tmp_path, monkeypatch):
    monkeypatch.setattr(bridge, "get_auth_status", lambda b: {"ok": True})

    def fail(*args, **kwargs):
        raise bridge.CliBridgeError("disk full")

    monkeypatch.setattr(bridge, "run_download_blocking", fail)
    with TestClient(create_app(seeded_db, tmp_path / "lib")) as client:
        assert client.post("/download", json={"item_id": "id0"}).status_code == 200
        state = client.get("/health").json()["download"]
        assert state["running"] is False and state["ok"] is False
        assert "disk full" in state["error"]


def test_a05_cli_cleanup_exclusion_and_recovery(seeded_db, tmp_path):
    from core.library_lock import library_lock

    root = tmp_path / "lib"
    root.mkdir()
    downloads = root / "123_title" / "downloads"
    downloads.mkdir(parents=True)
    part = downloads / "file.bin.part"
    part.write_bytes(b"partial")
    argv = ["downloads", "cleanup", "--output-dir", str(root), "--json"]
    with library_lock(root), pytest.raises(bridge.CliBridgeError):
        bridge.run_cli_once(argv, seeded_db)
    assert part.read_bytes() == b"partial"
    result = bridge.run_cli_once(argv, seeded_db)
    assert result.data == {"ok": True, "removed": 1}
    assert not part.exists()


@pytest.fixture
def live_ui(seeded_db, tmp_path, monkeypatch):
    # Test browsers must never discover the user's real Cookie and auto-sync it.
    def isolated_auth(link):
        return link.run(
            ["auth", "status", "--cookie-path", str(tmp_path / "missing-cookies.json"), "--json"]
        ).data

    monkeypatch.setattr(bridge, "get_auth_status", isolated_auth)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(create_app(seeded_db, tmp_path / "lib"), log_level="error")
    )
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        assert server.started
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(15)
        sock.close()
        assert not thread.is_alive()


def test_a05_browser_classification_and_list_refresh(live_ui):
    # The repository already uses Python Playwright and a repo-local browser;
    # no Browser-plugin runtime is exposed in this harness.
    with sync_playwright() as pw:
        browser = launch_browser(pw, headless=True)
        try:
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(live_ui)
            page.locator("#b-new-list").click()
            page.locator("#in-listname").fill("監査リスト")
            page.locator("#b-list-create").click()
            page.wait_for_function("document.querySelector('#c-lists').textContent === '1'")
            page.locator("#b-add-items").click()
            page.locator('[data-add-id="id0"]').click()
            page.wait_for_function(
                "document.querySelector('#result-count').textContent === '1 商品'"
            )
            page.locator('[data-close="add-dialog"]').click()
            page.on("dialog", lambda dialog: dialog.accept())
            page.locator("#b-delete-list").click()
            page.wait_for_function(
                "document.querySelector('#result-count').textContent === '3 商品' && document.querySelector('#c-lists').textContent === '0'"
            )
            assert not errors
        finally:
            browser.close()
