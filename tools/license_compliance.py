"""Produce evidence from pinned archives, not installed metadata or prior reports.

Run inventory first; candidate verification never grants release approval.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from email.parser import BytesParser
from email.policy import default
from pathlib import Path
from urllib.parse import urlsplit

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.repository_files import MAX_RELATIVE_PATH_UNITS  # noqa: E402

AUDIT = ROOT / "license-audit"
LICENSES = ROOT / "THIRD_PARTY_LICENSES"
NOTICE_RE = re.compile(r"license|copying|notice|copyright|authors|credits|about", re.I)
NATIVE = {".exe", ".dll", ".pyd", ".so", ".dylib", ".wasm", ".jar", ".lib"}
ASSETS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".svg",
    ".ico",
    ".ttf",
    ".otf",
    ".woff",
    ".woff2",
    ".mp3",
    ".wav",
    ".mp4",
    ".webm",
    ".obj",
    ".fbx",
    ".pdf",
    ".pak",
    ".dat",
}
ORIGIN_RE = re.compile(
    r"Copyright|Licensed under|Source:|Based on|Derived from|Modified from|"
    r"Copied from|Ported from|Adapted from|Inspired by|github\.com|"
    r"gitlab\.com|stackoverflow\.com|gist\.github\.com",
    re.I,
)
# Findings store rule/location only; never matched credential values.
SECRET_RULES = {
    "private-key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "github-token": re.compile(rb"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})"),
    "openai-key": re.compile(rb"\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}"),
    "aws-key": re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
    "credential-assignment": re.compile(
        rb"(?im)^\s*(?:password|api_key|secret|access_token)\s*=\s*[\"'][^\"'\r\n]{12,}[\"']"
    ),
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def safe_name(name: str) -> str:
    return re.sub(r"[^\w.-]+", "_", name)[:180]


def retain(component: str, name: str, data: bytes, source: str) -> dict:
    path = LICENSES / safe_name(component) / (digest(data)[:12] + "-" + safe_name(name))
    if len(path.relative_to(ROOT).as_posix().encode("utf-16-le")) // 2 > MAX_RELATIVE_PATH_UNITS:
        directory = digest(component.encode("utf-8"))[:12] + "-" + safe_name(component)[:48]
        path = LICENSES / directory / (digest(data)[:12] + "-" + safe_name(Path(name).name)[:64])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "original_path": name,
        "sha256": digest(data),
        "size": len(data),
        "source": source,
    }


def entry(name: str, data: bytes, container: str) -> dict:
    return {
        "path": name,
        "container": container,
        "size": len(data),
        "sha256": digest(data),
        "native": Path(name).suffix.lower() in NATIVE,
        "asset": Path(name).suffix.lower() in ASSETS,
    }


def secret_findings(data: bytes, location: str) -> list[dict]:
    return [
        {"rule": key, "location": location, "count": len(pattern.findall(data))}
        for key, pattern in SECRET_RULES.items()
        if pattern.search(data)
    ]


def fetch(url: str) -> bytes:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in {
        "raw.githubusercontent.com",
        "api.github.com",
        "github.com",
        "www.sqlite.org",
        "ffmpeg.org",
        "pypi.org",
        "files.pythonhosted.org",
        "www.google.com",
        "developer.chrome.com",
        "nodejs.org",
        "opencode.ai",
        "dev.meta.ai",
        "policies.google.com",
        "openai.com",
        "static.crates.io",
        "crates.io",
    }:
        raise ValueError("unapproved evidence endpoint")
    request = urllib.request.Request(url, headers={"User-Agent": "BOOTH-Reader-license-audit/1"})  # noqa: S310 - HTTPS allowlist above
    with urllib.request.urlopen(request, timeout=45) as response:  # noqa: S310 - HTTPS allowlist above
        if urlsplit(response.geturl()).scheme != "https":
            raise ValueError("non-HTTPS redirect")
        return response.read()


def registry_check(row: dict) -> dict:
    url = f"https://pypi.org/pypi/{row['name']}/{row['version']}/json"
    try:
        data = fetch(url)
        published = json.loads(data)
        matching = [item for item in published["urls"] if item["filename"] == row["wheel"]]
        valid = len(matching) == 1 and matching[0]["digests"]["sha256"] == row["sha256"]
        derived = None
        if row["name"] == "pip" and (AUDIT / "runtime-derivation.json").is_file():
            provenance = json.loads((AUDIT / "runtime-derivation.json").read_text(encoding="utf-8"))
            if row["sha256"] == provenance["derived_pip_sha256"]:
                valid = (
                    len(matching) == 1
                    and matching[0]["digests"]["sha256"] == provenance["publisher_pip_sha256"]
                )
                derived = {
                    "path": "license-audit/runtime-derivation.json",
                    "publisher_sha256": provenance["publisher_pip_sha256"],
                    "derived_sha256": row["sha256"],
                }
        dump(
            AUDIT / "evidence/registry" / (row["name"] + ".json"),
            {
                "url": url,
                "response_sha256": digest(data),
                "info": published["info"],
                "urls": published["urls"],
                "wheel_digest_verified": valid,
            },
        )
        result = {"url": url, "wheel_digest_verified": valid}
        if derived:
            result["documented_derivation"] = derived
        if row["name"] in {"certifi", "packageurl-python", "pathspec"}:
            sdists = [item for item in published["urls"] if item["packagetype"] == "sdist"]
            if len(sdists) == 1:
                item = sdists[0]
                source = fetch(item["url"])
                if digest(source) != item["digests"]["sha256"]:
                    raise ValueError("source digest mismatch")
                target = ROOT / "SOURCE_OBLIGATIONS" / item["filename"]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source)
                result["source"] = {
                    "path": target.relative_to(ROOT).as_posix(),
                    "sha256": digest(source),
                    "url": item["url"],
                }
                with tarfile.open(fileobj=io.BytesIO(source)) as archive:
                    result["source_notices"] = []
                    if row["name"] == "certifi":
                        with zipfile.ZipFile(ROOT / ".cache/wheels" / row["wheel"]) as original:
                            matched = {}
                            for filename in (
                                "certifi/cacert.pem",
                                "certifi/core.py",
                                "certifi/__init__.py",
                            ):
                                source_member = next(
                                    m
                                    for m in archive.getmembers()
                                    if m.name.endswith("/" + filename)
                                )
                                stream = archive.extractfile(source_member)
                                if stream is None or stream.read() != original.read(filename):
                                    raise ValueError("certifi source does not match wheel")
                                matched[filename] = digest(original.read(filename))
                            result["source_matches_wheel"] = matched
                    for member in archive.getmembers():
                        if member.isfile() and NOTICE_RE.search(Path(member.name).name):
                            stream = archive.extractfile(member)
                            if stream:
                                result["source_notices"].append(
                                    retain(
                                        row["name"] + "-" + row["version"],
                                        member.name,
                                        stream.read(),
                                        item["url"],
                                    )
                                )
        return result
    except (OSError, ValueError, KeyError, tarfile.TarError) as exc:
        return {"url": url, "wheel_digest_verified": False, "error_type": type(exc).__name__}


def inventory(online: bool) -> None:
    AUDIT.mkdir(exist_ok=True)
    lock = (ROOT / "requirements-portable-lock.txt").read_text(encoding="utf-8")
    pinned = dict(re.findall(r"^([\w.-]+)==([^\s]+)", lock, re.M))
    allowed = set(re.findall(r"--hash=sha256:([0-9a-f]{64})", lock))
    runtime = set(re.findall(r"^([\w.-]+)==", (ROOT / "requirements-lock.txt").read_text(), re.M))
    manifest = json.loads((ROOT / "vendor/windows-x64/manifest.json").read_text())
    containers, files, packages, evidence, secrets = [], [], [], [], []
    embedded = []
    from tools.vendor_payload import materialize

    for name in manifest["assets"]:
        archive_path = materialize(name)
        containers.append(
            {
                "name": name,
                "path": archive_path.relative_to(ROOT).as_posix(),
                "sha256": sha(archive_path),
                "size": archive_path.stat().st_size,
                "parts": manifest["assets"][name]["parts"],
            }
        )
        if name == "browser-receipt":
            continue
        if name == "python":
            with tarfile.open(archive_path) as archive:
                for member in archive.getmembers():
                    if not member.isfile():
                        continue
                    stream = archive.extractfile(member)
                    if stream is None:
                        continue
                    data = stream.read()
                    files.append(entry(member.name, data, "CPython-3.12.13"))
                    if NOTICE_RE.search(Path(member.name).name) or member.name.endswith(
                        "/vendor.txt"
                    ):
                        evidence.append(
                            retain("CPython-3.12.13", member.name, data, containers[-1]["path"])
                        )
                    if member.name.endswith(".whl"):
                        with zipfile.ZipFile(io.BytesIO(data)) as nested_wheel:
                            for filename in nested_wheel.namelist():
                                if filename.endswith("/"):
                                    continue
                                content = nested_wheel.read(filename)
                                nested_path = member.name + "!" + filename
                                files.append(entry(nested_path, content, "CPython-3.12.13"))
                                if filename.endswith(".dist-info/METADATA"):
                                    meta = BytesParser(policy=default).parsebytes(content)
                                    embedded.append(
                                        {
                                            "parent": "CPython-3.12.13",
                                            "name": meta["Name"],
                                            "version": meta["Version"],
                                            "path": nested_path,
                                            "license": meta.get("License-Expression")
                                            or meta.get("License"),
                                            "status": "NOT VERIFIED",
                                        }
                                    )
                                if NOTICE_RE.search(Path(filename).name) or filename.endswith(
                                    "/vendor.txt"
                                ):
                                    evidence.append(
                                        retain(
                                            "CPython-3.12.13",
                                            nested_path,
                                            content,
                                            containers[-1]["path"],
                                        )
                                    )
            continue
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue
                data = archive.read(member)
                if name != "wheels":
                    files.append(entry(member.filename, data, name))
                    if NOTICE_RE.search(Path(member.filename).name):
                        evidence.append(retain(name, member.filename, data, containers[-1]["path"]))
                    continue
                if digest(data) not in allowed:
                    raise ValueError("wheel not in lock")
                with zipfile.ZipFile(io.BytesIO(data)) as wheel:
                    metadata_name = next(
                        n
                        for n in wheel.namelist()
                        if n.count("/") == 1 and n.endswith(".dist-info/METADATA")
                    )
                    meta = BytesParser(policy=default).parsebytes(wheel.read(metadata_name))
                    pkg_name = canonicalize_name(meta["Name"])
                    version = meta["Version"]
                    if pinned.get(pkg_name) != version:
                        raise ValueError("wheel version mismatch")
                    notices, nested, native, headers = [], [], [], []
                    for n in wheel.namelist():
                        if n.endswith("/"):
                            continue
                        content = wheel.read(n)
                        files.append(entry(n, content, pkg_name + "@" + version))
                        if NOTICE_RE.search(Path(n).name) or n.endswith("/vendor.txt"):
                            notices.append(
                                retain(pkg_name + "-" + version, n, content, member.filename)
                            )
                        if n.endswith(".dist-info/METADATA") and n != metadata_name:
                            nested_meta = BytesParser(policy=default).parsebytes(content)
                            nested.append(
                                {
                                    "path": n,
                                    "name": nested_meta["Name"],
                                    "version": nested_meta["Version"],
                                }
                            )
                        if Path(n).suffix.lower() in NATIVE:
                            native.append(n)
                        if Path(n).suffix.lower() in {".py", ".js", ".ts", ".h", ".c", ".rs"}:
                            text = content.decode("utf-8", errors="replace")
                            found = ORIGIN_RE.findall(text)
                            if found:
                                headers.append({"path": n, "markers": sorted(set(found))})
                    dependencies, optional, unsatisfied = [], [], []
                    for raw in meta.get_all("Requires-Dist", []):
                        req = Requirement(raw)
                        dep = canonicalize_name(req.name)
                        if req.marker is None or req.marker.evaluate():
                            dependencies.append(dep)
                            if dep not in pinned or not req.specifier.contains(
                                pinned.get(dep, "0")
                            ):
                                unsatisfied.append(raw)
                        else:
                            optional.append(raw)
                    packages.append(
                        {
                            "id": "pkg:pypi/" + pkg_name + "@" + version,
                            "name": pkg_name,
                            "version": version,
                            "wheel": member.filename,
                            "sha256": digest(data),
                            "role": "runtime" if pkg_name in runtime else "development/build",
                            "reported_license": meta.get("License-Expression")
                            or meta.get("License")
                            or "NOT VERIFIED",
                            "authors": meta.get("Author")
                            or meta.get("Author-email")
                            or "NOT VERIFIED",
                            "upstream": meta.get_all("Project-URL", [])
                            + ([meta["Home-page"]] if meta["Home-page"] else []),
                            "dependencies": dependencies,
                            "inactive_or_optional_requirements": optional,
                            "unsatisfied": unsatisfied,
                            "notices": notices,
                            "nested_metadata": nested,
                            "native_files": native,
                            "source_markers": headers,
                            "status": "NOT VERIFIED",
                            "classification": "THIRD-PARTY",
                        }
                    )
    if {p["name"] for p in packages} != set(pinned):
        raise ValueError("incomplete wheel closure")
    if online:
        with ThreadPoolExecutor(max_workers=6) as pool:
            checks = list(pool.map(registry_check, packages))
        for row, check in zip(packages, checks, strict=True):
            row["registry"] = check
            row["notices"].extend(check.get("source_notices", []))
    tracked = (
        git("ls-files", "--cached", "--others", "--exclude-standard", "-z").decode().split("\0")
    )
    repository, origins = [], []
    for name in tracked:
        path = ROOT / name
        if not name or not path.is_file():
            continue
        data = path.read_bytes()
        classification = (
            "THIRD-PARTY"
            if name.startswith(
                ("vendor/", "third_party/", "THIRD_PARTY_LICENSES/", "SOURCE_OBLIGATIONS/")
            )
            else "UNKNOWN"
        )
        if name.startswith(("license-audit/", "audit/")):
            classification = "GENERATED"
        if name.startswith("requirements-"):
            classification = "GENERATED"
        repository.append(
            {
                "path": name,
                "sha256": digest(data),
                "size": len(data),
                "classification": classification,
                "first_commit": git("log", "--diff-filter=A", "--format=%H", "--", name)
                .decode()
                .splitlines(),
                "status": "NOT VERIFIED",
            }
        )
        if len(data) < 2000000:
            secrets.extend(secret_findings(data, "worktree:" + name))
            text = data.decode("utf-8", errors="replace")
            for line_number, line in enumerate(text.splitlines(), 1):
                if ORIGIN_RE.search(line):
                    # URL/header presence, not credential-bearing line contents.
                    origins.append(
                        {
                            "path": name,
                            "line": line_number,
                            "markers": sorted(set(ORIGIN_RE.findall(line))),
                        }
                    )
    # Independently enumerate ignored/local material, without reading user content.
    local = []
    stack = [ROOT]
    while stack:
        base = stack.pop()
        for path in base.iterdir():
            if path == ROOT / ".cache":
                local.append({"path": ".cache", "scope": "private-generated-state-not-read"})
            elif path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                local.append(
                    {"path": path.relative_to(ROOT).as_posix(), "scope": "symlink-not-followed"}
                )
            elif path.is_dir():
                if path.name != ".git" and path not in {AUDIT, LICENSES}:
                    stack.append(path)
            else:
                rel = path.relative_to(ROOT).as_posix()
                if rel in tracked:
                    continue
                scope = "local-generated-or-cache"
                if rel.startswith((".tools/", ".playwright-browsers/", ".venv/")):
                    scope = "third-party-installed-or-generated"
                if rel.startswith(("BOOTH-Reader-Library/", "data/")) or path.suffix == ".db":
                    scope = "private-user-content-excluded"
                local.append(
                    {
                        "path": rel,
                        "size": path.stat().st_size,
                        "scope": scope,
                        "classification": "UNKNOWN"
                        if scope == "private-user-content-excluded"
                        else "GENERATED",
                    }
                )
    history = git("log", "--all", "--format=%H %ad %an %s", "--date=iso-strict").decode()
    (AUDIT / "evidence").mkdir(exist_ok=True)
    (AUDIT / "evidence/git-history.txt").write_text(history, encoding="utf-8")
    # Every historical text blob, including removed files; binary blobs skipped explicitly.
    objects = git("rev-list", "--objects", "--all").decode().splitlines()
    scanned, skipped = 0, []
    for item in objects:
        object_id, _, name = item.partition(" ")
        if not name or git("cat-file", "-t", object_id).strip() != b"blob":
            continue
        size = int(git("cat-file", "-s", object_id))
        if size > 2000000 or Path(name).suffix.lower() in NATIVE | {
            ".chunk",
            ".zip",
            ".gz",
            ".png",
        }:
            skipped.append({"object": object_id, "path": name, "size": size})
            continue
        data = git("cat-file", "blob", object_id)
        if b"\0" in data:
            skipped.append({"object": object_id, "path": name, "size": size})
            continue
        scanned += 1
        secrets.extend(secret_findings(data, "git:" + object_id + ":" + name))
    dump(AUDIT / "repository-inventory.json", repository)
    dump(AUDIT / "local-inventory.json", local)
    dump(AUDIT / "source-markers.json", origins)
    dump(AUDIT / "archive-files.json", files)
    dump(AUDIT / "containers.json", containers)
    dump(AUDIT / "packages.json", packages)
    dump(AUDIT / "embedded-python-packages.json", embedded)
    correspondence = AUDIT / "pbs-correspondence.json"
    if correspondence.is_file():
        evidence.extend(json.loads(correspondence.read_text(encoding="utf-8"))["notices"])
    dump(AUDIT / "license-evidence.json", evidence + [n for p in packages for n in p["notices"]])
    dump(
        AUDIT / "secret-scan.json",
        {
            "rules": list(SECRET_RULES),
            "historical_text_blobs": scanned,
            "skipped_history_blobs": skipped,
            "findings": secrets,
            "scope": "tracked worktree and all reachable historical text blobs; binary resources and private local user data not credential-verified",
        },
    )
    print(
        json.dumps(
            {
                "packages": len(packages),
                "archive_files": len(files),
                "repository_files": len(repository),
                "local_files": len(local),
                "secret_candidates": len(secrets),
                "registry_verified": sum(
                    p.get("registry", {}).get("wheel_digest_verified", False) for p in packages
                ),
            },
            indent=2,
        )
    )


def verify(directory: Path) -> None:
    package_files = []
    results = []
    for line in (directory / "SHA256SUMS.txt").read_text().splitlines():
        expected, name = line.split(None, 1)
        path = directory / name.strip()
        if sha(path) != expected:
            raise ValueError("candidate checksum mismatch")
        results.append({"path": path.name, "sha256": expected, "size": path.stat().st_size})
        if path.suffix in {".zip", ".whl"}:
            with zipfile.ZipFile(path) as archive:
                if archive.testzip() is not None:
                    raise ValueError("CRC failure")
                contents = [(n, archive.read(n)) for n in archive.namelist() if not n.endswith("/")]
        elif path.name.endswith(".tar.gz"):
            with tarfile.open(path) as archive:
                contents = []
                for member in archive.getmembers():
                    if member.issym() or member.islnk():
                        raise ValueError("unexpected archive link")
                    if member.isfile():
                        stream = archive.extractfile(member)
                        if stream:
                            contents.append((member.name, stream.read()))
        else:
            continue
        for name, data in contents:
            if ".." in Path(name).parts or name.startswith("/"):
                raise ValueError("unsafe archive path")
            if Path(name).suffix.lower() in {".db", ".env", ".part", ".pyc"}:
                raise ValueError("private/generated data in package")
            row = entry(name, data, path.name)
            row["secret_candidates"] = secret_findings(data, path.name + ":" + name)
            package_files.append(row)
        if path.suffix == ".zip":
            with zipfile.ZipFile(path) as archive:
                # Check every file produced by the release collector against current inputs.
                inputs = json.loads(archive.read("AUDITED-INPUTS.json"))
                for name, expected_input in inputs.items():
                    source = ROOT / name
                    if (
                        sha(source) != expected_input
                        or digest(archive.read(name)) != expected_input
                    ):
                        raise ValueError("candidate differs from audited source: " + name)
    dump(AUDIT / "distribution-inventory.json", package_files)
    dump(
        AUDIT / "final-package-result.json",
        {
            "artifacts": results,
            "entries": len(package_files),
            "checksums": "PASS",
            "crc": "PASS",
            "collector_byte_comparison": "PASS",
            "nested_archive_inventory": "archive-files.json (validated vendor hashes)",
            "secret_candidates": sum(len(r["secret_candidates"]) for r in package_files),
            "license_clearance": "BLOCKED",
        },
    )
    print(
        f"Verified {len(results)} candidates, {len(package_files)} entries; license clearance BLOCKED"
    )


def triage() -> None:
    report = json.loads((AUDIT / "secret-scan.json").read_text(encoding="utf-8"))
    assessed = []
    for row in report["findings"]:
        location = row["location"]
        if location.startswith("git:"):
            _, object_id, name = location.split(":", 2)
            data = git("cat-file", "blob", object_id)
        else:
            name = location.removeprefix("worktree:")
            data = (ROOT / name).read_bytes()
        matches = SECRET_RULES[row["rule"]].findall(data)
        known = False
        reason = "requires individual review"
        if name == "core/logging_setup.py" and row["rule"] == "private-key":
            known = b"-----BEGIN PRIVATE KEY-----{_REPLACEMENT}" in data and len(matches) == 1
            reason = "redaction replacement template; no key body"
        elif name == "tests/test_auth_security.py":
            if row["rule"] == "private-key":
                known = b"MIIEowIBAAKCAQEAxxxxxxxxxxxxxxxx" in data and len(matches) == 1
                reason = "explicit synthetic PEM fixture in redaction test"
            elif row["rule"] == "credential-assignment":
                known = len(matches) == 1 and b"SUPER-SECRET-COOKIE-VALUE-9f3a" in matches[0]
                reason = "synthetic cookie fixture in isolated full-flow test"
        elif name.endswith(".xml") and row["rule"] == "openai-key":
            known = all(
                value.startswith(b"sk-1234567890abcdef-sk-1234567890abcdef") for value in matches
            )
            reason = "JUnit parameter ID repeats the documented dummy key, not a key value"
        elif name == "tools/license_compliance.py":
            if row["rule"] == "private-key":
                known = len(matches) == 1 and b"PRIVATE KEY-----{_REPLACEMENT}" in data
                reason = "triage checks the redaction template header; no key body"
            elif row["rule"] == "openai-key":
                known = bool(matches) and all(
                    value == b"sk-" + b"1234567890abcdef-" + b"sk-" + b"1234567890abcdef"
                    for value in matches
                )
                reason = "exact synthetic test parameter prefix used by triage"
        assessed.append(
            {**row, "status": "FALSE POSITIVE" if known else "NOT VERIFIED", "reason": reason}
        )
    dump(
        AUDIT / "secret-triage.json",
        {
            "findings": assessed,
            "unresolved": sum(row["status"] == "NOT VERIFIED" for row in assessed),
            "scope": "exact known fixture/template matches only; no credential values retained",
        },
    )
    print(
        f"Secret candidates reviewed: {len(assessed)}; unresolved: {sum(r['status'] == 'NOT VERIFIED' for r in assessed)}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["inventory", "verify", "triage"])
    parser.add_argument("--online", action="store_true")
    parser.add_argument("--directory", type=Path)
    args = parser.parse_args()
    if args.action == "inventory":
        inventory(args.online)
    elif args.action == "triage":
        triage()
    elif args.directory:
        verify(args.directory)
    else:
        parser.error("verify requires --directory")


if __name__ == "__main__":
    main()
