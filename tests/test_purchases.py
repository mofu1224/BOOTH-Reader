"""Purchase library parsing, storage and CSV export tests.

The parser is the part most exposed to BOOTH-side changes, so both the happy
path and every "the markup moved" path are pinned down here.
"""

from __future__ import annotations

import csv
import time

import pytest

from core.db import get_connection, init_db
from core.errors import (
    BoothLayoutChangedError,
    BoothNetworkError,
    exit_code_for,
)
from core.purchases import (
    export_csv,
    list_purchases,
    parse_library_html,
    upsert_purchases,
)

LIBRARY_HTML = """
<html><head><title>購入履歴</title></head>
<body>
<div class="item-list">
  <div class="item">
    <a href="/orders/111111">東方在上海人物 Requirements</a>
    <a href="https://booth.pm/ja/items/987654">商品ページ</a>
    <span class="shop-name">東方Shop</span>
    <img src="https://booth.pm/1.png">
    <span class="price">¥1,200</span>
  </div>
  <div class="item">
    <a href="/orders/222222">ゆ Cantarella</a>
    <a href="https://booth.pm/items/555111">商品ページ2</a>
    <span class="shop-name">Yuyushiki</span>
    <img data-src="https://booth.pm/2.png">
    <span class="price">無料</span>
  </div>
</div>
</body></html>
"""


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_parse_library_html_extracts_rows():
    rows = parse_library_html(LIBRARY_HTML)
    assert len(rows) == 2
    ids = sorted(r["item_id"] for r in rows)
    assert ids == ["555111", "987654"], "item id must come from the row's own link"
    first = next(r for r in rows if r["item_id"] == "987654")
    assert first["title"] == "東方在上海人物 Requirements"
    assert first["shop"] == "東方Shop"
    assert first["price"] == "¥1,200"
    assert first["thumbnail"] == "https://booth.pm/1.png"
    assert first["url"].startswith("https://accounts.booth.pm/orders/")
    second = next(r for r in rows if r["item_id"] == "555111")
    assert second["thumbnail"] == "https://booth.pm/2.png"  # data-src fallback
    assert second["price"] == "無料"


def test_parse_deduplicates_repeated_order_links():
    html = (
        '<a href="/orders/111">A</a><a href="/orders/111">A</a>'
        '<a href="https://booth.pm/ja/items/1">p</a>'
    )
    rows = parse_library_html(html)
    assert len(rows) == 1


def test_parse_falls_back_to_order_id():
    rows = parse_library_html('<a href="/orders/777">No product link</a>')
    assert rows[0]["item_id"] == "order_777"


def test_parse_scales_to_large_library():
    """Must stay near-linear: the old positional scan was quadratic."""
    parts = ["<html><body>booth"]
    for i in range(2000):
        parts.append(
            f'<div><a href="/orders/{i}">item{i}</a>'
            f'<a href="https://booth.pm/ja/items/{i}">p</a></div>'
        )
    parts.append("</body></html>")
    html = "".join(parts)
    started = time.perf_counter()
    rows = parse_library_html(html)
    elapsed = time.perf_counter() - started
    assert len(rows) == 2000
    # Correctness: each row must get its own product id, not a neighbour's.
    assert [r["item_id"] for r in rows][:3] == ["0", "1", "2"]
    assert elapsed < 8.0, f"parse took {elapsed:.2f}s for 2000 rows"


def test_order_ids_are_indexed_once():
    """Regression: the positional fallback must not rescan per row."""
    html = (
        "<html>booth"
        + "<a href='/orders/1'>a</a>" * 1
        + "".join(f"<a href='/orders/{i}'>x</a>" for i in range(2, 400))
        + "</html>"
    )
    started = time.perf_counter()
    rows = parse_library_html(html)
    assert time.perf_counter() - started < 3.0
    assert len(rows) == 399


# ---------------------------------------------------------------------------
# Layout-change detection
# ---------------------------------------------------------------------------


def test_unrelated_page_raises_layout_changed():
    with pytest.raises(BoothLayoutChangedError) as exc:
        parse_library_html("<html><body>some random page, no markers</body></html>")
    assert "BOOTH_LAYOUT_CHANGED" in str(exc.value)
    assert exit_code_for(exc.value) == 3


def test_empty_html_raises_layout_changed():
    for bad in ("", "   ", "\n\t"):
        with pytest.raises(BoothLayoutChangedError):
            parse_library_html(bad)


def test_booth_page_without_orders_and_without_empty_marker_raises():
    with pytest.raises(BoothLayoutChangedError):
        parse_library_html("<html><body>booth mwfeibnwfeibnw</body></html>")


@pytest.mark.parametrize(
    "marker",
    [
        "まだ購入していません",
        "購入履歴がありません",
        "ライブラリに何もありません",
        "No orders",
    ],
)
def test_empty_library_returns_no_rows(marker):
    html = f"<html><body>booth {marker}</body></html>"
    assert parse_library_html(html) == []


def test_age_gate_page_raises_layout_changed():
    html = "<html><body>年齢確認 あなたは18歳以上ですか？ " + "x" * 50 + "</body></html>"
    with pytest.raises(BoothLayoutChangedError):
        parse_library_html(html)


