"""Purchase list acquisition: browser cookies -> HTML -> parsed rows.

BOOTH publishes no purchase API, so the library page is scraped. When the
markup no longer matches, parsing stops with
:class:`~core.errors.BoothLayoutChangedError` instead of returning an empty
list that looks like "you bought nothing".
"""

from __future__ import annotations

import contextlib
import csv
import os
import re
import sqlite3
import tempfile
import time
from itertools import islice
from pathlib import Path
from typing import Any
from urllib.parse import urldefrag, urljoin, urlsplit

from . import net
from .auth import LIBRARY_URL, load_cookies
from .errors import (
    BoothAuthError,
    BoothLayoutChangedError,
    BoothLimitExceededError,
    BoothNetworkError,
    BoothPrerequisiteError,
)
from .logging_setup import get_logger

log = get_logger(__name__)

ORDER_HREF_RE = re.compile(r"/orders/([0-9a-zA-Z\-_]+)")
PRODUCT_HREF_RE = re.compile(r"booth\.pm/(?:[a-z]{2}/)?items/(\d+)")
PRICE_RE = re.compile(r"[¥￥]\s?[\d,]+|無料|FREE", re.I)
ITEM_LINK_RE = re.compile(r"/items/")
SHOP_CLASS_RE = re.compile(r"shop", re.I)

TIMEOUT = 30
MAX_ROWS = 20_000
CONTAINER_WALK = 4
# A row container holds a handful of nodes. Anything larger is a list or page
# wrapper, and searching it would make parsing quadratic.
MAX_CONTAINER_CHILDREN = 64
MAX_CONTAINER_DESCENDANTS = 400

# Text that identifies a genuinely empty library, as opposed to a parse failure.
EMPTY_LIBRARY_MARKERS = (
    "まだ購入",
    "購入履歴がありません",
    "ライブラリに何もありません",
    "购买的商品がありません",
    "No orders",
)


def _looks_logged_out(url: str) -> bool:
    lowered = (url or "").lower()
    return "login" in lowered or "accounts.pixiv.net" in lowered


def fetch_library_html(
    cookies: list[dict] | None = None, cookie_path: str | Path | None = None, timeout: int = TIMEOUT
) -> tuple[str, str]:
    """Fetch the purchase library page. Returns ``(html, final_url)``."""
    if cookies is None:
        cookies = load_cookies(cookie_path)
    log.info("fetching library (cookie count=%d)", len(cookies or []))
    response = net.request(LIBRARY_URL, cookies=cookies, timeout=timeout)
    final = str(response.url)
    if response.status_code in (401, 403) or _looks_logged_out(final):
        raise BoothAuthError("購入一覧の取得に失敗しました (要再ログイン)。")
    return response.text, final


def _text(el: Any) -> str:
    return el.get_text(" ", strip=True) if el is not None else ""


def _attr(el: Any, name: str) -> str:
    """Read a BeautifulSoup attribute as ``str``.

    ``bs4`` returns a list for multi-valued attributes (e.g. ``class``) and
    ``None`` when absent, so every read has to be coerced.
    """
    if el is None:
        return ""
    value = el.get(name)
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return " ".join(str(v) for v in value)
    return str(value)


def _row_container(anchor: Any, order_id: str) -> tuple[Any, list[Any]]:
    """Find a bounded subtree belonging to exactly this order, never a neighbour."""
    node = anchor.parent
    fallback = None
    for _ in range(CONTAINER_WALK):
        if node is None or not _is_row_sized(node):
            break
        links = node.find_all("a", href=True)
        orders = {m.group(1) for a in links if (m := ORDER_HREF_RE.search(_attr(a, "href")))}
        if orders != {order_id}:
            break
        fallback = node
        products = [a for a in links if ITEM_LINK_RE.search(_attr(a, "href"))]
        if products:
            return node, products
        node = node.parent
    return fallback, []


def _item_id_for(links: list[Any], order_id: str) -> str:
    """Use only a unique product link in the order's own bounded row."""
    if links:
        products = set()
        for link in links:
            href = _attr(link, "href")
            host = (urlsplit(href).hostname or "").lower()
            scoped = PRODUCT_HREF_RE.search(href)
            if scoped and (host == "booth.pm" or host.endswith(".booth.pm")):
                products.add(scoped.group(1))
        if len(products) == 1:
            return products.pop()
    log.warning(
        "order %s: 商品リンクが見つからないため暫定ID order_%s で記録します。"
        "BOOTH側のマークアップ変更が疑われます。",
        order_id,
        order_id,
    )
    return f"order_{order_id}"


