"""Hardening tests: security, boundaries, negatives, regressions (no network)."""

import json
import zipfile
from pathlib import Path

import pytest

import cli as cli_mod
from core import lists as lists_mod
from core.auth import BoothAuthError, save_cookies, status
from core.db import get_connection, init_db
from core.download import safe_extract_zip
from core.purchases import list_purchases


def _seed(db: Path, n: int = 3) -> None:
    init_db(db)
    conn = get_connection(db)
    for i in range(n):
        conn.execute(
            "INSERT INTO items(item_id,title,shop) VALUES(?,?,?)",
            (f"id{i}", f"Title {i}", f"Shop {i % 2}"),
        )
        conn.execute(
            "INSERT INTO purchases(item_id,purchase_date) VALUES(?,?)",
            (f"id{i}", f"2024-01-0{i + 1}"),
        )
    conn.commit()
    conn.close()


# --- Zip Slip ---------------------------------------------------------------


def test_zip_slip_sibling_prefix_rejected(tmp_path):
    """文字列prefix比較の bypass (dir / dir_evil) を拒否すること。"""
    z = tmp_path / "a.zip"
    with zipfile.ZipFile(z, "w") as zz:
        zz.writestr("ok.txt", "hi")
        zz.writestr("../evil.txt", "x")
        zz.writestr("/abs.txt", "x")
        zz.writestr("C:/win.txt", "x")
        zz.writestr("sub/../../escape.txt", "x")
    dest = tmp_path / "lib" / "item_title"
    files = safe_extract_zip(z, dest)
    assert files == ["ok.txt"]
    assert (dest / "ok.txt").exists()
    assert not (tmp_path / "lib" / "evil.txt").exists()
    assert not (tmp_path / "abs.txt").exists()
    assert not (tmp_path / "escape.txt").exists()


# --- Limit boundaries --------------------------------------------------------


def test_limit_boundaries(tmp_path):
    db = tmp_path / "app.db"
    _seed(db, 5)
    conn = get_connection(db)
    try:
        assert len(list_purchases(conn, limit=-5)) == 5  # 0以下は制限なし
        assert len(list_purchases(conn, limit=0)) == 5
        assert len(list_purchases(conn, limit=2)) == 2
        assert len(list_purchases(conn, limit=10**9)) == 5  # 上限クランプ
        assert len(lists_mod.get_unclassified(conn, limit=0)) == 5
        assert len(lists_mod.get_unclassified(conn, limit=2)) == 2
        assert len(lists_mod.get_classified(conn, limit=-1)) == 0
    finally:
        conn.close()


# --- Lists validation ---------------------------------------------------------


def test_lists_name_validation(tmp_path):
    db = tmp_path / "app.db"
    init_db(db)
    conn = get_connection(db)
    try:
        with pytest.raises(ValueError):
            lists_mod.create_list(conn, "")
        with pytest.raises(ValueError):
            lists_mod.create_list(conn, "   ")
        with pytest.raises(ValueError):
            lists_mod.create_list(conn, "x" * 129)
        lid = lists_mod.create_list(conn, "  fav  ")
        assert lid > 0
        # 同名再作成は冪等 (ON CONFLICT DO NOTHING)
        assert lists_mod.create_list(conn, "fav") == lid
    finally:
        conn.close()


def test_lists_numeric_name_roundtrip(tmp_path):
    db = tmp_path / "app.db"
    _seed(db, 1)
    conn = get_connection(db)
    try:
        lid = lists_mod.create_list(conn, "123")
        # 数字名でもID優先→名前フォールバックで削除できる
        lists_mod.add_member(conn, "123", "id0")
        assert lists_mod.get_unclassified(conn) == []
        assert lists_mod.delete_list(conn, str(lid)) == 1
    finally:
        conn.close()


def test_add_member_unknown_item_is_value_error(tmp_path):
    db = tmp_path / "app.db"
    _seed(db, 1)
    conn = get_connection(db)
    try:
        with pytest.raises(ValueError):
            lists_mod.add_member(conn, "no-such-list-id-99999", "ghost")
    finally:
        conn.close()


# --- Auth ---------------------------------------------------------------------


