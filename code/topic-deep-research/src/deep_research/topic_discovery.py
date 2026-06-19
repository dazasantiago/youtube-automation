from __future__ import annotations

import os
from typing import Any

import httpx

from deep_research.models import Signal

_HN_ALGOLIA = "https://hn.algolia.com/api/v1/search"
_YT_SEARCH = "https://www.googleapis.com/youtube/v3/search"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; deep-research-bot/1.0)"}


def discover_topic_signals(
    topic: str, http: httpx.Client, per_source: int = 8
) -> list[Signal]:
    """Discover signals about `topic` from HN and YouTube, interleaved.

    Reddit is intentionally excluded: old.reddit.com/search.json blocks bots
    unreliably, and Tavily (run in the same pipeline via discover_sources) already
    surfaces the most relevant Reddit threads as discovered_sources.
    """
    hn = discover_hn_signals(topic, http, per_source)
    yt = discover_youtube_signals(topic, http, per_source)
    return _interleave(hn, yt)


def discover_hn_signals(topic: str, http: httpx.Client, n: int = 8) -> list[Signal]:
    """Search HN via Algolia API (no key required)."""
    try:
        resp = http.get(
            _HN_ALGOLIA,
            params={"query": topic, "tags": "story", "hitsPerPage": n},
            headers=_HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        hits: list[dict[str, Any]] = resp.json().get("hits", [])
        out: list[Signal] = []
        for h in hits:
            oid = str(h.get("objectID", ""))
            url = h.get("url") or f"https://news.ycombinator.com/item?id={oid}"
            out.append(
                Signal(
                    source="hn",
                    source_id=oid,
                    title=h.get("title") or h.get("story_title") or "",
                    url=url,
                    description=None,
                    posted_at=h.get("created_at"),
                    language=None,
                    metrics={
                        "points": h.get("points", 0),
                        "num_comments": h.get("num_comments", 0),
                    },
                    signal_type="signal",
                    roles=["signal"],
                )
            )
        return out
    except Exception:
        return []


def discover_youtube_signals(topic: str, http: httpx.Client, n: int = 8) -> list[Signal]:
    """Search YouTube via Data API v3. Requires YOUTUBE_API_KEY env var; returns [] if absent."""
    api_key = os.environ.get("YOUTUBE_API_KEY", "")
    if not api_key:
        return []
    try:
        resp = http.get(
            _YT_SEARCH,
            params={
                "part": "snippet",
                "q": topic,
                "type": "video",
                "maxResults": n,
                "relevanceLanguage": "en",
                "key": api_key,
            },
            headers=_HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        items: list[dict[str, Any]] = resp.json().get("items", [])
        out: list[Signal] = []
        for it in items:
            vid: str = it.get("id", {}).get("videoId", "")
            sn: dict[str, Any] = it.get("snippet", {})
            if not vid:
                continue
            out.append(
                Signal(
                    source="youtube",
                    source_id=vid,
                    title=sn.get("title", ""),
                    url=f"https://www.youtube.com/watch?v={vid}",
                    description=sn.get("description"),
                    posted_at=sn.get("publishedAt"),
                    language=None,
                    # No outlier_ratio available — enricher runs in force mode
                    metrics={},
                    signal_type="yt_video",
                    roles=["signal"],
                )
            )
        return out
    except Exception:
        return []


def _interleave(*lists: list[Signal]) -> list[Signal]:
    """Round-robin interleave multiple lists so no source dominates the top_signals window."""
    result: list[Signal] = []
    iters = [iter(lst) for lst in lists if lst]
    while iters:
        next_iters: list[Any] = []
        for it in iters:
            try:
                result.append(next(it))
                next_iters.append(it)
            except StopIteration:
                pass
        iters = next_iters
    return result
