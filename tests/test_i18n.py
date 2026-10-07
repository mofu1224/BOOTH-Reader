"""Language selection exercises actual UI state, errors and English-only logs."""

import re

import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import expect, sync_playwright

import cli
from tests.browser_helpers import launch_browser
from tests.test_audit_web import live_ui as server_fixture
from web import cli_bridge as bridge
from web.app import create_app

live_ui = server_fixture


@pytest.fixture(autouse=True)
def isolate_purchase_sync(monkeypatch):
    def no_network(link):
        raise bridge.CliAuthError("BOOTH login required. Run `start.bat auth login`.")

    monkeypatch.setattr(bridge, "update_purchases", no_network)


def test_language_switch_preserves_state_and_persists(live_ui, tmp_path):
    with sync_playwright() as pw:
        browser = launch_browser(pw, headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(live_ui)
            expect(page.locator("#auth-state")).to_have_text("Cookie未登録")
            page.locator("#language").select_option("en")
            expect(page.locator("html")).to_have_attribute("lang", "en")
            expect(page.locator("#view-title")).to_have_text("All products")
            expect(page.locator("#search")).to_have_attribute(
                "placeholder", "Search by product or shop name"
            )
            expect(page.locator("#b-update")).to_have_text("Sync with BOOTH→")
            expect(page.locator("#auth-state")).to_have_text("No cookies registered")
            expect(page.locator("#terms-link")).to_have_attribute(
                "href", "/third-party-terms?lang=en"
            )
            expect(page.locator('[data-item="id0"] h2')).to_have_text("タイトル0")
            page.locator("#search").fill("タイトル1")
            page.locator("#sel-sort").select_option("name")
            page.locator("#language").select_option("ja")
            expect(page.locator("#grid .product")).to_have_count(1)
            expect(page.locator("#search")).to_have_value("タイトル1")
            expect(page.locator("#sel-sort")).to_have_value("name")
            page.locator("#language").select_option("en")
            page.locator("#b-new-list").click()
            expect(page.locator("#create-dialog h2")).to_have_text("Create list")
            page.locator("#in-listname").fill("すべての商品")
            page.locator("#b-list-create").click()
            expect(page.locator("#view-title")).to_have_text("すべての商品")
            expect(page.locator("#msg")).to_have_text("List created.")
            page.locator("#language").select_option("ja")
            expect(page.locator("#msg")).to_have_text("リストを作成しました。")
            page.locator("#language").select_option("en")
            page.locator("#b-add-items").click()
            expect(page.locator("#add-title")).to_have_text("Add products")
            expect(page.locator("[data-add-id]").first).to_have_text("Add")
            page.locator('[data-add-id="id0"]').click()
            expect(page.locator("#grid .product")).to_have_count(1)
            page.locator('[data-close="add-dialog"]').click()
            expect(page.locator("[data-remove]")).to_have_attribute(
                "aria-label", "Remove タイトル0 from list"
            )
            page.reload()
            expect(page.locator("#language")).to_have_value("en")
            expect(page.locator("html")).to_have_attribute("lang", "en")
            expect(page.locator("#list-nav .nav-label")).to_have_text("すべての商品")
            page.screenshot(path=str(tmp_path / "i18n-en-desktop.png"), full_page=True)
            for language in ["en", "ja"]:
                page.locator("#language").select_option(language)
                for width in [320, 390, 768]:
                    page.set_viewport_size({"width": width, "height": 900})
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(tmp_path / "i18n-ja-mobile.png"), full_page=True)
            assert not errors
        finally:
            browser.close()


