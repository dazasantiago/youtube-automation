"""GitHub Trending source adapter — scrapes trending repos page."""

from __future__ import annotations

import logging
import re
import time
from datetime import UTC, datetime
from typing import Any

import httpx
from bs4 import BeautifulSoup

from content_intel.sources.base import RawSignal, SourceAdapter

logger = logging.getLogger(__name__)

_TRENDING_URLS = [
    "https://github.com/trending?since=daily",
    "https://github.com/trending?since=weekly",
    "https://github.com/trending/python?since=daily",
    "https://github.com/trending/python?since=weekly",
    "https://github.com/trending/typescript?since=daily",
]

_AI_KEYWORDS = [
    "llm", "ai", "agent", "mcp", "rag", "gpt", "claude",
    "openai", "anthropic", "ml", "neural",
    "gemini", "mistral", "agentic", "copilot", "codex",
]

_STARS_RE = re.compile(r"([\d,]+)\s+stars?\s+(today|this week)", re.IGNORECASE)


# Word-boundary match (with optional plural) so short keywords don't
# false-positive inside other words: "ai" must not match "av-ai-lable",
# "ml" must not match "ht-ml", "rag" must not match "sto-rag-e" — while still
# catching plurals like "agents", "skills".
_AI_RE = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in _AI_KEYWORDS) + r")s?\b", re.IGNORECASE
)


def _matches_ai(description: str) -> bool:
    return bool(_AI_RE.search(description))


def _parse_stars_recent(article: Any) -> int:
    """Parse recent-star velocity as an approximate stars-per-DAY figure.

    Trending pages report 'N stars today' (daily pages) or 'N stars this week'
    (weekly pages). Weekly counts are normalized to a daily rate (÷7) so the
    metric is comparable regardless of which page surfaced the repo — otherwise
    weekly totals (thousands) saturate the importance score and erase ranking.
    """
    span = article.find("span", class_="d-inline-block float-sm-right")
    if span is None:
        return 0
    m = _STARS_RE.search(span.get_text(" ", strip=True))
    if not m:
        return 0
    count = int(m.group(1).replace(",", ""))
    period = m.group(2).lower()
    if "week" in period:
        return round(count / 7)
    return count


def _parse_stars_total(article: Any) -> int:
    """Parse total stargazers count. 0 if absent."""
    a = article.find("a", href=lambda h: bool(h) and h.endswith("/stargazers"))
    if a is None:
        return 0
    txt = a.get_text(strip=True).replace(",", "")
    try:
        return int(txt)
    except ValueError:
        return 0


class GitHubTrendingAdapter(SourceAdapter):
    name = "github_trending"

    def fetch(self) -> list[RawSignal]:
        seen: set[str] = set()
        signals: list[RawSignal] = []

        with httpx.Client(
            timeout=30,
            headers={"User-Agent": "Mozilla/5.0 (content-intel-bot/1.0)"},
            follow_redirects=True,
        ) as client:
            for url in _TRENDING_URLS:
                try:
                    time.sleep(1.0)
                    resp = client.get(url)
                    resp.raise_for_status()
                    soup = BeautifulSoup(resp.text, "lxml")
                    articles: Any = soup.find_all("article", class_="Box-row")
                    for article in articles:
                        h2 = article.find("h2")
                        if not h2:
                            continue
                        a_tag = h2.find("a")
                        if not a_tag:
                            continue
                        href = str(a_tag.get("href", "")).strip("/")
                        parts = href.split("/")
                        if len(parts) < 2:
                            continue
                        owner, repo = parts[0], parts[1]
                        source_id = f"{owner}/{repo}"
                        if source_id in seen:
                            continue

                        p_tag = article.find("p")
                        description = p_tag.get_text(strip=True) if p_tag else ""
                        if not _matches_ai(f"{source_id} {description}"):
                            continue

                        seen.add(source_id)
                        stars_today = _parse_stars_recent(article)
                        stars_total = _parse_stars_total(article)
                        signals.append(
                            RawSignal(
                                source="github_trending",
                                source_id=source_id,
                                title=source_id,
                                url=f"https://github.com/{source_id}",
                                description=description or None,
                                posted_at=datetime.now(UTC),
                                raw_metrics={"stars_today": stars_today, "stars_total": stars_total},
                                language="en",
                            )
                        )
                except httpx.HTTPStatusError as exc:
                    logger.warning(
                        "[github_trending] HTTP %s for %s", exc.response.status_code, url
                    )
                except Exception:
                    logger.warning(
                        "[github_trending] failed to scrape url=%r", url, exc_info=True
                    )

        logger.info("[github_trending] fetched %d signals", len(signals))
        return signals
