"""BOOTH-Reader CLI.

The CLI is the single source of truth for behaviour. The Web UI drives this
same code through a subprocess, so anything the UI can do is reproducible from
a terminal, and the two interfaces cannot drift apart.

Exit code contract
------------------
===== ==========================================================
Code  Meaning
===== ==========================================================
0     success
1     operational failure (auth expired, network, bad input)
2     usage error (bad flags, mutually exclusive options)
3     BOOTH markup changed -- selectors need updating
===== ==========================================================

Machine-readable output
-----------------------
``--json`` writes **only** JSON to stdout, ASCII-escaped, so it survives a
cp936/cp932 console pipe. Human-facing progress and all logging go to stderr.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sqlite3
import sys
import time
import unicodedata
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, NoReturn, cast

from core.portable import apply_portable_env, effective_browsers_path

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB = str(BASE_DIR / "app.db")
DEFAULT_LIBRARY = str(BASE_DIR / "BOOTH-Reader-Library")

# Portable defaults (Playwright browsers, pip/uv caches inside the repo) are
# applied before anything else runs, so every entry point -- direct CLI, the
# persistent `rpc` worker and its one-shot children -- shares one layout.
# Explicitly set variables always win; see core/portable.py.
apply_portable_env(BASE_DIR)

SORT_CHOICES = ("newest", "oldest", "name", "shop")

EPILOG = """\
Examples:
  start.bat unclassified --sort newest
  start.bat purchases list --update-db
  start.bat download --item-id order_12345
  start.bat download --all --concurrent 3
  start.bat auth login
  start.bat doctor
  start.bat web --port 8000

Exit codes: 0=success 1=error 2=usage error 3=BOOTH layout changed
"""


def _add_common(p: argparse.ArgumentParser) -> None:
    """Allow --db/--log-level before or after the subcommand.

    ``SUPPRESS`` keeps the subparser from overwriting a value that was already
    given at the top level.
    """
    p.add_argument("--db", default=argparse.SUPPRESS, help="Database path (default: app.db)")
    p.add_argument(
        "--log-level",
        default=argparse.SUPPRESS,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level",
    )


class _Parser(argparse.ArgumentParser):
    """Usage errors retain exit code 2 and a concise help command."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        print(f"ERROR {message}", file=sys.stderr)
        print(
            "Help: start.bat help",
            file=sys.stderr,
        )
        self.exit(2)


def _resolve(args: argparse.Namespace) -> tuple[str, str]:
    db = getattr(args, "db", None) or DEFAULT_DB
    level = getattr(args, "log_level", None) or "INFO"
    return db, level


