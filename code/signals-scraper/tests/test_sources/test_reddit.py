"""Tests for the Reddit adapter (RSS-based, no API/app)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from content_intel.sources.reddit import RedditAdapter

_ATOM_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Claude 4.7 release discussion</title>
    <link href="https://www.reddit.com/r/LocalLLaMA/comments/abc123/x/"/>
    <id>t3_abc123</id>
    <published>2026-05-13T08:00:00+00:00</published>
  </entry>
</feed>
"""


def _ok_response() -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.content = _ATOM_FEED
    return resp


def test_reddit_fetch_parses_rss_and_dedupes() -> None:
    """Same id from top + rising (and across subs) appears once; no upvote metrics."""
    with (
        patch("httpx.Client.get", return_value=_ok_response()),
        patch("content_intel.sources.reddit.time.sleep"),
    ):
        signals = RedditAdapter().fetch()

    assert len(signals) == 1  # global dedup by id across all subs/feeds
    sig = signals[0]
    assert sig.source_id == "t3_abc123"
    assert sig.source.startswith("reddit:")
    assert sig.title == "Claude 4.7 release discussion"
    assert sig.language is None
    assert sig.raw_metrics == {}  # RSS has no score/upvotes (presence signal)


def test_reddit_all_feeds_fail_returns_empty() -> None:
    """If every feed request fails on both hosts, fetch returns no signals."""
    resp = MagicMock()
    resp.raise_for_status.side_effect = Exception("503")

    with (
        patch("httpx.Client.get", return_value=resp),
        patch("content_intel.sources.reddit.time.sleep"),
    ):
        signals = RedditAdapter().fetch()

    assert signals == []
