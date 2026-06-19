"""Tests for YouTube bootstrap — mocked API."""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from content_intel.db import get_db, init_db
from content_intel.sources.youtube import bootstrap_channels


def _make_channel_response(channel_id: str, title: str, uploads: str, subs: str) -> dict[str, object]:
    return {
        "items": [{
            "id": channel_id,
            "snippet": {"title": title},
            "contentDetails": {"relatedPlaylists": {"uploads": uploads}},
            "statistics": {"subscriberCount": subs, "viewCount": "1000000"},
        }]
    }


def test_bootstrap_no_api_key_returns_early() -> None:
    with patch.dict("os.environ", {}, clear=True):
        bootstrap_channels()  # should not raise


def test_bootstrap_inserts_channels() -> None:
    fake_channels = [
        (1, "Test Channel", "testhandle", "EN-Tier1"),
        (2, "Otro Canal", "otrocanal", "ES-Tier2"),
    ]
    responses = {
        "@testhandle": _make_channel_response("UC_test1", "Test Channel", "UU_test1", "500000"),
        "@otrocanal": _make_channel_response("UC_test2", "Otro Canal", "UU_test2", "200000"),
    }

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        init_db(db_path)

        with (
            patch.dict("os.environ", {"YOUTUBE_API_KEY": "fake_key"}),
            patch("content_intel.sources.youtube.build") as mock_build,
            patch("content_intel.sources.youtube.CHANNELS", fake_channels),
            patch("content_intel.db.DB_PATH", db_path),
        ):
            mock_yt = MagicMock()
            mock_build.return_value = mock_yt
            mock_list = MagicMock()
            mock_yt.channels.return_value.list.return_value = mock_list
            mock_list.execute.side_effect = [
                responses["@testhandle"],
                responses["@otrocanal"],
            ]
            bootstrap_channels(db_path=db_path)

        conn = get_db(db_path)
        rows = conn.execute("SELECT channel_id, language FROM yt_channels").fetchall()
        conn.close()

    ids = {r[0] for r in rows}
    assert "UC_test1" in ids
    assert "UC_test2" in ids
    langs = {r[0]: r[1] for r in rows}
    assert langs["UC_test1"] == "en"
    assert langs["UC_test2"] == "es"
