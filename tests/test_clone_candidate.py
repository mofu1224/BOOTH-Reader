"""The clone candidate must match Git, including files omitted by old ZIP lists."""

import subprocess

import pytest

from tools.repository_files import collect


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=True)


def test_candidate_includes_every_tracked_and_eligible_file_but_no_ignored_data(tmp_path):
    git(tmp_path, "init")
    (tmp_path / ".gitignore").write_text(".private/\n*.db\n")
    audit = tmp_path / "license-audit"
    audit.mkdir()
    retained = audit / "24-current-final-verification.md"
    retained.write_text("retained audit")
    git(tmp_path, "add", ".gitignore", "license-audit")
    (tmp_path / "new-source.py").write_text("pass")
    (tmp_path / "app.db").write_bytes(b"synthetic private data")
    private = tmp_path / ".private"
    private.mkdir()
    (private / "import.json").write_text("synthetic")
    assert {path.relative_to(tmp_path).as_posix() for path in collect(tmp_path)} == {
        ".gitignore",
        "license-audit/24-current-final-verification.md",
        "new-source.py",
    }


def test_tracked_private_file_is_rejected_even_when_ignored(tmp_path):
    git(tmp_path, "init")
    (tmp_path / "app.db").write_bytes(b"synthetic")
    git(tmp_path, "add", "app.db")
    (tmp_path / ".gitignore").write_text("*.db\n")
    with pytest.raises(SystemExit, match="private"):
        collect(tmp_path)


def test_candidate_preserves_deletions_and_does_not_touch_index(tmp_path):
    git(tmp_path, "init")
    source = tmp_path / "deleted.py"
    source.write_text("pass")
    git(tmp_path, "add", "deleted.py")
    index = (tmp_path / ".git/index").read_bytes()
    source.unlink()
    assert collect(tmp_path) == []
    assert (tmp_path / ".git/index").read_bytes() == index


def test_gate_hashes_survive_git_line_endings_without_altering_upstream(tmp_path):
    import hashlib

    from tools.repository_files import input_hashes

    git(tmp_path, "init")
    (tmp_path / ".gitattributes").write_text(
        "*.py text eol=lf\n*.bat text eol=crlf\nTHIRD_PARTY_LICENSES/** -text\n"
    )
    script = tmp_path / "script.py"
    launcher = tmp_path / "run.bat"
    notice = tmp_path / "THIRD_PARTY_LICENSES" / "LICENSE.txt"
    notice.parent.mkdir()
    script.write_bytes(b"pass\r\n")
    launcher.write_bytes(b"@echo off\n")
    notice.write_bytes(b"verbatim upstream\r\n")
    files = [script, launcher, notice]
    hashes = input_hashes(files, tmp_path)
    assert hashes["script.py"] == hashlib.sha256(b"pass\n").hexdigest()
    assert (
        hashes["THIRD_PARTY_LICENSES/LICENSE.txt"]
        == hashlib.sha256(notice.read_bytes()).hexdigest()
    )
    script.write_bytes(b"pass\n")
    launcher.write_bytes(b"@echo off\r\n")
    assert input_hashes(files, tmp_path) == hashes
    notice.write_bytes(b"verbatim upstream\n")
    assert input_hashes(files, tmp_path) != hashes