def _is_row_sized(node: Any) -> bool:
    """True when ``node`` is small enough to be a single row rather than the page.

    The metadata walk climbs towards the root looking for the shop name, image
    and price. Without this guard it reaches ``<body>`` on a long library and
    runs a CSS selector over the whole document *once per row* -- 2.9 million
    selector matches for a 2000-item library, which took ~98 seconds. The
    descendant count is taken with ``islice`` so the check itself stays O(cap).
    """
    if len(node.contents) > MAX_CONTAINER_CHILDREN:
        return False
    for seen, _ in enumerate(islice(node.descendants, MAX_CONTAINER_DESCENDANTS + 1), start=1):
        if seen > MAX_CONTAINER_DESCENDANTS:
            return False
    return True


def _row_metadata(container: Any) -> tuple[str, str, str]:
    """Best-effort shop / thumbnail / price for one row."""
    if container is None:
        return "", "", ""
    shop = _text(container.find(class_=SHOP_CLASS_RE))
    img = container.find("img")
    thumb = _attr(img, "data-src") or _attr(img, "data-original") or _attr(img, "src")
    if thumb:
        thumb = urljoin(LIBRARY_URL, thumb)
    match = PRICE_RE.search(container.get_text(" ", strip=True))
    price = match.group(0) if match else ""
    return shop, thumb, price


def _library_product_id(href: str) -> str:
    parts = urlsplit(urljoin("https://booth.pm", href))
    host = (parts.hostname or "").lower()
    match = re.fullmatch(r"/(?:[a-z]{2}/)?items/(\d+)/?", parts.path)
    return match.group(1) if match and (host == "booth.pm" or host.endswith(".booth.pm")) else ""


def library_card(thumbnail: Any) -> tuple[Any, str]:
    """Find one current library card without crossing into another product."""
    node, card, item_id = thumbnail.parent, None, ""
    for _ in range(CONTAINER_WALK):
        if node is None or not _is_row_sized(node):
            break
        if len(node.select("img.l-library-item-thumbnail")) != 1:
            break
        ids = {_library_product_id(_attr(a, "href")) for a in node.select("a[href]")}
        if node.name == "a":
            ids.add(_library_product_id(_attr(node, "href")))
        ids.discard("")
        if len(ids) != 1:
            break
        card, item_id = node, next(iter(ids))
        node = node.parent
    if card is None:
        raise BoothLayoutChangedError("ライブラリの商品カードから商品IDを確認できません。")
    return card, item_id


def _parse_current_library(thumbnails: list[Any], base_url: str) -> list[dict]:
    source, _ = urldefrag(base_url)
    parts = urlsplit(source)
    if parts.scheme != "https" or parts.hostname != "accounts.booth.pm" or parts.path != "/library":
        raise BoothLayoutChangedError("ライブラリの取得元URLが想定外です。")
    rows: list[dict] = []
    for thumbnail in thumbnails:
        if len(rows) >= MAX_ROWS:
            raise BoothLimitExceededError(f"購入一覧が上限 {MAX_ROWS} 件を超えました。")
        card, item_id = library_card(thumbnail)
        anchors = card.select("a[href]")
        title = next(
            (
                _text(a)
                for a in anchors
                if _library_product_id(_attr(a, "href")) == item_id and _text(a)
            ),
            "",
        )
        if not title:
            raise BoothLayoutChangedError("ライブラリの商品カードから商品名を確認できません。")
        shop = ""
        for anchor in anchors:
            shop_url = urlsplit(urljoin(source, _attr(anchor, "href")))
            if (shop_url.hostname or "").endswith(".booth.pm") and shop_url.path in ("", "/"):
                shop = _text(anchor)
                break
        image = (
            _attr(thumbnail, "data-src")
            or _attr(thumbnail, "data-original")
            or _attr(thumbnail, "src")
        )
        date_node = card.find("time")
        rows.append(
            {
                "item_id": item_id,
                "order_id": f"item_{item_id}",
                "title": title,
                # Resolve downloads from the purchased card, never its public product page.
                "url": f"{source}#item-{item_id}",
                "shop": shop,
                "thumbnail": urljoin(source, image) if image else "",
                "category": "",
                "published_at": "",
                "purchase_date": _attr(date_node, "datetime") or _text(date_node),
                "price": "",
            }
        )
    return rows


