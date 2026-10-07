"""Regression tests for the defects fixed in 1.0.2.

Each test here corresponds to a defect that was reproduced against the running
code before the fix. The reproduction conditions, not the implementation, are
what is pinned down, so a future refactor cannot quietly reintroduce them.

1. A second ``download`` re-fetched every file under a new name
   (``x.zip``, ``x_2.zip``, ``x_3.zip`` ...), so the documented "a re-run does
   not re-fetch completed files" guarantee was unreachable.
2. A server that answers ``206`` with a range start other than the one that was
   requested caused wrong bytes to be spliced into the file, which was then
   published at exactly the expected length and recorded as ``done``.
3. A database written by a newer build was refused with a raw traceback.
4. ``doctor`` could not inspect a cookie jar other than the default one, so a
   user who had logged in with ``--cookie-path`` was told to log in again.
5. ``auth login`` reported a network failure while opening the login page as a
   missing Chromium, sending the user to reinstall a browser that was fine.
"""

from __future__ import annotations

import hashlib
import http.server
import json
import socketserver
import threading
from pathlib import Path

import pytest

from core.db import get_connection, init_db
from core.download import download_file, download_item
from core.errors import BoothNetworkError
from tests.test_download import seed_resume_state

# ---------------------------------------------------------------------------
# A local BOOTH-shaped server: one item page, N download links
# ---------------------------------------------------------------------------


class ItemServer:
    """Serves an item page and its files, counting every transfer.

    ``anchors`` is an optional list of ``(href, label)`` pairs so a test can
    change the link text while keeping the URL, which is what BOOTH does when a
    seller renames a file.
    """

    def __init__(self, files: dict[str, bytes], anchors: list[tuple[str, str]] | None = None):
        self.files = files
        self.anchors = anchors
        self.transfers: list[str] = []
        self._lock = threading.Lock()
        self.server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), self._handler())
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    @property
    def item_url(self) -> str:
        return f"{self.base}/item"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def __enter__(self) -> ItemServer:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _handler(self):
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def do_GET(self):
                if self.path == "/item":
                    pairs = outer.anchors or [
                        (href, href.rsplit("/", 1)[-1]) for href in outer.files
                    ]
                    body = (
                        "<html><body><div>"
                        + "".join(f'<a href="{href}">{label}</a>' for href, label in pairs)
                        + "</div></body></html>"
                    ).encode()
                    ctype = "text/html; charset=utf-8"
                elif self.path in outer.files:
                    with outer._lock:
                        outer.transfers.append(self.path)
                    body = outer.files[self.path]
                    ctype = "application/octet-stream"
                else:
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return Handler


class RangeLiarServer:
    """Answers the first ``liar_requests`` Range requests with the wrong start.

    The response is otherwise well formed -- ``206``, a plausible
    ``Content-Range`` whose *total* is correct -- which is what a CDN that
    re-encodes the body looks like to the client.
    """

    def __init__(self, data: bytes, liar_requests: int = 1) -> None:
        self.data = data
        self.liar_requests = liar_requests
        self.requests: list[str | None] = []
        self._lock = threading.Lock()
        self.server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), self._handler())
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}/f.bin"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def __enter__(self) -> RangeLiarServer:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _handler(self):
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def do_GET(self):
                rng = self.headers.get("Range")
                with outer._lock:
                    outer.requests.append(rng)
                    index = len(outer.requests)
                if not rng:
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(outer.data)))
                    self.send_header("ETag", '"' + hashlib.sha256(outer.data).hexdigest() + '"')
                    self.end_headers()
                    self.wfile.write(outer.data)
                    return
                start = int(rng.split("=")[1].split("-")[0])
                if index <= outer.liar_requests:
                    # Start at 0 no matter what was asked for.
                    body = outer.data[:100]
                    self.send_response(206)
                    self.send_header("Content-Range", f"bytes 0-99/{len(outer.data)}")
                else:
                    body = outer.data[start:]
                    self.send_response(206)
                    self.send_header(
                        "Content-Range", f"bytes {start}-{len(outer.data) - 1}/{len(outer.data)}"
                    )
                self.send_header("Content-Length", str(len(body)))
                self.send_header("ETag", '"' + hashlib.sha256(outer.data).hexdigest() + '"')
                self.end_headers()
                self.wfile.write(body)

        return Handler


