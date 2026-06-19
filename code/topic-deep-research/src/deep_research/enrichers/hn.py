from __future__ import annotations

from datetime import UTC, datetime

import httpx
import trafilatura

from deep_research.enrichers.base import Enricher
from deep_research.models import EnrichedSignal, Signal

_MAX_CHARS = 15_000


class HNEnricher(Enricher):
    """Fetches full article text for HN signals (and acts as generic fallback for other sources)."""

    def can_enrich(self, signal: Signal) -> bool:
        return signal.source == "hn" or bool(signal.url)

    def enrich(self, signal: Signal, client: httpx.Client) -> EnrichedSignal:
        scraped_at = datetime.now(UTC).isoformat()
        url = signal.url
        if not url:
            return EnrichedSignal(
                original=signal,
                full_text=None,
                metadata={},
                scraped_at=scraped_at,
                fetch_status="skipped",
                fetch_error="no url",
            )

        try:
            downloaded = trafilatura.fetch_url(url)
            if downloaded is None:
                return EnrichedSignal(
                    original=signal,
                    full_text=None,
                    metadata={},
                    scraped_at=scraped_at,
                    fetch_status="skipped",
                    fetch_error="trafilatura fetch returned None",
                )

            text = trafilatura.extract(
                downloaded,
                include_comments=False,
                include_tables=False,
                no_fallback=False,
            )
            if text is None:
                return EnrichedSignal(
                    original=signal,
                    full_text=None,
                    metadata={},
                    scraped_at=scraped_at,
                    fetch_status="skipped",
                    fetch_error="trafilatura extract returned None",
                )

            meta = trafilatura.extract_metadata(downloaded)
            meta_dict: dict[str, object] = {}
            if meta:
                meta_dict = {
                    "author": meta.author,
                    "sitename": meta.sitename,
                    "date": meta.date,
                }

            return EnrichedSignal(
                original=signal,
                full_text=text[:_MAX_CHARS],
                metadata=meta_dict,
                scraped_at=scraped_at,
                fetch_status="ok",
                fetch_error=None,
            )
        except Exception as exc:
            return EnrichedSignal(
                original=signal,
                full_text=None,
                metadata={},
                scraped_at=scraped_at,
                fetch_status="error",
                fetch_error=str(exc),
            )
