"""Download, extraction and resume tests.

The resume tests are the important ones: a partial file left by an interrupted
run, combined with a flaky server, used to produce a silently corrupted file
that was then recorded as a successful download.
"""

from __future__ import annotations

import hashlib
import http.server
import json
import socketserver
import threading
import zipfile
from pathlib import Path

import pytest

from core.download import (
    ExtractLimits,
    check_concurrent,
    cleanup_partials,
    item_dir,
    item_page_url,
    safe_extract_zip,
    safe_title,
    sanitize_component,
    sha256_of,
    validate_item_id,
)
from core.errors import BoothAuthError, BoothLimitExceededError, BoothNetworkError

# ---------------------------------------------------------------------------
# Local HTTP server used to exercise the real transfer path
# ---------------------------------------------------------------------------


class FlakyServer:
    """Serves fixed bytes; optionally drops the connection after N bytes.

    ``support_range`` toggles between a well-behaved origin and one that
    ignores the Range header, which are the two cases the resume logic must
    distinguish.
    """

    def __init__(
        self,
        data: bytes,
        support_range: bool = True,
        fail_times: int = 0,
        status: int = 200,
        fail_status_times: int = 0,
    ) -> None:
        self.data = data
        self.support_range = support_range
        self.fail_times = fail_times
        self.status = status
        self.fail_status_times = fail_status_times
        self.requests: list[str | None] = []
        self._lock = threading.Lock()
        handler = self._make_handler()
        self.server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}/f.bin"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _make_handler(self):
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def do_GET(self):
                with outer._lock:
                    outer.requests.append(self.headers.get("Range"))
                    attempt = len(outer.requests)
                if attempt <= outer.fail_status_times:
                    self.send_response(503)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                if outer.status != 200:
                    self.send_response(outer.status)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                rng = self.headers.get("Range") if outer.support_range else None
                if rng and outer.support_range:
                    start = int(rng.split("=")[1].split("-")[0])
                    body = outer.data[start:]
                    self.send_response(206)
                    self.send_header(
                        "Content-Range", f"bytes {start}-{len(outer.data) - 1}/{len(outer.data)}"
                    )
                else:
                    body = outer.data
                    self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("ETag", '"' + hashlib.sha256(outer.data).hexdigest() + '"')
                self.send_header("Accept-Ranges", "bytes" if outer.support_range else "none")
                self.end_headers()
                if attempt <= outer.fail_times:
                    # Send a partial body then hang up, like a dropped connection.
                    self.wfile.write(body[: max(1, len(body) // 2)])
                    self.wfile.flush()
                    self.close_connection = True
                else:
                    self.wfile.write(body)

        return Handler


@pytest.fixture
def payload() -> bytes:
    # Non-repeating so a duplicated or missing range is always detectable.
    return bytes((i * 7 + 11) % 251 for i in range(300_000))


def _cookie() -> list[dict]:
    return [{"name": "session", "value": "v", "domain": "127.0.0.1"}]


def seed_resume_state(part: Path, url: str, payload: bytes) -> None:
    """Model a prefix persisted from a validated, previously interrupted GET."""
    part.with_name(part.name + ".json").write_text(
        json.dumps(
            {
                "url": url,
                "header": "etag",
                "validator": '"' + hashlib.sha256(payload).hexdigest() + '"',
            }
        ),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Resume correctness (regression tests)
# ---------------------------------------------------------------------------


def test_resume_after_dropped_connection_yields_identical_bytes(tmp_path, payload):
    """The original corruption bug: retry re-requested a stale byte range.

    A pre-existing partial file plus two dropped connections used to produce a
    file larger than the source, with duplicated bytes in the middle, that the
    code then reported as a success.
    """
    from core.download import download_file

    dest = tmp_path / "f.bin"
    dest.write_bytes(payload[:150_000])  # partial left by an earlier run

    with FlakyServer(payload, support_range=True, fail_times=2) as server:
        download_file(server.url, dest, _cookie(), resume=True, timeout=30)

    assert dest.stat().st_size == len(payload)
    assert hashlib.sha256(dest.read_bytes()).hexdigest() == hashlib.sha256(payload).hexdigest()


def test_no_partial_file_left_after_failure(tmp_path, payload):
    """A failed transfer must never leave a truncated file in the library."""
    from core.download import download_file

    dest = tmp_path / "f.bin"
    with FlakyServer(payload, support_range=True, fail_times=99) as server:
        with pytest.raises(BoothNetworkError):
            download_file(server.url, dest, _cookie(), resume=True, timeout=30)
    assert not dest.exists(), "a truncated file was published as if complete"
    assert list(tmp_path.glob("*.part")), "the .part resume file should remain"


def test_resume_continues_from_part_file(tmp_path, payload):
    from core.download import download_file

    dest = tmp_path / "f.bin"
    part = tmp_path / "f.bin.part"
    part.write_bytes(payload[:100_000])
    with FlakyServer(payload, support_range=True) as server:
        seed_resume_state(part, server.url, payload)
        download_file(server.url, dest, _cookie(), resume=True, timeout=30)
    assert server.requests == ["bytes=100000-"]
    assert dest.read_bytes() == payload
    assert not part.exists()


def test_server_ignoring_range_restarts_cleanly(tmp_path, payload):
    """If the origin ignores Range, the body starts at 0 and must not be appended."""
    from core.download import download_file

    dest = tmp_path / "f.bin"
    dest.write_bytes(payload[:120_000])  # stale partial larger than needed
    with FlakyServer(payload, support_range=False) as server:
        download_file(server.url, dest, _cookie(), resume=True, timeout=30)
    assert dest.read_bytes() == payload
    assert dest.stat().st_size == len(payload)


def test_incomplete_body_is_detected_even_when_server_hangs_up(tmp_path, payload):
    """Content-Length promises more than arrives, with no exception raised."""
    from core.download import download_file

    dest = tmp_path / "f.bin"
    with FlakyServer(payload, support_range=True, fail_times=1) as server:
        download_file(server.url, dest, _cookie(), resume=True, timeout=30, max_retries=2)
    assert dest.read_bytes() == payload


def test_auth_error_is_not_retried(tmp_path):
    """A 403 must fail immediately as an auth error, without retrying."""
    from core.download import download_file

    dest = tmp_path / "f.bin"
    with FlakyServer(b"x", status=403) as server, pytest.raises(BoothAuthError):
        download_file(server.url, dest, _cookie(), timeout=10, max_retries=3)
    # No retry was attempted, so only the first request was made.
    assert len(server.requests) == 1
    assert not dest.exists()


def test_server_error_is_retried_then_succeeds(tmp_path, payload):
    """A transient 5xx must be retried, not surfaced as a hard failure."""
    from core.download import download_file

    dest = tmp_path / "f.bin"
    with FlakyServer(payload, fail_status_times=2) as server:
        download_file(server.url, dest, _cookie(), timeout=30)
    assert dest.read_bytes() == payload
    assert len(server.requests) == 3


def test_missing_local_partial_size_handled(tmp_path, payload):
    """A .part file that does not exist yet must start from zero."""
    from core.download import download_file

    dest = tmp_path / "f.bin"
    with FlakyServer(payload) as server:
        download_file(server.url, dest, _cookie(), resume=True, timeout=30)
    assert dest.read_bytes() == payload
    assert server.requests == [None]


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def test_zip_slip_variants_rejected(tmp_path):
    dest = tmp_path / "out"
    z = tmp_path / "a.zip"
    with zipfile.ZipFile(z, "w") as zz:
        zz.writestr("ok.txt", "hi")
        zz.writestr("../evil.txt", "x")
        zz.writestr("/abs.txt", "x")
        zz.writestr("C:/win.txt", "x")
        zz.writestr("sub/../../escape.txt", "x")
        zz.writestr("a\\..\\..\\back.txt", "x")
        zz.writestr("\\\\server\\share\\s.txt", "x")
        zz.writestr("CON", "x")
        zz.writestr("dir./f.txt", "x")
        zz.writestr("", "x")
    files = safe_extract_zip(z, dest)
    assert files == ["ok.txt"]
    assert (dest / "ok.txt").read_text() == "hi"
    for escaped in ("evil.txt", "abs.txt", "win.txt", "escape.txt", "back.txt"):
        assert not (tmp_path / escaped).exists()
        assert not (dest.parent / escaped).exists()
    assert not (dest / "CON").exists()


def test_zip_bomb_rejected_without_writing_anything(tmp_path):
    """A highly compressible archive must be refused before extraction."""
    dest = tmp_path / "out"
    z = tmp_path / "bomb.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zz:
        zz.writestr("bomb.bin", b"\0" * (60 * 1024 * 1024))
    assert z.stat().st_size < 5 * 1024 * 1024  # tiny on disk
    with pytest.raises(BoothLimitExceededError):
        safe_extract_zip(z, dest)
    written = [p for p in dest.rglob("*") if p.is_file()] if dest.exists() else []
    assert written == []


def test_zip_total_size_cap(tmp_path):
    z = tmp_path / "many.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zz:
        for i in range(5):
            zz.writestr(f"f{i}.bin", b"a" * 200_000)
    with pytest.raises(BoothLimitExceededError):
        safe_extract_zip(z, tmp_path / "out", ExtractLimits(max_total_bytes=100_000))


def test_zip_entry_count_cap(tmp_path):
    z = tmp_path / "many2.zip"
    with zipfile.ZipFile(z, "w") as zz:
        for i in range(50):
            zz.writestr(f"f{i}.txt", "x")
    with pytest.raises(BoothLimitExceededError):
        safe_extract_zip(z, tmp_path / "out", ExtractLimits(max_entries=10))
    assert safe_extract_zip(z, tmp_path / "out2", ExtractLimits(max_entries=100)) != []


def test_nested_directories_extract(tmp_path):
    dest = tmp_path / "out"
    z = tmp_path / "n.zip"
    with zipfile.ZipFile(z, "w") as zz:
        zz.writestr("a/b/c/deep.txt", "deep")
    assert safe_extract_zip(z, dest) == ["a/b/c/deep.txt"]
    assert (dest / "a" / "b" / "c" / "deep.txt").read_text() == "deep"


def test_corrupt_zip_raises_badzipfile(tmp_path):
    z = tmp_path / "bad.zip"
    z.write_bytes(b"PK\x03\x04 definitely not a zip")
    with pytest.raises(zipfile.BadZipFile):
        safe_extract_zip(z, tmp_path / "out")


def test_cleanup_partials(tmp_path):
    (tmp_path / "a.bin.part").write_bytes(b"x")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.bin.part").write_bytes(b"y")
    (tmp_path / "keep.bin").write_bytes(b"z")
    assert cleanup_partials(tmp_path) == 2
    assert (tmp_path / "keep.bin").exists()
    assert cleanup_partials(tmp_path / "nonexistent") == 0


# ---------------------------------------------------------------------------
# Name and path handling
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "../../../Windows/System32/drivers/etc",
        "..",
        ".",
        "",
        "a/b",
        "a\\b",
        "C:evil",
        "x" * 200,
        "a\x00b",
        "a:b",
    ],
)
def test_item_id_rejects_traversal(bad):
    with pytest.raises(ValueError):
        validate_item_id(bad)
    with pytest.raises(ValueError):
        item_dir(Path("C:/lib"), bad, "title")


def test_item_dir_stays_under_root(tmp_path):
    d = item_dir(tmp_path, "12345", "タイトル")
    assert d.parent == tmp_path.resolve()
    assert d.name == "12345_タイトル"


@pytest.mark.parametrize(
    "name,expected",
    [
        ("CON", "_CON"),
        ("PRN.txt", "_PRN.txt"),
        ("AUX", "_AUX"),
        ("COM1", "_COM1"),
        ("LPT9", "_LPT9"),
        ("nul", "_nul"),
        ("a:b/c", "a_b_c"),
        ("trailing.", "trailing"),
        ("  x  ", "x"),
        ("", "untitled"),
        ("   ", "untitled"),
        (".", "untitled"),
        # Tabs are control characters, so they are replaced like any other.
        ("tab\there", "tab_here"),
        ("null\x00byte", "null_byte"),
        ("a\nb", "a_b"),
        ("bell\x07", "bell_"),
    ],
)
def test_sanitize_component(name, expected):
    assert sanitize_component(name) == expected


def test_sanitize_component_preserves_japanese_and_spaces():
    assert sanitize_component("東方Project 博士") == "東方Project 博士"
    assert safe_title("a:b/c") == "a_b_c"
    assert len(sanitize_component("x" * 500)) <= 120


def test_sanitize_component_does_not_collide_on_windows_names():
    a = sanitize_component("report")
    b = sanitize_component("report.")
    assert a == b == "report"


def test_item_page_url():
    assert item_page_url("https://booth.pm/ja/items/1") == "https://booth.pm/ja/items/1"
    assert item_page_url("order_abc") == "https://accounts.booth.pm/orders/abc"
    assert item_page_url("12345") == "https://booth.pm/ja/items/12345"
    for bad in ("", "  ", "http", "../../etc"):
        with pytest.raises(ValueError):
            item_page_url(bad)


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------


def test_check_concurrent_bounds():
    assert check_concurrent(1) == 1
    assert check_concurrent(3) == 3
    assert check_concurrent(5) == 5
    for bad in (0, -1, 6, 99, "x", None):
        with pytest.raises(ValueError):
            check_concurrent(bad)  # type: ignore[arg-type]


def test_sha256_of(tmp_path):
    p = tmp_path / "a.bin"
    p.write_bytes(b"hello")
    assert sha256_of(p) == hashlib.sha256(b"hello").hexdigest()
    assert len(sha256_of(p)) == 64


def test_error_hierarchy_and_exit_codes():
    from core.errors import BoothError, exit_code_for

    assert issubclass(BoothLimitExceededError, BoothError)
    assert issubclass(BoothAuthError, BoothError)
    assert issubclass(BoothNetworkError, BoothError)
    assert BoothLimitExceededError.CODE == "BOOTH_LIMIT_EXCEEDED"
    # Exit-code contract.
    from core.errors import BoothLayoutChangedError

    assert exit_code_for(BoothLayoutChangedError()) == 3
    assert exit_code_for(BoothAuthError()) == 1
    assert exit_code_for(BoothNetworkError("x")) == 1
    assert exit_code_for(BoothLimitExceededError("x")) == 1
    assert exit_code_for(ValueError("x")) == 2
    assert exit_code_for(RuntimeError("x")) == 1