def parse_library_html(html: str, base_url: str = LIBRARY_URL) -> list[dict]:
    """Parse the BOOTH purchase library into rows.

    Raises :class:`BoothLayoutChangedError` when the page does not look like a
    library we can read, so a markup change is reported instead of guessed at.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError as e:
        raise BoothPrerequisiteError(
            "beautifulsoup4 (HTML パーサ) が未導入です",
            "`setup.bat --repair` で同梱の固定依存を復元してください。",
        ) from e
    if not html or not html.strip():
        raise BoothLayoutChangedError("購入一覧のHTMLが空です。")

    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text(" ", strip=True)

    thumbnails = soup.select("img.l-library-item-thumbnail")
    if thumbnails:
        current_rows = _parse_current_library(thumbnails, base_url)
        log.info("parsed current library rows=%d", len(current_rows))
        return current_rows

    # Age-gate and other interstitial pages are surfaced, never treated as data.
    if "年齢確認" in page_text and len(page_text) < 2000 and not soup.select('a[href*="/orders/"]'):
        raise BoothLayoutChangedError(
            "年齢確認ページの可能性があります。実ブラウザで確認してください。"
        )
    if "ギフト" in page_text:
        log.warning("gift items may be present; they are recorded as normal rows")

    anchors = soup.select('a[href*="/orders/"]')
    if not anchors:
        if "booth" not in html.lower() and "pixiv" not in html.lower():
            raise BoothLayoutChangedError(
                "購入一覧のマーカーが見つかりません。HTML構造が変更された可能性があります。"
            )
        if any(marker in page_text for marker in EMPTY_LIBRARY_MARKERS):
            log.info("library appears empty; returning 0 rows")
            return []
        raise BoothLayoutChangedError(
            f"商品カードと注文リンクが見つかりません (html={len(html)}bytes)。"
        )

    rows: list[dict] = []
    seen: set[str] = set()
    for anchor in anchors:
        href = _attr(anchor, "href")
        if not href:
            continue
        order_match = ORDER_HREF_RE.search(href)
        if not order_match:
            continue
        order_id = order_match.group(1)
        if order_id in seen:
            continue
        seen.add(order_id)
        if len(rows) >= MAX_ROWS:
            raise BoothLimitExceededError(
                f"購入一覧が上限 {MAX_ROWS} 件を超えました。DBは更新しません。"
            )

        title = _text(anchor) or _attr(anchor, "title")
        container, product_links = _row_container(anchor, order_id)
        shop, thumb, price = _row_metadata(container)
        item_id = _item_id_for(product_links, order_id)
        date_node = container.find("time") if container is not None else None
        purchase_date = _attr(date_node, "datetime") or _text(date_node)

        rows.append(
            {
                "item_id": item_id,
                "order_id": order_id,
                "title": title or item_id,
                "url": urljoin("https://accounts.booth.pm", href),
                "shop": shop,
                "thumbnail": thumb,
                "category": "",
                "published_at": "",
                "purchase_date": purchase_date,
                "price": price,
            }
        )

    if not rows:
        raise BoothLayoutChangedError("注文リンクから有効な注文を解析できませんでした。")
    log.info("parsed library rows=%d", len(rows))
    return rows


def upsert_purchases(conn: sqlite3.Connection, rows: list[dict]) -> int:
    """Insert or refresh items and purchases in one transaction.

    Returning 0 rows is not an error; the caller reports the count.
    """
    if not rows:
        return 0
    n = 0
    try:
        for library_order, row in enumerate(rows):
            conn.execute(
                """INSERT INTO items(item_id,title,url,shop,thumbnail,category,published_at)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(item_id) DO UPDATE SET
                     title=excluded.title, url=excluded.url, shop=excluded.shop,
                     thumbnail=excluded.thumbnail, category=excluded.category,
                     published_at=excluded.published_at""",
                (
                    str(row.get("item_id", "")),
                    str(row.get("title", "")),
                    str(row.get("url", "")),
                    str(row.get("shop", "")),
                    str(row.get("thumbnail", "")),
                    str(row.get("category", "")),
                    str(row.get("published_at", "")),
                ),
            )
            conn.execute(
                """INSERT INTO purchases(item_id,purchase_date,price,library_order) VALUES(?,?,?,?)
                   ON CONFLICT(item_id) DO UPDATE SET
                      purchase_date=excluded.purchase_date, price=excluded.price,
                      library_order=excluded.library_order""",
                (
                    str(row.get("item_id", "")),
                    str(row.get("purchase_date", "")),
                    str(row.get("price", "")),
                    library_order,
                ),
            )
            n += 1
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise BoothNetworkError(f"購入データの保存に失敗しました ({type(e).__name__})") from e
    return n


def list_purchases(conn: sqlite3.Connection, limit: int | None = None) -> list[dict]:
    query = """SELECT i.item_id,i.title,i.url,i.shop,i.thumbnail,i.category,i.published_at,
                      p.purchase_date,p.price,p.library_order,i.created_at
               FROM items i LEFT JOIN purchases p ON p.item_id=i.item_id
               ORDER BY p.purchase_date DESC,
                        p.library_order ASC, i.item_id ASC"""
    if limit is not None and int(limit) > 0:
        capped = max(1, min(int(limit), MAX_ROWS))
        return [dict(r) for r in conn.execute(query + " LIMIT ?", (capped,)).fetchall()]
    return [dict(r) for r in conn.execute(query + " LIMIT ?", (MAX_ROWS,)).fetchall()]


CSV_FIELDS = ("item_id", "title", "url", "shop", "purchase_date", "price", "thumbnail")


def _csv_cell(value: Any) -> str:
    text = str(value) if value is not None else ""
    # CSV quoting does not stop Excel from executing a seller-provided formula.
    return (
        "'" + text if text.lstrip(" ").startswith(("=", "+", "-", "@", "\t", "\r", "\n")) else text
    )


def export_csv(rows: list[dict], path: str | Path) -> Path:
    """Write rows to CSV atomically, with a BOM so Excel reads UTF-8 correctly."""
    target = Path(path)
    tmp = None
    try:
        if target.parent and str(target.parent) not in ("", "."):
            target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".br-csv-", suffix=".tmp", dir=target.parent)
        tmp = Path(temporary)
        with os.fdopen(fd, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(CSV_FIELDS), extrasaction="ignore")
            writer.writeheader()
            writer.writerows(
                {key: _csv_cell(row.get(key, "")) for key in CSV_FIELDS} for row in rows or []
            )
            handle.flush()
            os.fsync(handle.fileno())
        # os.replace is the atomic rename on both Windows and POSIX and, unlike
        # Path.replace, cannot be shadowed by a subclass; tmp and target are on
        # the same volume by construction.
        for attempt in range(3):
            try:
                os.replace(tmp, target)  # noqa: PTH105
                break
            except PermissionError:
                # Windows can briefly deny replacement while another writer
                # publishes. Persistent locks still fail with the original intact.
                if os.name != "nt" or attempt == 2:
                    raise
                time.sleep(0.01 * (attempt + 1))
    except OSError as e:
        raise BoothNetworkError(f"CSV出力に失敗しました ({target}: {type(e).__name__})") from e
    finally:
        if tmp is not None:
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)
    return target


def update_from_network(db_path: str | Path, cookie_path: str | Path | None = None) -> int:
    """Fetch, parse and store the purchase list. Returns the number of rows."""
    try:
        from bs4 import BeautifulSoup
    except ImportError as e:
        raise BoothPrerequisiteError(
            "beautifulsoup4 が未導入です", "`setup.bat --repair` で固定依存を復元してください。"
        ) from e

    from .db import get_connection

    cookies = load_cookies(cookie_path)
    html, final = fetch_library_html(cookies=cookies)
    rows_by_order: dict[str, dict] = {}
    visited = {final}
    for _ in range(200):
        for row in parse_library_html(html, base_url=final):
            rows_by_order.setdefault(row["order_id"], row)
        if len(rows_by_order) > MAX_ROWS:
            raise BoothLimitExceededError(
                f"購入一覧が上限 {MAX_ROWS} 件を超えました。DBは更新しません。"
            )
        soup = BeautifulSoup(html, "html.parser")
        next_link = soup.select_one('a[rel~="next"]')
        if next_link is None:
            break
        next_url = urljoin(final, _attr(next_link, "href"))
        parts = urlsplit(next_url)
        if (
            parts.scheme != "https"
            or parts.hostname != "accounts.booth.pm"
            or parts.path.rstrip("/") != "/library"
            or next_url in visited
        ):
            raise BoothLayoutChangedError("購入一覧の次ページリンクが不正または循環しています。")
        visited.add(next_url)
        response = net.request(next_url, cookies=cookies)
        final = str(response.url)
        if _looks_logged_out(final):
            raise BoothAuthError("購入一覧の次ページ取得で認証が切れました。")
        html = response.text
    else:
        raise BoothLimitExceededError("購入一覧のページ数が上限200を超えました。DBは更新しません。")
    rows = list(rows_by_order.values())
    conn = get_connection(db_path)
    try:
        return upsert_purchases(conn, rows)
    finally:
        conn.close()
