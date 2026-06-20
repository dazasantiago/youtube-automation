"""Database schema and connection management."""

from __future__ import annotations

import datetime as _dt
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data" / "intel.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  source_id TEXT NOT NULL,
  title TEXT NOT NULL,
  url TEXT,
  description TEXT,
  posted_at TIMESTAMP NOT NULL,
  extracted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  raw_metrics TEXT,
  language TEXT,
  UNIQUE(source, source_id)
);
CREATE INDEX IF NOT EXISTS idx_signals_posted ON signals(posted_at);
CREATE INDEX IF NOT EXISTS idx_signals_source ON signals(source, posted_at DESC);

CREATE TABLE IF NOT EXISTS yt_channels (
  channel_id TEXT PRIMARY KEY,
  handle TEXT NOT NULL,
  channel_name TEXT NOT NULL,
  uploads_playlist_id TEXT NOT NULL,
  language TEXT NOT NULL,
  tier TEXT,
  category TEXT,
  subscriber_count INTEGER,
  median_views_30v INTEGER,
  median_updated_at TIMESTAMP,
  active INTEGER NOT NULL DEFAULT 1,
  bootstrapped_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS yt_videos (
  video_id TEXT PRIMARY KEY,
  channel_id TEXT REFERENCES yt_channels(channel_id),
  title TEXT NOT NULL,
  description TEXT,
  published_at TIMESTAMP NOT NULL,
  duration_sec INTEGER,
  language TEXT,
  views INTEGER,
  likes INTEGER,
  comments INTEGER,
  outlier_ratio REAL,
  views_history TEXT,
  monitoring_active INTEGER NOT NULL DEFAULT 0,
  monitoring_started_at TIMESTAMP,
  last_refreshed_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_yt_videos_published ON yt_videos(published_at);
CREATE INDEX IF NOT EXISTS idx_yt_videos_channel ON yt_videos(channel_id);
CREATE INDEX IF NOT EXISTS idx_yt_videos_outlier ON yt_videos(outlier_ratio);

CREATE TABLE IF NOT EXISTS quota_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  date DATE NOT NULL,
  service TEXT NOT NULL,
  operation TEXT,
  units INTEGER NOT NULL,
  ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_quota_date_service ON quota_log(date, service);

CREATE TABLE IF NOT EXISTS run_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_name TEXT NOT NULL,
  started_at TIMESTAMP NOT NULL,
  finished_at TIMESTAMP,
  status TEXT NOT NULL,
  signals_added INTEGER DEFAULT 0,
  error_message TEXT
);
"""


def get_db(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def init_db(path: Path = DB_PATH) -> None:
    conn = get_db(path)
    try:
        conn.executescript(_SCHEMA)
        _migrations = [
            "ALTER TABLE yt_videos ADD COLUMN monitoring_started_at TIMESTAMP",
            "ALTER TABLE yt_channels ADD COLUMN median_views_30v INTEGER",
            "ALTER TABLE yt_channels ADD COLUMN median_updated_at TIMESTAMP",
        ]
        for migration in _migrations:
            try:
                conn.execute(migration)
                conn.commit()
            except sqlite3.OperationalError:
                pass  # column already exists
    finally:
        conn.close()


def log_quota(
    service: str,
    operation: str,
    units: int,
    conn: sqlite3.Connection | None = None,
    path: Path = DB_PATH,
) -> None:
    """Record API quota usage.

    Reuses `conn` when the caller already has one open to avoid WAL lock contention.
    """
    today = _dt.date.today().isoformat()
    if conn is not None:
        conn.execute(
            "INSERT INTO quota_log (date, service, operation, units) VALUES (?, ?, ?, ?)",
            (today, service, operation, units),
        )
        conn.commit()
        return

    own_conn = get_db(path)
    try:
        own_conn.execute(
            "INSERT INTO quota_log (date, service, operation, units) VALUES (?, ?, ?, ?)",
            (today, service, operation, units),
        )
        own_conn.commit()
    finally:
        own_conn.close()
