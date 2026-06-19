from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path


def write_topic_result(result: object, base: Path = Path("results")) -> Path:
    from deep_research.models import TopicResult

    assert isinstance(result, TopicResult)
    slug = _slugify(result.topic_input.topic)
    out_dir = base / result.week_label / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    _write_json(out_dir / "signals_enriched.json", [dataclasses.asdict(s) for s in result.enriched_signals])
    _write_json(out_dir / "discovered_sources.json", [dataclasses.asdict(s) for s in result.discovered_sources])

    return out_dir


def _write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")
