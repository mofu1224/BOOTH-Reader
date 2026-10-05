"""Missing or changed notice/source originals must fail independently of metadata."""

import hashlib
import json
from pathlib import Path

import pytest

from tools import check_license_evidence, license_compliance


@pytest.mark.parametrize("leaf", ["LICENSE-APACHE", "LICENSE-MIT", "jemalloc/COPYING"])
def test_long_crate_notice_keeps_original_with_copyable_path(tmp_path, monkeypatch, leaf):
    monkeypatch.setattr(license_compliance, "ROOT", tmp_path)
    monkeypatch.setattr(license_compliance, "LICENSES", tmp_path / "THIRD_PARTY_LICENSES")
    version = "0.6.1+5.3.0-1-ge13ca993e8ccb9ba9847cc330696e02839f328f7"
    original = f"tikv-jemalloc-sys-{version}/{leaf}"
    data = b"Unmodified upstream license text\n"
    notice = license_compliance.retain(
        "rust-tikv-jemalloc-sys-" + version, original, data, "upstream"
    )
    # Leave room for a checkout root of 78 UTF-16 units and its separator.
    assert len(notice["path"].encode("utf-16-le")) // 2 <= 180
    assert notice["original_path"] == original
    assert notice["source"] == "upstream"
    assert notice["sha256"] == hashlib.sha256(data).hexdigest()
    assert (tmp_path / notice["path"]).read_bytes() == data


def test_shipped_crate_notices_are_short_and_match_retained_source():
    import tarfile

    root = Path(__file__).resolve().parent.parent
    evidence = json.loads(
        (root / "license-audit/native-source-evidence.json").read_text(encoding="utf-8")
    )
    crate = next(
        row for row in evidence["locked_rust_dependencies"] if row["name"] == "tikv-jemalloc-sys"
    )
    with tarfile.open(root / crate["source"]) as archive:
        for notice in crate["notices"]:
            assert len(notice["path"].encode("utf-16-le")) // 2 <= 180
            stream = archive.extractfile(notice["original_path"])
            assert stream is not None
            assert (root / notice["path"]).read_bytes() == stream.read()


def test_changed_notice_and_missing_source_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(check_license_evidence, "EVIDENCE", ("evidence.json",))
    original = b"synthetic notice"
    digest = hashlib.sha256(original).hexdigest()
    notices = tmp_path / "THIRD_PARTY_LICENSES"
    notices.mkdir()
    notice = notices / f"{digest[:12]}-LICENSE"
    notice.write_bytes(original)
    sources = tmp_path / "SOURCE_OBLIGATIONS"
    sources.mkdir()
    source = sources / "source.tar.gz"
    source.write_bytes(b"synthetic source")
    evidence = tmp_path / "license-audit"
    evidence.mkdir()
    rows = [
        {"path": notice.relative_to(tmp_path).as_posix(), "sha256": digest},
        {
            "source": source.relative_to(tmp_path).as_posix(),
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        },
    ]
    (evidence / "evidence.json").write_text(json.dumps(rows))
    assert check_license_evidence.inspect(tmp_path)["ok"]
    notice.write_bytes(b"modified")
    source.unlink()
    report = check_license_evidence.inspect(tmp_path)
    assert not report["ok"]
    assert len(report["failures"]) == 2
