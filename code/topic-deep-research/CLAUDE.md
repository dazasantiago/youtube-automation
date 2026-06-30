# Claude Code rules — topic-deep-research

## Purpose

**Scraping-only.** Takes either a pre-classified topic JSON or a bare topic string and performs
deep content enrichment: full YouTube transcripts, full article text via trafilatura (HN/RSS/web),
full Reddit threads + comments, and Tavily web discovery for additional sources.

**No LLM API calls. No scoring. No evaluation.** Veracity and recency analysis happen in a
downstream stage.

---

## Architecture invariants

1. **No LLM API calls.** Pure scraping and HTTP-based search.
2. **No scoring or evaluation.** Roles and signals are preserved as-is.
3. **Isolation.** Does not import from `../automation/`. Reads only the topic input JSON or a topic
   string.
4. **Every enrichment is isolated.** A single failed fetch must never abort the pipeline
   (try/except per unit, returns `fetch_status: "error"` or `"skipped"`).
5. **`results/` is versioned.** Output files per topic/week are committed; `data/*.json` inputs stay gitignored.

---

## Two modes of operation

### Mode 1: `--input` — pre-classified signals (classic)

Consumes a JSON file produced by an upstream middleware that has already classified signals under
a topic.

```bash
uv run deep-research --input data/<topic-slug>.json
```

Optional flags (both modes):
- `--out-dir <path>` — base output directory (default: `results/`)
- `--top-signals <n>` — max signals to enrich (default: 20)
- `--top-comments <n>` — max Reddit comments per post (default: 10)

**Input shape:**
```json
{
  "topic": "MCP Servers",
  "generated_at": "2026-06-18T12:00:00Z",
  "signals": [ ...Signal[] ]
}
```

**Required fields per signal:**

| Field | Type | Notes |
|---|---|---|
| `source` | string | `"hn"`, `"reddit"`, `"reddit/<sub>"`, `"youtube"`, `"rss"`, `"github_trending"`, etc. |
| `source_id` | string | Unique ID within the source |
| `title` | string | |
| `url` | string \| null | Required for enrichment; no URL → skip |
| `signal_type` | `"signal"` \| `"yt_video"` | `"yt_video"` activates the YouTube transcript enricher |
| `roles` | string[] | See below |
| `metrics` | object | For YouTube in classic mode must include `outlier_ratio` |

**Roles** (metadata from upstream, not used to change scraping behavior):

| Role | Meaning |
|---|---|
| `"signal"` | Primary content source |
| `"validator"` | Corroborates the topic direction |
| `"saturator"` | Indicates topic saturation in this source |

See [`data/example_input.json`](data/example_input.json) for a full example.

---

### Mode 2: `--topic` — discover from scratch (topic-only)

Discovers signals from scratch across HN, Reddit, YouTube, and Tavily web, then enriches them
with the same pipeline as Mode 1.

```bash
uv run deep-research --topic "GLM 5.2"
```

Additional flag:
- `--per-source <n>` — signals to fetch per source (default: 8)

**Sources used for discovery:**

| Source | Implementation | Key required |
|---|---|---|
| HN | Algolia API (`hn.algolia.com/api/v1/search`) | No |
| YouTube | YouTube Data API v3 (`googleapis.com/youtube/v3/search`) | `YOUTUBE_API_KEY` |
| Tavily web | Existing `discover_sources()` | `TAVILY_API_KEY` |

If `YOUTUBE_API_KEY` is absent, YouTube signals are silently skipped; HN/Tavily continue.

**Reddit is intentionally excluded from discovery.** `old.reddit.com/search.json` blocks bots
unreliably. Tavily already surfaces the most relevant Reddit threads as `discovered_sources`,
which can then be enriched by `RedditEnricher` in a downstream step if the URL is a direct post
link.

Discovered signals are interleaved (round-robin across sources) before being passed to the
enricher pipeline, so `--top-signals` doesn't eliminate an entire source.

