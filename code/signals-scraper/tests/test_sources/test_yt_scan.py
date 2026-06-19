"""Tests for YouTube scan logic."""
from __future__ import annotations

import datetime as _dt
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from content_intel.db import get_db, init_db
from content_intel.sources.youtube import (
    _check_outliers,
    _parse_duration,
    run_yt_scan,
)


def test_parse_duration() -> None:
    assert _parse_duration("PT4M13S") == 253
    assert _parse_duration("PT1H30M") == 5400
    assert _parse_duration("PT45S") == 45
    assert _parse_duration("") == 0


def test_check_outliers_marks_high_ratio() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        init_db(db_path)
        conn = get_db(db_path)
        # Insert a channel with known median
        conn.execute(
            "INSERT INTO yt_channels (channel_id, handle, channel_name, uploads_playlist_id, language, median_views_30v) "
            "VALUES ('UC1', 'handle1', 'Channel One', 'UU1', 'en', 10000)"
        )
        # Insert a video published >48h ago with views well above median
        old_time = (datetime.now(UTC) - timedelta(hours=72)).isoformat()
        conn.execute(
            "INSERT INTO yt_videos (video_id, channel_id, title, published_at, views) "
            "VALUES ('vid1', 'UC1', 'Big Hit Video', ?, 50000)",
            (old_time,),
        )
        conn.commit()
        _check_outliers(conn)
        conn.commit()
        row = conn.execute(
            "SELECT outlier_ratio, monitoring_active FROM yt_videos WHERE video_id='vid1'"
        ).fetchone()
        conn.close()
    assert row[0] == pytest.approx(5.0)
    assert row[1] == 1


def test_run_yt_scan_no_api_key() -> None:
    with patch.dict("os.environ", {}, clear=True):
        run_yt_scan()  # should not raise


def test_run_yt_scan_quota_exceeded() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        init_db(db_path)
        # Insert quota log entries totalling > 7500
        conn = get_db(db_path)
        today = _dt.date.today().isoformat()
        conn.execute(
            "INSERT INTO quota_log (date, service, operation, units) VALUES (?, 'youtube', 'test', 7600)",
            (today,),
        )
        conn.commit()
        conn.close()
        with (
            patch.dict("os.environ", {"YOUTUBE_API_KEY": "fake"}),
            patch("content_intel.sources.youtube.build") as mock_build,
        ):
            run_yt_scan(db_path=db_path)
            # build should never have its methods called
            mock_build.return_value.playlistItems.assert_not_called()
