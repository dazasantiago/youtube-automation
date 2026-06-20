"""YouTube source adapter: channel bootstrap and daily scan."""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from googleapiclient.discovery import build  # type: ignore[import-untyped]

from content_intel.db import DB_PATH, get_db, log_quota

logger = logging.getLogger(__name__)

YOUTUBE_API_VERSION = "v3"
YOUTUBE_SERVICE_NAME = "youtube"

# ---------------------------------------------------------------------------
# Channel list — lives at repo root, not inside src/
# ---------------------------------------------------------------------------

# Add repo root to sys.path so channels_final.py is importable at runtime.
_repo_root = Path(__file__).parent.parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

CHANNELS: list[tuple[int, str, str, str]]
try:
    from channels_final import CHANNELS
except ImportError:
    CHANNELS = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_duration(duration: str) -> int:
    """Parse ISO 8601 duration string like PT4M13S to seconds."""
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
    if not m:
        return 0
    h, min_, s = (int(x or 0) for x in m.groups())
    return h * 3600 + min_ * 60 + s


def _get_daily_youtube_quota(conn: sqlite3.Connection) -> int:
    """Return total YouTube quota units used today."""
    import datetime as _dt

    today = _dt.date.today().isoformat()
    row = conn.execute(
        "SELECT COALESCE(SUM(units), 0) FROM quota_log WHERE date=? AND service='youtube'",
        (today,),
    ).fetchone()
    return int(row[0]) if row else 0


def _fetch_new_uploads(youtube: Any, conn: sqlite3.Connection) -> list[str]:
    """Returns list of new video IDs not yet in yt_videos."""
    channels = conn.execute(
        "SELECT channel_id, uploads_playlist_id FROM yt_channels WHERE active=1"
    ).fetchall()

    new_ids: list[str] = []
    for channel_row in channels:
        uploads_playlist_id: str = channel_row[1]

        response: dict[str, Any] = (
            youtube.playlistItems()
            .list(
                playlistId=uploads_playlist_id,
                part="contentDetails",
                maxResults=50,
            )
            .execute()
        )
        log_quota("youtube", "playlistItems.list", 1, conn=conn)

        if _get_daily_youtube_quota(conn) >= 7500:
            logger.warning("quota guard hit in _fetch_new_uploads — stopping channel scan early")
            break

        items: list[dict[str, Any]] = response.get("items", [])
        video_ids = [item["contentDetails"]["videoId"] for item in items]

        if not video_ids:
            continue

        placeholders = ",".join("?" * len(video_ids))
        existing_rows = conn.execute(
            f"SELECT video_id FROM yt_videos WHERE video_id IN ({placeholders})",
            video_ids,
        ).fetchall()
        existing_ids = {row[0] for row in existing_rows}

        for vid_id in video_ids:
            if vid_id not in existing_ids:
                new_ids.append(vid_id)

    return new_ids