**`--input` and `--topic` are mutually exclusive** — exactly one must be provided.

---

## Enrichment logic by source

| `source` / `signal_type` | Enricher | What it fetches |
|---|---|---|
| `signal_type == "yt_video"` | `YouTubeEnricher` | Full transcript (up to 20k chars), EN or ES |
| `source == "hn"` | `HNEnricher` (trafilatura) | Full article text + author/date |
| `source.startswith("reddit")` | `RedditEnricher` | Post body + top N comments + timestamps |
| Any other with URL | `HNEnricher` (trafilatura fallback) | Extracted text from URL |

### YouTube outlier gate

In **classic mode** (`--input`), the transcript is fetched only when:
- `outlier_ratio >= 3.0` (clear overperformer), **or**
- `outlier_ratio <= 0.33` (extreme underperformer)

Videos with ratio between 0.34–2.99 → `fetch_status: "skipped"`.

In **topic mode** (`--topic`), discovered YouTube videos have no channel baseline so no
`outlier_ratio` is available. The enricher runs with `force=True`, which **bypasses the gate
entirely** and always attempts to fetch the transcript.

---

## Web discovery (Tavily)

`discover_sources()` runs on every invocation (both modes) and searches Tavily for additional web
sources on the topic. Results are written to `discovered_sources.json` alongside the enriched
signals. If `TAVILY_API_KEY` is absent, this step is silently skipped and an empty array is
written.

---

## Output

Written to:
```
results/<YYYY-WNN>/<topic-slug>/
  signals_enriched.json
  discovered_sources.json
```

The ISO week label is auto-calculated. The slug lowercases the topic and replaces non-alphanumeric
chars with hyphens (`"MCP Servers"` → `"mcp-servers"`).

**`signals_enriched.json`** — array of `EnrichedSignal`:
```json
{
  "original": { ...full Signal with roles + metrics... },
  "full_text": "Transcript or article...",
  "metadata": { "transcript_segment_count": 312, "video_id": "abc111" },
  "scraped_at": "2026-06-18T13:45:00Z",
  "fetch_status": "ok",
  "fetch_error": null
}
```
`fetch_status`: `"ok"` | `"skipped"` (no error, just not applicable) | `"error"` (fetch failed).

**`discovered_sources.json`** — array of `DiscoveredSource`:
```json
{
  "url": "https://...",
  "domain": "simonwillison.net",
  "title": "...",
  "content": "Extracted text from Tavily...",
  "published_date": "2026-06-15",
  "search_query": "MCP Servers",
  "scraped_at": "2026-06-18T13:45:00Z"
}
```
`published_date` can be `null`.

See [`data/example.output.json`](data/example.output.json) for a full example. A real run writes the
two arrays as **separate files** (`signals_enriched.json` and `discovered_sources.json`); the example
combines them in one documented object under `signals_enriched` / `discovered_sources` keys.

---

## Environment variables

| Variable | Required | Used by |
|---|---|---|
| `TAVILY_API_KEY` | Optional | Web discovery (`discover_sources`). Without it → empty `discovered_sources.json`, enrichment continues |
| `YOUTUBE_API_KEY` | Optional (topic mode only) | YouTube signal discovery. Without it → YouTube signals skipped, HN/Reddit still run |
| `YOUTUBE_COOKIES_FILE` | Optional | Path to a Netscape-format cookies.txt exported from a logged-in browser. Required when YouTube returns 429 rate-limit errors on transcript fetch. Export via the "Get cookies.txt LOCALLY" browser extension. |

---

## Code style

- Python 3.12, `uv` for packages, `ruff` for lint, `mypy --strict` for types.
- All datetimes in UTC.
- Run tests: `uv run python -m pytest -q` (not `uv run pytest`) on Windows.
- Lint: `uv run ruff check .`
- Types: `uv run mypy --strict src`
