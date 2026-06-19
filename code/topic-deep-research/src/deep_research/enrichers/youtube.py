from __future__ import annotations

import re
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import httpx
from youtube_transcript_api import (
    NoTranscriptFound,
    TranscriptsDisabled,
    YouTubeTranscriptApi,
)

from deep_research.enrichers.base import Enricher
from deep_research.models import EnrichedSignal, Signal

_MAX_CHARS = 20_000


class YouTubeEnricher(Enricher):
    def __init__(self, force: bool = False) -> None:
        self._force = force

    def can_enrich(self, signal: Signal) -> bool:
        if signal.signal_type == "yt_video":
            return True
        url = signal.url or ""
        return "youtube.com/watch" in url or "youtu.be/" in url

    def enrich(self, signal: Signal, client: httpx.Client) -> EnrichedSignal:
        scraped_at = datetime.now(UTC).isoformat()
        video_id = _extract_video_id(signal.url or "")
        if not video_id and signal.signal_type == "yt_video":
            video_id = signal.source_id

        if not video_id:
            return EnrichedSignal(
                original=signal,
                full_text=None,
                metadata={},
                scraped_at=scraped_at,
                fetch_status="skipped",
                fetch_error="could not extract video_id from url",
            )

        raw_ratio = signal.metrics.get("outlier_ratio")
        outlier_ratio = float(raw_ratio) if isinstance(raw_ratio, (int, float)) else 1.0
        if not self._force and outlier_ratio >= 0.34 and outlier_ratio < 3.0:
            return EnrichedSignal(
                original=signal,
                full_text=None,
                metadata={"video_id": video_id, "outlier_ratio": outlier_ratio},
                scraped_at=scraped_at,
                fetch_status="skipped",
                fetch_error=f"outlier_ratio {outlier_ratio:.2f} outside enrichment range (>=3.0 or <=0.33)",
            )

        try:
            segments = YouTubeTranscriptApi.get_transcript(video_id, languages=["en", "es"])
            text = " ".join(s["text"] for s in segments)[:_MAX_CHARS]
            return EnrichedSignal(
                original=signal,
                full_text=text,
                metadata={"transcript_segment_count": len(segments), "video_id": video_id},
                scraped_at=scraped_at,
                fetch_status="ok",
                fetch_error=None,
            )
        except (TranscriptsDisabled, NoTranscriptFound) as exc:
            return EnrichedSignal(
                original=signal,
                full_text=None,
                metadata={"video_id": video_id},
                scraped_at=scraped_at,
                fetch_status="skipped",
                fetch_error=str(exc),
            )
        except Exception as exc:
            return EnrichedSignal(
                original=signal,
                full_text=None,
                metadata={"video_id": video_id},
                scraped_at=scraped_at,
                fetch_status="error",
                fetch_error=str(exc),
            )


def _extract_video_id(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc in ("www.youtube.com", "youtube.com", "m.youtube.com"):
        qs = parse_qs(parsed.query)
        ids = qs.get("v", [])
        return ids[0] if ids else ""
    if parsed.netloc in ("youtu.be",):
        return parsed.path.lstrip("/").split("?")[0]
    # bare video_id pattern as last resort
    match = re.search(r"(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})", url)
    return match.group(1) if match else ""
