"""Invoked by GitHub Actions — runs a named scraping stage."""

from __future__ import annotations

import argparse
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

STAGES = {
    "discovery_morning": ["hn", "reddit", "rss", "hf", "github_trending", "product_hunt", "x_apify", "gtrends"],
    "youtube_scan": [],
    "discovery_afternoon": ["hn", "reddit", "x_apify"],
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True, choices=list(STAGES) + ["all"])
    args = parser.parse_args()

    from content_intel.db import init_db

    init_db()

    if args.stage in ("discovery_morning", "discovery_afternoon", "all"):
        from content_intel.pipeline.ingest import run_pull

        sources = ",".join(STAGES.get(args.stage, [])) if args.stage != "all" else "all"
        run_pull(sources=sources)

    if args.stage in ("youtube_scan", "all"):
        from content_intel.sources.youtube import run_yt_scan

        run_yt_scan()

    if args.stage in ("all", "discovery_afternoon"):
        from content_intel.export import run_export

        run_export(days=7, out="data/signals.json")


if __name__ == "__main__":
    main()