def _fetch_video_details(
    youtube: Any,
    video_ids: list[str],
    conn: sqlite3.Connection,
) -> None:
    """Fetch details for new video IDs and insert into yt_videos."""
    batch_size = 50
    for i in range(0, len(video_ids), batch_size):
        if _get_daily_youtube_quota(conn) >= 7500:
            logger.warning("quota guard hit in _fetch_video_details — %d/%d video ids processed", i, len(video_ids))
            return
        batch = video_ids[i : i + batch_size]
        response: dict[str, Any] = (
            youtube.videos()
            .list(
                id=",".join(batch),
                part="snippet,statistics,contentDetails",
            )
            .execute()
        )
        log_quota("youtube", "videos.list", 1, conn=conn)

        items: list[dict[str, Any]] = response.get("items", [])
        for item in items:
            video_id: str = item["id"]
            snippet: dict[str, Any] = item["snippet"]
            statistics: dict[str, Any] = item.get("statistics", {})
            content_details: dict[str, Any] = item.get("contentDetails", {})

            channel_id: str = snippet["channelId"]
            title: str = snippet["title"]
            description: str = snippet.get("description", "")[:500]
            published_at_str: str = snippet["publishedAt"]
            published_at = datetime.fromisoformat(
                published_at_str.replace("Z", "+00:00")
            ).isoformat()
            duration_sec = _parse_duration(content_details.get("duration", ""))
            views = int(statistics.get("viewCount", 0))
            likes = int(statistics.get("likeCount", 0))
            comments = int(statistics.get("commentCount", 0))

            conn.execute(
                """
                INSERT OR IGNORE INTO yt_videos (
                    video_id, channel_id, title, description,
                    published_at, duration_sec, views, likes, comments
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    video_id,
                    channel_id,
                    title,
                    description,
                    published_at,
                    duration_sec,
                    views,
                    likes,
                    comments,
                ),
            )


def _refresh_detection_window(youtube: Any, conn: sqlite3.Connection) -> None:
    """Refresh view counts for non-monitored videos in the 30-day detection window."""
    rows = conn.execute(
        """
        SELECT video_id FROM yt_videos
        WHERE monitoring_active=0
          AND datetime(published_at) >= datetime('now', '-30 days')
        """
    ).fetchall()

    video_ids = [row[0] for row in rows]
    if not video_ids:
        return

    batch_size = 50
    for i in range(0, len(video_ids), batch_size):
        if _get_daily_youtube_quota(conn) >= 7500:
            logger.warning(
                "quota guard hit in _refresh_detection_window — %d/%d videos refreshed",
                i,
                len(video_ids),
            )
            return
        batch = video_ids[i : i + batch_size]
        response: dict[str, Any] = (
            youtube.videos()
            .list(
                id=",".join(batch),
                part="statistics",
            )
            .execute()
        )
        log_quota("youtube", "videos.list", 1, conn=conn)

        for item in response.get("items", []):
            vid_id: str = item["id"]
            views = int(item.get("statistics", {}).get("viewCount", 0))
            conn.execute(
                "UPDATE yt_videos SET views=? WHERE video_id=?",
                (views, vid_id),
            )


def _check_outliers(conn: sqlite3.Connection) -> None:
    """Re-evaluate outlier_ratio for non-monitored videos in the 30-day detection window."""
    rows = conn.execute(
        """
        SELECT v.video_id, v.views, c.median_views_30v
        FROM yt_videos v
        JOIN yt_channels c ON v.channel_id = c.channel_id
        WHERE v.monitoring_active=0
          AND datetime(v.published_at) >= datetime('now', '-30 days')
          AND c.median_views_30v IS NOT NULL
          AND c.median_views_30v > 0
        """
    ).fetchall()

    for row in rows:
        video_id: str = row[0]
        views: int = row[1]
        median_views_30v: float = row[2]
        ratio = views / median_views_30v
        if ratio >= 2.0:
            conn.execute(
                """
                UPDATE yt_videos
                SET outlier_ratio=?, monitoring_active=1, monitoring_started_at=?
                WHERE video_id=?
                """,
                (ratio, datetime.now(UTC).isoformat(), video_id),
            )
        else:
            conn.execute(
                "UPDATE yt_videos SET outlier_ratio=? WHERE video_id=?",
                (ratio, video_id),
            )


def _deactivate_expired_monitors(conn: sqlite3.Connection) -> None:
    """Flip monitoring_active to 0 for videos whose 7-day monitoring window has expired."""
    conn.execute(
        """
        UPDATE yt_videos
        SET monitoring_active=0
        WHERE monitoring_active=1
          AND datetime(monitoring_started_at) <= datetime('now', '-7 days')
        """
    )


def _refresh_monitored_videos(youtube: Any, conn: sqlite3.Connection) -> None:
    """Re-fetch stats for actively monitored videos."""
    rows = conn.execute(
        """
        SELECT video_id, published_at, views_history
        FROM yt_videos
        WHERE monitoring_active=1
          AND (last_refreshed_at IS NULL OR datetime(last_refreshed_at) <= datetime('now', '-24 hours'))
        """
    ).fetchall()

    if _get_daily_youtube_quota(conn) >= 7500:
        logger.warning("quota guard hit before _refresh_monitored_videos — skipping entirely")
        return

    video_ids = [row[0] for row in rows]
    history_map: dict[str, str | None] = {row[0]: row[2] for row in rows}

    batch_size = 50
    for i in range(0, len(video_ids), batch_size):
        if _get_daily_youtube_quota(conn) >= 7500:
            logger.warning("quota guard hit in _refresh_monitored_videos — %d/%d videos refreshed", i, len(video_ids))
            return
        batch = video_ids[i : i + batch_size]
        response: dict[str, Any] = (
            youtube.videos()
            .list(
                id=",".join(batch),
                part="statistics",
            )
            .execute()
        )
        log_quota("youtube", "videos.list", 1, conn=conn)

        items: list[dict[str, Any]] = response.get("items", [])
        for item in items:
            vid_id: str = item["id"]
            statistics: dict[str, Any] = item.get("statistics", {})
            views = int(statistics.get("viewCount", 0))
            likes = int(statistics.get("likeCount", 0))
            comments_count = int(statistics.get("commentCount", 0))

            existing_history_json = history_map.get(vid_id)
            history: list[dict[str, Any]] = (
                json.loads(existing_history_json)
                if existing_history_json
                else []
            )
            history.append(
                {
                    "ts": datetime.now(UTC).isoformat(),
                    "views": views,
                    "likes": likes,
                    "comments": comments_count,
                }
            )

            conn.execute(
                """
                UPDATE yt_videos
                SET views=?, likes=?, comments=?, views_history=?, last_refreshed_at=?
                WHERE video_id=?
                """,
                (views, likes, comments_count, json.dumps(history), datetime.now(UTC).isoformat(), vid_id),
            )


def _weekly_median_refresh(youtube: Any, conn: sqlite3.Connection) -> None:
    """Refresh median_views_30v for channels that haven't been updated in 7 days."""
    channels = conn.execute(
        """
        SELECT channel_id, uploads_playlist_id
        FROM yt_channels
        WHERE median_updated_at IS NULL OR datetime(median_updated_at) <= datetime('now', '-7 days')
        ORDER BY median_updated_at ASC
        LIMIT 50
        """
    ).fetchall()

    for channel_row in channels:
        if _get_daily_youtube_quota(conn) >= 7500:
            logger.warning("quota guard hit in _weekly_median_refresh — stopping channel median updates early")
            return

        channel_id: str = channel_row[0]
        uploads_playlist_id: str = channel_row[1]

        playlist_response: dict[str, Any] = (
            youtube.playlistItems()
            .list(
                playlistId=uploads_playlist_id,
                part="contentDetails",
                maxResults=30,
            )
            .execute()
        )
        log_quota("youtube", "playlistItems.list", 1, conn=conn)

        playlist_items: list[dict[str, Any]] = playlist_response.get("items", [])
        video_ids = [item["contentDetails"]["videoId"] for item in playlist_items]

        if not video_ids:
            continue

        if _get_daily_youtube_quota(conn) >= 7500:
            logger.warning("quota guard hit in _weekly_median_refresh mid-channel — stopping before videos.list")
            return

        videos_response: dict[str, Any] = (
            youtube.videos()
            .list(
                id=",".join(video_ids),
                part="statistics",
            )
            .execute()
        )
        log_quota("youtube", "videos.list", 1, conn=conn)

        view_counts: list[int] = []
        for item in videos_response.get("items", []):
            vc = int(item.get("statistics", {}).get("viewCount", 0))
            view_counts.append(vc)

        if not view_counts:
            continue

        view_counts.sort()
        n = len(view_counts)
        if n % 2 == 1:
            median = float(view_counts[n // 2])
        else:
            median = (view_counts[n // 2 - 1] + view_counts[n // 2]) / 2.0

        conn.execute(
            "UPDATE yt_channels SET median_views_30v=?, median_updated_at=? WHERE channel_id=?",
            (int(median), datetime.now(UTC).isoformat(), channel_id),
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def bootstrap_channels(db_path: Path = DB_PATH) -> None:
    """Upsert every channel from channels_final.CHANNELS into yt_channels."""
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        logger.error("YOUTUBE_API_KEY environment variable is not set; cannot bootstrap channels")
        return

    youtube: Any = build(YOUTUBE_SERVICE_NAME, YOUTUBE_API_VERSION, developerKey=api_key, cache_discovery=False)

    conn = get_db(db_path)
    inserted = 0
    try:
        for _row_num, _channel_name, handle, tier in CHANNELS:
            response: dict[str, Any] = (
                youtube.channels()
                .list(
                    part="snippet,contentDetails,statistics",
                    forHandle=f"@{handle}",
                )
                .execute()
            )
            log_quota("youtube", "channels.list", 1, conn=conn)

            items: list[dict[str, Any]] = response.get("items", [])
            if not items:
                logger.error("No YouTube channel found for handle @%s", handle)
                continue

            item = items[0]
            channel_id: str = item["id"]
            uploads_playlist_id: str = item["contentDetails"]["relatedPlaylists"]["uploads"]
            channel_name_api: str = item["snippet"]["title"]
            subscriber_count: int = int(item["statistics"].get("subscriberCount", 0))

            language = "en" if tier.startswith("EN") else "es"
            category = tier.split("-")[1] if "-" in tier else tier
            bootstrapped_at = datetime.now(UTC).isoformat()

            conn.execute(
                """
                INSERT INTO yt_channels (
                    channel_id, handle, channel_name, uploads_playlist_id,
                    language, tier, category, subscriber_count, bootstrapped_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(channel_id) DO UPDATE SET
                    handle=excluded.handle,
                    channel_name=excluded.channel_name,
                    uploads_playlist_id=excluded.uploads_playlist_id,
                    language=excluded.language,
                    tier=excluded.tier,
                    category=excluded.category,
                    subscriber_count=excluded.subscriber_count
                """,
                (
                    channel_id,
                    handle,
                    channel_name_api,
                    uploads_playlist_id,
                    language,
                    tier,
                    category,
                    subscriber_count,
                    bootstrapped_at,
                ),
            )
            conn.commit()
            inserted += 1

        logger.info("bootstrap_channels complete: %d channels inserted/updated", inserted)
        _weekly_median_refresh(youtube, conn)
        conn.commit()
    finally:
        conn.close()


def run_yt_scan(db_path: Path = DB_PATH) -> None:
    """Scan YouTube channels for new videos, compute outliers, refresh monitored videos."""
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        logger.error("YOUTUBE_API_KEY not set; skipping yt-scan")
        return

    youtube: Any = build(YOUTUBE_SERVICE_NAME, YOUTUBE_API_VERSION, developerKey=api_key, cache_discovery=False)
    conn = get_db(db_path)
    try:
        if _get_daily_youtube_quota(conn) >= 7500:
            logger.critical("Daily YouTube quota cap reached. Halting.")
            return
        new_ids = _fetch_new_uploads(youtube, conn)
        _fetch_video_details(youtube, new_ids, conn)
        conn.commit()
        _refresh_detection_window(youtube, conn)
        conn.commit()
        _weekly_median_refresh(youtube, conn)
        conn.commit()
        _check_outliers(conn)
        _deactivate_expired_monitors(conn)
        conn.commit()
        _refresh_monitored_videos(youtube, conn)
        conn.commit()
    finally:
        conn.close()
    logger.info("yt-scan complete")
