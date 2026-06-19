from __future__ import annotations

import re
import time
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx

from deep_research.enrichers.base import Enricher
from deep_research.models import EnrichedSignal, Signal

_DELAY_SECS = 3
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; deep-research-bot/1.0)"
}


class RedditEnricher(Enricher):
    def __init__(self, top_comments: int = 10) -> None:
        self._top_comments = top_comments

    def can_enrich(self, signal: Signal) -> bool:
        return signal.source.startswith("reddit")

    def enrich(self, signal: Signal, client: httpx.Client) -> EnrichedSignal:
        scraped_at = datetime.now(UTC).isoformat()
        url = signal.url
        if not url or not _is_post_url(url):
            return EnrichedSignal(
                original=signal,
                full_text=None,
                metadata={},
                scraped_at=scraped_at,
                fetch_status="skipped",
                fetch_error="not a direct post url",
            )

        json_url = _to_json_url(url)
        try:
            time.sleep(_DELAY_SECS)
            response = client.get(json_url, headers=_HEADERS, timeout=15)
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", _DELAY_SECS))
                time.sleep(retry_after)
                response = client.get(json_url, headers=_HEADERS, timeout=15)
            response.raise_for_status()

            data = response.json()
            post_data = data[0]["data"]["children"][0]["data"]
            selftext: str = post_data.get("selftext", "") or ""
            post_created: str = str(post_data.get("created_utc", ""))

            raw_comments = data[1]["data"]["children"]
            top_comments = sorted(
                [c for c in raw_comments if c.get("kind") == "t1"],
                key=lambda c: c["data"].get("score", 0),
                reverse=True,
            )[: self._top_comments]

            comments_out = [
                {
                    "body": c["data"].get("body", ""),
                    "score": c["data"].get("score", 0),
                    "created_utc": str(c["data"].get("created_utc", "")),
                }
                for c in top_comments
            ]

            parts = [selftext] + [c["body"] for c in comments_out]
            full_text = "\n\n---\n\n".join(p for p in parts if p)

            return EnrichedSignal(
                original=signal,
                full_text=full_text or None,
                metadata={
                    "post_created_utc": post_created,
                    "comments": comments_out,
                },
                scraped_at=scraped_at,
                fetch_status="ok",
                fetch_error=None,
            )
        except Exception as exc:
            return EnrichedSignal(
                original=signal,
                full_text=None,
                metadata={},
                scraped_at=scraped_at,
                fetch_status="error",
                fetch_error=str(exc),
            )


def _is_post_url(url: str) -> bool:
    return bool(re.search(r"/comments/[a-z0-9]+", url, re.IGNORECASE))


def _to_json_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    return f"https://old.reddit.com{path}.json?limit=100"
