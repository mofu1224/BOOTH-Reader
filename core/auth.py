"""Cookie-based authentication.

The password is never stored, never logged and never leaves the browser that
the user types it into. Only the resulting cookie jar is persisted, and it is
locked to the current OS account.

Layout-change note
------------------
Login is performed by the bundled WebView2 via Playwright and the resulting cookies
are reused for plain HTTP requests. If BOOTH tightens its session handling the
failure surfaces as :class:`BoothAuthError` with a re-login hint rather than as
a silent empty result.
"""

from __future__ import annotations

import contextlib
import json
import os
import stat
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

from . import net
from .errors import (
    BoothAuthError,
    BoothError,
    BoothNetworkError,
    BoothPrerequisiteError,
)
from .logging_setup import get_logger

log = get_logger(__name__)

LIBRARY_URL = "https://accounts.booth.pm/library"
LOGIN_URL = "https://accounts.pixiv.net/login?lang=ja&source=booth&view_type=page"

DEFAULT_COOKIE_PATH = Path(__file__).resolve().parent.parent / "data" / "cookies.json"

INSTALL_HINT = (
    "Playwrightが未導入です。"
    "`start.bat` を実行してください (同梱の固定依存とブラウザーを repo-local に"
    "展開します。追加ダウンロードは不要です)。"
)

_TMP_SUFFIX = ".tmp"


def cookie_path(custom: str | Path | None = None) -> Path:
    return Path(custom) if custom else DEFAULT_COOKIE_PATH


# ---------------------------------------------------------------------------
# File access control
# ---------------------------------------------------------------------------


def _windows_tool(name: str) -> str:
    """Absolute path to a Windows system utility, or the bare name as fallback.

    Resolving first means the call cannot be hijacked by a same-named binary
    placed earlier on ``PATH``.
    """
    system_root = os.environ.get("SYSTEMROOT", r"C:\Windows")
    candidate = Path(system_root) / "System32" / name
    if candidate.exists():
        return str(candidate)
    log.debug("%s not found at %s; relying on PATH", name, candidate)
    return name


def icacls(path: Path, *args: str) -> bool:
    """Run icacls. Never raises; returns True on success.

    Only the exit code matters, so the output is decoded leniently: icacls
    writes localised (and on some systems UTF-8) text, which would otherwise
    raise inside the reader thread and take down the caller.
    """
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [_windows_tool("icacls"), str(path), *args],
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
            timeout=15,
        )
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError) as e:
        log.warning("icacls failed (%s): %s", args[0] if args else "?", type(e).__name__)
        return False


def current_account() -> str:
    """Best-effort ``DOMAIN\\user`` for the current process owner.

    ``whoami`` is authoritative; the environment is only a fallback. Returning
    an empty string means ACL lockdown is skipped rather than guessed.
    """
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [_windows_tool("whoami")],
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
            timeout=10,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except (OSError, subprocess.SubprocessError) as e:
        log.debug("whoami failed: %s", type(e).__name__)
    user = os.environ.get("USERNAME", "").strip()
    domain = os.environ.get("USERDOMAIN", "").strip()
    if user:
        return f"{domain}\\{user}" if domain else user
    return ""


