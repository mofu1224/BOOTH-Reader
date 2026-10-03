"""New purchases must not stat every unrelated directory in a large library."""

import shutil
from pathlib import Path

from core.db import get_connection
from core.download import download_item
from tests.test_regression_102 import ItemServer, _jar, _seeded_item


def test_new_download_does_not_probe_unrelated_directories(tmp_path, monkeypatch):
    library = tmp_path / "lib"
    library.mkdir()
    for i in range(1000):
        (library / f"unrelated_{i}").mkdir()
    inspected = []
    original_is_dir = Path.is_dir

    def measured(path):
        if path.name.startswith("unrelated_"):
            inspected.append(path)
        return original_is_dir(path)

    monkeypatch.setattr(Path, "is_dir", measured)
    with ItemServer({"/downloads/a.bin": b"payload"}) as server:
        db = _seeded_item(tmp_path, server.item_url)
        result = download_item("12345", db, library, cookie_path=_jar(tmp_path))
    assert result["status"] == "done"
    assert inspected == [], "a new item performed O(library-size) filesystem probes"


def test_copied_library_preserves_old_directory_after_title_update(tmp_path):
    original = tmp_path / "original"
    copied = tmp_path / "copied"
    with ItemServer({"/downloads/a.bin": b"payload"}) as server:
        db = _seeded_item(tmp_path, server.item_url)
        jar = _jar(tmp_path)
        first = download_item("12345", db, original, cookie_path=jar)
        shutil.copytree(original, copied)
        conn = get_connection(db)
        conn.execute("UPDATE items SET title='Renamed'")
        conn.commit()
        conn.close()
        second = download_item("12345", db, copied, cookie_path=jar)
        assert Path(second["dir"]) == copied / Path(first["dir"]).name
        assert second["files"][0]["skipped"] is True
        assert len(server.transfers) == 1
