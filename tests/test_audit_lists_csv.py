"""Consistent list identity and safe spreadsheet exports."""

import csv

import pytest

from core import lists, purchases
from core.db import get_connection


def test_a09_numeric_list_name_remove_roundtrip(seeded_db):
    conn = get_connection(seeded_db)
    try:
        lists.create_list(conn, "123")
        lists.add_member(conn, "123", "id0")
        assert lists.remove_member(conn, "123", "id0") == 1
        assert len(lists.get_unclassified(conn)) == 3
    finally:
        conn.close()


def test_a09_invalid_item_never_creates_list(seeded_db):
    conn = get_connection(seeded_db)
    try:
        with pytest.raises(ValueError):
            lists.add_member(conn, "new list", "ghost")
        assert lists.list_lists(conn) == []
    finally:
        conn.close()


@pytest.mark.parametrize("name", ["a\nb", "a\rb", "a\x00b"])
def test_a09_cli_list_control_characters_rejected(db, name):
    conn = get_connection(db)
    try:
        with pytest.raises(ValueError):
            lists.create_list(conn, name)
    finally:
        conn.close()


@pytest.mark.parametrize(
    "value",
    ['=HYPERLINK("https://example.invalid")', "+SUM(1,2)", "-1+2", "@SUM(1,2)", "\t=1+2", "  =1+2"],
)
def test_a09_export_neutralises_formulas(tmp_path, value):
    path = purchases.export_csv([{"item_id": "1", "title": value}], tmp_path / "out.csv")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["title"] == "'" + value
