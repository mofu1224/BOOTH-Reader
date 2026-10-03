"""Stable library identities and safe representation-aware resume."""

import io
import zipfile
from pathlib import Path

import httpx
import pytest

from core import download
from core.db import get_connection
from core.errors import BoothAuthError, BoothNetworkError
from tests.test_audit_http import mock_http as _mock_http
from tests.test_regression_102 import ItemServer, _jar, _seeded_item

mock_http = _mock_http


def test_a13_title_change_keeps_original_library_directory(tmp_path):
    with ItemServer({"/downloads/a.bin": b"payload"}) as server:
        db = _seeded_item(tmp_path, server.item_url)
        jar = _jar(tmp_path)
        first = download.download_item("12345", db, tmp_path / "lib", cookie_path=jar)
        conn = get_connection(db)
        conn.execute("UPDATE items SET title='New Title'")
        conn.commit()
        conn.close()
        second = download.download_item("12345", db, tmp_path / "lib", cookie_path=jar)
        assert second["dir"] == first["dir"]
        assert len(server.transfers) == 1


def test_a13_extract_after_no_extract_without_redownload(tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("inner.txt", "payload")
    with ItemServer({"/downloads/a.zip": buffer.getvalue()}) as server:
        db = _seeded_item(tmp_path, server.item_url)
        jar = _jar(tmp_path)
        first = download.download_item(
            "12345", db, tmp_path / "lib", cookie_path=jar, extract=False
        )
        second = download.download_item(
            "12345", db, tmp_path / "lib", cookie_path=jar, extract=True
        )
        assert second["files"][0]["extracted"] == ["inner.txt"]
        assert (Path(first["dir"]) / "extracted" / "inner.txt").read_text() == "payload"
        assert len(server.transfers) == 1


@pytest.mark.parametrize("etag", [None, '"old-version"'])
def test_a13_changed_origin_after_interruption_never_splices_versions(mock_http, tmp_path, etag):
    seen = []
    old = b"a" * download.CHUNK_SIZE + b"old tail"
    new = b"b" * download.CHUNK_SIZE + b"new tail"

    class Interrupted(httpx.SyncByteStream):
        def __iter__(self):
            yield old[: download.CHUNK_SIZE]
            raise httpx.ReadError("injected disconnect")

    def handler(request):
        seen.append(dict(request.headers))
        if len(seen) == 1:
            headers = {"Content-Length": str(len(old))}
            if etag:
                headers["ETag"] = etag
            return httpx.Response(200, headers=headers, stream=Interrupted())
        offset = int(request.headers.get("Range", "bytes=0-").split("=")[1].split("-")[0])
        headers = {"ETag": '"new-version"', "Content-Length": str(len(new) - offset)}
        if offset:
            headers["Content-Range"] = f"bytes {offset}-{len(new) - 1}/{len(new)}"
        return httpx.Response(206 if offset else 200, content=new[offset:], headers=headers)

    mock_http(handler)
    dest = tmp_path / "file.bin"
    url = "https://booth.pm/downloads/f.bin"
    with pytest.raises(BoothNetworkError):
        download.download_file(url, dest, [], max_retries=1)
    download.download_file(url, dest, [], max_retries=3)
    assert dest.read_bytes() == new
    if etag:
        assert seen[1].get("if-range") == etag
    else:
        assert "range" not in seen[1]


def test_a13_login_html_is_never_published_as_download(mock_http, tmp_path):
    def handler(request):
        if request.url.host == "booth.pm":
            return httpx.Response(302, headers={"Location": "https://accounts.pixiv.net/login"})
        return httpx.Response(200, text="<html>login form</html>")

    mock_http(handler)
    dest = tmp_path / "model.zip"
    with pytest.raises(BoothAuthError):
        download.download_file("https://booth.pm/downloads/1", dest, [])
    assert not dest.exists()


@pytest.mark.parametrize("error_number", [13, 28])
def test_write_permission_or_disk_full_preserves_published_file(
    mock_http, tmp_path, monkeypatch, error_number
):
    mock_http(lambda request: httpx.Response(200, content=b"new bytes"))
    dest = tmp_path / "original.bin"
    dest.write_bytes(b"original bytes")
    original_open = Path.open

    def denied(path, *args, **kwargs):
        if path.name.endswith(".part"):
            raise OSError(error_number, "injected filesystem failure")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", denied)
    with pytest.raises(BoothNetworkError, match="空き容量"):
        download.download_file("https://booth.pm/downloads/1", dest, [], resume=False)
    assert dest.read_bytes() == b"original bytes"
