"""RSS feed source adapter using feedparser."""

from __future__ import annotations

import logging
import re
from calendar import timegm
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import feedparser
import yaml

from content_intel.sources.base import RawSignal, SourceAdapter

logger = logging.getLogger(__name__)

_MAX_AGE = timedelta(hours=48)


def _load_feeds() -> list[str]:
    # src/content_intel/sources/rss.py -> .parent x4 -> repo root
    root = Path(__file__).resolve().parent.parent.parent.parent
    cfg_file = root / "config" / "rss_feeds.yml"
    with cfg_file.open() as f:
        data: dict[str, Any] = yaml.safe_load(f)
    return [str(u) for u in data.get("feeds", [])]


def _parse_time(entry: Any) -> datetime:
    for attr in ("published_parsed", "updated_parsed"):
        val = getattr(entry, attr, None)
        if val is not None:
            try:
                return datetime.fromtimestamp(timegm(val), tz=UTC)
            except Exception:
                pass
    return datetime.now(UTC)


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


class RssAdapter(SourceAdapter):
    name = "rss"

    def fetch(self) -> list[RawSignal]:
        feeds = _load_feeds()
        signals: list[RawSignal] = []
        cutoff = datetime.now(UTC) - _MAX_AGE

        for feed_url in feeds:
            try:
                parsed = feedparser.parse(feed_url)
                for entry in parsed.entries:
                    source_id = str(
                        entry.get("id") or entry.get("link") or ""
                    )
                    if not source_id:
                        continue
                    posted_at = _parse_time(entry)
                    if posted_at < cutoff:
                        continue
                    title = str(entry.get("title", ""))
                    url = str(entry.get("link", "")) or None
                    raw_summary = str(entry.get("summary", ""))
                    description = _strip_html(raw_summary)[:500] or None
                    signals.append(
                        RawSignal(
                            source="rss",
                            source_id=source_id,
                            title=title,
                            url=url,
                            description=description,
                            posted_at=posted_at,
                            raw_metrics={},
                            language="en",
                        )
                    )
            except Exception:
                logger.warning("[rss] failed to parse feed=%r", feed_url, exc_info=True)

        logger.info("[rss] fetched %d signals", len(signals))
        return signals
