from pathlib import Path

from tools.make_webview_icon import build

ROOT = Path(__file__).resolve().parent.parent


def test_committed_host_icon_is_reproducible():
    assert build() == (ROOT / "tools/webview_host.ico").read_bytes()
