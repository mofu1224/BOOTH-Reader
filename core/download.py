"""Download, extraction and verification.

State machine (``downloads`` table)
-----------------------------------
``pending -> downloading -> done | failed``

Crash safety
------------
Bytes are written to ``<name>.part`` and moved into place with ``os.replace``
only after the transfer is verified complete. A crash, a killed process or a
dropped connection therefore never leaves a truncated file in the library, and
the leftover ``.part`` is the resume source for the next run.

Resume correctness
------------------
The resume offset is recomputed from the on-disk size **inside** the retry
loop and the append/truncate decision is taken from the *response*, not from
the request. The previous implementation captured the offset once before the
loop, so after a partial transfer the retry re-requested the same byte range and
appended it a second time -- producing a silently corrupted file that was then
recorded as ``done`` with a checksum. The final size is also compared against
``Content-Range``/``Content-Length`` before the file is published.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
import time
import zipfile
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from urllib.parse import urljoin, urlsplit

from . import net
from .errors import (
    BoothAuthError,
    BoothLayoutChangedError,
    BoothLimitExceededError,
    BoothNetworkError,
    BoothPrerequisiteError,
)
from .logging_setup import get_logger, redact

log = get_logger(__name__)

DEFAULT_CONCURRENT = 3
MAX_CONCURRENT = 5
RETRY = 3

CHUNK_SIZE = 256 * 1024
PART_SUFFIX = ".part"

DOWNLOAD_LINK_RE = re.compile(r"(?:/downloads?/|download|file)", re.I)

# Characters Windows forbids in a path component, plus C0/C1 control characters.
FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')
_DRIVE_RE = re.compile(r"^[A-Za-z]:")
# Reserved DOS device names. Creating a file with one of these names either
# fails or silently targets the device, so they must be escaped.
_RESERVED_NAMES = frozenset(
    ["CON", "PRN", "AUX", "NUL"]
    + [f"COM{i}" for i in range(1, 10)]
    + [f"LPT{i}" for i in range(1, 10)]
)
_MAX_COMPONENT = 120
_MAX_WIN_PATH = 240


@dataclass(frozen=True)
class ExtractLimits:
    """Caps applied to a single archive extraction."""

    max_total_bytes: int = 8 * 1024**3  # 8 GiB across the whole archive
    max_entry_bytes: int = 8 * 1024**3  # 8 GiB for one member
    max_entries: int = 50_000
    max_compression_ratio: int = 200  # bombs explode far beyond this


def extract_limits() -> ExtractLimits:
    """Caps for one extraction. A zip bomb expands KB into GB; these stop it."""
    return ExtractLimits()


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def check_concurrent(n: int) -> int:
    try:
        v = int(n)
    except (TypeError, ValueError) as e:
        raise ValueError("concurrentは整数で指定してください") from e
    if v < 1:
        raise ValueError("concurrent must be >= 1")
    if v > MAX_CONCURRENT:
        raise ValueError(f"concurrent上限は{MAX_CONCURRENT}です (負荷配慮)。要求={v}")
    return v


def _reserved_stem(name: str) -> str:
    """Return the reserved DOS device name a component would collide with."""
    stem = name.split(".", 1)[0].strip().upper()
    return stem if stem in _RESERVED_NAMES else ""


def sanitize_component(name: str, maxlen: int = _MAX_COMPONENT, fallback: str = "untitled") -> str:
    """Reduce arbitrary text to a single safe filesystem path component.

    Removes path separators and characters Windows rejects, escapes reserved
    device names, and strips trailing dots/spaces (which Windows silently
    discards, so ``a.`` and ``a`` would collide).
    """
    value = cast("object", name)
    raw = value if isinstance(value, str) else ""
    cleaned = FORBIDDEN.sub("_", raw).strip()
    # Collapse whitespace runs so control characters removed above do not leave
    # stray tabs that make paths awkward to handle.
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    cleaned = cleaned[:maxlen].strip(" .")
    if not cleaned:
        return fallback
    reserved = _reserved_stem(cleaned)
    if reserved:
        cleaned = f"_{cleaned}"
    return cleaned[:maxlen].strip(" .") or fallback


def safe_title(name: str, maxlen: int = 80) -> str:
    """Backwards-compatible alias for :func:`sanitize_component`."""
    return sanitize_component(name, maxlen=maxlen)


def validate_item_id(item_id: str) -> str:
    """Reject item ids that could escape the library root.

    Item ids normally look like ``1234567`` or ``order_abc-123``. Anything
    containing a separator, a drive letter or a parent reference is refused
    rather than sanitised, because silently rewriting an id would point the
    download at a different directory than the database row.
    """
    value = (item_id or "").strip()
    if not value or len(value) > 128:
        raise ValueError("item_id が不正です (1〜128文字)")
    if FORBIDDEN.search(value) or _DRIVE_RE.match(value) or ".." in value:
        raise ValueError(f"item_id に使用できない文字が含まれています: {value[:64]!r}")
    if value in (".", ".."):
        raise ValueError("item_id が不正です")
    return value


def item_dir(library_root: str | Path, item_id: str, title: str = "") -> Path:
    """Resolve the directory for one item, guaranteed to stay under the root."""
    safe_id = validate_item_id(item_id)
    base = Path(library_root)
    dirname = f"{safe_id}_{sanitize_component(title)}" if title else safe_id
    candidate = (base / dirname).resolve()
    root = base.resolve()
    if candidate != root and root not in candidate.parents:
        # Defence in depth: validate_item_id already prevents separators, but
        # a containment check makes the guarantee local and testable.
        raise ValueError(f"item directory escapes the library root: {candidate}")
    return candidate


def _is_within(dest_dir: Path, target: Path) -> bool:
    """True when ``target`` is ``dest_dir`` or lives under it.

    A string-prefix test is wrong here: ``/lib_evil`` starts with ``/lib`` and
    would be accepted for a destination of ``/lib``.
    """
    try:
        target.relative_to(dest_dir)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Hashing / disk
# ---------------------------------------------------------------------------


def sha256_of(path: str | Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def disk_free_bytes(path: str | Path) -> int:
    """Free bytes on the volume holding ``path`` (0 when unknown)."""
    try:
        import shutil as _shutil

        target = Path(path)
        probe = target if target.exists() else target.parent
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        return _shutil.disk_usage(str(probe)).free
    except Exception as e:  # noqa: BLE001
        log.debug("disk_free_bytes unavailable: %s", type(e).__name__)
        return 0


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def _iter_safe_parts(name: str) -> list[str]:
    """Validate one archive member name and return its path parts.

    Raises ``ValueError`` for anything that must not be written to disk.
    """
    if not name:
        raise ValueError("空のエントリ名")
    if "\x00" in name or any(ord(c) < 32 or ord(c) == 127 for c in name):
        raise ValueError("制御文字を含むエントリ名")
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or _DRIVE_RE.match(name):
        raise ValueError("絶対パスのエントリ名")
    if normalized.startswith("//"):
        raise ValueError("UNC パスのエントリ名")
    parts = [p for p in normalized.split("/") if p not in ("", ".")]
    if not parts:
        raise ValueError("空のエントリ名")
    if any(p == ".." for p in parts):
        raise ValueError("親ディレクトリ参照を含むエントリ名")
    for part in parts:
        if FORBIDDEN.search(part) or part != part.rstrip(" .") or _reserved_stem(part):
            raise ValueError(f"使用できないエントリ名: {part[:64]!r}")
    if len(normalized) > _MAX_WIN_PATH:
        raise ValueError("パス長超過のエントリ名")
    return parts


def safe_extract_zip(
    zip_path: str | Path,
    dest_dir: str | Path,
    limits: ExtractLimits | None = None,
    *,
    strict: bool = False,
) -> list[str]:
    """Extract a zip with Zip-Slip and zip-bomb protection.

    Returns the list of extracted member names (relative, forward slashes).

    The declared sizes are validated *before* a single byte is written, so a
    bomb is rejected without leaving a half-extracted tree behind.
    """
    limits = limits or extract_limits()
    zip_path = Path(zip_path)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    resolved_base = dest_dir.resolve()

    skipped: list[str] = []
    written: list[str] = []
    total = 0

    with zipfile.ZipFile(zip_path) as z:
        infos = z.infolist()
        if len(infos) > limits.max_entries:
            raise BoothLimitExceededError(
                f"エントリ数が上限を超えています ({len(infos)} > {limits.max_entries})"
            )
        declared_total = 0
        targets: set[str] = set()
        for info in infos:
            try:
                key = "/".join(_iter_safe_parts(info.filename)).casefold()
            except ValueError:
                if strict:
                    raise BoothNetworkError(
                        f"ZIP に安全でないエントリがあります: {info.filename[:80]!r}"
                    ) from None
            else:
                if key in targets:
                    raise BoothNetworkError(f"ZIP の展開先が重複しています: {info.filename[:80]!r}")
                targets.add(key)
            if info.file_size > limits.max_entry_bytes:
                raise BoothLimitExceededError(
                    f"エントリが大きすぎます ({info.filename[:80]}: {info.file_size} bytes)"
                )
            declared_total += info.file_size
            if info.compress_size > 0:
                ratio = info.file_size / max(1, info.compress_size)
                if ratio > limits.max_compression_ratio:
                    raise BoothLimitExceededError(
                        f"圧縮比が異常です ({info.filename[:80]}: {ratio:.0f}:1)。"
                        "zip bomb の可能性があります。"
                    )
        if declared_total > limits.max_total_bytes:
            raise BoothLimitExceededError(
                f"展開後サイズが上限を超えています "
                f"({declared_total} > {limits.max_total_bytes} bytes)"
            )

        for info in infos:
            name = info.filename
            try:
                parts = _iter_safe_parts(name)
            except ValueError as e:
                log.warning("skip unsafe zip entry %r: %s", name[:80], e)
                skipped.append(name)
                continue

            target = resolved_base.joinpath(*parts)
            # Re-check after resolution: catches symlinked parents and any
            # residual traversal that survived textual validation.
            if not _is_within(resolved_base, target.resolve()):
                if strict:
                    raise BoothNetworkError("ZIP の展開先が出力フォルダ外です")
                log.warning("skip zip entry escaping destination: %s", name[:80])
                skipped.append(name)
                continue

            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix=".br-extract-", dir=target.parent)
            temp_path = Path(temporary)
            try:
                with os.fdopen(fd, "wb") as dst, z.open(info) as src:
                    while True:
                        block = src.read(CHUNK_SIZE)
                        if not block:
                            break
                        total += len(block)
                        if total > limits.max_total_bytes:
                            raise BoothLimitExceededError(
                                f"展開後サイズが上限を超えました (> {limits.max_total_bytes} bytes)"
                            )
                        dst.write(block)
                    dst.flush()
                    os.fsync(dst.fileno())
                _finalize(temp_path, target)
            finally:
                _unlink(temp_path)
            written.append("/".join(parts))

    if skipped:
        log.warning("extracted %d entries, skipped %d unsafe", len(written), len(skipped))
    return written


def cleanup_partials(
    root: str | Path, protected_paths: list[Path] | None = None, *, downloads_only: bool = False
) -> int:
    """Remove leftover ``.part`` files. Returns how many were deleted.

    The CLI limits cleanup to item/downloads and protects recorded originals.
    """
    removed = 0
    root = Path(root)
    if not root.exists():
        return 0
    protected = {path.resolve() for path in protected_paths or []}
    for part in root.rglob("*" + PART_SUFFIX):
        if downloads_only:
            relative = part.relative_to(root)
            if (
                len(relative.parts) != 3
                or relative.parts[1] != "downloads"
                or not _is_within(root.resolve(), part.resolve())
            ):
                continue
        if part.resolve() in protected:
            continue
        try:
            part.unlink()
            state = part.with_name(part.name + ".json")
            if state.resolve() not in protected:
                _unlink(state)
            removed += 1
        except OSError as e:
            log.warning("could not remove %s: %s", part, type(e).__name__)
    return removed


# ---------------------------------------------------------------------------
# Link resolution
# ---------------------------------------------------------------------------


def item_page_url(item_url_or_id: str) -> str:
    """Map a stored item id or URL to the page that carries the download links."""
    value = (item_url_or_id or "").strip()
    if value.startswith("http://") or value.startswith("https://"):
        return value
    if value.startswith("order_"):
        return f"https://accounts.booth.pm/orders/{value[len('order_') :]}"
    if value.isdigit():
        return f"https://booth.pm/ja/items/{value}"
    raise ValueError(f"item_id から商品URLを判定できません: {value[:64]!r}")


def resolve_download_links(
    item_url_or_id: str,
    cookies: list[dict[str, Any]],
    timeout: int = 30,
    max_links: int = 64,
) -> list[dict[str, Any]]:
    """Fetch the item/order page and extract download links.

    Raises ``BoothLayoutChangedError`` when the page does not look like a BOOTH
    item page, so a markup change stops with an explicit message instead of
    silently downloading nothing.

    Exceeding ``max_links`` is reported as :class:`BoothLimitExceededError`.
    Silently keeping the first 64 and reporting the item as complete would tell
    the user they have everything when they do not, which is the one outcome
    this module exists to prevent.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError as e:
        raise BoothPrerequisiteError(
            "beautifulsoup4 (HTML パーサ) が未導入です",
            "`start.bat --repair` で同梱の固定依存を復元してください。",
        ) from e

    url = item_page_url(item_url_or_id)
    log.info("download links item=%s", net.safe_url(url))
    source = urlsplit(url)
    library_item = re.fullmatch(r"item-(\d+)", source.fragment)
    if library_item and (
        source.scheme != "https"
        or source.hostname != "accounts.booth.pm"
        or source.path != "/library"
    ):
        raise ValueError("ライブラリのダウンロード元URLが不正です")
    response = net.request(
        url.split("#", 1)[0], cookies=cookies, timeout=timeout, accept_statuses=(200,)
    )
    final = str(response.url)
    if response.status_code in (401, 403) or "login" in final.lower():
        raise BoothAuthError("DLリンク取得に失敗 (要再ログイン)。")
    html = response.text

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    if "年齢確認" in text and not soup.select("a[href]"):
        raise BoothLayoutChangedError("年齢確認ページの可能性。実ブラウザで確認してください。")

    links: dict[str, dict[str, Any]] = {}
    if library_item:
        from .purchases import library_card

        for thumbnail in soup.select("img.l-library-item-thumbnail"):
            card, item_id = library_card(thumbnail)
            if item_id != library_item.group(1):
                continue
            for button in card.select(".js-download-button[data-href]"):
                absolute = urljoin(final, str(button.get("data-href") or ""))
                endpoint = urlsplit(absolute)
                if (
                    endpoint.scheme != "https"
                    or endpoint.hostname not in {"booth.pm", "accounts.booth.pm"}
                    or not re.fullmatch(r"/downloadables/\d+", endpoint.path)
                ):
                    raise BoothLayoutChangedError("商品のダウンロード先が想定外です。")
                row = button.parent
                for _ in range(3):
                    if row is None or row.get_text(" ", strip=True):
                        break
                    row = row.parent
                label = row.get_text(" ", strip=True) if row is not None else ""
                links.setdefault(absolute, {"url": absolute, "label": label})
                if len(links) > max_links:
                    raise BoothLimitExceededError(
                        f"ダウンロードリンクが上限 ({max_links}) を超えています。"
                    )
        if not links:
            raise BoothLayoutChangedError(
                "選択した商品のダウンロードリンクを確認できません。再同期してください。"
            )
        return list(links.values())
    for a in soup.select("a[href]"):
        href = str(a.get("href") or "")
        if not href:
            continue
        label = a.get_text(" ", strip=True) or a.get("title", "") or ""
        if DOWNLOAD_LINK_RE.search(href) or "ダウンロード" in label:
            absolute = urljoin(final, href)
            if not absolute.startswith(("http://", "https://")):
                continue
            links.setdefault(
                absolute, {"url": absolute, "label": label or absolute.rsplit("/", 1)[-1]}
            )
            if len(links) > max_links:
                raise BoothLimitExceededError(
                    f"ダウンロードリンクが上限 ({max_links}) を超えています: "
                    f"{net.safe_url(url)}。この商品はまとめて取得できません。"
                )

    if not links:
        if "booth" in html.lower():
            # Free / gift / multi-file cases are reported, never silently
            # treated as a layout break.
            if any(k in text for k in ("無料", "ギフト", "プレゼント", "複数")):
                log.warning("no direct links (free/gift/multi-file?) url=%s", url)
                return []
            raise BoothLayoutChangedError(
                "DLリンクが見つかりません。BOOTH側マークアップ変更の可能性があります。"
            )
        raise BoothLayoutChangedError("DLページの取得内容が想定外です。")
    return list(links.values())


