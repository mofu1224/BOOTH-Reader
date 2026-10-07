"""SQLite schema, connection management and forward-only migrations.

Scope
-----
BOOTH-Reader owns exactly one database file (``app.db``). It never reads or
migrates another application's database.

Concurrency
-----------
The downloader runs up to 5 worker threads, each holding its own connection and
writing ``downloads`` rows. Under the default rollback journal those writers
serialise on a whole-file lock and surface as ``database is locked``. WAL mode
lets readers run concurrently with a single writer and removes most of that
contention, so it is enabled once at init. If the journal mode cannot be set
(read-only media, network share) the code degrades to the default journal
rather than failing.

Durability
----------
WAL + ``synchronous=NORMAL`` is the standard pairing: a committed transaction
survives application crashes, and only an OS-level power loss can lose the most
recent commits. That is the correct trade for a download ledger that can always
be reconciled from the filesystem.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .errors import BoothDatabaseError, BoothSchemaTooNewError

SCHEMA_VERSION = 5

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  item_id TEXT PRIMARY KEY,
  title TEXT NOT NULL DEFAULT '',
  url TEXT NOT NULL DEFAULT '',
  shop TEXT NOT NULL DEFAULT '',
  thumbnail TEXT NOT NULL DEFAULT '',
  category TEXT NOT NULL DEFAULT '',
  published_at TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS purchases (
  item_id TEXT PRIMARY KEY REFERENCES items(item_id) ON DELETE CASCADE,
  purchase_date TEXT NOT NULL DEFAULT '',
  price TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS downloads (
  item_id TEXT NOT NULL REFERENCES items(item_id) ON DELETE CASCADE,
  file_name TEXT NOT NULL DEFAULT '',
  path TEXT NOT NULL DEFAULT '',
  path_encoding TEXT NOT NULL DEFAULT 'legacy' CHECK (path_encoding IN ('legacy','library-relative')),
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','downloading','done','failed')),
  sha256 TEXT NOT NULL DEFAULT '',
  downloaded_at TEXT NOT NULL DEFAULT '',
  url TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (item_id, file_name)
);
CREATE TABLE IF NOT EXISTS lists (
  list_id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS list_members (
  list_id INTEGER NOT NULL REFERENCES lists(list_id) ON DELETE CASCADE,
  item_id TEXT NOT NULL REFERENCES items(item_id) ON DELETE CASCADE,
  added_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (list_id, item_id)
);
CREATE INDEX IF NOT EXISTS idx_purchases_date ON purchases(purchase_date);
CREATE INDEX IF NOT EXISTS idx_items_title ON items(title);
CREATE INDEX IF NOT EXISTS idx_items_shop ON items(shop);
CREATE INDEX IF NOT EXISTS idx_list_members_item ON list_members(item_id);
CREATE INDEX IF NOT EXISTS idx_downloads_status ON downloads(status);
"""

BUSY_TIMEOUT_MS = 15000


def get_connection(db_path: str | Path) -> sqlite3.Connection:
    """Open a tuned connection.

    A file that is truncated, corrupt or simply not a database raises
    ``sqlite3.DatabaseError`` from the PRAGMA setup below. That is converted
    into :class:`BoothDatabaseError` so the user gets the file name and a
    recovery path instead of SQLite's "file is not a database".
    """
    db_path = Path(db_path)
    try:
        if db_path.parent and str(db_path.parent) not in ("", "."):
            db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), timeout=BUSY_TIMEOUT_MS / 1000.0)
    except (OSError, sqlite3.Error) as e:  # unreadable path, permissions, not a database
        raise BoothDatabaseError(str(db_path), type(e).__name__) from e
    conn.row_factory = sqlite3.Row
    try:
        current = _user_version(conn)
        if current > SCHEMA_VERSION:
            raise BoothSchemaTooNewError(str(db_path), current, SCHEMA_VERSION)
        # Foreign keys are off by default in SQLite; without this the
        # ON DELETE CASCADE rules in the schema would silently do nothing.
        conn.execute("PRAGMA foreign_keys = ON")
        # Wait instead of failing immediately when another thread holds the write lock.
        conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        conn.execute("PRAGMA synchronous = NORMAL")
    except BoothSchemaTooNewError:
        conn.close()
        raise
    except sqlite3.DatabaseError as e:
        conn.close()
        raise BoothDatabaseError(str(db_path), type(e).__name__) from e
    return conn


def ensure_current_schema(db_path: str | Path) -> None:
    """Upgrade known existing schemas; do not create or repair an empty DB."""
    if not Path(db_path).is_file():
        return
    conn = get_connection(db_path)
    try:
        current = _user_version(conn)
    finally:
        conn.close()
    if 0 < current < SCHEMA_VERSION:
        init_db(db_path)


def _set_wal(conn: sqlite3.Connection) -> bool:
    """Best-effort switch to WAL. Returns True when WAL is active."""
    try:
        mode = conn.execute("PRAGMA journal_mode = WAL").fetchone()
        return bool(mode) and str(mode[0]).lower() == "wal"
    except sqlite3.DatabaseError:
        # Read-only volume, network share, or an older SQLite. The default
        # journal still works, just with more writer contention.
        return False


