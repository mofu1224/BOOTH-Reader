"""Private, checkout-owned IPC adapter for the macOS WebKit login host."""

from __future__ import annotations

import contextlib
import json
import queue
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any


class WebKitBrowser:
    def __init__(self, executable: Path, env: dict[str, str], *, headless: bool) -> None:
        args = [str(executable), *(["--headless"] if headless else [])]
        self.process = subprocess.Popen(  # noqa: S603 - fixed owned host
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self.responses: queue.Queue[dict[str, Any]] = queue.Queue()
        self.lock = threading.Lock()
        self.sequence = 0
        self.closed = False
        self.reader = threading.Thread(target=self._read, daemon=True, name="webkit-host-reader")
        self.reader.start()
        try:
            self.request("state", timeout=30)
        except BaseException:
            self.close()
            raise

    def _read(self) -> None:
        assert self.process.stdout is not None
        for line in self.process.stdout:
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    self.responses.put(value)
            except ValueError:
                continue

    def request(self, operation: str, *, timeout: float = 30, **fields: Any) -> Any:
        with self.lock:
            if self.closed or self.process.poll() is not None:
                raise RuntimeError("Private WebKit host is closed")
            self.sequence += 1
            assert self.process.stdin is not None
            self.process.stdin.write(
                json.dumps({"id": self.sequence, "op": operation, **fields}, ensure_ascii=True)
                + "\n"
            )
            self.process.stdin.flush()
            try:
                response = self.responses.get(timeout=timeout)
            except queue.Empty as error:
                raise TimeoutError("Private WebKit request timed out") from error
            if response.get("id") != self.sequence:
                raise RuntimeError("Private WebKit response ID mismatch")
            if response.get("error"):
                raise RuntimeError(str(response["error"]))
            return response.get("value")

    def new_context(self, **options: Any) -> WebKitContext:
        context = WebKitContext(self)
        if options.get("viewport"):
            context.new_page().set_viewport_size(options["viewport"])
        return context

    def new_page(self, **options: Any) -> WebKitPage:
        return self.new_context(**options).new_page()

    def close(self) -> None:
        if self.closed:
            return
        with contextlib.suppress(OSError, RuntimeError, TimeoutError):
            self.request("close", timeout=3)
        self.closed = True
        if self.process.stdin is not None:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=10)
        self.reader.join(timeout=5)
        if self.process.stdout is not None:
            self.process.stdout.close()

    def __enter__(self) -> WebKitBrowser:
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()


class WebKitContext:
    def __init__(self, browser: WebKitBrowser) -> None:
        self.browser = browser

    def new_page(self) -> WebKitPage:
        return WebKitPage(self.browser)

    def cookies(self) -> list[dict[str, Any]]:
        return list(self.browser.request("cookies"))

    def close(self) -> None:
        self.browser.close()


class WebKitPage:
    def __init__(self, browser: WebKitBrowser) -> None:
        self.browser = browser

    def goto(self, url: str, *, wait_until: str = "load", timeout: int = 30000) -> Any:
        if wait_until not in {"load", "domcontentloaded", "networkidle"}:
            raise ValueError("Unsupported WebKit navigation wait condition")
        result = self.browser.request("goto", url=url, timeout=timeout / 1000)
        return SimpleNamespace(status=result["status"])

    @property
    def url(self) -> str:
        return str(self.browser.request("state")["url"])

    def title(self) -> str:
        value = str(self.browser.request("state")["title"])
        if value:
            return value
        # WKWebView.title can stay empty right after load on some macOS versions.
        return str(self.browser.request("evaluate", script="document.title") or "")

    def evaluate(self, script: str) -> Any:
        return self.browser.request("evaluate", script=script)

    def set_viewport_size(self, viewport: dict[str, Any]) -> None:
        self.browser.request(
            "resize", width=float(viewport["width"]), height=float(viewport["height"])
        )

    def locator(self, selector: str) -> WebKitLocator:
        return WebKitLocator(self, selector)


class WebKitLocator:
    def __init__(self, page: WebKitPage, selector: str) -> None:
        self.page, self.selector = page, selector

    def count(self) -> int:
        return int(
            self.page.evaluate(
                "document.querySelectorAll(" + json.dumps(self.selector) + ").length"
            )
        )
