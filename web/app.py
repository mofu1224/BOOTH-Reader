"""Loopback-only presentation layer. All processing travels through the CLI."""

from __future__ import annotations

import builtins
import json
import logging
import threading
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from redaction import redact

from . import cli_bridge as bridge
from .ui import render_index

log = logging.getLogger("booth_reader.web")
_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = str(_REPO_ROOT / "app.db")
DEFAULT_LIBRARY_ROOT = str(_REPO_ROOT / "BOOTH-Reader-Library")
VALID_SORTS = bridge.VALID_SORTS
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "[::1]", "testserver"]
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class DownloadReq(BaseModel):
    item_id: str | None = Field(default=None, max_length=128)
    all: bool = False
    concurrent: int = Field(default=3, ge=1, le=5)


class ListsReq(BaseModel):
    list_ids: builtins.list[int] = Field(default_factory=builtins.list[int], max_length=20000)
    item_ids: builtins.list[str] = Field(default_factory=builtins.list[str], max_length=20000)
    action: str = Field(pattern="^(create|add|remove|delete|sort|reorder|reorder-lists)$")
    name: str | None = Field(default=None, max_length=128)
    list: str | None = Field(default=None, max_length=128)
    item_id: str | None = Field(default=None, max_length=128)
    sort: str = Field(default="newest", pattern="^(newest|oldest|name|shop|manual)$")


class CookieReq(BaseModel):
    content: str = Field(min_length=1, max_length=1_048_576)


def _err_payload(exc: Exception) -> tuple[int, dict[str, Any]]:
    safe = redact(str(exc))
    if isinstance(exc, bridge.CliAuthError):
        return 401, {
            "ok": False,
            "error": safe,
            "code": "BOOTH_AUTH_REQUIRED",
            "hint": "Cookieを登録するか、`start.bat auth login` で再ログインしてください",
        }
    if isinstance(exc, bridge.CliLayoutChangedError):
        return 502, {
            "ok": False,
            "error": safe,
            "code": "BOOTH_LAYOUT_CHANGED",
            "hint": "BOOTH側のページ構成が変わった可能性があります。"
            "BOOTH-Readerを更新してから、もう一度お試しください。",
        }
    if isinstance(exc, bridge.CliBridgeError):
        if exc.returncode == 124:
            return 504, {"ok": False, "error": safe, "code": "TIMEOUT"}
        if exc.returncode == 2:
            return 400, {"ok": False, "error": safe, "code": "BAD_REQUEST"}
        return 500, {"ok": False, "error": safe}
    log.error("unhandled web error: %s", type(exc).__name__)
    return 500, {"ok": False, "error": f"予期しないエラーが発生しました ({type(exc).__name__})"}


def _error(exc: Exception) -> JSONResponse:
    code, body = _err_payload(exc)
    return JSONResponse(body, status_code=code)


class OriginGuard:
    """Reject cross-origin writes and cross-site forms on the local server."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope.get("method") in UNSAFE_METHODS:
            headers = {
                k.decode("latin-1").lower(): v.decode("latin-1")
                for k, v in scope.get("headers", [])
            }
            origin = headers.get("origin")
            if (
                origin and origin != f"{scope.get('scheme', 'http')}://{headers.get('host', '')}"
            ) or headers.get("sec-fetch-site") == "cross-site":
                response = JSONResponse(
                    {"ok": False, "error": "cross-origin request rejected", "code": "BAD_ORIGIN"},
                    status_code=403,
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


class PrivateResponseHeaders:
    """Purchase and authentication responses must not be cached by the browser."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def private_send(message: Any) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() not in {b"cache-control", b"referrer-policy"}
                ] + [(b"cache-control", b"no-store"), (b"referrer-policy", b"no-referrer")]
            await send(message)

        await self.app(scope, receive, private_send)


