# CLAUDE.md — YouTube content pipeline

This file is loaded on every Claude Code session in this project. It gives the high-level map.
**For stage-specific rules, read the `STAGE.md` inside the relevant `code/<stage>/` folder** — those
files hold the detailed invariants, schemas, and run instructions for each stage.

## Purpose

A two-stage pipeline that turns a topic Santiago has already decided to make into raw research
material and then a video schema. There is **no scraping, classification, or automated topic
discovery** — Santiago picks the topic himself (from whatever he's reading, watching, or wants to
learn) and tells Claude to research it. **No stage makes LLM API calls or scores content** —
editorial judgment happens via Claude reading skills, not via automated ML.

> The pipeline used to start with an automated signals-scraper → topic-classifier → topic-decider
> chain that scraped the web daily and proposed topics. It was removed (2026-07-12): the noise-to-signal
> ratio was poor (mostly clickbait/generic YouTube trends already visible without scraping), it
> required constant manual triage, and it pulled Santiago toward being a generic "trend reporter"
> instead of building a more authentic, self-directed channel. If you find references to those stages
> in old commits or docs, they're gone — don't try to resurrect or depend on them.

## Pipeline stages

```
topic-deep-research  →  longform-schema-builder
   (automated CLI)          (Claude skill)
   results/<week>/<slug>/   data/<week>/<slug>/schema.md
```

| Stage | What it does | How it runs | Details |
|---|---|---|---|
| **topic-deep-research** | Given a bare topic string, discovers and deep-enriches content on it (HN, YouTube transcripts, Tavily web search) — full text, not just links | Claude invokes it directly: `uv run deep-research --topic "<topic>"` | [code/topic-deep-research/STAGE.md](code/topic-deep-research/STAGE.md) |
| **longform-schema-builder** | Digests the deep research and dialogues with Santiago to build the long-form video's general schema (angle, sections, sources, hook, closing) as a Markdown recording guide | Claude invokes the `longform-schema-builder` skill | [code/longform-schema-builder/STAGE.md](code/longform-schema-builder/STAGE.md) |

## How this starts

Santiago tells Claude the topic directly ("corre deep research sobre X", "investiga Y para el
próximo video") — no upstream artifact required. Optionally he can paste 1-3 seed links/sources into
the conversation; the skill/CLI folds those in, but most of the time `--topic` alone is enough since
`topic-deep-research` does its own discovery (HN Algolia, YouTube Data API, Tavily).

`topic-deep-research` still supports a legacy `--input <file>.json` mode (pre-built signal list) for
one-off cases where Santiago wants to hand it a specific curated set of sources instead of letting it
discover on its own — see the stage's `STAGE.md` for the shape. This is not the common path anymore.

## How stages communicate

### topic-deep-research → longform-schema-builder

- **Artifacts consumed:** `code/topic-deep-research/results/<YYYY-WNN>/<slug>/signals_enriched.json`
  + `discovered_sources.json` for one already-researched topic. `<YYYY-WNN>` is the ISO week the
  research ran, auto-calculated by the CLI; `<slug>` is the topic string slugified.
- **Artifact produced:** `code/longform-schema-builder/data/<YYYY-WNN>/<slug>/schema.md` —
  angle/thesis, hook, ordered sections (each with key points + sources), counterpoints, closing,
  optional clip candidates. `<YYYY-WNN>` and `<slug>` are reused as-is from the `results/` folder
  being read — this stage never invents a new week label or slug. **This is a Markdown document for
  Santiago to read while recording, not a JSON handoff contract** — there is deliberately no
  machine-readable artifact here.
- **Producer:** the `longform-schema-builder` skill (dialogue-driven — this is the creative core of
  the stage, not automatable).
- **Consumer:** none — Santiago, directly, while recording. This is the terminal stage. A future
  line-by-line script / production stage does not exist yet and, if built, would need its own
  contract (this stage's output is intentionally human-only, not designed to be parsed).
- **Optional side-effect:** may move the Topic in the Notion Content Hub from `Approved` to
  `In Production` (confirmed with Santiago first), if Santiago is still tracking topics there.

## Automation (GitHub Actions)

None. There is no scheduled workflow in this repo anymore — everything is started manually by
Santiago telling Claude what to research.

## Conventions

- Python 3.12, `uv` for packages, `ruff` for lint, `mypy --strict` for types (in the runnable stages).
- All datetimes stored in UTC.
- On Windows, run tests with `uv run python -m pytest -q` (not `uv run pytest` — the uv trampoline can fail).
- Per-stage `STAGE.md` files are the source of truth for that stage; this file only covers cross-stage concerns.
