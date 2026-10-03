"""Collect official redistribution metadata without touching user credentials."""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import re
import subprocess
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "license-audit/evidence/redistribution"


def fetch(url: str) -> bytes:
    if not url.startswith("https://"):
        raise ValueError("HTTPS is required")
    with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310 - maintainer supplied HTTPS
        data = response.read()
        return gzip.decompress(data) if data.startswith(b"\x1f\x8b") else data


def retain(name: str, url: str) -> bytes:
    data = fetch(url)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / name).write_bytes(data)
    (EVIDENCE / (name + ".provenance.json")).write_text(
        json.dumps({"url": url, "sha256": hashlib.sha256(data).hexdigest()}, indent=2) + "\n",
        encoding="utf-8",
    )
    return data


def webview_distribution() -> None:
    """Retain Microsoft's official distribution guidance for the fixed runtime."""
    urls = {
        "webview2-distribution.html": (
            "https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution"
        ),
    }
    for name, url in urls.items():
        retain(name, url)
    print(json.dumps({"retained": sorted(urls)}, indent=2))


def vc_runtime() -> None:
    """Retain Microsoft's terms for redistributing the Visual C++ runtime files."""
    urls = {
        "msvc-redistributing-files.html": (
            "https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files"
            "?view=msvc-170"
        ),
    }
    for name, url in urls.items():
        retain(name, url)
    print(json.dumps({"retained": sorted(urls)}, indent=2))


def webview() -> None:
    page = retain(
        "webview-download.html", "https://developer.microsoft.com/en-us/microsoft-edge/webview2/"
    ).decode()
    # Page state contains the official download and EULA pointers.
    links = sorted(set(re.findall(r'https?[^\s"<>\\]+', page)))
    print(
        json.dumps(
            [
                url
                for url in links
                if any(word in url.lower() for word in ("cab", "license", "eula", "webview"))
            ],
            indent=2,
        )
    )
    state = json.loads(re.search(r'id="__NUXT_DATA__">(.*?)</script>', page, re.S).group(1))
    for item in state:
        if isinstance(item, str) and (
            item.endswith(".cab") or "eula" in item.lower() or "license terms" in item.lower()
        ):
            print(item)
    products = json.loads(
        retain(
            "edge-products.json", "https://edgeupdates.microsoft.com/api/products?view=enterprise"
        )
    )
    for product in products:
        if "webview" in product.get("Product", "").lower():
            releases = [
                row
                for row in product["Releases"]
                if row.get("Platform") == "Windows" and row.get("Architecture") == "x64"
            ]
            print(json.dumps({"product": product["Product"], "release": releases[:1]}, indent=2))


def webview_terms() -> None:
    import os
    import sys

    sys.path.insert(0, str(ROOT))
    from playwright.sync_api import sync_playwright

    from core.portable import portable_env

    os.environ.update(portable_env(ROOT))
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(
                "https://developer.microsoft.com/en-us/microsoft-edge/webview2/",
                wait_until="networkidle",
            )
            page.locator(".block-webview2__download-button").click()
            page.wait_for_timeout(1000)
            print(page.locator("body").inner_text())
            EVIDENCE.mkdir(parents=True, exist_ok=True)
            (EVIDENCE / "webview-eula-page.txt").write_text(
                page.locator("body").inner_text(), encoding="utf-8"
            )
        finally:
            browser.close()


