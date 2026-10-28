"""Responsiveness, bounded background work and failure-state regressions."""

import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import bs4
import httpx
import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import expect, sync_playwright

from core import download, purchases
from core.db import get_connection
from core.errors import BoothPrerequisiteError
from tests.browser_helpers import launch_browser
from tests.test_audit_http import mock_http as http_fixture
from tests.test_audit_web import live_ui as server_fixture
from tests.test_current_library import card
from web import cli_bridge as bridge
from web.app import create_app

live_ui = server_fixture
mock_http = http_fixture


def test_batch_download_keeps_only_worker_count_jobs_pending(tmp_path, monkeypatch):
    submitted = []

    class MeasuredExecutor(ThreadPoolExecutor):
        def submit(self, fn, *args, **kwargs):
            submitted.append(args[0])
            return super().submit(fn, *args, **kwargs)

    def transfer(item_id, *args, **kwargs):
        if item_id == "id3":
            raise OSError("synthetic disk failure")
        if item_id == "id5":
            return {"item_id": item_id, "failed": [{"error": "synthetic file failure"}]}
        return {"item_id": item_id, "failed": []}

    progress = []
    monkeypatch.setattr(download, "ThreadPoolExecutor", MeasuredExecutor)
    monkeypatch.setattr(download, "download_item", transfer)
    result = download.download_many(
        [*(f"id{i}" for i in range(20)), "id0"],
        tmp_path / "app.db",
        tmp_path / "lib",
        concurrent=3,
        progress_cb=lambda done, total: progress.append((done, total, len(submitted))),
    )
    assert len(result["ok"]) == 18
    assert {r["item_id"] for r in result["failed"]} == {"id3", "id5"}
    assert len(submitted) == 20
    assert [(done, total) for done, total, _ in progress] == [(n, 20) for n in range(1, 21)]
    assert all(queued - done <= 3 for done, _, queued in progress)


def test_sync_does_not_hold_up_library_reads(seeded_db, tmp_path, monkeypatch):
    started, finish = threading.Event(), threading.Event()
    original = bridge.run_cli_once
    worker_call = bridge.CliWorker.call

    def guard_sync(worker, argv, timeout=60):
        assert "--update-db" not in argv, "network sync must not occupy the read worker"
        return worker_call(worker, argv, timeout)

    def delayed(argv, *args, **kwargs):
        if "--update-db" in argv:
            started.set()
            assert finish.wait(10)
            return bridge.CliResult(0, "", "", {"count": 3, "updated": 3, "items": []})
        return original(argv, *args, **kwargs)

    monkeypatch.setattr(bridge, "run_cli_once", delayed)
    monkeypatch.setattr(bridge.CliWorker, "call", guard_sync)
    with TestClient(create_app(seeded_db, tmp_path / "lib")) as client:
        client.get("/library").raise_for_status()
        with ThreadPoolExecutor(max_workers=2) as pool:
            sync = pool.submit(client.post, "/purchases/update")
            try:
                assert started.wait(2), "sync must use a dedicated process, not the read worker"
                result = pool.submit(client.get, "/library").result(timeout=2)
                assert len(result.json()["items"]) == 3
                assert client.post("/purchases/update").status_code == 409
            finally:
                finish.set()
            assert sync.result(timeout=5).json()["updated"] == 3


def test_sync_parses_each_html_page_only_once(mock_http, seeded_db, cookie_file, monkeypatch):
    parsed = []
    original = bs4.BeautifulSoup.__init__

    def counted(self, html, *args, **kwargs):
        parsed.append(html)
        original(self, html, *args, **kwargs)

    monkeypatch.setattr(bs4.BeautifulSoup, "__init__", counted)
    mock_http(
        lambda request: httpx.Response(
            200,
            text=card("123", "456") + '<a rel="next" href="/library?page=2">Next</a>'
            if not request.url.query
            else card("789", "987"),
        )
    )
    assert purchases.update_from_network(seeded_db, cookie_file) == 2
    assert len(parsed) == 2
    conn = get_connection(seeded_db)
    try:
        assert [r["item_id"] for r in purchases.list_purchases(conn)][:2] == ["id2", "id1"]
        assert conn.execute("SELECT count(*) FROM purchases").fetchone()[0] == 5
    finally:
        conn.close()


