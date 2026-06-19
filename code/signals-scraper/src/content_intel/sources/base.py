"""Base class for all source adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RawSignal:
    source: str
    source_id: str
    title: str
    url: str | None
    description: str | None
    posted_at: datetime
    raw_metrics: dict[str, object] = field(default_factory=dict)
    language: str | None = None  # 'en', 'es', or None


class SourceAdapter(ABC):
    name: str

    @abstractmethod
    def fetch(self) -> list[RawSignal]: ...
