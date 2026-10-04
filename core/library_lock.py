"""Process-level exclusion for download batches and destructive partial cleanup."""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from .errors import BoothError


@contextmanager
def library_lock(root: str | Path) -> Generator[None, None, None]:
    if os.name != "nt":
        raise BoothError("ダウンロードの排他制御は Windows のみ対応しています。")
    import msvcrt

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
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as e:
            raise BoothError("ライブラリで別のダウンロードまたは削除処理が実行中です。") from e
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
