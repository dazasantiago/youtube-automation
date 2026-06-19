from __future__ import annotations

from abc import ABC, abstractmethod

import httpx

from deep_research.models import EnrichedSignal, Signal


class Enricher(ABC):
    @abstractmethod
    def can_enrich(self, signal: Signal) -> bool: ...

    @abstractmethod
    def enrich(self, signal: Signal, client: httpx.Client) -> EnrichedSignal: ...
