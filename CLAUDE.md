# CLAUDE.md — YouTube content pipeline

This file is loaded on every Claude Code session in this project. It gives the high-level map.
**For stage-specific rules, read the `STAGE.md` inside the relevant `code/<stage>/` folder** — those
files hold the detailed invariants, schemas, and run instructions for each stage.

## Purpose

A pipeline that turns a topic Santiago has already decided to make into raw research material, a
curated digest, and then a content plan (which pieces get made, and each one's schema). There is
**no scraping, classification, or automated topic discovery** — Santiago picks the topic himself
(from whatever he's reading, watching, or wants to learn) and tells Claude to research it. **No
stage makes LLM API calls or scores content** — editorial judgment happens via Claude reading skills
and dialoguing with Santiago, not via automated ML.

> The pipeline used to start with an automated signals-scraper → topic-classifier → topic-decider
> chain that scraped the web daily and proposed topics. It was removed (2026-07-12): the noise-to-signal
> ratio was poor (mostly clickbait/generic YouTube trends already visible without scraping), it
> required constant manual triage, and it pulled Santiago toward being a generic "trend reporter"
> instead of building a more authentic, self-directed channel. If you find references to those stages
> in old commits or docs, they're gone — don't try to resurrect or depend on them.

## Pipeline stages

```
topic-deep-research  →  research-digest  →  schema-builder
   (automated CLI)        (Claude subagent,     (Claude skill)
                            auto-invoked)
   results/<week>/<slug>/  results/<week>/<slug>/  data/<week>/<slug>/schema.md
                            digest.md               + Notion Topic/Pieces
```

| Stage | What it does | How it runs | Details |
|---|---|---|---|
| **topic-deep-research** | Given a bare topic string, discovers and deep-enriches content on it (HN, YouTube transcripts, Tavily web search) — full text, not just links | Claude invokes it directly: `uv run deep-research --topic "<topic>"` | [code/topic-deep-research/STAGE.md](code/topic-deep-research/STAGE.md) |
| **research-digest** | Condenses the raw enriched signals + discovered sources into a single curated `digest.md` (sub-angles, contradictions, gaps, a content-depth read) so the next stage never wades through raw/noisy JSON | Claude always invokes this subagent right after `topic-deep-research` finishes for a topic — not triggered by name | [.claude/agents/research-digest.md](.claude/agents/research-digest.md) |
| **schema-builder** | Reads the digest and dialogues with Santiago to decide *which* content pieces to make (long-form, shorts, text — no fixed set per platform) and builds each one's schema (angle, structure/points, sources, hook, closing) as a Markdown plan. Approving the schemas creates the Topic + Pieces in Notion, `In Production` | Claude invokes the `schema-builder` skill | [code/schema-builder/STAGE.md](code/schema-builder/STAGE.md) |

## How this starts

Santiago tells Claude the topic directly ("corre deep research sobre X", "investiga Y para el
próximo video") — no upstream artifact required. Optionally he can paste 1-3 seed links/sources into
the conversation; the skill/CLI folds those in, but most of the time `--topic` alone is enough since
`topic-deep-research` does its own discovery (HN Algolia, YouTube Data API, Tavily).

`topic-deep-research` still supports a legacy `--input <file>.json` mode (pre-built signal list) for
one-off cases where Santiago wants to hand it a specific curated set of sources instead of letting it
discover on its own — see the stage's `STAGE.md` for the shape. This is not the common path anymore.

## How stages communicate

### topic-deep-research → research-digest

- **Artifacts consumed:** `code/topic-deep-research/results/<YYYY-WNN>/<slug>/signals_enriched.json`
  + `discovered_sources.json` for one already-researched topic. `<YYYY-WNN>` is the ISO week the
  research ran, auto-calculated by the CLI; `<slug>` is the topic string slugified.
- **Artifact produced:** `code/topic-deep-research/results/<YYYY-WNN>/<slug>/digest.md` — sub-angles
  with key points + backing sources, contradictions/tensions, gaps, and a content-depth read (does
  this topic support a long-form, or is it more of a shorts/text-sized topic). Written into the same
  `results/` folder — `research-digest` never invents a new week label or slug.
- **Producer:** the `research-digest` subagent — no dialogue, filesystem-only, always invoked
  automatically right after the CLI finishes for a topic.
- **Consumer:** `schema-builder`, which reads only `digest.md`, never the raw JSON directly.

### research-digest → schema-builder

- **Artifact consumed:** `digest.md` for one already-digested topic.
- **Artifact produced:** `code/schema-builder/data/<YYYY-WNN>/<slug>/schema.md` — a leading "piezas
  aprobadas" list (the negotiated content mix), the shared angle/thesis, then one schema section per
  approved piece (full hook/structure/closing for long-form; lighter angle/points/hook for shorts
  and text pieces). `<YYYY-WNN>` and `<slug>` are reused as-is from the `results/` folder being
  read. **This is a Markdown document for Santiago to read while recording/writing, not a JSON
  handoff contract** — there is deliberately no machine-readable artifact here.
- **Producer:** the `schema-builder` skill (dialogue-driven — first asks Santiago's own read on the
  topic, then negotiates which pieces get made at all, then builds each one's schema; this is the
  creative core of the stage, not automatable).
- **Consumer:** none — Santiago, directly, while recording/writing. This is the terminal
  file-producing stage. A future line-by-line script / production stage does not exist yet and, if
  built, would need its own contract (this stage's output is intentionally human-only).
- **Side-effect:** once Santiago approves the schemas, `schema-builder` **creates** the Topic
  (`Status: In Production` directly — there's no separate pre-research approval step anymore) and
  one Piece per approved content item in the Notion Content Hub, confirmed with Santiago first.

## Automation (GitHub Actions)

None. There is no scheduled workflow in this repo anymore — everything is started manually by
Santiago telling Claude what to research.

## Conventions

- Python 3.12, `uv` for packages, `ruff` for lint, `mypy --strict` for types (in the runnable stages).
- All datetimes stored in UTC.
- On Windows, run tests with `uv run python -m pytest -q` (not `uv run pytest` — the uv trampoline can fail).
- Per-stage `STAGE.md` files are the source of truth for that stage; this file only covers cross-stage concerns.
