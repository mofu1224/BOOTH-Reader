"""Git-owned materials must reconstruct locally and fail closed on tampering."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from core.platforms import target_id
from tools.vendor_payload import materialize


def fixture_payload(root: Path, destination: str = ".cache/downloads/python.tar.gz") -> Path:
    vendor = root / "vendor" / target_id()
    vendor.mkdir(parents=True)
    chunks = [b"first half", b"second half"]
    parts = []
    for i, data in enumerate(chunks):
        name = f"python-{i}.chunk"
        (vendor / name).write_bytes(data)
        parts.append({"file": name, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)})
    whole = b"".join(chunks)
    manifest = {
        "assets": {
            "python": {
                "destination": destination,
                "sha256": hashlib.sha256(whole).hexdigest(),
                "size": len(whole),
                "parts": parts,
            }
        }
    }
    (vendor / "manifest.json").write_text(json.dumps(manifest))
    return vendor


def test_payload_reconstructs_without_any_external_source(tmp_path):
    fixture_payload(tmp_path)
    result = materialize("python", tmp_path)
    assert result.read_bytes() == b"first halfsecond half"
    assert result.is_relative_to(tmp_path)
    assert list((tmp_path / ".cache/tmp").iterdir()) == []


def test_corrupt_chunk_preserves_previous_cache_asset(tmp_path):
    vendor = fixture_payload(tmp_path)
    target = tmp_path / ".cache/downloads/python.tar.gz"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"previous cache")
    (vendor / "python-1.chunk").write_bytes(b"tampered")
    with pytest.raises(RuntimeError, match="hash mismatch"):
        materialize("python", tmp_path)
    assert target.read_bytes() == b"previous cache"
    assert list((tmp_path / ".cache/tmp").iterdir()) == []


def test_vendor_destination_cannot_write_outside_repository(tmp_path):
    fixture_payload(tmp_path, "../outside.bin")
    with pytest.raises(RuntimeError, match="escapes"):
        materialize("python", tmp_path)
    assert not (tmp_path.parent / "outside.bin").exists()


def test_chunk_path_cannot_reference_external_material(tmp_path):
    vendor = fixture_payload(tmp_path)
    path = vendor / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["assets"]["python"]["parts"][0]["file"] = "../../foreign.chunk"
    path.write_text(json.dumps(manifest))
    with pytest.raises(RuntimeError, match="escapes"):
        materialize("python", tmp_path)


def test_git_payload_has_no_lfs_or_oversized_blob_requirement():
    root = Path(__file__).resolve().parent.parent
    manifest = json.loads((root / "vendor/windows-x64/manifest.json").read_text())
    for spec in manifest["assets"].values():
        for part in spec["parts"]:
            path = root / "vendor/windows-x64" / part["file"]
            assert 0 < path.stat().st_size <= 40 * 1024 * 1024
            with path.open("rb") as stream:
                assert not stream.read(100).startswith(b"version https://git-lfs")
