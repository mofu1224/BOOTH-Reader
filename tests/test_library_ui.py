"""Library membership, order persistence, complete listing and rendered flows."""

import base64
import io
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import expect, sync_playwright

from core import auth, lists, purchases
from core.db import get_connection, init_db
from tests.browser_helpers import launch_browser
from tests.test_audit_web import live_ui as server_fixture
from web import cli_bridge as bridge
from web.app import create_app

live_ui = server_fixture


def drag_list(page, source, target):
    start = page.locator(f'#list-nav [data-view="{source}"]').bounding_box()
    end = page.locator(f'#list-nav [data-view="{target}"]').bounding_box()
    page.mouse.move(start["x"] + start["width"] / 2, start["y"] + start["height"] / 2)
    page.mouse.down()
    direction = 1 if end["x"] > start["x"] else -1
    page.mouse.move(
        end["x"] + end["width"] / 2 + direction * 10, end["y"] + end["height"] / 2, steps=12
    )
    page.wait_for_timeout(220)
    page.mouse.up()


def test_membership_is_exclusive_and_reorder_is_atomic(seeded_db):
    conn = get_connection(seeded_db)
    try:
        a = lists.create_list(conn, "A")
        lists.create_list(conn, "B")
        lists.add_member(conn, "A", "id0")
        lists.add_member(conn, "A", "id1")
        lists.add_member(conn, "A", "id0")  # idempotent
        with pytest.raises(ValueError, match="another list"):
            lists.add_member(conn, "B", "id0")
        with pytest.raises(ValueError, match="another list"):
            lists.add_member(conn, "not-created", "id0")
        assert len(lists.list_lists(conn)) == 2
        lists.reorder(conn, "A", ["id1", "id0"])
        with pytest.raises(ValueError):
            lists.reorder(conn, "A", ["id1", "id1"])
        with pytest.raises(ValueError):
            lists.reorder(conn, "A", ["id2", "id0"])
        state = lists.library(conn)
        assert [r["item_id"] for r in state["members"] if r["list_id"] == a] == ["id1", "id0"]
        assert next(row for row in state["lists"] if row["list_id"] == a)["sort"] == "manual"
        assert [i["item_id"] for i in lists.get_unclassified(conn)] == ["id2"]
        lists.remove_member(conn, "A", "id0")
        lists.add_member(conn, "B", "id0")
    finally:
        conn.close()


def test_concurrent_add_cannot_duplicate_membership(seeded_db):
    def add(key):
        conn = get_connection(seeded_db)
        try:
            lists.add_member(conn, key, "id0")
            return True
        except ValueError:
            return False
        finally:
            conn.close()

    with ThreadPoolExecutor(max_workers=2) as workers:
        assert sum(workers.map(add, ["A", "B"])) == 1


def test_list_order_is_atomic_persistent_and_new_lists_append(seeded_db):
    conn = get_connection(seeded_db)
    try:
        a = lists.create_list(conn, "A")
        b = lists.create_list(conn, "B")
        c = lists.create_list(conn, "C")
        lists.add_member(conn, "A", "id0")
        lists.reorder_lists(conn, [c, a, b])
        for invalid in ([c, a, a], [c, a], [c, a, 999], [True, a, b]):
            with pytest.raises(ValueError):
                lists.reorder_lists(conn, invalid)
            assert [row["list_id"] for row in lists.list_lists(conn)] == [c, a, b]
        d = lists.create_list(conn, "0-new")
        lists.create_list(conn, "A")
        lists.add_member(conn, "implicit", "id1")
        expected = [c, a, b, d]
        assert [r["list_id"] for r in lists.list_lists(conn)][:4] == expected
        assert lists.library(conn)["members"][0]["item_id"] == "id0"
    finally:
        conn.close()
    init_db(seeded_db)
    conn = get_connection(seeded_db)
    try:
        assert [r["list_id"] for r in lists.list_lists(conn)][:4] == expected
    finally:
        conn.close()


