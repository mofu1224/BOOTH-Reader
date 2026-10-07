"""Browser preparation must support concurrent hosts and failed process startup."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from core import browser


def test_host_is_reused_until_source_sdk_or_icon_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(browser, "ROOT", tmp_path)
    source = tmp_path / "tools/webview_host.cs"
    source.parent.mkdir()
    source.write_text("synthetic source")
    icon = tmp_path / "tools/webview_host.ico"
    icon.write_bytes(b"synthetic icon")
    sdk = tmp_path / "sdk"
    sdk.mkdir()
    for name in ("Microsoft.Web.WebView2.Core.dll", "Microsoft.Web.WebView2.WinForms.dll"):
        (sdk / name).write_bytes(b"synthetic assembly")
    calls = []

    def compile_once(args, **kwargs):
        output = Path(next(arg[5:] for arg in args if arg.startswith("-out:")))
        output.write_bytes(b"synthetic host")
        calls.append(output)

    monkeypatch.setattr(browser.subprocess, "run", compile_once)
    first = browser.compile_host(sdk)
    assert browser.compile_host(sdk) == first
    assert len(calls) == 1, "Recompiling a running executable fails on Windows"
    source.write_text("changed synthetic source")
    changed = browser.compile_host(sdk)
    assert changed != first
    assert len(calls) == 2
    icon.write_bytes(b"changed synthetic icon")
    recolored = browser.compile_host(sdk)
    assert recolored != changed
    assert len(calls) == 3
    recolored.write_bytes(b"corrupted generated host")
    assert browser.compile_host(sdk) == recolored
    assert recolored.read_bytes() == b"synthetic host"
    assert len(calls) == 4


def test_failed_host_spawn_removes_private_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(browser, "ROOT", tmp_path)
    monkeypatch.setattr(browser, "load_manifest", lambda root: {"browser": {"engine": "webview2"}})
    (tmp_path / "portable-manifest.json").write_text(
        json.dumps({"browser": {"engine": "webview2"}})
    )
    runtime = tmp_path / ".playwright-browsers/webview2"
    runtime.mkdir(parents=True)
    (runtime / "msedgewebview2.exe").write_bytes(b"synthetic")
    from core import auth

    monkeypatch.setattr(auth, "current_account", lambda: "synthetic-account")
    monkeypatch.setattr(auth, "icacls", lambda *args: True)
    monkeypatch.setattr(browser, "compile_host", lambda sdk: tmp_path / "host.exe")

    def fail_spawn(*args, **kwargs):
        raise OSError("synthetic process creation failure")

    monkeypatch.setattr(browser.subprocess, "Popen", fail_spawn)
    pw = SimpleNamespace(chromium=SimpleNamespace(connect_over_cdp=lambda *args: None))
    with pytest.raises(OSError, match="synthetic"):
        browser.launch_browser(pw)
    assert not list((tmp_path / ".cache/tmp").glob("webview-profile-*"))
