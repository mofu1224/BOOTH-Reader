"""Portable-layout tests: the repo must work from any folder it is copied to.

These tests pin the guarantees PORTABLE.md makes:

* default data paths resolve inside the repository
* the portable environment defaults point inside the repository and never
  override an explicit user setting
* the launchers keep everything repo-local without touching machine state
* ``doctor`` reports the portable checks so a moved folder is diagnosable
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def test_repo_root_found_from_nested_start():
    from core.portable import repo_root

    assert repo_root(BASE / "core" / "auth.py") == BASE
    assert repo_root(BASE / "tools" / "portable.py") == BASE


def test_portable_env_defaults_stay_inside_repo():
    from core.portable import portable_env

    env = portable_env(BASE)
    for key in (
        "PLAYWRIGHT_BROWSERS_PATH",
        "PIP_CACHE_DIR",
        "UV_CACHE_DIR",
        "RUFF_CACHE_DIR",
        "MYPY_CACHE_DIR",
    ):
        assert Path(env[key]).resolve().is_relative_to(BASE.resolve()), key


def test_browser_env_keeps_every_writable_location_inside_repo(monkeypatch, tmp_path):
    from core.browser import browser_env

    # An inherited (or deliberately broken) profile must not reach the browser
    # child: WebView2 writes crashpad/user data through these variables.
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "outside"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "outside-local"))
    env = browser_env()
    for key in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP"):
        assert Path(env[key]).resolve().is_relative_to(BASE.resolve()), key
    for key in ("HOME", "APPDATA", "LOCALAPPDATA", "TEMP"):
        assert Path(env[key]).is_dir(), key


def test_apply_portable_env_respects_explicit_settings(monkeypatch, tmp_path):
    from core.portable import apply_portable_env

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path / "custom"))
    monkeypatch.delenv("PIP_CACHE_DIR", raising=False)
    applied = apply_portable_env(BASE)
    assert Path(os.environ["PLAYWRIGHT_BROWSERS_PATH"]).resolve() == tmp_path / "custom"
    assert "PLAYWRIGHT_BROWSERS_PATH" not in applied
    assert Path(os.environ["PIP_CACHE_DIR"]).resolve().is_relative_to(BASE.resolve())


def test_effective_browsers_path_prefers_env(monkeypatch, tmp_path):
    from core.portable import browsers_path, effective_browsers_path

    monkeypatch.delenv("PLAYWRIGHT_BROWSERS_PATH", raising=False)
    assert effective_browsers_path(BASE) == browsers_path(BASE)
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path))
    assert effective_browsers_path(BASE) == tmp_path


def test_default_data_paths_are_repo_local():
    import cli as cli_mod
    from core.auth import DEFAULT_COOKIE_PATH

    for value in (cli_mod.DEFAULT_DB, cli_mod.DEFAULT_LIBRARY, str(DEFAULT_COOKIE_PATH)):
        assert Path(value).resolve().is_relative_to(BASE.resolve()), value


def test_venv_health_reports_current_repo():
    import pytest

    from tools.portable import venv_health, venv_python

    if not venv_python(BASE).is_file():
        pytest.skip("no .venv in this checkout (source bundle); nothing to check")
    ok, reason = venv_health(BASE)
    assert ok, reason


def test_candidate_pythons_prefers_bundled(tmp_path):
    from tools.portable import candidate_pythons, tools_python

    bundled = tmp_path / ".tools" / "python" / "python.exe"
    bundled.parent.mkdir(parents=True)
    bundled.write_bytes(b"")
    first = candidate_pythons(tmp_path)[0]
    assert first == [str(tools_python(tmp_path))]


def test_launchers_stay_portable():
    for name in ("setup.bat", "cli.bat", "start-web.bat", "run.cmd"):
        text = (BASE / name).read_text(encoding="utf-8", errors="replace")
        lowered = text.lower()
        assert "PLAYWRIGHT_BROWSERS_PATH" in text, name
        assert "%~dp0" in text, name  # repo-relative, never an absolute path
        assert "setx" not in lowered, name
        assert "reg add" not in lowered, name
        assert "c:\\users" not in lowered, name
        assert "appdata\\local\\ms-playwright" not in lowered, name


def test_generic_entry_points_exist():
    # Clone-to-Run generic naming: run.cmd / run.ps1 delegate to the same
    # verified bootstrap; run.sh is a Windows-only stub with a clear message.
    run_cmd = (BASE / "run.cmd").read_text(encoding="utf-8", errors="replace")
    assert "bootstrap.ps1" in run_cmd and "-Mode web" in run_cmd
    run_ps1 = (BASE / "run.ps1").read_text(encoding="utf-8", errors="replace")
    assert "bootstrap.ps1" in run_ps1 and "PLAYWRIGHT_BROWSERS_PATH" in run_ps1
    assert "SystemRoot" in run_ps1  # OS-standard PowerShell, never a hardcoded drive
    run_sh = (BASE / "run.sh").read_text(encoding="utf-8", errors="replace")
    assert "Windows x64 only" in run_sh


def test_setup_bat_supports_repair_and_browser_skip():
    text = (BASE / "setup.bat").read_text(encoding="utf-8", errors="replace")
    assert "--repair" in text
    assert "bootstrap.ps1" in text
    manager = (BASE / "tools/manage_portable.py").read_text(encoding="utf-8")
    assert "ensure_browser(python, offline=True" in manager


def test_bat_blocks_contain_no_stray_parens():
    """A ``)`` inside a parenthesised block ends the block early in cmd.exe.

    The launchers use Allman-style blocks, so depth is tracked by lines
    ending in ``(`` / exactly ``)`` / ``) else (``. An ``echo`` or ``rem``
    line inside a block must not contain parentheses of its own.
    """
    for name in ("setup.bat", "cli.bat", "start-web.bat", "run.cmd"):
        lines = (BASE / name).read_text(encoding="utf-8", errors="replace").splitlines()
        depth = 0
        for lineno, raw in enumerate(lines, 1):
            line = raw.strip().lower()
            if depth > 0 and (line.startswith("echo ") or line.startswith("rem ")):
                assert "(" not in raw and ")" not in raw, f"{name}:{lineno}: {raw}"
            # ") else (" closes one block and opens another: net zero.
            if line.startswith(")"):
                depth -= 1
            if line.endswith("("):
                depth += 1
            assert depth >= 0, f"{name}:{lineno}: unbalanced blocks"


def test_tool_caches_configured_inside_repo():
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib

    config = tomllib.loads((BASE / "pyproject.toml").read_text(encoding="utf-8"))
    pytest_cache = config["tool"]["pytest"]["ini_options"]["cache_dir"]
    assert str(pytest_cache).startswith(".cache"), pytest_cache
    ruff_cache = config["tool"]["ruff"]["cache-dir"]
    assert str(ruff_cache).startswith(".cache"), ruff_cache
    mypy_cache = config["tool"]["mypy"]["cache_dir"]
    assert str(mypy_cache).startswith(".cache"), mypy_cache


def test_gitignore_covers_portable_runtime():
    ignored = (BASE / ".gitignore").read_text(encoding="utf-8")
    for entry in (".cache/", ".playwright-browsers/", ".tools/"):
        assert entry in ignored, entry


def test_web_defaults_are_repo_local():
    from web.app import DEFAULT_DB_PATH, DEFAULT_LIBRARY_ROOT

    assert Path(DEFAULT_DB_PATH).resolve().is_relative_to(BASE.resolve())
    assert Path(DEFAULT_LIBRARY_ROOT).resolve().is_relative_to(BASE.resolve())


def test_venv_base_lives_inside_repo_when_bundled():
    import pytest

    from tools.portable import tools_python, venv_base_home, venv_python

    if not venv_python(BASE).is_file():
        pytest.skip("no .venv in this checkout (source bundle); nothing to check")
    if not tools_python(BASE).is_file():
        pytest.skip("no bundled python in this checkout; base check is not actionable")
    home = venv_base_home(BASE)
    assert home is not None
    assert home.resolve().is_relative_to(BASE.resolve()), home


def test_fetch_python_scratch_stays_inside_repo():
    text = (BASE / "tools" / "fetch_python.py").read_text(encoding="utf-8")
    assert ".cache" in text
    assert 'tempfile.mkdtemp(prefix="booth-python-")' not in text


def test_doctor_reports_portable_checks(tmp_path):
    import contextlib
    import io
    import json

    import cli as cli_mod
    from core.db import init_db

    db = init_db(tmp_path / "portable.db")
    ns = cli_mod.build_parser().parse_args(
        ["doctor", "--db", str(db), "--library", str(tmp_path / "lib"), "--json"]
    )
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cli_mod._cmd_doctor(ns, str(db))
    payload = json.loads(buf.getvalue())
    names = {c["name"]: c for c in payload["checks"]}
    assert "portable:venv" in names
    assert "portable:browsers" in names
    # Informational only: a system-wide install must still report healthy.
    assert names["portable:venv"]["fatal"] is False
    assert names["portable:browsers"]["fatal"] is False
    # rc follows the fatal checks only (browser may be absent in a bundle).
    assert rc == (0 if payload["ok"] else 1)
    assert sys.executable  # the check reports the running interpreter, whatever it is
