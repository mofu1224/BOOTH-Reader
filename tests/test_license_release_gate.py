"""A release candidate must never silently bypass incomplete license evidence."""

import json

import pytest

from tools import build_release


def test_release_gate_rejects_missing_and_blocked_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(build_release, "ROOT", tmp_path)
    with pytest.raises(SystemExit, match="missing"):
        build_release.require_release_clearance([])
    gate = tmp_path / "license-audit/release-gate.json"
    gate.parent.mkdir()
    gate.write_text(json.dumps({"release_status": "BLOCKED", "blockers": ["unknown"]}))
    with pytest.raises(SystemExit, match="BLOCKED"):
        build_release.require_release_clearance([])


def test_release_gate_rejects_changed_or_added_input(tmp_path, monkeypatch):
    import subprocess

    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    monkeypatch.setattr(build_release, "ROOT", tmp_path)
    source = tmp_path / "cli.py"
    source.write_text("original")
    gate = tmp_path / "license-audit/release-gate.json"
    gate.parent.mkdir()
    gate.write_text(
        json.dumps(
            {
                "release_status": "READY FOR RELEASE",
                "scope": "github-repository-clone",
                "blockers": [],
                "input_hashes": {"cli.py": build_release.sha256(source)},
            }
        )
    )
    build_release.require_release_clearance([source, gate])
    source.write_text("changed")
    with pytest.raises(SystemExit, match="stale"):
        build_release.require_release_clearance([source, gate])
    source.write_text("original")
    added = tmp_path / "new-source.py"
    added.write_text("pass")
    with pytest.raises(SystemExit, match="stale"):
        build_release.require_release_clearance([source, gate, added])


def test_collector_rejects_inactive_vendor_chunks(tmp_path, monkeypatch):
    import subprocess

    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    monkeypatch.setattr(build_release, "ROOT", tmp_path)
    vendor = tmp_path / "vendor/windows-x64"
    vendor.mkdir(parents=True)
    active = vendor / "browser-current.chunk"
    inactive = vendor / "browser-original.chunk"
    active.write_bytes(b"current")
    inactive.write_bytes(b"old ffmpeg payload")
    (vendor / "manifest.json").write_text(
        json.dumps({"assets": {"browser": {"parts": [{"file": active.name}]}}})
    )
    with pytest.raises(SystemExit, match="inactive"):
        build_release.collect()
    inactive.unlink()
    assert active in build_release.collect()


def test_collector_excludes_local_receipts_and_private_sidecars(tmp_path, monkeypatch):
    import subprocess

    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    monkeypatch.setattr(build_release, "ROOT", tmp_path)
    paths = [
        "tools/custom.sqlite3-wal",
        "tools/private.har",
        "tools/.env.private",
        "tools/export.csv",
        "license-audit/creation-session-evidence.json",
    ]
    (tmp_path / ".gitignore").write_text("\n".join(paths) + "\n")
    for name in [*paths, "tools/check.py", "license-audit/pathspec-source.json"]:
        path = tmp_path / name
        path.parent.mkdir(exist_ok=True)
        path.write_text("synthetic")
    collected = {path.relative_to(tmp_path).as_posix() for path in build_release.collect()}
    assert collected == {".gitignore", "tools/check.py", "license-audit/pathspec-source.json"}


def test_collector_rejects_paths_that_leave_no_room_for_checkout_root(tmp_path):
    import subprocess

    from tools.repository_files import collect

    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    directory = tmp_path / ("a" * 80)
    directory.mkdir()
    boundary = directory / ("b" * 99)
    boundary.write_bytes(b"notice")
    assert boundary in collect(tmp_path)
    boundary.unlink()
    (directory / ("b" * 100)).write_bytes(b"notice")
    with pytest.raises(SystemExit, match=r"path.*long"):
        collect(tmp_path)