def _seeded_item(tmp_path: Path, url: str, item_id: str = "12345") -> Path:
    db = init_db(tmp_path / "app.db")
    conn = get_connection(db)
    conn.execute(
        "INSERT INTO items(item_id,title,url,shop) VALUES(?,?,?,?)",
        (item_id, "Test Item", url, "shop"),
    )
    conn.commit()
    conn.close()
    return db


def _jar(tmp_path: Path) -> Path:
    path = tmp_path / "cookies.json"
    path.write_text(
        json.dumps([{"name": "session", "value": "v", "domain": "127.0.0.1"}]), encoding="utf-8"
    )
    return path


# ---------------------------------------------------------------------------
# 1. A re-run must not create a second copy of anything
# ---------------------------------------------------------------------------


def test_rerun_does_not_duplicate_downloads(tmp_path):
    """The core regression: three runs, one file, one ledger row.

    The bug derived each file name from what was already on disk, so every
    re-run appended ``_2``, ``_3``, ... and re-downloaded the payload. The user
    saw the download complete and the DL progress table keep growing.
    """
    with ItemServer({"/downloads/1/a.bin": b"A" * 2048}) as server:
        db = _seeded_item(tmp_path, server.item_url)
        jar = _jar(tmp_path)
        library = tmp_path / "lib"

        first = download_item("12345", db, library, cookie_path=jar)
        assert len(first["files"]) == 1
        assert first["files"][0]["file"] == "a.bin"
        assert first["files"][0].get("skipped") is not True

        for run in (2, 3):
            again = download_item("12345", db, library, cookie_path=jar)
            assert len(again["files"]) == 1, f"run {run} produced extra files"
            assert again["files"][0]["file"] == "a.bin", (
                f"run {run} renamed the file to {again['files'][0]['file']!r}"
            )
            assert again["files"][0].get("skipped") is True, f"run {run} re-downloaded the file"

    on_disk = sorted(p.name for p in (library).rglob("*") if p.is_file() and p.suffix == ".bin")
    assert on_disk == ["a.bin"], f"duplicates left in the library: {on_disk}"

    conn = get_connection(db)
    try:
        rows = [
            dict(r) for r in conn.execute("SELECT file_name, status, url FROM downloads").fetchall()
        ]
    finally:
        conn.close()
    assert [r["file_name"] for r in rows] == ["a.bin"]
    assert rows[0]["status"] == "done"
    # The binding is what makes the re-run a no-op, so it must be recorded.
    assert rows[0]["url"].endswith("/downloads/1/a.bin")

    assert len(server.transfers) == 1, f"payload was fetched {len(server.transfers)} times"


def test_rerun_skips_even_when_the_link_label_changes(tmp_path):
    """A label change must not create a second copy of the same URL.

    BOOTH renders the link text from the seller's file name, so renaming a file
    on their side changes the label while the URL stays put. Binding on the URL
    means the already downloaded file is still recognised and reused; binding on
    the label would have produced a duplicate.
    """
    payload = b"A" * 512
    href = "/downloads/1/a.bin"
    with ItemServer({href: payload}, anchors=[(href, "a.bin")]) as server:
        db = _seeded_item(tmp_path, server.item_url)
        jar = _jar(tmp_path)
        library = tmp_path / "lib"
        download_item("12345", db, library, cookie_path=jar)
        assert server.transfers == [href], "the first run must actually fetch the payload"

        # The seller renames the file: BOOTH keeps the URL and changes the text.
        server.anchors = [(href, "renamed-by-seller.bin")]
        again = download_item("12345", db, library, cookie_path=jar)
        assert again["files"][0]["file"] == "a.bin"
        assert again["files"][0].get("skipped") is True
        assert server.transfers == [href], "the payload was fetched again after a label change"

    assert sorted(p.name for p in library.rglob("*.bin")) == ["a.bin"]


