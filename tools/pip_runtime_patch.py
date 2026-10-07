"""Update the recipient's pip HTTP vendor from a hash-verified publisher wheel."""

from __future__ import annotations

import ast
import base64
import csv
import hashlib
import io
import json
import re
import shutil
import zipfile
from pathlib import Path


def checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def patch_wheel(root: Path) -> Path:
    from core.platforms import load_manifest

    runtime = load_manifest(root)
    lock = (root / runtime["lock"]).read_text(encoding="utf-8")
    allowed = set(re.findall(r"--hash=sha256:([0-9a-f]{64})", lock))
    wheels = root / runtime["wheelhouse"]
    pip_path = wheels / "pip-26.2.1-py3-none-any.whl"
    urllib3_path = wheels / "urllib3-2.8.0-py3-none-any.whl"
    original, replacement = pip_path.read_bytes(), urllib3_path.read_bytes()
    if checksum(original) not in allowed or checksum(replacement) not in allowed:
        raise RuntimeError("Pip patch inputs are not publisher-hash-verified lock files")
    with zipfile.ZipFile(io.BytesIO(original)) as archive:
        files = {name: archive.read(name) for name in archive.namelist() if not name.endswith("/")}
    if "urllib3==2.8.0" in files["pip/_vendor/vendor.txt"].decode("utf-8"):
        modifications = json.loads(files["pip/_vendor/BOOTH-MODIFICATIONS.json"])
        if modifications["urllib3_publisher_sha256"] != checksum(replacement):
            raise RuntimeError("Derived pip has unexpected upstream vendor provenance")
        return pip_path
    files = {
        name: data for name, data in files.items() if not name.startswith("pip/_vendor/urllib3/")
    }
    changed_imports = []
    with zipfile.ZipFile(io.BytesIO(replacement)) as archive:
        for name in archive.namelist():
            if name.endswith("/"):
                continue
            if name.startswith("urllib3/"):
                data = archive.read(name)
                if name.endswith(".py"):
                    text = data.decode("utf-8")
                    lines = text.splitlines(keepends=True)
                    for node in ast.walk(ast.parse(text)):
                        if isinstance(node, ast.Import):
                            for alias in node.names:
                                if alias.name.startswith("urllib3."):
                                    old = lines[node.lineno - 1]
                                    indent = old[: len(old) - len(old.lstrip())]
                                    lines[node.lineno - 1] = (
                                        indent
                                        + "from pip._vendor import urllib3\n"
                                        + indent
                                        + "import pip._vendor."
                                        + alias.name
                                        + "\n"
                                    )
                                    changed_imports.append({"path": name, "line": node.lineno})
                    data = "".join(lines).encode("utf-8")
                files["pip/_vendor/" + name] = data
            if name.endswith(".dist-info/licenses/LICENSE.txt"):
                files["pip/_vendor/urllib3/LICENSE.txt"] = archive.read(name)
    vendor = files["pip/_vendor/vendor.txt"].decode("utf-8")
    if "urllib3==2.7.0" not in vendor:
        raise RuntimeError("Unexpected pip vendor version")
    files["pip/_vendor/vendor.txt"] = vendor.replace("urllib3==2.7.0", "urllib3==2.8.0").encode(
        "utf-8"
    )
    details = {
        "parent": "pip-26.2.1",
        "original_sha256": checksum(original),
        "urllib3_publisher_sha256": checksum(replacement),
        "updated_vendor": "urllib3-2.8.0",
        "import_namespace_changes": changed_imports,
        "distribution": "locally derived installation; upstream archives retained unchanged; see license-audit/19-release-readiness.md for folder redistribution status",
    }
    files["pip/_vendor/BOOTH-MODIFICATIONS.json"] = (json.dumps(details, indent=2) + "\n").encode(
        "utf-8"
    )
    record = "pip-26.2.1.dist-info/RECORD"
    files.pop(record)
    text = io.StringIO(newline="")
    writer = csv.writer(text, lineterminator="\n")
    for name, data in sorted(files.items()):
        writer.writerow(
            [
                name,
                "sha256="
                + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode(),
                len(data),
            ]
        )
    writer.writerow([record, "", ""])
    files[record] = text.getvalue().encode("utf-8")
    target = root / ".cache/patched/pip-26.2.1-py3-none-any.whl"
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(name, data)
    return target


def update_ensurepip(root: Path, patched: Path) -> None:
    from core.platforms import load_manifest, target_id

    base = root / ".tools/python"
    version = ".".join(load_manifest(root)["python"]["version"].split(".")[:2])
    stdlib = base / ("Lib" if target_id() == "windows-x64" else f"lib/python{version}")
    module = stdlib / "ensurepip/__init__.py"
    text = module.read_text(encoding="utf-8")
    match = re.search(r'^_PIP_VERSION = "([0-9.]+)"$', text, re.M)
    if not match:
        raise RuntimeError("Unexpected ensurepip version")
    bundled = stdlib / "ensurepip/_bundled"
    shutil.copyfile(patched, bundled / patched.name)
    if match[1] != "26.2.1":
        (bundled / f"pip-{match[1]}-py3-none-any.whl").unlink(missing_ok=True)
    module.write_text(
        text[: match.start()] + '_PIP_VERSION = "26.2.1"' + text[match.end() :], encoding="utf-8"
    )
    # The base interpreter's obsolete pip is not used to install applications.
    # Remove only these exact disposable installation directories.
    for name in ("pip", "pip-26.0.1.dist-info"):
        path = stdlib / "site-packages" / name
        if path.is_symlink() or not path.resolve().is_relative_to(base.resolve()):
            raise RuntimeError("Unexpected base pip location")
        if path.exists():
            shutil.rmtree(path)