def _is_readable(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            fh.read(1)
        return True
    except OSError:
        return False


def restrict_permissions(path: str | Path) -> bool:
    """Restrict a file to the current account. Returns True when locked down.

    The grant is applied *before* inheritance is removed. Reversing that order
    leaves a window in which the file has no access rules at all, and if the
    grant then fails the user is locked out of their own cookie file with no
    way back other than deleting it. The result is verified afterwards and
    rolled back if the file became unreadable.
    """
    p = Path(path)
    try:
        p.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError as e:
        log.warning("chmod 0600 failed: %s", type(e).__name__)
        return False

    if os.name != "nt":
        return True

    account = current_account()
    if not account:
        log.warning("account unknown; ACL unchanged")
        return False

    # DELETE is required for atomic rename and logout when the parent grants
    # Modify rather than Full Control (no FILE_DELETE_CHILD on the directory).
    granted = icacls(p, "/grant:r", f"{account}:(R,W,D)")
    if not granted:
        return False
    restricted = icacls(p, "/inheritance:r")
    if not _is_readable(p):
        log.error("ACL unreadable %s; restoring inheritance", p.name)
        icacls(p, "/grant:r", f"{account}:(F)")
        icacls(p, "/inheritance:e")
        return False
    return restricted


# Backwards-compatible private alias used by earlier call sites/tests.
_restrict_permissions = restrict_permissions


# ---------------------------------------------------------------------------
# Cookie storage
# ---------------------------------------------------------------------------


def save_cookies(cookies: list[dict[str, Any]], path: str | Path | None = None) -> Path:
    """Persist a cookie jar atomically, then lock it to this account."""
    p = cookie_path(path)
    # Validate before doing anything, including logging, so a malformed argument
    # produces a clean error rather than a TypeError from len()/json.dumps.
    raw_cookies = cast("object", cookies)
    if not isinstance(raw_cookies, list) or not raw_cookies:
        raise BoothAuthError("保存するCookieが空または形式不正です。")
    entries = cast("list[object]", raw_cookies)
    if not any(isinstance(c, dict) and cast("dict[str, Any]", c).get("name") for c in entries):
        raise BoothAuthError("Cookieの形式が不正です (name がありません)。")
    p.parent.mkdir(parents=True, exist_ok=True)
    # Values are never logged; only the count and the path.
    log.info("cookies save count=%d path=%s", len(cookies), p)
    try:
        payload = json.dumps(cookies, ensure_ascii=False)
    except (TypeError, ValueError) as e:
        raise BoothAuthError(f"CookieをJSONに変換できませんでした ({type(e).__name__})。") from e
    fd, temporary = tempfile.mkstemp(prefix=".cookies-", suffix=_TMP_SUFFIX, dir=p.parent)
    tmp = Path(temporary)
    try:
        # Create with 0600 from the outset so the secret is never briefly
        # world-readable between write and ACL change.
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            if not restrict_permissions(tmp):
                raise BoothAuthError(
                    "Cookie保存先のアクセス制限に失敗しました。以前のCookieは維持します。"
                )
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        # os.replace is the atomic rename on Windows and POSIX; a crash here
        # leaves the previous jar intact rather than a truncated one.
        if os.name == "nt" and p.is_file() and not restrict_permissions(p):
            raise BoothAuthError("以前のCookieの更新権限を準備できませんでした。内容は維持します。")
        os.replace(tmp, p)  # noqa: PTH105
    except OSError as e:
        raise BoothAuthError(f"Cookieを保存できませんでした ({p}: {type(e).__name__})") from e
    finally:
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)
    return p


def load_cookies(path: str | Path | None = None) -> list[dict[str, Any]]:
    p = cookie_path(path)
    if not p.exists():
        raise BoothAuthError(f"Cookieがありません ({p})。")
    try:
        data: object = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise BoothAuthError(f"Cookie読取に失敗しました ({type(e).__name__})。") from e
    if not isinstance(data, list) or not data:
        raise BoothAuthError("Cookieが空または形式不正です。")
    entries = cast("list[object]", data)
    if not any(isinstance(c, dict) and cast("dict[str, Any]", c).get("name") for c in entries):
        raise BoothAuthError("Cookieの形式が不正です (name がありません)。")
    return cast("list[dict[str, Any]]", data)


def has_cookies(path: str | Path | None = None) -> bool:
    p = cookie_path(path)
    try:
        return p.exists() and p.stat().st_size > 0
    except OSError:
        return False


def logout(path: str | Path | None = None) -> bool:
    p = cookie_path(path)
    if p.exists():
        try:
            if os.name == "nt" and p.is_file() and not restrict_permissions(p):
                raise BoothAuthError("Cookieの削除権限を準備できませんでした。")
            p.unlink()
        except OSError as e:
            raise BoothAuthError(f"Cookieを削除できませんでした ({type(e).__name__})") from e
        log.info("cookies removed path=%s", p)
        return True
    log.info("cookies absent")
    return False


def cookies_to_jar(cookies: list[dict[str, Any]]) -> dict[str, str]:
    """Flatten a cookie jar to ``name -> value``.

    Callers that know the target URL should prefer
    :func:`core.net.cookie_header`, which scopes the jar to the request host.
    """
    jar: dict[str, str] = {}
    for c in cast("list[object]", cookies or []):
        if not isinstance(c, dict):
            continue
        entry = cast("dict[str, Any]", c)
        if entry.get("name"):
            jar[str(entry["name"])] = str(entry["value"])
    return jar


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