def test_two_links_with_the_same_label_get_distinct_files(tmp_path):
    """Uniqueness must still hold between different links of one item."""
    with ItemServer(
        {"/downloads/1/data.bin": b"first", "/downloads/2/data.bin": b"second"}
    ) as server:
        db = _seeded_item(tmp_path, server.item_url)
        jar = _jar(tmp_path)
        library = tmp_path / "lib"
        result = download_item("12345", db, library, cookie_path=jar)
        names = sorted(f["file"] for f in result["files"])
        assert names == ["data.bin", "data_2.bin"]
        contents = {p.name: p.read_bytes() for p in library.rglob("*.bin")}
        assert contents == {"data.bin": b"first", "data_2.bin": b"second"}

        # And a re-run keeps both bindings.
        again = download_item("12345", db, library, cookie_path=jar)
        assert sorted(f["file"] for f in again["files"]) == names
        assert all(f.get("skipped") is True for f in again["files"])


def test_force_refetches_in_place_without_renaming(tmp_path):
    """``--force`` must overwrite the recorded file, not add a numbered copy."""
    with ItemServer({"/downloads/1/a.bin": b"A" * 128}) as server:
        db = _seeded_item(tmp_path, server.item_url)
        jar = _jar(tmp_path)
        library = tmp_path / "lib"
        download_item("12345", db, library, cookie_path=jar)
        forced = download_item("12345", db, library, cookie_path=jar, force=True)
        assert [f["file"] for f in forced["files"]] == ["a.bin"]
        assert forced["files"][0].get("skipped") is not True
    assert sorted(p.name for p in library.rglob("*.bin")) == ["a.bin"]


def test_untracked_file_in_the_download_dir_is_not_clobbered(tmp_path):
    """The filesystem still guards files this application does not own."""
    with ItemServer({"/downloads/1/a.bin": b"from the server"}) as server:
        db = _seeded_item(tmp_path, server.item_url)
        jar = _jar(tmp_path)
        library = tmp_path / "lib"
        dl_dir = library / "12345_Test Item" / "downloads"
        dl_dir.mkdir(parents=True)
        intruder = dl_dir / "a.bin"
        intruder.write_bytes(b"hand placed")

        download_item("12345", db, library, cookie_path=jar)
        assert intruder.read_bytes() == b"hand placed"
        assert (dl_dir / "a_2.bin").read_bytes() == b"from the server"


def test_legacy_ledger_rows_stay_idempotent(tmp_path):
    """A library written before the url column existed must not re-download.

    Existing users already have ``downloads`` rows with no url. Matching those
    on the preferred name keeps the upgrade free of a full re-download.
    """
    with ItemServer({"/downloads/1/a.bin": b"A" * 64}) as server:
        db = _seeded_item(tmp_path, server.item_url)
        jar = _jar(tmp_path)
        library = tmp_path / "lib"
        download_item("12345", db, library, cookie_path=jar)

        # Rewrite the ledger into its pre-1.0.2 shape.
        conn = get_connection(db)
        conn.execute("UPDATE downloads SET url=''")
        conn.commit()
        conn.close()

        again = download_item("12345", db, library, cookie_path=jar)
        assert again["files"][0]["file"] == "a.bin"
        assert again["files"][0].get("skipped") is True
    assert len(server.transfers) == 1


# ---------------------------------------------------------------------------
# 2. A 206 must start where it was asked to start
# ---------------------------------------------------------------------------


def test_wrong_range_start_never_reaches_the_published_file(tmp_path):
    """The exact corruption scenario, end to end.

    A 206 that starts somewhere else must be refused *before* any byte is
    written. Appending it produced a full-length file with 100 wrong bytes in
    the middle, which was recorded as ``done`` together with its checksum.
    """
    data = bytes((i * 7 + 11) % 251 for i in range(4096))
    dest = tmp_path / "f.bin"
    part = dest.with_name("f.bin.part")
    part.write_bytes(data[:2048])

    with RangeLiarServer(data, liar_requests=1) as server:
        seed_resume_state(part, server.url, data)
        with pytest.raises(BoothNetworkError) as exc:
            download_file(server.url, dest, [], resume=True, timeout=20, max_retries=1)
    assert not dest.exists(), "a corrupt file was published as if it were complete"
    # The poisoned part must be gone, or the next resume splices it in.
    assert not part.exists(), "a .part with the wrong bytes survived for the next attempt"
    assert "range" in str(exc.value).lower()


