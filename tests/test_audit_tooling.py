"""Release validation must quote paths and describe the real portable layout."""

import sys
from pathlib import Path
from types import SimpleNamespace

from tools import rc_test


def test_launcher_probe_does_not_kill_unowned_processes(tmp_path, monkeypatch):
    import pytest

    from tools import launcher_probe

    (tmp_path / "OWNED-BY-PORTABILITY-TEST.txt").touch()
    monkeypatch.setattr(launcher_probe, "ROOT", tmp_path / "checkout")
    calls = []
    monkeypatch.setattr(launcher_probe.subprocess, "run", lambda *a, **k: calls.append(a))

    def stop_before_launch():
        raise RuntimeError("probe boundary")

    monkeypatch.setattr(launcher_probe.socket, "socket", stop_before_launch)
    with pytest.raises(RuntimeError, match="probe boundary"):
        launcher_probe.main()
    assert calls == [], "An isolated probe must not terminate pre-existing applications"


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
