from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from deep_research.enrichers.reddit import RedditEnricher, _is_post_url, _to_json_url
from deep_research.models import Signal


def _make_signal(url: str = "https://www.reddit.com/r/LocalLLaMA/comments/abc123/some_post/") -> Signal:
    return Signal(
        source="reddit",
        source_id="abc123",
        title="Test reddit post",
        url=url,
        description=None,
        posted_at=None,
        language="en",
        metrics={},
    )


def test_is_post_url_true() -> None:
    assert _is_post_url("https://www.reddit.com/r/LocalLLaMA/comments/abc123/post/")


def test_is_post_url_false_subreddit() -> None:
    assert not _is_post_url("https://www.reddit.com/r/LocalLLaMA/")


def test_to_json_url() -> None:
    url = "https://www.reddit.com/r/LocalLLaMA/comments/abc123/post/"
    result = _to_json_url(url)
    assert result == "https://old.reddit.com/r/LocalLLaMA/comments/abc123/post.json?limit=100"


def test_can_enrich() -> None:
    enricher = RedditEnricher()
    assert enricher.can_enrich(_make_signal())


def test_skips_non_post_url() -> None:
    enricher = RedditEnricher()
    signal = _make_signal(url="https://www.reddit.com/r/LocalLLaMA/")
    result = enricher.enrich(signal, MagicMock(spec=httpx.Client))
    assert result.fetch_status == "skipped"


def test_enrich_success() -> None:
    enricher = RedditEnricher(top_comments=2)
    fake_response = [
        {"data": {"children": [{"data": {"selftext": "Post body here", "created_utc": 1718000000}}]}},
        {
            "data": {
                "children": [
                    {"kind": "t1", "data": {"body": "Top comment", "score": 100, "created_utc": 1718001000}},
                    {"kind": "t1", "data": {"body": "Second comment", "score": 50, "created_utc": 1718002000}},
                ]
            }
        },
    ]

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = fake_response

    mock_client = MagicMock(spec=httpx.Client)
    mock_client.get.return_value = mock_resp

    with patch("deep_research.enrichers.reddit.time.sleep"):
        result = enricher.enrich(_make_signal(), mock_client)

    assert result.fetch_status == "ok"
    assert "Post body here" in (result.full_text or "")
    assert len(result.metadata["comments"]) == 2
