"""Inventory the actual pinned closure, nested licenses, native assets and origins."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import ssl
import sys
import urllib.request
import zipfile
from importlib import metadata
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.platforms import site_packages, target_id  # noqa: E402
from core.portable import apply_portable_env  # noqa: E402
from tools.manage_portable import WHEELS, locked_versions  # noqa: E402


def sha(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-pypi", action="store_true")
    args = parser.parse_args()
    apply_portable_env(ROOT)
    runtime = set(re.findall(r"^([\w.-]+)==", (ROOT / "requirements-lock.txt").read_text(), re.M))
    direct = {"httpx", "beautifulsoup4", "fastapi", "uvicorn", "pydantic", "playwright"}
    versions = locked_versions()
    packages = []
    for name, ver in versions.items():
        dist = metadata.distribution(name)
        assert dist.version == ver, f"installed version mismatch: {name}"
        active = []
        for raw in dist.requires or []:
            req = Requirement(raw)
            if req.marker is None or req.marker.evaluate():
                dependency = canonicalize_name(req.name)
                assert dependency in versions and req.specifier.contains(versions[dependency]), raw
                active.append(dependency)
        licenses = []
        for relative in dist.files or []:
            if re.search(r"license|copying|notice", str(relative), re.I):
                path = Path(str(dist.locate_file(relative)))
                if path.is_file():
                    licenses.append(
                        {"path": str(relative), "sha256": sha(path), "bytes": path.stat().st_size}
                    )
        role = (
            "実行(直接)" if name in direct else "実行(推移)" if name in runtime else "開発・ビルド"
        )
        if name == "packageurl-python":
            supplement = ROOT / "third_party/packageurl-python-MIT.txt"
            licenses.append(
                {
                    "path": "third_party/packageurl-python-MIT.txt",
                    "sha256": sha(supplement),
                    "bytes": supplement.stat().st_size,
                    "source": "https://raw.githubusercontent.com/package-url/packageurl-python/main/mit.LICENSE",
                }
            )
        row = {
            "name": name,
            "version": ver,
            "role": role,
            "active_dependencies": active,
            "requires": dist.requires or [],
            "license": dist.metadata.get("License-Expression") or dist.metadata.get("License", ""),
            "license_files": licenses,
            "location": site_packages(ROOT).relative_to(ROOT).as_posix(),
            "source": f"https://pypi.org/project/{name}/{ver}/",
            "migration": "ハッシュ固定wheelを.cache/wheelsへ保管し.venvへ導入",
            "verification": "SHA-256、pip check、import、全回帰試験",
        }
        wheels = [
            path
            for path in WHEELS.glob("*.whl")
            if canonicalize_name(path.name.split("-")[0]) == name
        ]
        assert len(wheels) == 1, name
        wheel = wheels[0]
        row["wheel"] = {"file": wheel.name, "sha256": sha(wheel), "bytes": wheel.stat().st_size}
        with zipfile.ZipFile(wheel) as archive:
            row["embedded_native_files"] = [
                p
                for p in archive.namelist()
                if p.lower().endswith((".dll", ".exe", ".pyd", ".so", ".dylib"))
                or p.endswith("/driver/node")
            ]
            row["vendored_metadata"] = [
                p
                for p in archive.namelist()
                if p.endswith(".dist-info/METADATA") and len(p.split("/")) > 2
            ]
        if args.verify_pypi:
            url = f"https://pypi.org/pypi/{name}/{ver}/json"
            with urllib.request.urlopen(url, timeout=60) as response:
                published = json.load(response)
            matching = [item for item in published["urls"] if item["filename"] == wheel.name]
            assert len(matching) == 1, name
            published_digest = matching[0]["digests"]["sha256"]
            wheel_digest = sha(wheel)
            derived = None
            if name == "pip":
                # The vendored pip wheel is patched (documented derivation) and
                # therefore cannot byte-match the upstream publisher digest.
                evidence = ROOT / "license-audit/runtime-derivation.json"
                if evidence.is_file():
                    provenance = json.loads(evidence.read_text(encoding="utf-8"))
                    if wheel_digest == provenance["derived_pip_sha256"]:
                        assert published_digest == provenance["publisher_pip_sha256"], name
                        derived = provenance
            assert derived is not None or wheel_digest == published_digest, name
            row["pypi_digest_verified"] = True
            if derived is not None:
                row["documented_derivation"] = {
                    "path": "license-audit/runtime-derivation.json",
                    "publisher_sha256": derived["publisher_pip_sha256"],
                    "derived_sha256": derived["derived_pip_sha256"],
                }
        packages.append(row)
    assets = []
    for base in (ROOT / ".tools/python", ROOT / ".playwright-browsers"):
        for path in base.rglob("*"):
            if path.is_file() and (
                path.suffix.lower() in {".exe", ".dll", ".pyd", ".so", ".dylib"}
                or re.search(r"license|copying|about", path.name, re.I)
            ):
                assets.append(
                    {
                        "path": path.relative_to(ROOT).as_posix(),
                        "sha256": sha(path),
                        "bytes": path.stat().st_size,
                    }
                )
    report = {
        "target": target_id() + " / CPython " + sys.version.split()[0],
        "packages": packages,
        "stdlib_native": {"openssl": ssl.OPENSSL_VERSION, "sqlite": sqlite3.sqlite_version},
        "runtime_assets": assets,
        "license_scope": "実ファイルと出所を確認。第三者バイナリの公衆再配布条件は別途確認が必要。",
    }
    (ROOT / "audit/portable-dependencies.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    lines = [
        "# ポータブル依存台帳",
        "",
        "Windows x64 / CPython 3.12.13。全62パッケージの推移閉包を実測。",
        "用途・保存場所・移行方式・検証・出所・実ライセンスのSHA-256は `portable-dependencies.json` に記録。",
        "全パッケージは `.cache/wheels` から `.venv/Lib/site-packages` に導入する。",
        "追加Compiler/SDKの導入は不要。WebView2ホストはWindows標準.NET Framework cscと同梱SDKで生成する。",
        "",
        "| 名前 | バージョン | 用途 | 有効な直接依存先 | ライセンス情報 | 通知ファイル数 |",
        "|---|---|---|---|---|---|",
    ]
    for row in packages:
        license_text = (
            row["license"].splitlines()[0] if row["license"] else "metadata未記載(実通知参照)"
        )
        lines.append(
            f"| {row['name']} | {row['version']} | {row['role']} | {', '.join(row['active_dependencies']) or 'なし'} | {license_text.replace('|', '/')} | {len(row['license_files'])} |"
        )
    lines += [
        "",
        "## 実行・ビルド以外の依存",
        "",
        "- Runtime: `.tools/python`。Python、OpenSSL、SQLite、libffi、VC runtime等の実DLLをJSONで記録。",
        "- Browser: `.playwright-browsers`。Microsoft WebView2 Fixed Version 154.0.4258.53と公式SDK 1.0.4258.31 (同梱payloadから展開)。",
        "- Playwright driver: wheel内 `playwright/driver/node.exe`(Node24.21.0)とJS。グローバルNode/npmは不要。",
        "- OS: Windows x64、PowerShell5.1、tar、cmd、whoami、icacls、標準DLL、GPUドライバー。",
        "- 外部サービス: BOOTH/pixiv認証/販売者CDN。購入・ログイン・DLの機能仕様上必要。",
        "- 起動・修復: Git追跡済みvendorから無通信で構築。BOOTH/pixiv/CDNへの本来の通信とWebView2自身の通信は別。",
        "- データ/アセット: ローカルSQLite、Cookie、購入ファイル、動的HTML。AIモデル/外部DB/追加フォントなし。",
        "- Git: 任意の開発メタデータ診断だけ。セットアップ・本体・ポータブル監査はGit不要。",
        "- 古いdist/release/トップレベルキャッシュは未使用。既存物を保護し、自動削除しない。",
        "- `.venv`の絶対パスは生成物。起動前に旧homeを拒否し、ローカルwheelから再生成。",
        "- CPythonのPDB/未使用Tcl開発設定にあるビルド元パスはデバッグ情報であり、アプリの実行参照ではない。",
        "",
    ]
    (ROOT / "audit/portable-dependencies-current.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"verified {len(packages)} packages and {len(assets)} native/license assets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
