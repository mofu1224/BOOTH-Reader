"""lists + 未分類 (LEFT JOIN を既定ビューに。分類済みは既定で非表示)."""

from __future__ import annotations

import sqlite3

SORTS = ("newest", "oldest", "name", "shop")

ORDER_BY = {
    "newest": "p.purchase_date DESC, p.library_order ASC, i.item_id ASC",
    "oldest": "p.purchase_date ASC, p.library_order DESC, i.item_id ASC",
    "name": "i.title COLLATE NOCASE ASC",
    "shop": "i.shop COLLATE NOCASE ASC, i.title COLLATE NOCASE ASC",
}


def _order(sort: str) -> str:
    s = (sort or "newest").lower()
    if s not in ORDER_BY:
        raise ValueError(f"sort must be one of {SORTS}")
    return ORDER_BY[s]


def _clamp_limit(limit: int | None) -> int | None:
    if limit is None:
        return None
    v = int(limit)
    if v <= 0:
        return None  # 0以下は制限なし (従来の `if limit:` 扱いを維持)
    return max(1, min(v, 1000))


def _check_name(name: str) -> str:
    v = (name or "").strip()
    if not v or len(v) > 128 or any(c in v for c in "\r\n\x00"):
        raise ValueError("リスト名は1〜128文字で指定してください")
    return v


def create_list(conn: sqlite3.Connection, name: str) -> int:
    name = _check_name(name)
    # ON CONFLICT DO NOTHING makes creation idempotent: re-creating an existing
    # list returns its id instead of raising.
    conn.execute(
        "INSERT INTO lists(name,position) SELECT ?,COALESCE(MAX(position),-1)+1 FROM lists WHERE 1 "
        "ON CONFLICT(name) DO NOTHING",
        (name,),
    )
    conn.commit()
    row = conn.execute("SELECT list_id FROM lists WHERE name=?", (name,)).fetchone()
    return int(row["list_id"])


def list_lists(conn: sqlite3.Connection) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            "SELECT list_id,name,sort,position FROM lists ORDER BY position,list_id"
        ).fetchall()
    ]


def _resolve_list(conn: sqlite3.Connection, name_or_id: str) -> int | None:
    key = _check_name(str(name_or_id))
    if key.isdecimal() and len(key) < 20 and int(key) <= 2**63 - 1:
        row = conn.execute("SELECT list_id FROM lists WHERE list_id=?", (int(key),)).fetchone()
        if row is not None:
            return int(row["list_id"])
    row = conn.execute("SELECT list_id FROM lists WHERE name=?", (key,)).fetchone()
    return int(row["list_id"]) if row is not None else None


def delete_list(conn: sqlite3.Connection, name_or_id: str) -> int:
    list_id = _resolve_list(conn, name_or_id)
    cur = conn.execute("DELETE FROM lists WHERE list_id=?", (list_id,))
    conn.commit()
    return cur.rowcount


def add_member(conn: sqlite3.Connection, list_id_or_name: str, item_id: str) -> None:
    key = _check_name(str(list_id_or_name))
    # item存在確認
    if conn.execute("SELECT 1 FROM items WHERE item_id=?", (item_id,)).fetchone() is None:
        raise ValueError(f"item_id not found: {item_id}")
    try:
        conn.execute("BEGIN IMMEDIATE")
        list_id = _resolve_list(conn, key)
        existing = conn.execute(
            "SELECT list_id FROM list_members WHERE item_id=? AND list_id<>?",
            (item_id, list_id if list_id is not None else -1),
        ).fetchone()
        if existing is not None:
            raise ValueError("この商品は既に別のリストに登録されています")
        if list_id is None:
            conn.execute(
                "INSERT INTO lists(name,position) SELECT ?,COALESCE(MAX(position),-1)+1 FROM lists",
                (key,),
            )
            list_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        conn.execute(
            "INSERT INTO list_members(list_id,item_id,position) "
            "SELECT ?,?,COALESCE(MAX(position),-1)+1 FROM list_members WHERE list_id=? "
            "ON CONFLICT DO NOTHING",
            (list_id, item_id, list_id),
        )
        conn.commit()
    except ValueError:
        conn.rollback()
        raise
    except sqlite3.Error as e:
        conn.rollback()
        raise ValueError(f"リスト追加に失敗しました ({type(e).__name__})") from e


def remove_member(conn: sqlite3.Connection, list_id_or_name: str, item_id: str) -> int:
    list_id = _resolve_list(conn, list_id_or_name)
    cur = conn.execute("DELETE FROM list_members WHERE list_id=? AND item_id=?", (list_id, item_id))
    conn.commit()
    return cur.rowcount


