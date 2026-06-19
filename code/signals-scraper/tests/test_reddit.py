"""Tests for the Reddit source adapter."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from content_intel.sources.reddit import RedditAdapter, _parse_description, _parse_num_comments

# ── _parse_num_comments ──────────────────────────────────────────────────────


def test_parse_num_comments_plural() -> None:
    assert _parse_num_comments({"summary": '<a href="#">342 comments</a>'}) == 342


def test_parse_num_comments_singular() -> None:
    assert _parse_num_comments({"summary": '<a href="#">1 comment</a>'}) == 1


def test_parse_num_comments_no_match() -> None:
    assert _parse_num_comments({"summary": "submitted by /u/user"}) is None


def test_parse_num_comments_no_summary() -> None:
    assert _parse_num_comments({}) is None


# ── _parse_description ───────────────────────────────────────────────────────


def test_parse_description_strips_html() -> None:
    entry = {"summary": "<p>Post content</p> submitted by <a href='#'>user</a>"}
    result = _parse_description(entry)
    assert result is not None
    assert "<" not in result
    assert "Post content" in result


def test_parse_description_unescapes_entities() -> None:
    entry = {"summary": "&lt;code&gt;hello &amp; world&lt;/code&gt;"}
    result = _parse_description(entry)
    assert result == "<code>hello & world</code>"


def test_parse_description_empty_summary() -> None:
    assert _parse_description({}) is None
    assert _parse_description({"summary": ""}) is None


def test_parse_description_truncates_at_500() -> None:
    entry = {"summary": "a" * 600}
    result = _parse_description(entry)
    assert result is not None
    assert len(result) == 500


# ── Fake RSS feed fixtures ───────────────────────────────────────────────────

_TOP_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>https://www.reddit.com/r/LocalLLaMA/comments/abc123/fake_post/</id>
    <link href="https://example.com/article"/>
    <title>Fake LLM Post</title>
    <published>2026-06-18T10:00:00+00:00</published>
    <updated>2026-06-18T10:00:00+00:00</updated>
    <summary type="html">&lt;p&gt;Body text&lt;/p&gt; submitted by user &lt;a href="#"&gt;342 comments&lt;/a&gt;</summary>
  </entry>
</feed>"""

_RISING_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>https://www.reddit.com/r/LocalLLaMA/comments/def456/rising_post/</id>
    <link href="https://example.com/rising"/>
    <title>Rising Post</title>
    <published>2026-06-18T13:00:00+00:00</published>
    <updated>2026-06-18T13:00:00+00:00</updated>
    <summary type="html">submitted by user &lt;a href="#"&gt;5 comments&lt;/a&gt;</summary>
  </entry>
</feed>"""


def _fake_response(content: bytes) -> MagicMock:
    resp = MagicMock()
    resp.content = content
    resp.raise_for_status.return_value = None
    return resp


def _make_client(url_map: dict[str, bytes]) -> MagicMock:
    def fake_get(url: str, **_: object) -> MagicMock:
        for key, body in url_map.items():
            if key in url:
                return _fake_response(body)
        return _fake_response(b"<feed/>")

    client = MagicMock()
    client.__enter__ = lambda s: s
    client.__exit__ = MagicMock(return_value=False)
    client.get.side_effect = fake_get
    return client


# ── RedditAdapter integration tests ─────────────────────────────────────────


def test_adapter_returns_signals(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("content_intel.sources.reddit._load_subs", lambda: ["LocalLLaMA"])
    client = _make_client({"top/.rss": _TOP_FEED, "rising/.rss": _RISING_FEED})

    with patch("content_intel.sources.reddit.httpx.Client", return_value=client):
        with patch("content_intel.sources.reddit.time.sleep"):
            signals = RedditAdapter().fetch()

    assert len(signals) == 2


def test_adapter_num_comments_in_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("content_intel.sources.reddit._load_subs", lambda: ["LocalLLaMA"])
    client = _make_client({"top/.rss": _TOP_FEED, "rising/.rss": b"<feed/>"})

    with patch("content_intel.sources.reddit.httpx.Client", return_value=client):
        with patch("content_intel.sources.reddit.time.sleep"):
            signals = RedditAdapter().fetch()

    assert len(signals) == 1
    assert signals[0].raw_metrics.get("num_comments") == 342


def test_adapter_description_populated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("content_intel.sources.reddit._load_subs", lambda: ["LocalLLaMA"])
    client = _make_client({"top/.rss": _TOP_FEED, "rising/.rss": b"<feed/>"})

    with patch("content_intel.sources.reddit.httpx.Client", return_value=client):
        with patch("content_intel.sources.reddit.time.sleep"):
            signals = RedditAdapter().fetch()

    assert signals[0].description is not None
    assert "<" not in signals[0].description


def test_adapter_dedup_across_feeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same post appearing in top and rising is stored only once."""
    monkeypatch.setattr("content_intel.sources.reddit._load_subs", lambda: ["LocalLLaMA"])
    client = _make_client({"top/.rss": _TOP_FEED, "rising/.rss": _TOP_FEED})

    with patch("content_intel.sources.reddit.httpx.Client", return_value=client):
        with patch("content_intel.sources.reddit.time.sleep"):
            signals = RedditAdapter().fetch()

    assert len(signals) == 1


def test_adapter_source_includes_subreddit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("content_intel.sources.reddit._load_subs", lambda: ["LocalLLaMA"])
    client = _make_client({"top/.rss": _TOP_FEED, "rising/.rss": b"<feed/>"})

    with patch("content_intel.sources.reddit.httpx.Client", return_value=client):
        with patch("content_intel.sources.reddit.time.sleep"):
            signals = RedditAdapter().fetch()

    assert signals[0].source == "reddit:LocalLLaMA"


def test_adapter_failed_feed_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """A feed that raises HTTP 429 for both hosts yields no signals (no crash)."""
    import httpx

    monkeypatch.setattr("content_intel.sources.reddit._load_subs", lambda: ["LocalLLaMA"])

    client = MagicMock()
    client.__enter__ = lambda s: s
    client.__exit__ = MagicMock(return_value=False)
    client.get.side_effect = httpx.TimeoutException("timeout")

    with patch("content_intel.sources.reddit.httpx.Client", return_value=client):
        with patch("content_intel.sources.reddit.time.sleep"):
            signals = RedditAdapter().fetch()

    assert signals == []
