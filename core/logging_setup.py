"""Logging setup. Cookie / token / password must never reach a log sink.

Design notes
------------
Redaction is *defense in depth*: the primary guarantee is that call sites never
pass secret values to the logger (they log counts and paths only). This module
is the safety net for the cases that slip through.

The previous implementation matched ``(cookie|token|...|pixiv|booth).*?[:=]\\S+``
which was wrong in both directions:

* it destroyed legitimate diagnostics -- ``cookies count=42`` became
  ``[REDACTED]`` (the key was followed by `` count=``, not a separator);
* it failed to redact the actual secret -- ``Authorization: Bearer <jwt>``
  only had the literal word ``Bearer`` removed because ``\\S+`` stops at the
  space, so the token itself was written to the log verbatim.

The patterns below match a *known secret key* followed by a separator and then
consume the **entire** remainder of the value, so the secret is fully removed
while the surrounding message stays readable.
"""

from __future__ import annotations

import io
import logging
import sys
from typing import Any

from redaction import contains_secret, redact

__all__ = [
    "SecretRedactingFilter",
    "contains_secret",
    "ensure_pipe_encoding",
    "get_logger",
    "redact",
    "setup_logging",
]

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"


class SecretRedactingFilter(logging.Filter):
    """Redacts credential values from the formatted message.

    Rewrites ``record.msg`` and clears ``record.args`` so the record can be
    re-formatted by downstream handlers without reintroducing the secret.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if record.exc_info:
            record.exc_text = redact(logging.Formatter().formatException(record.exc_info))
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = redact(record.exc_text)
        if record.stack_info:
            record.stack_info = redact(record.stack_info)
        try:
            rendered = record.getMessage()
        except Exception:  # noqa: BLE001 - never let logging break the app
            record.msg = "invalid log message"
            record.args = ()
            return True
        if not rendered:
            return True
        safe = redact(rendered)
        if safe != rendered:
            record.msg = safe
            record.args = ()
        return True


_configured = False


def ensure_pipe_encoding() -> None:
    """Force UTF-8 on redirected/piped streams; leave consoles alone.

    An interactive console keeps its native codepage so Japanese messages still
    render. A pipe or file, however, is almost always consumed by another
    process that will decode it as UTF-8 -- on Japanese Windows the default is
    cp932, which silently corrupts the text. Making the piped channels
    deterministic removes a whole class of "garbled output" reports.

    ``errors="backslashreplace"`` guarantees a log call can never raise
    ``UnicodeEncodeError`` and kill the operation being logged.
    """
    for target in (sys.stdout, sys.stderr):
        reconfigure = getattr(target, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            if target.isatty():
                continue
            encoding = (getattr(target, "encoding", "") or "").lower().replace("-", "")
            if encoding == "utf8":
                continue
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (AttributeError, ValueError, OSError, io.UnsupportedOperation):
            # A non-reconfigurable stream (e.g. a pytest capture object) is
            # perfectly usable; leave it alone.
            pass


def setup_logging(
    level: str | int = "INFO", *, force: bool = False, stream: Any = None
) -> logging.Logger:
    """Configure root logging once and return the package logger.

    The handler writes to ``stderr`` by default so that ``stdout`` stays a
    pure, ASCII-safe JSON channel for ``--json`` consumers.
    """
    global _configured  # noqa: PLW0603 - one-time process configuration
    if isinstance(level, str):
        numeric = getattr(logging, level.upper(), logging.INFO)
    else:
        numeric = int(level)

    ensure_pipe_encoding()
    root = logging.getLogger()
    for existing in root.handlers:
        if (
            isinstance(existing, logging.StreamHandler)
            and any(isinstance(f, SecretRedactingFilter) for f in existing.filters)
            and getattr(existing.stream, "closed", False)
        ):
            existing.stream = sys.stderr
    root.setLevel(numeric)
    if force and _configured:
        for h in list(root.handlers):
            root.removeHandler(h)
        _configured = False
    if not _configured:
        handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
        handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
        handler.addFilter(SecretRedactingFilter())
        root.addHandler(handler)
        # Third-party libraries are chatty at DEBUG and add no value here.
        for noisy in ("httpx", "httpcore", "hpack", "urllib3", "asyncio"):
            logging.getLogger(noisy).setLevel(max(numeric, logging.WARNING))
        _configured = True
    return get_logger("booth_reader")


def get_logger(name: str) -> logging.Logger:
    """Return a logger. No per-logger filters are attached.

    ``logging.Logger`` filters only apply to records emitted through that exact
    logger, never to records propagated from children, so attaching the filter
    here was both ineffective and a source of duplicate registrations. The
    root handler owns redaction instead.
    """
    return logging.getLogger(name)
