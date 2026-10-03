"""Purchase rows must never borrow a neighbouring product identity."""

import httpx
import pytest

from core import purchases
from core.db import get_connection, init_db
from core.errors import BoothLayoutChangedError, BoothLimitExceededError
from tests.test_audit_http import mock_http as _mock_http

mock_http = _mock_http


def test_a07_missing_product_is_not_neighbour_product():
    html = (
        '<html><body><div><a href="/orders/1">missing</a></div>'
        '<div><a href="/orders/2">valid</a><a href="https://booth.pm/items/22">p</a>'
        '<span class="shop">other shop</span><span>¥100</span></div></body></html>'
    )
    rows = purchases.parse_library_html(html)
    assert [r["item_id"] for r in rows] == ["order_1", "22"]
    assert rows[0]["shop"] == rows[0]["price"] == ""


def test_a07_nested_order_anchor_stays_in_own_row():
    html = (
        "<html><body>"
        + "".join(
            f'<div class="row"><h2><a href="/orders/{i}">item{i}</a></h2>'
            f'<a href="https://booth.pm/items/{i}">p</a><span class="shop">shop{i}</span></div>'
            for i in range(1, 4)
        )
        + "</body></html>"
    )
    rows = purchases.parse_library_html(html)
    assert [r["item_id"] for r in rows] == ["1", "2", "3"]


def test_a07_limit_is_explicit_failure(monkeypatch):
    monkeypatch.setattr(purchases, "MAX_ROWS", 1)
    with pytest.raises(BoothLimitExceededError):
        purchases.parse_library_html('<a href="/orders/1">one</a><a href="/orders/2">two</a>')


def test_a07_invalid_order_links_do_not_become_empty_success():
    with pytest.raises(BoothLayoutChangedError):
        purchases.parse_library_html('<a href="/orders/">invalid booth order</a>')


def test_a07_paginated_library_imports_all_pages(mock_http, tmp_path):
    seen = []

    def handler(request):
        seen.append(str(request.url))
        if request.url.query:
            return httpx.Response(200, text='<a href="/orders/2">two</a>')
        return httpx.Response(
            200, text='<a href="/orders/1">one</a><a rel="next" href="/library?page=2">次へ</a>'
        )

    mock_http(handler)
    jar = tmp_path / "ck.json"
    jar.write_text('[{"name":"a","value":"v","domain":".booth.pm"}]', encoding="utf-8")
    db = init_db(tmp_path / "d.db")
    assert purchases.update_from_network(db, jar) == 2
    assert len(seen) == 2
    conn = get_connection(db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM purchases").fetchone()[0] == 2
    finally:
        conn.close()
