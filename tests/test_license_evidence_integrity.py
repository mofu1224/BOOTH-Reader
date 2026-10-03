"""Missing or changed notice/source originals must fail independently of metadata."""

import hashlib
import json

from tools import check_license_evidence


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
