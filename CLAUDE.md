# CLAUDE.md — YouTube content-intelligence pipeline

This file is loaded on every Claude Code session in this project. It gives the high-level map.
**For stage-specific rules, read the `STAGE.md` inside the relevant `code/<stage>/` folder** — those
files hold the detailed invariants, schemas, and run instructions for each stage.

## Purpose

An end-to-end pipeline that decides what to produce for an AI / automation / tech YouTube channel.
It scrapes signals from across the web, groups them into emerging weekly topics, lets Santiago pick
which ones are worth producing, and deep-researches the chosen ones into raw material for video
scripts. **No stage makes LLM API calls or scores content** — classification and editorial judgment
happen via Claude reading prompts/skills, not via automated ML.

## Pipeline stages

```
signals-scraper  →  topic-classifier  →  topic-decider  →  topic-deep-research
   (automated)         (Claude prompt)      (Claude skill)      (automated)
   intel.db            topics-YYYY-WNN.json  Notion Hub          results/<week>/<slug>/
   handoff*.json       topic_inputs/         data/<slug>.json
```

| Stage | What it does | How it runs | Details |
|---|---|---|---|
| **signals-scraper** | Scrapes 7 sources + YouTube competitor scan into `intel.db`; exports `handoff*.json` | Automated — GitHub Actions, daily cron | [code/signals-scraper/STAGE.md](code/signals-scraper/STAGE.md) |
| **topic-classifier** | Groups a week of signals into emerging topics (`topics-YYYY-WNN.json`) | Claude reads `prompt.md` (weekly, manual) | [code/topic-classifier/STAGE.md](code/topic-classifier/STAGE.md) |
| **topic-decider** | Editorial layer: ranks topics, cross-checks Notion Content Hub, approves & creates entries | Claude invokes the `topic-decider` skill | [code/topic-decider/STAGE.md](code/topic-decider/STAGE.md) |
| **topic-deep-research** | Deep content enrichment (transcripts, articles, Reddit, Tavily) per approved topic | Automated CLI (`uv run deep-research`) | [code/topic-deep-research/STAGE.md](code/topic-deep-research/STAGE.md) |

## How stages communicate (handoff contracts)

Stages do **not** call each other directly — each one hands off to the next through a versioned
**artifact** with a fixed shape. This is the contract surface; the per-stage `STAGE.md` files own
the full schemas.

### 1. signals-scraper → topic-classifier

- **Artifacts:** `code/signals-scraper/data/handoff.json` (all non-YT signals as `{id, title}`),
  `handoff_yt.json` (`yt:` viral + `yt_under:` flop videos as `{id, title, description?}`), and
  `intel.db` (used later to resolve signal IDs).
- **Producer:** `run_export`, called **only in the `discovery_afternoon` stage** (21:00 UTC) — the
  files are committed back to the repo. If they look stale, that stage did not run.
- **Consumer:** Claude, during the classifier session, reads `prompt.md` + both handoff files.
- **Type:** automated artifact, **manual consumption**.

### 2. topic-classifier → topic-decider

- **Artifacts:** `code/topic-classifier/data/topics-YYYY-WNN.json` (topics with `signal_ids`,
  `has_viral_yt`, `has_yt_flop`, `sources`, `signal_count`). `build_topic_inputs.py` resolves those
  IDs against `intel.db` into per-topic files under `data/topic_inputs/` (gitignored, regenerated weekly).
- **Producer:** the Claude classifier session.
- **Consumer:** the `topic-decider` skill (reads the most recent topics file; cross-checks Notion to dedupe).
- **Type:** manual → manual.

### 3. topic-decider → topic-deep-research

- **Artifact:** one standalone `code/topic-deep-research/data/<slug>.json` per approved topic, plus a
  Topic + 6 Pieces created in the Notion Content Hub. Input shape:
  ```json
  { "topic": "MCP Servers", "generated_at": "2026-06-18T12:00:00Z", "signals": [ Signal, ... ] }
  ```
  Required per signal: `source`, `source_id`, `title`, `url` (null → skipped), `signal_type`
  (`"signal"` | `"yt_video"`), `roles`, `metrics` (YouTube must include `outlier_ratio`).
- **Roles** (assigned upstream, preserved as-is, never change scraping behavior):
  `"signal"` (primary source) · `"validator"` (corroborates) · `"saturator"` (topic saturation).
- **Producer:** the `topic-decider` skill (copies the per-topic input out of `topic_inputs/`).
- **Consumer:** `uv run deep-research --input data/<slug>.json` — the skill can invoke it directly.
- **Output (terminal):** `results/<YYYY-WNN>/<slug>/signals_enriched.json` + `discovered_sources.json`.
- **Type:** manual skill → automated CLI.

## Connection status

- **All four stages are wired** end-to-end through the artifact contracts above — there is no broken
  link between them. ✅
- **Only one boundary is fully automated:** the daily cron inside `signals-scraper`. Everything from
  `topic-classifier` onward is **human-in-the-loop** — a Claude prompt or skill that Santiago starts.
  There is **no scheduler** that triggers weekly classification; that step is initiated manually.
- **Downstream gap:** `topic-deep-research` is currently the **terminal** stage. Its `results/` are
  the raw material for scripting/production, but **no automated stage consumes them yet** — veracity
  analysis, script-writing, and video production happen outside this repo (or manually). A future
  stage would read `results/<week>/<slug>/` as its input contract.
- **Contract watch-point:** `build_topic_inputs.py` must emit the exact fields `topic-deep-research`
  requires (esp. `signal_type` and `metrics.outlier_ratio` for YouTube). A mismatch here silently
  degrades enrichment, so changes to either side must stay in sync.

## Automation (GitHub Actions)

Only `signals-scraper` runs on a schedule — see [.github/workflows/daily.yml](.github/workflows/daily.yml).
Three daily cron stages (11:00 `discovery_morning`, 12:00 `youtube_scan`, 21:00 `discovery_afternoon` UTC).
The stage is derived from the **cron expression** that triggered the run (`github.event.schedule`),
not the runner's wall-clock hour — this matters because GitHub frequently delays scheduled runs (see
the bug-fix note in [code/signals-scraper/STAGE.md](code/signals-scraper/STAGE.md)).

**Health check:** a real stage run takes minutes; a skipped/no-op run finishes in ~15s.

## Conventions

- Python 3.12, `uv` for packages, `ruff` for lint, `mypy --strict` for types (in the runnable stages).
- All datetimes stored in UTC.
- On Windows, run tests with `uv run python -m pytest -q` (not `uv run pytest` — the uv trampoline can fail).
- Per-stage `STAGE.md` files are the source of truth for that stage; this file only covers cross-stage concerns.
