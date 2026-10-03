"""Shared pytest fixtures and import bootstrap.

``conftest.py`` at the repository root puts the project on ``sys.path`` so the
suite runs from a clean checkout with no installation step and no reliance on
the interpreter's working directory.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

CLI = BASE / "cli.py"


def pytest_configure(config: pytest.Config) -> None:
    """Keep default test scratch data local; explicit --basetemp stays supported."""
    if config.option.basetemp is None:
        config.option.basetemp = str(BASE / ".cache" / "pytest-tmp")


@pytest.fixture
def base_dir() -> Path:
    return BASE


@pytest.fixture
def cli_path() -> Path:
    return CLI


@pytest.fixture
def db(tmp_path: Path) -> Path:
    """An initialised, empty database."""
    from core.db import init_db

    path = tmp_path / "app.db"
    init_db(path)
    return path


@pytest.fixture
def seeded_db(db: Path) -> Path:
    """A database with three items, their purchases, and no classifications."""
    from core.db import get_connection

    conn = get_connection(db)
    try:
        for i in range(3):
            conn.execute(
                "INSERT INTO items(item_id,title,shop,thumbnail,url) VALUES(?,?,?,?,?)",
                (
                    f"id{i}",
                    f"タイトル{i}",
                    f"ショップ{i % 2}",
                    f"https://example.invalid/{i}.png",
                    f"https://example.invalid/{i}",
                ),
            )
            conn.execute(
                "INSERT INTO purchases(item_id,purchase_date,price) VALUES(?,?,?)",
                (f"id{i}", f"2024-01-0{i + 1}", f"¥{100 * (i + 1)}"),
            )
        conn.commit()
    finally:
        conn.close()
    return db


@pytest.fixture
def cookie_file(tmp_path: Path) -> Path:
    """A syntactically valid cookie jar. No login is ever performed in tests."""
    import json

    path = tmp_path / "cookies.json"
    path.write_text(
        json.dumps(
            [
                {"name": "session", "value": "not-a-real-token", "domain": ".booth.pm"},
            ]
        ),
        encoding="utf-8",
    )
    return path
