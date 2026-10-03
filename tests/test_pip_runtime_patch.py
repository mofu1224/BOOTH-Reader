"""Runtime pip patch preserves upstream inputs and rejects oversized chunks."""

import ast
import hashlib
import json
import zipfile

from tools.pip_runtime_patch import patch_wheel


def test_offline_folder_setup_applies_pip_security_patch(tmp_path, monkeypatch):
    from tools import manage_portable, pip_runtime_patch

    monkeypatch.setattr(manage_portable, "ROOT", tmp_path)
    monkeypatch.setattr(manage_portable, "MANIFEST", {})
    lock = tmp_path / "requirements-portable-lock.txt"
    lock.write_text("locked inputs")
    monkeypatch.setattr(manage_portable, "LOCK", lock)
    monkeypatch.setattr(manage_portable, "WHEELS", tmp_path / ".cache/wheels")
    marker = tmp_path / "setup.json"
    monkeypatch.setattr(manage_portable, "setup_marker", lambda: marker)
    ready = iter([False, True])
    monkeypatch.setattr(manage_portable, "environment_ready", lambda: next(ready))
    monkeypatch.setattr(manage_portable, "wheelhouse_ready", lambda: True)
    python = tmp_path / ".venv/Scripts/python.exe"
    monkeypatch.setattr(manage_portable, "ensure_venv", lambda root: python)
    calls = []
    monkeypatch.setattr(manage_portable, "call", lambda args: calls.append(args))
    patched = tmp_path / "patched.whl"
    monkeypatch.setattr(pip_runtime_patch, "patch_wheel", lambda root: patched)
    updates = []
    monkeypatch.setattr(pip_runtime_patch, "update_ensurepip", lambda *args: updates.append(args))
    assert manage_portable.install_environment(offline=True, repair=False) == python
    assert any(str(patched) in args and "--force-reinstall" in args for args in calls)
    assert updates == [(tmp_path, patched)]


def test_pip_patch_replaces_only_vendor_and_preserves_upstream_inputs(tmp_path):
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    wheels = tmp_path / ".cache/wheels"
    wheels.mkdir(parents=True)
    names = ["pip-26.2.1-py3-none-any.whl", "urllib3-2.8.0-py3-none-any.whl"]
    before = {}
    for name in names:
        data = (root / ".cache/wheels" / name).read_bytes()
        before[name] = hashlib.sha256(data).hexdigest()
        (wheels / name).write_bytes(data)
    (tmp_path / "requirements-portable-lock.txt").write_text(
        "\n".join("--hash=sha256:" + value for value in before.values())
    )
    patched = patch_wheel(tmp_path)
    with zipfile.ZipFile(patched) as archive:
        assert "urllib3==2.8.0" in archive.read("pip/_vendor/vendor.txt").decode()
        with zipfile.ZipFile(root / ".cache/wheels" / names[0]) as original:
            assert archive.read("pip/_internal/cli/main.py") == original.read(
                "pip/_internal/cli/main.py"
            )
        with zipfile.ZipFile(root / ".cache/wheels" / names[1]) as upstream:
            assert archive.read("pip/_vendor/urllib3/response.py") == upstream.read(
                "urllib3/response.py"
            )
        assert archive.read("pip/_vendor/urllib3/LICENSE.txt")
        for name in archive.namelist():
            if name.endswith(".py"):
                ast.parse(archive.read(name).decode("utf-8"))
        details = json.loads(archive.read("pip/_vendor/BOOTH-MODIFICATIONS.json"))
        assert details["urllib3_publisher_sha256"] == before[names[1]]
    assert all(
        hashlib.sha256((wheels / name).read_bytes()).hexdigest() == value
        for name, value in before.items()
    )
    # Loading a wheel through zipimport tests the actual vendored namespace.
    import subprocess
    import sys

    code = "\n".join(
        [
            "import io, sys",
            "from types import SimpleNamespace",
            "sys.path.insert(0, sys.argv[1])",
            "from pip._vendor import urllib3",
            "assert urllib3.__version__ == '2.8.0'",
            "from pip._vendor.requests import Session",
            "assert Session()",
            "reader = io.BytesIO(b'f' * 70000 + b'\\r\\n')",
            "response = urllib3.response.HTTPResponse()",
            "response._fp = SimpleNamespace(fp=reader)",
            "response.close = lambda: None",
            "try:",
            "    response._update_chunk_length()",
            "except urllib3.exceptions.ProtocolError:",
            "    pass",
            "else:",
            "    raise AssertionError('oversized chunk header accepted')",
            "assert reader.tell() <= 65537, reader.tell()",
        ]
    )
    result = subprocess.run([sys.executable, "-I", "-c", code, str(patched)], capture_output=True)
    assert result.returncode == 0, result.stderr.decode()
