"""Acquire additional pinned provenance and reconcile current release candidates."""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from html.parser import HTMLParser
from pathlib import Path

from tools.license_compliance import AUDIT, ROOT, digest, dump, fetch, retain, sha


class PageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden and data.strip():
            self.parts.append(data.strip())


def python_correspondence() -> None:
    for page in (AUDIT / "evidence/upstream").glob("chrome-*.txt"):
        if page.name.endswith(".readable.txt"):
            continue
        text = PageText()
        text.feed(page.read_text(encoding="utf-8", errors="replace"))
        page.with_suffix(".readable.txt").write_text("\n".join(text.parts), encoding="utf-8")
    evidence = json.loads((AUDIT / "reaudit-upstream.json").read_text(encoding="utf-8"))
    full = next(row for row in evidence if row.get("metadata"))
    archive = ROOT / ".cache/downloads" / Path(full["url"].replace("%2B", "+")).name
    system_tar = Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32/tar.exe"
    listing = (
        subprocess.run(
            [str(system_tar), "-tf", str(archive)], capture_output=True, check=True, timeout=90
        )
        .stdout.decode()
        .splitlines()
    )
    assert all(
        not Path(n).is_absolute() and ".." not in Path(n).parts and ":" not in n for n in listing
    )
    root = Path(tempfile.mkdtemp(prefix="pbs-license-", dir=ROOT / ".cache/tmp"))
    try:
        subprocess.run(
            [
                str(system_tar),
                "-xf",
                str(archive),
                "-C",
                str(root),
                "python/install",
                "python/licenses",
            ],
            capture_output=True,
            check=True,
            timeout=120,
        )
        from tools.vendor_payload import materialize

        matched, mismatched = [], []
        with tarfile.open(materialize("python")) as original:
            for member in original.getmembers():
                if not member.isfile():
                    continue
                stream = original.extractfile(member)
                assert stream is not None
                data = stream.read()
                relative = member.name.removeprefix("python/")
                path = root / "python/install" / relative
                row = {"path": member.name, "install_only_sha256": digest(data)}
                if path.is_file() and sha(path) == digest(data):
                    matched.append(row)
                else:
                    mismatched.append(row)
        notices = [
            retain("CPython-3.12.13", p.name, p.read_bytes(), full["url"])
            for p in (root / "python/licenses").rglob("*")
            if p.is_file()
        ]
        dump(
            AUDIT / "pbs-correspondence.json",
            {
                "full_archive": full,
                "matched_files": len(matched),
                "mismatched": mismatched,
                "notices": notices,
                "status": "PASS" if not mismatched else "NOT VERIFIED",
                "scope": "exact install_only file bytes vs full archive; does not establish CRT contract rights",
            },
        )
        metadata = json.loads((AUDIT / "evidence/pbs-python-full.json").read_text(encoding="utf-8"))
        extensions = metadata.get("build_info", {}).get("extensions", {})
        rows = [
            {
                "name": name,
                "parent": "CPython-3.12.13",
                "classification": "THIRD-PARTY",
                "status": "NOT VERIFIED",
                "build_records": records,
            }
            for name, records in extensions.items()
            if any(r.get("license_paths") for r in records)
        ]
        dump(AUDIT / "pbs-embedded-components.json", rows)
        print(
            f"PBS full/install-only matched {len(matched)} files; mismatches {len(mismatched)}; retained {len(notices)} license files"
        )
    finally:
        shutil.rmtree(root)


def embedded_sources() -> None:
    from tools.vendor_payload import materialize

    contents = {}
    vendors = []

    def collect(name, data, parent):
        if name.endswith("/vendor.txt"):
            vendors.append({"parent": parent, "path": name, "requirements": data.decode("utf-8")})
        if "/_vendor/certifi/" in name and not name.endswith("/"):
            contents[parent + "/" + name] = data

    with tarfile.open(materialize("python")) as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            stream = archive.extractfile(member)
            assert stream is not None
            data = stream.read()
            collect(member.name, data, "CPython-3.12.13")
            if member.name.endswith(".whl"):
                with zipfile.ZipFile(io.BytesIO(data)) as wheel:
                    for name in wheel.namelist():
                        if not name.endswith("/"):
                            collect(name, wheel.read(name), "ensurepip-25.0.1")
    with zipfile.ZipFile(materialize("wheels")) as archive:
        for member in archive.namelist():
            if not member.startswith("pip-"):
                continue
            with zipfile.ZipFile(io.BytesIO(archive.read(member))) as wheel:
                for name in wheel.namelist():
                    if not name.endswith("/"):
                        collect(name, wheel.read(name), "pip-26.2.1")
    assert contents
    destination = ROOT / "SOURCE_OBLIGATIONS/vendored-certifi-source.tar.gz"
    with tarfile.open(destination, "w:gz") as output:
        for name, data in sorted(contents.items()):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mtime = 0
            output.addfile(info, io.BytesIO(data))
    dump(AUDIT / "embedded-vendor-requirements.json", vendors)
    dump(
        AUDIT / "vendored-certifi-source.json",
        {
            "archive": destination.relative_to(ROOT).as_posix(),
            "sha256": sha(destination),
            "files": [
                {"path": n, "sha256": digest(d), "size": len(d)}
                for n, d in sorted(contents.items())
            ],
            "scope": "exact shipped preferred-source .py/.pem/license files, including pip vendoring changes; no source offer",
        },
    )
    print(
        f"Provided {len(contents)} exact vendored certifi source files; {len(vendors)} vendor requirement manifests"
    )