def test_sync_checks_parser_before_network(seeded_db, cookie_file, monkeypatch):
    requests = []
    monkeypatch.setitem(sys.modules, "bs4", None)
    monkeypatch.setattr(
        purchases, "fetch_library_html", lambda **kwargs: requests.append(1) or ("", "")
    )
    with pytest.raises(BoothPrerequisiteError):
        purchases.update_from_network(seeded_db, cookie_file)
    assert requests == []


def test_search_reuses_sort_and_navigation_nodes(live_ui):
    with sync_playwright() as pw:
        browser = launch_browser(pw, headless=True)
        try:
            page = browser.new_page()
            page.goto(live_ui)
            expect(page.locator("#grid .product")).to_have_count(3)
            page.evaluate("""() => {
                window.navNode=document.querySelector('[data-view="unclassified"]');
                window.comparisons=0;
                const original=collator;
                collator={compare:(a,b)=>{window.comparisons++;return original.compare(a,b);}};
            }""")
            page.locator("#search").fill("タイトル1")
            expect(page.locator("#grid .product")).to_have_count(1)
            assert page.evaluate("comparisons") == 0
            assert page.evaluate("navNode===document.querySelector('[data-view=\"unclassified\"]')")
            page.locator('[data-view="unclassified"]').focus()
            page.keyboard.press("Enter")
            expect(page.locator('[data-view="unclassified"]')).to_be_focused()
            expect(page.locator("#grid .product")).to_have_count(3)
        finally:
            browser.close()


def test_sort_save_failure_restores_saved_order(live_ui):
    with sync_playwright() as pw:
        browser = launch_browser(pw, headless=True)
        try:
            page = browser.new_page()
            assert page.request.post(live_ui + "/lists", data={"action": "create", "name": "A"}).ok
            for item in ["id0", "id1"]:
                assert page.request.post(
                    live_ui + "/lists", data={"action": "add", "list": "A", "item_id": item}
                ).ok
            page.goto(live_ui)
            page.locator('[data-view="1"]').click()
            page.route(
                "**/lists", lambda route: route.fulfill(status=500, json={"error": "save failed"})
            )
            page.locator("#sel-sort").select_option("name")
            expect(page.locator("#msg")).to_contain_text("save failed")
            expect(page.locator("#sel-sort")).to_have_value("newest")
            expect(page.locator("#grid .product").first).to_have_attribute("data-item", "id1")
        finally:
            browser.close()


def test_sort_save_keeps_requested_order_after_navigation(live_ui):
    with sync_playwright() as pw:
        browser = launch_browser(pw, headless=True)
        pending = []
        try:
            page = browser.new_page()
            assert page.request.post(live_ui + "/lists", data={"action": "create", "name": "A"}).ok
            for item in ["id0", "id1"]:
                assert page.request.post(
                    live_ui + "/lists", data={"action": "add", "list": "A", "item_id": item}
                ).ok
            page.goto(live_ui)
            page.locator('[data-view="1"]').click()
            page.route("**/lists", lambda route: pending.append(route))
            page.locator("#sel-sort").select_option("name")
            page.locator('[data-view="all"]').click()
            page.locator('[data-view="1"]').click()
            assert len(pending) == 1
            response = page.request.post(
                live_ui + "/lists", data={"action": "sort", "list": "1", "sort": "name"}
            )
            pending.pop().fulfill(response=response)
            expect(page.locator("#msg")).to_have_text("並び順を保存しました。")
            expect(page.locator("#sel-sort")).to_have_value("name")
            expect(page.locator("#grid .product").first).to_have_attribute("data-item", "id0")
            page.reload()
            page.locator('[data-view="1"]').click()
            expect(page.locator("#sel-sort")).to_have_value("name")
        finally:
            for route in pending:
                route.abort()
            browser.close()


def test_keyboard_can_add_another_product_without_losing_focus(live_ui):
    with sync_playwright() as pw:
        browser = launch_browser(pw, headless=True)
        try:
            page = browser.new_page()
            assert page.request.post(live_ui + "/lists", data={"action": "create", "name": "A"}).ok
            page.goto(live_ui)
            page.locator('[data-view="1"]').click()
            page.locator("#b-add-items").click()
            page.locator('[data-add-id="id0"]').focus()
            page.keyboard.press("Enter")
            expect(page.locator("#grid .product")).to_have_count(1)
            expect(page.locator('[data-add-id="id1"]')).to_be_focused()
            page.keyboard.press("Enter")
            expect(page.locator("#grid .product")).to_have_count(2)
            expect(page.locator('[data-add-id="id2"]')).to_be_focused()
        finally:
            browser.close()


