"""Shared HTTP layer: connection reuse, timeouts, retry/backoff, cookies.

Every outbound request in BOOTH-Reader goes through here so that timeout,
retry and header behaviour is consistent and auditable in one place.

Rationale for the defaults
--------------------------
* One ``httpx.Client`` per thread (connection pooling + keep-alive). Creating a
  client per request forces a new TCP+TLS handshake for every call, which was
  the dominant cost on the page-fetch path.
* Retries apply to **idempotent GETs only**, with exponential backoff and full
  jitter. Writes are never retried automatically.
* 4xx responses are not retried except for 408/429, which are explicitly
  "try again" signals. Retrying a 403 (auth) or 404 wastes load on BOOTH.
* ``Retry-After`` is honoured when the server sends it.
"""

from __future__ import annotations

import email.utils
import math
import os
import random
import threading
import time
from collections.abc import Generator, Iterable
from contextlib import contextmanager
from http.cookiejar import Cookie, CookieJar, DefaultCookiePolicy
from typing import Any, cast
from urllib.parse import urlsplit

from .errors import BoothAuthError, BoothNetworkError, BoothPrerequisiteError
from .logging_setup import get_logger

log = get_logger(__name__)

try:  # optional at import time so the CLI still starts without it
    import httpx as _httpx
except ImportError:  # pragma: no cover - exercised only on a broken install
    _httpx = None  # type: ignore[assignment]

# The login flow runs the bundled WebView2 via Playwright and its cookies are reused
# for every subsequent request, so the HTTP client presents the same engine
# identity. It stays overridable because BOOTH may tighten its checks; see
# `BOOTH_READER_USER_AGENT`.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

DEFAULT_TIMEOUT = 30.0
DOWNLOAD_TIMEOUT = 60.0
CONNECT_TIMEOUT = 15.0

MAX_RETRIES = 3
BACKOFF_BASE = 0.5
BACKOFF_CAP = 8.0

RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})

# Transient transport failures. Anything not listed is treated as permanent so
# a genuine bug surfaces immediately instead of being retried three times.
RETRYABLE_EXC: tuple[type[BaseException], ...] = (
    (
        _httpx.ConnectError,
        _httpx.ConnectTimeout,
        _httpx.ReadTimeout,
        _httpx.WriteTimeout,
        _httpx.PoolTimeout,
        _httpx.RemoteProtocolError,
        _httpx.TransportError,
        _httpx.NetworkError,
    )
    if _httpx is not None
    else ()
)

_local = threading.local()


def require_httpx() -> Any:
    if _httpx is None:
        raise BoothPrerequisiteError(
            "httpx (HTTP client)",
            "Run `start.bat --repair` to restore bundled dependencies.",
        )
    return _httpx


def user_agent() -> str:
    return os.environ.get("BOOTH_READER_USER_AGENT", "").strip() or DEFAULT_USER_AGENT


def default_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Baseline request headers. Kept small and honest; no fingerprint spoofing."""
    h = {
        "User-Agent": user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja,en;q=0.8",
        "Connection": "keep-alive",
    }
    if extra:
        h.update(extra)
    return h


def _new_client(timeout: float) -> Any:
    httpx = require_httpx()
    limits = httpx.Limits(max_connections=8, max_keepalive_connections=4, keepalive_expiry=30.0)
    return httpx.Client(
        follow_redirects=True,
        timeout=httpx.Timeout(timeout, connect=CONNECT_TIMEOUT),
        limits=limits,
        headers=default_headers(),
    )


def get_client(timeout: float = DEFAULT_TIMEOUT) -> Any:
    """Return a per-thread shared ``httpx.Client`` (created on first use).

    ``httpx.Client`` is thread-safe for concurrent requests, but a single
    instance shared across threads with a small pool is a bottleneck when the
    downloader runs 5 workers, hence thread-local instances.
    """
    cache: dict[float, Any] | None = getattr(_local, "clients", None)
    if cache is None:
        cache = {}
        _local.clients = cache
    client = cache.get(timeout)
    if client is None or client.is_closed:
        client = _new_client(timeout)
        cache[timeout] = client
    return client


def close_clients() -> None:
    """Close and forget this thread's clients (called at shutdown)."""
    cache: dict[float, Any] | None = getattr(_local, "clients", None)
    if not cache:
        return
    for client in cache.values():
        try:
            client.close()
        except Exception as e:  # noqa: BLE001
            log.debug("client close failed: %s", type(e).__name__)
    _local.clients = {}


