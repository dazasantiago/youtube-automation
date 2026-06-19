"""VCR tests for Product Hunt adapter."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import vcr  # type: ignore[import-untyped]

from content_intel.sources.product_hunt import ProductHuntAdapter

CASSETTES = str(Path(__file__).parent.parent / "fixtures" / "cassettes")


def test_product_hunt_no_token_returns_empty() -> None:
    with patch.dict("os.environ", {}, clear=True):
        adapter = ProductHuntAdapter()
        signals = adapter.fetch()
    assert signals == []


def test_product_hunt_fetch_returns_signals() -> None:
    with (
        patch.dict("os.environ", {"PRODUCT_HUNT_TOKEN": "fake_test_token"}),
        vcr.VCR().use_cassette(
            f"{CASSETTES}/product_hunt_fetch.yaml",
            record_mode="none",
            match_on=["method", "scheme", "host", "path"],
        ),
    ):
        adapter = ProductHuntAdapter()
        signals = adapter.fetch()
    assert len(signals) >= 1
    assert all(s.source == "product_hunt" for s in signals)


def test_product_hunt_signals_have_required_fields() -> None:
    with (
        patch.dict("os.environ", {"PRODUCT_HUNT_TOKEN": "fake_test_token"}),
        vcr.VCR().use_cassette(
            f"{CASSETTES}/product_hunt_fetch.yaml",
            record_mode="none",
            match_on=["method", "scheme", "host", "path"],
        ),
    ):
        adapter = ProductHuntAdapter()
        signals = adapter.fetch()
    for sig in signals:
        assert sig.source_id, "source_id must be non-empty"
        assert sig.title, "title must be non-empty"
        assert "votes" in sig.raw_metrics
        assert "comments" in sig.raw_metrics
        assert "topic" in sig.raw_metrics


def test_product_hunt_deduplicates_across_topics() -> None:
    with (
        patch.dict("os.environ", {"PRODUCT_HUNT_TOKEN": "fake_test_token"}),
        vcr.VCR().use_cassette(
            f"{CASSETTES}/product_hunt_fetch.yaml",
            record_mode="none",
            match_on=["method", "scheme", "host", "path"],
        ),
    ):
        adapter = ProductHuntAdapter()
        signals = adapter.fetch()
    # ph_001 appears in artificial-intelligence and open-source — must appear only once
    ids = [s.source_id for s in signals]
    assert len(ids) == len(set(ids)), "duplicate source_ids found"
    assert len(signals) == 4  # ph_001, ph_002, ph_003, ph_004