def test_list_order_api_rejects_stale_state_without_partial_save(tmp_path):
    db = init_db(tmp_path / "app.db")
    with TestClient(create_app(db, tmp_path / "lib")) as client:
        for name in ["A", "B", "C"]:
            client.post("/lists", json={"action": "create", "name": name}).raise_for_status()
        ids = [r["list_id"] for r in client.get("/lists").json()["lists"]]
        expected = ids[::-1]
        client.post(
            "/lists", json={"action": "reorder-lists", "list_ids": expected}
        ).raise_for_status()
        assert [r["list_id"] for r in client.get("/library").json()["lists"]] == expected
        assert (
            client.post("/lists", json={"action": "reorder-lists", "list_ids": ids[:2]}).status_code
            == 400
        )
        assert [r["list_id"] for r in client.get("/lists").json()["lists"]] == expected


def test_network_order_survives_missing_dates_and_sync(tmp_path):
    db = tmp_path / "app.db"
    init_db(db)
    conn = get_connection(db)
    try:
        rows = [{"item_id": "b", "title": "B"}, {"item_id": "a", "title": "A"}]
        purchases.upsert_purchases(conn, rows)
        # Creation times must not be mistaken for purchase times.
        conn.execute("UPDATE items SET created_at='2099-01-01' WHERE item_id='a'")
        conn.commit()
        assert [i["item_id"] for i in purchases.list_purchases(conn)] == ["b", "a"]
        assert [i["item_id"] for i in lists.get_unclassified(conn, "oldest")] == ["a", "b"]
        lists.add_member(conn, "A", "a")
        lists.set_sort(conn, "A", "name")
        purchases.upsert_purchases(conn, rows)
        assert lists.library(conn)["lists"][0]["sort"] == "name"
        assert lists.library(conn)["members"][0]["item_id"] == "a"
    finally:
        conn.close()


def test_v2_migration_preserves_existing_multi_memberships(tmp_path):
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    from core.db import SCHEMA

    conn.executescript(SCHEMA)
    conn.execute("INSERT INTO items(item_id,title) VALUES('a','既存の商品')")
    conn.executemany("INSERT INTO lists(name) VALUES(?)", [("A",), ("B",)])
    conn.executemany("INSERT INTO list_members(list_id,item_id) VALUES(?,'a')", [(1,), (2,)])
    conn.execute("PRAGMA user_version=2")
    conn.commit()
    conn.close()
    init_db(db)
    init_db(db)
    conn = get_connection(db)
    try:
        assert len(lists.library(conn)["members"]) == 2
        assert not lists.get_unclassified(conn)
    finally:
        conn.close()


def test_library_api_returns_all_products_and_persists_order(tmp_path):
    db = tmp_path / "app.db"
    init_db(db)
    conn = get_connection(db)
    conn.executemany(
        "INSERT INTO items(item_id,title) VALUES(?,?)", [(f"i{i}", f"商品{i}") for i in range(1005)]
    )
    conn.commit()
    conn.close()
    with TestClient(create_app(db, tmp_path / "lib")) as client:
        assert len(client.get("/library").json()["items"]) == 1005
        client.post("/lists", json={"action": "create", "name": "A"}).raise_for_status()
        for item_id in ["i0", "i1"]:
            client.post(
                "/lists", json={"action": "add", "list": "A", "item_id": item_id}
            ).raise_for_status()
        client.post(
            "/lists", json={"action": "reorder", "list": "A", "item_ids": ["i1", "i0"]}
        ).raise_for_status()
        state = client.get("/library").json()
        assert [m["item_id"] for m in state["members"]] == ["i1", "i0"]
        assert state["lists"][0]["sort"] == "manual"
        assert (
            client.post("/lists", json={"action": "add", "list": "B", "item_id": "i0"}).status_code
            == 400
        )


