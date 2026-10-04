"""CLI contract, exit codes, RPC protocol and end-to-end smoke tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

import cli as cli_mod
from core.db import get_connection, init_db

BASE = Path(__file__).resolve().parent.parent
CLI = BASE / "cli.py"


def _run(db: Path, *args: str, env_extra: dict | None = None):
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, str(CLI), "--db", str(db), *args],
        capture_output=True,
        text=True,
        timeout=120,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )


def _seed(db: Path, n: int = 3) -> None:
    conn = get_connection(db)
    for i in range(n):
        conn.execute(
            "INSERT INTO items(item_id,title,shop) VALUES(?,?,?)",
            (f"id{i}", f"タイトル{i}", f"ショップ{i}"),
        )
        conn.execute(
            "INSERT INTO purchases(item_id,purchase_date,price) VALUES(?,?,?)",
            (f"id{i}", f"2024-01-0{i + 1}", f"¥{100 + i}"),
        )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Basics
# ---------------------------------------------------------------------------


def test_version(capsys):
    from core.version import __version__

    assert cli_mod.main(["--version"]) == 0
    assert __version__ in capsys.readouterr().out


def test_no_args_prints_help(capsys):
    assert cli_mod.main([]) == 2
    captured = capsys.readouterr()
    assert "usage" in captured.out.lower()
    # The pointer to the supported entry point goes to stderr, keeping stdout
    # free for machines that pipe the help output.
    assert "start.bat" in captured.err


def test_init_db_creates_and_is_idempotent(tmp_path):
    db = tmp_path / "app.db"
    assert cli_mod.main(["--db", str(db), "init-db"]) == 0
    assert cli_mod.main(["--db", str(db), "init-db"]) == 0
    assert db.exists()


def test_db_flag_accepted_in_both_positions(tmp_path):
    """--db before and after the subcommand must both work."""
    a = tmp_path / "a.db"
    b = tmp_path / "b.db"
    assert cli_mod.main(["--db", str(a), "init-db"]) == 0
    assert cli_mod.main(["init-db", "--db", str(b)]) == 0
    assert a.exists() and b.exists()


def test_read_commands_on_empty_db(tmp_path, capsys):
    db = tmp_path / "app.db"
    init_db(db)
    for argv in (["purchases", "list"], ["unclassified"], ["downloads", "list"], ["lists", "list"]):
        assert cli_mod.main(["--db", str(db), *argv]) == 0
    assert "(0件)" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Exit-code contract
# ---------------------------------------------------------------------------


def test_usage_errors_exit_2(tmp_path):
    db = init_db(tmp_path / "app.db")
    # Mutually exclusive / missing required selector.
    with pytest.raises(SystemExit) as e:
        cli_mod.main(["--db", str(db), "download", "--item-id", "a", "--all"])
    assert e.value.code == 2
    with pytest.raises(SystemExit) as e:
        cli_mod.main(["--db", str(db), "download"])
    assert e.value.code == 2
    # Semantic validation.
    assert cli_mod.main(["--db", str(db), "download", "--item-id", "x", "--concurrent", "6"]) == 2
    assert cli_mod.main(["--db", str(db), "lists", "create", "--name", ""]) == 2
    # Unknown subcommand / bad choice.
    with pytest.raises(SystemExit) as e:
        cli_mod.main(["--db", str(db), "nosuchcommand"])
    assert e.value.code == 2


def test_unknown_command_prints_japanese_guidance(tmp_path, capsys):
    db = init_db(tmp_path / "app.db")
    with pytest.raises(SystemExit) as e:
        cli_mod.main(["--db", str(db), "nosuchcommand"])
    assert e.value.code == 2
    err = capsys.readouterr().err
    assert "使い方" in err
    assert "start.bat" in err


def test_missing_auth_exits_1(tmp_path):
    db = init_db(tmp_path / "app.db")
    code = cli_mod.main(
        [
            "--db",
            str(db),
            "purchases",
            "list",
            "--update-db",
            "--cookie-path",
            str(tmp_path / "none.json"),
        ]
    )
    assert code == 1


def test_download_unknown_item_is_not_a_crash(tmp_path):
    db = init_db(tmp_path / "app.db")
    ck = tmp_path / "ck.json"
    ck.write_text(json.dumps([{"name": "a", "value": "v"}]), encoding="utf-8")
    code = cli_mod.main(
        ["--db", str(db), "download", "--item-id", "ghost", "--cookie-path", str(ck)]
    )
    assert code == 1


# ---------------------------------------------------------------------------
# JSON purity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        ("unclassified", "--json"),
        ("purchases", "list", "--json"),
        ("downloads", "list", "--json"),
        ("lists", "list", "--json"),
        ("doctor", "--json"),
    ],
)
def test_json_output_is_pure_and_ascii(tmp_path, argv):
    db = init_db(tmp_path / "app.db")
    _seed(db, 2)
    proc = _run(db, *argv)
    assert proc.returncode == 0, proc.stderr[-500:]
    proc.stdout.encode("ascii")  # must not raise
    json.loads(proc.stdout)


def test_json_survives_cp932_style_pipe(tmp_path):
    """A Japanese console encodes a pipe as cp932; --json must still decode.

    Run without ``text=`` so the raw bytes are inspected, which is exactly what
    a UTF-8-decoding consumer on the other end of the pipe sees.
    """
    db = init_db(tmp_path / "app.db")
    _seed(db, 1)
    env = dict(os.environ, PYTHONIOENCODING="cp932", PYTHONUTF8="")
    env.pop("PYTHONIOENCODING", None)
    env["PYTHONIOENCODING"] = "cp932"
    env.pop("PYTHONUTF8", None)
    proc = subprocess.run(
        [sys.executable, str(CLI), "--db", str(db), "unclassified", "--json"],
        capture_output=True,
        timeout=120,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-500:]
    proc.stdout.decode("ascii")  # no raw UTF-8 leaked into a cp932 pipe
    data = json.loads(proc.stdout.decode("utf-8"))
    assert data["items"][0]["title"] == "タイトル0"


def test_logs_do_not_pollute_json_at_debug(tmp_path):
    """Whatever the log level, stdout must contain JSON and nothing else."""
    db = init_db(tmp_path / "app.db")
    _seed(db, 1)
    for level in ("DEBUG", "INFO", "WARNING", "ERROR"):
        proc = _run(db, "--log-level", level, "unclassified", "--json")
        assert proc.returncode == 0, proc.stderr[-300:]
        json.loads(proc.stdout)  # a stray log line would break this


# ---------------------------------------------------------------------------
# lists round-trip
# ---------------------------------------------------------------------------


def test_lists_lifecycle(tmp_path, capsys):
    db = init_db(tmp_path / "app.db")
    _seed(db, 3)
    assert cli_mod.main(["--db", str(db), "lists", "create", "--name", "fav"]) == 0
    assert cli_mod.main(["--db", str(db), "lists", "add", "--list", "fav", "--item-id", "id0"]) == 0
    conn = get_connection(db)
    from core.lists import get_unclassified

    assert [r["item_id"] for r in get_unclassified(conn)] == ["id2", "id1"]
    conn.close()
    # Adding twice is idempotent.
    assert cli_mod.main(["--db", str(db), "lists", "add", "--list", "fav", "--item-id", "id0"]) == 0
    conn = get_connection(db)
    assert len(get_unclassified(conn)) == 2
    conn.close()
    assert (
        cli_mod.main(["--db", str(db), "lists", "remove", "--list", "fav", "--item-id", "id0"]) == 0
    )
    conn = get_connection(db)
    assert len(get_unclassified(conn)) == 3
    conn.close()
    assert cli_mod.main(["--db", str(db), "lists", "delete", "--name", "fav"]) == 0
    conn = get_connection(db)
    from core.lists import list_lists

    assert list_lists(conn) == []
    conn.close()


def test_csv_export_via_cli(tmp_path):
    db = init_db(tmp_path / "app.db")
    _seed(db, 2)
    out = tmp_path / "out.csv"
    assert cli_mod.main(["--db", str(db), "purchases", "list", "--csv", str(out)]) == 0
    assert out.exists() and "id0" in out.read_text(encoding="utf-8-sig")


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------


def test_doctor_reports_health(tmp_path):
    db = init_db(tmp_path / "app.db")
    proc = _run(
        db,
        "doctor",
        "--library",
        str(tmp_path / "lib"),
        "--cookie-path",
        str(tmp_path / "missing-cookies.json"),
        "--json",
    )
    payload = json.loads(proc.stdout)
    names = {c["name"]: c for c in payload["checks"]}
    assert names["db:tables"]["ok"] is True
    assert names["db:integrity"]["ok"] is True
    assert names["library"]["ok"] is True
    # Missing cookies is a warning, not a failure.
    assert names["cookies"]["ok"] is False
    assert names["cookies"]["fatal"] is False
    assert payload["ok"] is True


def test_doctor_flags_missing_database(tmp_path):
    proc = _run(tmp_path / "missing.db", "doctor", "--library", str(tmp_path / "lib"), "--json")
    payload = json.loads(proc.stdout)
    names = {c["name"]: c for c in payload["checks"]}
    assert names["db:exists"]["ok"] is False
    assert payload["ok"] is True  # not fatal: the user can just run init-db


# ---------------------------------------------------------------------------
# RPC protocol
# ---------------------------------------------------------------------------


def _rpc(db: Path, requests: list[dict], timeout: int = 60) -> list[dict]:
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    payload = "\n".join(json.dumps(r) for r in requests) + "\n"
    proc = subprocess.run(
        [sys.executable, str(CLI), "--db", str(db), "rpc"],
        input=payload,
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-800:]
    return [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]


def test_rpc_serves_multiple_requests(tmp_path):
    db = init_db(tmp_path / "app.db")
    _seed(db, 2)
    responses = _rpc(
        db,
        [
            {"id": 1, "args": ["unclassified", "--json"]},
            {"id": 2, "args": ["purchases", "list", "--json"]},
            {"id": 3, "args": ["downloads", "list", "--json"]},
        ],
    )
    assert [r["id"] for r in responses] == [1, 2, 3]
    assert all(r["ok"] for r in responses)
    assert responses[0]["data"]["count"] == 2
    assert responses[1]["data"]["count"] == 2
    assert responses[2]["data"]["count"] == 0
    assert all("elapsed_ms" in r for r in responses)


def test_rpc_reports_errors_without_dying(tmp_path):
    db = init_db(tmp_path / "app.db")
    _seed(db, 1)
    responses = _rpc(
        db,
        [
            {
                "id": 1,
                "args": [
                    "purchases",
                    "list",
                    "--update-db",
                    "--cookie-path",
                    str(tmp_path / "none.json"),
                ],
            },
            {"id": 2, "args": ["unclassified", "--json"]},  # must still work
        ],
    )
    assert responses[0]["ok"] is False
    assert responses[0]["returncode"] == 1
    assert "ログイン" in responses[0]["error"]
    assert responses[1]["ok"] is True


def test_rpc_rejects_malformed_requests(tmp_path):
    db = init_db(tmp_path / "app.db")
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    payload = (
        'not json\n[1,2,3]\n{"id": 9}\n{"id": 10, "args": "nope"}\n'
        '{"id": 11, "args": ["unclassified", "--json"]}\n'
    )
    proc = subprocess.run(
        [sys.executable, str(CLI), "--db", str(db), "rpc"],
        input=payload,
        capture_output=True,
        text=True,
        timeout=60,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    assert proc.returncode == 0
    responses = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    assert responses[0]["returncode"] == 2
    assert responses[1]["returncode"] == 2
    assert responses[2]["returncode"] == 2
    assert responses[3]["returncode"] == 2
    # The worker survived every bad request and still served the last one.
    assert responses[4]["ok"] is True


def test_rpc_ignores_client_db_flag(tmp_path):
    """A request must not be able to redirect the worker at another database."""
    db = init_db(tmp_path / "app.db")
    _seed(db, 2)
    other = tmp_path / "other.db"
    init_db(other)
    responses = _rpc(
        db,
        [
            {"id": 1, "args": ["unclassified", "--json", "--db", str(other)]},
        ],
    )
    assert responses[0]["ok"] is True
    assert responses[0]["data"]["count"] == 2, "worker DB must win"


# ---------------------------------------------------------------------------
# End-to-end smoke
# ---------------------------------------------------------------------------


def test_full_local_roundtrip_via_subprocess(tmp_path):
    db = init_db(tmp_path / "app.db")
    _seed(db, 2)
    ck = tmp_path / "ck.json"
    ck.write_text(json.dumps([{"name": "a", "value": "v"}]), encoding="utf-8")

    zip_path = tmp_path / "payload.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr("inner.txt", "hello")

    # Drive a download with the network layer stubbed out.
    import core.download as dl

    real_resolve = dl.resolve_download_links
    real_download = dl.download_file
    try:
        dl.resolve_download_links = lambda *a, **k: [
            {"url": "https://example.invalid/payload.zip", "label": "payload.zip"}
        ]

        def fake_download(url, dest, cookies, resume=True, timeout=60, **kw):
            dest = Path(dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zip_path.read_bytes())
            return dest

        dl.download_file = fake_download
        assert (
            cli_mod.main(
                [
                    "--db",
                    str(db),
                    "download",
                    "--item-id",
                    "id0",
                    "--cookie-path",
                    str(ck),
                    "--output-dir",
                    str(tmp_path / "lib"),
                    "--json",
                ]
            )
            == 0
        )
    finally:
        dl.resolve_download_links = real_resolve
        dl.download_file = real_download

    out = tmp_path / "lib" / "id0_タイトル0"
    assert (out / "downloads" / "payload.zip").exists()
    assert (out / "extracted" / "inner.txt").read_text() == "hello"
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "done"
    assert meta["files"][0]["sha256"]

    conn = get_connection(db)
    try:
        row = conn.execute("SELECT status,sha256 FROM downloads WHERE item_id='id0'").fetchone()
        assert row["status"] == "done"
        assert len(row["sha256"]) == 64
    finally:
        conn.close()

    proc = _run(db, "downloads", "list", "--json")
    assert json.loads(proc.stdout)["count"] == 1


def test_repeated_execution_is_stable(tmp_path):
    """Running the same commands repeatedly must not change the outcome."""
    db = init_db(tmp_path / "app.db")
    _seed(db, 2)
    results = set()
    for _ in range(5):
        proc = _run(db, "unclassified", "--json")
        results.add(proc.stdout)
    assert len(results) == 1
    for _ in range(3):
        assert cli_mod.main(["--db", str(db), "lists", "create", "--name", "x"]) == 0
    conn = get_connection(db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM lists").fetchone()[0] == 1
    finally:
        conn.close()


def test_unclassified_sorts(tmp_path, capsys):
    db = init_db(tmp_path / "app.db")
    conn = get_connection(db)
    conn.execute("INSERT INTO items(item_id,title,shop) VALUES('a','Zebra','S2')")
    conn.execute("INSERT INTO items(item_id,title,shop) VALUES('b','apple','S1')")
    conn.commit()
    conn.close()
    from core.lists import get_unclassified

    conn = get_connection(db)
    try:
        assert [r["item_id"] for r in get_unclassified(conn, sort="name")] == ["b", "a"]
        assert [r["item_id"] for r in get_unclassified(conn, sort="shop")] == ["b", "a"]
        with pytest.raises(ValueError):
            get_unclassified(conn, sort="; DROP TABLE items")
    finally:
        conn.close()
