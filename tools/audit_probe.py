"""Reproducible offline inventory and performance probes for the quality audit."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def inventory() -> dict:
    """Count actual files without following links or reading user data."""
    groups: Counter[str] = Counter()
    sizes: Counter[str] = Counter()
    sources = []
    for directory, dirs, files in os.walk(ROOT, followlinks=False):
        dirs[:] = [d for d in dirs if not (Path(directory) / d).is_symlink()]
        for name in files:
            path = Path(directory) / name
            rel = path.relative_to(ROOT)
            group = rel.parts[0] if len(rel.parts) > 1 else "root"
            groups[group] += 1
            sizes[group] += path.stat().st_size
            if group in {"core", "web", "tests", "tools", ".github", "root"} and (
                path.suffix in {".py", ".md", ".bat", ".toml", ".txt", ".yml"}
                or name in {"LICENSE", ".gitignore", ".gitattributes"}
            ):
                sources.append(
                    {
                        "path": rel.as_posix(),
                        "bytes": path.stat().st_size,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                )
    return {
        "files_by_group": dict(groups),
        "bytes_by_group": dict(sizes),
        "source_files": sorted(sources, key=lambda x: x["path"]),
        "git_status": subprocess.run(
            ["git", "status", "--short"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout,
        "dependencies": sorted(
            (
                {
                    "name": d.metadata["Name"],
                    "version": d.version,
                    "license": d.metadata.get("License-Expression")
                    or d.metadata.get("License", ""),
                    "license_files": d.metadata.get_all("License-File", []),
                    "project_urls": d.metadata.get_all("Project-URL", []),
                    "requires": d.requires or [],
                }
                for d in importlib.metadata.distributions()
            ),
            key=lambda d: d["name"].lower(),
        ),
    }


def measure(fn, repeats: int = 7) -> dict:
    values = []
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        values.append((time.perf_counter() - start) * 1000)
    return {"median_ms": statistics.median(values), "samples_ms": values}


def benchmark() -> dict:
    from fastapi.testclient import TestClient

    from core.db import get_connection, init_db
    from core.purchases import parse_library_html
    from web.app import create_app
    from web.cli_bridge import Bridge, get_purchases

    html = (
        "<html><body>booth"
        + "".join(
            f'<div><a href="/orders/{i}">item{i}</a><a href="https://booth.pm/items/{i}">p</a></div>'
            for i in range(2000)
        )
        + "</body></html>"
    )
    cache = ROOT / ".cache"
    cache.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="audit-probe-", dir=cache) as td:
        db = init_db(Path(td) / "probe.db")
        conn = get_connection(db)
        conn.executemany(
            "INSERT INTO items(item_id,title) VALUES(?,?)",
            [(str(i), f"商品{i}") for i in range(2000)],
        )
        conn.commit()
        conn.close()
        link = Bridge(db)
        try:
            get_purchases(link)
            result = {
                "parser_2000": measure(lambda: parse_library_html(html), 3),
                "worker_200_rows": measure(lambda: get_purchases(link)),
            }
        finally:
            link.close()
        with TestClient(create_app(db, Path(td) / "lib")) as client:
            client.get("/purchases")
            result["http_purchases_200"] = measure(lambda: client.get("/purchases"))
            result["http_index"] = measure(lambda: client.get("/"))
    return result


def path_benchmark() -> dict:
    from core.db import get_connection, init_db
    from core.download import _stable_item_dir

    with tempfile.TemporaryDirectory(prefix="audit-paths-", dir=ROOT / ".cache") as td:
        root = Path(td) / "lib"
        root.mkdir()
        for i in range(1000):
            (root / f"unrelated_{i}").mkdir()
        conn = get_connection(init_db(Path(td) / "paths.db"))
        try:
            return {
                "new_item_in_1000_directory_library": measure(
                    lambda: _stable_item_dir(root, "12345", "New", conn)
                )
            }
        finally:
            conn.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["inventory", "benchmark", "paths"])
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = {
        "environment": {"python": sys.version, "platform": platform.platform()},
        "result": {"inventory": inventory, "benchmark": benchmark, "paths": path_benchmark}[
            args.mode
        ](),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{args.mode}: {out}")
    if args.mode in {"benchmark", "paths"}:
        print(json.dumps(result["result"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
