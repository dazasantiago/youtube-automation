"""Tests for X/Apify adapter."""

from __future__ import annotations

from unittest.mock import patch

from content_intel.sources.x_apify import XApifyAdapter


def test_x_apify_no_token_returns_empty() -> None:
    with patch.dict("os.environ", {}, clear=True):
        adapter = XApifyAdapter()
        signals = adapter.fetch()
    assert signals == []


def test_x_apify_empty_accounts_returns_empty() -> None:
    with (
        patch.dict("os.environ", {"APIFY_TOKEN": "fake_token"}),
        patch("content_intel.sources.x_apify.XApifyAdapter._load_accounts", return_value=[]),
    ):
        adapter = XApifyAdapter()
        signals = adapter.fetch()
    assert signals == []


def test_x_apify_parses_tweet_response() -> None:
    fake_tweets = [
        {
            "id": "tweet_001",
            "text": "Claude 4.7 is incredible for agent workflows #AI",
            "url": "https://x.com/user/status/tweet_001",
            "createdAt": "2026-05-13T10:00:00.000Z",
            "likeCount": 250,
            "retweetCount": 45,
        }
    ]
    with (
        patch.dict("os.environ", {"APIFY_TOKEN": "fake_token"}),
        patch("content_intel.sources.x_apify.XApifyAdapter._load_accounts", return_value=["testuser"]),
        patch("httpx.post") as mock_post,
        patch("content_intel.db.log_quota"),
    ):
        mock_resp = mock_post.return_value
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = fake_tweets
        adapter = XApifyAdapter()
        signals = adapter.fetch()
    assert len(signals) == 1
    assert signals[0].source == "x_apify"
    assert signals[0].source_id == "tweet_001"
    assert signals[0].language == "en"
