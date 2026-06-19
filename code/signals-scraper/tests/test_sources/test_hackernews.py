"""VCR tests for HackerNews adapter."""

from __future__ import annotations

from pathlib import Path

import vcr  # type: ignore[import-untyped]

from content_intel.sources.hackernews import HackerNewsAdapter

CASSETTES = str(Path(__file__).parent.parent / "fixtures" / "cassettes")


def test_hn_fetch_returns_signals() -> None:
    with vcr.VCR().use_cassette(
        f"{CASSETTES}/hn_fetch.yaml",
        record_mode="none",
        match_on=["method", "scheme", "host", "path"],
    ):
        adapter = HackerNewsAdapter()
        signals = adapter.fetch()
    assert len(signals) >= 1
    assert all(s.source == "hn" for s in signals)
    assert all(s.language == "en" for s in signals)


def test_hn_signals_have_required_fields() -> None:
    with vcr.VCR().use_cassette(
        f"{CASSETTES}/hn_fetch.yaml",
        record_mode="none",
        match_on=["method", "scheme", "host", "path"],
    ):
        adapter = HackerNewsAdapter()
        signals = adapter.fetch()
    for sig in signals:
        assert sig.source_id, "source_id must be non-empty"
        assert sig.title, "title must be non-empty"
        assert sig.posted_at is not None
        assert "points" in sig.raw_metrics
        assert "num_comments" in sig.raw_metrics
