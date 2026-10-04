"""New audit regressions: preserve published data and reject false success."""

import hashlib
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from core import auth, download, purchases
from core.db import get_connection, init_db
from tools import dependency_inventory, manage_portable, vendor_payload, verify_clone


@pytest.mark.parametrize("status", [401, 403, 404, 429, 500, 503])
def test_login_verification_rejects_http_failure(status):
    page = SimpleNamespace(
        url=auth.LIBRARY_URL,
        goto=lambda *args, **kwargs: SimpleNamespace(status=status),
        locator=lambda *args: SimpleNamespace(count=lambda: 0),
    )
    assert auth._verify_login(page) is False


@pytest.mark.parametrize(
    "url,response,expected",
    [
        (auth.LIBRARY_URL, SimpleNamespace(status=200), True),
        (auth.LIBRARY_URL, None, False),
        ("https://accounts.booth.pm/login", SimpleNamespace(status=200), False),
        ("https://portal.example.test/library", SimpleNamespace(status=200), False),
    ],
)
def test_login_verification_checks_destination_and_empty_library(url, response, expected):
    page = SimpleNamespace(
        url=url,
        goto=lambda *args, **kwargs: response,
        locator=lambda *args: SimpleNamespace(count=lambda: 0),
    )
    assert auth._verify_login(page) is expected


def test_published_part_suffix_survives_cleanup(tmp_path):
    name = download._file_name_for(
        tmp_path, {"label": "model.part", "url": "https://example.test/model.part"}, 1, set()
    )
    published = tmp_path / name
    published.write_bytes(b"purchased original")
    interrupted = tmp_path / (name + download.PART_SUFFIX)
    interrupted.write_bytes(b"incomplete")
    assert download.cleanup_partials(tmp_path) == 1
    assert published.read_bytes() == b"purchased original"


@pytest.mark.parametrize("moved", [False, True])
def test_cli_cleanup_preserves_legacy_original_and_sidecar(tmp_path, moved):
    import cli

    db = init_db(tmp_path / "test.db")
    root = tmp_path / "library"
    folder = root / "123_title" / "downloads"
    folder.mkdir(parents=True)
    original = folder / "model.part"
    sidecar_original = folder / "unfinished.part.json"
    for path in (original, sidecar_original):
        path.write_bytes(b"original")
    (folder / "unfinished.part").write_bytes(b"interrupted")
    extracted = folder.parent / "extracted" / "asset.part"
    extracted.parent.mkdir()
    extracted.write_bytes(b"extracted original")
    conn = get_connection(db)
    try:
        conn.execute("INSERT INTO items(item_id) VALUES('123')")
        for path in (original, sidecar_original):
            recorded = tmp_path / "old-library" / path.relative_to(root) if moved else path
            conn.execute(
                "INSERT INTO downloads(item_id,file_name,path,status) VALUES(?,?,?,'done')",
                ("123", path.name, str(recorded)),
            )
        conn.commit()
    finally:
        conn.close()
    assert cli.main(["--db", str(db), "downloads", "cleanup", "--output-dir", str(root)]) == 0
    assert original.read_bytes() == sidecar_original.read_bytes() == b"original"
    assert not (folder / "unfinished.part").exists()
    assert extracted.read_bytes() == b"extracted original"


def test_new_download_scratch_never_overwrites_legacy_original(tmp_path):
    ledger = download._NameLedger([{"file_name": "model.bin.part", "url": "legacy"}])
    name = download._file_name_for(tmp_path, {"label": "model.bin", "url": "new"}, 1, set(), ledger)
    assert name == "model_2.bin"


def test_legacy_scratch_collision_fails_before_writing(tmp_path):
    ledger = download._NameLedger(
        [
            {"file_name": "model.bin", "url": "old"},
            {"file_name": "model.bin.part", "url": "other"},
        ]
    )
    with pytest.raises(ValueError, match="衝突"):
        download._file_name_for(tmp_path, {"label": "model.bin", "url": "old"}, 1, set(), ledger)


def test_csv_export_does_not_clobber_existing_sibling_temp(tmp_path):
    target = tmp_path / "export.csv"
    sibling = tmp_path / "export.csv.tmp"
    sibling.write_bytes(b"another writer's data")
    purchases.export_csv([{"item_id": "1", "title": "商品"}], target)
    assert sibling.read_bytes() == b"another writer's data"
    assert "商品" in target.read_text(encoding="utf-8-sig")