# ---------------------------------------------------------------------------
# Transfer
# ---------------------------------------------------------------------------


class _IncompleteTransferError(Exception):
    """Internal: the body ended before the advertised length was reached."""

    def __init__(self, received: int, expected: int) -> None:
        super().__init__(f"expected {expected} bytes, received {received}")
        self.received = received
        self.expected = expected


def _content_range_total(value: str) -> int | None:
    """Parse the total size out of a ``Content-Range`` header value."""
    match = re.search(r"/(\d+)\s*$", value or "")
    return int(match.group(1)) if match else None


def _content_range_start(value: str) -> int | None:
    """Parse the first byte offset out of a ``Content-Range`` header value."""
    match = re.match(r"\s*bytes\s+(\d+)\s*-\s*(\d+)?\s*/", value or "", re.I)
    return int(match.group(1)) if match else None


class _RangeMismatchError(Exception):
    """The 206 body does not start where we asked it to start.

    Appending it would splice the wrong bytes into the middle of the file. The
    size check at the end of the transfer does catch the immediate attempt, but
    the poisoned ``.part`` survives it, and the *next* attempt resumes from that
    offset and completes at exactly the expected length -- publishing a file of
    the right size with the wrong content and recording its checksum. The start
    offset is therefore verified before a single byte is written, not inferred
    from the status code.
    """


