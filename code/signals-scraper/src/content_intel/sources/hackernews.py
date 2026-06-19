"""Hacker News source adapter using Algolia search API."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import yaml

from content_intel.sources.base import RawSignal, SourceAdapter

logger = logging.getLogger(__name__)

_ALGOLIA_URL = "https://hn.algolia.com/api/v1/search"


def _load_keywords() -> list[str]:
    # src/content_intel/sources/hackernews.py -> .parent x4 -> repo root
    root = Path(__file__).resolve().parent.parent.parent.parent
    cfg_file = root / "config" / "seed_keywords.yml"
    with cfg_file.open() as f:
        data: dict[str, Any] = yaml.safe_load(f)
    return [str(k) for k in data.get("keywords", [])]


def _fetch_keyword(client: httpx.Client, keyword: str, cutoff_ts: int) -> list[dict[str, Any]]:
    try:
        resp = client.get(
            _ALGOLIA_URL,
            params={
                "query": keyword,
                "tags": "story",
                "numericFilters": f"points>50,created_at_i>{cutoff_ts}",
                "hitsPerPage": 50,
            },
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        return data.get("hits", [])
    except Exception:
        logger.warning("[hn] failed to fetch keyword=%r", keyword, exc_info=True)
        return []


class HackerNewsAdapter(SourceAdapter):
    name = "hn"

    def fetch(self) -> list[RawSignal]:
        keywords = _load_keywords()
        cutoff_ts = int((datetime.now(UTC) - timedelta(hours=72)).timestamp())
        seen: set[str] = set()
        signals: list[RawSignal] = []

        with httpx.Client(timeout=30) as client:
            with ThreadPoolExecutor(max_workers=min(len(keywords), 8)) as executor:
                futures = {
                    executor.submit(_fetch_keyword, client, kw, cutoff_ts): kw
                    for kw in keywords
                }
                for future in as_completed(futures):
                    for hit in future.result():
                        oid = str(hit.get("objectID", ""))
                        if not oid or oid in seen:
                            continue
                        seen.add(oid)
                        created_raw = hit.get("created_at", "")
                        try:
                            posted_at = datetime.fromisoformat(
                                str(created_raw).replace("Z", "+00:00")
                            )
                        except (ValueError, AttributeError):
                            posted_at = datetime.now(UTC)
                        signals.append(
                            RawSignal(
                                source="hn",
                                source_id=oid,
                                title=str(hit.get("title", "")),
                                url=hit.get("url") or f"https://news.ycombinator.com/item?id={oid}",
                                description=hit.get("story_text") or None,
                                posted_at=posted_at,
                                raw_metrics={
                                    "points": hit.get("points", 0),
                                    "num_comments": hit.get("num_comments", 0),
                                },
                                language="en",
                            )
                        )

        logger.info("[hn] fetched %d unique signals", len(signals))
        return signals
