from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx

from deep_research.discovery import discover_sources
from deep_research.enrichers import HNEnricher, RedditEnricher, YouTubeEnricher
from deep_research.enrichers.base import Enricher
from deep_research.models import DiscoveredSource, EnrichedSignal, Signal, TopicInput, TopicResult
from deep_research.writer import write_topic_result


def run(
    topic_input: TopicInput,
    *,
    top_signals: int = 20,
    top_comments: int = 10,
    out_dir: Path = Path("results"),
    force_youtube: bool = False,
) -> tuple[Path, TopicResult]:
    enrichers: list[Enricher] = [
        YouTubeEnricher(force=force_youtube),
        RedditEnricher(top_comments=top_comments),
        HNEnricher(),
    ]

    with httpx.Client(follow_redirects=True) as http:
        enriched = _enrich_signals(
            topic_input.signals[:top_signals],
            enrichers=enrichers,
            http=http,
        )
        discovered: list[DiscoveredSource] = discover_sources(topic_input.topic)  # type: ignore[assignment]

    usable = [s for s in enriched if s.full_text]

    week_label = _week_label()
    result = TopicResult(
        topic_input=topic_input,
        enriched_signals=usable,
        discovered_sources=discovered,
        week_label=week_label,
        generated_at=datetime.now(UTC).isoformat(),
        signals_attempted=len(enriched),
    )

    out_path = write_topic_result(result, base=out_dir)
    return out_path, result


def run_topic(
    topic: str,
    *,
    top_signals: int = 20,
    top_comments: int = 10,
    per_source: int = 8,
    out_dir: Path = Path("results"),
) -> tuple[Path, TopicResult]:
    """Discover signals for `topic` from scratch (HN, Reddit, YouTube) then enrich them."""
    from deep_research.topic_discovery import discover_topic_signals

    with httpx.Client(follow_redirects=True) as http:
        signals = discover_topic_signals(topic, http, per_source=per_source)

    topic_input = TopicInput(
        topic=topic,
        generated_at=datetime.now(UTC).isoformat(),
        signals=signals,
    )
    return run(
        topic_input,
        top_signals=top_signals,
        top_comments=top_comments,
        out_dir=out_dir,
        force_youtube=True,
    )


def _enrich_signals(
    signals: list[Signal],
    enrichers: list[Enricher],
    http: httpx.Client,
) -> list[EnrichedSignal]:
    results: list[EnrichedSignal] = []
    for signal in signals:
        enricher = _pick_enricher(signal, enrichers)
        if enricher is None:
            results.append(_skipped(signal, "no enricher matched"))
            continue
        try:
            results.append(enricher.enrich(signal, http))
        except Exception as exc:
            results.append(_errored(signal, str(exc)))
    return results


def _pick_enricher(signal: Signal, enrichers: list[Enricher]) -> Enricher | None:
    for enricher in enrichers:
        if enricher.can_enrich(signal):
            return enricher
    return None


def _skipped(signal: Signal, reason: str) -> EnrichedSignal:
    from datetime import UTC, datetime

    return EnrichedSignal(
        original=signal,
        full_text=None,
        metadata={},
        scraped_at=datetime.now(UTC).isoformat(),
        fetch_status="skipped",
        fetch_error=reason,
    )


def _errored(signal: Signal, reason: str) -> EnrichedSignal:
    from datetime import UTC, datetime

    return EnrichedSignal(
        original=signal,
        full_text=None,
        metadata={},
        scraped_at=datetime.now(UTC).isoformat(),
        fetch_status="error",
        fetch_error=reason,
    )


def _week_label() -> str:
    iso = datetime.now(UTC).isocalendar()
    return f"{iso.year}-W{iso.week:02d}"
