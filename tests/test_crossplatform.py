"""Cross-OS boundaries: target selection, safe relocation, real process locks."""

import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from core.library_lock import library_lock
from core.library_paths import record_path, resolve_record
from core.platforms import load_manifest, target_id, venv_relative


@pytest.mark.parametrize(
    "system,cpu,target", [("win32", "AMD64", "windows-x64"), ("darwin", "arm64", "macos-arm64")]
)
def test_target_detection(system, cpu, target):
    assert target_id(system, cpu) == target


@pytest.mark.parametrize(
    "system,cpu", [("darwin", "x86_64"), ("win32", "ARM64"), ("linux", "aarch64")]
)
def test_unsupported_targets_fail_explicitly(system, cpu):
    with pytest.raises(RuntimeError, match="Unsupported platform"):
        target_id(system, cpu)


def test_mac_layout_and_lock_are_selected():
    root = Path(__file__).resolve().parent.parent
    spec = load_manifest(root, "macos-arm64")
    assert spec["lock"] == "requirements-macos-arm64-lock.txt"
    assert venv_relative("macos-arm64").as_posix() == "bin/python3"
    assert spec["bootstrapNetwork"] is False


@pytest.mark.parametrize(
    "value",
    [
        r"E:\old\lib\123_商品\downloads\data.part",
        "/old/lib/123_商品/downloads/data.part",
        "library:/123_商品/downloads/data.part",
    ],
)
def test_windows_posix_and_relative_records_recover_in_new_library(tmp_path, value):
    path = resolve_record(value, tmp_path)
    assert path is not None
    assert path == tmp_path / "123_商品/downloads/data.part"
    assert record_path(path, tmp_path) == "library:/123_商品/downloads/data.part"


@pytest.mark.parametrize(
    "value",
    [
        "library:/../escape",
        "library://absolute",
        "library:/item/../../escape",
        "library:/item\\escape",
    ],
)
def test_relative_records_refuse_escape(tmp_path, value):
    with pytest.raises(ValueError, match="library path"):
        resolve_record(value, tmp_path)


def test_library_lock_excludes_another_process_and_releases(tmp_path):
    code = "from core.library_lock import library_lock; import sys;\nwith library_lock(sys.argv[1]): print('acquired')"
    with library_lock(tmp_path):
        result = subprocess.run(
            [sys.executable, "-c", code, str(tmp_path)],
            cwd=Path(__file__).resolve().parent.parent,
            capture_output=True,
            timeout=30,
        )
        assert result.returncode != 0
        assert b"Another download" in result.stderr
    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path)],
        cwd=Path(__file__).resolve().parent.parent,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert b"acquired" in result.stdout


def test_zip_rejects_unicode_normalization_collision(tmp_path):
    from core.download import safe_extract_zip
    from core.errors import BoothNetworkError

    path = tmp_path / "collision.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("が.txt", b"one")
        archive.writestr("か\u3099.txt", b"two")
    with pytest.raises(BoothNetworkError, match="Duplicate ZIP"):
        safe_extract_zip(path, tmp_path / "out", strict=True)


def test_running_runtime_accepts_readers_but_refuses_repair(tmp_path):
    from core.runtime_lock import runtime_lock

    with runtime_lock(tmp_path, exclusive=False), runtime_lock(tmp_path, exclusive=False):
        with pytest.raises(RuntimeError, match="Runtime is in use"):
            with runtime_lock(tmp_path, exclusive=True):
                pytest.fail("Exclusive repair must not enter a running runtime")
    with runtime_lock(tmp_path, exclusive=True) as downgrade:
        downgrade()
        with runtime_lock(tmp_path, exclusive=False):
            pass


def test_download_names_preserve_both_unicode_equivalent_files(tmp_path):
    from core.download import _file_name_for

    used = {"か\u3099.zip"}
    assert (
        _file_name_for(
            tmp_path, {"url": "https://booth.pm/files/new.zip", "label": "が.zip"}, 1, used
        )
        == "が_2.zip"
    )


def test_v4_upgrade_preserves_legacy_downloads_and_supports_portable_records(tmp_path):
    from core.db import ensure_current_schema, get_connection, init_db, schema_version
    from core.download import _set_status

    database = init_db(tmp_path / "legacy.db")
    conn = get_connection(database)
    try:
        conn.execute("ALTER TABLE downloads DROP COLUMN path_encoding")
        conn.execute("PRAGMA user_version=4")
        conn.execute("INSERT INTO items(item_id,title) VALUES('123','移動確認')")
        conn.execute(
            "INSERT INTO downloads(item_id,file_name,path,status) VALUES('123','old.zip',?,'done')",
            (r"E:\old\123_商品\downloads\old.zip",),
        )
        conn.commit()
    finally:
        conn.close()
    ensure_current_schema(database)
    assert schema_version(database) == 5
    conn = get_connection(database)
    try:
        old = conn.execute(
            "SELECT path,path_encoding FROM downloads WHERE file_name='old.zip'"
        ).fetchone()
        assert old["path"] == r"E:\old\123_商品\downloads\old.zip"
        assert old["path_encoding"] == "legacy"
        _set_status(conn, "123", "new.zip", "done", "library:/123_商品/downloads/new.zip")
        assert (
            conn.execute(
                "SELECT path_encoding FROM downloads WHERE file_name='new.zip'"
            ).fetchone()[0]
            == "library-relative"
        )
    finally:
        conn.close()


def test_manifests_do_not_share_native_payloads():
    root = Path(__file__).resolve().parent.parent
    specs = [load_manifest(root, target) for target in ("windows-x64", "macos-arm64")]
    assert len({spec["vendorManifest"] for spec in specs}) == 2
    assert len({spec["lock"] for spec in specs}) == 2
    for spec in specs:
        assert (
            json.loads((root / spec["vendorManifest"]).read_text())["assets"]["python"]["sha256"]
            == spec["python"]["sha256"]
        )
