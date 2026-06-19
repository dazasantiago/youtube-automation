from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from deep_research.enrichers.hn import HNEnricher
from deep_research.models import Signal


def _make_signal(url: str | None = "https://example.com/article") -> Signal:
    return Signal(
        source="hn",
        source_id="hn-12345",
        title="Interesting AI article",
        url=url,
        description="Short desc",
        posted_at=None,
        language="en",
        metrics={"points": 200},
    )


def test_can_enrich_hn() -> None:
    enricher = HNEnricher()
    assert enricher.can_enrich(_make_signal())


def test_skips_no_url() -> None:
    enricher = HNEnricher()
    result = enricher.enrich(_make_signal(url=None), MagicMock(spec=httpx.Client))
    assert result.fetch_status == "skipped"
    assert result.fetch_error == "no url"


def test_skips_on_none_fetch() -> None:
    enricher = HNEnricher()
    with patch("deep_research.enrichers.hn.trafilatura") as mock_t:
        mock_t.fetch_url.return_value = None
        result = enricher.enrich(_make_signal(), MagicMock(spec=httpx.Client))
    assert result.fetch_status == "skipped"


def test_enrich_success() -> None:
    enricher = HNEnricher()
    fake_html = "<html>...</html>"
    fake_text = "Full article content here. " * 50

    mock_meta = MagicMock()
    mock_meta.author = "Jane Doe"
    mock_meta.sitename = "Example"
    mock_meta.date = "2026-06-17"

    with patch("deep_research.enrichers.hn.trafilatura") as mock_t:
        mock_t.fetch_url.return_value = fake_html
        mock_t.extract.return_value = fake_text
        mock_t.extract_metadata.return_value = mock_meta
        result = enricher.enrich(_make_signal(), MagicMock(spec=httpx.Client))

    assert result.fetch_status == "ok"
    assert result.full_text is not None
    assert result.metadata["author"] == "Jane Doe"
    assert result.metadata["date"] == "2026-06-17"
