"""Exercise the delivered private host, including HttpOnly cookie isolation."""

import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="macOS system WebKit")


def test_native_host_navigation_viewport_cookies_and_private_session():
    from playwright.sync_api import sync_playwright

    from core.browser import launch_browser

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'<title>private-host</title><div class="product">fixture</div>'
            self.send_response(200)
            self.send_header(
                "Set-Cookie", "synthetic-session=fixture; HttpOnly; SameSite=Lax; Path=/"
            )
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with sync_playwright() as playwright:
            browser = launch_browser(playwright, headless=True)
            process = browser.process
            try:
                context = browser.new_context()
                page = context.new_page()
                url = f"http://127.0.0.1:{server.server_port}/"
                assert page.goto(url).status == 200
                assert page.url == url
                assert page.title() == "private-host"
                assert page.locator(".product").count() == 1
                page.set_viewport_size({"width": 390, "height": 700})
                assert page.evaluate("window.innerWidth") == 390
                cookies = context.cookies()
                cookie = next(value for value in cookies if value["name"] == "synthetic-session")
                assert cookie["value"] == "fixture" and cookie["httpOnly"] is True
            finally:
                browser.close()
            assert process.poll() == 0
            with launch_browser(playwright, headless=True) as clean:
                assert clean.new_context().cookies() == []
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