def test_href_missing_is_skipped_not_crashed():
    rows = parse_library_html('<a>no href</a><a href="">empty</a><a href="/orders/5">ok</a>')
    assert len(rows) == 1


def test_missing_beautifulsoup_reports_a_prerequisite(monkeypatch):
    """A missing parser is an install problem, not an authentication problem.

    It used to raise BoothAuthError, which appended "run auth login again" to
    an install instruction -- see tests/test_prerequisites.py.
    """
    import builtins

    from core.errors import BoothPrerequisiteError

    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "bs4":
            raise ImportError("no module named bs4")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    with pytest.raises(BoothPrerequisiteError) as exc:
        parse_library_html(LIBRARY_HTML)
    message = str(exc.value)
    assert "beautifulsoup4" in message
    assert "start.bat --repair" in message
    assert "auth login" not in message


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def test_upsert_is_idempotent_and_updates(tmp_path):
    db = tmp_path / "app.db"
    init_db(db)
    conn = get_connection(db)
    rows = parse_library_html(LIBRARY_HTML)
    assert upsert_purchases(conn, rows) == 2
    assert upsert_purchases(conn, rows) == 2  # same again, no duplicates
    assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 2
    # Changed metadata is refreshed.
    rows[0] = dict(rows[0], title="新しいタイトル")
    upsert_purchases(conn, rows)
    got = conn.execute("SELECT title FROM items WHERE item_id=?", (rows[0]["item_id"],)).fetchone()[
        0
    ]
    assert got == "新しいタイトル"
    conn.close()


def test_upsert_empty_is_noop(tmp_path):
    conn = get_connection(init_db(tmp_path / "app.db"))
    try:
        assert upsert_purchases(conn, []) == 0
    finally:
        conn.close()


def test_upsert_rolls_back_on_bad_row(tmp_path):
    """A failure part-way through must not leave half the rows committed."""
    conn = get_connection(init_db(tmp_path / "app.db"))

    class FailingConn:
        """Delegates to the real connection but raises on the third statement.

        ``sqlite3.Connection.execute`` cannot be monkeypatched, so the failure
        is injected through a proxy instead.
        """

        def __init__(self, inner):
            self._inner = inner
            self.calls = 0

        def execute(self, sql, *args, **kwargs):
            self.calls += 1
            if self.calls > 2:  # allow the first item, then fail
                raise ValueError("simulated storage failure")
            return self._inner.execute(sql, *args, **kwargs)

        def commit(self):
            return self._inner.commit()

        def rollback(self):
            return self._inner.rollback()

    proxy = FailingConn(conn)
    try:
        rows = parse_library_html(LIBRARY_HTML)
        with pytest.raises(BoothNetworkError):
            upsert_purchases(proxy, rows)  # type: ignore[arg-type]
    finally:
        conn.close()
    # Rolled back: neither item survived.
    check = get_connection(tmp_path / "app.db")
    try:
        assert check.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 0
        assert check.execute("SELECT COUNT(*) FROM purchases").fetchone()[0] == 0
    finally:
        check.close()


def test_list_purchases_limits(tmp_path):
    db = tmp_path / "app.db"
    init_db(db)
    conn = get_connection(db)
    for i in range(5):
        conn.execute("INSERT INTO items(item_id,title) VALUES(?,?)", (f"i{i}", f"T{i}"))
    conn.commit()
    try:
        assert len(list_purchases(conn, limit=-5)) == 5  # <=0 means no limit
        assert len(list_purchases(conn, limit=0)) == 5
        assert len(list_purchases(conn, limit=2)) == 2
        assert len(list_purchases(conn, limit=10**9)) == 5
        assert len(list_purchases(conn)) == 5
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------


def test_export_csv_roundtrip(tmp_path):
    rows = parse_library_html(LIBRARY_HTML)
    out = export_csv(rows, tmp_path / "out.csv")
    assert out.exists()
    with out.open(encoding="utf-8-sig", newline="") as fh:
        read = list(csv.DictReader(fh))
    assert len(read) == 2
    assert {r["title"] for r in read} == {"東方在上海人物 Requirements", "ゆ Cantarella"}
    # BOM present so Excel detects UTF-8.
    assert out.read_bytes().startswith(b"\xef\xbb\xbf")


def test_export_csv_is_atomic_and_ignores_extra_columns(tmp_path):
    rows = [{"item_id": "1", "title": "T", "unexpected": "x"}]
    out = export_csv(rows, tmp_path / "sub" / "o.csv")
    assert out.exists()
    assert not list((tmp_path / "sub").glob("*.tmp"))
    assert "unexpected" not in out.read_text(encoding="utf-8-sig")


def test_export_csv_reports_failure(tmp_path):
    """A blocked path must raise BoothNetworkError, not leak an OSError."""
    blocker = tmp_path / "out.csv"
    blocker.write_text("existing file blocks the directory", encoding="utf-8")
    with pytest.raises(BoothNetworkError):
        export_csv([{"item_id": "1"}], blocker / "sub" / "o.csv")
    # The original file must be untouched and no temp left behind.
    assert blocker.read_text(encoding="utf-8") == "existing file blocks the directory"
    assert not list(tmp_path.glob("*.tmp"))
