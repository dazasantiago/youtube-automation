"""VCR tests for GitHub Trending adapter."""

from __future__ import annotations

from pathlib import Path

import vcr  # type: ignore[import-untyped]

from content_intel.sources.github_trending import GitHubTrendingAdapter

CASSETTES = str(Path(__file__).parent.parent / "fixtures" / "cassettes")


def test_github_trending_fetch_returns_signals() -> None:
    with vcr.VCR().use_cassette(
        f"{CASSETTES}/github_trending_fetch.yaml",
        record_mode="none",
        match_on=["method", "scheme", "host", "path", "query"],
    ):
        adapter = GitHubTrendingAdapter()
        signals = adapter.fetch()
    assert len(signals) >= 1
    assert all(s.source == "github_trending" for s in signals)
    assert all(s.language == "en" for s in signals)


def test_github_trending_signals_are_ai_related() -> None:
    with vcr.VCR().use_cassette(
        f"{CASSETTES}/github_trending_fetch.yaml",
        record_mode="none",
        match_on=["method", "scheme", "host", "path", "query"],
    ):
        adapter = GitHubTrendingAdapter()
        signals = adapter.fetch()
    ai_keywords = ["llm", "ai", "agent", "mcp", "rag", "gpt", "claude",
                   "openai", "anthropic", "ml", "neural"]
    for sig in signals:
        desc = (sig.description or "").lower()
        assert any(kw in desc for kw in ai_keywords), (
            f"Signal {sig.source_id!r} description not AI-related: {sig.description!r}"
        )


def test_github_trending_captures_star_velocity() -> None:
    with vcr.VCR().use_cassette(
        f"{CASSETTES}/github_trending_fetch.yaml",
        record_mode="none",
        match_on=["method", "scheme", "host", "path", "query"],
    ):
        adapter = GitHubTrendingAdapter()
        signals = adapter.fetch()
    assert any(s.raw_metrics.get("stars_today", 0) > 0 for s in signals)


def test_github_trending_source_id_format() -> None:
    with vcr.VCR().use_cassette(
        f"{CASSETTES}/github_trending_fetch.yaml",
        record_mode="none",
        match_on=["method", "scheme", "host", "path", "query"],
    ):
        adapter = GitHubTrendingAdapter()
        signals = adapter.fetch()
    for sig in signals:
        assert "/" in sig.source_id, f"source_id should be owner/repo, got {sig.source_id!r}"
        assert sig.url is not None
        assert sig.url.startswith("https://github.com/")
