"""VCR tests for RSS adapter."""

from __future__ import annotations

from pathlib import Path

import vcr  # type: ignore[import-untyped]

from content_intel.sources.rss import RssAdapter

CASSETTES = str(Path(__file__).parent.parent / "fixtures" / "cassettes")


def test_rss_fetch_returns_signals() -> None:
    with vcr.VCR().use_cassette(
        f"{CASSETTES}/rss_fetch.yaml",
        record_mode="none",
        match_on=["method", "scheme", "host", "path"],
    ):
        adapter = RssAdapter()
        signals = adapter.fetch()
    assert len(signals) >= 1
    assert all(s.source == "rss" for s in signals)
    assert all(s.language == "en" for s in signals)


def test_rss_signals_have_required_fields() -> None:
    with vcr.VCR().use_cassette(
        f"{CASSETTES}/rss_fetch.yaml",
        record_mode="none",
        match_on=["method", "scheme", "host", "path"],
    ):
        adapter = RssAdapter()
        signals = adapter.fetch()
    for sig in signals:
        assert sig.source_id, "source_id must be non-empty"
        assert sig.title, "title must be non-empty"
        assert sig.posted_at is not None


def test_rss_strips_html_from_description() -> None:
    with vcr.VCR().use_cassette(
        f"{CASSETTES}/rss_fetch.yaml",
        record_mode="none",
        match_on=["method", "scheme", "host", "path"],
    ):
        adapter = RssAdapter()
        signals = adapter.fetch()
    for sig in signals:
        if sig.description:
            assert "<" not in sig.description, "HTML tags found in description"
