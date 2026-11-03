"""Import a free BOOTH product into the library from its public URL.

Purchases are discovered by scraping the BOOTH library. Free downloads never
appear there, so they need a second entry path: the user supplies the product
page URL, this module reads the product metadata and records the item. The
stored public URL is also what the downloader needs to resolve the free
download links later.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any, cast
from urllib.parse import urljoin, urlsplit

from . import auth, net
from .errors import BoothAuthError, BoothLayoutChangedError, BoothPrerequisiteError
from .logging_setup import get_logger

log = get_logger(__name__)

ITEM_PATH_RE = re.compile(r"^/(?:[a-z]{2}(?:-[a-z]{2})?/)?items/(\d+)/?$", re.I)
MAX_URL_LENGTH = 2048


def parse_item_url(value: str) -> tuple[str, str]:
    """Return ``(item_id, canonical_url)`` for a BOOTH product URL.

    Only product pages on ``booth.pm`` (or a shop subdomain) are accepted. The
    returned URL is rebuilt from the numeric ID, so query strings, fragments and
    locale prefixes cannot influence the request that follows.
    """
    raw = (value or "").strip()
    if not raw or len(raw) > MAX_URL_LENGTH:
        raise ValueError("Enter a BOOTH product URL")
    parts = urlsplit(raw)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or (host != "booth.pm" and not host.endswith(".booth.pm")):
        raise ValueError("Enter a BOOTH product URL (https://booth.pm/)")
    match = ITEM_PATH_RE.match(parts.path)
    if match is None:
        raise ValueError("Enter a BOOTH product URL (https://booth.pm/ja/items/...)")
    item_id = match.group(1)
    return item_id, f"https://booth.pm/ja/items/{item_id}"


def _html_parser() -> Any:
    try:
        from bs4 import BeautifulSoup
    except ImportError as e:
        raise BoothPrerequisiteError(
            "beautifulsoup4 (HTML parser)",
            "Run `start.bat --repair` to restore bundled dependencies.",
        ) from e
    return BeautifulSoup


def _soup(html: str) -> Any:
    if not html or not html.strip():
        raise BoothLayoutChangedError("Empty product HTML.")
    return _html_parser()(html, "html.parser")


def _text(element: Any) -> str:
    return element.get_text(" ", strip=True) if element is not None else ""


def _collect_ld_nodes(value: object, out: list[dict[str, Any]]) -> None:
    if isinstance(value, list):
        for entry in value:
            _collect_ld_nodes(entry, out)
    elif isinstance(value, dict):
        node = cast("dict[str, Any]", value)
        out.append(node)
        graph = node.get("@graph")
        if isinstance(graph, list):
            _collect_ld_nodes(graph, out)


def _ld_nodes(soup: Any) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for script in soup.select('script[type="application/ld+json"]'):
        raw = script.string if script.string is not None else script.get_text("", strip=False)
        try:
            value: object = json.loads(raw)
        except (TypeError, ValueError):
            continue
        _collect_ld_nodes(value, nodes)
    return nodes


def _product_node(nodes: list[dict[str, Any]]) -> dict[str, Any] | None:
    for node in nodes:
        raw_type = node.get("@type")
        types = raw_type if isinstance(raw_type, list) else [raw_type]
        if any(isinstance(kind, str) and kind.lower() == "product" for kind in types):
            return node
    return None


def _first_image(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        for entry in cast("list[object]", value):
            image = _first_image(entry)
            if image:
                return image
    if isinstance(value, dict):
        return _first_image(cast("dict[str, Any]", value).get("url"))
    return ""


def _low_price(product: dict[str, Any] | None) -> float | None:
    if not product:
        return None
    offers = product.get("offers")
    entries = offers if isinstance(offers, list) else [offers]
    for entry in cast("list[object]", entries):
        if not isinstance(entry, dict):
            continue
        offer = cast("dict[str, Any]", entry)
        for key in ("lowPrice", "price"):
            raw = offer.get(key)
            if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                return float(raw)
            if isinstance(raw, str):
                try:
                    return float(raw.replace(",", "").strip())
                except ValueError:
                    continue
    return None


def _meta_content(soup: Any, key: str) -> str:
    node = soup.select_one(f'meta[property="{key}"],meta[name="{key}"]')
    return str(node.get("content") or "").strip() if node is not None else ""


def _shop_from_page(soup: Any) -> str:
    shop = _text(soup.select_one(".shop-name"))
    if shop:
        return shop
    for anchor in soup.select("a[href]"):
        parts = urlsplit(urljoin("https://booth.pm", str(anchor.get("href") or "")))
        host = (parts.hostname or "").lower()
        if host.endswith(".booth.pm") and host != "booth.pm" and parts.path in ("", "/"):
            name = _text(anchor)
            if name:
                return name
    return ""


def _strip_booth_suffix(title: str, shop: str) -> str:
    value = re.sub(r"\s+-\s+BOOTH\s*$", "", title, flags=re.I).strip()
    if shop:
        suffix = f" - {shop}"
        if value.endswith(suffix):
            value = value[: -len(suffix)].strip()
    return value


def _https_url(value: str, base_url: str) -> str:
    absolute = urljoin(base_url, value.strip())
    try:
        parts = urlsplit(absolute)
    except ValueError:
        return ""
    if parts.scheme != "https" or not parts.hostname:
        return ""
    return absolute


def parse_item_page(html: str, page_url: str) -> dict[str, Any]:
    """Parse product metadata and free-download availability from an item page."""
    soup = _soup(html)
    product = _product_node(_ld_nodes(soup))
    page_text = soup.get_text(" ", strip=True)

    title = str(product.get("name") or "").strip() if product is not None else ""
    shop = ""
    if product is not None:
        brand = product.get("brand")
        if isinstance(brand, dict):
            shop = str(cast("dict[str, Any]", brand).get("name") or "").strip()
    image = _first_image(product.get("image")) if product is not None else ""
    price = _low_price(product)
    downloadable = bool(
        soup.select_one('[href*="/downloadables/"], [data-href*="/downloadables/"]')
    )
    free = (price is not None and price <= 0) or downloadable

    if not title:
        title = _strip_booth_suffix(_meta_content(soup, "og:title"), shop)
    if not title:
        title = _strip_booth_suffix(_text(soup.select_one("title")), shop)
    if not title:
        if "年齢確認" in page_text:
            raise BoothLayoutChangedError("Possible age verification page. Check in the browser.")
        raise BoothLayoutChangedError("Product title missing; possible BOOTH markup change.")

    if not shop:
        shop = _shop_from_page(soup)
    if not image:
        image = _meta_content(soup, "og:image")

    return {
        "title": title,
        "shop": shop,
        "thumbnail": _https_url(image, page_url) if image else "",
        "free": free,
        "price": "" if price is None else (f"{price:g}"),
    }


def fetch_item_metadata(
    url: str,
    cookies: list[dict[str, Any]] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    """Fetch and parse one public product page."""
    item_id, canonical_url = parse_item_url(url)
    response = net.request(canonical_url, cookies=cookies, timeout=timeout)
    final = str(response.url)
    if net.is_login_url(final) or "sign_in" in final.lower() or "login" in final.lower():
        raise BoothAuthError("Failed to fetch product information.")

    metadata = parse_item_page(response.text, final)
    metadata.update(item_id=item_id, url=canonical_url)
    log.info("parsed item url=%s free=%s", net.safe_url(canonical_url), metadata["free"])
    return metadata


def add_item_from_url(
    conn: sqlite3.Connection,
    url: str,
    cookie_path: str | Path | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    """Add one free BOOTH product from its URL and return its metadata.

    Re-adding an existing manual item refreshes its metadata. A purchased item
    keeps the library URL that its download links depend on, and only gains the
    requested list membership (the caller adds that).
    """
    cookies: list[dict[str, Any]] = []
    if auth.has_cookies(cookie_path):
        try:
            cookies = auth.load_cookies(cookie_path)
        except BoothAuthError:
            log.warning("cookies unreadable; fetching the public item page anonymously")
    metadata = fetch_item_metadata(url, cookies=cookies, timeout=timeout)
    if not metadata["free"]:
        raise ValueError(
            "This BOOTH item is not a free download. Add paid purchases by syncing BOOTH."
        )

    existing = conn.execute(
        """SELECT i.item_id,i.source,i.url,i.title,i.shop,i.thumbnail,
                  p.item_id AS purchase_item
           FROM items i LEFT JOIN purchases p ON p.item_id=i.item_id
           WHERE i.item_id=?""",
        (metadata["item_id"],),
    ).fetchone()

    if existing is None:
        conn.execute(
            """INSERT INTO items(item_id,title,url,shop,thumbnail,category,published_at,source)
               VALUES(?,?,?,?,?,'','','url')""",
            (
                metadata["item_id"],
                metadata["title"],
                metadata["url"],
                metadata["shop"],
                metadata["thumbnail"],
            ),
        )
        created = True
    else:
        created = False
        if existing["purchase_item"] is None and existing["source"] == "url":
            conn.execute(
                "UPDATE items SET title=?,url=?,shop=?,thumbnail=? WHERE item_id=?",
                (
                    metadata["title"] or existing["title"],
                    metadata["url"] or existing["url"],
                    metadata["shop"] or existing["shop"],
                    metadata["thumbnail"] or existing["thumbnail"],
                    metadata["item_id"],
                ),
            )
    conn.commit()
    log.info("item url add item=%s created=%s", metadata["item_id"], created)
    return {**metadata, "created": created}
