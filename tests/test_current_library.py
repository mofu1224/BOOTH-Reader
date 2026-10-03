"""Current purchased-library cards, isolated from recommendations and neighbours."""

import httpx
import pytest

from core import download, purchases
from core.db import get_connection, init_db
from core.errors import BoothLayoutChangedError, BoothLimitExceededError
from tests.test_audit_http import mock_http as http_fixture

mock_http = http_fixture


def card(item_id, file_id, title="商品", shop="ショップ"):
    return f"""<div class="bg-white p-16">
      <div class="flex gap-8">
        <a href="https://sample.booth.pm/items/{item_id}">
          <img class="l-library-item-thumbnail" src="https://cdn.example/{item_id}.jpg">
        </a>
        <div><a class="no-underline" href="https://sample.booth.pm/items/{item_id}">
          <div class="text-text-default font-bold">{title}</div></a>
          <a href="https://sample.booth.pm/"><img src="https://cdn.example/avatar.jpg">
            <div class="text-14">{shop}</div></a></div>
      </div>
      <div class="mt-16"><div class="desktop:flex">
        <div class="min-w-0"><div class="text-14">asset_{item_id}.zip</div></div>
        <div><div class="js-download-button" data-href="https://booth.pm/downloadables/{file_id}"></div>
          <div class="js-download-button"></div></div>
      </div></div>
    </div>"""


def test_current_cards_parse_without_orders_and_exclude_recommendations():
    html = '<main><div class="w-full">' + card("123", "456", "衣装", "衣装屋")
    html += card("789", "987", "本", "本屋") + "</div></main>"
    html += '<aside><a href="https://booth.pm/items/999">おすすめ</a></aside>'
    rows = purchases.parse_library_html(html, base_url="https://accounts.booth.pm/library?page=2")
    assert [r["item_id"] for r in rows] == ["123", "789"]
    assert rows[0]["title"] == "衣装"
    assert rows[0]["shop"] == "衣装屋"
    assert rows[0]["thumbnail"] == "https://cdn.example/123.jpg"
    assert rows[0]["url"] == "https://accounts.booth.pm/library?page=2#item-123"
    assert rows[0]["purchase_date"] == rows[0]["price"] == ""


def test_current_card_identity_failure_never_borrows_neighbour():
    html = card("123", "456").replace("sample.booth.pm/items/123", "example.invalid/items/123")
    html += card("789", "987")
    with pytest.raises(BoothLayoutChangedError):
        purchases.parse_library_html(html)


def test_current_library_download_only_resolves_selected_card(mock_http):
    seen = []

    def handle(request):
        seen.append(str(request.url))
        return httpx.Response(200, text=card("123", "456") + card("789", "987"))

    mock_http(handle)
    links = download.resolve_download_links("https://accounts.booth.pm/library?page=2#item-123", [])
    assert links == [{"url": "https://booth.pm/downloadables/456", "label": "asset_123.zip"}]
    assert len(seen) == 1  # resolving must never start a file transfer


def test_current_library_pages_deduplicate_products_keep_newest_source(mock_http, tmp_path):
    def handle(request):
        if request.url.query:
            return httpx.Response(200, text=card("123", "456") + card("789", "987"))
        return httpx.Response(
            200, text=card("123", "456") + '<a rel="next" href="/library?page=2">次へ</a>'
        )

    mock_http(handle)
    cookies = tmp_path / "cookies.json"
    cookies.write_text('[{"name":"test","value":"test-only","domain":".booth.pm"}]')
    db = init_db(tmp_path / "app.db")
    assert purchases.update_from_network(db, cookies) == 2
    conn = get_connection(db)
    try:
        rows = purchases.list_purchases(conn)
        assert [r["item_id"] for r in rows] == ["123", "789"]
        assert rows[0]["url"] == "https://accounts.booth.pm/library#item-123"
    finally:
        conn.close()


def test_selected_product_disappeared_is_not_empty_download_success(mock_http):
    mock_http(lambda request: httpx.Response(200, text=card("789", "987")))
    with pytest.raises(BoothLayoutChangedError):
        download.resolve_download_links("https://accounts.booth.pm/library#item-123", [])


@pytest.mark.parametrize(
    "url", ["https://evil.example/downloadables/456", "http://booth.pm/downloadables/456"]
)
def test_current_card_rejects_unexpected_download_host(mock_http, url):
    html = card("123", "456").replace("https://booth.pm/downloadables/456", url)
    mock_http(lambda request: httpx.Response(200, text=html))
    with pytest.raises(BoothLayoutChangedError):
        download.resolve_download_links("https://accounts.booth.pm/library#item-123", [])


def test_current_card_download_limit_remains_explicit(mock_http):
    html = card("123", "456").replace(
        '<div class="js-download-button"></div>',
        '<div class="js-download-button" data-href="https://booth.pm/downloadables/789"></div>',
    )
    mock_http(lambda request: httpx.Response(200, text=html))
    with pytest.raises(BoothLimitExceededError):
        download.resolve_download_links(
            "https://accounts.booth.pm/library#item-123", [], max_links=1
        )