def build_parser() -> argparse.ArgumentParser:
    p = _Parser(
        prog="cli.py",
        description="BOOTH-Reader: sync, download and organize BOOTH purchases",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--db", default=DEFAULT_DB, help="Database path (default: app.db)")
    p.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level",
    )
    p.add_argument("--version", action="store_true", help="Show version")
    sub = p.add_subparsers(dest="cmd", required=False)

    sp = sub.add_parser("init-db", help="Create or update app.db")
    _add_common(sp)

    ap = sub.add_parser("auth", help="Browser login management")
    _add_common(ap)
    asub = ap.add_subparsers(dest="auth_cmd", required=True)
    l = asub.add_parser("login", help="Open browser, log in and save cookies")  # noqa: E741
    l.add_argument("--headless", action="store_true", help="Use headless browser")
    l.add_argument("--cookie-path", default=None, help="Cookie file path")
    l.add_argument("--timeout", type=int, default=600, help="Login timeout in seconds")
    _add_common(l)
    o = asub.add_parser("logout", help="Delete cookies")
    o.add_argument("--cookie-path", default=None)
    _add_common(o)
    s = asub.add_parser("status", help="Check cookie status")
    s.add_argument("--cookie-path", default=None)
    s.add_argument("--verify-network", action="store_true", help="Verify session over HTTP")
    s.add_argument("--json", action="store_true", help="JSON output")
    _add_common(s)

    imp = asub.add_parser("import", help="Import cookie JSON from stdin")
    imp.add_argument("--cookie-path", default=None)
    imp.add_argument("--json", action="store_true")
    _add_common(imp)

    pp = sub.add_parser("purchases", help="Purchases")
    _add_common(pp)
    psub = pp.add_subparsers(dest="purchases_cmd", required=True)
    pl = psub.add_parser("list", help="List purchases (database by default)")
    pl.add_argument("--update-db", action="store_true", help="Sync purchases from BOOTH")
    pl.add_argument("--csv", default=None, help="CSV output path")
    pl.add_argument("--limit", type=int, default=None, help="Row limit (<=0: all)")
    pl.add_argument("--cookie-path", default=None)
    pl.add_argument("--json", action="store_true", help="JSON output")
    _add_common(pl)

    dp = sub.add_parser("download", help="Download, extract and verify files")
    dp.add_argument("--item-id", default=None, help="Download one product ID")
    dp.add_argument("--all", action="store_true", help="Download all products")
    dp.add_argument(
        "--output-dir", default=None, help="Output folder (default: BOOTH-Reader-Library)"
    )
    dp.add_argument("--concurrent", type=int, default=3, help="Concurrency (1-5, default: 3)")
    dp.add_argument("--no-extract", action="store_true", help="Disable automatic ZIP extraction")
    dp.add_argument("--force", action="store_true", help="Download completed files again")
    dp.add_argument("--cookie-path", default=None)
    dp.add_argument("--json", action="store_true", help="JSON output")
    _add_common(dp)

    dlp = sub.add_parser("downloads", help="Query download records")
    _add_common(dlp)
    dlsub = dlp.add_subparsers(dest="downloads_cmd", required=True)
    dll = dlsub.add_parser("list", help="List download records")
    dll.add_argument("--limit", type=int, default=200, help="Row limit (1-1000)")
    dll.add_argument("--status", default=None, choices=["pending", "downloading", "done", "failed"])
    dll.add_argument("--json", action="store_true", help="JSON output")
    _add_common(dll)

    clean = dlsub.add_parser("cleanup", help="Delete incomplete .part files")
    clean.add_argument("--output-dir", default=DEFAULT_LIBRARY)
    clean.add_argument("--json", action="store_true")
    _add_common(clean)

    up = sub.add_parser("unclassified", help="List unclassified products")
    up.add_argument(
        "--sort", default="newest", choices=SORT_CHOICES, help="Sort order (default: newest)"
    )
    up.add_argument("--limit", type=int, default=None, help="Row limit (<=0: all)")
    up.add_argument("--csv", default=None, help="CSV output path")
    up.add_argument("--json", action="store_true", help="JSON output")
    _add_common(up)

    lp = sub.add_parser("lists", help="Manage product lists")
    _add_common(lp)
    lsub = lp.add_subparsers(dest="lists_cmd", required=True)
    c = lsub.add_parser("create", help="Create list (idempotent by name)")
    c.add_argument("--name", required=True)
    _add_common(c)
    ll = lsub.add_parser("list", help="List lists")
    ll.add_argument("--json", action="store_true", help="JSON output")
    _add_common(ll)
    a = lsub.add_parser("add", help="Add product to list")
    a.add_argument("--list", required=True, help="List name or ID")
    a.add_argument("--item-id", required=True)
    _add_common(a)
    r = lsub.add_parser("remove", help="Remove product from list")
    r.add_argument("--list", required=True)
    r.add_argument("--item-id", required=True)
    _add_common(r)
    d = lsub.add_parser("delete", help="Delete list")
    d.add_argument("--name", required=True, help="List name or ID")
    _add_common(d)

    lib = lsub.add_parser("library", help="Show products and list memberships as JSON")
    lib.add_argument("--json", action="store_true")
    _add_common(lib)
    order = lsub.add_parser("sort", help="Save list sort order")
    order.add_argument("--list", required=True)
    order.add_argument("--sort", required=True, choices=[*SORT_CHOICES, "manual"])
    order.add_argument("--json", action="store_true")
    _add_common(order)
    move = lsub.add_parser("reorder", help="Save manual product order")
    move.add_argument("--list", required=True)
    move.add_argument("--items", required=True, help="JSON array of product IDs")
    move.add_argument("--json", action="store_true")
    _add_common(move)
    nav_order = lsub.add_parser("reorder-lists", help="Save list navigation order")
    nav_order.add_argument("--lists", required=True, help="JSON array of list IDs (- for stdin)")
    nav_order.add_argument("--json", action="store_true")
    _add_common(nav_order)

    wp = sub.add_parser("web", help="Start local Web UI")
    wp.add_argument("--host", default="127.0.0.1", help="Listen address (default: 127.0.0.1)")
    wp.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")
    wp.add_argument("--output-dir", default=None, help="Library output folder")
    _add_common(wp)

    dp2 = sub.add_parser("doctor", help="Check environment, database and dependencies")
    dp2.add_argument(
        "--library", default=None, help="Library output folder (default: BOOTH-Reader-Library)"
    )
    # Without this the cookie check always inspected the default jar, so a user
    # who authenticated with `--cookie-path` was told "not logged in" and told
    # to log in again -- they were logged in, in the place they had chosen.
    dp2.add_argument("--cookie-path", default=None, help="Cookie file to check")
    dp2.add_argument("--json", action="store_true", help="JSON output")
    _add_common(dp2)

    rp = sub.add_parser("rpc", help="Internal: persistent JSON-line worker")
    rp.add_argument("--max-workers", type=int, default=1, help="Reserved (always 1, sequential)")
    _add_common(rp)

    return p


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _display_width(text: str) -> int:
    """Terminal column count, counting CJK/emoji as two columns.

    The tables are read by humans looking at Japanese titles; measuring string
    length instead would misalign every column containing kana or kanji.
    """
    width = 0
    for ch in str(text):
        if unicodedata.combining(ch):
            continue
        width += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return width


