from __future__ import annotations

from pathlib import Path

import pytest

from src.db.operations import configure_database, init_db


@pytest.fixture()
def temp_db(tmp_path: Path) -> str:
    db_path = tmp_path / "test.sqlite"
    db_url = f"sqlite:///{db_path}"
    configure_database(db_url)
    init_db()
    return db_url