def create_app(
    db_path: str | Path = DEFAULT_DB_PATH,
    library_root: str | Path = DEFAULT_LIBRARY_ROOT,
    cli_path: str | Path | None = None,
    python_exe: str | Path | None = None,
) -> FastAPI:
    db, root = str(db_path), str(library_root)
    link = bridge.Bridge(db, cli_path=cli_path, python_exe=python_exe)
    job_lock = threading.Lock()
    sync_lock = threading.Lock()
    download_state: dict[str, Any] = {"running": False, "ok": None, "error": ""}

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:  # noqa: ARG001
        log.info("web ui starting db=%s library=%s", db, root)
        try:
            yield
        finally:
            link.close()
            log.info("web ui stopped")

    app = FastAPI(title="BOOTH-Reader", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.add_middleware(OriginGuard)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(ALLOWED_HOSTS))
    app.add_middleware(PrivateResponseHeaders)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Any, exc: RequestValidationError) -> JSONResponse:
        # Pydantic's input/ctx can contain a complete Cookie jar or request body.
        errors = [
            {"type": error["type"], "loc": error["loc"], "msg": "入力形式が不正です"}
            for error in exc.errors()
        ]
        return JSONResponse({"detail": errors}, status_code=422)

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "transport": link.transport, "download": dict(download_state)}

    @app.get("/third-party-terms", response_class=PlainTextResponse)
    def third_party_terms() -> str:
        documents = [
            _REPO_ROOT / "THIRD_PARTY_TERMS.md",
            _REPO_ROOT / "THIRD_PARTY_LICENSES/browser/15bc46c641bc-WEBVIEW2-RUNTIME-LICENSE.txt",
            _REPO_ROOT / "THIRD_PARTY_LICENSES/browser/0af8f1b80751-webview2-sdk_LICENSE.txt",
            _REPO_ROOT / "THIRD_PARTY_LICENSES/CPython-3.12.13/886a0ead2d89-python_LICENSE.txt",
        ]
        return "\n\n".join(path.read_text(encoding="utf-8") for path in documents)

    @app.get("/library")
    def get_library() -> Any:
        try:
            return bridge.get_library(link)
        except Exception as e:  # noqa: BLE001
            return _error(e)

    @app.get("/purchases")
    def get_purchases(limit: int = Query(200, ge=1, le=1000)) -> Any:
        try:
            data = bridge.get_purchases(link, limit=limit)
            data["downloads"] = bridge.get_downloads(link, limit=200).get("downloads", [])
            return data
        except Exception as e:  # noqa: BLE001
            return _error(e)

    @app.get("/unclassified")
    def get_unclassified(
        sort: str = Query("newest"), limit: int = Query(200, ge=1, le=1000)
    ) -> Any:
        try:
            return bridge.get_unclassified(link, sort=sort, limit=limit)
        except Exception as e:  # noqa: BLE001
            return _error(e)

    @app.get("/downloads")
    def get_downloads(limit: int = Query(200, ge=1, le=1000), status: str | None = None) -> Any:
        try:
            return bridge.get_downloads(link, limit=limit, status=status)
        except Exception as e:  # noqa: BLE001
            return _error(e)

    @app.get("/lists")
    def get_lists() -> Any:
        try:
            return bridge.get_lists(link)
        except Exception as e:  # noqa: BLE001
            return _error(e)

    @app.get("/auth/status")
    def get_auth_status() -> Any:
        try:
            return bridge.get_auth_status(link)
        except Exception as e:  # noqa: BLE001
            return _error(e)

    @app.post("/auth/import")
    def post_auth_import(req: CookieReq) -> Any:
        if not sync_lock.acquire(blocking=False):
            return JSONResponse({"ok": False, "error": "同期中です"}, status_code=409)
        try:
            return bridge.import_cookies(link, req.content)
        except Exception as e:  # noqa: BLE001
            return _error(e)
        finally:
            sync_lock.release()

    @app.post("/lists")
    def post_lists(req: ListsReq) -> Any:
        try:
            operations = {"create": bridge.lists_create, "delete": bridge.lists_delete}
            member_operations = {"add": bridge.lists_add, "remove": bridge.lists_remove}
            if req.action == "reorder-lists":
                return bridge.run_cli_once(
                    ["lists", "reorder-lists", "--lists", "-", "--json"],
                    db,
                    cli_path,
                    python_exe,
                    timeout=30,
                    stdin_text=json.dumps(req.list_ids),
                ).data
            if req.action in operations and req.name:
                return operations[req.action](link, req.name)
            if req.action in member_operations and req.list and req.item_id:
                return member_operations[req.action](link, req.list, req.item_id)
            if req.action in {"sort", "reorder"} and req.list:
                key = bridge.sanitize_list_name(req.list)
                argv = ["lists", req.action, "--list", key, "--json"]
                if req.action == "sort":
                    argv += ["--sort", req.sort]
                    result = link.run(argv, timeout=30)
                else:
                    ids = [bridge.sanitize_item_id(i) for i in req.item_ids]
                    argv += ["--items", "-"]
                    result = bridge.run_cli_once(
                        argv, db, cli_path, python_exe, timeout=30, stdin_text=json.dumps(ids)
                    )
                return result.data
            return JSONResponse(
                {"ok": False, "error": "リスト名・商品・操作を指定してください"}, status_code=400
            )
        except Exception as e:  # noqa: BLE001
            return _error(e)

    @app.post("/purchases/update")
    def post_purchases_update() -> Any:
        if not sync_lock.acquire(blocking=False):
            return JSONResponse({"ok": False, "error": "同期中です"}, status_code=409)
        try:
            return {"ok": True, **bridge.update_purchases(link)}
        except Exception as e:  # noqa: BLE001
            return _error(e)
        finally:
            sync_lock.release()

    @app.post("/downloads/cleanup")
    def post_downloads_cleanup() -> Any:
        if not job_lock.acquire(blocking=False):
            return JSONResponse({"ok": False, "error": "ダウンロード実行中です"}, status_code=409)
        try:
            return link.run_blocking(
                ["downloads", "cleanup", "--output-dir", root, "--json"], timeout=60
            ).data
        except Exception as e:  # noqa: BLE001
            return _error(e)
        finally:
            job_lock.release()

    def _run_download(item_id: str | None, all_items: bool, concurrent: int) -> None:
        try:
            result = bridge.run_download_blocking(
                link, item_id=item_id, all=all_items, concurrent=concurrent, output_dir=root
            )
            download_state.update(ok=result["ok"], error="")
        except Exception as e:  # noqa: BLE001
            _, body = _err_payload(e)
            safe = str(body["error"])[:2000]
            log.error("background download failed: %s", safe)
            download_state.update(ok=False, error=safe)
        finally:
            download_state["running"] = False
            job_lock.release()

    @app.post("/download")
    def post_download(req: DownloadReq, bg: BackgroundTasks) -> Any:
        try:
            bridge.download_argv(item_id=req.item_id, all=req.all, concurrent=req.concurrent)
            bridge.get_auth_status(link)
        except Exception as e:  # noqa: BLE001
            return _error(e)
        if not job_lock.acquire(blocking=False):
            return JSONResponse({"ok": False, "error": "ダウンロード実行中です"}, status_code=409)
        download_state.update(running=True, ok=None, error="")
        bg.add_task(_run_download, req.item_id, req.all, req.concurrent)
        return (
            {"ok": True, "all": True, "concurrent": req.concurrent}
            if req.all
            else {"ok": True, "queued": [req.item_id]}
        )

    @app.get("/", response_class=HTMLResponse)
    def index() -> Any:
        try:
            data = bridge.get_library(link)
            error = ""
        except Exception as e:  # noqa: BLE001
            data, error = {}, str(e)[:200]
        return HTMLResponse(
            render_index(data, error, library_path=root), media_type="text/html; charset=utf-8"
        )

    return app


def link_shutdown(db_path: str) -> None:
    try:
        bridge.run_cli_once(["init-db"], db_path, timeout=60)
    except Exception as e:  # noqa: BLE001
        log.warning("shutdown checkpoint skipped: %s", type(e).__name__)


def run(
    host: str = "127.0.0.1",
    port: int = 8000,
    db_path: str = DEFAULT_DB_PATH,
    library_root: str = DEFAULT_LIBRARY_ROOT,
    cli_path: str | Path | None = None,
    python_exe: str | Path | None = None,
) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Web UI は loopback アドレスのみで起動できます")
    if not 1 <= int(port) <= 65535:
        raise ValueError("port は1〜65535で指定してください")
    import uvicorn

    bridge.run_cli_once(["init-db"], db_path, cli_path=cli_path, python_exe=python_exe, timeout=60)
    app = create_app(db_path, library_root, cli_path=cli_path, python_exe=python_exe)
    log.info("serving on http://%s:%s", host, port)
    try:
        uvicorn.run(app, host=host, port=int(port), log_level="info", access_log=False)
    except KeyboardInterrupt:
        log.info("shutdown requested")
    finally:
        link_shutdown(db_path)
