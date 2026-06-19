from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

SignalRole = Literal["signal", "validator", "saturator"]


@dataclass
class Signal:
    source: str
    source_id: str
    title: str
    url: str | None
    description: str | None
    posted_at: str | None
    language: str | None
    metrics: dict[str, object]
    signal_type: Literal["signal", "yt_video"] = "signal"
    roles: list[SignalRole] = field(default_factory=lambda: ["signal"])


@dataclass
class TopicInput:
    topic: str
    generated_at: str
    signals: list[Signal]


@dataclass
class EnrichedSignal:
    original: Signal
    full_text: str | None
    metadata: dict[str, object]
    scraped_at: str
    fetch_status: Literal["ok", "skipped", "error"]
    fetch_error: str | None


@dataclass
class DiscoveredSource:
    url: str
    domain: str
    title: str
    content: str
    published_date: str | None
    search_query: str
    scraped_at: str


@dataclass
class TopicResult:
    topic_input: TopicInput
    enriched_signals: list[EnrichedSignal]
    discovered_sources: list[DiscoveredSource]
    week_label: str
    generated_at: str
    signals_attempted: int = 0
