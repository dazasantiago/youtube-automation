#!/usr/bin/env python3
"""Build per-topic input files for topic-deep-research.

Reads topics.json (output of the topic-classifier Claude prompt), resolves each
signal_id against intel.db, and writes one JSON file per topic to data/topic_inputs/.

The output folder is cleared before writing (weekly overwrite — previous week's
files are always replaced).

Usage:
    python code/topic-classifier/build_topic_inputs.py
"""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
TOPICS_JSON = HERE / "data" / "topics.json"
OUT_DIR = HERE / "data" / "topic_inputs"
DB_PATH = HERE.parent / "signals-scraper" / "data" / "intel.db"


def main() -> None:
    if not TOPICS_JSON.exists():
        print(f"Error: {TOPICS_JSON} not found — run the topic-classifier prompt first.")
        return

    if not DB_PATH.exists():
        print(f"Error: {DB_PATH} not found — signals-scraper DB is missing.")
        return

    topics_data: dict[str, Any] = json.loads(TOPICS_JSON.read_text(encoding="utf-8"))
    topics: list[dict[str, Any]] = topics_data.get("topics", [])

    if not topics:
        print("No topics in topics.json.")
        return

    # Weekly overwrite — clear previous week's files before writing new ones
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        generated_at = datetime.now(UTC).isoformat()
        for topic in topics:
            topic_name: str = topic["topic"]
            signal_ids: list[str] = topic.get("signal_ids", [])

            signals, missing = _resolve_signals(signal_ids, conn)

            slug = _slugify(topic_name)
            out_path = OUT_DIR / f"{slug}.json"
            out_path.write_text(
                json.dumps(
                    {"topic": topic_name, "generated_at": generated_at, "signals": signals},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            note = f" ({len(missing)} not found in DB: {missing})" if missing else ""
            print(f"  {slug}.json  ({len(signals)} signals){note}")
    finally:
        conn.close()

    print(f"\nWrote {len(topics)} files to {OUT_DIR}/")
    print("Feed them to topic-deep-research with:")
    print("  uv run deep-research --input code/topic-classifier/data/topic_inputs/<slug>.json")


def _resolve_signals(
    signal_ids: list[str], conn: sqlite3.Connection
) -> tuple[list[dict[str, Any]], list[str]]:
    signals: list[dict[str, Any]] = []
    missing: list[str] = []
    for sid in signal_ids:
        parts = sid.split(":", 1)
        if len(parts) != 2:
            missing.append(sid)
            continue
        prefix, raw_id = parts
        if prefix == "yt":
            row = _fetch_yt_video(raw_id, conn)
        else:
            row = _fetch_signal(prefix, raw_id, conn)
        if row is None:
            missing.append(sid)
        else:
            signals.append(row)
    return signals, missing


def _fetch_signal(
    source: str, source_id: str, conn: sqlite3.Connection
) -> dict[str, Any] | None:
    cur = conn.execute(
        "SELECT source, source_id, title, url, description, posted_at, raw_metrics, language"
        " FROM signals WHERE source = ? AND source_id = ?",
        (source, source_id),
    )
    row = cur.fetchone()
    if row is None:
        return None

    metrics: dict[str, Any] = {}
    if row["raw_metrics"]:
        try:
            metrics = json.loads(row["raw_metrics"])
        except (json.JSONDecodeError, TypeError):
            pass

    return {
        "source": row["source"],
        "source_id": row["source_id"],
        "title": row["title"],
        "url": row["url"],
        "description": row["description"],
        "posted_at": row["posted_at"],
        "language": row["language"],
        "metrics": metrics,
        "signal_type": "signal",
        "roles": ["signal"],
    }


def _fetch_yt_video(video_id: str, conn: sqlite3.Connection) -> dict[str, Any] | None:
    cur = conn.execute(
        "SELECT video_id, title, description, published_at, views, outlier_ratio, language"
        " FROM yt_videos WHERE video_id = ?",
        (video_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None

    outlier_ratio: float = row["outlier_ratio"] or 0.0
    # outlier_ratio < 0.5 = underperformer → saturator role (indicates topic flopped on YT)
    roles = ["saturator"] if outlier_ratio < 0.5 else ["signal"]

    return {
        "source": "youtube",
        "source_id": video_id,
        "title": row["title"],
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "description": row["description"],
        "posted_at": row["published_at"],
        "language": row["language"],
        "metrics": {"views": row["views"], "outlier_ratio": outlier_ratio},
        "signal_type": "yt_video",
        "roles": roles,
    }


def _slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


if __name__ == "__main__":
    main()