def set_sort(conn: sqlite3.Connection, key: str, sort: str) -> None:
    if sort not in (*SORTS, "manual"):
        raise ValueError("並び順が不正です")
    list_id = _resolve_list(conn, key)
    if list_id is None:
        raise ValueError("リストが見つかりません")
    conn.execute("UPDATE lists SET sort=? WHERE list_id=?", (sort, list_id))
    conn.commit()


def reorder(conn: sqlite3.Connection, key: str, item_ids: list[str]) -> None:
    list_id = _resolve_list(conn, key)
    if list_id is None:
        raise ValueError("リストが見つかりません")
    try:
        conn.execute("BEGIN IMMEDIATE")
        members = {
            r[0]
            for r in conn.execute("SELECT item_id FROM list_members WHERE list_id=?", (list_id,))
        }
        if len(item_ids) != len(set(item_ids)) or set(item_ids) != members:
            raise ValueError("リストの商品が変更されています。表示を更新してください")
        conn.executemany(
            "UPDATE list_members SET position=? WHERE list_id=? AND item_id=?",
            [(position, list_id, item_id) for position, item_id in enumerate(item_ids)],
        )
        conn.execute("UPDATE lists SET sort='manual' WHERE list_id=?", (list_id,))
        conn.commit()
    except (ValueError, sqlite3.Error):
        conn.rollback()
        raise


def reorder_lists(conn: sqlite3.Connection, list_ids: list[int]) -> None:
    if any(type(i) is not int or not 1 <= i <= 2**63 - 1 for i in list_ids):
        raise ValueError("リストID配列の形式が不正です")
    try:
        conn.execute("BEGIN IMMEDIATE")
        existing = {row[0] for row in conn.execute("SELECT list_id FROM lists")}
        if len(list_ids) != len(set(list_ids)) or set(list_ids) != existing:
            raise ValueError("マイリストが変更されています。表示を更新してください")
        conn.executemany(
            "UPDATE lists SET position=? WHERE list_id=?",
            [(position, list_id) for position, list_id in enumerate(list_ids)],
        )
        conn.commit()
    except (ValueError, sqlite3.Error):
        conn.rollback()
        raise


def library(conn: sqlite3.Connection) -> dict:
    from .purchases import list_purchases

    return {
        "items": list_purchases(conn),
        "lists": list_lists(conn),
        "members": [
            dict(r)
            for r in conn.execute(
                "SELECT list_id,item_id,position FROM list_members ORDER BY position,item_id"
            )
        ],
    }


def get_unclassified(
    conn: sqlite3.Connection, sort: str = "newest", limit: int | None = None
) -> list[dict]:
    """Return items that are not in any list.

    The only interpolated fragment is ``ORDER_BY[sort]``, a constant taken from
    a fixed dict after validation in :func:`_order`, so no caller input ever
    reaches the SQL text. Values are always bound as parameters.
    """
    order = _order(sort)
    q = f"""SELECT i.item_id,i.title,i.url,i.shop,i.thumbnail,i.category,i.published_at,
                   p.purchase_date,p.price
            FROM items i
            LEFT JOIN purchases p ON p.item_id=i.item_id
            LEFT JOIN list_members m ON m.item_id=i.item_id
            WHERE m.item_id IS NULL
            ORDER BY {order}"""  # noqa: S608
    limit = _clamp_limit(limit)
    if limit is not None:
        q += " LIMIT ?"
        return [dict(r) for r in conn.execute(q, (limit,)).fetchall()]
    return [dict(r) for r in conn.execute(q).fetchall()]


def get_classified(
    conn: sqlite3.Connection, sort: str = "newest", limit: int | None = None
) -> list[dict]:
    """Return items that belong to at least one list."""
    order = _order(sort)
    q = f"""SELECT DISTINCT i.item_id,i.title,i.url,i.shop,i.thumbnail,i.category,i.published_at,
                   p.purchase_date,p.price
            FROM items i
            LEFT JOIN purchases p ON p.item_id=i.item_id
            INNER JOIN list_members m ON m.item_id=i.item_id
            ORDER BY {order}"""  # noqa: S608
    limit = _clamp_limit(limit)
    if limit is not None:
        q += " LIMIT ?"
        return [dict(r) for r in conn.execute(q, (limit,)).fetchall()]
    return [dict(r) for r in conn.execute(q).fetchall()]
