"""Tests for Google Trends adapter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd

from content_intel.sources.google_trends import GoogleTrendsAdapter


def test_gtrends_returns_empty_on_exception() -> None:
    with patch("content_intel.sources.google_trends.TrendReq") as mock_pytrends:
        mock_instance = MagicMock()
        mock_pytrends.return_value = mock_instance
        mock_instance.build_payload.side_effect = Exception("Rate limited")
        adapter = GoogleTrendsAdapter()
        signals = adapter.fetch()
    assert isinstance(signals, list)


def test_gtrends_parses_rising_queries() -> None:
    rising_df = pd.DataFrame({"query": ["claude agent tutorial", "llm fine tuning"], "value": [5000, 3200]})
    fake_related = {"LLM": {"rising": rising_df, "top": None}}

    with patch("content_intel.sources.google_trends.TrendReq") as mock_pytrends:
        mock_instance = MagicMock()
        mock_pytrends.return_value = mock_instance
        mock_instance.related_queries.return_value = fake_related
        adapter = GoogleTrendsAdapter()
        signals = adapter.fetch()

    gtrends_signals = [s for s in signals if s.source == "gtrends"]
    assert len(gtrends_signals) >= 1
    assert all(s.language == "en" for s in gtrends_signals)
    assert all("geo" in s.raw_metrics for s in gtrends_signals)


def test_gtrends_handles_breakout_value() -> None:
    rising_df = pd.DataFrame({"query": ["mcp server tool"], "value": ["Breakout"]})
    fake_related = {"MCP": {"rising": rising_df, "top": None}}

    with patch("content_intel.sources.google_trends.TrendReq") as mock_pytrends:
        mock_instance = MagicMock()
        mock_pytrends.return_value = mock_instance
        mock_instance.related_queries.return_value = fake_related
        adapter = GoogleTrendsAdapter()
        signals = adapter.fetch()

    gtrends_signals = [s for s in signals if s.source == "gtrends"]
    assert len(gtrends_signals) >= 1
    sig = gtrends_signals[0]
    assert sig.raw_metrics["is_breakout"] is True
    assert sig.raw_metrics["value"] == 9999
    assert "breakout" in sig.title