def test_resume_after_a_wrong_range_yields_identical_bytes(tmp_path):
    """The follow-up run must produce the exact original, not a full-length wrong file."""
    data = bytes((i * 13 + 5) % 251 for i in range(4096))
    dest = tmp_path / "f.bin"
    part = dest.with_name("f.bin.part")
    part.write_bytes(data[:2048])

    # One lying response, then an honest one.
    with RangeLiarServer(data, liar_requests=1) as server:
        seed_resume_state(part, server.url, data)
        download_file(server.url, dest, [], resume=True, timeout=20, max_retries=3)

    assert dest.read_bytes() == data
    assert dest.stat().st_size == len(data)


def test_a_honest_server_still_resumes(tmp_path):
    """The added check must not break a well-behaved origin."""
    data = bytes((i * 3 + 1) % 251 for i in range(2048))
    dest = tmp_path / "f.bin"
    part = dest.with_name("f.bin.part")
    part.write_bytes(data[:1000])
    with RangeLiarServer(data, liar_requests=0) as server:
        seed_resume_state(part, server.url, data)
        download_file(server.url, dest, [], resume=True, timeout=20)
    assert dest.read_bytes() == data


def test_content_range_parsing():
    from core.download import _content_range_start, _content_range_total

    assert _content_range_start("bytes 100-199/200") == 100
    assert _content_range_start("bytes 0-0/1") == 0
    assert _content_range_start("bytes */200") is None
    assert _content_range_start("") is None
    assert _content_range_start("garbage") is None
    assert _content_range_total("bytes 100-199/200") == 200
    assert _content_range_total("bytes */200") == 200


# ---------------------------------------------------------------------------
# 3. No false "done": a cap must be reported, never silently applied
# ---------------------------------------------------------------------------


def test_too_many_download_links_is_reported_not_silently_truncated(tmp_path):
    """A cap on the number of links must not yield a false "done".

    Keeping the first 64 and recording the item as complete told the user they
    had the whole purchase when a file was missing, with nothing on screen or
    in the ledger to say otherwise.
    """
    from core.download import resolve_download_links
    from core.errors import BoothLimitExceededError

    anchors = [(f"/downloads/{i}/f{i}.bin", f"f{i}.bin") for i in range(6)]
    files = {href: b"x" for href, _ in anchors}
    with ItemServer(files, anchors=anchors) as server:
        with pytest.raises(BoothLimitExceededError) as exc:
            resolve_download_links(server.item_url, [], max_links=4)
        assert "limit" in str(exc.value)

        # Under the cap it still works.
        links = resolve_download_links(server.item_url, [], max_links=10)
        assert len(links) == 6