def _retry_after(response: Any) -> float | None:
    raw = response.headers.get("retry-after") if response is not None else None
    if not raw:
        return None
    raw = raw.strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    try:
        when = email.utils.parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    import datetime as _dt

    if when.tzinfo is None:
        when = when.replace(tzinfo=_dt.timezone.utc)
    return max(0.0, when.timestamp() - time.time())


def backoff_delay(attempt: int, retry_after: float | None = None) -> float:
    """Exponential backoff with full jitter, clamped to ``BACKOFF_CAP``."""
    if retry_after is not None:
        return min(retry_after, BACKOFF_CAP)
    ceiling = min(BACKOFF_BASE * (2 ** max(0, attempt - 1)), BACKOFF_CAP)
    # Full jitter over a non-cryptographic RNG: the only requirement is that
    # concurrent workers do not retry in lockstep.
    return random.uniform(0.0, ceiling)  # noqa: S311


def cookie_header(
    cookies: Iterable[dict[str, Any]] | dict[str, str] | None, url: str
) -> dict[str, str]:
    """Build a cookie header scoped to ``url``'s host.

    BOOTH hands out cookies for several domains (``accounts.booth.pm``,
    ``booth.pm``, CDN hosts). Sending the whole jar to every host leaks the
    session to third parties and is rejected by some CDNs, so cookies are
    filtered by domain and path before being attached.
    """
    from urllib.request import Request

    request = Request(url)  # noqa: S310 - builds headers only; performs no I/O
    jar = _cookie_jar(cookies, url)
    jar.add_cookie_header(request)
    return dict(
        part.split("=", 1) for part in request.get_header("Cookie", "").split("; ") if "=" in part
    )


def _cookie_jar(cookies: Iterable[dict[str, Any]] | dict[str, str] | None, url: str) -> CookieJar:
    """Retain browser scopes, including host-only, on every redirect."""
    jar = CookieJar(
        policy=DefaultCookiePolicy(strict_ns_domain=DefaultCookiePolicy.DomainStrictNonDomain)
    )
    host = (urlsplit(url).hostname or "").lower()
    if isinstance(cookies, dict):
        cookies = [
            {"name": k, "value": v, "domain": host}
            for k, v in cast("dict[str, Any]", cookies).items()
        ]
    for raw in cast("Iterable[object]", cookies or []):
        if not isinstance(raw, dict):
            continue
        c = cast("dict[str, Any]", raw)
        name, value = c.get("name"), c.get("value")
        if not name or value is None:
            continue
        domain = str(c.get("domain") or host).lower()
        expires = c.get("expires")
        expiry = (
            int(expires)
            if isinstance(expires, (float, int))
            and not isinstance(expires, bool)
            and math.isfinite(expires)
            and expires > 0
            else None
        )
        if not domain or any(ch in str(name) + str(value) for ch in "\r\n\x00"):
            continue
        jar.set_cookie(
            Cookie(
                version=0,
                name=str(name),
                value=str(value),
                port=None,
                port_specified=False,
                domain=domain,
                domain_specified=domain.startswith("."),
                domain_initial_dot=domain.startswith("."),
                path=str(c.get("path") or "/"),
                path_specified=True,
                secure=bool(c.get("secure")),
                expires=expiry,
                discard=expiry is None,
                comment=None,
                comment_url=None,
                rest={},
            )
        )
    return jar


