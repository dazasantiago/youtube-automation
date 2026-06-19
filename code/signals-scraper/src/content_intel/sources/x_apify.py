"""X (Twitter) via Apify source adapter."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import yaml

from content_intel.sources.base import RawSignal, SourceAdapter

logger = logging.getLogger(__name__)

APIFY_BASE = "https://api.apify.com/v2"
ACTOR_ID = "quacker/twitter-scraper"
MAX_TWEETS_PER_USER = 10
MIN_LIKES = 100

_ACCOUNTS_PATH = Path(__file__).parent.parent.parent.parent / "config" / "x_accounts.yml"


class XApifyAdapter(SourceAdapter):
    name = "x_apify"

    def _load_accounts(self) -> list[str]:
        try:
            with open(_ACCOUNTS_PATH) as f:
                data: dict[str, Any] = yaml.safe_load(f) or {}
            accounts: list[str] = data.get("accounts", []) or []
            return accounts
        except Exception:
            logger.warning("Failed to load x_accounts.yml")
            return []

    def fetch(self) -> list[RawSignal]:
        from content_intel.db import log_quota

        token = os.environ.get("APIFY_TOKEN")
        if not token:
            logger.warning("APIFY_TOKEN not set — skipping X/Apify source")
            return []

        accounts = self._load_accounts()
        if not accounts:
            logger.info("No X accounts configured — skipping X/Apify source")
            return []

        since = (
            datetime.now(UTC)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .date()
            .isoformat()
        )
        payload: dict[str, Any] = {
            "searchTerms": [f"from:{user} min_faves:{MIN_LIKES}" for user in accounts],
            "maxItems": len(accounts) * MAX_TWEETS_PER_USER,
            "since": since,
        }

        url = (
            f"{APIFY_BASE}/acts/{ACTOR_ID}/run-sync-get-dataset-items"
            f"?token={token}&timeout=60"
        )

        try:
            response = httpx.post(url, json=payload, timeout=70.0)
            response.raise_for_status()
            tweets: list[dict[str, Any]] = response.json()
        except Exception as exc:
            logger.warning("X/Apify request failed: %s", exc)
            return []

        log_quota("apify", "tweet-scraper-run", 1)

        signals: list[RawSignal] = []
        for tweet in tweets:
            source_id: str | None = tweet.get("id") or tweet.get("tweet_id")
            if not source_id:
                continue

            likes: int = int(tweet.get("likeCount", 0))
            if likes < MIN_LIKES:
                continue

            title: str = tweet.get("text", "")[:280]
            tweet_url: str = tweet.get("url") or f"https://x.com/i/web/status/{source_id}"

            raw_created: str | None = tweet.get("createdAt") or tweet.get("created_at")
            try:
                posted_at = datetime.fromisoformat(raw_created.replace("Z", "+00:00")) if raw_created else datetime.now(UTC)
            except Exception:
                posted_at = datetime.now(UTC)

            raw_metrics: dict[str, object] = {
                "likes": likes,
                "retweets": int(tweet.get("retweetCount", 0)),
            }

            signals.append(
                RawSignal(
                    source=self.name,
                    source_id=source_id,
                    title=title,
                    url=tweet_url,
                    description=None,
                    posted_at=posted_at,
                    raw_metrics=raw_metrics,
                    language="en",
                )
            )

        return signals
