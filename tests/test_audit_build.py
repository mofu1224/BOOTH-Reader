"""The retired archive command must leave existing output and user data intact."""

import pytest

from tools import build_release


def test_a10_existing_output_is_preserved(tmp_path):
    output = tmp_path / "valuable"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("original", encoding="utf-8")
    with pytest.raises(SystemExit):
        build_release.main(["--out", str(output), "--skip-python-build"])
    assert sentinel.read_text(encoding="utf-8") == "original"


def test_archive_command_creates_no_output(tmp_path):
    output = tmp_path / "new-output"
    with pytest.raises(SystemExit, match="retired"):
        build_release.main(["--out", str(output), "--offline-bundle", "--audit-candidate"])
    assert not output.exists()
