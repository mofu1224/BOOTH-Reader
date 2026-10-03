"""Regression tests for the prerequisite-versus-authentication error split.

Background: `auth login` originally reported a missing Playwright as
``BoothAuthError``, which produced::

    ERROR BOOTHへのログインが必要です。`python cli.py auth login` で
    再ログインしてください。 Playwrightが未導入です。

-- telling the user to re-run the command they had just run, while burying the
actual cause. A missing component is not an authentication problem and must
never be reported as one.
"""

from __future__ import annotations

import builtins
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from core.auth import login
from core.db import init_db
from core.errors import (
    BoothAuthError,
    BoothError,
    BoothNetworkError,
    BoothPrerequisiteError,
    exit_code_for,
)

BASE = Path(__file__).resolve().parent.parent


def _block(*modules: str):
    """Return an __import__ replacement that hides the given modules."""

    real_import = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name in modules or name.split(".")[0] in modules:
            raise ImportError(f"No module named {name!r}")
        return real_import(name, *args, **kwargs)

    return guarded


# --- the taxonomy itself ----------------------------------------------------


def test_prerequisite_is_not_an_auth_error():
    assert issubclass(BoothPrerequisiteError, BoothError)
    assert not issubclass(BoothPrerequisiteError, BoothAuthError)
    assert BoothPrerequisiteError.CODE == "BOOTH_PREREQUISITE_MISSING"
    assert exit_code_for(BoothPrerequisiteError("x", "y")) == 1


def test_prerequisite_message_names_component_and_remedy():
    err = BoothPrerequisiteError("httpx が未導入です", "`setup.bat --repair`")
    message = str(err)
    assert "httpx" in message
    assert "setup.bat --repair" in message


def test_auth_error_still_keeps_its_relogin_hint():
    """The legitimate auth message must not be weakened by the split."""
    message = str(BoothAuthError("購入一覧の取得に失敗しました。"))
    assert "auth login" in message
    assert "再ログイン" in message


# --- missing Playwright -----------------------------------------------------


def test_login_without_playwright_reports_a_prerequisite(monkeypatch, tmp_path):
    monkeypatch.setattr(builtins, "__import__", _block("playwright"))
    with pytest.raises(BoothPrerequisiteError) as exc:
        login(path=tmp_path / "ck.json", timeout_s=30)
    message = str(exc.value)
    # Names the component and the exact command.
    assert "Playwright" in message
    assert "setup.bat --repair" in message
    # The regression: it must NOT tell the user to log in again.
    assert "auth login" not in message
    assert "再ログイン" not in message
    assert "ログインが必要" not in message


def test_login_playwright_message_has_no_contradiction(monkeypatch, tmp_path):
    """No error may instruct the user to run the command that just failed."""
    monkeypatch.setattr(builtins, "__import__", _block("playwright"))
    try:
        login(path=tmp_path / "ck.json", timeout_s=30)
    except BoothError as e:
        assert "cli.py auth login" not in str(e)


# --- missing HTTP / HTML dependencies ---------------------------------------


def test_missing_httpx_reports_a_prerequisite(monkeypatch):
    from core import net

    monkeypatch.setattr(net, "_httpx", None)
    with pytest.raises(BoothPrerequisiteError) as exc:
        net.request("https://example.invalid/", timeout=1)
    assert "httpx" in str(exc.value)
    assert "auth login" not in str(exc.value)


@pytest.mark.parametrize(
    ("module", "needle"),
    [("bs4", "beautifulsoup4")],
)
def test_missing_bs4_reports_a_prerequisite(monkeypatch, module, needle):
    from core.purchases import parse_library_html

    monkeypatch.setattr(builtins, "__import__", _block(module))
    with pytest.raises(BoothPrerequisiteError) as exc:
        parse_library_html("<a href='/orders/1'>x</a>")
    assert needle in str(exc.value)
    assert "auth login" not in str(exc.value)


def test_missing_httpx_is_not_reported_as_a_network_error():
    """A missing package is not a network fault; the codes must differ."""
    assert BoothNetworkError.CODE != BoothPrerequisiteError.CODE
    assert BoothAuthError.CODE != BoothPrerequisiteError.CODE


# --- end-to-end: the CLI surface -------------------------------------------


def _run_cli(*args: str):
    """Invoke the CLI with an exact argv, as a user would type it."""
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    return subprocess.run(
        [sys.executable, str(BASE / "cli.py"), *args],
        capture_output=True,
        text=True,
        timeout=300,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )


def test_cli_auth_status_without_cookies_is_an_auth_error(tmp_path):
    proc = _run_cli(
        "--db",
        str(init_db(tmp_path / "a.db")),
        "auth",
        "status",
        "--cookie-path",
        str(tmp_path / "absent.json"),
    )
    assert proc.returncode == 1
    assert "auth login" in proc.stderr
    assert "Traceback" not in proc.stderr


def _doctor(*argv: str) -> tuple[int, dict]:
    """Run doctor in-process and return (exit code, parsed payload)."""
    import argparse
    import contextlib
    import io

    import cli as cli_mod

    ns = argparse.Namespace(db=None, library=None, json=True)
    parser = cli_mod.build_parser()
    parsed = parser.parse_args(["doctor", "--json", *argv])
    ns.db = parsed.db
    ns.library = parsed.library
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cli_mod._cmd_doctor(ns, ns.db)
    return rc, json.loads(buf.getvalue())


def test_doctor_reports_playwright_and_the_browser(tmp_path):
    rc, payload = _doctor(
        "--db", str(init_db(tmp_path / "d.db")), "--library", str(tmp_path / "lib")
    )
    names = {c["name"]: c for c in payload["checks"]}
    assert "dep:playwright" in names
    assert "browser:webview2" in names
    assert rc == 0, [c for c in payload["checks"] if not c["ok"]]


def test_doctor_treats_a_missing_browser_as_fatal(tmp_path, monkeypatch):
    """Hiding Playwright must fail fatally, not merely warn.

    A browser that is not installed means the user cannot log in at all, which
    is exactly the case `doctor` exists to catch before they hit it.
    """
    monkeypatch.setattr(builtins, "__import__", _block("playwright"))
    rc, payload = _doctor(
        "--db", str(init_db(tmp_path / "d.db")), "--library", str(tmp_path / "lib")
    )
    names = {c["name"]: c for c in payload["checks"]}
    assert names["dep:playwright"]["ok"] is False
    assert names["dep:playwright"]["fatal"] is True
    assert names["browser:webview2"]["ok"] is False
    assert names["browser:webview2"]["fatal"] is True
    assert "playwright" in names["browser:webview2"]["detail"]
    assert payload["ok"] is False
    assert rc == 1


def test_setup_bat_installs_the_browser():
    """The browser download is the one step a package install cannot do."""
    text = (BASE / "setup.bat").read_text(encoding="utf-8", errors="replace")
    manager = (BASE / "tools/manage_portable.py").read_text(encoding="utf-8")
    manifest = (BASE / "portable-manifest.json").read_text(encoding="utf-8")
    assert "bootstrap.ps1" in text
    assert "ensure_browser(python, offline=True" in manager
    assert 'materialize("browser", ROOT)' in manager
    assert "requirements-portable-lock.txt" in manifest