def _pad(text: str, width: int) -> str:
    return str(text) + " " * max(0, width - _display_width(text))


def _print_table(rows: list[dict[str, Any]], cols: list[str], maxcol: int = 80) -> None:
    if not rows:
        print("(0 rows)")
        return
    # Widths are measured from the *truncated* cell so the header and the
    # body line up; the previous version measured full values and then cut
    # them, which shifted every following column.
    cells = [[str(r.get(c, "") or "")[:maxcol] for c in cols] for r in rows]
    widths = [
        max(_display_width(c), *(_display_width(row[i]) for row in cells))
        for i, c in enumerate(cols)
    ]
    print(" | ".join(_pad(c, widths[i]) for i, c in enumerate(cols)))
    print("-+-".join("-" * w for w in widths))
    for row in cells:
        print(" | ".join(_pad(v, widths[i]) for i, v in enumerate(row)))


def _print_json(obj: object) -> None:
    """Write pure JSON to stdout, ASCII-escaped.

    ``ensure_ascii=True`` is deliberate: a Japanese console pipes stdout through
    cp932, and raw UTF-8 there corrupts the payload for the UTF-8 consumer on
    the other end. Escaped JSON decodes to identical text in every encoding.
    """
    print(json.dumps(obj, ensure_ascii=True, default=str))


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------


def _cmd_init_db(db_path: str) -> int:
    from core.db import init_db, schema_version, table_names

    init_db(db_path)
    print(
        f"initialized {db_path}: {','.join(table_names(db_path))} "
        f"(schema v{schema_version(db_path)})"
    )
    return 0


def _cmd_auth(args: argparse.Namespace) -> int:
    from core import auth as auth_mod

    cpath = getattr(args, "cookie_path", None)
    if args.auth_cmd == "import":
        payload = sys.stdin.read(1_048_577)
        if len(payload) > 1_048_576:
            raise ValueError("Cookie file must be at most 1 MB")
        try:
            raw_cookies: object = json.loads(payload)
        except ValueError as e:
            raise ValueError("Invalid cookie JSON") from e
        if isinstance(raw_cookies, dict):
            raw_cookies = cast("dict[str, Any]", raw_cookies).get("cookies")
        if not isinstance(raw_cookies, list) or not raw_cookies:
            raise ValueError("Provide BOOTH / pixiv cookie JSON")
        cookies: list[dict[str, Any]] = []
        for entry in cast("list[object]", raw_cookies):
            if not isinstance(entry, dict):
                raise ValueError("Provide BOOTH / pixiv cookie JSON")
            c = cast("dict[str, Any]", entry)
            domain = c.get("domain")
            if (
                not isinstance(c.get("name"), str)
                or not isinstance(c.get("value"), str)
                or not isinstance(domain, str)
            ):
                raise ValueError("Provide BOOTH / pixiv cookie JSON")
            host = domain.lstrip(".")
            if (
                host != "booth.pm"
                and not host.endswith(".booth.pm")
                and host != "pixiv.net"
                and not host.endswith(".pixiv.net")
            ):
                raise ValueError("Provide BOOTH / pixiv cookie JSON")
            cookies.append(dict(c, expires=c.get("expires", c.get("expirationDate", -1))))
        auth_mod.save_cookies(cookies, cpath)
        _print_json({"ok": True, "count": len(cookies)})
        return 0
    if args.auth_cmd == "login":
        p = auth_mod.login(
            headless=args.headless,
            path=cpath,
            timeout_s=max(30, int(getattr(args, "timeout", 600))),
        )
        print(f"login ok: {p}")
        return 0
    if args.auth_cmd == "logout":
        ok = auth_mod.logout(cpath)
        print("logout ok" if ok else "No cookies")
        return 0
    if args.auth_cmd == "status":
        info = auth_mod.status(cpath, verify_network=args.verify_network)
        if getattr(args, "json", False):
            _print_json(
                {
                    "ok": True,
                    "count": info.get("count", 0),
                    "path": info.get("path", ""),
                    "http_status": info.get("http_status"),
                    "revision": Path(info["path"]).stat().st_mtime_ns,
                }
            )
        else:
            print(f"auth ok: count={info['count']} path={info['path']}")
        return 0
    return 2


