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
            SELECT v.video_id, v.title, v.description,
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
            SELECT v.video_id, v.title, v.description,
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
            "description": r["description"],
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

    # Two handoff files for the topic classifier (compact JSON, each must stay under 25K tokens).
    #
    # handoff.json      — all non-YT signals (hn, reddit, rss, x_apify, github_trending,
    #                     gtrends, hf). No descriptions; titles are sufficient for these sources.
    # handoff_yt.json   — yt: (viral) and yt_under: (flop) videos with truncated descriptions,
    #                     because video titles alone are often clickbait or compilations.

    _YT_DESC_MAX = 150  # chars — keeps handoff_yt.json under the 25K-token Read tool limit

    handoff_items: list[dict[str, str]] = []
    for src, items in payload["signals_by_source"].items():
        for item in items:
            handoff_items.append({
                "id": f"{src}:{item['id']}",
                "title": str(item["title"]),
            })

    handoff_yt_items: list[dict[str, str]] = []
    for v in yt_videos:
        entry: dict[str, str] = {
            "id": f"yt:{v['video_id']}",
            "title": str(v["title"]),
            "url": str(v["url"]),
        }
        if v["description"]:
            entry["description"] = str(v["description"])[:_YT_DESC_MAX]
        handoff_yt_items.append(entry)
    for v in yt_underperformers:
        entry = {
            "id": f"yt_under:{v['video_id']}",
            "title": str(v["title"]),
            "url": str(v["url"]),
        }
        if v["description"]:
            entry["description"] = str(v["description"])[:_YT_DESC_MAX]
        handoff_yt_items.append(entry)

    handoff_path = out_path.parent / "handoff.json"
    handoff_payload = {
        "generated_at": payload["generated_at"],
        "total": len(handoff_items),
        "items": handoff_items,
    }
    handoff_path.write_text(json.dumps(handoff_payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    handoff_yt_path = out_path.parent / "handoff_yt.json"
    handoff_yt_payload = {
        "generated_at": payload["generated_at"],
        "total": len(handoff_yt_items),
        "items": handoff_yt_items,
    }
    handoff_yt_path.write_text(json.dumps(handoff_yt_payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    logger.info(
        "Exported %d signals + %d YT outliers + %d YT underperformers to %s",
        payload["total_signals"],
        len(yt_videos),
        len(yt_underperformers),
        out_path,
    )
    logger.info("Wrote handoff.json (%d items) and handoff_yt.json (%d items) to %s",
                len(handoff_items), len(handoff_yt_items), handoff_path.parent)
    print(f"Exported {payload['total_signals']} signals + {len(yt_videos)} outliers + {len(yt_underperformers)} underperformers -> {out_path}")
    print(f"Handoff: {len(handoff_items)} items -> {handoff_path}")
    print(f"Handoff YT: {len(handoff_yt_items)} items (with descriptions) -> {handoff_yt_path}")
