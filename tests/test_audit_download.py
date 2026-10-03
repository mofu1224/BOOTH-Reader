"""Item-level correctness and recovery against a local BOOTH-shaped origin."""

import json

import pytest

import cli
from core import download
from core.db import get_connection, init_db
from core.errors import BoothNetworkError
from tests.test_regression_102 import ItemServer, _jar, _seeded_item


@pytest.mark.parametrize("concurrent", [1, 3])
def test_a02_partial_item_is_batch_failure(tmp_path, concurrent):
    with ItemServer(
        {"/downloads/a.bin": b"good"},
        anchors=[
            ("/downloads/a.bin", "a.bin"),
            ("/downloads/missing.bin", "missing.bin"),
        ],
    ) as server:
        db = _seeded_item(tmp_path, server.item_url)
        if concurrent > 1:
            conn = get_connection(db)
            conn.execute(
                "INSERT INTO items(item_id,title,url) VALUES('12346','Second',?)",
                (server.item_url,),
            )
            conn.commit()
            conn.close()
        ids = ["12345"] if concurrent == 1 else ["12345", "12346"]
        result = download.download_many(
            ids, db, tmp_path / "lib", cookie_path=_jar(tmp_path), concurrent=concurrent
        )
        assert result["ok"] == []
        assert len(result["failed"]) == len(ids)
        assert all(item["files"] and item["failed"] for item in result["failed"])


def test_a02_cli_corrupt_zip_is_failure(tmp_path, capsys):
    with ItemServer({"/downloads/bad.zip": b"not a zip"}) as server:
        db = _seeded_item(tmp_path, server.item_url)
        code = cli.main(
            [
                "--db",
                str(db),
                "download",
                "--item-id",
                "12345",
                "--cookie-path",
                str(_jar(tmp_path)),
                "--output-dir",
                str(tmp_path / "lib"),
                "--json",
            ]
        )
        payload = json.loads(capsys.readouterr().out)
        assert code == 1
        assert payload["ok_count"] == 0 and payload["failed_count"] == 1
        conn = get_connection(db)
        try:
            assert conn.execute("SELECT status FROM downloads").fetchone()[0] == "failed"
        finally:
            conn.close()


def test_a02_empty_download_json_is_json(tmp_path, capsys):
    db = init_db(tmp_path / "empty.db")
    assert cli.main(["--db", str(db), "download", "--all", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok_count"] == payload["failed_count"] == 0


def test_a03_force_never_splices_old_origin_bytes(tmp_path):
    with ItemServer({"/downloads/a.bin": b"old content"}) as server:
        db = _seeded_item(tmp_path, server.item_url)
        jar = _jar(tmp_path)
        first = download.download_item("12345", db, tmp_path / "lib", cookie_path=jar)
        server.files["/downloads/a.bin"] = b"new content with a changed prefix"
        # Mimic a changed origin supporting Range: the first bytes belong to a
        # different version and must not be adopted as a partial.
        from tests.test_download import FlakyServer

        with FlakyServer(server.files["/downloads/a.bin"]) as range_server:
            server.anchors = [(range_server.url, "ダウンロード a.bin")]
            conn = get_connection(db)
            conn.execute("UPDATE downloads SET url=?", (range_server.url,))
            conn.commit()
            conn.close()
            forced = download.download_item(
                "12345", db, tmp_path / "lib", cookie_path=jar, force=True
            )
        assert forced["failed"] == []
        assert range_server.requests == [None]
        assert first["files"][0]["path"] == forced["files"][0]["path"]
        from pathlib import Path

        assert Path(forced["files"][0]["path"]).read_bytes() == server.files["/downloads/a.bin"]


def test_a03_item_failure_preserves_resume_data(tmp_path, monkeypatch):
    with ItemServer({"/downloads/a.bin": b"complete"}) as server:
        db = _seeded_item(tmp_path, server.item_url)
        jar = _jar(tmp_path)

        def interrupted(url, dest, cookies, **kwargs):
            dest.with_name(dest.name + ".part").write_bytes(b"partial")
            raise BoothNetworkError("connection lost")

        monkeypatch.setattr(download, "download_file", interrupted)
        result = download.download_item("12345", db, tmp_path / "lib", cookie_path=jar)
        assert result["failed"]
        assert [p.read_bytes() for p in (tmp_path / "lib").rglob("*.part")] == [b"partial"]


def test_a03_skip_preserves_hash_and_extraction_metadata(tmp_path):
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("inner.txt", "payload")
    with ItemServer({"/downloads/a.zip": buffer.getvalue()}) as server:
        db = _seeded_item(tmp_path, server.item_url)
        jar = _jar(tmp_path)
        first = download.download_item("12345", db, tmp_path / "lib", cookie_path=jar)
        second = download.download_item("12345", db, tmp_path / "lib", cookie_path=jar)
        assert second["files"][0]["sha256"] == first["files"][0]["sha256"]
        assert second["files"][0]["extracted"] == ["inner.txt"]


def test_a04_case_insensitive_download_names(tmp_path):
    with ItemServer({"/downloads/A.bin": b"upper", "/downloads/a.bin": b"lower"}) as server:
        db = _seeded_item(tmp_path, server.item_url)
        result = download.download_item("12345", db, tmp_path / "lib", cookie_path=_jar(tmp_path))
        assert not result["failed"]
        assert len({f["file"].casefold() for f in result["files"]}) == 2
        from pathlib import Path

        assert {Path(f["path"]).read_bytes() for f in result["files"]} == {b"upper", b"lower"}


def test_a04_zip_extension_from_label_without_url_extension():
    name, ext = download._preferred_name(
        {"url": "https://booth.pm/downloads/123", "label": "model.zip"}, 1
    )
    assert name == "model.zip" and ext == ".zip"


@pytest.mark.parametrize("name", ["report.txt:stream", "a?b", "a<b", "a|b"])
def test_a04_zip_windows_invalid_names_are_not_written(tmp_path, name):
    import zipfile

    path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(name, "unsafe")
    assert download.safe_extract_zip(path, tmp_path / "out") == []


def test_a04_corrupt_member_keeps_existing_file(tmp_path):
    import zipfile

    archive_path = tmp_path / "crc.zip"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_STORED) as archive:
        archive.writestr("keep.txt", b"unique original data")
    archive_path.write_bytes(
        archive_path.read_bytes().replace(b"unique original data", b"unique corrupted dat")
    )
    out = tmp_path / "out"
    out.mkdir()
    target = out / "keep.txt"
    target.write_bytes(b"user original")
    with pytest.raises(zipfile.BadZipFile):
        download.safe_extract_zip(archive_path, out)
    assert target.read_bytes() == b"user original"


def test_a04_zip_case_collision_is_explicit_failure(tmp_path):
    import zipfile

    path = tmp_path / "duplicate.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("A.txt", "one")
        archive.writestr("a.txt", "two")
    with pytest.raises(BoothNetworkError):
        download.safe_extract_zip(path, tmp_path / "out")
