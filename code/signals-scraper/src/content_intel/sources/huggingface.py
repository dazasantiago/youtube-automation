"""Hugging Face trending models and spaces adapter."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from content_intel.sources.base import RawSignal, SourceAdapter

logger = logging.getLogger(__name__)

_MODELS_URL = "https://huggingface.co/api/models"
_SPACES_URL = "https://huggingface.co/api/spaces"

_ALLOWED_PIPELINE_TAGS = {
    "text-generation",
    "conversational",
    "text2text-generation",
    "question-answering",
    "summarization",
}
_ALLOWED_LIBRARIES = {"transformers", "peft"}


def _parse_hf_datetime(value: Any) -> datetime:
    if not value:
        return datetime.now(UTC)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(UTC)


def _model_description(model: dict[str, Any]) -> str | None:
    pipeline_tag = str(model.get("pipeline_tag") or "")
    library_name = str(model.get("library_name") or "")
    tags: list[str] = [str(t) for t in (model.get("tags") or []) if t]
    parts = [p for p in [pipeline_tag, library_name] if p]
    if tags:
        parts.append(", ".join(tags[:5]))
    return " | ".join(parts) or None


def _space_description(space: dict[str, Any]) -> str | None:
    sdk = str(space.get("sdk") or "")
    tags: list[str] = [str(t) for t in (space.get("tags") or []) if t]
    parts = [p for p in [sdk] if p]
    if tags:
        parts.append(", ".join(tags[:5]))
    return " | ".join(parts) or None


class HuggingFaceAdapter(SourceAdapter):
    name = "hf"

    def fetch(self) -> list[RawSignal]:
        signals: list[RawSignal] = []

        with httpx.Client(timeout=30, follow_redirects=True) as client:
            # --- Models ---
            try:
                resp = client.get(
                    _MODELS_URL, params={"sort": "trendingScore", "direction": -1, "limit": 30}
                )
                resp.raise_for_status()
                models: list[dict[str, Any]] = resp.json()
                for model in models:
                    model_id = str(model.get("modelId") or model.get("id") or "")
                    if not model_id:
                        continue
                    pipeline_tag = str(model.get("pipeline_tag") or "")
                    library_name = str(model.get("library_name") or "")
                    if (
                        pipeline_tag not in _ALLOWED_PIPELINE_TAGS
                        and library_name not in _ALLOWED_LIBRARIES
                    ):
                        continue
                    signals.append(
                        RawSignal(
                            source="hf",
                            source_id=f"model:{model_id}",
                            title=f"[HF Model] {model_id}",
                            url=f"https://huggingface.co/{model_id}",
                            description=_model_description(model),
                            posted_at=_parse_hf_datetime(
                                model.get("createdAt") or model.get("lastModified")
                            ),
                            raw_metrics={
                                "trending_score": model.get("trendingScore", 0),
                                "likes": model.get("likes", 0),
                                "downloads": model.get("downloads", 0),
                            },
                            language="en",
                        )
                    )
            except httpx.HTTPStatusError as exc:
                logger.warning("[hf] HTTP %s fetching models", exc.response.status_code)
            except Exception:
                logger.warning("[hf] failed to fetch models", exc_info=True)

            # --- Spaces ---
            try:
                resp = client.get(
                    _SPACES_URL, params={"sort": "trendingScore", "direction": -1, "limit": 20}
                )
                resp.raise_for_status()
                spaces: list[dict[str, Any]] = resp.json()
                for space in spaces:
                    space_id = str(space.get("id") or "")
                    if not space_id:
                        continue
                    signals.append(
                        RawSignal(
                            source="hf",
                            source_id=f"space:{space_id}",
                            title=f"[HF Space] {space_id}",
                            url=f"https://huggingface.co/spaces/{space_id}",
                            description=_space_description(space),
                            posted_at=_parse_hf_datetime(
                                space.get("createdAt") or space.get("lastModified")
                            ),
                            raw_metrics={
                                "trending_score": space.get("trendingScore", 0),
                                "likes": space.get("likes", 0),
                            },
                            language="en",
                        )
                    )
            except httpx.HTTPStatusError as exc:
                logger.warning("[hf] HTTP %s fetching spaces", exc.response.status_code)
            except Exception:
                logger.warning("[hf] failed to fetch spaces", exc_info=True)

        logger.info("[hf] fetched %d signals", len(signals))
        return signals
