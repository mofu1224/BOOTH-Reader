"""Regression proof for isolation, cold repair and trusted archive handling."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from tools import manage_portable, portable


@pytest.fixture
def isolated_env():
    """``manage_portable.main`` rebases process-wide env vars on purpose.

    In production that only affects the launcher process; in the test process
    it would leak into later tests (PATH without Git, TEMP moved under the
    repo). Snapshot and restore the real mapping so case-insensitive Windows
    keys keep working during the test.
    """
    saved = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(saved)


def test_relocated_venv_is_rejected_before_old_interpreter_runs(tmp_path, monkeypatch):
    exe = tmp_path / ".venv/Scripts/python.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"not executed")
    (tmp_path / ".venv/pyvenv.cfg").write_text("home = X:/old-checkout/.tools/python\n")

    def forbidden(*args, **kwargs):
        raise AssertionError("Old interpreter must never execute")

    monkeypatch.setattr(portable, "_venv_prefix", forbidden)
    assert portable.venv_health(tmp_path)[0] is False


def test_no_global_python_fallback(tmp_path):
    assert portable.candidate_pythons(tmp_path) == []


def test_launcher_environment_removes_developer_tool_injection(tmp_path, monkeypatch):
    (tmp_path / "cli.py").write_text("# repository marker\n")
    monkeypatch.setattr(manage_portable, "ROOT", tmp_path)
    monkeypatch.setattr(manage_portable, "WHEELS", tmp_path / ".cache/wheels")
    for key in (
        "PYTHONHOME",
        "PYTHONPATH",
        "NODE_OPTIONS",
        "PIP_INDEX_URL",
        "PIP_TARGET",
        "SSL_CERT_FILE",
        "PLAYWRIGHT_DOWNLOAD_HOST",
    ):
        monkeypatch.setenv(key, "outside-repo")
    env = manage_portable.child_env()
    for key in ("PYTHONHOME", "PYTHONPATH", "NODE_OPTIONS", "PIP_TARGET", "SSL_CERT_FILE"):
        assert key not in env
    for key in (
        "TEMP",
        "TMP",
        "HOME",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "PIP_CACHE_DIR",
        "PLAYWRIGHT_BROWSERS_PATH",
    ):
        assert Path(env[key]).is_relative_to(tmp_path)
    assert env["PIP_CONFIG_FILE"].lower() == "nul"
    assert "outside-repo" not in env["PATH"]


def test_portable_profile_prepares_file_picker_folders(tmp_path, monkeypatch):
    (tmp_path / "cli.py").write_text("# repository marker\n")
    monkeypatch.setattr(manage_portable, "ROOT", tmp_path)
    monkeypatch.setattr(manage_portable, "WHEELS", tmp_path / ".cache/wheels")
    env = manage_portable.child_env()
    home = Path(env["USERPROFILE"])
    folders = ("Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos")
    for name in folders:
        assert (home / name).is_dir(), f"File picker location missing: {name}"
    preserved = home / "Desktop" / "preserved.txt"
    preserved.write_text("existing personal data", encoding="utf-8")
    manage_portable.child_env()
    assert preserved.read_text(encoding="utf-8") == "existing personal data"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows shell folder resolution")
def test_windows_shell_resolves_portable_desktop(tmp_path, monkeypatch):
    (tmp_path / "cli.py").write_text("# repository marker\n")
    monkeypatch.setattr(manage_portable, "ROOT", tmp_path)
    monkeypatch.setattr(manage_portable, "WHEELS", tmp_path / ".cache/wheels")
    code = (
        "import ctypes,json; from pathlib import Path; "
        "folder=ctypes.create_unicode_buffer(260); "
        "result=ctypes.windll.shell32.SHGetFolderPathW(None,0x10,None,0,folder); "
        "print(json.dumps({'result':result,'path':folder.value,'exists':Path(folder.value).is_dir()}))"
    )
    result = subprocess.run(
        [sys.executable, "-s", "-c", code],
        env=manage_portable.child_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=True,
    )
    desktop = json.loads(result.stdout)
    assert desktop["result"] == 0
    assert desktop["exists"]
    assert Path(desktop["path"]) == tmp_path / ".cache/home/Desktop"


@pytest.mark.parametrize("name", ["../escape", "C:/escape", "nested/../../escape"])
def test_snapshot_rejects_external_paths(tmp_path, name):
    snapshot = tmp_path / "browser.zip"
    with zipfile.ZipFile(snapshot, "w") as bundle:
        bundle.writestr(name, b"untrusted")
    destination = tmp_path / "browsers"
    with pytest.raises(RuntimeError, match="bundled browser"):
        manage_portable.extract_snapshot(snapshot, destination)
    assert not (tmp_path / "escape").exists()


def test_repair_refuses_while_web_ui_is_running(isolated_env, monkeypatch, capsys):
    installed = []
    monkeypatch.setattr(manage_portable, "find_existing_web_instance", lambda port: 8000)
    monkeypatch.setattr(
        manage_portable, "install_environment", lambda **kwargs: installed.append(kwargs)
    )
    assert manage_portable.main(["setup", "--repair"]) == 1
    captured = capsys.readouterr()
    assert "Already running" in captured.err
    assert "8000" in captured.err
    assert installed == [], "repair must not touch a running instance"


def test_check_reports_readiness_on_stderr(isolated_env, monkeypatch, capsys):
    monkeypatch.setattr(manage_portable, "environment_ready", lambda: False)
    assert manage_portable.main(["setup", "--check"]) == 1
    assert "Not ready" in capsys.readouterr().err

    monkeypatch.setattr(manage_portable, "environment_ready", lambda: True)
    assert manage_portable.main(["setup", "--check"]) == 0
    assert "Ready" in capsys.readouterr().err


def test_web_argument_errors_are_english():
    with pytest.raises(RuntimeError, match="1-65535"):
        manage_portable.parse_web_args(["99999"])
    with pytest.raises(RuntimeError, match="Unknown"):
        manage_portable.parse_web_args(["--bogus"])
    with pytest.raises(RuntimeError, match="port number"):
        manage_portable.parse_web_args(["--port"])


def test_setup_flag_errors_are_english(isolated_env, capsys):
    assert manage_portable.main(["setup", "--bogus-flag"]) == 1
    assert "Unknown setup option" in capsys.readouterr().err


def test_offline_repair_preserves_old_environment_on_missing_wheels(tmp_path, monkeypatch):
    old = tmp_path / ".venv/preserved"
    old.parent.mkdir()
    old.write_bytes(b"previous environment")
    monkeypatch.setattr(manage_portable, "ROOT", tmp_path)
    monkeypatch.setattr(manage_portable, "environment_ready", lambda: False)
    monkeypatch.setattr(manage_portable, "wheelhouse_ready", lambda: False)
    with pytest.raises(RuntimeError, match="Bundled dependencies"):
        manage_portable.install_environment(offline=True, repair=True)
    assert old.read_bytes() == b"previous environment"


def test_lock_generator_ignores_vendored_distribution_metadata(tmp_path):
    from tools.gen_lock import main

    with zipfile.ZipFile(tmp_path / "example-1-py3-none-any.whl", "w") as bundle:
        bundle.writestr("example-1.dist-info/METADATA", "Name: example\nVersion: 1\n")
        bundle.writestr("example/vendor/nested.dist-info/METADATA", "Name: nested\nVersion: 2\n")
    out = tmp_path / "lock.txt"
    assert main([str(tmp_path), str(out)]) == 0
    assert "example==1" in out.read_text()
    assert "nested==" not in out.read_text()


def test_manifest_and_runtime_locks_agree():
    root = Path(__file__).resolve().parent.parent
    manifest = json.loads((root / "portable-manifest.json").read_text())
    assert manage_portable.locked_versions()["playwright"] == manifest["browser"]["version"]
    import re

    runtime = dict(
        re.findall(r"^([\w.-]+)==([^\s\\]+)", (root / "requirements-lock.txt").read_text(), re.M)
    )
    for name, version in runtime.items():
        assert manage_portable.locked_versions()[name] == version


def test_untracked_developer_path_is_detected_without_git(tmp_path, monkeypatch):
    from tools import check_portable

    (tmp_path / "core").mkdir()
    (tmp_path / "core/bad.py").write_text('RESOURCE = "D:/private-work/asset.bin"\n')
    monkeypatch.setattr(check_portable, "ROOT", tmp_path)
    check_portable.RESULTS.clear()
    check_portable.check_no_absolute_refs()
    assert any(not passed for _, passed, _ in check_portable.RESULTS)


def test_unmanaged_cli_and_persistent_environment_changes_are_detected(tmp_path, monkeypatch):
    from tools import check_portable

    (tmp_path / "tools").mkdir()
    (tmp_path / "tools/bad.py").write_text(
        'import subprocess\nsubprocess.run(["unmanaged-tool"])\n'
    )
    (tmp_path / "bad.bat").write_text("setx EXTERNAL_LOCATION outside\n")
    monkeypatch.setattr(check_portable, "ROOT", tmp_path)
    check_portable.RESULTS.clear()
    check_portable.check_machine_state()
    assert sum(not passed for _, passed, _ in check_portable.RESULTS) == 2


def test_failed_install_restores_the_previous_generated_environment(tmp_path, monkeypatch):
    old = tmp_path / ".venv/preserved"
    old.parent.mkdir()
    old.write_bytes(b"old environment")
    (tmp_path / ".cache/tmp").mkdir(parents=True)
    monkeypatch.setattr(manage_portable, "ROOT", tmp_path)
    monkeypatch.setattr(manage_portable, "environment_ready", lambda: False)
    monkeypatch.setattr(manage_portable, "wheelhouse_ready", lambda: True)

    def recreate(root):
        (root / ".venv").mkdir()
        return root / ".venv/python.exe"

    def fail_install(*args, **kwargs):
        raise RuntimeError("simulated install failure")

    monkeypatch.setattr(manage_portable, "ensure_venv", recreate)
    monkeypatch.setattr(manage_portable, "call", fail_install)
    with pytest.raises(RuntimeError, match="install failure"):
        manage_portable.install_environment(offline=True, repair=True)
    assert old.read_bytes() == b"old environment"
    assert not list((tmp_path / ".cache/tmp").iterdir())


@pytest.mark.parametrize("recover", [True, False])
def test_corrupt_existing_browser_restored_once_from_verified_snapshot(
    tmp_path, monkeypatch, recover
):
    from tools import vendor_payload

    browser = tmp_path / ".playwright-browsers/chrome.exe"
    browser.parent.mkdir()
    browser.write_bytes(b"corrupted executable")
    snapshot = tmp_path / "snapshot.zip"
    with zipfile.ZipFile(snapshot, "w") as archive:
        archive.writestr("chrome.exe", b"restored executable")
    receipt = tmp_path / "snapshot.json"
    receipt.write_text(json.dumps({"sha256": manage_portable.digest(snapshot)}))
    monkeypatch.setattr(manage_portable, "ROOT", tmp_path)
    monkeypatch.setattr(manage_portable, "SNAPSHOT", snapshot)
    monkeypatch.setattr(manage_portable, "RECEIPT", receipt)
    monkeypatch.setattr(manage_portable, "browser_files", lambda python: [browser, browser])
    restored = []
    monkeypatch.setattr(vendor_payload, "materialize", lambda name, root: restored.append(name))
    probes = []

    def probe(*args, **kwargs):
        probes.append(browser.read_bytes())
        if not recover or browser.read_bytes() != b"restored executable":
            raise RuntimeError("browser cannot launch")

    monkeypatch.setattr(manage_portable, "call", probe)
    if recover:
        manage_portable.ensure_browser(tmp_path / "python.exe", offline=True)
    else:
        with pytest.raises(RuntimeError, match="cannot launch"):
            manage_portable.ensure_browser(tmp_path / "python.exe", offline=True)
    assert probes == [b"corrupted executable", b"restored executable"]
    assert restored == ["browser", "browser-receipt"]


def test_locked_environment_reports_stop_first(tmp_path, monkeypatch):
    """A running app holds .venv open; the repair must name the fix, not crash."""
    old = tmp_path / ".venv/preserved"
    old.parent.mkdir()
    old.write_bytes(b"running environment")
    monkeypatch.setattr(manage_portable, "ROOT", tmp_path)
    monkeypatch.setattr(manage_portable, "environment_ready", lambda: False)
    monkeypatch.setattr(manage_portable, "wheelhouse_ready", lambda: True)
    real_rename = Path.rename

    def locked_rename(self, target):
        if self == old:
            raise OSError(32, "file in use")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", locked_rename)
    with pytest.raises(RuntimeError, match=r"Stop BOOTH-Reader with Ctrl\+C"):
        manage_portable.install_environment(offline=True, repair=True)
    assert old.read_bytes() == b"running environment"


def test_ci_global_install_is_detected(tmp_path, monkeypatch):
    from tools import check_portable

    workflow = tmp_path / ".github/workflows/ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("jobs:\n  test:\n    run: |\n      pip install dependency\n")
    monkeypatch.setattr(check_portable, "ROOT", tmp_path)
    check_portable.RESULTS.clear()
    check_portable.check_ci_isolation()
    assert any(not passed for _, passed, _ in check_portable.RESULTS)


@pytest.mark.parametrize(
    "args,port,opens",
    [
        ([], "8000", True),
        (["8080"], "8080", True),
        (["--no-open"], "8000", False),
        (["--port", "9000", "--no-open"], "9000", False),
    ],
)
def test_web_launch_schedules_browser_without_extra_output(monkeypatch, capsys, args, port, opens):
    calls = []
    opened = []
    monkeypatch.setattr(manage_portable, "find_existing_web_instance", lambda p: None)
    monkeypatch.setattr(manage_portable, "pick_free_port", lambda p: p)
    monkeypatch.setattr(manage_portable, "schedule_web_browser", opened.append)
    monkeypatch.setattr(
        manage_portable.subprocess, "call", lambda cmd, **kwargs: calls.append(cmd) or 0
    )
    assert manage_portable.web(Path("python.exe"), args) == 0
    assert len(calls) == 1
    assert calls[0][-5:] == ["web", "--host", "127.0.0.1", "--port", port]
    output = capsys.readouterr().out
    assert output == ""
    assert opened == ([int(port)] if opens else [])


@pytest.mark.parametrize(
    "running,url",
    [(8000, "http://127.0.0.1:8000/"), (8001, "http://127.0.0.1:8001/")],
)
def test_web_reuses_an_already_running_instance(monkeypatch, capsys, running, url):
    calls = []
    opened = []
    monkeypatch.setattr(manage_portable, "find_existing_web_instance", lambda p: running)
    monkeypatch.setattr(manage_portable, "open_web_browser", opened.append)
    monkeypatch.setattr(
        manage_portable.subprocess, "call", lambda cmd, **kwargs: calls.append(cmd) or 0
    )
    assert manage_portable.web(Path("python.exe"), []) == 0
    assert calls == []
    assert opened == [url]
    assert "Already running" in capsys.readouterr().out


def test_web_port_conflict_uses_the_next_free_port(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(manage_portable, "find_existing_web_instance", lambda p: None)
    monkeypatch.setattr(manage_portable, "pick_free_port", lambda p: p + 1)
    monkeypatch.setattr(manage_portable, "schedule_web_browser", lambda p: None)
    monkeypatch.setattr(
        manage_portable.subprocess, "call", lambda cmd, **kwargs: calls.append(cmd) or 0
    )
    assert manage_portable.web(Path("python.exe"), ["8000"]) == 0
    assert calls[0][-1] == "8001"
    assert "8001" in capsys.readouterr().out


def test_busy_port_is_skipped_by_binding():
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        busy = sock.getsockname()[1]
        assert manage_portable.pick_free_port(busy) != busy


def test_existing_web_instance_detection():
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"ok": True, "transport": "subprocess", "download": {}}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert manage_portable.existing_web_instance(server.server_port) is True
        assert manage_portable.find_existing_web_instance(server.server_port) == server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
