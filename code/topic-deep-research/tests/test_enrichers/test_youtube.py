from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from deep_research.enrichers.youtube import YouTubeEnricher, _extract_video_id
from deep_research.models import Signal


def _make_signal(url: str = "https://www.youtube.com/watch?v=abc123XYZ00", signal_type: str = "yt_video") -> Signal:
    return Signal(
        source="youtube",
        source_id="abc123XYZ00",
        title="Test video",
        url=url,
        description=None,
        posted_at=None,
        language="en",
        metrics={},
        signal_type=signal_type,  # type: ignore[arg-type]
    )


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ?t=30", "dQw4w9WgXcQ"),
        ("https://example.com/not-youtube", ""),
    ],
)
def test_extract_video_id(url: str, expected: str) -> None:
    assert _extract_video_id(url) == expected


def test_can_enrich_yt_video() -> None:
    enricher = YouTubeEnricher()
    assert enricher.can_enrich(_make_signal(signal_type="yt_video"))


def test_can_enrich_youtube_url() -> None:
    enricher = YouTubeEnricher()
    signal = _make_signal(url="https://www.youtube.com/watch?v=abc", signal_type="signal")
    assert enricher.can_enrich(signal)


def test_enrich_success() -> None:
    enricher = YouTubeEnricher()
    fake_segments = [{"text": "Hello world", "start": 0.0, "duration": 1.0}]
    signal = _make_signal()
    signal.metrics = {"outlier_ratio": 3.5}

    with patch("deep_research.enrichers.youtube.YouTubeTranscriptApi.get_transcript", return_value=fake_segments):
        result = enricher.enrich(signal, MagicMock(spec=httpx.Client))

    assert result.fetch_status == "ok"
    assert result.full_text == "Hello world"
    assert result.metadata["transcript_segment_count"] == 1


def test_enrich_transcripts_disabled() -> None:
    from youtube_transcript_api import TranscriptsDisabled  # type: ignore[import-untyped]

    enricher = YouTubeEnricher()
    with patch(
        "deep_research.enrichers.youtube.YouTubeTranscriptApi.get_transcript",
        side_effect=TranscriptsDisabled("abc123XYZ00"),
    ):
        result = enricher.enrich(_make_signal(), MagicMock(spec=httpx.Client))

    assert result.fetch_status == "skipped"


def test_enrich_no_url_returns_skipped() -> None:
    enricher = YouTubeEnricher()
    signal = Signal(
        source="youtube", source_id="", title="no url", url=None,
        description=None, posted_at=None, language=None, metrics={},
    )
    result = enricher.enrich(signal, MagicMock(spec=httpx.Client))
    assert result.fetch_status == "skipped"


@pytest.mark.parametrize("outlier_ratio", [2.0, 0.5, 0.34, 1.0])
def test_skips_mid_range_outlier_ratio(outlier_ratio: float) -> None:
    enricher = YouTubeEnricher()
    signal = _make_signal()
    signal.metrics = {"outlier_ratio": outlier_ratio}
    result = enricher.enrich(signal, MagicMock(spec=httpx.Client))
    assert result.fetch_status == "skipped"
    assert "outlier_ratio" in (result.fetch_error or "")


@pytest.mark.parametrize("outlier_ratio", [3.0, 5.2, 0.33, 0.1])
def test_enriches_threshold_outlier_ratio(outlier_ratio: float) -> None:
    enricher = YouTubeEnricher()
    signal = _make_signal()
    signal.metrics = {"outlier_ratio": outlier_ratio}
    fake_segments = [{"text": "content", "start": 0.0, "duration": 1.0}]
    with patch("deep_research.enrichers.youtube.YouTubeTranscriptApi.get_transcript", return_value=fake_segments):
        result = enricher.enrich(signal, MagicMock(spec=httpx.Client))
    assert result.fetch_status == "ok"


def test_force_bypasses_outlier_gate() -> None:
    """force=True should always fetch transcript, even when outlier_ratio is in skip range."""
    enricher = YouTubeEnricher(force=True)
    signal = _make_signal()
    signal.metrics = {}  # no outlier_ratio — default 1.0 would normally skip
    fake_segments = [{"text": "forced content", "start": 0.0, "duration": 1.0}]
    with patch(
        "deep_research.enrichers.youtube.YouTubeTranscriptApi.get_transcript",
        return_value=fake_segments,
    ):
        result = enricher.enrich(signal, MagicMock(spec=httpx.Client))
    assert result.fetch_status == "ok"
    assert result.full_text == "forced content"


def test_no_force_still_skips_midrange_regression() -> None:
    """Regression: force=False (default) must still skip mid-range outlier_ratio."""
    enricher = YouTubeEnricher(force=False)
    signal = _make_signal()
    signal.metrics = {"outlier_ratio": 1.0}
    result = enricher.enrich(signal, MagicMock(spec=httpx.Client))
    assert result.fetch_status == "skipped"
