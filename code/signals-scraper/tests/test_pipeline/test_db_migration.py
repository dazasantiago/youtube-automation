"""DB schema verification tests."""

from __future__ import annotations

import sqlite3

from content_intel.db import get_db, init_db


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def test_signals_has_expected_columns(tmp_path) -> None:
    db = tmp_path / "t.db"
    init_db(db)
    conn = get_db(db)
    try:
        cols = _columns(conn, "signals")
        assert {"source", "source_id", "title", "url", "description", "posted_at", "raw_metrics", "language"} <= cols
        assert "topic_id" not in cols
    finally:
        conn.close()


def test_yt_videos_has_expected_columns(tmp_path) -> None:
    db = tmp_path / "t.db"
    init_db(db)
    conn = get_db(db)
    try:
        cols = _columns(conn, "yt_videos")
        assert {"video_id", "channel_id", "title", "views", "outlier_ratio", "monitoring_active"} <= cols
        assert "topic_id" not in cols
    finally:
        conn.close()


def test_init_db_idempotent(tmp_path) -> None:
    db = tmp_path / "t.db"
    init_db(db)
    init_db(db)  # second call must not raise
