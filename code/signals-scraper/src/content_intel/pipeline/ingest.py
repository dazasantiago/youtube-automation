"""Signal ingestion — pull from sources and write to DB."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC

from content_intel.db import get_db
from content_intel.sources.base import RawSignal, SourceAdapter

logger = logging.getLogger(__name__)

_ALL_SOURCES = [
    "hn",
    "reddit",
    "rss",
    "hf",
    "github_trending",
    "product_hunt",
    "x_apify",
    "gtrends",
]


def _load_adapter(name: str) -> SourceAdapter:
    if name == "hn":
        from content_intel.sources.hackernews import HackerNewsAdapter
        return HackerNewsAdapter()
    if name == "reddit":
        from content_intel.sources.reddit import RedditAdapter
        return RedditAdapter()
    if name == "rss":
        from content_intel.sources.rss import RssAdapter
        return RssAdapter()
    if name == "hf":
        from content_intel.sources.huggingface import HuggingFaceAdapter
        return HuggingFaceAdapter()
    if name == "github_trending":
        from content_intel.sources.github_trending import GitHubTrendingAdapter
        return GitHubTrendingAdapter()
    if name == "product_hunt":
        from content_intel.sources.product_hunt import ProductHuntAdapter
        return ProductHuntAdapter()
    if name == "x_apify":
        from content_intel.sources.x_apify import XApifyAdapter
        return XApifyAdapter()
    if name == "gtrends":
        from content_intel.sources.google_trends import GoogleTrendsAdapter
        return GoogleTrendsAdapter()
    raise ValueError(f"Unknown source: {name}")


def _insert_signal(conn: sqlite3.Connection, sig: RawSignal) -> bool:
    try:
        conn.execute(
            """INSERT INTO signals (source, source_id, title, url, description,
               posted_at, raw_metrics, language)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                sig.source,
                sig.source_id,
                sig.title,
                sig.url,
                sig.description,
                sig.posted_at.astimezone(UTC).isoformat(),
                json.dumps(sig.raw_metrics),
                sig.language,
            ),
        )
        return True
    except sqlite3.IntegrityError:
        return False


def run_pull(sources: str = "all", dry_run: bool = False) -> None:
    names = _ALL_SOURCES if sources == "all" else [s.strip() for s in sources.split(",")]
    all_signals: list[RawSignal] = []

    for name in names:
        try:
            adapter = _load_adapter(name)
            signals = adapter.fetch()
            logger.info("[%s] fetched %d signals", name, len(signals))
            all_signals.extend(signals)
        except Exception as exc:
            logger.exception("[%s] fetch failed: %s", name, exc)

    if dry_run:
        logger.info("Dry run — %d signals fetched, not writing to DB", len(all_signals))
        by_source: dict[str, int] = {}
        for s in all_signals:
            by_source[s.source] = by_source.get(s.source, 0) + 1
        for src, count in sorted(by_source.items()):
            print(f"  {src}: {count}")
        print(f"Total: {len(all_signals)} signals from {len(by_source)} sources")
        return

    inserted = 0
    with get_db() as conn:
        for sig in all_signals:
            if _insert_signal(conn, sig):
                inserted += 1

    logger.info("Inserted %d/%d signals (duplicates skipped)", inserted, len(all_signals))