def test_auth_expiry_detection(tmp_path):
    expired = tmp_path / "exp.json"
    save_cookies(
        [{"name": "a", "value": "v", "expires": 1}, {"name": "b", "value": "w", "expires": 2}],
        expired,
    )
    with pytest.raises(BoothAuthError):
        status(expired)
    # 期限なしセッションCookieのみ → 判定不能のため有効扱い
    sess = tmp_path / "sess.json"
    save_cookies([{"name": "a", "value": "v"}], sess)
    info = status(sess)
    assert info["count"] == 1
    # 未来の期限が1つでもあれば有効
    import time

    mixed = tmp_path / "mixed.json"
    save_cookies(
        [
            {"name": "a", "value": "v", "expires": 1},
            {"name": "b", "value": "w", "expires": time.time() + 3600},
        ],
        mixed,
    )
    assert status(mixed)["count"] == 2
    # .tmp残留なし (原子書込)
    assert not list(tmp_path.glob("*.tmp"))


def test_auth_missing_cookie_file(tmp_path):
    with pytest.raises(BoothAuthError):
        status(tmp_path / "none.json")


# --- CLI negatives --------------------------------------------------------------


def test_cli_version(capsys):
    assert cli_mod.main(["--version"]) == 0
    out = capsys.readouterr().out
    assert "BOOTH-Reader" in out


def test_cli_download_conflicts(tmp_path):
    db = tmp_path / "app.db"
    init_db(db)
    with pytest.raises(SystemExit) as e:
        cli_mod.main(["--db", str(db), "download", "--item-id", "a", "--all"])
    assert e.value.code == 2
    with pytest.raises(SystemExit) as e:
        cli_mod.main(["--db", str(db), "download"])
    assert e.value.code == 2
    assert (
        cli_mod.main(
            [
                "--db",
                str(db),
                "download",
                "--item-id",
                "ghost",
                "--cookie-path",
                str(tmp_path / "none.json"),
            ]
        )
        == 1
    )


def test_cli_bad_concurrent_rejected(tmp_path, capsys):
    db = tmp_path / "app.db"
    init_db(db)
    assert cli_mod.main(["--db", str(db), "download", "--item-id", "x", "--concurrent", "6"]) == 2


def test_cli_lists_create_empty_name_rejected(tmp_path):
    """An invalid argument is a usage error, which is exit code 2."""
    db = tmp_path / "app.db"
    init_db(db)
    assert cli_mod.main(["--db", str(db), "lists", "create", "--name", ""]) == 2
    assert cli_mod.main(["--db", str(db), "lists", "create", "--name", "x" * 200]) == 2