def test_errors_confirmations_and_logs_follow_language_contract(live_ui):
    with sync_playwright() as pw:
        browser = launch_browser(pw, headless=True)
        try:
            page = browser.new_page()
            page.goto(live_ui)
            page.locator("#b-update").click()
            expect(page.locator("#msg")).to_have_text(
                "Cookieを登録するか、再ログインしてください。"
            )
            page.locator("#language").select_option("en")
            expect(page.locator("#msg")).to_contain_text("BOOTH login required")
            page.locator("#b-cookie").click()
            page.locator("#cookie-file").set_input_files(
                {"name": "invalid.json", "mimeType": "application/json", "buffer": b"invalid"}
            )
            page.locator("#cookie-form button.primary").click()
            expect(page.locator("#cookie-error")).to_have_text("Invalid cookie JSON")
            page.locator('[data-close="cookie-dialog"]').click()
            page.locator("#language").select_option("ja")
            expect(page.locator("#msg")).to_have_text("Cookie JSONの形式が不正です。")
            page.locator("#b-cookie").click()
            expect(page.locator("#cookie-error")).to_be_empty()
            page.locator('[data-close="cookie-dialog"]').click()
            page.route(
                "**/library",
                lambda route: route.fulfill(
                    status=500,
                    json={"error": "Cannot load library <script>", "code": "OPERATION_FAILED"},
                ),
            )
            page.locator("#b-refresh").click()
            expect(page.locator("#msg")).to_have_text(
                "処理に失敗しました。ログを確認してください。"
            )
            expect(page.locator("#download-rows")).to_contain_text("Cannot load library <script>")
            expect(page.locator("#download-rows script")).to_have_count(0)
            page.unroute("**/library")
            page.route(
                "**/downloads?*",
                lambda route: route.fulfill(
                    json={
                        "downloads": [{"status": "done", "item_id": "id0", "file_name": "衣装.zip"}]
                    }
                ),
            )
            page.route(
                "**/health",
                lambda route: route.fulfill(
                    json={
                        "download": {
                            "running": False,
                            "ok": False,
                            "error": "Download failed: disk full",
                        }
                    }
                ),
            )
            page.locator("#download-state").click()
            expect(page.locator("#download-rows")).to_contain_text("Download failed: disk full")
            log = page.locator("#download-rows").inner_text()
            assert "done" in log and "衣装.zip" in log
            page.locator("#language").select_option("en")
            expect(page.locator("#download-state")).to_have_text("Logs")
            assert page.locator("#download-rows").inner_text() == log
            confirmations = []
            page.on(
                "dialog", lambda dialog: (confirmations.append(dialog.message), dialog.dismiss())
            )
            page.locator("#b-dlclear").click()
            assert confirmations[-1].startswith("Delete incomplete downloads")
            page.locator("#language").select_option("ja")
            page.locator("#b-dlclear").click()
            assert confirmations[-1].startswith("未完了のダウンロード")
        finally:
            browser.close()


@pytest.mark.parametrize("storage", ["invalid", "blocked"])
def test_language_storage_failure_defaults_to_japanese(live_ui, storage):
    with sync_playwright() as pw:
        browser = launch_browser(pw, headless=True)
        try:
            page = browser.new_page()
            script = (
                "localStorage.setItem('booth-reader.language','invalid');"
                if storage == "invalid"
                else "Storage.prototype.getItem=Storage.prototype.setItem=()=>{throw new Error('blocked');};"
            )
            page.add_init_script(script)
            page.goto(live_ui)
            expect(page.locator("#view-title")).to_have_text("すべての商品")
            page.locator("#language").select_option("en")
            expect(page.locator("#view-title")).to_have_text("All products")
        finally:
            browser.close()


def test_terms_have_both_languages_and_original_licenses(seeded_db, tmp_path):
    with TestClient(create_app(seeded_db, tmp_path / "library")) as client:
        ja = client.get("/third-party-terms?lang=ja")
        en = client.get("/third-party-terms?lang=en")
        assert ja.status_code == en.status_code == 200
        assert "同梱Microsoft" in ja.text
        assert en.text.startswith("# Terms for bundled Microsoft software")
        assert "MICROSOFT SOFTWARE LICENSE TERMS" in ja.text
        assert "MICROSOFT SOFTWARE LICENSE TERMS" in en.text
        assert client.get("/third-party-terms?lang=invalid").status_code == 422


def test_cli_help_and_auth_failure_are_english(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    assert not re.search(r"[ぁ-んァ-ヶ一-龯]", capsys.readouterr().out)
    assert cli.main(["auth", "status", "--cookie-path", str(tmp_path / "missing.json")]) == 1
    output = capsys.readouterr()
    assert "login required" in output.err
    assert not re.search(r"[ぁ-んァ-ヶ一-龯]", output.err)
    assert not output.out
