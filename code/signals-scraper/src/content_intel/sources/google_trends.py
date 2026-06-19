"""Google Trends source adapter via pytrends."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from pytrends.request import TrendReq

from content_intel.sources.base import RawSignal, SourceAdapter

logger = logging.getLogger(__name__)

KEYWORDS_PATH = Path(__file__).parent.parent.parent.parent / "config" / "seed_keywords.yml"


class GoogleTrendsAdapter(SourceAdapter):
    name = "gtrends"

    def _load_keywords(self) -> list[str]:
        try:
            with open(KEYWORDS_PATH) as f:
                data: dict[str, Any] = yaml.safe_load(f) or {}
            keywords: list[str] = data.get("keywords", []) or []
            return keywords
        except Exception:
            logger.warning("Failed to load seed_keywords.yml")
            return []

    def _fetch_for_geo(
        self,
        pytrends: TrendReq,
        keywords: list[str],
        geo: str,
        seen_ids: set[str],
    ) -> list[RawSignal]:
        signals: list[RawSignal] = []
        for keyword in keywords:
            try:
                pytrends.build_payload([keyword], timeframe="now 1-d", geo=geo)
                related: dict[str, Any] = pytrends.related_queries()
                rising = related.get(keyword, {}).get("rising")
                if rising is None:
                    time.sleep(0.5)
                    continue
                for _, row in rising.iterrows():
                    query: str = str(row["query"])
                    raw_value = row["value"]
                    is_breakout = str(raw_value).lower() == "breakout"
                    value: int = 9999 if is_breakout else int(raw_value)
                    sid = f"{keyword}:{query}"
                    if sid in seen_ids:
                        continue
                    seen_ids.add(sid)
                    label = "breakout" if is_breakout else f"rising: {value}%"
                    signals.append(
                        RawSignal(
                            source=self.name,
                            source_id=sid,
                            title=f"{query} ({label} related to {keyword})",
                            url=None,
                            description=None,
                            posted_at=datetime.now(UTC),
                            raw_metrics={"value": value, "keyword": keyword, "geo": geo, "is_breakout": is_breakout},
                            language="en",
                        )
                    )
            except Exception as exc:
                logger.warning("Google Trends error for keyword %r (geo=%s): %s", keyword, geo, exc)
            time.sleep(0.5)
        return signals

    def fetch(self) -> list[RawSignal]:
        keywords = self._load_keywords()
        pytrends = TrendReq(hl="en-US", tz=300)

        seen_ids: set[str] = set()
        signals: list[RawSignal] = []

        for geo in ("US", "MX", "CO", "ES"):
            signals.extend(self._fetch_for_geo(pytrends, keywords, geo, seen_ids))

        return signals
