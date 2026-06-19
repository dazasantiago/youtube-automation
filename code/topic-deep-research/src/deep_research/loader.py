from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from deep_research.models import Signal, TopicInput


def load_topic_input(path: Path) -> TopicInput:
    raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))

    topic = raw.get("topic")
    if not topic or not isinstance(topic, str):
        raise ValueError(f"Missing or invalid 'topic' field in {path}")

    generated_at = raw.get("generated_at", "")
    raw_signals: list[dict[str, Any]] = raw.get("signals", [])

    signals = [_parse_signal(s) for s in raw_signals]
    return TopicInput(topic=topic, generated_at=generated_at, signals=signals)


def _parse_signal(raw: dict[str, Any]) -> Signal:
    roles_raw = raw.get("roles", ["signal"])
    valid_roles = {"signal", "validator", "saturator"}
    roles = [r for r in roles_raw if r in valid_roles] or ["signal"]

    return Signal(
        source=raw.get("source", "unknown"),
        source_id=raw.get("source_id", raw.get("video_id", "")),
        title=raw.get("title", ""),
        url=raw.get("url"),
        description=raw.get("description"),
        posted_at=raw.get("posted_at"),
        language=raw.get("language"),
        metrics=raw.get("metrics", {}),
        signal_type=raw.get("signal_type", "signal"),
        roles=roles,
    )
