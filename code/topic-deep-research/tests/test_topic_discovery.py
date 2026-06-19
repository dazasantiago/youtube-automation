from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from deep_research.models import Signal
from deep_research.topic_discovery import (
    _interleave,
    discover_hn_signals,
    discover_topic_signals,
    discover_youtube_signals,
)


def _mock_http_get(json_body: dict[str, Any]) -> httpx.Client:
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = json_body
    resp.raise_for_status.return_value = None
    client = MagicMock(spec=httpx.Client)
    client.get.return_value = resp
    return client


# ── HN ────────────────────────────────────────────────────────────────────────

def test_discover_hn_signals_parses_hits() -> None:
    payload = {
        "hits": [
            {
                "objectID": "12345",
                "title": "GLM 5.2 is out",
                "url": "https://example.com/glm",
                "created_at": "2026-06-01T00:00:00.000Z",
                "points": 300,
                "num_comments": 45,
            }
        ]
    }
    signals = discover_hn_signals("GLM 5.2", _mock_http_get(payload))
    assert len(signals) == 1
    s = signals[0]
    assert s.source == "hn"
    assert s.source_id == "12345"
    assert s.signal_type == "signal"
    assert s.url == "https://example.com/glm"
    assert s.metrics["points"] == 300


def test_discover_hn_signals_fallback_url_when_no_url_field() -> None:
    payload = {
        "hits": [{"objectID": "99", "title": "Ask HN: ...", "points": 10, "num_comments": 5}]
    }
    signals = discover_hn_signals("topic", _mock_http_get(payload))
    assert signals[0].url == "https://news.ycombinator.com/item?id=99"


def test_discover_hn_signals_failure_returns_empty() -> None:
    client = MagicMock(spec=httpx.Client)
    client.get.side_effect = Exception("network error")
    assert discover_hn_signals("topic", client) == []


# ── YouTube ───────────────────────────────────────────────────────────────────

def test_discover_youtube_requires_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    client = MagicMock(spec=httpx.Client)
    assert discover_youtube_signals("GLM 5.2", client) == []
    client.get.assert_not_called()


def test_discover_youtube_signals_parses_items(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YOUTUBE_API_KEY", "fake-key")
    payload = {
        "items": [
            {
                "id": {"videoId": "vid123ABC"},
                "snippet": {
                    "title": "GLM 5.2 demo",
                    "description": "A demo of GLM 5.2",
                    "publishedAt": "2026-06-01T12:00:00Z",
                },
            }
        ]
    }
    signals = discover_youtube_signals("GLM 5.2", _mock_http_get(payload))
    assert len(signals) == 1
    s = signals[0]
    assert s.signal_type == "yt_video"
    assert s.source_id == "vid123ABC"
    assert s.url == "https://www.youtube.com/watch?v=vid123ABC"
    assert s.metrics == {}


def test_discover_youtube_skips_items_without_video_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YOUTUBE_API_KEY", "fake-key")
    payload = {"items": [{"id": {}, "snippet": {"title": "no id"}}]}
    signals = discover_youtube_signals("topic", _mock_http_get(payload))
    assert signals == []


def test_discover_youtube_failure_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YOUTUBE_API_KEY", "fake-key")
    client = MagicMock(spec=httpx.Client)
    client.get.side_effect = Exception("API error")
    assert discover_youtube_signals("topic", client) == []


# ── discover_topic_signals (interleave) ───────────────────────────────────────

def test_discover_topic_signals_interleaves_hn_and_youtube(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("YOUTUBE_API_KEY", "fake-key")

    hn_payload = {
        "hits": [{"objectID": "h1", "title": "HN post", "points": 10, "num_comments": 0}]
    }
    yt_payload = {
        "items": [
            {
                "id": {"videoId": "yt1"},
                "snippet": {"title": "YT video", "publishedAt": "2026-01-01"},
            }
        ]
    }

    client = MagicMock(spec=httpx.Client)
    client.get.side_effect = [_make_response(hn_payload), _make_response(yt_payload)]

    signals = discover_topic_signals("topic", client, per_source=1)
    sources = [s.source for s in signals]
    assert "hn" in sources
    assert "youtube" in sources


# ── Helpers ───────────────────────────────────────────────────────────────────

def test_interleave_round_robin() -> None:
    def _sig(source: str) -> Signal:
        return Signal(
            source=source, source_id="x", title="t", url=None,
            description=None, posted_at=None, language=None, metrics={},
        )

    a = [_sig("a1"), _sig("a2")]
    b = [_sig("b1")]
    c = [_sig("c1"), _sig("c2"), _sig("c3")]

    result = _interleave(a, b, c)
    sources = [s.source for s in result]
    assert sources == ["a1", "b1", "c1", "a2", "c2", "c3"]


def _make_response(payload: dict[str, Any]) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp
