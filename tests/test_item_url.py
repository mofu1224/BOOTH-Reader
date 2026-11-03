"""Free-download items imported from a BOOTH product URL."""

from __future__ import annotations

import json

import pytest

from core import lists
from core.db import get_connection, init_db
from core.items import add_item_from_url, parse_item_page, parse_item_url


def _item_html(
    *,
    name: str = "無料素材",
    shop: str = "テストショップ",
    image: str = "https://booth.pximg.net/example/thumb.jpg",
    price: str | int = 0,
    downloadables: bool = True,
) -> str:
    data = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": name,
        "brand": {"@type": "Brand", "name": shop},
        "image": image,
        "offers": {"@type": "Offer", "price": str(price), "priceCurrency": "JPY"},
    }
    link = '<a href="https://booth.pm/downloadables/1?variation_id=2">無料ダウンロード</a>'
    return (
        "<html><head>"
        '<meta property="og:title" content="無料素材 - テストショップ - BOOTH">'
        "</head><body>"
        f"{link if downloadables else ''}"
        f'<script type="application/ld+json">{json.dumps(data)}</script>'
        "</body></html>"
    )


@pytest.mark.parametrize(
    "value,expected",
    [
        ("https://booth.pm/ja/items/1234567", ("1234567", "https://booth.pm/ja/items/1234567")),
        ("https://booth.pm/en/items/1234567/", ("1234567", "https://booth.pm/ja/items/1234567")),
        ("https://shop.booth.pm/items/1234567", ("1234567", "https://booth.pm/ja/items/1234567")),
    ],
)
def test_parse_item_url(value, expected):
    assert parse_item_url(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "http://booth.pm/ja/items/1",
        "https://example.com/ja/items/1",
        "https://booth.pm/ja/items/abc",
        "https://booth.pm/ja/library",
    ],
)
def test_parse_item_url_rejects_non_product_urls(value):
    with pytest.raises(ValueError):
        parse_item_url(value)


def test_parse_item_url_drops_query_before_fetching():
    assert parse_item_url("https://booth.pm/ja/items/1?next=https://example.com") == (
        "1",
        "https://booth.pm/ja/items/1",
    )


def test_parse_item_page_reads_json_ld_and_free_download():
    row = parse_item_page(_item_html(), "https://booth.pm/ja/items/1234567")
    assert row == {
        "title": "無料素材",
        "shop": "テストショップ",
        "thumbnail": "https://booth.pximg.net/example/thumb.jpg",
        "free": True,
        "price": "0",
    }


def test_parse_item_page_marks_paid_item_as_not_free():
    row = parse_item_page(
        _item_html(price=500, downloadables=False), "https://booth.pm/ja/items/1234567"
    )
    assert row["free"] is False
    assert row["price"] == "500"


def test_add_item_from_url_creates_url_source_and_can_be_classified(tmp_path, monkeypatch):
    db = init_db(tmp_path / "app.db")
    metadata = {
        "item_id": "1234567",
        "url": "https://booth.pm/ja/items/1234567",
        "title": "無料素材",
        "shop": "テストショップ",
        "thumbnail": "https://booth.pximg.net/example/thumb.jpg",
        "free": True,
        "price": "0",
    }
    monkeypatch.setattr("core.items.fetch_item_metadata", lambda *args, **kwargs: metadata)

    conn = get_connection(db)
    try:
        created = add_item_from_url(conn, metadata["url"])
        assert created["created"] is True
        lists.add_member(conn, "お気に入り", "1234567")
        row = conn.execute("SELECT title,url,source FROM items WHERE item_id='1234567'").fetchone()
        assert dict(row) == {
            "title": "無料素材",
            "url": "https://booth.pm/ja/items/1234567",
            "source": "url",
        }
        assert [r["item_id"] for r in lists.get_unclassified(conn)] == []
    finally:
        conn.close()


def test_add_item_from_url_keeps_library_url_of_a_purchased_item(tmp_path, monkeypatch):
    db = init_db(tmp_path / "app.db")
    conn = get_connection(db)
    try:
        conn.execute(
            "INSERT INTO items(item_id,title,url,source) VALUES('1','購入品',?,'purchase')",
            ("https://accounts.booth.pm/library#item-1",),
        )
        conn.execute("INSERT INTO purchases(item_id,purchase_date) VALUES('1','2026-01-01')")
        conn.commit()
    finally:
        conn.close()

    metadata = {
        "item_id": "1",
        "url": "https://booth.pm/ja/items/1",
        "title": "公開ページ名",
        "shop": "ショップ",
        "thumbnail": "",
        "free": True,
        "price": "0",
    }
    monkeypatch.setattr("core.items.fetch_item_metadata", lambda *args, **kwargs: metadata)

    conn = get_connection(db)
    try:
        result = add_item_from_url(conn, metadata["url"])
        assert result["created"] is False
        row = conn.execute("SELECT title,url,source FROM items WHERE item_id='1'").fetchone()
        assert dict(row) == {
            "title": "購入品",
            "url": "https://accounts.booth.pm/library#item-1",
            "source": "purchase",
        }
    finally:
        conn.close()


def test_add_item_from_url_rejects_paid_product(tmp_path, monkeypatch):
    db = init_db(tmp_path / "app.db")
    monkeypatch.setattr(
        "core.items.fetch_item_metadata",
        lambda *args, **kwargs: {
            "item_id": "1",
            "url": "https://booth.pm/ja/items/1",
            "title": "有料品",
            "shop": "",
            "thumbnail": "",
            "free": False,
            "price": "500",
        },
    )
    conn = get_connection(db)
    try:
        with pytest.raises(ValueError, match="not a free download"):
            add_item_from_url(conn, "https://booth.pm/ja/items/1")
        assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 0
    finally:
        conn.close()


def test_free_download_button_title_becomes_the_file_name(monkeypatch):
    from core import download

    html = (
        '<a href="https://booth.pm/downloadables/1?variation_id=2" '
        'title="ReFUSION.zip"><span>無料ダウンロード</span></a>'
    )

    class Response:
        url = "https://booth.pm/ja/items/1"
        status_code = 200
        text = html

    monkeypatch.setattr(download.net, "request", lambda *args, **kwargs: Response())
    links = download.resolve_download_links("https://booth.pm/ja/items/1", [])
    assert links == [
        {
            "url": "https://booth.pm/downloadables/1?variation_id=2",
            "label": "ReFUSION.zip",
        }
    ]


def test_schema_migration_adds_source_to_existing_items(tmp_path):
    db = tmp_path / "old.db"
    conn = get_connection(db)
    try:
        conn.executescript(
            """
            CREATE TABLE items (
              item_id TEXT PRIMARY KEY,
              title TEXT NOT NULL DEFAULT '',
              url TEXT NOT NULL DEFAULT '',
              shop TEXT NOT NULL DEFAULT '',
              thumbnail TEXT NOT NULL DEFAULT '',
              category TEXT NOT NULL DEFAULT '',
              published_at TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            INSERT INTO items(item_id,title) VALUES('old','既存');
            PRAGMA user_version=5;
            """
        )
        conn.commit()
    finally:
        conn.close()
    init_db(db)
    conn = get_connection(db)
    try:
        row = conn.execute("SELECT source FROM items WHERE item_id='old'").fetchone()
        assert row["source"] == "purchase"
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 6
    finally:
        conn.close()


def test_cli_lists_add_url_adds_product_and_membership(tmp_path, monkeypatch, capsys):
    import cli

    db = init_db(tmp_path / "app.db")
    metadata = {
        "item_id": "1234567",
        "url": "https://booth.pm/ja/items/1234567",
        "title": "無料素材",
        "shop": "テストショップ",
        "thumbnail": "",
        "free": True,
        "price": "0",
    }
    monkeypatch.setattr("core.items.fetch_item_metadata", lambda *args, **kwargs: metadata)

    code = cli.main(
        [
            "--db",
            str(db),
            "lists",
            "add",
            "--list",
            "無料",
            "--url",
            metadata["url"],
            "--json",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["item_id"] == "1234567"
    assert payload["item"]["title"] == "無料素材"

    conn = get_connection(db)
    try:
        assert conn.execute("SELECT source FROM items WHERE item_id='1234567'").fetchone()[0] == (
            "url"
        )
        assert [row["item_id"] for row in lists.get_unclassified(conn)] == []
    finally:
        conn.close()


def test_cli_lists_add_url_rejects_non_booth_url(tmp_path, capsys):
    import cli

    db = init_db(tmp_path / "app.db")
    code = cli.main(
        [
            "--db",
            str(db),
            "lists",
            "add",
            "--list",
            "無料",
            "--url",
            "https://example.com/ja/items/1",
        ]
    )
    assert code == 2
    assert "BOOTH product URL" in capsys.readouterr().err
