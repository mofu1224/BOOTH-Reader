"""Windows PowerShell must not consume CLI --db as its common -Debug alias."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def run_launcher(args):
    if sys.platform == "darwin":
        return subprocess.run(
            ["/bin/bash", str(ROOT / "start.sh"), "cli", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=180,
            check=False,
        )
    cmd = Path(os.environ["SYSTEMROOT"]) / "System32/cmd.exe"
    inner = subprocess.list2cmdline([str(ROOT / "start.bat"), "cli", *args])
    return subprocess.run(
        f'"{cmd}" /d /s /c "{inner}"',
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        check=False,
    )


@pytest.mark.parametrize("db_before", [False, True])
def test_cli_launcher_preserves_db_option_and_space_path(tmp_path, db_before):
    target = tmp_path / "日本語 space.db"
    args = ["--db", str(target), "init-db"] if db_before else ["init-db", "--db", str(target)]
    result = run_launcher(args)
    assert result.returncode == 0, result.stderr
    assert target.is_file()
    query = run_launcher(["--db", str(target), "lists", "list", "--json"])
    assert query.returncode == 0, query.stderr
    assert json.loads(query.stdout) == {"count": 0, "lists": []}