@pytest.mark.parametrize("module", [manage_portable, vendor_payload, dependency_inventory])
def test_portable_hashing_on_python310_api(tmp_path, monkeypatch, module):
    monkeypatch.delattr(hashlib, "file_digest", raising=False)
    path = tmp_path / "payload"
    path.write_bytes(b"payload")
    function = module.digest if module is manage_portable else module.sha
    assert function(path) == hashlib.sha256(b"payload").hexdigest()


def test_concurrent_csv_exports_publish_complete_snapshots(tmp_path, monkeypatch):
    import csv

    barrier = threading.Barrier(2)
    local = threading.local()
    replace = os.replace

    def synchronized_replace(source, target):
        if not getattr(local, "ready", False):
            barrier.wait(timeout=5)
            local.ready = True
        replace(source, target)

    monkeypatch.setattr(purchases.os, "replace", synchronized_replace)
    target = tmp_path / "shared.csv"
    batches = [[{"item_id": str(i), "title": title} for i in range(100)] for title in ("A", "B")]
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda rows: purchases.export_csv(rows, target), batches))
    with target.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 100
    assert {row["title"] for row in rows} in ({"A"}, {"B"})
    assert not list(tmp_path.glob("*.tmp"))


def test_csv_transient_windows_publish_denial_recovers(tmp_path, monkeypatch):
    replace = os.replace
    attempts = []

    def transient(source, target):
        attempts.append(source)
        if len(attempts) < 3:
            raise PermissionError("synthetic concurrent publish")
        replace(source, target)

    monkeypatch.setattr(purchases.os, "replace", transient)
    target = tmp_path / "retry.csv"
    purchases.export_csv([{"title": "complete"}], target)
    assert len(attempts) == 3
    assert "complete" in target.read_text(encoding="utf-8-sig")
    assert not list(tmp_path.glob("*.tmp"))


def test_csv_failed_publish_preserves_previous_file(tmp_path, monkeypatch):
    from core.errors import BoothNetworkError

    target = tmp_path / "shared.csv"
    target.write_bytes(b"previous export")

    def fail(*args):
        raise PermissionError("synthetic locked destination")

    monkeypatch.setattr(purchases.os, "replace", fail)
    with pytest.raises(BoothNetworkError):
        purchases.export_csv([{"item_id": "1"}], target)
    assert target.read_bytes() == b"previous export"
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("version", [(3, 10), (3, 12)])
def test_clone_cleanup_accepts_supported_shutil_api(tmp_path, monkeypatch, version):
    monkeypatch.setattr(verify_clone, "ROOT", tmp_path)
    monkeypatch.setattr(verify_clone.sys, "version_info", version)
    work = tmp_path / ".cache" / "clone-check-owned"
    work.mkdir(parents=True)
    (work / "OWNED-BY-PORTABILITY-TEST.txt").write_text("test")
    (work / "readonly").write_bytes(b"test")
    (work / "readonly").chmod(0o400)
    verify_clone.remove_owned(work)
    assert not work.exists()


def test_cookie_atomic_publish_and_logout_in_modify_only_directory(tmp_path):
    directory = tmp_path / "modify-only"
    directory.mkdir()
    account = auth.current_account()
    assert account
    assert auth.icacls(directory, "/grant:r", f"{account}:(OI)(CI)(M)")
    assert auth.icacls(directory, "/inheritance:r")
    path = directory / "cookies.json"
    try:
        auth.save_cookies([{"name": "synthetic", "value": "first"}], path)
        # A jar created by the previous version has read/write but no DELETE.
        assert auth.icacls(path, "/grant:r", f"{account}:(R,W)")
        auth.save_cookies([{"name": "synthetic", "value": "second"}], path)
        assert auth.load_cookies(path)[0]["value"] == "second"
        assert auth.icacls(path, "/grant:r", f"{account}:(R,W)")
        assert auth.logout(path)
        assert not list(directory.iterdir())
    finally:
        # Only test-owned files: restore cleanup access even on the red run.
        for file in directory.iterdir():
            assert auth.icacls(file, "/grant:r", f"{account}:(F)")
