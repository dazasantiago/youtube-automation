"""VCR tests for HuggingFace adapter."""

from __future__ import annotations

from pathlib import Path

import vcr  # type: ignore[import-untyped]

from content_intel.sources.huggingface import HuggingFaceAdapter

CASSETTES = str(Path(__file__).parent.parent / "fixtures" / "cassettes")


def test_hf_fetch_returns_signals() -> None:
    with vcr.VCR().use_cassette(
        f"{CASSETTES}/hf_fetch.yaml",
        record_mode="none",
        match_on=["method", "scheme", "host", "path", "query"],
    ):
        adapter = HuggingFaceAdapter()
        signals = adapter.fetch()
    assert len(signals) >= 1
    assert all(s.source == "hf" for s in signals)
    assert all(s.language == "en" for s in signals)


def test_hf_signals_have_model_and_space() -> None:
    with vcr.VCR().use_cassette(
        f"{CASSETTES}/hf_fetch.yaml",
        record_mode="none",
        match_on=["method", "scheme", "host", "path", "query"],
    ):
        adapter = HuggingFaceAdapter()
        signals = adapter.fetch()
    source_ids = [s.source_id for s in signals]
    assert any(sid.startswith("model:") for sid in source_ids)
    assert any(sid.startswith("space:") for sid in source_ids)


def test_hf_signals_have_required_fields() -> None:
    with vcr.VCR().use_cassette(
        f"{CASSETTES}/hf_fetch.yaml",
        record_mode="none",
        match_on=["method", "scheme", "host", "path", "query"],
    ):
        adapter = HuggingFaceAdapter()
        signals = adapter.fetch()
    for sig in signals:
        assert sig.source_id, "source_id must be non-empty"
        assert sig.title, "title must be non-empty"
        assert sig.url is not None