def _cmd_purchases(args: argparse.Namespace, db_path: str) -> int:
    from core import purchases as purch_mod
    from core.db import get_connection

    updated = None
    if args.update_db:
        updated = purch_mod.update_from_network(db_path, cookie_path=args.cookie_path)
        if not getattr(args, "json", False):
            print(f"updated {updated} items")
    conn = get_connection(db_path)
    try:
        rows = purch_mod.list_purchases(conn, limit=args.limit)
    finally:
        conn.close()

    csv_out = None
    if args.csv:
        out = purch_mod.export_csv(rows, args.csv)
        csv_out = str(out)
        if not getattr(args, "json", False):
            print(f"csv -> {out} ({len(rows)} rows)")

    if getattr(args, "json", False):
        payload: dict[str, Any] = {"count": len(rows), "items": rows}
        if updated is not None:
            payload["updated"] = updated
        if csv_out is not None:
            payload["csv"] = csv_out
        _print_json(payload)
    else:
        _print_table(rows, ["item_id", "title", "shop", "purchase_date", "price"])
    return 0


def _cmd_download(args: argparse.Namespace, db_path: str, parser: argparse.ArgumentParser) -> int:
    # Mutually exclusive / required selection is a usage error.
    if args.item_id and args.all:
        parser.error("--item-id and --all are mutually exclusive")
    if not args.item_id and not args.all:
        parser.error("Specify --item-id or --all")

    from core import download as dl_mod
    from core.db import get_connection

    conc = dl_mod.check_concurrent(args.concurrent)
    if args.all:
        conn = get_connection(db_path)
        try:
            ids = [r["item_id"] for r in conn.execute("SELECT item_id FROM items").fetchall()]
        finally:
            conn.close()
        if not ids:
            if args.json:
                _print_json({"ok": [], "failed": [], "ok_count": 0, "failed_count": 0})
            else:
                print("(0 rows: run purchases list --update-db first)")
            return 0
    else:
        ids = [args.item_id]

    res = dl_mod.download_many(
        ids,
        db_path,
        DEFAULT_LIBRARY,
        cookie_path=args.cookie_path,
        output_dir=args.output_dir,
        concurrent=conc,
        extract=not args.no_extract,
        force=args.force,
    )
    ok_n = len(res.get("ok", []))
    failed = res.get("failed", [])
    if getattr(args, "json", False):
        _print_json(
            {
                "ok": res.get("ok", []),
                "failed": failed,
                "ok_count": ok_n,
                "failed_count": len(failed),
            }
        )
    else:
        print(f"done ok={ok_n} failed={len(failed)}")
        for f in failed:
            print(f"FAILED {f.get('item_id')}: {f.get('error')}", file=sys.stderr)
    return 1 if failed else 0


