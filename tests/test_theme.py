"""Theme selection survives server restarts and fresh browser sessions."""

import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import expect, sync_playwright

from tests.browser_helpers import launch_browser
from tests.test_audit_web import live_ui as server_fixture
from web import cli_bridge as bridge
from web.app import create_app

live_ui = server_fixture


def test_theme_survives_app_restart_and_origin_change(tmp_path, monkeypatch):
    monkeypatch.setattr(bridge, "get_library", lambda link: {})
    db = tmp_path / "app.db"
    with TestClient(create_app(db), base_url="http://127.0.0.1:8000") as client:
        assert 'data-theme="light"' in client.get("/").text
        assert client.post("/ui/theme", json={"theme": "dark"}).json() == {
            "ok": True,
            "theme": "dark",
        }
    with TestClient(create_app(db), base_url="http://127.0.0.1:8001") as client:
        assert 'data-theme="dark"' in client.get("/").text
        assert client.post("/ui/theme", json={"theme": "light"}).status_code == 200
    with TestClient(create_app(db)) as client:
        assert 'data-theme="light"' in client.get("/").text


def test_theme_rejects_invalid_and_cross_origin_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(bridge, "get_library", lambda link: {})
    with TestClient(create_app(tmp_path / "app.db")) as client:
        assert client.post("/ui/theme", json={"theme": "dark"}).status_code == 200
        for theme in ["", "system", "dark\n", None, 1]:
            assert client.post("/ui/theme", json={"theme": theme}).status_code == 422
        assert (
            client.post(
                "/ui/theme", json={"theme": "light"}, headers={"Origin": "https://example.com"}
            ).status_code
            == 403
        )
        assert 'data-theme="dark"' in client.get("/").text


@pytest.mark.parametrize("saved", ["invalid JSON", "[]", '{"theme":"other"}'])
def test_invalid_theme_file_falls_back_to_light(tmp_path, monkeypatch, saved):
    monkeypatch.setattr(bridge, "get_library", lambda link: {})
    (tmp_path / "app.db.ui.json").write_text(saved, encoding="utf-8")
    with TestClient(create_app(tmp_path / "app.db")) as client:
        assert 'data-theme="light"' in client.get("/").text


def test_theme_save_failure_preserves_previous_file(tmp_path, monkeypatch):
    from pathlib import Path

    with TestClient(create_app(tmp_path / "app.db")) as client:
        assert client.post("/ui/theme", json={"theme": "dark"}).status_code == 200
        previous = (tmp_path / "app.db.ui.json").read_bytes()

        def fail(*args):
            raise OSError("disk unavailable")

        monkeypatch.setattr(Path, "replace", fail)
        assert client.post("/ui/theme", json={"theme": "light"}).status_code == 500
        assert (tmp_path / "app.db.ui.json").read_bytes() == previous
        assert not list(tmp_path.glob(".ui-theme-*.tmp"))


def test_rendered_theme_switch_and_fresh_browser(live_ui, tmp_path):
    with sync_playwright() as pw:
        browser = launch_browser(pw, headless=True)
        try:
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(live_ui)
            expect(page.locator("#grid .product")).to_have_count(3)
            page.locator("#search").fill("タイトル1")
            toggle = page.get_by_role("button", name="ダークモード", exact=True)
            expect(toggle).to_have_attribute("aria-pressed", "false")
            expect(toggle.locator(".theme-moon")).to_be_visible()
            expect(toggle.locator(".theme-sun")).to_be_hidden()
            toggle.click()
            expect(page.locator("html")).to_have_attribute("data-theme", "dark")
            expect(toggle).to_have_attribute("aria-pressed", "true")
            expect(toggle.locator(".theme-sun")).to_be_visible()
            expect(toggle.locator(".theme-moon")).to_be_hidden()
            expect(toggle).to_have_attribute("title", "ライトモードに切り替える")
            assert (
                page.locator("body").evaluate("el => getComputedStyle(el).backgroundColor")
                == "rgb(24, 24, 24)"
            )
            expect(page.locator("#grid .product")).to_have_count(1)
            expect(page.locator("#search")).to_have_value("タイトル1")
            page.locator("#b-new-list").click()
            assert (
                page.locator("dialog[open]").evaluate("el => getComputedStyle(el).backgroundColor")
                == "rgb(34, 34, 34)"
            )
            page.locator('[data-close="create-dialog"]').click()
            page.screenshot(path=str(tmp_path / "theme-dark-desktop.png"), full_page=True)
            page.locator("#language").select_option("en")
            expect(page.get_by_role("button", name="Dark mode", exact=True)).to_have_attribute(
                "aria-pressed", "true"
            )
            expect(page.locator("#theme")).to_have_attribute("title", "Switch to light mode")
            for width in [320, 390, 768]:
                page.set_viewport_size({"width": width, "height": 900})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(tmp_path / "theme-dark-mobile.png"), full_page=True)
            assert not errors
            browser.close()
            browser = launch_browser(pw, headless=True)
            context = browser.new_context()
            page = context.new_page()
            page.goto(live_ui)
            expect(page.locator("html")).to_have_attribute("data-theme", "dark")
            expect(page.locator("#theme")).to_have_attribute("aria-pressed", "true")
            page.route(
                "**/ui/theme", lambda route: route.fulfill(status=500, json={"error": "保存失敗"})
            )
            page.locator("#theme").click()
            expect(page.locator("#msg")).to_have_text("保存失敗")
            expect(page.locator("#theme")).to_have_attribute("aria-pressed", "true")
            expect(page.locator("html")).to_have_attribute("data-theme", "dark")
            page.unroute("**/ui/theme")
            page.locator("#theme").focus()
            page.keyboard.press("Enter")
            expect(page.locator("html")).to_have_attribute("data-theme", "light")
            page.reload()
            expect(page.locator("#theme")).to_have_attribute("aria-pressed", "false")
            expect(page.locator("#theme .theme-moon")).to_be_visible()
            page.locator("#theme").focus()
            page.keyboard.press("Space")
            expect(page.locator("html")).to_have_attribute("data-theme", "dark")
            context.close()
        finally:
            browser.close()
