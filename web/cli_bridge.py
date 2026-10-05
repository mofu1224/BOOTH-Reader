"""Web UI -> CLI bridge.

The Web layer never imports ``core``. Every piece of data and every action
travels through the CLI, which stays the single source of truth. Only the
database path and item ids normally cross this boundary. Cookie imports use
stdin on a dedicated subprocess; secret values never enter argv or logs.

Transport
---------
A one-shot ``python cli.py ... --json`` subprocess is the fallback and remains
fully supported, but it costs a fresh interpreter plus module import for every
request (measured at ~65 ms before any work happens). The Web UI issues several
reads per page, so the default transport is a **persistent worker**
(``cli.py rpc``) that speaks newline-delimited JSON over stdin/stdout.

The worker executes the same :func:`cli.main` code path, so both transports are
behaviourally identical; the worker only removes process startup from the loop.
If it cannot start, or dies, the bridge transparently falls back to one-shot
subprocesses.

Long-running work (``download``) always uses a one-shot subprocess so a
multi-hour transfer can never block the worker's request loop.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

log = logging.getLogger("booth_reader.bridge")

WEB_DIR = Path(__file__).resolve().parent
DEFAULT_CLI = WEB_DIR.parent / "cli.py"

VALID_SORTS = ("newest", "oldest", "name", "shop")
VALID_STATUS = ("pending", "downloading", "done", "failed")

# Item ids reach the filesystem as a path component, so they are restricted to
# characters BOOTH actually uses. Anything else is rejected, not sanitised.
_ITEM_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,128}$")
MAX_LIST_NAME = 128

CHILD_ENV_BASE = {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}


class CliBridgeError(RuntimeError):
    """The CLI ran and reported a failure."""

    def __init__(self, message: str, returncode: int = 1, stderr: str = "") -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


class CliAuthError(CliBridgeError):
    """Session expired; the user must log in again."""


class CliLayoutChangedError(CliBridgeError):
    """BOOTH served markup this build cannot parse."""


class WorkerTransportError(CliBridgeError):
    """The worker process could not be reached.

    Distinct from :class:`CliBridgeError` because this one is recoverable by
    falling back to a one-shot subprocess, whereas a CLI error is a real result
    that must be reported to the user.
    """


@dataclass
class CliResult:
    returncode: int
    stdout: str
    stderr: str
    data: dict[str, Any] | None = None
    elapsed_ms: float = 0.0


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def resolve_cli(cli_path: str | Path | None = None) -> Path:
    p = Path(cli_path) if cli_path else DEFAULT_CLI
    if not p.exists():
        raise CliBridgeError(f"cli.py not found: {p}")
    return p


def resolve_python(python_exe: str | Path | None = None) -> str:
    return str(python_exe) if python_exe else sys.executable


def _child_env() -> dict[str, str]:
    """Child environment. JSON stdout is ASCII-escaped; logs use UTF-8."""
    env = dict(os.environ)
    env.update(CHILD_ENV_BASE)
    return env


def sanitize_item_id(item_id: str) -> str:
    value = (item_id or "").strip()
    if not _ITEM_ID_RE.match(value):
        raise CliBridgeError(f"Invalid item_id: {value[:32]!r}", returncode=2)
    return value


def sanitize_list_name(name: str) -> str:
    value = (name or "").strip()
    if not value or len(value) > MAX_LIST_NAME or any(c in value for c in "\n\r\x00"):
        raise CliBridgeError("Invalid list name (1-128 characters)", returncode=2)
    return value


def _clamp_limit(limit: Any, default: int = 200, maximum: int = 1000) -> int:
    try:
        value = int(limit) if limit is not None else default
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, maximum))


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------


def _classify(returncode: int, stdout: str, stderr: str) -> CliBridgeError:
    """Turn a CLI failure into the most specific exception available.

    The CLI documents exit code 3 as "BOOTH markup changed" and 1 as an
    operational failure; stderr is consulted so an auth failure is reported as
    an auth failure even if the exit code is generic.
    """
    err = stderr or ""
    last_err = err.strip().splitlines()[-1].strip() if err.strip() else ""
    last_out = stdout.strip().splitlines()[-1].strip() if stdout.strip() else ""
    if returncode == 3 or "BOOTH_LAYOUT_CHANGED" in (err + stdout):
        raise CliLayoutChangedError(
            last_err or "BOOTH_LAYOUT_CHANGED", returncode=3, stderr=err[-2000:]
        )
    if "auth login" in err or "BOOTH_AUTH_REQUIRED" in err:
        raise CliAuthError(last_err or "Login required", returncode=returncode, stderr=err[-2000:])
    raise CliBridgeError(
        last_err or last_out or f"CLI failed (exit={returncode})",
        returncode=returncode,
        stderr=err[-2000:],
    )


# ---------------------------------------------------------------------------
# One-shot transport
# ---------------------------------------------------------------------------


def run_cli_once(
    argv: list[str],
    db_path: str | Path,
    cli_path: str | Path | None = None,
    python_exe: str | Path | None = None,
    timeout: int = 120,
    stdin_text: str | None = None,
) -> CliResult:
    """Execute the CLI once and return its result.

    The argv list is passed as an argument vector with no shell, so a value
    containing shell metacharacters cannot be interpreted as a command.
    """
    import time

    cli = resolve_cli(cli_path)
    py = resolve_python(python_exe)
    cmd = [py, str(cli), "--db", str(db_path), *argv]
    # Log the subcommand and its first flag only; later args can contain values.
    log.info("cli call: %s", " ".join(argv[:3]))
    started = time.perf_counter()
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, shell=False
            cmd,
            capture_output=True,
            input=stdin_text,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            env=_child_env(),
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise CliBridgeError(f"CLI timed out ({timeout}s)", returncode=124) from e
    except OSError as e:
        raise CliBridgeError(f"CLI launch failed ({type(e).__name__})") from e
    elapsed = (time.perf_counter() - started) * 1000

    data = None
    if "--json" in argv and proc.returncode == 0 and proc.stdout.strip():
        try:
            data = json.loads(proc.stdout)
        except ValueError as e:
            raise CliBridgeError(
                "Cannot parse CLI JSON response",
                returncode=proc.returncode,
                stderr=proc.stderr[-2000:],
            ) from e
    if proc.returncode != 0:
        _classify(proc.returncode, proc.stdout, proc.stderr)
    return CliResult(proc.returncode, proc.stdout, proc.stderr, data, elapsed)


# ---------------------------------------------------------------------------
# Persistent worker transport
# ---------------------------------------------------------------------------


class CliWorker:
    """A long-lived ``cli.py rpc`` process serving JSON-line requests.

    Requests are serialised with a lock: the worker executes them one at a
    time, which also serialises SQLite writes and guarantees that responses
    match requests.
    """

    def __init__(
        self,
        cli_path: str | Path | None = None,
        python_exe: str | Path | None = None,
        db_path: str | Path = "app.db",
    ) -> None:
        self._cli = resolve_cli(cli_path)
        self._python = resolve_python(python_exe)
        self._db = str(Path(db_path).resolve())
        self._proc: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()
        self._next_id = 0
        self.restarts = 0

    # -- lifecycle ---------------------------------------------------------
    def _spawn(self) -> None:
        cmd = [self._python, str(self._cli), "--db", self._db, "rpc"]
        log.info("starting CLI worker: %s", " ".join(cmd[-2:]))
        self._proc = subprocess.Popen(  # noqa: S603 - fixed argv, shell=False
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=_child_env(),
            cwd=str(self._cli.parent),
        )

    def _stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            if proc.stdin:
                proc.stdin.close()
            proc.terminate()
            proc.wait(timeout=5)
        except (OSError, ValueError, subprocess.TimeoutExpired) as e:
            log.debug("worker stop: %s", type(e).__name__)
            with contextlib.suppress(OSError, ValueError):
                proc.kill()
                proc.wait(timeout=5)
        finally:
            for pipe in (proc.stdin, proc.stdout, proc.stderr):
                if pipe is not None:
                    with contextlib.suppress(OSError, ValueError):
                        pipe.close()

    def close(self) -> None:
        with self._lock:
            self._stop()

    def alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    # -- request/response --------------------------------------------------
    def call(self, argv: list[str], timeout: int = 60) -> CliResult:
        import time

        with _request_lock(self._lock, timeout):
            if not self.alive():
                self._stop()
                try:
                    self._spawn()
                except OSError as e:
                    raise WorkerTransportError(
                        f"Cannot start CLI worker ({type(e).__name__})", returncode=125
                    ) from e
            assert self._proc is not None and self._proc.stdin and self._proc.stdout
            self._next_id += 1
            request = {"id": self._next_id, "args": argv}
            started = time.perf_counter()
            try:
                self._proc.stdin.write(json.dumps(request) + "\n")
                self._proc.stdin.flush()
            except (OSError, ValueError) as e:
                self.restarts += 1
                self._stop()
                raise WorkerTransportError(
                    f"Cannot send to CLI worker ({type(e).__name__})", returncode=125
                ) from e

            line = _read_line(self._proc, timeout)
            if line is None:
                # A worker wedged in a long operation cannot be interrupted
                # in-process, so the only safe recovery is to replace it.
                self.restarts += 1
                self._stop()
                raise WorkerTransportError(
                    f"CLI worker did not respond ({timeout}s)", returncode=124
                )

            elapsed = (time.perf_counter() - started) * 1000
            try:
                raw = json.loads(line)
                if not isinstance(raw, dict):
                    raise ValueError("response id/shape mismatch")
                response = cast("dict[str, Any]", raw)
                if response.get("id") != request["id"]:
                    raise ValueError("response id/shape mismatch")
                returncode = int(response.get("returncode", 1))
            except (ValueError, TypeError) as e:
                self.restarts += 1
                self._stop()
                raise WorkerTransportError("Cannot parse worker response", returncode=125) from e

            stdout = str(response.get("stdout") or "")
            stderr = str(response.get("stderr") or "")
            if not response.get("ok"):
                if stderr:
                    _classify(returncode, stdout, stderr)
                raise CliBridgeError(
                    str(response.get("error") or f"CLI failed (exit={returncode})"),
                    returncode=returncode,
                    stderr=stderr[-2000:],
                )
            return CliResult(returncode, stdout, stderr, response.get("data"), elapsed)


@contextlib.contextmanager
def _request_lock(lock: Any, timeout: int) -> Any:
    if not lock.acquire(timeout=timeout):
        raise CliBridgeError(f"CLI worker wait timed out ({timeout}s)", returncode=124)
    try:
        yield
    finally:
        lock.release()


def _read_line(proc: subprocess.Popen[str], timeout: int) -> str | None:
    """Read one line with a wall-clock bound, without blocking forever."""
    result: list[str] = []

    def _read() -> None:
        with contextlib.suppress(OSError, ValueError):
            if proc.stdout:
                result.append(proc.stdout.readline())

    thread = threading.Thread(target=_read, daemon=True, name="br-worker-read")
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        return None
    line = result[0] if result else ""
    return line if line.strip() else None


# ---------------------------------------------------------------------------
# Transport selection
# ---------------------------------------------------------------------------


class Bridge:
    """Facade that prefers the persistent worker and degrades gracefully."""

    def __init__(
        self,
        db_path: str | Path,
        cli_path: str | Path | None = None,
        python_exe: str | Path | None = None,
    ) -> None:
        self.db_path = str(Path(db_path).resolve())
        self.cli_path = cli_path
        self.python_exe = python_exe
        self._worker: CliWorker | None = None
        self._worker_broken = False
        self._lifecycle_lock = threading.RLock()

    def _ensure_worker(self) -> CliWorker | None:
        with self._lifecycle_lock:
            return self._get_worker()

    def _get_worker(self) -> CliWorker | None:
        if self._worker_broken:
            return None
        if self._worker is None:
            try:
                self._worker = CliWorker(self.cli_path, self.python_exe, self.db_path)
            except CliBridgeError as e:
                log.warning("CLI worker unavailable, using one-shot transport: %s", e)
                self._worker_broken = True
                return None
        return self._worker

    def _disable_worker(self) -> None:
        with self._lifecycle_lock:
            self._worker_broken = True
            self.close()

    def run(self, argv: list[str], timeout: int = 60) -> CliResult:
        """Run a read-only CLI command over the fastest available transport."""
        worker = self._ensure_worker()
        if worker is not None:
            try:
                return worker.call(argv, timeout=timeout)
            except WorkerTransportError as e:
                self._disable_worker()
                if not _read_only(argv):
                    raise CliBridgeError(
                        f"{e}. Check whether the operation completed before retrying.",
                        returncode=e.returncode,
                    ) from e
                log.warning("worker transport failure (%s); using one-shot", e)
        return run_cli_once(argv, self.db_path, self.cli_path, self.python_exe, timeout)

    def run_blocking(self, argv: list[str], timeout: int = 3600) -> CliResult:
        """Run a long command in a dedicated process.

        Never uses the worker: a multi-hour download would stall every other
        request behind it.
        """
        return run_cli_once(argv, self.db_path, self.cli_path, self.python_exe, timeout)

    def close(self) -> None:
        with self._lifecycle_lock:
            if self._worker is not None:
                self._worker.close()
                self._worker = None

    @property
    def transport(self) -> str:
        return "worker" if (self._worker is not None and not self._worker_broken) else "one-shot"


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------


def get_purchases(bridge: Bridge, limit: int = 200) -> dict[str, Any]:
    args = ["purchases", "list", "--json", "--limit", str(_clamp_limit(limit))]
    return bridge.run(args, timeout=60).data or {"count": 0, "items": []}


def get_downloads(bridge: Bridge, limit: int = 200, status: str | None = None) -> dict[str, Any]:
    args = ["downloads", "list", "--json", "--limit", str(_clamp_limit(limit))]
    if status in VALID_STATUS:
        args += ["--status", status]
    return bridge.run(args, timeout=30).data or {"count": 0, "downloads": []}


def get_unclassified(bridge: Bridge, sort: str = "newest", limit: int = 200) -> dict[str, Any]:
    normalized = (sort or "newest").lower()
    if normalized not in VALID_SORTS:
        normalized = "newest"
    args = ["unclassified", "--sort", normalized, "--json", "--limit", str(_clamp_limit(limit))]
    return bridge.run(args, timeout=60).data or {"sort": normalized, "count": 0, "items": []}


def get_lists(bridge: Bridge) -> dict[str, Any]:
    return bridge.run(["lists", "list", "--json"], timeout=30).data or {"count": 0, "lists": []}


def get_library(bridge: Bridge) -> dict[str, Any]:
    return bridge.run(["lists", "library", "--json"], timeout=60).data or {}


def import_cookies(bridge: Bridge, payload: str) -> dict[str, Any]:
    return run_cli_once(
        ["auth", "import", "--json"],
        bridge.db_path,
        bridge.cli_path,
        bridge.python_exe,
        timeout=30,
        stdin_text=payload,
    ).data or {"ok": False}


def get_auth_status(bridge: Bridge) -> dict[str, Any]:
    return bridge.run(["auth", "status", "--json"], timeout=30).data or {"ok": True}


def update_purchases(bridge: Bridge) -> dict[str, Any]:
    return bridge.run(["purchases", "list", "--update-db", "--json"], timeout=300).data or {
        "count": 0,
        "items": [],
    }


def lists_create(bridge: Bridge, name: str) -> dict[str, Any]:
    safe = sanitize_list_name(name)
    res = bridge.run(["lists", "create", "--name", safe], timeout=30)
    return {"ok": True, "message": res.stdout.strip()[-500:]}


def lists_add(bridge: Bridge, list_name: str, item_id: str) -> dict[str, Any]:
    safe_list = sanitize_list_name(list_name)
    safe_item = sanitize_item_id(item_id)
    res = bridge.run(["lists", "add", "--list", safe_list, "--item-id", safe_item], timeout=30)
    return {"ok": True, "message": res.stdout.strip()[-500:]}


def lists_remove(bridge: Bridge, list_name: str, item_id: str) -> dict[str, Any]:
    safe_list = sanitize_list_name(list_name)
    safe_item = sanitize_item_id(item_id)
    res = bridge.run(["lists", "remove", "--list", safe_list, "--item-id", safe_item], timeout=30)
    return {"ok": True, "message": res.stdout.strip()[-500:]}


def lists_delete(bridge: Bridge, name: str) -> dict[str, Any]:
    safe = sanitize_list_name(name)
    res = bridge.run(["lists", "delete", "--name", safe], timeout=30)
    return {"ok": True, "message": res.stdout.strip()[-500:]}


def download_argv(
    item_id: str | None = None,
    all: bool = False,
    concurrent: int = 3,
    output_dir: str | Path | None = None,
) -> list[str]:
    """Build and validate the argv for a download. Raises before any side effect."""
    try:
        conc = int(concurrent)
    except (TypeError, ValueError) as e:
        raise CliBridgeError("concurrent must be an integer", returncode=2) from e
    if conc < 1 or conc > 5:
        raise CliBridgeError("concurrent must be 1-5", returncode=2)
    if item_id and all:
        raise CliBridgeError("--item-id and --all are mutually exclusive", returncode=2)
    extra = ["--output-dir", str(output_dir)] if output_dir else []
    if all:
        return ["download", "--all", "--concurrent", str(conc), *extra]
    if item_id:
        return [
            "download",
            "--item-id",
            sanitize_item_id(item_id),
            "--concurrent",
            str(conc),
            *extra,
        ]
    raise CliBridgeError("Specify item_id or all", returncode=2)


def run_download_blocking(
    bridge: Bridge,
    item_id: str | None = None,
    all: bool = False,
    concurrent: int = 3,
    timeout: int = 3600,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    argv = download_argv(item_id=item_id, all=all, concurrent=concurrent, output_dir=output_dir)
    res = bridge.run_blocking(argv, timeout=timeout)
    return {"ok": True, "message": res.stdout.strip()[-2000:]}


def _read_only(argv: list[str]) -> bool:
    return bool(argv) and (
        argv[0] == "unclassified"
        or argv[:2]
        in (["lists", "list"], ["lists", "library"], ["downloads", "list"], ["auth", "status"])
        or (argv[:2] == ["purchases", "list"] and "--update-db" not in argv)
    )