def test_transient_auth_error_does_not_forget_cookie_revision(live_ui):
    with sync_playwright() as pw:
        browser = launch_browser(pw, headless=True)
        try:
            page = browser.new_page()
            updates = []
            page.route(
                "**/auth/status",
                lambda route: route.fulfill(json={"ok": True, "count": 1, "revision": "same"}),
            )
            page.route(
                "**/purchases/update",
                lambda route: (updates.append(1), route.fulfill(json={"ok": True, "updated": 3})),
            )
            page.goto(live_ui)
            expect(page.locator("#msg")).to_have_text("3 商品を同期しました。")
            page.route(
                "**/auth/status",
                lambda route: route.fulfill(status=500, json={"error": "temporarily unavailable"}),
            )
            page.evaluate("checkAuth()")
            expect(page.locator("#auth-state")).to_have_text("Cookie登録済み")
            page.unroute("**/auth/status")
            page.route(
                "**/auth/status",
                lambda route: route.fulfill(json={"ok": True, "count": 1, "revision": "same"}),
            )
            page.evaluate("checkAuth()")
            assert updates == [1]
        finally:
            browser.close()


def test_download_poll_is_single_flight_and_pauses_when_hidden(live_ui):
    with sync_playwright() as pw:
        browser = launch_browser(pw, headless=True)
        try:
            page = browser.new_page()
            page.goto(live_ui)
            page.locator("#downloads-panel").evaluate("el=>el.open=true")
            page.wait_for_function("downloadSnapshot!==null")
            calls = []
            page.route(
                "**/downloads?*",
                lambda route: (calls.append(1), route.fulfill(json={"downloads": []})),
            )
            page.evaluate("Promise.all([pollDownloads(),pollDownloads(),pollDownloads()])")
            assert calls == [1]
            page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,value:true})")
            page.evaluate("pollDownloads()")
            assert calls == [1]
        finally:
            browser.close()


def test_running_download_disables_duplicate_download_not_classification(live_ui):
    with sync_playwright() as pw:
        browser = launch_browser(pw, headless=True)
        try:
            page = browser.new_page()
            running = {"running": True, "ok": None, "error": ""}
            page.route(
                "**/health", lambda route: route.fulfill(json={"ok": True, "download": running})
            )
            page.goto(live_ui)
            page.locator("#download-state").click()
            expect(page.locator("[data-dl]").first).to_be_disabled()
            expect(page.locator("#b-dlall")).to_be_disabled()
            expect(page.locator("#b-dlclear")).to_be_disabled()
            expect(page.locator("[data-choose]").first).to_be_enabled()
            running.update(running=False, ok=True)
            page.evaluate("pollDownloads()")
            expect(page.locator("[data-dl]").first).to_be_enabled()
            expect(page.locator("#b-dlall")).to_be_enabled()
            expect(page.locator("#b-dlclear")).to_be_enabled()
        finally:
            browser.close()


def test_failed_poll_still_waits_for_its_other_pending_request(live_ui):
    with sync_playwright() as pw:
        browser = launch_browser(pw, headless=True)
        pending = []
        try:
            page = browser.new_page()
            page.goto(live_ui)
            page.locator("#download-state").click()
            page.wait_for_function("downloadSnapshot!==null")
            page.route("**/health", lambda route: pending.append(route))
            page.route(
                "**/downloads?*",
                lambda route: route.fulfill(status=500, json={"error": "unavailable"}),
            )
            page.evaluate("() => {window.pollOne=pollDownloads();}")
            page.wait_for_timeout(100)
            assert len(pending) == 1
            page.evaluate("() => {window.pollTwo=pollDownloads();}")
            page.wait_for_timeout(100)
            assert len(pending) == 1
        finally:
            for route in pending:
                route.fulfill(json={"download": {"running": False, "ok": None, "error": ""}})
            browser.close()