def _looks_logged_out(url: str) -> bool:
    lowered = (url or "").lower()
    return "login" in lowered or "accounts.pixiv.net" in lowered


def _verify_login(page: Any, timeout_ms: int = 30000) -> bool:
    """Navigate to the library and report whether the session is authenticated.

    A library with no purchases is still a *successful* login, so the signal is
    "we were not bounced to a login page" rather than "orders were found".
    """
    try:
        response = page.goto(LIBRARY_URL, wait_until="domcontentloaded", timeout=timeout_ms)
    except Exception as e:  # noqa: BLE001 - browser/nav errors are not fatal here
        log.warning("login verification navigation failed: %s", type(e).__name__)
        return False
    final = page.url or ""
    parts = urlsplit(final)
    if (
        response is None
        or response.status != 200
        or parts.scheme != "https"
        or parts.hostname != "accounts.booth.pm"
        or parts.path.rstrip("/") != "/library"
    ):
        return False
    try:
        count = page.locator('a[href*="/orders/"]').count()
        if count == 0:
            log.info("library reachable, empty")
    except Exception as e:  # noqa: BLE001
        log.debug("order probe failed: %s", type(e).__name__)
    return True


def _launch_browser(headless: bool, factory: Any) -> tuple[Any, Any]:
    """Start Playwright and the pinned browser. Returns ``(playwright, browser)``.

    Only a failure *here* is a prerequisite problem. Everything after the launch
    -- navigating to the login page, reading the jar -- fails for reasons that
    have nothing to do with the installation, and reporting those as a broken
    browser is the same self-contradicting advice 1.0.1 removed: the user runs
    the suggested command, it succeeds, and the error is unchanged. A DNS
    failure, a proxy or a captive portal is the common case, and it must say so.
    """
    try:
        pw = factory().start()
    except Exception as e:
        raise BoothPrerequisiteError(
            "実ブラウザを起動できませんでした",
            "`start.bat --repair` で同梱の固定ブラウザーを復元してください。 "
            f"({type(e).__name__}: {e})",
        ) from e
    try:
        from .browser import launch_browser

        browser = launch_browser(pw, headless=headless)
    except Exception as e:
        with contextlib.suppress(Exception):
            pw.stop()
        # The usual cause is a missing or corrupt browser runtime. The bundled
        # setup restores it from verified local material, so name that remedy.
        raise BoothPrerequisiteError(
            "ブラウザーを起動できませんでした",
            f"`start.bat --repair` で同梱の固定ブラウザーを復元してから再実行してください。 ({e})",
        ) from e
    return pw, browser


def _run_login_session(browser: Any, timeout_s: int) -> list[dict[str, Any]]:
    """Drive the browser: open the login page, wait for Enter, verify, read cookies."""
    try:
        context = browser.new_context()
        page = context.new_page()
    except Exception as e:
        raise BoothNetworkError(
            f"ブラウザセッションを開始できませんでした。 ({type(e).__name__}: {e})"
        ) from e
    try:
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
    except Exception as e:
        raise BoothNetworkError(
            "ログインページを開けませんでした。通信環境 (回線・DNS・プロキシ・"
            f"ファイアウォール) を確認してください。 ({type(e).__name__}: {e})"
        ) from e
    print("ブラウザで pixiv/BOOTH にログインしてください。")
    print(f"完了後、このターミナルで Enter を押してください (制限 {timeout_s}s)。")
    print(f"ログイン先目安: {LIBRARY_URL}")

    # Windows has no SIGALRM, so a daemon thread bounds the wait.
    # input() itself cannot be interrupted; the thread is daemonic
    # so it dies with the process.
    import threading

    done = threading.Event()
    unreadable: list[str] = []

    def _wait_enter() -> None:
        try:
            input("ログイン完了後にEnter > ")
        except (EOFError, KeyboardInterrupt):
            pass
        except OSError as e:
            # stdin is closed or redirected (a service, a scheduler, `< NUL`).
            # Letting this escape kills the thread with a stack trace and the
            # main thread then reports a misleading "could not confirm login".
            unreadable.append(type(e).__name__)
        finally:
            done.set()

    threading.Thread(target=_wait_enter, daemon=True, name="br-login-wait").start()
    if not done.wait(timeout=timeout_s):
        raise BoothAuthError(f"ログイン待ちがタイムアウトしました ({timeout_s}s)。")
    if unreadable:
        raise BoothAuthError(
            "標準入力が読み取れないため、ログイン完了を待てませんでした "
            f"({unreadable[0]})。対話型のターミナルから実行してください。"
        )

    if not _verify_login(page):
        # Give the user a second chance: the page may still have been
        # mid-redirect when Enter was pressed.
        log.info("login unconfirmed; retry once")
        if not _verify_login(page):
            raise BoothAuthError(
                "ログインを確認できませんでした。ブラウザでログインし直してから"
                "Enter を押してください (またはもう一度実行してください)。"
            )
    try:
        return list(context.cookies())
    except Exception as e:
        raise BoothNetworkError(f"Cookieを読み取れませんでした。 ({type(e).__name__}: {e})") from e