def init_db(db_path: str | Path) -> Path:
    """Create or upgrade the schema. Idempotent."""
    db_path = Path(db_path)
    conn = get_connection(db_path)
    try:
        _set_wal(conn)
        # executescript commits an existing transaction implicitly. These are
        # fixed schema statements, so execute them under one explicit lock.
        conn.execute("BEGIN IMMEDIATE")
        current = _user_version(conn)
        if current > SCHEMA_VERSION:
            raise BoothSchemaTooNewError(str(db_path), current, SCHEMA_VERSION)
        for statement in SCHEMA.split(";"):
            if statement.strip():
                conn.execute(statement)
        for step in _MIGRATIONS:
            if current >= step.version:
                continue
            step.apply(conn)
        _set_user_version(conn, SCHEMA_VERSION)
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        raise BoothDatabaseError(str(db_path), type(e).__name__) from e
    finally:
        conn.close()
    return db_path


def _user_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version").fetchone()
    return int(row[0]) if row else 0


def _set_user_version(conn: sqlite3.Connection, version: int) -> None:
    # PRAGMA does not accept bound parameters.
    conn.execute(f"PRAGMA user_version = {int(version)}")


class _Migration:
    __slots__ = ("apply", "description", "version")

    def __init__(
        self, version: int, apply: Callable[[sqlite3.Connection], None], description: str
    ) -> None:
        self.version = version
        self.apply = apply
        self.description = description


def _add_perf_indexes(conn: sqlite3.Connection) -> None:
    """Indexes that make the unclassified view and download ledger cheap.

    ``get_unclassified`` LEFT JOINs ``list_members`` on ``item_id`` and
    ``downloads list --status`` filters on ``status``; without these the planner
    scans the whole table for every WebUI refresh.
    """
    conn.execute("CREATE INDEX IF NOT EXISTS idx_list_members_item ON list_members(item_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_downloads_status ON downloads(status)")


def _add_download_url(conn: sqlite3.Connection) -> None:
    """Record which source URL produced each ledger row.

    Without this the ledger cannot answer "which file belongs to this link?",
    which is what makes a re-run skip work it has already done. The column is
    added only when absent so the same step is safe for a brand-new database
    (where ``SCHEMA`` already created it) and for an upgraded one.
    """
    columns = {str(r["name"]) for r in conn.execute("PRAGMA table_info(downloads)")}
    if "url" not in columns:
        conn.execute("ALTER TABLE downloads ADD COLUMN url TEXT NOT NULL DEFAULT ''")


# Forward-only migrations. Append new entries; never edit or reorder a shipped
# one, because a user upgrading from an older build replays from their version.
def _add_list_order(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE lists ADD COLUMN sort TEXT NOT NULL DEFAULT 'newest'")
    conn.execute("ALTER TABLE list_members ADD COLUMN position INTEGER NOT NULL DEFAULT 0")
    conn.execute("ALTER TABLE purchases ADD COLUMN library_order INTEGER NOT NULL DEFAULT 0")
    conn.execute("UPDATE list_members SET position=rowid")


def _add_navigation_order(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE lists ADD COLUMN position INTEGER NOT NULL DEFAULT 0")
    rows = conn.execute("SELECT list_id FROM lists ORDER BY name,list_id").fetchall()
    conn.executemany(
        "UPDATE lists SET position=? WHERE list_id=?",
        [(position, row[0]) for position, row in enumerate(rows)],
    )


def _add_download_path_encoding(conn: sqlite3.Connection) -> None:
    columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(downloads)")}
    if "path_encoding" not in columns:
        conn.execute(
            "ALTER TABLE downloads ADD COLUMN path_encoding TEXT NOT NULL DEFAULT 'legacy' CHECK (path_encoding IN ('legacy','library-relative'))"
        )


_MIGRATIONS: list[_Migration] = [
    _Migration(1, _add_perf_indexes, "add list_members.item_id and downloads.status indexes"),
    _Migration(2, _add_download_url, "record the source url of each downloads row"),
    _Migration(3, _add_list_order, "persist list sorting and BOOTH library order"),
    _Migration(4, _add_navigation_order, "persist my-list navigation order"),
    _Migration(
        5, _add_download_path_encoding, "support portable download paths; retain legacy records"
    ),
]


def table_names(db_path: str | Path) -> list[str]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            " ORDER BY name"
        ).fetchall()
        return [r["name"] for r in rows]
    finally:
        conn.close()


def schema_version(db_path: str | Path) -> int:
    conn = get_connection(db_path)
    try:
        return _user_version(conn)
    finally:
        conn.close()


def check_integrity(db_path: str | Path) -> dict[str, Any]:
    """Run SQLite's structural and FK checks. Used by ``doctor`` and tests."""
    conn = get_connection(db_path)
    try:
        integrity = [r[0] for r in conn.execute("PRAGMA integrity_check").fetchall()]
        fk_rows = [list(r) for r in conn.execute("PRAGMA foreign_key_check").fetchall()]
        return {
            "ok": integrity == ["ok"] and not fk_rows,
            "integrity": integrity,
            "foreign_key_violations": fk_rows,
        }
    finally:
        conn.close()


def vacuum(db_path: str | Path) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute("VACUUM")
    finally:
        conn.close()


def checkpoint(db_path: str | Path) -> None:
    """Fold the WAL back into the main database file.

    Run on shutdown so a copy of just ``app.db`` is complete and a large
    ``app.db-wal`` does not linger between sessions.
    """
    conn = get_connection(db_path)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.DatabaseError:
        pass
    finally:
        conn.close()
