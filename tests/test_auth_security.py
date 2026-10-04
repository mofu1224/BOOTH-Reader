"""Auth, secret-handling and redaction tests. No network, no browser."""

from __future__ import annotations

import logging
import time

import pytest

from core.auth import (
    BoothAuthError,
    cookies_to_jar,
    has_cookies,
    load_cookies,
    logout,
    restrict_permissions,
    save_cookies,
    status,
)
from core.logging_setup import SecretRedactingFilter, redact

# ---------------------------------------------------------------------------
# Cookie storage
# ---------------------------------------------------------------------------


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "ck.json"
    jar = [
        {"name": "a", "value": "1", "domain": ".booth.pm"},
        {"name": "b", "value": "2", "domain": "accounts.booth.pm"},
    ]
    save_cookies(jar, path)
    assert load_cookies(path) == jar
    assert has_cookies(path)
    assert not list(tmp_path.glob("*.tmp")), "atomic write left a temp file"


def test_save_rejects_empty_jar(tmp_path):
    for bad in ([], None, "nope", {"a": 1}):
        with pytest.raises(BoothAuthError):
            save_cookies(bad, tmp_path / "ck.json")  # type: ignore[arg-type]


def test_load_rejects_corrupted_files(tmp_path):
    corrupt = tmp_path / "bad.json"
    corrupt.write_text("{not json", encoding="utf-8")
    with pytest.raises(BoothAuthError):
        load_cookies(corrupt)

    empty = tmp_path / "empty.json"
    empty.write_text("[]", encoding="utf-8")
    with pytest.raises(BoothAuthError):
        load_cookies(empty)

    wrong_shape = tmp_path / "obj.json"
    wrong_shape.write_text('{"a": 1}', encoding="utf-8")
    with pytest.raises(BoothAuthError):
        load_cookies(wrong_shape)

    nameless = tmp_path / "nameless.json"
    nameless.write_text('[{"value": "x"}]', encoding="utf-8")
    with pytest.raises(BoothAuthError):
        load_cookies(nameless)


def test_load_missing_file(tmp_path):
    with pytest.raises(BoothAuthError):
        load_cookies(tmp_path / "absent.json")


def test_logout(tmp_path):
    path = tmp_path / "ck.json"
    save_cookies([{"name": "a", "value": "1"}], path)
    assert logout(path) is True
    assert not path.exists()
    assert logout(path) is False  # idempotent


def test_cookies_to_jar_skips_malformed():
    jar = [{"name": "a", "value": 1}, {"value": "no-name"}, "junk", {"name": "b", "value": "2"}]
    assert cookies_to_jar(jar) == {"a": "1", "b": "2"}


# ---------------------------------------------------------------------------
# Expiry semantics
# ---------------------------------------------------------------------------


def test_all_expired_is_expired(tmp_path):
    path = tmp_path / "exp.json"
    save_cookies(
        [{"name": "a", "value": "v", "expires": 1}, {"name": "b", "value": "w", "expires": 2}], path
    )
    with pytest.raises(BoothAuthError):
        status(path)


def test_any_future_expiry_is_valid(tmp_path):
    path = tmp_path / "mix.json"
    save_cookies(
        [
            {"name": "a", "value": "v", "expires": 1},
            {"name": "b", "value": "w", "expires": time.time() + 3600},
        ],
        path,
    )
    assert status(path)["count"] == 2


def test_session_cookies_cannot_be_judged_locally(tmp_path):
    path = tmp_path / "sess.json"
    save_cookies([{"name": "a", "value": "v"}], path)
    assert status(path)["count"] == 1


def test_expires_zero_and_bool_are_ignored(tmp_path):
    """expires=0 / -1 mean "session"; a bool must not be read as a timestamp."""
    path = tmp_path / "odd.json"
    save_cookies(
        [
            {"name": "a", "value": "v", "expires": 0},
            {"name": "b", "value": "w", "expires": -1},
            {"name": "c", "value": "x", "expires": True},
        ],
        path,
    )
    assert status(path)["count"] == 3


def test_status_requires_cookies(tmp_path):
    with pytest.raises(BoothAuthError):
        status(tmp_path / "none.json")


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------


def test_restrict_permissions_keeps_file_readable(tmp_path):
    """The lockdown must never lock the user out of their own cookie file."""
    path = tmp_path / "secret.json"
    save_cookies([{"name": "a", "value": "v"}], path)
    restrict_permissions(path)
    # Readable regardless of platform.
    assert path.read_text(encoding="utf-8")
    assert load_cookies(path)


def test_restrict_permissions_unknown_account_keeps_file(tmp_path, monkeypatch):
    import core.auth as auth_mod

    monkeypatch.setattr(auth_mod, "current_account", lambda: "")
    path = tmp_path / "s.json"
    path.write_text("[]", encoding="utf-8")
    assert auth_mod.restrict_permissions(path) is False
    assert path.exists()


# ---------------------------------------------------------------------------
# Domain scoping
# ---------------------------------------------------------------------------