def test_cookie_import_uses_stdin_and_rejects_invalid_without_replacing(tmp_path, monkeypatch):
    import cli

    cookie_path = tmp_path / "cookies.json"
    old = [{"name": "session", "value": "test-only-old", "domain": ".booth.pm"}]
    auth.save_cookies(old, cookie_path)
    monkeypatch.setattr("sys.stdin", io.StringIO('{"cookies": []}'))
    assert cli.main(["auth", "import", "--cookie-path", str(cookie_path)]) == 2
    assert auth.load_cookies(cookie_path) == old
    new = [{"name": "session", "value": "test-only-new", "domain": ".booth.pm", "expires": -1}]
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"cookies": new})))
    assert cli.main(["auth", "import", "--cookie-path", str(cookie_path)]) == 0
    assert auth.load_cookies(cookie_path) == new
    result = bridge.run_cli_once(
        ["auth", "import", "--cookie-path", str(cookie_path), "--json"],
        tmp_path / "app.db",
        stdin_text=json.dumps(new),
    )
    assert result.data == {"ok": True, "count": 1}
    assert auth.load_cookies(cookie_path) == new
    seen = {}

    def once(argv, *args, **kwargs):
        seen.update(argv=argv, stdin=kwargs["stdin_text"])
        return bridge.CliResult(0, "", "", {"ok": True})

    monkeypatch.setattr(bridge, "run_cli_once", once)
    link = bridge.Bridge(str(tmp_path / "app.db"))
    try:
        bridge.import_cookies(link, json.dumps(new))
        assert "test-only-new" not in " ".join(seen["argv"])
        assert "test-only-new" in seen["stdin"]
    finally:
        link.close()