def login(
    headless: bool = False,
    path: str | Path | None = None,
    timeout_s: int = 600,
) -> Path:
    """Open a real browser, let the user sign in, then store the cookies.

    The session is verified against the library before anything is written, so
    a premature Enter press reports a clear failure instead of saving a guest
    cookie jar that only fails later with a confusing error.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise BoothPrerequisiteError(
            "Playwright (実ブラウザ操作) が未導入です",
            "`start.bat --repair` で同梱の固定依存とブラウザーを復元してください。追加ダウンロードは不要です。",
        ) from e

    p = cookie_path(path)
    log.info("login browser; password not stored")
    pw, browser = _launch_browser(headless, sync_playwright)
    try:
        cookies = _run_login_session(browser, timeout_s)
    except BoothError:
        raise
    except Exception as e:
        # A browser-runtime fault that is neither an install problem nor a
        # network problem is still a distinct condition; it is named as such
        # instead of being folded into one of the two.
        raise BoothPrerequisiteError(
            "実ブラウザの操作に失敗しました",
            "もう一度実行してください。WebView2 が起動しない場合は "
            f"`start.bat doctor` で環境を確認してください。 ({type(e).__name__}: {e})",
        ) from e
    finally:
        for closer in (getattr(browser, "close", None), getattr(pw, "stop", None)):
            if closer is not None:
                with contextlib.suppress(Exception):
                    closer()

    if not cookies:
        raise BoothAuthError("Cookieが取得できませんでした。")
    # Playwright returns its own cookie objects; normalise to plain dicts so
    # the on-disk format does not depend on the library version.
    return save_cookies([dict(c) for c in cookies], p)


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def status(path: str | Path | None = None, verify_network: bool = False) -> dict[str, Any]:
    """Report cookie state. Values are never logged or returned.

    Expiry is judged from the cookie timestamps: if every cookie that carries
    an expiry is in the past the jar is treated as expired. Session cookies
    have no expiry, so their state cannot be determined locally.
    """
    p = cookie_path(path)
    if not has_cookies(p):
        raise BoothAuthError("未ログインです。")
    info: dict[str, Any] = {"path": str(p), "ok": True, "count": 0}
    cookies = load_cookies(p)
    info["count"] = len(cookies)

    now = time.time()
    dated: list[float] = []
    for c in cast("list[object]", cookies):
        if not isinstance(c, dict):
            continue
        expires = cast("dict[str, Any]", c).get("expires")
        if (
            isinstance(expires, (int, float))
            and not isinstance(expires, bool)
            and float(expires) > 0
        ):
            dated.append(float(expires))
    if dated and len(dated) == len(cookies) and all(e < now for e in dated):
        raise BoothAuthError("Cookieの有効期限が切れています。")

    if verify_network:
        response = net.request(LIBRARY_URL, cookies=cookies, timeout=20)
        final = str(response.url)
        if response.status_code in (401, 403) or _looks_logged_out(final):
            raise BoothAuthError("Cookieが失効しています。")
        info["http_status"] = response.status_code

    log.info("auth status ok count=%d", info["count"])
    return info