def test_a_provisional_item_id_is_logged(tmp_path, caplog):
    """A row with no product link is keyed provisionally, and says so.

    The provisional id is a different key from the real product id, so a later
    parse that does find the link would add a second copy of the same purchase.
    """
    import logging

    from core.purchases import parse_library_html

    html = """
    <html><body><div class="item-list">
      <div class="item"><a href="/orders/111">商品A</a></div>
    </div></body></html>
    """
    with caplog.at_level(logging.WARNING, logger="core.purchases"):
        rows = parse_library_html(html)
    assert rows[0]["item_id"] == "order_111"
    assert any("provisional ID" in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# 4. A newer database is refused cleanly
# ---------------------------------------------------------------------------


def test_download_url_migration_is_forward_only(tmp_path):
    """A v1 database gains the column and keeps its rows."""
    from core.db import SCHEMA_VERSION, schema_version

    db = tmp_path / "old.db"
    conn = get_connection(db)
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
      PRAGMA user_version = 1;
    """)
    conn.execute("INSERT INTO items(item_id,title) VALUES('old','既存')")
    conn.execute("INSERT INTO downloads(item_id,file_name,status) VALUES('old','x.bin','done')")
    conn.commit()
    conn.close()

    init_db(db)
    assert schema_version(db) == SCHEMA_VERSION
    conn = get_connection(db)
    try:
        columns = {r["name"] for r in conn.execute("PRAGMA table_info(downloads)")}
        assert "url" in columns
        assert (
            conn.execute("SELECT file_name, url FROM downloads").fetchone()["file_name"] == "x.bin"
        )
    finally:
        conn.close()
    # Idempotent.
    init_db(db)


# ---------------------------------------------------------------------------
# 4. doctor inspects the cookie jar it is told about
# ---------------------------------------------------------------------------


def test_doctor_honours_cookie_path(tmp_path):
    import argparse
    import contextlib
    import io

    import cli as cli_mod

    custom = tmp_path / "custom.json"
    custom.write_text(json.dumps([{"name": "s", "value": "v"}]), encoding="utf-8")
    db = init_db(tmp_path / "d.db")

    def run(extra: list[str]) -> dict:
        parser = cli_mod.build_parser()
        parsed = parser.parse_args(["doctor", "--json", *extra])
        ns = argparse.Namespace(db=parsed.db, library=parsed.library, json=True)
        ns.cookie_path = parsed.cookie_path
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cli_mod._cmd_doctor(ns, str(db))
        return json.loads(buf.getvalue())

    reported = run(
        ["--db", str(db), "--library", str(tmp_path / "lib"), "--cookie-path", str(custom)]
    )
    cookies = {c["name"]: c for c in reported["checks"]}["cookies"]
    assert cookies["ok"] is True, "a logged-in custom jar was reported as missing"
    assert str(custom) in cookies["detail"]

    # And an absent one is reported as absent rather than silently checked.
    absent = run(
        [
            "--db",
            str(db),
            "--library",
            str(tmp_path / "lib"),
            "--cookie-path",
            str(tmp_path / "nope.json"),
        ]
    )
    assert {c["name"]: c for c in absent["checks"]}["cookies"]["ok"] is False


# ---------------------------------------------------------------------------
# 5. auth login names the real failure
# ---------------------------------------------------------------------------


class _FakePw:
    """Minimal stand-in exposing the API surface ``login`` actually uses."""

    def __init__(
        self,
        *,
        launch_error: Exception | None = None,
        goto_error: Exception | None = None,
        cookies_error: Exception | None = None,
    ) -> None:
        self.launch_error = launch_error
        self.goto_error = goto_error
        self.cookies_error = cookies_error
        self.chromium = self
        self.stopped = False
        self.closed = False

    def start(self):
        return self

    def stop(self):
        self.stopped = True

    def launch(self, headless: bool = False, **options):
        if self.launch_error:
            raise self.launch_error
        return self

    def new_context(self):
        return self

    def new_page(self):
        return self

    def goto(self, *a, **k):
        if self.goto_error:
            raise self.goto_error
        from types import SimpleNamespace

        return SimpleNamespace(status=200)

    @property
    def url(self) -> str:
        return "https://accounts.booth.pm/library"

    def locator(self, *a, **k):
        return self

    def count(self) -> int:
        return 1

    def cookies(self):
        if self.cookies_error:
            raise self.cookies_error
        return [{"name": "a", "value": "b"}]

    def close(self):
        self.closed = True


def _install_fake(monkeypatch, factory) -> None:
    import playwright.sync_api as pwapi

    from core import browser

    monkeypatch.setattr(pwapi, "sync_playwright", factory)
    monkeypatch.setattr(
        browser, "launch_browser", lambda pw, headless=False: pw.chromium.launch(headless=headless)
    )


@pytest.fixture
def enter(monkeypatch):
    """Answer the login prompt without a terminal.

    Without this the daemon thread's ``input()`` fails under pytest's capture
    and the login aborts before reaching the behaviour under test.
    """
    import builtins

    monkeypatch.setattr(builtins, "input", lambda prompt="": "")


def test_login_network_failure_is_not_reported_as_a_missing_browser(monkeypatch, tmp_path):
    """DNS / proxy / captive portal must not be reported as a broken install.

    The advice given was "run ``playwright install chromium``". The browser had
    launched fine, so following it changed nothing and the same error came back.
    """
    from core.auth import login
    from core.errors import BoothNetworkError, BoothPrerequisiteError

    _install_fake(monkeypatch, lambda: _FakePw(goto_error=OSError("ERR_NAME_NOT_RESOLVED")))
    with pytest.raises(BoothNetworkError) as exc:
        login(headless=True, path=tmp_path / "ck.json", timeout_s=5)
    assert not isinstance(exc.value, BoothPrerequisiteError)
    message = str(exc.value)
    assert "chromium" not in message.lower()
    assert "network" in message or "DNS" in message


def test_login_browser_start_failure_is_still_a_prerequisite(monkeypatch, tmp_path):
    from core.auth import login
    from core.errors import BoothPrerequisiteError

    _install_fake(
        monkeypatch, lambda: _FakePw(launch_error=RuntimeError("Executable doesn't exist"))
    )
    with pytest.raises(BoothPrerequisiteError) as exc:
        login(headless=True, path=tmp_path / "ck.json", timeout_s=5)
    from core.platforms import launcher_name

    assert f"{launcher_name()} --repair" in str(exc.value)


def test_login_playwright_start_failure_is_still_a_prerequisite(monkeypatch, tmp_path):
    from core.auth import login
    from core.errors import BoothPrerequisiteError

    class Bad:
        def start(self):
            raise RuntimeError("driver not installed")

    _install_fake(monkeypatch, lambda: Bad())
    with pytest.raises(BoothPrerequisiteError):
        login(headless=True, path=tmp_path / "ck.json", timeout_s=5)


def test_login_cookie_read_failure_is_reported_as_transport(monkeypatch, tmp_path, enter):
    from core.auth import login
    from core.errors import BoothNetworkError

    _install_fake(monkeypatch, lambda: _FakePw(cookies_error=RuntimeError("Target closed")))
    with pytest.raises(BoothNetworkError) as exc:
        login(headless=True, path=tmp_path / "ck.json", timeout_s=5)
    assert "chromium" not in str(exc.value).lower()


def test_login_succeeds_and_stores_the_jar(monkeypatch, tmp_path, enter):
    """The happy path still works end to end after the error handling changed."""
    from core.auth import login

    fake = _FakePw()
    _install_fake(monkeypatch, lambda: fake)
    saved = login(headless=True, path=tmp_path / "ck.json", timeout_s=5)
    assert saved.exists()
    assert json.loads(saved.read_text(encoding="utf-8")) == [{"name": "a", "value": "b"}]
    assert fake.closed and fake.stopped


def test_login_releases_the_browser_on_failure(monkeypatch, tmp_path):
    """A failed login must not leave Chromium running."""
    from core.auth import login
    from core.errors import BoothNetworkError

    fake = _FakePw(goto_error=OSError("boom"))
    _install_fake(monkeypatch, lambda: fake)
    with pytest.raises(BoothNetworkError):
        login(headless=True, path=tmp_path / "ck.json", timeout_s=5)
    assert fake.closed and fake.stopped


def test_login_reports_an_unreadable_stdin_instead_of_crashing_a_thread(monkeypatch, tmp_path):
    """``input()`` failing must be reported, not raised inside a worker thread.

    With stdin closed or redirected (``< NUL``, a scheduler, a service) the
    old code let the ``OSError`` escape the daemon thread: a stack trace was
    printed and the user was then told the login could not be confirmed, which
    has nothing to do with what happened.
    """
    import builtins

    from core.auth import login
    from core.errors import BoothAuthError

    fake = _FakePw()
    _install_fake(monkeypatch, lambda: fake)

    def broken_input(prompt: str = "") -> str:
        raise OSError("reading from stdin while output is captured")

    monkeypatch.setattr(builtins, "input", broken_input)
    with pytest.raises(BoothAuthError) as exc:
        login(headless=True, path=tmp_path / "ck.json", timeout_s=5)
    assert "stdin" in str(exc.value)
    assert fake.closed and fake.stopped
