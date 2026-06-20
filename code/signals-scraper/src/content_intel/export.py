"""Export scraped signals to JSON for LLM consumption."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from content_intel.db import DB_PATH, get_db

logger = logging.getLogger(__name__)

_SOURCE_ORDER = [
    "hn",
    "reddit",
    "rss",
    "x_apify",
    "product_hunt",
    "github_trending",
    "gtrends",
    "hf",
    "yt_videos_en",
    "yt_videos_es",
]


def run_export(days: int = 7, out: str = "data/signals.json", db_path: Path = DB_PATH) -> None:
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()

    conn = get_db(db_path)
    try:
        conn.execute("DELETE FROM signals WHERE posted_at < ?", (cutoff,))
        conn.commit()

        rows = conn.execute(
            """
            SELECT source, source_id, title, url, description, posted_at, raw_metrics, language
            FROM signals
            WHERE posted_at >= ?
            ORDER BY source, posted_at DESC
            """,
            (cutoff,),
        ).fetchall()

        yt_rows = conn.execute(
            """
            SELECT v.video_id, v.title,
                   'https://youtube.com/watch?v=' || v.video_id AS url,
                   v.published_at, v.views, v.outlier_ratio,
                   v.language, c.channel_name
            FROM yt_videos v
            JOIN yt_channels c ON c.channel_id = v.channel_id
            WHERE v.outlier_ratio >= 2.0
              AND datetime(v.published_at) >= datetime('now', '-30 days')
            ORDER BY v.outlier_ratio DESC
            """,
        ).fetchall()

        yt_under_rows = conn.execute(
            """
            SELECT v.video_id, v.title,
                   'https://youtube.com/watch?v=' || v.video_id AS url,
                   v.published_at, v.views, v.outlier_ratio,
                   v.language, c.channel_name
            FROM yt_videos v
            JOIN yt_channels c ON c.channel_id = v.channel_id
            WHERE v.outlier_ratio < 0.5
              AND datetime(v.published_at) <= datetime('now', '-10 days')
              AND datetime(v.published_at) >= datetime('now', '-30 days')
            ORDER BY v.outlier_ratio ASC
            """,
        ).fetchall()
    finally:
        conn.close()

    by_source: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        src = row["source"]
        by_source.setdefault(src, []).append({
            "id": row["source_id"],
            "title": row["title"],
            "url": row["url"],
            "description": row["description"],
            "posted_at": row["posted_at"],
            "language": row["language"],
            "metrics": json.loads(row["raw_metrics"]) if row["raw_metrics"] else {},
        })

    def _yt_row_to_dict(r: sqlite3.Row) -> dict[str, object]:
        return {
            "video_id": r["video_id"],
            "title": r["title"],
            "url": r["url"],
            "published_at": r["published_at"],
            "views": r["views"],
            "outlier_ratio": r["outlier_ratio"],
            "language": r["language"],
            "channel": r["channel_name"],
        }

    yt_videos = [_yt_row_to_dict(r) for r in yt_rows]
    yt_underperformers = [_yt_row_to_dict(r) for r in yt_under_rows]

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "window_days": days,
        "total_signals": sum(len(v) for v in by_source.values()),
        "signals_by_source": {k: by_source[k] for k in _SOURCE_ORDER if k in by_source}
        | {k: v for k, v in by_source.items() if k not in _SOURCE_ORDER},
        "yt_competitor_videos": yt_videos,
        "yt_underperformer_videos": yt_underperformers,
    }

    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info(
        "Exported %d signals + %d YT outliers + %d YT underperformers to %s",
        payload["total_signals"],
        len(yt_videos),
        len(yt_underperformers),
        out_path,
    )
    print(f"Exported {payload['total_signals']} signals + {len(yt_videos)} outliers + {len(yt_underperformers)} underperformers → {out_path}")
