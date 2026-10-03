"""Test-only CPython audit hook loaded from an isolated copy's sitecustomize.

Not a kernel monitor: native browser/Node/OS accesses require separate evidence.
Never logs contents, cookie values, environment values or full process argv.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DENIED = [Path(p).resolve() for p in json.loads(os.environ.get("BR_DENY_ROOTS_JSON", "[]"))]
LOG = ROOT / ".cache" / f"python-access-{os.getpid()}.jsonl"
LOG.parent.mkdir(parents=True, exist_ok=True)
STATE = threading.local()


def hook(event: str, args: tuple) -> None:
    if getattr(STATE, "active", False):
        return
    if event not in {
        "open",
        "subprocess.Popen",
        "os.chdir",
        "sqlite3.connect",
        "socket.connect",
        "socket.getaddrinfo",
    } and not event.startswith("winreg."):
        return
    STATE.active = True
    try:
        detail = ""
        if (
            event in {"open", "os.chdir", "subprocess.Popen", "sqlite3.connect"}
            and args
            and isinstance(args[0], (str, bytes, os.PathLike))
        ):
            detail = os.fsdecode(args[0])
            path = Path(detail).resolve()
            if not path.is_relative_to(ROOT) and any(
                path.is_relative_to(denied) for denied in DENIED
            ):
                raise PermissionError("Portable test blocked reference to an original checkout")
            category = "repository" if path.is_relative_to(ROOT) else "external"
        elif event == "socket.connect":
            detail = str(args[1])
            category = "loopback" if args[1][0] in ("127.0.0.1", "::1") else "network"
            if os.environ.get("BR_OFFLINE") == "1" and category == "network":
                raise PermissionError("Offline test blocked external network")
        else:
            category = "OS/DNS/registry"
        row = {
            "event": event,
            "category": category,
            "path_or_address": detail,
            "mode": str(args[1]) if event == "open" else None,
        }
        with LOG.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=True) + "\n")
    finally:
        STATE.active = False


sys.addaudithook(hook)
