"""Transport agreement, concurrency, and failure semantics."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from core.db import init_db
from web import cli_bridge as bridge


def test_a06_first_concurrent_calls_create_one_worker(seeded_db, monkeypatch):
    workers = []
    original = bridge.CliWorker.__init__

    def delayed(worker, *args, **kwargs):
        original(worker, *args, **kwargs)
        workers.append(worker)
        time.sleep(0.03)

    monkeypatch.setattr(bridge.CliWorker, "__init__", delayed)
    link = bridge.Bridge(seeded_db)
    barrier = threading.Barrier(8)

    def call(_):
        barrier.wait(10)
        return bridge.get_purchases(link)["count"]

    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            assert list(pool.map(call, range(8))) == [3] * 8
        assert len(workers) == 1
    finally:
        link.close()
        for worker in workers:
            worker.close()


def test_a06_close_releases_all_pipes(seeded_db):
    link = bridge.Bridge(seeded_db)
    bridge.get_purchases(link)
    proc = link._worker._proc
    link.close()
    assert proc.poll() is not None
    assert proc.stdin.closed and proc.stdout.closed


def test_a06_relative_db_agrees_in_both_transports(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    init_db("relative.db")
    link = bridge.Bridge("relative.db")
    try:
        assert bridge.get_purchases(link)["items"] == []
        link._disable_worker()
        assert bridge.get_purchases(link)["items"] == []
    finally:
        link.close()


def test_a06_uncertain_mutation_is_not_replayed(seeded_db, monkeypatch):
    link = bridge.Bridge(seeded_db)
    called = []

    def uncertain(worker, argv, timeout):
        raise bridge.WorkerTransportError("response lost", returncode=124)

    monkeypatch.setattr(bridge.CliWorker, "call", uncertain)
    monkeypatch.setattr(
        bridge, "run_cli_once", lambda *a, **k: called.append(a) or bridge.CliResult(0, "", "")
    )
    try:
        with pytest.raises(bridge.CliBridgeError, match="response lost"):
            bridge.lists_create(link, "write")
        assert called == []
    finally:
        link.close()