def _cmd_downloads(args: argparse.Namespace, db_path: str) -> int:
    if args.downloads_cmd == "cleanup":
        from core.db import get_connection
        from core.download import cleanup_partials
        from core.library_lock import library_lock

        with library_lock(args.output_dir):
            conn = get_connection(db_path)
            try:
                protected: list[Path] = []
                for row in conn.execute("SELECT path FROM downloads WHERE path != ''"):
                    path = Path(row["path"])
                    protected.append(path)
                    # The library may have moved while the ledger kept its old root.
                    if path.parent.name == "downloads":
                        protected.append(
                            Path(args.output_dir)
                            / path.parent.parent.name
                            / "downloads"
                            / path.name
                        )
                removed = cleanup_partials(args.output_dir, protected, downloads_only=True)
            finally:
                conn.close()
        if args.json:
            _print_json({"ok": True, "removed": removed})
        else:
            print(f"removed {removed} partial files")
        return 0

    from core.db import get_connection

    limit = max(1, min(int(args.limit or 200), 1000))
    conn = get_connection(db_path)
    try:
        if args.status:
            rows = [
                dict(r)
                for r in conn.execute(
                    "SELECT item_id,file_name,path,status,sha256,downloaded_at FROM downloads"
                    " WHERE status=? ORDER BY downloaded_at DESC LIMIT ?",
                    (args.status, limit),
                ).fetchall()
            ]
        else:
            rows = [
                dict(r)
                for r in conn.execute(
                    "SELECT item_id,file_name,path,status,sha256,downloaded_at FROM downloads"
                    " ORDER BY downloaded_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            ]
    finally:
        conn.close()
    if getattr(args, "json", False):
        _print_json({"count": len(rows), "downloads": rows, "status": args.status})
    else:
        _print_table(rows, ["item_id", "file_name", "status", "sha256", "downloaded_at"])
    return 0


def _cmd_unclassified(args: argparse.Namespace, db_path: str) -> int:
    from core import lists as lists_mod
    from core.db import get_connection

    conn = get_connection(db_path)
    try:
        rows = lists_mod.get_unclassified(conn, sort=args.sort, limit=args.limit)
    finally:
        conn.close()

    csv_out = None
    if args.csv:
        from core.purchases import export_csv

        out = export_csv(rows, args.csv)
        csv_out = str(out)
        if not getattr(args, "json", False):
            print(f"csv -> {out} ({len(rows)} rows)")

    if getattr(args, "json", False):
        payload: dict[str, Any] = {"sort": args.sort, "count": len(rows), "items": rows}
        if csv_out is not None:
            payload["csv"] = csv_out
        _print_json(payload)
    else:
        _print_table(rows, ["item_id", "title", "shop", "purchase_date", "price"])
    return 0


def _cmd_lists(args: argparse.Namespace, db_path: str) -> int:
    from core import lists as lists_mod
    from core.db import get_connection

    conn = get_connection(db_path)
    try:
        if args.lists_cmd == "library":
            _print_json(lists_mod.library(conn))
        elif args.lists_cmd == "sort":
            lists_mod.set_sort(conn, args.list, args.sort)
            _print_json({"ok": True})
        elif args.lists_cmd == "reorder":
            try:
                raw_items: object = json.loads(
                    sys.stdin.read(4_000_001) if args.items == "-" else args.items
                )
            except ValueError as e:
                raise ValueError("Invalid product ID array") from e
            if not isinstance(raw_items, list):
                raise ValueError("Invalid product ID array")
            item_ids = cast("list[object]", raw_items)
            if any(not isinstance(i, str) for i in item_ids):
                raise ValueError("Invalid product ID array")
            lists_mod.reorder(conn, args.list, cast("list[str]", item_ids))
            _print_json({"ok": True})
        elif args.lists_cmd == "reorder-lists":
            try:
                raw_lists: object = json.loads(
                    sys.stdin.read(4_000_001) if args.lists == "-" else args.lists
                )
            except ValueError as e:
                raise ValueError("Invalid list ID array") from e
            if not isinstance(raw_lists, list):
                raise ValueError("Invalid list ID array")
            lists_mod.reorder_lists(conn, cast("list[int]", raw_lists))
            _print_json({"ok": True})
        elif args.lists_cmd == "create":
            lid = lists_mod.create_list(conn, args.name)
            print(f"created list {args.name} (id={lid})")
        elif args.lists_cmd == "list":
            rows = lists_mod.list_lists(conn)
            if getattr(args, "json", False):
                _print_json({"count": len(rows), "lists": rows})
            else:
                for row in rows:
                    print(f"{row['list_id']}\t{row['name']}")
                if not rows:
                    print("(0 rows)")
        elif args.lists_cmd == "add":
            lists_mod.add_member(conn, args.list, args.item_id)
            print(f"added {args.item_id} -> {args.list}")
        elif args.lists_cmd == "remove":
            n = lists_mod.remove_member(conn, args.list, args.item_id)
            print(f"removed {n} memberships")
        elif args.lists_cmd == "delete":
            n = lists_mod.delete_list(conn, args.name)
            print(f"deleted {n} lists")
    finally:
        conn.close()
    return 0


def _cmd_doctor(args: argparse.Namespace, db_path: str) -> int:
    """Report on install health: deps, database, cookies, library, disk."""
    import shutil

    from core.auth import has_cookies
    from core.version import __version__

    library = Path(getattr(args, "library", None) or DEFAULT_LIBRARY)
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str, *, fatal: bool = False) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail, "fatal": fatal})

    add("version", True, __version__)
    add("python", sys.version_info >= (3, 10), f"{sys.version.split()[0]} ({sys.executable})")

    for module, required in (
        ("httpx", True),
        ("bs4", True),
        ("fastapi", True),
        ("uvicorn", True),
        ("pydantic", True),
        ("playwright", True),
    ):
        try:
            mod = __import__(module)
            ver = getattr(mod, "__version__", "?")
        except ImportError:
            add(f"dep:{module}", False, "not installed", fatal=required)
        else:
            add(f"dep:{module}", True, str(ver))

    # The runtime manifest names the concrete engine (WebView2 in the shipped
    # bundle) so doctor reports exactly what `auth login` will launch.
    try:
        engine = json.loads((BASE_DIR / "portable-manifest.json").read_text(encoding="utf-8"))[
            "browser"
        ]["engine"]
    except (OSError, KeyError, ValueError):
        engine = "chromium"

    # The Playwright package alone is not enough: the browser runtime is
    # restored from vendor/ by start.bat. Detecting it here is far better than
    # letting it surface as a confusing launch failure in `auth login`.
    try:
        from playwright.sync_api import sync_playwright

        try:
            with sync_playwright() as pw:
                from core.browser import launch_browser

                browser = launch_browser(pw, headless=True)
                browser.close()
            add(f"browser:{engine}", True, "installed")
        except Exception as e:  # noqa: BLE001
            add(
                f"browser:{engine}",
                False,
                f"Cannot launch browser. Run `start.bat --repair` ({type(e).__name__})",
                fatal=True,
            )
    except ImportError:
        add(f"browser:{engine}", False, "playwright not installed", fatal=True)

    # Portable layout: the interpreter and the browser should travel with the
    # folder. Informational (fatal=False): a system-wide setup still runs, but
    # a moved or copied folder without these is the classic "worked yesterday"
    # failure, so doctor names it before it bites.
    try:
        exe_inside = Path(sys.executable).resolve().is_relative_to(BASE_DIR.resolve())
    except (OSError, ValueError):
        exe_inside = False
    try:
        from tools.portable import venv_base_home

        _base = venv_base_home(BASE_DIR)
        _base_inside = True if _base is None else _base.resolve().is_relative_to(BASE_DIR.resolve())
    except (OSError, ValueError):
        _base_inside = True
    add(
        "portable:venv",
        exe_inside,
        f"{sys.executable} "
        + ("(repo-local)" if exe_inside else "(outside repo: run start.bat to create .venv)")
        + ("" if _base_inside else " [base outside repo: run start.bat --repair]"),
    )
    browsers = effective_browsers_path(BASE_DIR)
    try:
        browsers_inside = browsers.resolve().is_relative_to(BASE_DIR.resolve())
    except (OSError, ValueError):
        browsers_inside = False
    if engine == "webview2":
        has_repo_browser = (browsers / "webview2/msedgewebview2.exe").is_file()
    else:
        has_repo_browser = any(browsers.glob("chromium*")) if browsers.is_dir() else False
    add(
        "portable:browsers",
        browsers_inside,
        f"{browsers} " + ("(installed)" if has_repo_browser else "(not installed: run start.bat)"),
    )

    db = Path(db_path)
    add("db:path", True, str(db))
    if db.exists():
        try:
            from core.db import SCHEMA_VERSION, check_integrity, schema_version, table_names

            expected = {"items", "purchases", "downloads", "lists", "list_members"}
            present = set(table_names(db))
            add(
                "db:tables", expected <= present, ",".join(sorted(present)) or "(empty)", fatal=True
            )
            version = schema_version(db)
            add(
                "db:schema",
                version == SCHEMA_VERSION,
                f"v{version} (required: v{SCHEMA_VERSION})",
                fatal=True,
            )
            report = check_integrity(db)
            add(
                "db:integrity",
                report["ok"],
                "ok"
                if report["ok"]
                else f"{report['integrity']} / FK={len(report['foreign_key_violations'])}",
                fatal=True,
            )
        except Exception as e:  # noqa: BLE001
            add("db:open", False, f"{type(e).__name__}: {e}", fatal=True)
    else:
        add("db:exists", False, "not created; run `start.bat init-db`", fatal=False)

    cookie_file = Path(getattr(args, "cookie_path", None) or (BASE_DIR / "data" / "cookies.json"))
    have_jar = has_cookies(cookie_file)
    add(
        "cookies",
        have_jar,
        f"{cookie_file} " + ("present" if have_jar else "missing; run `start.bat auth login`"),
    )

    try:
        library.mkdir(parents=True, exist_ok=True)
        import tempfile

        with tempfile.TemporaryFile(dir=library) as probe:
            probe.write(b"ok")
        free = shutil.disk_usage(str(library)).free
        add("library", True, f"{library} ({free / 1024**3:.1f} GB free)")
    except OSError as e:
        add("library", False, f"{library}: {type(e).__name__}", fatal=True)

    ok = all(c["ok"] for c in checks if c["fatal"])
    warnings = [c for c in checks if not c["ok"] and not c["fatal"]]

    if getattr(args, "json", False):
        _print_json({"ok": ok, "checks": checks, "warnings": len(warnings)})
    else:
        for c in checks:
            mark = "OK  " if c["ok"] else ("FAIL" if c["fatal"] else "WARN")
            print(f"[{mark}] {c['name']:16} {c['detail']}")
        print()
        print(
            "All checks passed"
            if ok and not warnings
            else (
                "Critical checks failed" if not ok else f"{len(warnings)} warnings (can continue)"
            )
        )
    return 0 if ok else 1


