"""Build a documented Python/pip payload without obsolete embedded installers."""

from __future__ import annotations

import copy
import hashlib
import io
import json
import re
import shutil
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    from tools.gen_lock import main as gen_lock
    from tools.pip_runtime_patch import patch_wheel

    manifest_path = ROOT / "portable-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["python"].get("derived"):
        raise RuntimeError("Runtime is already derived; acquire a fresh publisher input to rebuild")
    original = ROOT / ".cache/downloads" / manifest["python"]["asset"]
    if digest(original) != manifest["python"]["sha256"]:
        raise RuntimeError("Python publisher hash mismatch")
    patched = patch_wheel(ROOT)
    pip_path = ROOT / ".cache/wheels/pip-26.2.1-py3-none-any.whl"
    private = ROOT / ".cache/original-payload"
    private.mkdir(exist_ok=True)
    source_pip_hash = digest(pip_path)
    shutil.copyfile(pip_path, private / pip_path.name)
    shutil.copyfile(patched, pip_path)
    gen_lock([str(ROOT / ".cache/wheels"), str(ROOT / "requirements-portable-lock.txt")])
    output = ROOT / ".cache/downloads/cpython-3.12.13-booth-runtime.tar.gz"
    removed, changed, retained = [], [], []
    with tarfile.open(original) as source, tarfile.open(output, "w:gz") as destination:
        for member in source.getmembers():
            name = member.name
            if name == "python" and member.isdir():
                destination.addfile(copy.copy(member))
                continue
            if (
                not name.startswith("python/")
                or ".." in Path(name).parts
                or member.issym()
                or member.islnk()
            ):
                raise RuntimeError("Unexpected publisher archive entry")
            if (
                name.endswith(".pyc")
                or name.startswith(
                    (
                        "python/Lib/site-packages/pip/",
                        "python/Lib/site-packages/pip-26.0.1.dist-info/",
                    )
                )
                or name.endswith("/pip-25.0.1-py3-none-any.whl")
                or re.fullmatch(r"python/Scripts/pip(?:3(?:\.12)?)?\.exe", name)
            ):
                removed.append(name)
                continue
            info = copy.copy(member)
            if member.isfile():
                stream = source.extractfile(member)
                if stream is None:
                    raise RuntimeError("Missing source stream")
                data = stream.read()
                if name == "python/Lib/ensurepip/__init__.py":
                    if b'_PIP_VERSION = "25.0.1"' not in data:
                        raise RuntimeError("Unexpected ensurepip version")
                    data = data.replace(b'_PIP_VERSION = "25.0.1"', b'_PIP_VERSION = "26.2.1"')
                    info.size = len(data)
                    info.mtime += 1
                    changed.append(name)
                else:
                    retained.append({"path": name, "sha256": hashlib.sha256(data).hexdigest()})
                destination.addfile(info, io.BytesIO(data))
            else:
                destination.addfile(info)
        data = pip_path.read_bytes()
        info = tarfile.TarInfo("python/Lib/ensurepip/_bundled/" + pip_path.name)
        info.size = len(data)
        info.mode = 0o644
        destination.addfile(info, io.BytesIO(data))
    report = {
        "publisher_python": dict(manifest["python"]),
        "publisher_pip_sha256": source_pip_hash,
        "derived_pip_sha256": digest(pip_path),
        "derived_python_sha256": digest(output),
        "removed": removed,
        "changed": changed,
        "unchanged_files": retained,
        "scope": "Python native binaries and original notices unchanged; obsolete pip/pyc removed; ensurepip uses documented urllib3-fixed pip",
    }
    (ROOT / "license-audit/runtime-derivation.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    manifest["python"].update(
        {
            "derived": True,
            "publisher_sha256": manifest["python"]["sha256"],
            "asset": output.name,
            "sha256": digest(output),
            "size": output.stat().st_size,
            "modifications": "license-audit/runtime-derivation.json",
        }
    )
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "native_binaries_unchanged": sum(
                    Path(row["path"]).suffix in {".exe", ".dll", ".pyd"} for row in retained
                ),
                "removed_entries": len(removed),
                "changed_python_source_files": len(changed),
                "runtime_sha256": digest(output),
            }
        )
    )


if __name__ == "__main__":
    main()
