"""Cold offline bootstrap, UI, repair exclusion and relocation on Apple Silicon."""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.platforms import load_manifest, target_id  # noqa: E402
from tools.repository_files import collect  # noqa: E402


def run(checkout: Path, args: list[str], *, ok: bool = True) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.update(
        {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(checkout / ".cache/home"),
            "TMPDIR": str(checkout / ".cache/tmp"),
            "PIP_INDEX_URL": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "HTTP_PROXY": "http://127.0.0.1:9",
        }
    )
    result = subprocess.run(
        ["/bin/bash", str(checkout / "start.sh"), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=240,
    )
    if ok and result.returncode:
        raise RuntimeError(f"Launcher failed ({args}): {result.stderr[-3000:]}")
    return result


def web_probe(checkout: Path) -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    log = checkout / ".cache/web-probe.log"
    with log.open("w", encoding="utf-8") as output:
        process = subprocess.Popen(
            ["/bin/bash", str(checkout / "start.sh"), "--port", str(port), "--no-open"],
            cwd=checkout,
            stdout=output,
            stderr=output,
            start_new_session=True,
        )
        try:
            url = f"http://127.0.0.1:{port}"
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(
                        "Web server exited: " + log.read_text(encoding="utf-8")[-2000:]
                    )
                try:
                    with opener.open(url + "/health", timeout=2) as response:
                        assert json.load(response)["ok"]
                    break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("Web server did not become healthy")
            with opener.open(url, timeout=5) as response:
                assert "BOOTH-Reader" in response.read().decode("utf-8")
            assert run(checkout, ["--repair"], ok=False).returncode == 1
            assert run(checkout, ["version"]).returncode == 0
            from playwright.sync_api import sync_playwright

            import core.browser as browser_module

            previous = browser_module.ROOT
            browser_module.ROOT = checkout
            try:
                with sync_playwright() as playwright:
                    browser = browser_module.launch_browser(playwright, headless=True)
                    try:
                        page = browser.new_page()
                        page.goto(url, wait_until="networkidle")
                        assert "BOOTH-Reader" in page.title()
                        for width in (1440, 768, 390):
                            page.set_viewport_size({"width": width, "height": 900})
                            assert page.evaluate(
                                "document.documentElement.scrollWidth <= window.innerWidth"
                            )
                    finally:
                        browser.close()
            finally:
                browser_module.ROOT = previous
        finally:
            if process.poll() is None and sys.platform != "win32":
                os.killpg(process.pid, signal.SIGINT)
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=15)


def main() -> int:
    if target_id() != "macos-arm64":
        raise RuntimeError("This probe requires Mac Apple Silicon")
    work = ROOT / ".cache/macos-clone-proof"
    if work.exists():
        raise RuntimeError("Refusing to overwrite an existing proof directory")
    work.mkdir(parents=True)
    marker = work / "OWNED-BY-PORTABILITY-TEST.txt"
    marker.write_text("macos-clone-proof", encoding="utf-8")
    results: dict[str, object] = {"target": "macos-arm64", "checks": []}
    checks = []
    try:
        checkout = work / "fresh"
        checkout.mkdir()
        for path in collect(ROOT):
            destination = checkout / path.relative_to(ROOT)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
            if path.suffix in {".sh", ".command"}:
                destination.chmod(0o755)
        assert run(checkout, ["--check"], ok=False).returncode == 1
        started = time.monotonic()
        run(checkout, ["setup"])
        results["cold_setup_seconds"] = round(time.monotonic() - started, 3)
        checks.append("cold offline setup without inherited generated state")
        run(checkout, ["--check"])
        assert json.loads(run(checkout, ["lists", "list", "--json"]).stdout)["count"] == 0
        run(checkout, ["lists", "create", "--name", "移動確認"])
        checks.append("CLI JSON and Japanese arguments")
        web_probe(checkout)
        checks.append(
            "real browser 1440/768/390px, Web health, concurrent repair refusal, shutdown"
        )
        moved = work / "日本語 space"
        checkout.rename(moved)
        assert json.loads(run(moved, ["lists", "list", "--json"]).stdout)["count"] == 1
        checks.append("relocation, automatic venv rebuild and preserved DB")
        spec = load_manifest(moved)
        executable = moved / ".playwright-browsers" / spec["browser"]["executable"]
        executable.write_bytes(b"synthetic damaged browser")
        run(moved, ["--repair"])
        assert json.loads(run(moved, ["lists", "list", "--json"]).stdout)["count"] == 1
        checks.append("signature failure recovery from local vendor and preserved DB")
        web_probe(moved)
        checks.append("restart after relocation and repair")
        results["ok"] = True
        return 0
    except Exception as error:
        results["ok"] = False
        results["error"] = str(error)
        raise
    finally:
        results["checks"] = checks
        if marker.is_file() and work.resolve().is_relative_to((ROOT / ".cache").resolve()):
            shutil.rmtree(work)
        results["owned_probe_removed"] = not work.exists()
        (ROOT / ".cache/macos-clone-result.json").write_text(
            json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
