"""Reddit source adapter via public RSS feeds — no API key or app required.

Reddit blocks the unauthenticated `.json` endpoints (HTTP 403 'Blocked') from
most clients/IPs, but the RSS feeds (`/.rss`) still respond. RSS carries no
score/upvote data; posts in `top/day` are already ranked by upvotes so
selection is implicit. Comment count is extracted from the `summary` HTML
field and stored as `num_comments` — a distinct engagement signal (discussion
depth vs passive scroll) not captured by the feed ordering alone.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import html as _html

import feedparser
import httpx
import yaml

from content_intel.sources.base import RawSignal, SourceAdapter

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}
_TIMEOUT = 20.0
# www first, old.reddit as fallback if the primary host blocks/empties.
_HOSTS = ["https://www.reddit.com", "https://old.reddit.com"]
# Reddit rate-limits unauthenticated requests aggressively (HTTP 429). Space
# requests out to stay polite and avoid getting feeds dropped.
_DELAY_SEC = 2.0


_COMMENTS_RE = re.compile(r"(\d+)\s+comment", re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>|<!--.*?-->", re.DOTALL)


def _parse_num_comments(entry: Any) -> int | None:
    """Extract comment count from the summary HTML Reddit embeds in RSS entries."""
    summary: str = entry.get("summary", "") or ""
    m = _COMMENTS_RE.search(summary)
    return int(m.group(1)) if m else None


def _parse_description(entry: Any) -> str | None:
    """Strip HTML from the RSS summary and return plain text, capped at 500 chars."""
    summary: str = entry.get("summary", "") or ""
    text = _HTML_TAG_RE.sub(" ", summary)
    text = _html.unescape(text)
    text = " ".join(text.split())
    return text[:500] if text else None


def _load_subs() -> list[str]:
    root = Path(__file__).resolve().parent.parent.parent.parent
    cfg_file = root / "config" / "reddit_subs.yml"
    with cfg_file.open(encoding="utf-8") as f:
        data: dict[str, Any] = yaml.safe_load(f)
    return [str(s) for s in data.get("subreddits", [])]


def _fetch_feed(client: httpx.Client, sub: str, path: str) -> list[Any]:
    """Fetch one subreddit RSS feed; try www, then old.reddit as fallback."""
    for host in _HOSTS:
        url = f"{host}/r/{sub}/{path}"
        try:
            time.sleep(_DELAY_SEC)
            resp = client.get(url)
            resp.raise_for_status()
            parsed = feedparser.parse(resp.content)
            entries = list(parsed.entries)
            if entries:
                return entries
        except httpx.HTTPStatusError as exc:
            logger.warning("[reddit] HTTP %s for %s", exc.response.status_code, url)
        except Exception:
            logger.warning("[reddit] failed feed %s", url, exc_info=True)
    return []


class RedditAdapter(SourceAdapter):
    name = "reddit"

    def fetch(self) -> list[RawSignal]:
        subs = _load_subs()
        seen: set[str] = set()
        signals: list[RawSignal] = []

        with httpx.Client(
            timeout=_TIMEOUT, headers=_HEADERS, follow_redirects=True
        ) as client:
            for sub in subs:
                entries = _fetch_feed(client, sub, "top/.rss?t=day")
                entries += _fetch_feed(client, sub, "rising/.rss")

                for entry in entries:
                    sid = str(entry.get("id") or entry.get("link") or "")
                    if not sid or sid in seen:
                        continue
                    seen.add(sid)

                    posted_at = datetime.now(UTC)
                    tp = entry.get("published_parsed") or entry.get("updated_parsed")
                    if tp:
                        posted_at = datetime(
                            tp[0], tp[1], tp[2], tp[3], tp[4], tp[5], tzinfo=UTC
                        )

                    num_comments = _parse_num_comments(entry)
                    signals.append(
                        RawSignal(
                            source=f"reddit:{sub}",
                            source_id=sid,
                            title=str(entry.get("title", "")),
                            url=str(entry.get("link", "")) or None,
                            description=_parse_description(entry),
                            posted_at=posted_at,
                            raw_metrics=(
                                {"num_comments": num_comments}
                                if num_comments is not None
                                else {}
                            ),
                            language=None,
                        )
                    )

        logger.info("[reddit] fetched %d signals via RSS", len(signals))
        return signals
