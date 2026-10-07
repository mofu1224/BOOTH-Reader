"""Shared running-app leases and exclusive setup/repair locks."""

from __future__ import annotations

import sys
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def runtime_lock(root: Path, *, exclusive: bool) -> Generator[Callable[[], None], None, None]:
    directory = root / ".cache"
    lock = directory / "runtime.lock"
    if not directory.resolve().is_relative_to(root.resolve()) or lock.is_symlink():
        raise RuntimeError("Runtime lock path escapes the repository")
    directory.mkdir(parents=True, exist_ok=True)
    with lock.open("a+b") as handle:
        if sys.platform == "win32":
            import ctypes
            import msvcrt
            from ctypes import wintypes

            class Overlapped(ctypes.Structure):
                _fields_ = [
                    ("internal", ctypes.c_size_t),
                    ("internal_high", ctypes.c_size_t),
                    ("offset", wintypes.DWORD),
                    ("offset_high", wintypes.DWORD),
                    ("event", wintypes.HANDLE),
                ]

            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.LockFileEx.argtypes = [
                wintypes.HANDLE,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.DWORD,
                ctypes.POINTER(Overlapped),
            ]
            kernel.UnlockFileEx.argtypes = [
                wintypes.HANDLE,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.DWORD,
                ctypes.POINTER(Overlapped),
            ]
            overlapped = Overlapped()
            native = msvcrt.get_osfhandle(handle.fileno())

            def acquire(write: bool) -> None:
                if not kernel.LockFileEx(
                    native, 1 | (2 if write else 0), 0, 1, 0, ctypes.byref(overlapped)
                ):
                    raise RuntimeError(
                        "Runtime is in use. Stop BOOTH-Reader with Ctrl+C before repair."
                    )

            def release() -> None:
                kernel.UnlockFileEx(native, 0, 1, 0, ctypes.byref(overlapped))

            def downgrade() -> None:
                if exclusive:
                    release()
                    acquire(False)

            acquire(exclusive)
            try:
                yield downgrade
            finally:
                release()
        else:
            import fcntl

            mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
            try:
                fcntl.flock(handle.fileno(), mode | fcntl.LOCK_NB)
            except OSError as error:
                raise RuntimeError(
                    "Runtime is in use. Stop BOOTH-Reader with Ctrl+C before repair."
                ) from error
            try:
                yield lambda: fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
