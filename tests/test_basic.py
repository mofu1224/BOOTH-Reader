"""Tests for M0-M4 core paths (no network)."""

import tempfile
import zipfile
from pathlib import Path

from core import lists as lists_mod
from core.db import get_connection, init_db
from core.download import check_concurrent, safe_extract_zip, safe_title, sha256_of
from core.errors import BOOTH_LAYOUT_CHANGED, BoothLayoutChangedError
from core.purchases import parse_library_html


def test_init_tables():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "app.db"
        init_db(db)
        conn = get_connection(db)
        try:
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert {"items", "purchases", "downloads", "lists", "list_members"} <= tables
        finally:
            conn.close()


def test_unclassified_excludes_classified():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "app.db"
        init_db(db)
        conn = get_connection(db)
        conn.execute("INSERT INTO items(item_id,title) VALUES('a','B'),('b','A')")
        conn.execute(
            "INSERT INTO purchases(item_id,purchase_date) VALUES('a','2024-01-02'),('b','2024-01-01')"
        )
        lid = lists_mod.create_list(conn, "fav")
        lists_mod.add_member(conn, lid, "a")
        rows = lists_mod.get_unclassified(conn, sort="newest")
        assert [r["item_id"] for r in rows] == ["b"]
        rows_old = lists_mod.get_unclassified(conn, sort="oldest")
        assert [r["item_id"] for r in rows_old] == ["b"]
        conn.close()


def test_layout_changed_detection():
    assert BOOTH_LAYOUT_CHANGED == "BOOTH_LAYOUT_CHANGED"
    try:
        parse_library_html(
            "<html><body>hello booth but no orders marker at all, some random page without markers</body></html>"
        )
    except BoothLayoutChangedError as e:
        assert "BOOTH_LAYOUT_CHANGED" in str(e)
    else:
        raise AssertionError("should raise")


def test_zip_safety_and_sha():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        z = td / "a.zip"
        with zipfile.ZipFile(z, "w") as zz:
            zz.writestr("ok.txt", "hi")
            zz.writestr("../evil.txt", "x")
        out = td / "ex"
        files = safe_extract_zip(z, out)
        assert "ok.txt" in files
        assert not (td / "evil.txt").exists()
        assert len(sha256_of(z)) == 64
        try:
            check_concurrent(99)
        except ValueError:
            pass
        else:
            raise AssertionError("concurrent limit should fail")
        assert safe_title("a:b/c") == "a_b_c"
