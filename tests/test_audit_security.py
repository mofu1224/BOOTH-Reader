"""Fail-closed secret persistence and local Web trust boundaries."""

import logging
import sys

import pytest
from fastapi.testclient import TestClient

import cli
from core import auth
from core.errors import BoothAuthError, BoothNetworkError
from core.logging_setup import SecretRedactingFilter, redact
from web import app as web_app


def test_a12_cookie_lockdown_failure_preserves_previous_jar(tmp_path, monkeypatch):
    path = tmp_path / "ck.json"
    path.write_text('[{"name":"a","value":"old"}]', encoding="utf-8")
    monkeypatch.setattr(auth, "restrict_permissions", lambda p: False)
    with pytest.raises(BoothAuthError):
        auth.save_cookies([{"name": "a", "value": "new"}], path)
    assert '"old"' in path.read_text(encoding="utf-8")
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.skipif(sys.platform != "win32", reason="Windows ACL inheritance")
def test_a12_failed_acl_grant_never_removes_inheritance(tmp_path, monkeypatch):
    calls = []
    path = tmp_path / "ck.json"
    path.write_bytes(b"empty")
    monkeypatch.setattr(auth, "current_account", lambda: "fake")
    monkeypatch.setattr(auth, "icacls", lambda p, *args: calls.append(args) or False)
    assert auth.restrict_permissions(path) is False
    assert all("/inheritance:r" not in call for call in calls)


def test_a12_errors_and_tracebacks_redact_signed_urls(tmp_path, monkeypatch, capsys):
    text = "https://booth.pm/file?X-Amz-Signature=fake-signature&Policy=fake-policy"
    assert "fake-signature" not in redact(text)
    record = logging.LogRecord("x", logging.ERROR, "f", 1, "failed", (), None)
    try:
        raise RuntimeError("password=fake-password")
    except RuntimeError:
        import sys

        record.exc_info = sys.exc_info()
    SecretRedactingFilter().filter(record)
    assert "fake-password" not in logging.Formatter().format(record)

    def fail(*args):
        raise BoothNetworkError(text)

    monkeypatch.setattr(cli, "_cmd_init_db", fail)
    assert cli.main(["--db", str(tmp_path / "none.db"), "init-db"]) == 1
    assert "fake-signature" not in capsys.readouterr().err


def test_a12_origin_scheme_and_fetch_site_guard(db, tmp_path):
    with TestClient(web_app.create_app(db, tmp_path / "lib")) as client:
        for headers in ({"Origin": "https://testserver"}, {"Sec-Fetch-Site": "cross-site"}):
            assert (
                client.post(
                    "/lists", json={"action": "create", "name": "bad"}, headers=headers
                ).status_code
                == 403
            )


def test_a12_non_loopback_bind_is_rejected_before_side_effects(tmp_path, monkeypatch):
    import uvicorn

    calls = []
    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: None)
    monkeypatch.setattr(web_app.bridge, "run_cli_once", lambda *a, **k: calls.append(a))
    with pytest.raises(ValueError):
        web_app.run(host="0.0.0.0", db_path=str(tmp_path / "none.db"))
    assert calls == []