def _expected_total(response: Any, offset: int, status: int) -> int | None:
    """Total size the finished file should have, or None when unknown."""
    if status == 206:
        total = _content_range_total(response.headers.get("content-range", ""))
        if total is not None:
            return total
    length = response.headers.get("content-length")
    if length and length.isdigit():
        base = offset if status == 206 else 0
        return base + int(length)
    return None


def _finalize(part: Path, dest: Path) -> None:
    """Publish a completed ``.part`` file as ``dest`` (atomic on same volume)."""
    os.replace(part, dest)  # noqa: PTH105 - atomic publish of the .part file
    _fsync_dir(dest.parent)


def _fsync_dir(directory: Path) -> None:
    """Flush the directory entry so the rename survives a power loss.

    Windows has no directory fsync; the failure is expected there and ignored.
    """
    if os.name == "nt":
        return
    try:
        fd = os.open(str(directory), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def download_file(
    url: str,
    dest: str | Path,
    cookies: list[dict[str, Any]],
    resume: bool = True,
    timeout: int = 60,
    progress_cb: Callable[[int, int | None], None] | None = None,
    max_retries: int = RETRY,
) -> Path:
    """Download one file with verified resume support and bounded retries.

    ``dest`` is only created (or replaced) once the transfer is verified
    complete, so the library never contains a truncated file.
    """
    httpx = net.require_httpx()
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + PART_SUFFIX)
    state_path = part.with_name(part.name + ".json")
    client = net.get_client(timeout)

    if resume and not part.exists() and dest.exists() and dest.stat().st_size > 0:
        # Adopt a partial file left behind by an earlier run so an interrupted
        # download continues instead of starting over.
        try:
            os.replace(dest, part)  # noqa: PTH105 - atomic adopt of the partial file
            log.info("resume %s offset=%d", dest.name, part.stat().st_size)
        except OSError as e:
            log.warning("could not adopt partial file %s: %s", dest, type(e).__name__)

    last_error: BaseException | None = None
    for attempt in range(1, max_retries + 1):
        offset = part.stat().st_size if (resume and part.exists()) else 0
        validator = ""
        validator_header = ""
        if offset:
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
                if state.get("url") == url:
                    validator = str(state.get("validator") or "")
                    validator_header = str(state.get("header") or "")
            except (OSError, ValueError, TypeError, AttributeError):
                pass
            if not validator or validator_header not in {"etag", "last-modified"}:
                # A prefix from an unknown representation cannot be joined to
                # a new body, even if its length and Content-Range are plausible.
                offset = 0
        if not resume and part.exists():
            _unlink(part)
            offset = 0
        headers = {"Accept": "*/*", "Accept-Encoding": "identity"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
            headers["If-Range"] = validator
        try:
            with (
                net.scoped_cookies(client, cookies, url),
                client.stream("GET", url, headers=headers) as r,
            ):
                status = r.status_code
                if net.is_login_url(str(r.url)):
                    raise BoothAuthError("DL先がログインページへ転送されました。")
                if status in (401, 403):
                    raise BoothAuthError("DL中に認証切れ (要再ログイン)。")
                if status == 416:
                    # Equal length does not prove equal content. A 416 never
                    # authenticates the local prefix; restart with a full GET.
                    # The local file does not match what the server has.
                    _unlink(part)
                    last_error = BoothNetworkError(
                        "ローカルの部分ファイルが想定外です。再ダウンロードします。"
                    )
                    if attempt < max_retries:
                        continue
                    raise last_error
                if status not in (200, 206):
                    if status in net.RETRYABLE_STATUS and attempt < max_retries:
                        last_error = BoothNetworkError(f"HTTP {status}")
                        r.close()
                        _sleep_backoff(attempt)
                        continue
                    raise BoothNetworkError(
                        f"ダウンロード失敗 (HTTP {status}): {net.safe_url(url)}"
                    )

                if status == 206:
                    # Verify the range actually starts at our offset before
                    # trusting any of its bytes.
                    served = _content_range_start(r.headers.get("content-range", ""))
                    if served != offset or (
                        offset and r.headers.get(validator_header) != validator
                    ):
                        _unlink(part)
                        last_error = _RangeMismatchError(
                            f"サーバーが返した範囲の開始位置が要求と一致しません "
                            f"(要求={offset} 応答={served})。ローカルの部分ファイルを破棄しました。"
                        )
                        if attempt < max_retries:
                            continue
                        raise last_error

                if r.headers.get("content-encoding", "identity").lower() not in {"", "identity"}:
                    raise BoothNetworkError(
                        "サーバーが圧縮された応答を返しました。安全に再開できません。"
                    )
                if status == 200 or not offset:
                    _unlink(part)
                    if part.exists():
                        raise BoothNetworkError("古い部分ファイルを置換できませんでした。")
                etag = r.headers.get("etag", "")
                header = "etag" if etag and not etag.startswith("W/") else "last-modified"
                _atomic_write_json(
                    state_path,
                    {
                        "url": url,
                        "validator": etag if header == "etag" else r.headers.get(header, ""),
                        "header": header,
                    },
                )

                expected = _expected_total(r, offset, status)
                append = status == 206 and offset > 0
                if offset and not append:
                    # The server ignored our Range header, so the body starts at
                    # byte 0. Appending would corrupt the file.
                    log.info("Range ignored %s; restart", dest.name)
                    offset = 0
                mode = "ab" if append else "wb"
                written = 0
                with part.open(mode) as f:
                    for block in r.iter_bytes(CHUNK_SIZE):
                        f.write(block)
                        written += len(block)
                        if progress_cb:
                            progress_cb(offset + written, expected)
                    f.flush()
                    os.fsync(f.fileno())
                if progress_cb:
                    progress_cb(offset + written, expected)

                actual = part.stat().st_size
                if expected is not None and actual != expected:
                    raise _IncompleteTransferError(actual, expected)
                _finalize(part, dest)
                _unlink(state_path)
                return dest
        except BoothAuthError:
            raise
        except BoothNetworkError:
            raise
        except (_IncompleteTransferError, _RangeMismatchError) as e:
            last_error = e
        except OSError as e:
            # Out of disk space, read-only volume, permission denied. Retrying
            # cannot help, and the message must say so.
            raise BoothNetworkError(
                f"ファイル書き込みに失敗しました ({dest}: {type(e).__name__}。"
                "空き容量と書き込み権限を確認してください。"
            ) from e
        except net.RETRYABLE_EXC as e:
            last_error = e
        except httpx.HTTPError as e:
            last_error = e
        except Exception as e:  # noqa: BLE001 - never leak a raw traceback
            last_error = e

        if attempt < max_retries:
            delay = net.backoff_delay(attempt)
            log.warning(
                "retry %d/%d %s: %s wait=%.2fs",
                attempt,
                max_retries,
                dest.name,
                type(last_error).__name__,
                delay,
            )
            _sleep_backoff(attempt, delay)

    raise BoothNetworkError(f"ダウンロード失敗 ({dest.name}: {_reason(last_error)})")


def _sleep_backoff(attempt: int, delay: float | None = None) -> None:
    time.sleep(delay if delay is not None else net.backoff_delay(attempt))


def _reason(error: BaseException | None) -> str:
    """One-line reason for the final failure message, detail included.

    The type name alone told the user nothing actionable; the internal errors
    this module raises (a short body, a bad range) carry the actual explanation
    in their message.
    """
    if error is None:
        return "unknown"
    text = redact(str(error).strip())
    return f"{type(error).__name__}: {text}" if text else type(error).__name__


def _unlink(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError as e:
        log.warning("could not remove %s: %s", path, type(e).__name__)


# ---------------------------------------------------------------------------
# Item level orchestration
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON via ``.tmp`` + ``os.replace`` so readers never see a torn file."""
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)  # noqa: PTH105 - atomic publish
        _fsync_dir(path.parent)
    except OSError as e:
        raise BoothNetworkError(f"{path.name} の書込に失敗しました ({type(e).__name__})") from e
    finally:
        _unlink(tmp)


def _set_status(
    conn: sqlite3.Connection,
    item_id: str,
    file_name: str,
    status: str,
    path: str = "",
    sha256: str = "",
    url: str = "",
) -> None:
    conn.execute(
        """INSERT INTO downloads(item_id,file_name,path,status,sha256,downloaded_at,url)
           VALUES(?,?,?,?,?,datetime('now'),?)
           ON CONFLICT(item_id,file_name) DO UPDATE SET
             path=excluded.path, status=excluded.status, sha256=excluded.sha256,
             downloaded_at=excluded.downloaded_at, url=excluded.url""",
        (item_id, file_name, path, status, sha256, url),
    )
    conn.commit()


def _stable_item_dir(root: Path, item_id: str, title: str, conn: sqlite3.Connection) -> Path:
    recorded_paths = conn.execute(
        "SELECT path FROM downloads WHERE item_id=?", (item_id,)
    ).fetchall()
    # No owned download exists yet, so there is no earlier directory identity
    # to recover. Scanning every sibling here makes a first batch quadratic.
    if not recorded_paths:
        return item_dir(root, item_id, title)
    resolved_root = root.resolve()
    candidates: set[Path] = set()
    for row in recorded_paths:
        recorded = Path(row["path"])
        # A copied library can recover the old folder by basename without an
        # O(library-size) scan, even while its ledger still stores the old root.
        for directory in {
            recorded.parent.parent.resolve(),
            (root / recorded.parent.parent.name).resolve(),
        }:
            if (
                recorded.parent.name == "downloads"
                and directory.parent == resolved_root
                and (directory.name == item_id or directory.name.startswith(item_id + "_"))
                and directory.is_dir()
            ):
                candidates.add(directory)
    if not candidates and root.is_dir():
        candidates = {
            p.resolve()
            for p in root.iterdir()
            if (p.name == item_id or p.name.startswith(item_id + "_"))
            and p.is_dir()
            and p.resolve().parent == resolved_root
        }
    if len(candidates) > 1:
        raise ValueError(f"同じ商品の保存先が複数あります: {item_id}")
    return next(iter(candidates)) if candidates else item_dir(root, item_id, title)


class _NameLedger:
    """Durable link -> file-name binding, read from the ``downloads`` table.

    This is what makes a second ``download`` a no-op instead of a second copy.

    Deriving the file name from the *filesystem* looks correct and is not: the
    first run writes ``data.zip``, and the next run sees ``data.zip`` already on
    disk, concludes the name is taken and picks ``data_2.zip``. The ledger row
    that said "done" is filed under ``data.zip``, so the skip check misses, the
    transfer runs again, and every repetition adds another copy. The documented
    guarantee that a re-run does not re-fetch completed files was unreachable.

    The binding therefore has to come from persistent state, and the filesystem
    may only be consulted for names this application does not own.
    """

    def __init__(self, rows: Iterable[sqlite3.Row | Mapping[str, object]]) -> None:
        self.by_url: dict[str, str] = {}
        self.legacy_names: set[str] = set()
        self.names: set[str] = set()
        for row in rows:
            name = str(row["file_name"] or "")
            if not name:
                continue
            self.names.add(name)
            url = str(row["url"] or "")
            if url:
                self.by_url.setdefault(url, name)
            else:
                # Written before the url column existed. Kept usable so an
                # existing library stays idempotent across the upgrade instead
                # of being re-downloaded in full.
                self.legacy_names.add(name)

    def resolve(self, url: str, preferred: str) -> str | None:
        """Return the name already bound to ``url``, or None for a new link."""
        bound = self.by_url.get(url)
        if bound is not None:
            return bound
        if preferred in self.legacy_names:
            return preferred
        return None


def download_item(
    item_id: str,
    db_path: str | Path,
    library_root: str | Path,
    cookie_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    extract: bool = True,
    timeout: int = 60,
    force: bool = False,
    max_extracted_listed: int = 500,
) -> dict[str, Any]:
    """Download every file belonging to one item.

    A failure on one file is recorded and the remaining files are still
    attempted, so a single dead link does not discard the rest of a multi-file
    purchase. The item result reports ``ok`` and ``failed`` separately.
    """
    from .auth import load_cookies
    from .db import get_connection

    safe_id = validate_item_id(item_id)
    root = Path(output_dir) if output_dir else Path(library_root)
    cookies = load_cookies(cookie_path)
    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT * FROM items WHERE item_id=?", (safe_id,)).fetchone()
        if row is None:
            raise ValueError(
                f"item_id not found in DB: {safe_id} (先に purchases list --update-db を実行)"
            )
        title = row["title"] or safe_id
        url = row["url"] or ""
        ddir = _stable_item_dir(root, safe_id, title, conn)
        dl_dir = ddir / "downloads"
        ex_dir = ddir / "extracted"
        for directory in (dl_dir, ex_dir):
            if not _is_within(ddir, directory.resolve()):
                raise ValueError("ライブラリのサブフォルダが出力先外を参照しています")
        dl_dir.mkdir(parents=True, exist_ok=True)
        ex_dir.mkdir(parents=True, exist_ok=True)

        free = disk_free_bytes(dl_dir)
        if free == 0:
            log.info("free space unknown for %s", dl_dir)

        links = resolve_download_links(url or safe_id, cookies, timeout=timeout)
        if not links:
            meta: dict[str, Any] = {
                "item_id": safe_id,
                "title": title,
                "url": url,
                "files": [],
                "status": "no_links",
                "note": "no direct download links (free/gift/age-check?)",
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            _atomic_write_json(ddir / "meta.json", meta)
            log.warning("no files item=%s; note saved", safe_id)
            return {
                "item_id": safe_id,
                "files": [],
                "failed": [],
                "dir": str(ddir),
                "status": "no_links",
            }

        results: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        try:
            previous: Any = json.loads((ddir / "meta.json").read_text(encoding="utf-8"))
            previous_files: dict[str, dict[str, Any]] = {
                f["file"]: f for f in previous.get("files", [])
            }
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            previous_files = {}
        used_names: set[str] = set()
        ledger = _NameLedger(
            conn.execute(
                "SELECT file_name, url FROM downloads WHERE item_id=?", (safe_id,)
            ).fetchall()
        )
        for index, link in enumerate(links, start=1):
            link_url = str(link.get("url") or "")
            fname = _file_name_for(dl_dir, link, index, used_names, ledger)
            dest = dl_dir / fname

            existing = conn.execute(
                "SELECT status,sha256 FROM downloads WHERE item_id=? AND file_name=?",
                (safe_id, fname),
            ).fetchone()
            if (
                not force
                and existing is not None
                and existing["status"] == "done"
                and dest.is_file()
                and (not existing["sha256"] or sha256_of(dest) == existing["sha256"])
            ):
                log.info("[%s] %s skip (done)", safe_id, fname)
                cached: dict[str, Any] = {
                    **previous_files.get(fname, {}),
                    "file": fname,
                    "path": str(dest),
                    "sha256": existing["sha256"],
                    "skipped": True,
                    "extracted": previous_files.get(fname, {}).get("extracted", []),
                }
                try:
                    if (
                        extract
                        and dest.suffix.lower() == ".zip"
                        and (
                            not cached.get("extraction_completed")
                            or any(not (ex_dir / p).is_file() for p in cached["extracted"])
                        )
                    ):
                        cached_extracted = safe_extract_zip(dest, ex_dir, strict=True)
                        cached.update(
                            extracted=cached_extracted[:max_extracted_listed],
                            extracted_total=len(cached_extracted),
                            extraction_completed=True,
                        )
                except (
                    OSError,
                    zipfile.BadZipFile,
                    BoothNetworkError,
                    BoothLimitExceededError,
                ) as e:
                    _set_status(
                        conn, safe_id, fname, "failed", str(dest), existing["sha256"], url=link_url
                    )
                    failures.append({"file": fname, "error": f"{type(e).__name__}: {e}"})
                    continue
                results.append(cached)
                continue

            _set_status(conn, safe_id, fname, "downloading", str(dest), url=link_url)
            log.info("[%s] %s download", safe_id, fname)
            try:
                # Existing published files are complete versions, never resume
                # prefixes. Force/repair must leave them intact until replacement.
                if force:
                    _unlink(dest.with_name(dest.name + PART_SUFFIX))
                download_file(link_url, dest, cookies, resume=not dest.exists(), timeout=timeout)
                sha = sha256_of(dest)
                extracted: list[str] = []
                if extract and dest.suffix.lower() == ".zip":
                    try:
                        extracted = safe_extract_zip(dest, ex_dir, strict=True)
                    except zipfile.BadZipFile as e:
                        raise BoothNetworkError(f"ZIP が破損しています: {dest.name}") from e
                    except BoothLimitExceededError:
                        raise
                _set_status(conn, safe_id, fname, "done", str(dest), sha, url=link_url)
                results.append(
                    {
                        "file": fname,
                        "path": str(dest),
                        "sha256": sha,
                        "extracted": extracted[:max_extracted_listed],
                        "extracted_total": len(extracted),
                        "extraction_completed": extract and dest.suffix.lower() == ".zip",
                    }
                )
                log.info("[%s] %s done sha256=%s", safe_id, fname, sha[:12])
            except BoothAuthError:
                _set_status(conn, safe_id, fname, "failed", str(dest), url=link_url)
                raise
            except Exception as e:  # noqa: BLE001 - record and continue
                _set_status(conn, safe_id, fname, "failed", str(dest), url=link_url)
                log.error("download failed %s/%s: %s: %s", safe_id, fname, type(e).__name__, e)
                failures.append({"file": fname, "error": f"{type(e).__name__}: {e}"})

        item_meta: dict[str, Any] = {
            "item_id": safe_id,
            "title": title,
            "url": url,
            "shop": row["shop"],
            "status": "partial" if failures else "done",
            "files": results,
            "failed": failures,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        _atomic_write_json(ddir / "meta.json", item_meta)
        return {
            "item_id": safe_id,
            "files": results,
            "failed": failures,
            "dir": str(ddir),
            "status": item_meta["status"],
        }
    finally:
        conn.close()


def _preferred_name(link: dict[str, Any], index: int) -> tuple[str, str]:
    """Return ``(name, extension)`` derived from one download link.

    The extension is only trusted when it is short and alphanumeric, so a URL
    such as ``/files/thing.php?x=1`` cannot smuggle a misleading suffix into
    the library.
    """
    label = link.get("label") or ""
    # Operating on a label string, not a filesystem path, so splitext is the
    # right tool here (Path would strip the directory, which a label has none of).
    stem = sanitize_component(os.path.splitext(label)[0], maxlen=100) if label else f"file{index}"  # noqa: PTH122
    tail = link.get("url", "").split("?")[0].rstrip("/").rsplit("/", 1)[-1]
    ext = ""
    for source in (label, tail):
        candidate = os.path.splitext(source)[1]  # noqa: PTH122
        if candidate and len(candidate) <= 6 and candidate[1:].replace(".", "").isalnum():
            ext = candidate
            break
    name = f"{stem}{ext}" if ext else stem
    # Published originals must never occupy a transfer/metadata scratch name.
    if name.lower().endswith((".part", ".part.json", ".part.json.tmp")):
        name += ".bin"
        ext = ".bin"
    if not name or name in (".", ".."):
        name = f"file{index}"
    return name, ext


def _file_name_for(
    dl_dir: Path,
    link: dict[str, Any],
    index: int,
    used: set[str],
    ledger: _NameLedger | None = None,
) -> str:
    """Derive the file name for one download link.

    Resolution order:

    1. the name this exact URL was already recorded under, so a re-run
       reproduces the previous layout instead of creating ``name_2``;
    2. a legacy row (recorded before the ledger stored URLs) whose name equals
       the preferred name, so an existing library keeps its numbering;
    3. otherwise a fresh name, unique against this batch and against the names
       already bound to other links of this item.

    The filesystem is consulted only for names this application does not track,
    so a file the user put there by hand is still not clobbered. Names the
    ledger *does* own are never treated as collisions -- that check is what
    produced a new copy on every run.
    """
    preferred, ext = _preferred_name(link, index)
    if ledger is not None:
        bound = ledger.resolve(link.get("url", ""), preferred)
        if bound is not None:
            if bound != sanitize_component(bound) or not _is_within(
                dl_dir.resolve(), (dl_dir / bound).resolve()
            ):
                raise ValueError("ダウンロード台帳のファイル名が安全でありません")
            scratch_names = {bound + suffix for suffix in (".part", ".part.json", ".part.json.tmp")}
            if {name.casefold() for name in scratch_names} & {
                name.casefold() for name in ledger.names
            }:
                raise ValueError("ダウンロードの一時保存先が別の原本と衝突しています")
            used.add(bound)
            return bound

    ledger_names: set[str] = ledger.names if ledger is not None else set()
    reserved = {n.casefold() for n in set(used) | ledger_names}
    name = preferred
    counter = 2
    while {
        name.casefold() + suffix for suffix in ("", ".part", ".part.json", ".part.json.tmp")
    } & reserved or _untracked_file_exists(dl_dir, name):
        name = f"{preferred.rsplit('.', 1)[0]}_{counter}{ext}"
        counter += 1
    used.add(name)
    return name


def _untracked_file_exists(dl_dir: Path, name: str) -> bool:
    """True when ``name`` is occupied by a file this item does not track."""
    for candidate in (name, name + PART_SUFFIX, name + ".part.json", name + ".part.json.tmp"):
        try:
            if (dl_dir / candidate).exists():
                return True
        except OSError:
            return False
    return False


def download_many(
    item_ids: list[str],
    db_path: str | Path,
    library_root: str | Path,
    cookie_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    concurrent: int = DEFAULT_CONCURRENT,
    extract: bool = True,
    force: bool = False,
    progress_cb: Callable[[int, int | None], None] | None = None,
) -> dict[str, Any]:
    from .library_lock import library_lock

    with library_lock(output_dir or library_root):
        return _download_many(
            item_ids,
            db_path,
            library_root,
            cookie_path,
            output_dir,
            concurrent,
            extract,
            force,
            progress_cb,
        )


def _download_many(
    item_ids: list[str],
    db_path: str | Path,
    library_root: str | Path,
    cookie_path: str | Path | None,
    output_dir: str | Path | None,
    concurrent: int,
    extract: bool,
    force: bool,
    progress_cb: Callable[[int, int | None], None] | None,
) -> dict[str, Any]:
    """Download many items with bounded parallelism.

    Returns ``{"ok": [...], "failed": [...]}``. Failures are collected rather
    than raised so one broken item cannot abandon the rest of a batch.
    """
    workers = check_concurrent(concurrent)
    results: dict[str, list[Any]] = {"ok": [], "failed": []}
    ids = [i for i in dict.fromkeys(item_ids or []) if str(i).strip()]
    if not ids:
        return results

    completed = 0
    total = len(ids)

    def run(iid: str) -> dict[str, Any]:
        try:
            return download_item(
                iid, db_path, library_root, cookie_path, output_dir, extract, force=force
            )
        finally:
            net.close_clients()

    def record(result: dict[str, Any]) -> None:
        if result.get("failed"):
            result["error"] = "; ".join(str(f.get("error", "")) for f in result["failed"])
            results["failed"].append(result)
        else:
            results["ok"].append(result)

    if workers == 1 or len(ids) == 1:
        for iid in ids:
            completed += 1
            try:
                record(run(iid))
            except Exception as e:  # noqa: BLE001
                results["failed"].append({"item_id": iid, "error": f"{type(e).__name__}: {e}"})
            if progress_cb:
                progress_cb(completed, total)
        return results

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="br-dl") as ex:
        futures = {ex.submit(run, iid): iid for iid in ids}
        for fut in as_completed(futures):
            iid = futures[fut]
            completed += 1
            try:
                record(fut.result())
            except Exception as e:  # noqa: BLE001
                results["failed"].append({"item_id": iid, "error": f"{type(e).__name__}: {e}"})
            if progress_cb:
                progress_cb(completed, total)
    return results