def test_rendered_library_sort_membership_and_mobile(live_ui, tmp_path):
    with sync_playwright() as pw:
        browser = launch_browser(pw, headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(live_ui)
            expect(page.locator("#grid .product")).to_have_count(3)
            page.locator("#b-new-list").click()
            page.locator("#in-listname").fill("衣装リスト")
            page.locator("#b-list-create").click()
            expect(page.locator("#view-title")).to_have_text("衣装リスト")
            page.locator("#b-add-items").click()
            page.locator('[data-add-id="id0"]').click()
            expect(page.locator('[data-add-id="id0"]')).to_have_count(0)
            page.locator('[data-add-id="id1"]').click()
            expect(page.locator("#grid .product")).to_have_count(2)
            page.locator('[data-close="add-dialog"]').click()
            page.locator("#sel-sort").select_option("name")
            expect(page.locator("#grid .product").first).to_have_attribute("data-item", "id0")
            expect(page.locator('#sel-sort option[value="manual"]')).to_have_count(0)
            page.reload()
            page.locator('[data-view="1"]').click()
            expect(page.locator("#sel-sort")).to_have_value("name")
            expect(page.locator("#grid .product").first).to_have_attribute("data-item", "id0")
            page.locator("#b-new-list").click()
            page.locator("#in-listname").fill("読むもの")
            page.locator("#b-list-create").click()
            expect(page.locator("#view-title")).to_have_text("読むもの")
            page.locator("#b-add-items").click()
            expect(page.locator("[data-add-id]")).to_have_count(1)
            expect(page.locator("[data-add-id]")).to_have_attribute("data-add-id", "id2")
            page.locator('[data-close="add-dialog"]').click()
            drag_list(page, 2, 1)
            expect(page.locator("#msg")).to_have_text("マイリストの並び順を保存しました。")
            expect(page.locator("#list-nav button").first).to_have_attribute("data-view", "2")
            page.reload()
            expect(page.locator("#list-nav button").first).to_have_attribute("data-view", "2")
            page.locator('#list-nav [data-view="2"]').focus()
            page.keyboard.press("Alt+ArrowRight")
            expect(page.locator("#list-nav button").first).to_have_attribute("data-view", "1")
            expect(page.locator("#msg")).to_have_text("マイリストの並び順を保存しました。")
            page.route(
                "**/lists",
                lambda route: route.fulfill(
                    status=400, content_type="application/json", body='{"error":"保存失敗"}'
                ),
            )
            drag_list(page, 2, 1)
            expect(page.locator("#msg")).to_have_text("保存失敗")
            expect(page.locator("#list-nav button").first).to_have_attribute("data-view", "1")
            page.unroute("**/lists")
            page.locator('[data-view="all"]').click()
            page.screenshot(path=str(tmp_path / "library-desktop.png"), full_page=True)
            for width in [320, 390, 768]:
                page.set_viewport_size({"width": width, "height": 900})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.set_viewport_size({"width": 390, "height": 900})
            page.screenshot(path=str(tmp_path / "library-mobile.png"), full_page=True)
            assert not errors
            print(f"UI screenshots: {tmp_path}")
        finally:
            browser.close()


def test_horizontal_list_drag_steps_live_and_saves_only_on_release(live_ui):
    with sync_playwright() as pw:
        browser = launch_browser(pw, headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors, saves = [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            for name in ["List A", "List B", "List C", "List D"]:
                response = page.request.post(
                    live_ui + "/lists", data={"action": "create", "name": name}
                )
                assert response.ok
            page.goto(live_ui)
            page.on(
                "request",
                lambda request: (
                    saves.append(request.post_data_json)
                    if request.method == "POST" and request.url.endswith("/lists")
                    else None
                ),
            )
            nav = page.locator("#list-nav")

            def ids():
                return nav.locator("button").evaluate_all("bs => bs.map(b => b.dataset.view)")

            a = page.locator('#list-nav [data-view="1"]')
            start = a.bounding_box()
            b = page.locator('#list-nav [data-view="2"]').bounding_box()
            c = page.locator('#list-nav [data-view="3"]').bounding_box()
            x, y = start["x"] + start["width"] / 2, start["y"] + start["height"] / 2
            page.mouse.move(x, y)
            page.mouse.down()
            page.mouse.move(x, y + 160, steps=8)
            assert ids() == ["1", "2", "3", "4"]
            page.mouse.move(b["x"] + b["width"] / 2 + 10, y + 160, steps=12)
            page.wait_for_function(
                "document.querySelector('#list-nav button').dataset.view === '2'"
            )
            assert ids() == ["2", "1", "3", "4"]
            assert abs(a.bounding_box()["y"] - start["y"]) < 1
            assert not saves
            page.mouse.move(c["x"] + c["width"] / 2 + 10, y - 80, steps=12)
            page.wait_for_function(
                "document.querySelector('#list-nav button:nth-child(2)').dataset.view === '3'"
            )
            assert ids() == ["2", "3", "1", "4"]
            assert abs(a.bounding_box()["y"] - start["y"]) < 1
            page.mouse.up()
            expect(page.locator("#msg")).to_have_text("マイリストの並び順を保存しました。")
            assert len(saves) == 1
            assert saves[0]["list_ids"] == [2, 3, 1, 4]
            expect(page.locator("#view-title")).to_have_text("すべての商品")
            page.reload()
            assert ids() == ["2", "3", "1", "4"]
            page.emulate_media(reduced_motion="reduce")
            # Escape cancels the preview rather than saving it.
            first, second = nav.locator("button").nth(0), nav.locator("button").nth(1)
            box, target = first.bounding_box(), second.bounding_box()
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + 10)
            page.mouse.down()
            page.mouse.move(target["x"] + target["width"] / 2 + 10, box["y"] + 10, steps=12)
            page.wait_for_function(
                "document.querySelector('#list-nav button').dataset.view === '3'"
            )
            assert nav.evaluate("el => el.getAnimations({subtree:true}).length") == 0
            page.keyboard.press("Escape")
            page.mouse.up()
            assert ids() == ["2", "3", "1", "4"]
            assert len(saves) == 1
            # Overflow stays within a single horizontally scrollable bar.
            for n in range(10):
                assert page.request.post(
                    live_ui + "/lists", data={"action": "create", "name": f"More lists {n}"}
                ).ok
            page.reload()
            page.set_viewport_size({"width": 390, "height": 900})
            assert nav.evaluate("el => el.scrollWidth > el.clientWidth")
            assert (
                len(set(nav.locator("button").evaluate_all("bs => bs.map(b => b.offsetTop)"))) == 1
            )
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            edge = nav.bounding_box()
            first_box = nav.locator("button").first.bounding_box()
            page.mouse.move(first_box["x"] + 20, first_box["y"] + 10)
            page.mouse.down()
            page.mouse.move(edge["x"] + edge["width"] - 5, first_box["y"] + 120, steps=15)
            page.wait_for_function("document.querySelector('#list-nav').scrollLeft > 100")
            page.keyboard.press("Escape")
            page.mouse.up()
            assert not errors
        finally:
            browser.close()


def test_native_window_resize_reflows_library(live_ui, tmp_path):
    with sync_playwright() as pw:
        browser = launch_browser(pw, headless=False)
        try:
            page = browser.new_page(no_viewport=True)
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(live_ui)
            expect(page.locator("#grid .product")).to_have_count(3)
            session = page.context.new_cdp_session(page)
            window = session.send("Browser.getWindowForTarget")["windowId"]
            columns = []
            for width in [1440, 800, 500]:
                session.send(
                    "Browser.setWindowBounds",
                    {"windowId": window, "bounds": {"width": width, "height": 900}},
                )
                page.wait_for_function("w => Math.abs(outerWidth - w) < 30", arg=width)
                page.wait_for_timeout(200)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                columns.append(
                    page.locator("#grid").evaluate(
                        "el => getComputedStyle(el).gridTemplateColumns.split(' ').length"
                    )
                )
                page.screenshot(path=str(tmp_path / f"native-window-{width}.png"))
            assert columns[0] > columns[1] > columns[2]
            assert columns[2] == 2
            page.locator("#search").fill("not-a-product")
            expect(page.locator("#empty-title")).to_have_text("該当する商品がありません")
            assert not errors
        finally:
            browser.close()


def test_cookie_registration_auto_sync_images_and_pagination(live_ui, seeded_db, monkeypatch):
    state = {"authenticated": False, "updates": 0}

    def status(link):
        if not state["authenticated"]:
            raise bridge.CliAuthError("Cookie未登録")
        return {"ok": True, "count": 1, "revision": "test-revision"}

    def register(link, content):
        assert json.loads(content)[0]["value"] == "test-only-cookie"
        state["authenticated"] = True
        return {"ok": True}

    def update(link):
        state["updates"] += 1
        conn = get_connection(seeded_db)
        try:
            purchases.upsert_purchases(
                conn,
                [
                    {
                        "item_id": f"p{i}",
                        "title": f"商品{i}",
                        "thumbnail": f"https://images.example/{i}.png",
                    }
                    for i in range(55)
                ],
            )
        finally:
            conn.close()
        return {"ok": True, "updated": 55}

    monkeypatch.setattr(bridge, "get_auth_status", status)
    monkeypatch.setattr(bridge, "import_cookies", register)
    monkeypatch.setattr(bridge, "update_purchases", update)
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1sAAAAASUVORK5CYII="
    )
    with sync_playwright() as pw:
        browser = launch_browser(pw, headless=True)
        try:
            page = browser.new_page()
            page.route(
                "https://images.example/*",
                lambda route: route.fulfill(status=200, content_type="image/png", body=png),
            )
            page.goto(live_ui)
            expect(page.locator("#auth-state")).to_have_text("Cookie未登録")
            page.locator("#b-cookie").click()
            page.locator("#cookie-file").set_input_files(
                {
                    "name": "test-cookies.json",
                    "mimeType": "application/json",
                    "buffer": json.dumps(
                        [{"name": "session", "value": "test-only-cookie", "domain": ".booth.pm"}]
                    ).encode(),
                }
            )
            page.locator('#cookie-form button[type="submit"], #cookie-form button.primary').click()
            expect(page.locator("#result-count")).to_have_text("58 商品")
            expect(page.locator("#msg")).to_have_text("55 商品を同期しました。")
            expect(page.locator("#grid .product")).to_have_count(48)
            page.wait_for_function(
                "[...document.querySelectorAll('#grid img')].some(i=>i.naturalWidth>0)"
            )
            page.locator("#page-next").click()
            expect(page.locator("#grid .product")).to_have_count(10)
            page.locator("#search").fill("商品54")
            expect(page.locator("#grid .product")).to_have_count(1)
            assert state["updates"] == 1
            # Saved cookies are detected automatically on a new page load too.
            page.reload()
            expect(page.locator("#msg")).to_have_text("55 商品を同期しました。")
            assert state["updates"] == 2
        finally:
            browser.close()


def test_library_parser_resolves_lazy_image_and_purchase_date():
    row = purchases.parse_library_html("""<div>
      <a href="/orders/order1">商品</a>
      <a href="https://example.booth.pm/items/123">商品ページ</a>
      <img src="/placeholder.png" data-src="//cdn.example/image.jpg">
      <time datetime="2026-09-30">2026年9月30日</time>
    </div>""")[0]
    assert row["thumbnail"] == "https://cdn.example/image.jpg"
    assert row["purchase_date"] == "2026-09-30"
