"""Release validation must quote paths and describe the real portable layout."""

import sys
from pathlib import Path
from types import SimpleNamespace

from tools import rc_test


def test_a11_rc_startup_preserves_paths_with_spaces(tmp_path, monkeypatch):
    work = tmp_path / "path with spaces"
    work.mkdir()
    calls = []
    monkeypatch.setattr(
        rc_test,
        "run",
        lambda cmd, *a, **k: (
            calls.append(cmd) or SimpleNamespace(returncode=0, stdout="", stderr="")
        ),
    )
    monkeypatch.setattr(rc_test, "record", lambda *a, **k: None)
    rc_test.gate_startup(Path(sys.executable), work)
    assert calls[1][-1] == str(work / "app.db")


def test_a11_lock_regenerator_metadata_and_hash(tmp_path):
    import hashlib
    import zipfile

    from tools.gen_lock import main

    wheels = tmp_path / "wheels"
    wheels.mkdir()
    wheel = wheels / "fake_package-1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            "fake_package-1.0.dist-info/METADATA", "Name: fake-package\nVersion: 1.0\n"
        )
    output = tmp_path / "lock.txt"
    assert main([str(wheels), str(output)]) == 0
    text = output.read_text(encoding="utf-8")
    assert "fake-package==1.0" in text
    assert hashlib.sha256(wheel.read_bytes()).hexdigest() in text
