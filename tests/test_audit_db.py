"""Database boundaries, atomic migrations and non-destructive diagnostics."""

import json
import sqlite3

import pytest

import cli
from core import db as database
from core.errors import BoothDatabaseError, BoothSchemaTooNewError


def test_a08_every_connection_refuses_future_schema(tmp_path):
    path = database.init_db(tmp_path / "future.db")
    conn = sqlite3.connect(path)
    conn.execute(f"PRAGMA user_version={database.SCHEMA_VERSION + 1}")
    conn.commit()
    conn.close()
    with pytest.raises(BoothSchemaTooNewError):
        database.get_connection(path)


def test_a08_failed_migration_rolls_back_schema(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE preserved(value TEXT)")
    conn.execute("INSERT INTO preserved VALUES('original')")
    conn.commit()
    conn.close()

    def broken(conn):
        conn.execute("ALTER TABLE preserved ADD COLUMN temporary TEXT")
        raise sqlite3.OperationalError("fault injection")

    monkeypatch.setattr(database, "_MIGRATIONS", [database._Migration(1, broken, "injected")])
    with pytest.raises(BoothDatabaseError):
        database.init_db(path)
    conn = sqlite3.connect(path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 0
        assert [r[1] for r in conn.execute("PRAGMA table_info(preserved)")] == ["value"]
        assert conn.execute("SELECT value FROM preserved").fetchone()[0] == "original"
        assert conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == [
            ("preserved",)
        ]
    finally:
        conn.close()


def test_a08_doctor_incomplete_schema_is_fatal_and_preserves_probe(tmp_path, capsys):
    path = tmp_path / "empty.db"
    sqlite3.connect(path).close()
    library = tmp_path / "lib"
    library.mkdir()
    probe = library / ".write-probe"
    probe.write_bytes(b"user data")
    result = cli.main(["--db", str(path), "doctor", "--library", str(library), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert result == 1 and payload["ok"] is False
    assert probe.read_bytes() == b"user data"


def test_a08_uninitialised_db_has_no_traceback(tmp_path, capsys):
    assert cli.main(["--db", str(tmp_path / "empty.db"), "unclassified", "--json"]) == 1
    output = capsys.readouterr()
    assert "予期しないエラー" not in output.err
    assert "init-db" in output.err