@contextmanager
def scoped_cookies(
    client: Any, cookies: Iterable[dict[str, Any]] | dict[str, str] | None, url: str
) -> Generator[None, None, None]:
    """Connections are reusable; authentication state is not reusable after logout.

    httpx copies CookieJar when building redirects and loses its strict policy.
    The request hook reapplies that policy before each redirected send.
    """
    jar = _cookie_jar(cookies, url)
    client.cookies = require_httpx().Cookies(jar)

    def scope_request(request: Any) -> None:
        request.headers.pop("cookie", None)
        client.cookies.jar.set_policy(
            DefaultCookiePolicy(strict_ns_domain=DefaultCookiePolicy.DomainStrictNonDomain)
        )
        client.cookies.set_cookie_header(request)

    client.event_hooks["request"].append(scope_request)
    try:
        yield
    finally:
        client.event_hooks["request"].remove(scope_request)
        client.cookies.clear()


def request(
    url: str,
    *,
    cookies: Iterable[dict[str, Any]] | dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    max_retries: int = MAX_RETRIES,
    accept_statuses: Iterable[int] = (200,),
) -> Any:
    """GET ``url`` with retries. Returns the ``httpx.Response``.

    ``accept_statuses`` are statuses the caller wants back verbatim (e.g. 206
    or 416 for range downloads). Everything else outside 2xx raises.
    """
    httpx = require_httpx()
    client = get_client(timeout)
    accept = set(accept_statuses)
    last_error: BaseException | None = None

    for attempt in range(1, max_retries + 1):
        try:
            with scoped_cookies(client, cookies, url):
                response = client.get(url, headers=headers or None)
        except BoothNetworkError:
            raise
        except RETRYABLE_EXC as e:
            last_error = e
            if attempt >= max_retries:
                break
            delay = backoff_delay(attempt)
            log.warning(
                "http retry %d/%d url=%s err=%s sleep=%.2fs",
                attempt,
                max_retries,
                safe_url(url),
                type(e).__name__,
                delay,
            )
            time.sleep(delay)
            continue
        except httpx.HTTPError as e:
            raise BoothNetworkError(
                f"HTTP client error ({type(e).__name__}): {safe_url(url)}"
            ) from e

        if response.status_code in accept or 200 <= response.status_code < 300:
            return response

        if response.status_code in (401, 403):
            response.close()
            raise BoothAuthError(f"HTTP {response.status_code} for {safe_url(url)}")

        if response.status_code in RETRYABLE_STATUS and attempt < max_retries:
            delay = backoff_delay(attempt, _retry_after(response))
            log.warning(
                "http retry %d/%d url=%s status=%d sleep=%.2fs",
                attempt,
                max_retries,
                safe_url(url),
                response.status_code,
                delay,
            )
            response.close()
            time.sleep(delay)
            continue

        raise BoothNetworkError(f"HTTP {response.status_code} for {safe_url(url)}")

    raise BoothNetworkError(
        f"Request failed ({safe_url(url)}: "
        f"{type(last_error).__name__ if last_error else 'unknown'})"
    )


def safe_url(url: str) -> str:
    """Strip query and fragment so signed URLs never reach the log."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return "<invalid-url>"
    host = parts.hostname or ""
    return f"{parts.scheme}://{host}{parts.path}" if host else "<invalid-url>"


def is_login_url(url: str) -> bool:
    parts = urlsplit(url)
    return parts.hostname == "accounts.pixiv.net" or (
        parts.hostname == "accounts.booth.pm" and parts.path.rstrip("/") == "/login"
    )


def check_network(timeout: float = 10.0) -> bool:
    """Best-effort connectivity probe. Never raises."""
    if _httpx is None:
        return False

    try:
        r = get_client(timeout).get("https://accounts.booth.pm/", timeout=timeout)
        return bool(r.status_code < 500)
    except Exception as e:  # noqa: BLE001
        log.debug("network probe failed: %s", type(e).__name__)
        return False