def _cmd_web(args: argparse.Namespace, db_path: str) -> int:
    from web.app import run

    run(
        host=args.host,
        port=int(args.port),
        db_path=db_path,
        library_root=getattr(args, "output_dir", None) or DEFAULT_LIBRARY,
    )
    return 0


# ---------------------------------------------------------------------------
# RPC worker
# ---------------------------------------------------------------------------


def _run_capture(argv: list[str]) -> tuple[int, str, str, Any]:
    """Run a command in-process, capturing its streams.

    Returns ``(returncode, stdout, stderr, json_payload)``.

    Reusing :func:`main` means the worker and the one-shot subprocess execute
    *exactly* the same code path, so the two front ends cannot drift.
    Logging handlers keep their own reference to the real stderr, so log
    records are not swallowed into the buffer.
    """
    out_buffer = io.StringIO()
    err_buffer = io.StringIO()
    with redirect_stdout(out_buffer), redirect_stderr(err_buffer):
        try:
            code = main(argv, _already_configured=True)
        except SystemExit as e:  # parser.error() and friends
            code = int(e.code) if isinstance(e.code, int) else 2

    out_text = out_buffer.getvalue()
    err_text = err_buffer.getvalue()
    payload: Any = None
    if "--json" in argv:
        for line in reversed(out_text.strip().splitlines()):
            try:
                payload = json.loads(line)
                break
            except ValueError:
                continue
    return code, out_text, err_text, payload


