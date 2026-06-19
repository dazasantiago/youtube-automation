"""Phase 1 acceptance tests — DB schema and init."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from content_intel.db import init_db

EXPECTED_TABLES = {
    "signals",
    "yt_channels",
    "yt_videos",
    "quota_log",
    "run_log",
}


def _get_app_tables(db_path: Path) -> set[str]:
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence'"
    ).fetchall()
    conn.close()
    return {r[0] for r in rows}


def test_init_db_creates_all_tables() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        init_db(db_path)
        assert _get_app_tables(db_path) == EXPECTED_TABLES


def test_init_db_idempotent() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        init_db(db_path)
        init_db(db_path)  # second call must not raise
        assert _get_app_tables(db_path) == EXPECTED_TABLES


def test_signals_unique_constraint() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        init_db(db_path)
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "INSERT INTO signals (source, source_id, title, posted_at) VALUES (?, ?, ?, ?)",
                ("hn", "123", "Test", "2026-01-01T00:00:00"),
            )
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO signals (source, source_id, title, posted_at) VALUES (?, ?, ?, ?)",
                    ("hn", "123", "Duplicate", "2026-01-01T00:00:00"),
                )
        finally:
            conn.close()
