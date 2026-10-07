"""Private live-service smoke; never publish cookies, purchase names or URLs."""

from __future__ import annotations

import json
import logging
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main(progress: dict[str, str]) -> None:
    from core.auth import load_cookies, status
    from core.db import get_connection, init_db
    from core.download import download_file, resolve_download_links, safe_extract_zip
    from core.net import close_clients, get_client, scoped_cookies
    from core.purchases import list_purchases, update_from_network

    logging.disable(logging.CRITICAL)
    session = status(verify_network=True)
    if not session["ok"] or session.get("http_status") != 200:
        raise RuntimeError("Authorized BOOTH session is unavailable")
    cookies = load_cookies()
    verified = False
    extracted = False
    size = 0
    with tempfile.TemporaryDirectory(
        prefix="live-service-probe-", dir=ROOT / ".cache/tmp"
    ) as scratch:
        database = init_db(Path(scratch) / "private.db")
        progress["stage"] = "purchase-pagination"
        count = update_from_network(database)
        conn = get_connection(database)
        try:
            rows = list_purchases(conn, limit=20)
        finally:
            conn.close()
        for row in rows:
            progress["stage"] = "resolve-owned-download-links"
            links = resolve_download_links(row["url"], cookies)
            for link in links:
                progress["stage"] = "download-get-preflight"
                client = get_client(30)
                with (
                    scoped_cookies(client, cookies, link["url"]),
                    client.stream(
                        "GET", link["url"], headers={"Accept-Encoding": "identity"}
                    ) as response,
                ):
                    length = int(response.headers.get("Content-Length") or 0)
                    if response.status_code != 200 or not 0 < length <= 32 * 1024 * 1024:
                        continue
                destination = Path(scratch) / "purchased-fixture.zip"
                progress["stage"] = "authorized-download"
                download_file(link["url"], destination, cookies, resume=False)
                if not zipfile.is_zipfile(destination):
                    destination.unlink()
                    continue
                size = destination.stat().st_size
                safe_extract_zip(destination, Path(scratch) / "extracted", strict=True)
                verified, extracted = True, True
                break
            if verified:
                break
    close_clients()
    report = {
        "session_http_200": True,
        "purchases_fetched": count,
        "authorized_download_verified": verified,
        "zip_extraction_verified": extracted,
        "download_bytes": size,
        "private_test_files_removed": True,
        "scope": "existing authorized session; no credential/purchase/URL values persisted",
    }
    (ROOT / ".cache/live-service-result.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report))
    if not verified:
        raise RuntimeError("No small authorized ZIP was available for download smoke")


if __name__ == "__main__":
    progress = {"stage": "session"}
    try:
        main(progress)
    except Exception as error:  # noqa: BLE001 - never expose private service details
        print(
            json.dumps(
                {
                    "ok": False,
                    "stage": progress["stage"],
                    "error_type": type(error).__name__,
                    "private_details_omitted": True,
                }
            )
        )
        raise SystemExit(1) from None