def _serve_rpc(db_path: str, level: str) -> int:
    """Serve newline-delimited JSON requests on stdin/stdout.

    Protocol
    --------
    Request:  ``{"id": 1, "args": ["unclassified", "--json"]}``
    Response: ``{"id": 1, "ok": true, "returncode": 0, "data": {...}}``
              ``{"id": 1, "ok": false, "returncode": 1, "error": "..."}``

    The worker exists so the Web UI does not pay a full interpreter start per
    request. Requests are served strictly one at a time, which also serialises
    database writes and removes any chance of interleaved stdout.
    """
    from core.logging_setup import setup_logging

    setup_logging(level)
    stdin = sys.stdin
    stdout = sys.stdout
    # The protocol is ASCII-only; reconfigure defensively in case the parent
    # did not set PYTHONUTF8.
    reconfigures: tuple[tuple[Any, dict[str, Any]], ...] = (
        (stdin, {"encoding": "utf-8", "errors": "replace"}),
        (stdout, {"encoding": "utf-8", "line_buffering": True}),
    )
    for stream, options in reconfigures:
        reconfigure = getattr(stream, "reconfigure", None)
        # A stream that cannot be reconfigured (a test double, for instance)
        # is still usable with its default encoding.
        if reconfigure is None:
            continue
        with contextlib.suppress(ValueError, OSError):
            reconfigure(**options)

    while True:
        line = stdin.readline()
        if not line:
            return 0
        line = line.strip()
        if not line:
            continue
        try:
            request: object = json.loads(line)
        except ValueError:
            _rpc_emit(
                stdout, {"id": None, "ok": False, "returncode": 2, "error": "invalid JSON request"}
            )
            continue
        if not isinstance(request, dict):
            _rpc_emit(
                stdout,
                {
                    "id": None,
                    "ok": False,
                    "returncode": 2,
                    "error": "request must be a JSON object",
                },
            )
            continue
        body = cast("dict[str, Any]", request)
        request_id = body.get("id")
        raw_argv = body.get("args")
        if not isinstance(raw_argv, list) or not all(
            isinstance(a, str) for a in cast("list[object]", raw_argv)
        ):
            _rpc_emit(
                stdout,
                {
                    "id": request_id,
                    "ok": False,
                    "returncode": 2,
                    "error": "args must be a list of strings",
                },
            )
            continue
        argv = cast("list[str]", raw_argv)
        # Never let a request reach a subcommand's own --db: the worker's DB is
        # authoritative for its lifetime.
        filtered = [a for i, a in enumerate(argv) if not (a == "--db" or _is_db_value(argv, i))]
        stdin_command = (
            filtered[:2] == ["auth", "import"]
            or (
                filtered[:2] == ["lists", "reorder"]
                and any(filtered[i : i + 2] == ["--items", "-"] for i in range(len(filtered)))
            )
            or (
                filtered[:2] == ["lists", "reorder-lists"]
                and any(filtered[i : i + 2] == ["--lists", "-"] for i in range(len(filtered)))
            )
        )
        if any(a in {"rpc", "web", "login"} for a in filtered[:2]) or stdin_command:
            _rpc_emit(
                stdout,
                {
                    "id": request_id,
                    "ok": False,
                    "returncode": 2,
                    "error": "interactive or recursive commands are not supported by RPC",
                },
            )
            continue
        started = time.perf_counter()
        try:
            code, out_text, err_text, payload = _run_capture([*filtered, "--db", db_path])
        except Exception as e:  # noqa: BLE001 - a bad request must not kill the worker
            _rpc_emit(
                stdout,
                {
                    "id": request_id,
                    "ok": False,
                    "returncode": 1,
                    "error": f"{type(e).__name__}: {e}",
                },
            )
            continue
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        response: dict[str, Any] = {
            "id": request_id,
            "ok": code == 0,
            "returncode": code,
            "data": payload,
            "stdout": out_text[-4000:],
            "elapsed_ms": elapsed_ms,
        }
        if code != 0:
            response["error"] = _last_line(err_text) or _last_line(out_text) or f"exit {code}"
            response["stderr"] = err_text[-4000:]
        _rpc_emit(stdout, response)


