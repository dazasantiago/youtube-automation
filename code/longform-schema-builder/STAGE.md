# Claude Code rules — longform-schema-builder

## Purpose

This stage is the **structural planning layer** between deep research and production. It reads the
enriched signals produced by `topic-deep-research` for a single already-researched topic, digests
them into sub-angles and gaps, and runs a dialogue with Santiago to build the **general schema** of
the long-form video: central thesis/angle, hook, an ordered list of sections (each with its key
points and the sources backing them), counterpoints worth showing, closing/CTA, and optional
short-form clip candidates.

This stage is executed by Claude invoking the `longform-schema-builder` skill. It is not a Python
project — no runnable package, no scripts. The skill lives at
`.claude/skills/longform-schema-builder/SKILL.md`.

**This is not a line-by-line script, and it is not a machine-readable artifact.** The output is a
single Markdown document meant for Santiago to read while recording — not JSON for another stage to
parse. A future stage (not implemented yet) would take this schema and produce the word-for-word
script.

---

## Pipeline position

```
topic-deep-research  →  longform-schema-builder  →  (future: line-by-line script / production)
results/<week>/<slug>/   (this stage)               data/<week>/<slug>/schema.md
```

---

## How to run this stage

### Prerequisites

- `topic-deep-research` must have already run for the topic: `code/topic-deep-research/results/<YYYY-WNN>/<slug>/signals_enriched.json` and `discovered_sources.json` must exist.
- Notion MCP connector active in the session **only if** you want the optional Topic status update (Phase 4). Everything else works without it.

### Invoke the skill

Trigger the skill with any phrase like:

- "armemos el esquema del video de \<tema\>"
- "qué puntos toca el video de \<tema\>"
- "estructura del video"
- "esqueleto del guion"

The `longform-schema-builder` skill auto-triggers on these phrases. No slash command needed.

### What the skill does (phases)

1. **Preconditions** — `git pull`; resolves which topic (asks if ambiguous, cross-checking
   `code/topic-deep-research/results/*/*/` and Notion Topics in `Approved`/`In Production`); confirms
   `signals_enriched.json` + `discovered_sources.json` exist; checks for an existing schema for that
   topic before overwriting.
2. **Digest** — groups enriched signals + discovered sources into sub-angles, flags contradictions
   and gaps, presents a short table before dialogue starts.
3. **Dialogue** — builds the schema block by block with Santiago: angle/thesis, hook, sections
   (title + key points + sources per section), counterpoints, closing/CTA, optional clip candidates.
4. **Write output** — a single `code/longform-schema-builder/data/<YYYY-WNN>/<slug>/schema.md`.
5. **Optional Notion update** — offers to move the Topic from `Approved` to `In Production`.
6. **Summary** — reports the file path, section count, and Notion status change (if any).

---

## Files in this folder

| File / Folder | Purpose |
|---|---|
| `STAGE.md` | This file — stage documentation |
| `data/example/schema.md` | Reference example of the exact output shape |
| `data/<YYYY-WNN>/<slug>/schema.md` | The schema for one topic — committed |

The active skill is at: `.claude/skills/longform-schema-builder/SKILL.md`

`data/example/` is a reference fixture, not a real run — never delete it.

---

## Outputs produced

| Output | Location | Committed? |
|---|---|---|
| `schema.md` | `code/longform-schema-builder/data/<YYYY-WNN>/<slug>/schema.md` | Yes — terminal artifact of this stage, same convention as `topic-deep-research/results/` |
| Topic status → `In Production` | Content Hub (cloud), optional | N/A |

`<YYYY-WNN>` and `<slug>` are **reused as-is** from the `topic-deep-research/results/` folder being
read — this stage never invents a new week label or slug.

There is deliberately **no JSON artifact**. This stage's output is for Santiago to read while
recording, not for another automated stage to consume — see
[`data/example/schema.md`](data/example/schema.md) for the exact shape.

---

## `schema.md` shape

```markdown
# <Título> — Esquema del video

**Semana:** 2026-W28 · **Slug:** hyperframes · **Generado:** 2026-07-09

## Ángulo / tesis
...

## Hook (apertura)
...

## Estructura

### 1. <Título de sección> (media)
- idea clave
- idea clave

**Fuentes:** hn:47797513, discovered:https://hyperframes.app

## Contrapuntos
- ...

## Cierre
...

## Candidatos a clips (opcional)
- ...

## Preguntas abiertas / huecos
- ...
```

`Fuentes` entries reuse the `source:source_id` format already used by `topic-classifier` for
signals (`hn:47797513`, `yt:RuhhLUfTXrY`), and use a `discovered:<url>` prefix for entries that came
from `discovered_sources.json` (no `source_id` there).

---

## Notion Content Hub reference

Only touches the **Topics** database — `data_source_id: 206658fc-5314-417f-ad4b-f114d26deacd` —
and only its `Status` property, moving it from `Approved` to `In Production`. This stage never
creates or edits Pieces; it may only *reference* existing Pieces (if Santiago is tracking the topic
in the Content Hub at all) when proposing clip candidates in the schema.

---

## Scope invariants

1. **No LLM API calls beyond the conversation itself.** No automated scoring — the schema is built
   through dialogue, not inferred silently.
2. **Never invents content** outside `signals_enriched.json`, `discovered_sources.json`, and what
   Santiago contributes in the dialogue.
3. **Never overwrites an existing `schema.md`** for a topic without explicit confirmation.
4. **Output is Markdown, never JSON.** This is a human-facing recording guide, not a machine
   handoff contract.
5. **Does not write a line-by-line script.** That is a distinct, not-yet-implemented future stage.
