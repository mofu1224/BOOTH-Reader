"""Database layer: schema, migrations, concurrency and integrity."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from core.db import (
    SCHEMA_VERSION,
    check_integrity,
    checkpoint,
    get_connection,
    init_db,
    schema_version,
    table_names,
    vacuum,
)
from core.errors import BoothSchemaTooNewError

BASE = Path(__file__).resolve().parent.parent


def test_init_creates_all_tables(tmp_path):
    db = tmp_path / "app.db"
    init_db(db)
    assert set(table_names(db)) == {"downloads", "items", "list_members", "lists", "purchases"}
    assert schema_version(db) == SCHEMA_VERSION
    report = check_integrity(db)
    assert report["ok"], report


def test_init_is_idempotent_and_preserves_data(tmp_path):
    db = tmp_path / "app.db"
    init_db(db)
    conn = get_connection(db)
    conn.execute("INSERT INTO items(item_id,title) VALUES('keep','データ')")
    conn.commit()
    conn.close()
    init_db(db)
    conn = get_connection(db)
    try:
        assert conn.execute("SELECT title FROM items").fetchone()[0] == "データ"
    finally:
        conn.close()


def test_wal_mode_enabled(tmp_path):
    db = tmp_path / "app.db"
    init_db(db)
    conn = get_connection(db)
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    finally:
        conn.close()


def test_v3_list_order_migration_preserves_visible_order_and_members(tmp_path):
    from core import lists
    from core.db import SCHEMA, _add_list_order

    db = tmp_path / "v3.db"
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _add_list_order(conn)
    conn.execute("INSERT INTO items(item_id,title) VALUES('keep','商品')")
    conn.executemany("INSERT INTO lists(name,sort) VALUES(?,?)", [("B", "name"), ("A", "manual")])
    conn.execute("INSERT INTO list_members(list_id,item_id,position) VALUES(1,'keep',7)")
    conn.execute("PRAGMA user_version=3")
    conn.commit()
    conn.close()
    init_db(db)
    init_db(db)
    conn = get_connection(db)
    try:
        state = lists.library(conn)
        assert [r["name"] for r in state["lists"]] == ["A", "B"]
        assert [r["sort"] for r in state["lists"]] == ["manual", "name"]
        assert state["members"] == [{"list_id": 1, "item_id": "keep", "position": 7}]
    finally:
        conn.close()


def test_foreign_keys_enforced(tmp_path):
    """ON DELETE CASCADE only works if the pragma is on for every connection."""
    db = tmp_path / "app.db"
    init_db(db)
    conn = get_connection(db)
    conn.execute("INSERT INTO items(item_id,title) VALUES('a','A')")
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO purchases(item_id,purchase_date) VALUES('ghost','x')")
    conn.rollback()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO list_members(list_id,item_id) VALUES(999,'a')")
    conn.rollback()
    # Deleting the item cascades to purchases.
    conn.execute("INSERT INTO purchases(item_id,purchase_date) VALUES('a','x')")
    conn.commit()
    conn.execute("DELETE FROM items WHERE item_id='a'")
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM purchases").fetchone()[0] == 0
    conn.close()


def test_status_check_constraint(tmp_path):
    db = init_db(tmp_path / "app.db")
    conn = get_connection(db)
    conn.execute("INSERT INTO items(item_id) VALUES('a')")
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO downloads(item_id,file_name,status) VALUES('a','f','bogus')")
    conn.close()


def test_concurrent_writers_do_not_lock_each_other_out(tmp_path):
    """Regression: 5 download workers writing status must not deadlock."""
    db = init_db(tmp_path / "app.db")
    conn = get_connection(db)
    conn.execute("INSERT INTO items(item_id) VALUES('a')")
    conn.commit()
    conn.close()

    errors: list[Exception] = []
    barrier = threading.Barrier(5)

    def writer(n: int) -> None:
        try:
            c = get_connection(db)
            barrier.wait(timeout=20)
            for i in range(25):
                c.execute(
                    """INSERT INTO downloads(item_id,file_name,status,path,downloaded_at)
                       VALUES('a',?,'downloading','',datetime('now'))
                       ON CONFLICT(item_id,file_name) DO UPDATE SET status='downloading'""",
                    (f"w{n}-{i}",),
                )
                c.commit()
            c.close()
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert not errors, errors
    conn = get_connection(db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM downloads").fetchone()[0] == 125
    finally:
        conn.close()


def test_repeated_open_close_does_not_leak_or_grow(tmp_path):
    db = init_db(tmp_path / "app.db")
    for _ in range(200):
        conn = get_connection(db)
        conn.execute("SELECT 1")
        conn.close()
    assert check_integrity(db)["ok"]
    vacuum(db)
    checkpoint(db)
    assert check_integrity(db)["ok"]


def test_newer_schema_is_refused(tmp_path):
    """A database from a future build must not be silently downgraded.

    The refusal is also a routine "please update" case, so it must reach the
    user as an actionable message and never as a traceback. It used to be a bare
    ``sqlite3.DatabaseError``, which the CLI's catch-all handler reported as
    "予期しないエラーが発生しました" together with a full stack trace.
    """
    db = init_db(tmp_path / "app.db")
    conn = get_connection(db)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 5}")
    conn.commit()
    conn.close()
    with pytest.raises(BoothSchemaTooNewError) as exc:
        init_db(db)
    message = str(exc.value)
    assert "schema" in message
    # The remedy is to update the program, not to repair the file.
    assert "Update" in message
    assert "schema" in str(sqlite3.DatabaseError(message))


def test_newer_schema_is_reported_without_a_traceback(tmp_path):
    """The CLI must not print a stack trace for a deliberate refusal."""
    proc = subprocess.run(
        [sys.executable, str(BASE / "cli.py"), "--db", str(_newer_schema_db(tmp_path)), "init-db"],
        capture_output=True,
        text=True,
        timeout=120,
        encoding="utf-8",
        errors="replace",
        env=dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8"),
        check=False,
    )
    assert proc.returncode == 1
    assert "Traceback" not in proc.stderr
    assert "Unexpected error" not in proc.stderr
    assert "schema" in proc.stderr


def _newer_schema_db(tmp_path: Path) -> Path:
    db = init_db(tmp_path / "future.db")
    conn = get_connection(db)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 5}")
    conn.commit()
    conn.close()
    return db


def test_migration_from_older_version_runs(tmp_path):
    """A pre-migration database must be brought forward, not ignored."""
    db = tmp_path / "app.db"
    conn = get_connection(db)
    # Create only the v0 shape: tables but no perf indexes.
    conn.executescript("""
      CREATE TABLE items (item_id TEXT PRIMARY KEY, title TEXT NOT NULL DEFAULT '',
        url TEXT NOT NULL DEFAULT '', shop TEXT NOT NULL DEFAULT '',
        thumbnail TEXT NOT NULL DEFAULT '', category TEXT NOT NULL DEFAULT '',
        published_at TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT (datetime('now')));
      CREATE TABLE purchases (item_id TEXT PRIMARY KEY REFERENCES items(item_id)
        ON DELETE CASCADE, purchase_date TEXT NOT NULL DEFAULT '',
        price TEXT NOT NULL DEFAULT '');
      CREATE TABLE downloads (item_id TEXT NOT NULL REFERENCES items(item_id)
        ON DELETE CASCADE, file_name TEXT NOT NULL DEFAULT '',
        path TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','downloading','done','failed')),
        sha256 TEXT NOT NULL DEFAULT '',
        downloaded_at TEXT NOT NULL DEFAULT '', PRIMARY KEY (item_id, file_name));
      CREATE TABLE lists (list_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE);
      CREATE TABLE list_members (list_id INTEGER NOT NULL REFERENCES lists(list_id)
        ON DELETE CASCADE, item_id TEXT NOT NULL REFERENCES items(item_id)
        ON DELETE CASCADE, added_at TEXT NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY (list_id, item_id));
      PRAGMA user_version = 0;
    """)
    conn.execute("INSERT INTO items(item_id,title) VALUES('old','既存データ')")
    conn.commit()
    conn.close()

    init_db(db)
    assert schema_version(db) == SCHEMA_VERSION
    indexes = {
        r["name"]
        for r in get_connection(db).execute("SELECT name FROM sqlite_master WHERE type='index'")
    }
    assert "idx_list_members_item" in indexes
    assert "idx_downloads_status" in indexes
    conn = get_connection(db)
    try:
        assert (
            conn.execute("SELECT title FROM items WHERE item_id='old'").fetchone()[0]
            == "既存データ"
        )
    finally:
        conn.close()


def test_corrupt_database_is_reported_not_hidden(tmp_path):
    """A corrupt file must name itself and offer a recovery path.

    SQLite's own "file is not a database" is useless to a user who has just
    lost their library index, so it is translated.
    """
    from core.errors import BoothDatabaseError, exit_code_for

    db = tmp_path / "app.db"
    db.write_bytes(b"this is definitely not a sqlite database" * 40)
    with pytest.raises(BoothDatabaseError) as exc:
        get_connection(db).execute("SELECT * FROM items").fetchall()
    message = str(exc.value)
    assert "app.db" in message  # names the file
    assert "init-db" in message  # offers a way forward
    assert "--db" in message  # offers an alternative location
    assert exit_code_for(exc.value) == 1


def test_truncated_database_is_reported(tmp_path):
    """A file that starts like SQLite but is cut short is still detected."""
    from core.errors import BoothDatabaseError

    db = init_db(tmp_path / "app.db")
    raw = db.read_bytes()
    db.write_bytes(raw[: len(raw) // 2])
    with pytest.raises(BoothDatabaseError):
        get_connection(db).execute("SELECT name FROM sqlite_master").fetchall()


def test_directory_instead_of_database_is_reported(tmp_path):
    from core.errors import BoothDatabaseError

    as_dir = tmp_path / "app.db"
    as_dir.mkdir()
    with pytest.raises(BoothDatabaseError):
        get_connection(as_dir)


def test_connection_settings(tmp_path):
    conn = get_connection(init_db(tmp_path / "app.db"))
    try:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] >= 5000
        assert conn.execute("PRAGMA synchronous").fetchone()[0] in (1, 2)
    finally:
        conn.close()


def test_nested_db_path_is_created(tmp_path):
    nested = tmp_path / "a" / "b" / "c" / "app.db"
    init_db(nested)
    assert nested.exists()