def audit_vendors() -> None:
    results = []
    for parent in json.loads(
        (AUDIT / "embedded-vendor-requirements.json").read_text(encoding="utf-8")
    ):
        directory = Path(tempfile.mkdtemp(prefix="vendor-advisory-", dir=ROOT / ".cache/tmp"))
        try:
            requirements = directory / "requirements.txt"
            requirements.write_text(
                "\n".join(
                    name + "==" + version
                    for name, version in re.findall(
                        r"^\s*([\w.-]+)==([^\s]+)", parent["requirements"], re.M
                    )
                )
                + "\n",
                encoding="utf-8",
            )
            output = directory / "advisories.json"
            process = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip_audit",
                    "-r",
                    str(requirements),
                    "--no-deps",
                    "--disable-pip",
                    "--format",
                    "json",
                    "--output",
                    str(output),
                ],
                capture_output=True,
                timeout=150,
            )
            results.append(
                {
                    "parent": parent["parent"],
                    "returncode": process.returncode,
                    "report": json.loads(output.read_text(encoding="utf-8"))
                    if output.is_file()
                    else "NOT VERIFIED",
                    "scope": "declared upstream versions; pip vendor patches and runtime reachability need individual review",
                }
            )
        finally:
            shutil.rmtree(directory)
    dump(AUDIT / "security-embedded-vendors.json", results)
    print(
        json.dumps(
            [
                {
                    "parent": row["parent"],
                    "returncode": row["returncode"],
                    "vulnerabilities": sum(
                        len(d["vulns"]) for d in row["report"].get("dependencies", [])
                    )
                    if isinstance(row["report"], dict)
                    else "NOT VERIFIED",
                }
                for row in results
            ],
            indent=2,
        )
    )


def summarize_vendors() -> None:
    reports = json.loads((AUDIT / "security-embedded-vendors.json").read_text(encoding="utf-8"))
    aliases = set()
    text = "# 内包依存のadvisory候補\n\n監査日: 2026-10-02。判定: NOT VERIFIED / LC-07。\n\n"
    text += "同一IDの重複を除き、parent・実申告版ごとに記録する。上流の全パッケージとpipの内包サブセットは同じではなく、未検証の実脆弱性件数として扱わない。\n\n"
    text += "| Parent | Component | Version | Unique advisory IDs | Fixed versions |\n|---|---|---|---|---|\n"
    counts = []
    for report in reports:
        count = 0
        for package in report["report"]["dependencies"]:
            unique = {v["id"]: v for v in package["vulns"]}
            if not unique:
                continue
            count += len(unique)
            for vulnerability in unique.values():
                aliases.update(a for a in vulnerability.get("aliases", []) if a.startswith("GHSA-"))
            fixed = sorted({version for v in unique.values() for version in v["fix_versions"]})
            text += f"| {report['parent']} | {package['name']} | {package['version']} | {', '.join(unique)} | {', '.join(fixed)} |\n"
        counts.append({"parent": report["parent"], "unique_package_advisory_candidates": count})
    evidence = []
    for alias in sorted(aliases):
        url = "https://api.github.com/advisories/" + alias
        try:
            data = fetch(url)
            path = AUDIT / "evidence/advisories" / (alias + ".json")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            evidence.append(
                {
                    "id": alias,
                    "url": url,
                    "path": path.relative_to(ROOT).as_posix(),
                    "sha256": digest(data),
                    "status": "retrieved",
                }
            )
        except (OSError, ValueError) as error:
            evidence.append(
                {
                    "id": alias,
                    "url": url,
                    "status": "NOT VERIFIED",
                    "error_type": type(error).__name__,
                }
            )
    text += "\n## 適用判定と現在の対策\n\n"
    text += "- pipのsetuptools宣言は主としてpkg_resourcesを内包し、setuptools全体を同梱した証明ではない。PackageIndex/FileListのadvisoryを版だけで適用しない。\n"
    text += "- msgpackのUnpacker/C extension問題は、pipのfallback実装と実呼出条件の確認が必要。版だけで修正済み/該当と確定しない。\n"
    text += "- urllib3/requests/idnaは通信処理の候補。公式setupはno-index/no-depsでネットワーク取得を行わず、アプリ本体はhttpxを使う。任意のpipネットワーク利用まで修正済みとは判定しない。\n"
    text += "- 更新による内包importやvendor patchの破損を避けるため、上流版を単純上書きしない。適用する修正の確認と再監査が済むまでLC-07を維持する。\n"
    text += (
        "- 原advisoryの取得結果はadvisory-evidence.json。配布バイナリ全CVEの網羅検査ではない。\n"
    )
    (AUDIT / "25-embedded-advisory-review.md").write_text(text, encoding="utf-8")
    dump(
        AUDIT / "advisory-evidence.json",
        {"counts": counts, "evidence": evidence, "final_status": "NOT VERIFIED"},
    )
    print(json.dumps(counts, indent=2))


