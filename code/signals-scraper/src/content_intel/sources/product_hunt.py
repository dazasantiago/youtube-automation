"""Product Hunt source adapter — GraphQL API."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from content_intel.sources.base import RawSignal, SourceAdapter

logger = logging.getLogger(__name__)

_GQL_URL = "https://api.producthunt.com/v2/api/graphql"

_TOPICS = [
    "artificial-intelligence",
    "developer-tools",
    "open-source",
]

_QUERY = """
query($topic: String!, $postedAfter: DateTime!) {
  posts(topic: $topic, order: VOTES, first: 20, postedAfter: $postedAfter) {
    edges {
      node {
        id
        name
        tagline
        url
        votesCount
        commentsCount
        createdAt
      }
    }
  }
}
"""


class ProductHuntAdapter(SourceAdapter):
    name = "product_hunt"

    def fetch(self) -> list[RawSignal]:
        token = os.environ.get("PRODUCT_HUNT_TOKEN")
        if not token:
            logger.warning("[product_hunt] PRODUCT_HUNT_TOKEN not set — skipping")
            return []

        posted_after = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        seen_ids: set[str] = set()
        signals: list[RawSignal] = []

        with httpx.Client(timeout=30) as client:
            for topic in _TOPICS:
                try:
                    resp = client.post(
                        _GQL_URL,
                        json={"query": _QUERY, "variables": {"topic": topic, "postedAfter": posted_after}},
                        headers={
                            "Authorization": f"Bearer {token}",
                            "Content-Type": "application/json",
                            "Accept": "application/json",
                        },
                    )
                    resp.raise_for_status()
                    data: dict[str, Any] = resp.json()
                    edges: list[dict[str, Any]] = (
                        data.get("data", {})
                        .get("posts", {})
                        .get("edges", [])
                    )
                    for edge in edges:
                        node: dict[str, Any] = edge.get("node", {})
                        post_id = str(node.get("id", ""))
                        if not post_id or post_id in seen_ids:
                            continue
                        seen_ids.add(post_id)
                        created_raw = str(node.get("createdAt", ""))
                        try:
                            posted_at = datetime.fromisoformat(
                                created_raw.replace("Z", "+00:00")
                            )
                        except (ValueError, AttributeError):
                            posted_at = datetime.now(UTC)
                        signals.append(
                            RawSignal(
                                source="product_hunt",
                                source_id=post_id,
                                title=str(node.get("name", "")),
                                url=node.get("url"),
                                description=str(node.get("tagline", "")) or None,
                                posted_at=posted_at,
                                raw_metrics={
                                    "votes": node.get("votesCount", 0),
                                    "comments": node.get("commentsCount", 0),
                                    "topic": topic,
                                },
                                language="en",
                            )
                        )
                except Exception:
                    logger.warning("[product_hunt] fetch failed for topic=%r", topic, exc_info=True)

        logger.info("[product_hunt] fetched %d signals", len(signals))
        return signals
