"""HTTP trust-boundary regressions; all requests use a local mock transport."""

import httpx
import pytest

from core import auth, download, net, purchases
from core.errors import BoothAuthError, BoothNetworkError


@pytest.fixture
def mock_http(monkeypatch):
    clients = []
    net.close_clients()

    def install(handler):
        def factory(timeout):
            client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
            clients.append(client)
            return client

        monkeypatch.setattr(net, "_new_client", factory)

    yield install
    net.close_clients()
    for client in clients:
        client.close()


@pytest.mark.parametrize("stream", [False, True])
def test_redirect_never_leaks_cookie_and_logout_clears_pool(mock_http, tmp_path, stream):
    seen = []

    def handler(request):
        seen.append((request.url.host, request.headers.get("cookie", "")))
        if request.url.host == "accounts.booth.pm":
            return httpx.Response(302, headers={"Location": "https://cdn.example.test/file.bin"})
        return httpx.Response(200, content=b"data", headers={"Set-Cookie": "stale=x; Path=/"})

    mock_http(handler)
    cookies = [
        {
            "name": "session",
            "value": "fake-session",
            "domain": "accounts.booth.pm",
            "path": "/",
            "secure": True,
        }
    ]
    if stream:
        download.download_file("https://accounts.booth.pm/file", tmp_path / "f.bin", cookies)
    else:
        net.request("https://accounts.booth.pm/library", cookies=cookies)
    assert "fake-session" in seen[0][1]
    assert seen[1][1] == "", "a BOOTH session reached an unrelated redirect target"
    net.request("https://cdn.example.test/file.bin", cookies=[])
    assert seen[-1][1] == "", "cookies survived logout in a pooled client"


def test_cookie_host_only_secure_path_and_expiry(mock_http):
    seen = []

    def handler(request):
        seen.append(request.headers.get("cookie", ""))
        return httpx.Response(200, content=b"ok")

    mock_http(handler)
    jar = [
        {"name": "host", "value": "h", "domain": "booth.pm", "path": "/"},
        {"name": "domain", "value": "d", "domain": ".booth.pm", "path": "/"},
        {"name": "secure", "value": "s", "domain": ".booth.pm", "secure": True},
        {"name": "path", "value": "p", "domain": ".booth.pm", "path": "/library"},
        {"name": "expired", "value": "e", "domain": ".booth.pm", "expires": 1},
    ]
    net.request("http://accounts.booth.pm/library-other", cookies=jar)
    assert seen == ["domain=d"]
    net.request("https://booth.pm/library/1", cookies=jar)
    assert set(seen[-1].split("; ")) == {"host=h", "domain=d", "secure=s", "path=p"}


@pytest.mark.parametrize("operation", ["purchase", "links", "status"])
def test_http_403_is_auth_error(mock_http, tmp_path, operation):
    mock_http(lambda req: httpx.Response(403))
    jar = [{"name": "a", "value": "v", "domain": ".booth.pm"}]
    with pytest.raises(BoothAuthError):
        if operation == "purchase":
            purchases.fetch_library_html(jar)
        elif operation == "links":
            download.resolve_download_links("123", jar)
        else:
            path = auth.save_cookies(jar, tmp_path / "ck.json")
            auth.status(path, verify_network=True)


def test_auth_status_network_failure_is_not_auth(mock_http, tmp_path):
    mock_http(lambda req: httpx.Response(404))
    path = auth.save_cookies([{"name": "a", "value": "v"}], tmp_path / "ck.json")
    with pytest.raises(BoothNetworkError):
        auth.status(path, verify_network=True)


def test_session_cookie_with_expired_tracking_cookie_is_not_expired(tmp_path):
    path = auth.save_cookies(
        [
            {"name": "session", "value": "v", "expires": -1},
            {"name": "tracking", "value": "v", "expires": 1},
        ],
        tmp_path / "ck.json",
    )
    assert auth.status(path)["ok"]