def acquire() -> None:
    results = []
    release_url = (
        "https://api.github.com/repos/astral-sh/python-build-standalone/releases/tags/20260325"
    )
    release = json.loads(fetch(release_url))
    assets = [
        a
        for a in release["assets"]
        if a["name"].startswith("cpython-3.12.13+20260325-x86_64-pc-windows-msvc-")
    ]
    dump(AUDIT / "evidence/pbs-release-assets.json", {"url": release_url, "assets": assets})
    full = [a for a in assets if a["name"].endswith("-full.tar.zst") and "debug" not in a["name"]]
    for asset in full:
        try:
            data = fetch(asset["browser_download_url"])
            if asset.get("digest") != "sha256:" + digest(data):
                raise ValueError("publisher full archive digest mismatch")
            path = ROOT / ".cache/downloads" / asset["name"]
            path.write_bytes(data)
            system_tar = Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32/tar.exe"
            result = subprocess.run(
                [str(system_tar), "-xOf", str(path), "python/PYTHON.json"],
                capture_output=True,
                check=True,
                timeout=90,
            )
            metadata = json.loads(result.stdout)
            dump(AUDIT / "evidence/pbs-python-full.json", metadata)
            results.append(
                {
                    "url": asset["browser_download_url"],
                    "sha256": digest(data),
                    "metadata": "license-audit/evidence/pbs-python-full.json",
                    "status": "retrieved",
                    "install_only_byte_correspondence": "NOT VERIFIED",
                }
            )
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            results.append(
                {
                    "url": asset["browser_download_url"],
                    "status": "NOT VERIFIED",
                    "error_type": type(error).__name__,
                }
            )
    sources = {
        "chrome-additional-terms": "https://www.google.com/chrome/terms/",
        "chrome-for-testing-official": "https://developer.chrome.com/blog/chrome-for-testing/",
        "pbs-windows-build": "https://raw.githubusercontent.com/astral-sh/python-build-standalone/20260325/cpython-windows/build.py",
        "node-24.21.0-license": "https://raw.githubusercontent.com/nodejs/node/v24.21.0/LICENSE",
    }
    for name, url in sources.items():
        try:
            data = fetch(url)
            path = AUDIT / "evidence/upstream" / (name + ".txt")
            path.write_bytes(data)
            if name.startswith("chrome-"):
                text = PageText()
                text.feed(data.decode("utf-8", errors="replace"))
                path.with_suffix(".readable.txt").write_text(
                    "\n".join(text.parts), encoding="utf-8"
                )
            results.append(
                {
                    "url": url,
                    "path": path.relative_to(ROOT).as_posix(),
                    "sha256": digest(data),
                    "status": "retrieved",
                    "scope": "current official document, not proof of individual contractual permission",
                }
            )
        except (OSError, ValueError) as error:
            results.append(
                {"url": url, "status": "NOT VERIFIED", "error_type": type(error).__name__}
            )
    dump(AUDIT / "reaudit-upstream.json", results)
    print(json.dumps(results, ensure_ascii=False, indent=2))


