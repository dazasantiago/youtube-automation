from __future__ import annotations

from pathlib import Path

import pytest

from deep_research.loader import load_topic_input

FIXTURE = Path(__file__).parent / "fixtures" / "topic_input_sample.json"


def test_loads_topic_and_signals() -> None:
    result = load_topic_input(FIXTURE)
    assert result.topic == "MCP Servers"
    assert len(result.signals) == 5


def test_signal_roles_parsed() -> None:
    result = load_topic_input(FIXTURE)
    reddit_signal = next(s for s in result.signals if s.source == "reddit")
    assert "signal" in reddit_signal.roles
    assert "validator" in reddit_signal.roles


def test_yt_video_type() -> None:
    result = load_topic_input(FIXTURE)
    yt = next(s for s in result.signals if s.signal_type == "yt_video")
    assert yt.source_id == "dQw4w9WgXcQ"


def test_missing_topic_raises() -> None:
    import json
    import tempfile

    bad = {"signals": []}
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
        json.dump(bad, f)
        tmp = Path(f.name)
    with pytest.raises(ValueError, match="topic"):
        load_topic_input(tmp)
    tmp.unlink()