def test_cli_download_json_is_pure(tmp_path, monkeypatch, capsys):
    """--json 出力は純JSONのみ (進捗print混入の回帰防止)。"""
    import core.download as dl_mod

    db = tmp_path / "app.db"
    lib = tmp_path / "lib"
    _seed(db, 1)
    ck = tmp_path / "ck.json"
    ck.write_text(json.dumps([{"name": "a", "value": "v"}]), encoding="utf-8")

    monkeypatch.setattr(
        dl_mod,
        "resolve_download_links",
        lambda url_or_id, cookies, timeout=30: [
            {"url": "https://example.invalid/f.bin", "label": "f.bin"}
        ],
    )

    def _fake_dl(url, dest, cookies, resume=True, timeout=60, progress_cb=None):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"data")
        return dest

    monkeypatch.setattr(dl_mod, "download_file", _fake_dl)

    rc = cli_mod.main(
        [
            "--db",
            str(db),
            "download",
            "--item-id",
            "id0",
            "--cookie-path",
            str(ck),
            "--output-dir",
            str(lib),
            "--json",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)  # 純JSONでなければここで失敗する
    assert payload["ok_count"] == 1 and payload["failed_count"] == 0
    assert (lib / "id0_Title 0" / "meta.json").exists()
    # meta.json に秘密が含まれていない
    assert '"value"' not in (lib / "id0_Title 0" / "meta.json").read_text(encoding="utf-8")


# --- Smoke: full local roundtrip --------------------------------------------------


def test_smoke_roundtrip(tmp_path, capsys):
    db = tmp_path / "app.db"
    assert cli_mod.main(["--db", str(db), "init-db"]) == 0
    capsys.readouterr()
    _seed(db, 2)
    assert cli_mod.main(["--db", str(db), "purchases", "list"]) == 0
    assert cli_mod.main(["--db", str(db), "unclassified", "--sort", "newest"]) == 0
    assert cli_mod.main(["--db", str(db), "lists", "create", "--name", "fav"]) == 0
    assert cli_mod.main(["--db", str(db), "lists", "add", "--list", "fav", "--item-id", "id0"]) == 0
    assert cli_mod.main(["--db", str(db), "lists", "list"]) == 0
    assert cli_mod.main(["--db", str(db), "downloads", "list"]) == 0
    csvp = tmp_path / "out.csv"
    assert cli_mod.main(["--db", str(db), "purchases", "list", "--csv", str(csvp)]) == 0
    assert csvp.exists() and "id0" in csvp.read_text(encoding="utf-8-sig")
    conn = get_connection(db)
    try:
        assert [r["item_id"] for r in lists_mod.get_unclassified(conn)] == ["id1"]
    finally:
        conn.close()
    # 繰り返し実行で壊れない (冪等)
    assert cli_mod.main(["--db", str(db), "lists", "add", "--list", "fav", "--item-id", "id0"]) == 0
    assert (
        cli_mod.main(["--db", str(db), "lists", "remove", "--list", "fav", "--item-id", "id0"]) == 0
    )
    conn = get_connection(db)
    try:
        assert len(lists_mod.get_unclassified(conn)) == 2
    finally:
        conn.close()


# --- Web --------------------------------------------------------------------------


def test_web_escapes_malicious_title(tmp_path):
    from fastapi.testclient import TestClient

    from web.app import create_app

    db = tmp_path / "app.db"
    init_db(db)
    conn = get_connection(db)
    evil = "<script>alert(1)</script><img src=x onerror=alert(2)>"
    conn.execute("INSERT INTO items(item_id,title,shop) VALUES('e',?,?)", (evil, evil))
    conn.commit()
    conn.close()
    client = TestClient(create_app(str(db), library_root=str(tmp_path / "lib")))
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "<script>alert(1)</script>" not in r.text  # 素通りの生タグは存在しない
    assert "&lt;script&gt;" in r.text  # エスケープ済み
    # 動的描画JSもエスケープ関数を通す
    assert "const esc" in r.text


def test_web_download_argv_output_dir():
    from web import cli_bridge as bridge

    argv = bridge.download_argv(item_id="abc", output_dir="L:/lib")
    assert "--output-dir" in argv and "L:/lib" in argv
    with pytest.raises(bridge.CliBridgeError):
        bridge.download_argv()
    with pytest.raises(bridge.CliBridgeError):
        bridge.download_argv(item_id="a b")
    with pytest.raises(bridge.CliBridgeError):
        bridge.download_argv(item_id="a", all=True)
    with pytest.raises(bridge.CliBridgeError):
        bridge.download_argv(item_id="a", concurrent=9)


def test_web_endpoints_smoke(tmp_path):
    from fastapi.testclient import TestClient

    from web.app import create_app

    db = tmp_path / "app.db"
    _seed(db, 2)
    client = TestClient(create_app(str(db), library_root=str(tmp_path / "lib")))
    assert client.get("/purchases").status_code == 200
    assert client.get("/unclassified?sort=name").status_code == 200
    assert client.get("/downloads").status_code == 200
    assert client.get("/lists").status_code == 200
    r = client.post("/lists", json={"action": "create", "name": "fav"})
    assert r.status_code == 200
    r = client.post("/lists", json={"action": "add", "list": "fav", "item_id": "id0"})
    assert r.status_code == 200
    u = client.get("/unclassified?sort=newest").json()
    assert u["count"] == 1 and u["items"][0]["item_id"] == "id1"
    # 不正入力は400系
    assert client.post("/download", json={}).status_code in (400, 422)
    assert client.post("/lists", json={"action": "add"}).status_code == 400