def _is_db_value(argv: list[str], index: int) -> bool:
    return index > 0 and argv[index - 1] == "--db"


def _last_line(text: str) -> str:
    for line in reversed((text or "").strip().splitlines()):
        if line.strip():
            return line.strip()[:1000]
    return ""


def _rpc_emit(stdout: Any, payload: dict[str, Any]) -> None:
    stdout.write(json.dumps(payload, ensure_ascii=True, default=str) + "\n")
    stdout.flush()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


# A flat command table is clearer here than a dispatch table would be.
def _dispatch(  # noqa: PLR0911
    args: argparse.Namespace, db_path: str, parser: argparse.ArgumentParser
) -> int:
    command = args.cmd
    if command == "init-db":
        return _cmd_init_db(db_path)
    if command == "auth":
        return _cmd_auth(args)
    if command == "purchases":
        return _cmd_purchases(args, db_path)
    if command == "download":
        return _cmd_download(args, db_path, parser)
    if command == "downloads":
        return _cmd_downloads(args, db_path)
    if command == "unclassified":
        return _cmd_unclassified(args, db_path)
    if command == "lists":
        return _cmd_lists(args, db_path)
    if command == "doctor":
        return _cmd_doctor(args, db_path)
    if command == "web":
        return _cmd_web(args, db_path)
    parser.print_help()
    return 2


def main(  # noqa: PLR0911 - a flat command table reads better than a dispatch map
    argv: list[str] | None = None,
    _already_configured: bool = False,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    db_path, level = _resolve(args)

    from core.errors import BoothError, exit_code_for
    from core.logging_setup import redact, setup_logging

    if not _already_configured:
        setup_logging(level)

    if getattr(args, "version", False):
        from core.version import __version__

        print(f"BOOTH-Reader {__version__}")
        return 0
    if args.cmd is None:
        print(
            "No command specified. Help: start.bat help",
            file=sys.stderr,
        )
        parser.print_help()
        return 2
    if args.cmd == "rpc":
        return _serve_rpc(db_path, level)

    try:
        return _dispatch(args, db_path, parser)
    except BoothError as e:
        print(redact(f"ERROR {e}"), file=sys.stderr)
        return exit_code_for(e)
    except ValueError as e:
        print(redact(f"ERROR {e}"), file=sys.stderr)
        return 2
    except sqlite3.Error as e:
        from core.errors import BoothDatabaseError

        print(f"ERROR {BoothDatabaseError(db_path, type(e).__name__)}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        return 130
    except Exception as e:  # noqa: BLE001 - never surface a raw traceback
        from core.logging_setup import get_logger

        get_logger("booth_reader.cli").error(
            "unhandled error in %s: %s", args.cmd, type(e).__name__
        )
        print(
            redact(f"ERROR Unexpected error: {type(e).__name__}: {e}"),
            file=sys.stderr,
        )
        return 1
    finally:
        if args.cmd != "web":
            _shutdown(db_path, _cmd_writes(args))


# Read-only commands skip the WAL checkpoint: folding the WAL back in is real
# I/O and would tax every Web UI refresh for no benefit.
def _cmd_writes(args: argparse.Namespace) -> bool:
    command = args.cmd
    if command == "lists":
        return args.lists_cmd not in {"list", "library"}
    if command in ("init-db", "download"):
        return True
    if command == "purchases":
        return bool(getattr(args, "update_db", False))
    return False


def _shutdown(db_path: str, checkpoint_db: bool = True) -> None:
    """Release per-thread HTTP clients and optionally fold the WAL back in."""
    try:
        from core import net

        net.close_clients()
    except Exception as e:  # noqa: BLE001
        print(f"warn: client cleanup failed: {type(e).__name__}", file=sys.stderr)
    if not checkpoint_db:
        return
    try:
        from core.db import checkpoint

        if Path(db_path).exists():
            checkpoint(db_path)
    except Exception as e:  # noqa: BLE001
        print(f"warn: db checkpoint failed: {type(e).__name__}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
