"""Web UI and CLI-bridge tests. No network access, no real login."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.db import get_connection, init_db
from web import cli_bridge as bridge
from web.app import create_app


def _seed(db: Path, n: int = 3) -> None:
    conn = get_connection(db)
    for i in range(n):
        conn.execute(
            "INSERT INTO items(item_id,title,shop) VALUES(?,?,?)",
            (f"id{i}", f"タイトル{i}", f"ショップ{i}"),
        )
        conn.execute(
            "INSERT INTO purchases(item_id,purchase_date) VALUES(?,?)",
            (f"id{i}", f"2024-01-0{i + 1}"),
        )
    conn.commit()
    conn.close()


def _run_json(db: Path, *args: str) -> dict:
    env = dict(**{k: v for k, v in _child_env().items()})
    proc = subprocess.run(
        [sys.executable, str(_CLI()), "--db", str(db), *args, "--json"],
        capture_output=True,
        text=True,
        timeout=120,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    assert proc.returncode == 0, f"CLI failed: {proc.stderr[-800:]}"
    return json.loads(proc.stdout)


def _CLI() -> Path:
    return Path(__file__).resolve().parent.parent / "cli.py"


def _child_env() -> dict:
    import os

    return dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")


# --- CLI JSON contract ------------------------------------------------------


def test_cli_json_unclassified_purchases_downloads(tmp_path):
    db = tmp_path / "app.db"
    init_db(db)
    _seed(db, 1)

    u = _run_json(db, "unclassified", "--sort", "newest")
    assert u["count"] == 1 and u["items"][0]["item_id"] == "id0"

    p = _run_json(db, "purchases", "list")
    assert p["count"] == 1 and p["items"][0]["item_id"] == "id0"

    d = _run_json(db, "downloads", "list")
    assert d["count"] == 0 and d["downloads"] == []

    ls = _run_json(db, "lists", "list")
    assert ls["count"] == 0


def test_cli_json_is_ascii_only(tmp_path):
    """--json must survive a Japanese console pipe, so it is ASCII-escaped."""
    db = tmp_path / "app.db"
    init_db(db)
    _seed(db, 1)
    proc = subprocess.run(
        [sys.executable, str(_CLI()), "--db", str(db), "unclassified", "--json"],
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-500:]
    proc.stdout.decode("ascii")  # raises if any non-ASCII byte leaked out
    data = json.loads(proc.stdout.decode("utf-8"))
    assert data["items"][0]["title"] == "タイトル0"
    assert data["items"][0]["shop"] == "ショップ0"


def test_cli_json_never_polluted_by_logs(tmp_path, monkeypatch):
    """A WARNING-level log line must not end up inside the JSON payload."""
    db = tmp_path / "app.db"
    init_db(db)
    _seed(db, 1)
    env = _child_env()
    proc = subprocess.run(
        [
            sys.executable,
            str(_CLI()),
            "--db",
            str(db),
            "--log-level",
            "DEBUG",
            "unclassified",
            "--json",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    assert proc.returncode == 0
    json.loads(proc.stdout)  # a stray log line would break this


# --- Bridge transport -------------------------------------------------------


def test_bridge_uses_persistent_worker(seeded_db):
    link = bridge.Bridge(str(seeded_db))
    try:
        first = bridge.get_purchases(link)
        assert first["count"] == 3
        assert link.transport == "worker"
        # Second call must not spawn a new process.
        assert bridge.get_unclassified(link, sort="name")["count"] == 3
        assert link.transport == "worker"
    finally:
        link.close()


def test_bridge_one_shot_transport(seeded_db):
    link = bridge.Bridge(str(seeded_db))
    try:
        link._worker_broken = True  # force the fallback path
        assert bridge.get_purchases(link)["count"] == 3
        assert link.transport == "one-shot"
    finally:
        link.close()


def test_bridge_and_one_shot_agree(seeded_db):
    """Both transports must produce identical payloads."""
    worker_link = bridge.Bridge(str(seeded_db))
    one_shot_link = bridge.Bridge(str(seeded_db))
    one_shot_link._worker_broken = True
    try:
        for op in (
            lambda b: bridge.get_purchases(b),
            lambda b: bridge.get_unclassified(b, sort="shop"),
            lambda b: bridge.get_downloads(b),
            lambda b: bridge.get_lists(b),
        ):
            assert op(worker_link) == op(one_shot_link)
    finally:
        worker_link.close()
        one_shot_link.close()


def test_bridge_survives_worker_death(seeded_db):
    """Killing the worker must not break the caller; it falls back."""
    link = bridge.Bridge(str(seeded_db))
    try:
        assert bridge.get_purchases(link)["count"] == 3
        worker = link._worker
        assert worker is not None and worker._proc is not None
        proc = worker._proc
        proc.kill()
        proc.wait(timeout=10)
        # Next call: the worker is dead, so the bridge must recover.
        assert bridge.get_purchases(link)["count"] == 3
    finally:
        link.close()


def test_bridge_rejects_bad_item_id(seeded_db):
    link = bridge.Bridge(str(seeded_db))
    try:
        for bad in ("a b", "../x", "a;b", "", "x" * 200, "a\x00b"):
            with pytest.raises(bridge.CliBridgeError):
                bridge.download_argv(item_id=bad)
    finally:
        link.close()


def test_bridge_list_name_validation(seeded_db):
    link = bridge.Bridge(str(seeded_db))
    try:
        for bad in ("", "   ", "x" * 200, "a\nb"):
            with pytest.raises(bridge.CliBridgeError):
                bridge.lists_create(link, bad)
    finally:
        link.close()


def test_web_app_never_imports_core():
    """Contract: the Web layer reaches core only through the CLI."""
    src = (Path(__file__).resolve().parent.parent / "web" / "app.py").read_text("utf-8")
    assert "from core" not in src and "import core" not in src
    src2 = (Path(__file__).resolve().parent.parent / "web" / "cli_bridge.py").read_text("utf-8")
    assert "from core" not in src2 and "import core" not in src2


# --- Web endpoints ----------------------------------------------------------


def test_web_endpoints_smoke(tmp_path):
    db = tmp_path / "app.db"
    init_db(db)
    _seed(db, 2)
    with TestClient(create_app(str(db), library_root=str(tmp_path / "lib"))) as client:
        assert client.get("/purchases").status_code == 200
        assert client.get("/unclassified?sort=name").status_code == 200
        assert client.get("/downloads").status_code == 200
        assert client.get("/lists").status_code == 200
        assert client.get("/health").json()["ok"] is True
        assert client.post("/lists", json={"action": "create", "name": "fav"}).status_code == 200
        assert (
            client.post(
                "/lists", json={"action": "add", "list": "fav", "item_id": "id0"}
            ).status_code
            == 200
        )
        u = client.get("/unclassified?sort=newest").json()
        assert u["count"] == 1 and u["items"][0]["item_id"] == "id1"


def test_web_index_renders(tmp_path):
    db = tmp_path / "app.db"
    init_db(db)
    _seed(db, 1)
    with TestClient(create_app(str(db), library_root=str(tmp_path / "lib"))) as client:
        r = client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert "charset=utf-8" in r.headers["content-type"]
        assert "タイトル0" in r.text


def test_web_escapes_malicious_title(tmp_path):
    db = tmp_path / "app.db"
    init_db(db)
    conn = get_connection(db)
    evil = "<script>alert(1)</script><img src=x onerror=alert(2)>"
    conn.execute("INSERT INTO items(item_id,title,shop) VALUES('e',?,?)", (evil, evil))
    conn.commit()
    conn.close()
    with TestClient(create_app(str(db), library_root=str(tmp_path / "lib"))) as client:
        r = client.get("/")
        assert r.status_code == 200
        # Server-rendered HTML must escape the payload: the raw tags must be
        # absent and the escaped text must be present.
        assert "<script>alert(1)</script>" not in r.text
        assert "<img src=x" not in r.text
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in r.text
        assert "&lt;img src=x onerror=alert(2)&gt;" in r.text
        # No unescaped attribute context anywhere in the document.
        assert 'onerror="alert' not in r.text and "onerror='alert" not in r.text
        # The client-side renderer must escape as well.
        assert "const esc" in r.text
        # The JSON API returns the title as *data*; the JSON media type is not
        # an HTML context, so it must stay byte-exact. The escaping duty is the
        # renderer's, which the assertion above covers.
        payload = client.get("/purchases").json()
        assert payload["items"][0]["title"] == evil


def test_web_rejects_cross_origin_post(tmp_path):
    """A page on another origin must not be able to trigger a write."""
    db = tmp_path / "app.db"
    init_db(db)
    _seed(db, 1)
    with TestClient(create_app(str(db), library_root=str(tmp_path / "lib"))) as client:
        evil = {"headers": {"Origin": "http://evil.example", "Host": "testserver"}}
        r = client.post("/lists", json={"action": "create", "name": "pwned"}, **evil)
        assert r.status_code == 403
        assert r.json()["code"] == "BAD_ORIGIN"
        # Same-origin must still work.
        good = {"headers": {"Origin": "http://testserver", "Host": "testserver"}}
        assert (
            client.post("/lists", json={"action": "create", "name": "ok"}, **good).status_code
            == 200
        )
        # No Origin header (local CLI tool) is allowed.
        assert client.post("/lists", json={"action": "create", "name": "cli"}).status_code == 200


def test_web_rejects_rebinding_host(tmp_path):
    """DNS rebinding: a Host that is not loopback must be refused."""
    db = tmp_path / "app.db"
    init_db(db)
    with TestClient(create_app(str(db), library_root=str(tmp_path / "lib"))) as client:
        r = client.get("/health", headers={"Host": "attacker.example"})
        assert r.status_code == 400
        assert client.get("/health", headers={"Host": "127.0.0.1:8000"}).status_code == 200


def test_web_negative_inputs(tmp_path):
    db = tmp_path / "app.db"
    init_db(db)
    _seed(db, 1)
    with TestClient(create_app(str(db), library_root=str(tmp_path / "lib"))) as client:
        assert client.post("/download", json={}).status_code in (400, 422)
        assert client.post("/download", json={"item_id": "id0", "all": True}).status_code == 400
        assert client.post("/download", json={"concurrent": 99}).status_code == 422
        assert client.post("/lists", json={"action": "add"}).status_code == 400
        assert client.post("/lists", json={"action": "bogus"}).status_code == 422
        assert (
            client.post(
                "/lists", json={"action": "add", "list": "a", "item_id": "../etc"}
            ).status_code
            == 400
        )
        assert client.get("/unclassified?sort=DROP%20TABLE").status_code == 200
        assert client.get("/purchases?limit=99999").status_code == 422
        assert client.get("/purchases?limit=-1").status_code == 422


def test_web_auth_status_unauthenticated(tmp_path, monkeypatch):
    def isolated_auth(link):
        return link.run(
            ["auth", "status", "--cookie-path", str(tmp_path / "missing-cookies.json"), "--json"]
        ).data

    monkeypatch.setattr(bridge, "get_auth_status", isolated_auth)
    db = tmp_path / "app.db"
    init_db(db)
    with TestClient(create_app(str(db), library_root=str(tmp_path / "lib"))) as client:
        r = client.get("/auth/status")
        assert r.status_code == 401
        assert r.json()["code"] == "BOOTH_AUTH_REQUIRED"
        assert "auth login" in r.json()["hint"]


def test_web_index_survives_upstream_failure(tmp_path):
    """The page must still render when the CLI reports an error."""
    db = tmp_path / "app.db"
    init_db(db)
    with TestClient(create_app(str(db), library_root=str(tmp_path / "lib"))) as client:
        r = client.get("/")
        assert r.status_code == 200
        assert "Cookie" in r.text  # auth line shows the problem


def test_web_index_shows_first_steps_and_library_path(tmp_path):
    db = tmp_path / "app.db"
    init_db(db)
    library = tmp_path / "lib"
    with TestClient(create_app(str(db), library_root=str(library))) as client:
        text = client.get("/").text
    assert "empty-steps" in text
    assert "BOOTHと同期" in text
    assert "購入ファイルの保存先" in text
    assert str(library) in text


def test_layout_changed_payload_carries_user_hint():
    from web.app import _err_payload

    code, body = _err_payload(bridge.CliLayoutChangedError("markup changed"))
    assert code == 502
    assert body["code"] == "BOOTH_LAYOUT_CHANGED"
    assert "Update" in body["hint"]


# --- Launchers --------------------------------------------------------------


def test_single_bat_launcher_is_valid():
    base = Path(__file__).resolve().parent.parent
    path = base / "start.bat"
    assert path.exists(), "start.bat missing"
    text = path.read_text(encoding="utf-8", errors="replace")
    for marker in ("bootstrap.ps1", "-Mode auto", "%*"):
        assert marker in text, f"start.bat missing marker: {marker}"
    # cmd.exe misparses LF-only batch files.
    assert "\r\n" in path.read_bytes().decode("utf-8", "replace"), (
        "start.bat must use CRLF line endings"
    )
