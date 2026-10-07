"""Retain original Mac notices without granting release clearance."""

from __future__ import annotations

import hashlib
import io
import json
import re
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.platforms import load_manifest  # noqa: E402
from tools.vendor_payload import materialize  # noqa: E402


def main() -> None:
    spec = load_manifest(ROOT, "macos-arm64")
    retained = []

    def retain(component: str, original: str, data: bytes) -> None:
        digest = hashlib.sha256(data).hexdigest()
        name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(original).name)[:65]
        destination = ROOT / "THIRD_PARTY_LICENSES/macos" / component / f"{digest[:12]}-{name}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.is_file() and destination.read_bytes() != data:
            raise RuntimeError("Refusing to overwrite changed original notice")
        destination.write_bytes(data)
        retained.append(
            {
                "component": component,
                "source_path": original,
                "retained_path": destination.relative_to(ROOT).as_posix(),
                "sha256": digest,
            }
        )

    pattern = re.compile(r"license|copying|notice|copyright", re.I)
    python = materialize("python", ROOT, target="macos-arm64")
    with tarfile.open(python) as archive:
        for member in archive.getmembers():
            if member.isfile() and pattern.search(Path(member.name).name):
                source = archive.extractfile(member)
                if source is not None:
                    retain("CPython-" + spec["python"]["version"], member.name, source.read())
    wheels = materialize("wheels", ROOT, target="macos-arm64")
    with zipfile.ZipFile(wheels) as archive:
        for filename in archive.namelist():
            component = "-".join(filename.split("-")[:2])
            with zipfile.ZipFile(io.BytesIO(archive.read(filename))) as wheel:
                for name in wheel.namelist():
                    if not name.endswith("/") and pattern.search(Path(name).name):
                        retain(component, name, wheel.read(name))
    browser = materialize("browser", ROOT, target="macos-arm64")
    with tarfile.open(browser) as archive:
        for member in archive.getmembers():
            if member.isfile() and pattern.search(Path(member.name).name):
                source = archive.extractfile(member)
                if source is not None:
                    retain(
                        "Chrome-" + spec["browser"]["runtimeVersion"], member.name, source.read()
                    )
    report = {
        "target": "macos-arm64",
        "release_status": "NOTICE RETAINED",
        "reason": "Notice retention does not verify redistribution permission or native source obligations",
        "notices": retained,
    }
    (ROOT / "license-audit/macos-notice-inventory.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Retained {len(retained)} original Mac notices; candidate clearance is assessed separately"
    )


if __name__ == "__main__":
    main()
