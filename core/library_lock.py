"""Process-level exclusion for download batches and destructive partial cleanup."""

from __future__ import annotations

import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from .errors import BoothError


@contextmanager
def library_lock(root: str | Path) -> Generator[None, None, None]:
    directory = Path(root)
    directory.mkdir(parents=True, exist_ok=True)
    # Keep the file after release: unlinking a lock creates a second inode and
    # lets other processes acquire two different locks for the same directory.
    with (directory / ".download.lock").open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            raise BoothError("Another download or cleanup is running in this library.") from e
        try:
            yield
        finally:
            handle.seek(0)
            if sys.platform == "win32":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
