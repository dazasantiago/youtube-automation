# Claude Code rules for this repository

This file is loaded on every Claude Code session. Follow these rules unconditionally.

## Purpose

This is a **scraping-only module**. Its sole job is to collect raw signals from multiple sources and organize them so an LLM can read and classify them by topic. It does not evaluate, cluster, score, or categorize signals. All downstream analysis happens outside this module.

## Sources

Seven sources are scraped daily:
- `hn` — HackerNews (Algolia API)
- `reddit` — Configured subreddits (public RSS)
- `rss` — AI lab blogs + tech news feeds
- `hf` — HuggingFace models and spaces
- `github_trending` — GitHub trending repositories
- `x_apify` — X/Twitter accounts via Apify (optional; skipped gracefully if token missing)
- `gtrends` — Google Trends rising queries
- YouTube — Competitor channel scan via `run_yt_scan()` (separate from the 7 source adapters)

## Architecture invariants

1. **No LLM API calls.** Not Anthropic, not OpenAI. The pipeline is pure scraping.
2. **No embeddings.** No sentence-transformers, no DBSCAN, no ML.
3. **No scoring.** No demand/saturation/validation axes.
4. **No Notion sync.** Output is `data/signals.json` — a JSON file ready for LLM consumption.
5. **Channel handles live in `channels_final.py`.** Do not modify this file. Import to read.
6. **The DB is committed back to the repo.** SQLite at `data/intel.db`, binary in `.gitattributes`.
7. **YouTube quota is capped at 7,500 units/day.** Every call tracked in `quota_log`. Halt if exceeded.
8. **Every stage must be idempotent.** `UNIQUE(source, source_id)` enforces deduplication on signals.

## Pipeline stages (GitHub Actions — `.github/workflows/daily.yml`)

| UTC hour | Stage | What happens |
|---|---|---|
| 11:00 | `discovery_morning` | pull hn, reddit, rss, hf, github_trending, x_apify, gtrends |
| 12:00 | `youtube_scan` | scan tracked channels → new uploads → outlier detection |
| 21:00 | `discovery_afternoon` | lighter re-scan: hn, reddit, x_apify |

`workflow_dispatch` supports `all` or any single stage.

## Output

- `data/intel.db` — SQLite with raw signals, yt_channels, yt_videos, quota_log, run_log
- `data/signals.json` — Full export: last 7 days of signals grouped by source + YT outliers + YT underperformers. Rich structure with metrics and metadata.
- `data/handoff.json` — Compact flat list of `{id, title}` for all non-YT signals (hn, reddit, rss, x_apify, github_trending, gtrends, hf). No URLs — titles are sufficient for classification. ~15K tokens.
- `data/handoff_yt.json` — Compact flat list of `{id, title, url, description?}` for YT competitor videos (`yt:`) and underperformers (`yt_under:`). Descriptions truncated to 150 chars. ~20K tokens.

Both handoff files use compact JSON (no indentation) to stay under the Claude Read tool's 25K-token per-file limit.

## Database schema (simplified)

| Table | Purpose |
|---|---|
| `signals` | Raw items from all sources. `UNIQUE(source, source_id)` deduplicates. |
| `yt_channels` | ~50 competitor channels with cached playlist IDs and view medians. |
| `yt_videos` | Competitor uploads with view counts and outlier ratios. |
| `quota_log` | YouTube API call tracking — must not exceed 7,500 units/day. |
| `run_log` | Pipeline run metadata. |

## Code style

- Python 3.12, `uv` for packages, `ruff` for lint, `mypy --strict` for types.
- Every source adapter inherits from `SourceAdapter` ABC in `sources/base.py`.
- All times stored in UTC.

## Testing

- Every source adapter has at least one VCR-recorded test.
- `uv run python -m pytest -q` must pass before any change is merged.
- Use `uv run python -m pytest -q` (not `uv run pytest`) — the uv trampoline can fail on Windows.