def test_cookies_are_scoped_to_the_request_host():
    """Session cookies must not be sent to unrelated third-party hosts."""
    from core.net import cookie_header

    jar = [
        {"name": "ac", "value": "1", "domain": "accounts.booth.pm"},
        {"name": "pm", "value": "2", "domain": ".booth.pm"},
        {"name": "cdn", "value": "3", "domain": "cdn.example.net"},
    ]
    assert cookie_header(jar, "https://accounts.booth.pm/library") == {"ac": "1", "pm": "2"}
    assert cookie_header(jar, "https://booth.pm/ja/items/1") == {"pm": "2"}
    assert cookie_header(jar, "https://cdn.example.net/x") == {"cdn": "3"}
    assert cookie_header(jar, "https://evil.test/steal") == {}
    assert cookie_header(None, "https://booth.pm/") == {}
    assert cookie_header([], "https://booth.pm/") == {}


def test_url_logging_drops_query_string():
    from core.net import safe_url

    assert "SECRET" not in safe_url("https://booth.pm/dl/a.zip?sig=SECRET&t=1#f")
    assert safe_url("https://booth.pm/dl/a.zip?sig=X") == "https://booth.pm/dl/a.zip"
    assert safe_url("") == "<invalid-url>"


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,secret",
    [
        ("cookie=abc123def456", "abc123def456"),
        ("Cookie: sessionvalue123", "sessionvalue123"),
        ("Set-Cookie: a=b; Path=/", "a=b"),
        (
            "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcdefgh",
            "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcdefgh",
        ),
        ("Authorization: Basic dXNlcjpwYXNzd29yZA==", "dXNlcjpwYXNzd29yZA=="),
        ("X-API-Key: sk-1234567890abcdef", "sk-1234567890abcdef"),
        ('{"token": "ghp_ABCdef1234567890"}', "ghp_ABCdef1234567890"),
        ('{"api_key": "sk-live-abcdef"}', "sk-live-abcdef"),
        ("password=hunter2", "hunter2"),
        ("client_secret=abc", "abc"),
        ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sigvalue", "eyJhbGciOiJIUzI1NiJ9"),
    ],
)
def test_redaction_removes_secret_values(text, secret):
    out = redact(text)
    assert secret not in out, f"secret leaked: {out}"
    assert "[REDACTED]" in out


@pytest.mark.parametrize(
    "text",
    [
        "fetching library (cookies count=42)",
        "GET https://accounts.booth.pm/library -> 200",
        "resolved url=1 failed attempts=3",
        "https://accounts.pixiv.net/login -> 302",
        r"login ok cookies saved to D:\data\cookies.json (password not stored)",
        "database is locked",
        "[12345] downloading タイトル.zip",
        "auth status ok count=7",
        "",
    ],
)
def test_redaction_preserves_useful_lines(text):
    assert redact(text) == text


def test_redaction_keeps_url_path_but_omits_query_values():
    assert redact("https://accounts.pixiv.net/login?lang=ja -> 302") == (
        "https://accounts.pixiv.net/login?[REDACTED] -> 302"
    )


def test_redaction_handles_pem_keys():
    pem = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEowIBAAKCAQEAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n"
        "-----END RSA PRIVATE KEY-----"
    )
    out = redact(f"config follows: {pem}")
    assert "MIIEowIBAAKCAQEA" not in out
    assert "BEGIN" in out  # structure retained for diagnosis


def test_redacting_filter_rewrites_record():
    f = SecretRedactingFilter()
    record = logging.LogRecord("x", logging.INFO, "f", 1, "token=%s", ("supersecretvalue",), None)
    assert f.filter(record) is True
    assert "supersecretvalue" not in record.getMessage()
    assert record.args == ()


def test_redacting_filter_never_raises_on_bad_format():
    f = SecretRedactingFilter()
    record = logging.LogRecord("x", logging.INFO, "f", 1, "value=%d", ("oops",), None)
    assert f.filter(record) is True


def test_no_secret_in_logs_during_full_flow(tmp_path, caplog):
    """End-to-end: the cookie value must not appear in any log record."""
    from core.db import get_connection, init_db

    secret = "SUPER-SECRET-COOKIE-VALUE-9f3a"
    path = tmp_path / "ck.json"
    save_cookies([{"name": "session", "value": secret, "domain": ".booth.pm"}], path)

    db = tmp_path / "app.db"
    init_db(db)
    conn = get_connection(db)
    conn.execute("INSERT INTO items(item_id,title) VALUES('x','T')")
    conn.commit()
    conn.close()

    with caplog.at_level(logging.DEBUG):
        status(path)
        load_cookies(path)
        cookies_to_jar(load_cookies(path))
        try:
            from core.download import resolve_download_links

            resolve_download_links("x", load_cookies(path))
        except Exception:
            pass

    dumped = "\n".join(r.getMessage() for r in caplog.records)
    assert secret not in dumped
    assert secret not in caplog.text