def reconcile(directory: Path) -> None:
    manifest = json.loads((ROOT / "vendor/windows-x64/manifest.json").read_text(encoding="utf-8"))
    sbom = json.loads((AUDIT / "sbom.cdx.json").read_text(encoding="utf-8"))
    by_ref = {c["bom-ref"]: c for c in sbom["components"]}
    packages = json.loads((AUDIT / "packages.json").read_text(encoding="utf-8"))
    secret_triage = json.loads((AUDIT / "secret-triage.json").read_text(encoding="utf-8"))
    assert secret_triage["unresolved"] == 0
    known_secret_templates = {
        (row["location"].removeprefix("worktree:"), row["rule"])
        for row in secret_triage["findings"]
        if row["location"].startswith("worktree:") and row["status"] == "FALSE POSITIVE"
    }
    for package in packages:
        assert by_ref[package["id"]]["hashes"][0]["content"] == package["sha256"]
        assert package["registry"]["wheel_digest_verified"]
        assert not package["unsatisfied"]
    for name, asset in manifest["assets"].items():
        assert by_ref["archive:" + name]["hashes"][0]["content"] == asset["sha256"]
    notice_files = [ROOT / n for n in ("LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md")]
    notice_files.extend(p for p in (ROOT / "THIRD_PARTY_LICENSES").rglob("*") if p.is_file())
    source_files = [p for p in (ROOT / "SOURCE_OBLIGATIONS").rglob("*") if p.is_file()]
    original = json.loads((AUDIT / "browser-pruning.json").read_text(encoding="utf-8"))[
        "original_browser"
    ]
    original_path = ROOT / original["destination"]
    rows = []
    for path in sorted(directory.iterdir()):
        if path.suffix in {".zip", ".whl"}:
            with zipfile.ZipFile(path) as archive:
                contents = {n: archive.read(n) for n in archive.namelist() if not n.endswith("/")}
        elif path.name.endswith(".tar.gz"):
            with tarfile.open(path) as archive:
                contents = {}
                for member in archive.getmembers():
                    if member.isfile():
                        stream = archive.extractfile(member)
                        assert stream is not None
                        contents[member.name] = stream.read()
        else:
            continue
        from tools.license_compliance import secret_findings

        secret_candidates = 0
        for name, data in contents.items():
            for finding in secret_findings(data, name):
                matching = [
                    local
                    for local, rule in known_secret_templates
                    if rule == finding["rule"] and (name == local or name.endswith("/" + local))
                ]
                assert len(matching) == 1 and data == (ROOT / matching[0]).read_bytes(), (
                    "unreviewed credential candidate: " + name
                )
                secret_candidates += 1
        for source in notice_files:
            name = source.relative_to(ROOT).as_posix()
            matches = [data for n, data in contents.items() if n == name or n.endswith("/" + name)]
            assert len(matches) == 1 and digest(matches[0]) == sha(source), name
        if path.suffix != ".whl":
            for source in source_files:
                name = source.relative_to(ROOT).as_posix()
                matches = [
                    data for n, data in contents.items() if n == name or n.endswith("/" + name)
                ]
                assert len(matches) == 1 and digest(matches[0]) == sha(source), name
            allowed = {
                part["file"] for asset in manifest["assets"].values() for part in asset["parts"]
            }
            shipped = {Path(n).name for n in contents if n.endswith(".chunk")}
            assert shipped == allowed, "inactive or missing vendor chunk"
            for name, asset in manifest["assets"].items():
                data = b"".join(
                    next(d for n, d in contents.items() if n.endswith("/" + part["file"]))
                    for part in asset["parts"]
                )
                assert digest(data) == asset["sha256"]
                if name == "browser":
                    with (
                        zipfile.ZipFile(io.BytesIO(data)) as current,
                        zipfile.ZipFile(original_path) as previous,
                    ):
                        for member in current.namelist():
                            assert not member.startswith("ffmpeg-")
                            assert current.read(member) == previous.read(member), (
                                "retained browser modified"
                            )
                        assert set(previous.namelist()) - set(current.namelist()) == {
                            n for n in previous.namelist() if n.startswith("ffmpeg-")
                        }
        rows.append(
            {
                "artifact": path.name,
                "sha256": sha(path),
                "notices_byte_matched": len(notice_files),
                "source_archives_byte_matched": len(source_files)
                if path.suffix != ".whl"
                else "not bundled in wheel; source URLs supplied",
                "vendor_sbom_reconciled": path.suffix != ".whl",
                "unused_ffmpeg_excluded": path.suffix != ".whl",
                "secret_candidates_exact_reviewed_source": secret_candidates,
            }
        )
    dump(
        AUDIT / "package-reconciliation.json",
        {
            "artifacts": rows,
            "wheels_verified": len(packages),
            "containers_verified": len(manifest["assets"]),
            "sbom_closure": "PARTIAL",
            "license_clearance": "BLOCKED",
        },
    )
    print(
        f"Reconciled {len(rows)} artifacts, {len(notice_files)} notice files; FFmpeg excluded, retained browser bytes identical"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=[
            "acquire",
            "python-correspondence",
            "embedded-sources",
            "audit-vendors",
            "summarize-vendors",
            "reconcile",
        ],
    )
    parser.add_argument("--directory", type=Path)
    args = parser.parse_args()
    if args.action == "acquire":
        acquire()
    elif args.action == "python-correspondence":
        python_correspondence()
    elif args.action == "embedded-sources":
        embedded_sources()
    elif args.action == "audit-vendors":
        audit_vendors()
    elif args.action == "summarize-vendors":
        summarize_vendors()
    elif args.directory:
        reconcile(args.directory)
    else:
        parser.error("reconcile requires --directory")
