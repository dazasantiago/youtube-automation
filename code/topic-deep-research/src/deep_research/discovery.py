from __future__ import annotations

import os
from datetime import UTC, datetime
from urllib.parse import urlparse


def discover_sources(topic: str, n: int = 10) -> list[object]:
    """Search Tavily for additional sources on the topic."""
    from deep_research.models import DiscoveredSource

    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        return []

    scraped_at = datetime.now(UTC).isoformat()

    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=api_key)
        response = client.search(
            query=topic,
            search_depth="advanced",
            max_results=n,
        )
        results = response.get("results", [])
        sources: list[DiscoveredSource] = []
        for r in results:
            url: str = r.get("url", "")
            domain = urlparse(url).netloc
            sources.append(
                DiscoveredSource(
                    url=url,
                    domain=domain,
                    title=r.get("title", ""),
                    content=r.get("content", ""),
                    published_date=r.get("published_date"),
                    search_query=topic,
                    scraped_at=scraped_at,
                )
            )
        return sources  # type: ignore[return-value]
    except Exception:
        return []
