"""Pure credential redaction shared by CLI logs and HTTP errors."""

from __future__ import annotations

import re

_SECRET_KEY = "|".join(
    [
        "set-cookie",
        "proxy-authorization",
        "authorization",
        "x-api-key",
        r"api[_-]?key",
        "apikey",
        r"access[_-]?token",
        r"refresh[_-]?token",
        r"id[_-]?token",
        r"auth[_-]?token",
        "token",
        r"secret[_-]?key",
        r"client[_-]?secret",
        r"client[_-]?id",
        "secret",
        "password",
        "passwd",
        "pwd",
        r"session[_-]?id",
        "sid",
        "session",
        "cookies?",
        r"private[_-]?key",
        "passphrase",
        "credential",
        "auth",
    ]
)
_KV_RE = re.compile(
    rf"""(?i)(?<![\w])({_SECRET_KEY})(["']?\s*[:=]\s*)"""
    r"""("[^"]*"|'[^']*'|[^\s,;\)\]\}]+|.*)""",
    re.DOTALL,
)
_SCHEME_RE = re.compile(r"(?i)\b(Bearer|Basic|Digest|Negotiate)\s+([A-Za-z0-9\-._~+/=]{8,})")
_PEM_RE = re.compile(
    r"(?s)-----BEGIN [A-Z0-9 ]*(?:PRIVATE KEY|OPENSSH PRIVATE KEY)-----.*?"
    r"-----END [A-Z0-9 ]*(?:PRIVATE KEY|OPENSSH PRIVATE KEY)-----"
)
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\b")
_REPLACEMENT = "[REDACTED]"
_URL_QUERY_RE = re.compile(r"(https?://[^\s?\"'<>]+)\?[^\s\"'<>]*", re.I)
_URL_USERINFO_RE = re.compile(r"(https?://)[^\s/@]+@", re.I)
_HEADER_RE = re.compile(
    r"(?i)(?<![\w])(set-cookie|cookies?|proxy-authorization|authorization)(\s*:\s*)[^\r\n]*"
)


def redact(text: str) -> str:
    if not text:
        return text
    out = _PEM_RE.sub(f"-----BEGIN PRIVATE KEY-----{_REPLACEMENT}-----END PRIVATE KEY-----", text)
    out = _SCHEME_RE.sub(lambda m: f"{m.group(1)} {_REPLACEMENT}", out)
    out = _JWT_RE.sub(_REPLACEMENT, out)
    out = _URL_QUERY_RE.sub(lambda m: f"{m.group(1)}?[REDACTED]", out)
    out = _URL_USERINFO_RE.sub(r"\1[REDACTED]@", out)
    out = _HEADER_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{_REPLACEMENT}", out)
    return _KV_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{_REPLACEMENT}", out)


def contains_secret(text: str) -> bool:
    return bool(text and redact(text) != text)