def chromium() -> None:
    revision = (
        retain(
            "chromium-last-change.txt",
            "https://storage.googleapis.com/chromium-browser-snapshots/Win_x64/LAST_CHANGE",
        )
        .decode()
        .strip()
    )
    if not revision.isdecimal():
        raise ValueError("Invalid publisher revision")
    url = f"https://storage.googleapis.com/chromium-browser-snapshots/Win_x64/{revision}/chrome-win.zip"
    metadata = json.loads(
        retain(
            "chromium-object.json",
            f"https://storage.googleapis.com/storage/v1/b/chromium-browser-snapshots/o/Win_x64%2F{revision}%2Fchrome-win.zip",
        )
    )
    retain(
        "chromium-revisions.json",
        f"https://storage.googleapis.com/chromium-browser-snapshots/Win_x64/{revision}/REVISIONS",
    )
    target = ROOT / ".cache/downloads" / f"chromium-{revision}.zip"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.is_file():
        with urllib.request.urlopen(url, timeout=120) as response, target.open("wb") as output:
            while block := response.read(1024 * 1024):
                output.write(block)
    data = target.read_bytes()
    if (
        len(data) != int(metadata["size"])
        or base64.b64encode(hashlib.md5(data, usedforsecurity=False).digest()).decode()
        != metadata["md5Hash"]
    ):
        raise RuntimeError("Publisher object checksum mismatch")
    print(
        json.dumps(
            {"revision": revision, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
        )
    )
    with zipfile.ZipFile(target) as archive:
        print(
            json.dumps(
                [
                    name
                    for name in archive.namelist()
                    if name.endswith((".dll", "LICENSE", "credits.html"))
                ],
                indent=2,
            )
        )


def acquire_webview() -> None:
    import os

    from defusedxml.ElementTree import fromstring

    page = (EVIDENCE / "webview-download.html").read_text(encoding="utf-8")
    state = json.loads(re.search(r'id="__NUXT_DATA__">(.*?)</script>', page, re.S).group(1))
    url = next(
        item for item in state if isinstance(item, str) and item.endswith("154.0.4258.53.x64.cab")
    )
    archive = ROOT / ".cache/downloads" / url.rsplit("/", 1)[1]
    if not archive.is_file():
        with urllib.request.urlopen(url, timeout=120) as response, archive.open("wb") as output:  # noqa: S310 - captured official Microsoft download
            while block := response.read(1024 * 1024):
                output.write(block)
    target = ROOT / ".cache/webview-acquisition"
    target.mkdir(parents=True, exist_ok=True)
    expand = Path(os.environ["SYSTEMROOT"]) / "System32/expand.exe"
    subprocess.run(
        [str(expand), str(archive), "-F:*", str(target)],
        capture_output=True,
        check=True,
        timeout=180,
    )
    executable = next(target.rglob("msedgewebview2.exe"))
    powershell = Path(os.environ["SYSTEMROOT"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    command = (
        "$s=Get-AuthenticodeSignature -LiteralPath '"
        + str(executable).replace("'", "''")
        + "'; $s.Status; $s.SignerCertificate.Subject; $s.StatusMessage; if($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notmatch 'Microsoft Corporation'){exit 1}"
    )
    env = dict(os.environ)
    env["PSModulePath"] = str(
        Path(os.environ["SYSTEMROOT"]) / "System32/WindowsPowerShell/v1.0/Modules"
    )
    signature = subprocess.run(
        [str(powershell), "-NoProfile", "-Command", command],
        capture_output=True,
        timeout=60,
        env=env,
    )
    if signature.returncode:
        raise RuntimeError(
            "Microsoft signature validation failed: "
            + (signature.stdout + signature.stderr).decode(errors="replace")
        )
    version = "1.0.4258.31"
    metadata_url = (
        f"https://www.nuget.org/api/v2/Packages(Id='Microsoft.Web.WebView2',Version='{version}')"
    )
    metadata = retain("webview-sdk-metadata.xml", metadata_url)
    nodes = fromstring(metadata)
    package_hash = next(node.text for node in nodes.iter() if node.tag.endswith("}PackageHash"))
    package_url = f"https://api.nuget.org/v3-flatcontainer/microsoft.web.webview2/{version}/microsoft.web.webview2.{version}.nupkg"
    data = fetch(package_url)
    if base64.b64encode(hashlib.sha512(data).digest()).decode() != package_hash:
        raise RuntimeError("NuGet publisher SHA-512 mismatch")
    sdk_archive = ROOT / ".cache/downloads" / f"microsoft.web.webview2.{version}.nupkg"
    sdk_archive.write_bytes(data)
    with zipfile.ZipFile(sdk_archive) as package:
        names = [
            name
            for name in package.namelist()
            if "license" in name.lower()
            or name.endswith(("Core.dll", "WinForms.dll", "WebView2Loader.dll"))
        ]
        print(json.dumps(names, indent=2))
        sdk = target / "sdk"
        sdk.mkdir(exist_ok=True)
        for name in (
            "lib/net462/Microsoft.Web.WebView2.Core.dll",
            "lib/net462/Microsoft.Web.WebView2.WinForms.dll",
            "runtimes/win-x64/native/WebView2Loader.dll",
        ):
            (sdk / name.rsplit("/", 1)[1]).write_bytes(package.read(name))
        for name in names:
            if "license" in name.lower():
                (EVIDENCE / ("webview-sdk-" + name.replace("/", "_"))).write_bytes(
                    package.read(name)
                )
    result = {
        "runtime": {
            "url": url,
            "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "authenticode": "Valid Microsoft Corporation",
            "executable": executable.relative_to(ROOT).as_posix(),
        },
        "sdk": {
            "version": version,
            "url": package_url,
            "publisher_sha512": package_hash,
            "sha256": hashlib.sha256(data).hexdigest(),
        },
    }
    (EVIDENCE / "webview-acquisition.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2))


def pack_webview() -> None:
    acquisition = json.loads((EVIDENCE / "webview-acquisition.json").read_text(encoding="utf-8"))
    runtime = (ROOT / acquisition["runtime"]["executable"]).parent
    sdk = ROOT / ".cache/webview-acquisition/sdk"
    target = ROOT / ".cache/downloads/webview2-154.0.4258.53.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as package:
        for path in sorted(runtime.rglob("*")):
            if path.is_file():
                package.write(path, "webview2/" + path.relative_to(runtime).as_posix())
        for path in sorted(sdk.iterdir()):
            package.write(path, "webview2-sdk/" + path.name)
        package.write(EVIDENCE / "webview-sdk-LICENSE.txt", "webview2-sdk/LICENSE.txt")
        terms = (EVIDENCE / "webview-eula-page.txt").read_text(encoding="utf-8")
        package.writestr(
            "WEBVIEW2-RUNTIME-LICENSE.txt", terms[terms.index("MICROSOFT SOFTWARE LICENSE TERMS") :]
        )
    checksum = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix(".json").write_text(
        json.dumps(
            {
                "sha256": checksum,
                "playwright": "1.63.0",
                "source": "Microsoft WebView2 Fixed Version 154.0.4258.53 and publisher-hash-verified SDK 1.0.4258.31",
                "publisher_signed": True,
                "acquisition": acquisition,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"snapshot": target.name, "sha256": checksum}))


def webview_credits() -> None:
    import os
    import sys

    sys.path.insert(0, str(ROOT))
    from playwright.sync_api import sync_playwright

    from core.browser import launch_browser
    from core.portable import portable_env

    os.environ.update(portable_env(ROOT))
    with sync_playwright() as pw, launch_browser(pw, headless=True) as browser:
        page = browser.new_page()
        page.goto("edge://credits", wait_until="domcontentloaded")
        (EVIDENCE / "webview-third-party-credits.html").write_text(page.content(), encoding="utf-8")
        text = page.locator("body").inner_text()
        (EVIDENCE / "webview-third-party-credits.txt").write_text(text, encoding="utf-8")
        print(json.dumps({"credits_text_bytes": len(text.encode()), "url": page.url}))
        page.goto("https://thirdpartysource.microsoft.com/", wait_until="networkidle")
        print(page.locator("body").inner_text())
        print(
            json.dumps(
                page.locator("input,select").evaluate_all(
                    "elements=>elements.map(e=>({tag:e.tagName,id:e.id,name:e.name,placeholder:e.placeholder}))"
                )
            )
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=[
            "webview",
            "webview-terms",
            "webview-distribution",
            "vc-runtime",
            "chromium",
            "acquire-webview",
            "pack-webview",
            "webview-credits",
        ],
    )
    args = parser.parse_args()
    if args.action == "webview-distribution":
        webview_distribution()
    elif args.action == "vc-runtime":
        vc_runtime()
    elif args.action == "webview":
        webview()
    elif args.action == "webview-terms":
        webview_terms()
    elif args.action == "chromium":
        chromium()
    elif args.action == "acquire-webview":
        acquire_webview()
    elif args.action == "pack-webview":
        pack_webview()
    elif args.action == "webview-credits":
        webview_credits()


if __name__ == "__main__":
    main()
