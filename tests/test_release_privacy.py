"""Privacy regressions at log and HTTP boundaries (synthetic secrets only)."""

import logging

from fastapi.testclient import TestClient

from core.logging_setup import SecretRedactingFilter, redact
from tools.check_release_hygiene import private_path
from web.app import create_app


def test_cookie_header_redacts_every_cookie():
    text = "Cookie: first=synthetic-first; second=synthetic-second"
    safe = redact(text)
    assert "synthetic-first" not in safe
    assert "synthetic-second" not in safe


def test_multiline_header_retains_nonsecret_diagnostics():
    safe = redact("Cookie: first=synthetic-first; second=synthetic-second\nHTTP status=403")
    assert "synthetic-" not in safe
    assert "HTTP status=403" in safe


def test_validation_response_does_not_echo_cookie_or_extra_input(tmp_path):
    app = create_app(tmp_path / "test.db", tmp_path / "library")
    with TestClient(app) as client:
        response = client.post(
            "/auth/import", json={"content": {"session": "synthetic-private-session"}}
        )
        assert response.status_code == 422
        assert "synthetic-private-session" not in response.text
        assert "input" not in response.json()["detail"][0]


def test_validation_logs_do_not_receive_raw_body(tmp_path, caplog):
    app = create_app(tmp_path / "test.db", tmp_path / "library")
    with TestClient(app) as client, caplog.at_level(logging.DEBUG):
        client.post("/auth/import", json={"content": {"value": "synthetic-private-session"}})
    assert "synthetic-private-session" not in caplog.text


def test_exception_cookie_header_is_redacted():
    try:
        raise ValueError("Cookie: a=synthetic-first; b=synthetic-second")
    except ValueError:
        import sys

        record = logging.LogRecord(
            "privacy", logging.ERROR, __file__, 1, "failed", (), sys.exc_info()
        )
    assert SecretRedactingFilter().filter(record)
    assert "synthetic-first" not in record.exc_text
    assert "synthetic-second" not in record.exc_text


def test_private_headers_cover_success_and_validation_errors(tmp_path):
    with TestClient(create_app(tmp_path / "test.db", tmp_path / "library")) as client:
        for response in (client.get("/health"), client.post("/auth/import", json={})):
            assert response.headers["cache-control"] == "no-store"
            assert response.headers["referrer-policy"] == "no-referrer"


def test_git_private_path_rules_do_not_exclude_license_sources():
    for path in (
        "data/cookies.json",
        "backup.sqlite3-wal",
        "custom.db-journal",
        "cookies-export.json",
        ".cache/home/Desktop/import.json",
        "BOOTH-Reader-Library/private.png",
        "audit/reaudit-ui.png",
        "license-audit/creation-session-evidence.json",
        ".private/import.json",
        "my-Cookies-export.json",
        "browser-storage-state.json",
        "backups/history.db.bak",
    ):
        assert private_path(path), path
    for path in (
        "core/db.py",
        "SOURCE_OBLIGATIONS/pathspec-1.1.1.tar.gz",
        "license-audit/pathspec-source.json",
    ):
        assert not private_path(path), path


def test_real_git_ignore_rules_cover_private_imports_and_backups():
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    paths = [
        "app.db",
        "data/cookies.json",
        "BOOTH-Reader-Library/synthetic.txt",
        ".cache/browser-profile/synthetic.json",
        ".private/arbitrary-import.json",
        "My-Cookies-export.json",
        "browser-storage-state.json",
        "custom.db-wal",
        "history.sqlite3.bak",
        "custom.db.backup",
        "backups/arbitrary.json",
    ]
    process = subprocess.run(
        ["git", "-C", str(root), "check-ignore", "--no-index", "--stdin", "-z"],
        input="\0".join(paths).encode() + b"\0",
        capture_output=True,
        check=True,
    )
    assert set(process.stdout.decode().rstrip("\0").split("\0")) == set(paths)


def test_expected_http_error_redacts_cookie_and_signed_url():
    from web import cli_bridge
    from web.app import _err_payload

    exc = cli_bridge.CliAuthError("Cookie: session=synthetic-private-session")
    status, body = _err_payload(exc)
    assert status == 401
    assert "synthetic-private-session" not in str(body)
    _, body = _err_payload(
        cli_bridge.CliBridgeError("https://example.invalid/file?key=synthetic-signed-url")
    )
    assert "synthetic-signed-url" not in str(body)


def test_unexpected_http_error_does_not_echo_arbitrary_input():
    from web.app import _err_payload

    status, body = _err_payload(ValueError("arbitrary-synthetic-sensitive-body"))
    assert status == 500
    assert "arbitrary-synthetic-sensitive-body" not in str(body)


def test_background_failure_redacts_health_state(tmp_path, monkeypatch):
    from web import cli_bridge

    monkeypatch.setattr(cli_bridge, "get_auth_status", lambda *a: {"ok": True})

    def fail(*a, **k):
        raise cli_bridge.CliBridgeError("Cookie: session=synthetic-background-secret")

    monkeypatch.setattr(cli_bridge, "run_download_blocking", fail)
    with TestClient(create_app(tmp_path / "test.db", tmp_path / "library")) as client:
        assert client.post("/download", json={"item_id": "123"}).status_code == 200
        state = client.get("/health").json()["download"]
        assert state["ok"] is False
        assert state["running"] is False
        assert "synthetic-background-secret" not in str(state)


def test_third_party_terms_include_originals_and_data_notice(tmp_path):
    with TestClient(create_app(tmp_path / "test.db", tmp_path / "library")) as client:
        response = client.get("/third-party-terms")
        assert response.status_code == 200
        assert "SmartScreen" in response.text
        assert "DISTRIBUTABLE CODE" in response.text
        assert "Additional Conditions for this Windows binary build" in response.text
        assert response.headers["cache-control"] == "no-store"
