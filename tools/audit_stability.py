"""Bounded offline stress and forced-kill recovery on disposable SQLite data."""

from __future__ import annotations

import argparse
import ctypes
import gc
import json
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def handles() -> int:
    count = ctypes.c_ulong()
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.GetProcessHandleCount.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    if not kernel.GetProcessHandleCount(kernel.GetCurrentProcess(), ctypes.byref(count)):
        raise ctypes.WinError(ctypes.get_last_error())
    return count.value


def main(argv: list[str] | None = None) -> int:
    from core.db import check_integrity, get_connection, init_db
    from web.cli_bridge import Bridge, get_purchases

    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="audit-stability-", dir=ROOT / ".cache") as td:
        db = init_db(Path(td) / "stress.db")
        conn = get_connection(db)
        conn.execute("INSERT INTO items(item_id,title) VALUES('keep','original')")
        conn.commit()
        conn.close()
        link = Bridge(db)
        try:
            get_purchases(link)
            assert link._worker is not None and link._worker._proc is not None
            worker_pid = link._worker._proc.pid
            gc.collect()
            before = handles()
            barrier = threading.Barrier(8)
            started = time.perf_counter()

            def hammer(n: int) -> None:
                barrier.wait(10)
                for i in range(125):
                    if i % 25 == 0:
                        link.run(["lists", "create", "--name", f"worker-{n}"])
                    assert get_purchases(link)["count"] == 1

            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(hammer, range(8)))
            raw_after = handles()
            del pool
            gc.collect()
            after = handles()
            assert link._worker is not None and link._worker._proc is not None
            assert worker_pid == link._worker._proc.pid
            restarts = link._worker.restarts
            stress = {
                "reads": 1000,
                "writes": 40,
                "threads": 8,
                "elapsed_s": time.perf_counter() - started,
                "handles_before": before,
                "handles_after": after,
                "handles_after_before_gc": raw_after,
                "worker_restarts": restarts,
            }
            print(json.dumps(stress))
            assert after <= before + 8, "process handles grew unexpectedly"
        finally:
            link.close()

        script = (
            "import sqlite3,sys,time; c=sqlite3.connect(sys.argv[1]); "
            "c.execute('BEGIN IMMEDIATE'); "
            "c.execute(\"INSERT INTO items(item_id,title) VALUES('uncommitted','pending')\"); "
            "print('READY',flush=True); time.sleep(60)"
        )
        proc = subprocess.Popen(
            [sys.executable, "-c", script, str(db)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        stdout, stderr = proc.stdout, proc.stderr
        assert stdout is not None and stderr is not None
        try:
            assert stdout.readline().strip() == "READY"
            proc.kill()
            proc.wait(timeout=10)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=10)
            stdout.close()
            stderr.close()
        conn = get_connection(db)
        try:
            assert conn.execute("SELECT item_id FROM items").fetchall()[0][0] == "keep"
            assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM lists").fetchone()[0] == 8
        finally:
            conn.close()
        assert check_integrity(db)["ok"]
        report = {
            "stress": stress,
            "forced_kill_active_transaction": "recovered",
            "integrity": "ok",
            "scope": "short bounded stress; not an hours-long soak",
        }
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
