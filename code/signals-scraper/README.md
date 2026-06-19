# Signal Scraper

Daily scraping pipeline for an AI/automation YouTube creator. Pulls raw signals from 8 web sources and ~50 competitor YouTube channels. Outputs structured JSON for LLM-based topic analysis.

**This system scrapes only.** No evaluation, no clustering, no scoring. All analysis happens downstream.

See [ARCHITECTURE.md](ARCHITECTURE.md) for full technical documentation.

## Setup

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager

### Install

```bash
uv sync
```

### Secrets

Add these as GitHub Actions repository secrets (or in a local `.env` file):

| Secret | Required | Description |
|---|---|---|
| `YOUTUBE_API_KEY` | Yes | YouTube Data API v3 key |
| `PRODUCT_HUNT_TOKEN` | Yes | Product Hunt developer token |
| `APIFY_TOKEN` | No | Apify token for X/Twitter scraping (skipped if missing) |

### One-time bootstrap

```bash
# Resolve YouTube channel handles → channel IDs (run once, result committed to repo)
uv run python scripts/bootstrap_channels.py
```

## Usage

```bash
# Pull signals from all sources
uv run content-intel pull

# Pull from specific sources
uv run content-intel pull --sources hn,reddit,rss

# Dry run (no DB writes)
uv run content-intel pull --dry-run

# Scan competitor YouTube channels
uv run content-intel yt-scan

# Export last 3 days of signals to data/signals.json
uv run content-intel export

# Export last N days
uv run content-intel export --days 7
```

## Pipeline stages (automated via GitHub Actions)

| UTC | Stage | Sources |
|---|---|---|
| 11:00 | `discovery_morning` | hn, reddit, rss, hf, github_trending, product_hunt, x_apify, gtrends |
| 12:00 | `youtube_scan` | ~50 competitor channels |
| 21:00 | `discovery_afternoon` | hn, reddit, x_apify |

Run a stage manually:

```bash
uv run python scripts/run_pipeline.py --stage discovery_morning
uv run python scripts/run_pipeline.py --stage youtube_scan
uv run python scripts/run_pipeline.py --stage all
```

## Output

- `data/intel.db` — SQLite database with all scraped data (committed to repo)
- `data/signals.json` — last 3 days of signals grouped by source; feed this to an LLM

## Development

```bash
# Lint
uv run ruff check .

# Type check
uv run mypy --strict src/

# Tests (use python -m pytest, not pytest directly — uv trampoline issue on Windows)
uv run python -m pytest -q
```

## Channel list

Competitor channels are defined in `channels_final.py`. Do not modify — it is the owner-maintained source of truth. Import it to read.
