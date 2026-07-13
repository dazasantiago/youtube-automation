# Claude Code rules — schema-builder

## Purpose

This stage is the **structural planning + release-decision layer** between deep research and
production. It reads `digest.md` (produced by the `research-digest` subagent from a single
already-researched topic), negotiates with Santiago **which content pieces actually get made** —
long-form, shorts, text posts, in whatever mix fits the topic, not a fixed set per social network —
and then builds the schema for each approved piece: central thesis/angle (shared), and per piece a
hook/structure (long-form) or a lighter angle/points/hook (shorts, text).

Approving the schemas **is** approving the release plan. Once approved, this stage creates the Topic
and its Pieces directly in Notion, `In Production`.

This stage is executed by Claude invoking the `schema-builder` skill. It is not a Python project —
no runnable package, no scripts. The skill lives at `.claude/skills/schema-builder/SKILL.md`.

**This is not a line-by-line script, and it is not a machine-readable artifact.** The output is a
single Markdown document meant for Santiago to read while recording/writing — not JSON for another
stage to parse. A future stage (not implemented yet) would take this schema and produce the
word-for-word script.

---

## Pipeline position

```
topic-deep-research → research-digest → schema-builder → Notion (Topic + Pieces, In Production)
results/<week>/<slug>/   digest.md         (this stage)   data/<week>/<slug>/schema.md
```

`research-digest` (`.claude/agents/research-digest.md`) is a subagent Claude always invokes right
after `topic-deep-research` finishes for a topic — it's not something Santiago triggers by name.

---

## How to run this stage

### Prerequisites

- `topic-deep-research` must have already run for the topic, and `research-digest` must have
  produced `code/topic-deep-research/results/<YYYY-WNN>/<slug>/digest.md`. If the digest is missing
  but the raw JSON exists, this stage invokes `research-digest` itself before continuing.
- Notion MCP connector active in the session — required for Phase 5 (creating the Topic + Pieces).
  The dialogue and schema-writing phases work without it.

### Invoke the skill

Trigger the skill with any phrase like:

- "armemos el esquema del video de \<tema\>"
- "qué piezas sacamos de \<tema\>"
- "estructura del video"
- "esqueleto del guion"

The `schema-builder` skill auto-triggers on these phrases. No slash command needed.

### What the skill does (phases)

1. **Preconditions** — `git pull`; resolves which topic (asks if ambiguous, listing
   `code/topic-deep-research/results/*/*/`); confirms `digest.md` exists (runs `research-digest` if
   missing but raw JSON is there); checks for an existing schema for that topic before overwriting.
2. **Read the digest** — internalizes `digest.md` (already condensed by `research-digest`, not
   reprocessed here).
3. **Negotiate the piece mix** — asks Santiago's own read first, then proposes which pieces get
   made (long-form + obligatory shorts + something on X as the common default for a meaty topic;
   shorts-only or text-only for a thinner one), using the digest's depth read. No fixed set.
4. **Dialogue per piece** — shared angle/thesis once, then per approved piece: full
   hook/sections/closing for long-form, lighter angle/points/hook for shorts and text pieces.
5. **Write output** — a single `code/schema-builder/data/<YYYY-WNN>/<slug>/schema.md` with a leading
   "Piezas aprobadas" section.
6. **Notion creation** — creates the Topic (`Status: In Production`) and one Piece per approved
   item, after confirming with Santiago.
7. **Summary** — reports the file path, approved piece list, and the Notion Topic + Piece URLs.

---

## Files in this folder

| File / Folder | Purpose |
|---|---|
| `STAGE.md` | This file — stage documentation |
| `data/example/schema.md` | Reference example of the exact output shape |
| `data/<YYYY-WNN>/<slug>/schema.md` | The schema/plan for one topic — committed |

The active skill is at: `.claude/skills/schema-builder/SKILL.md`
The upstream digest agent is at: `.claude/agents/research-digest.md`

`data/example/` is a reference fixture, not a real run — never delete it.

---

## Outputs produced

| Output | Location | Committed? |
|---|---|---|
| `schema.md` | `code/schema-builder/data/<YYYY-WNN>/<slug>/schema.md` | Yes — terminal artifact of this stage, same convention as `topic-deep-research/results/` |
| Topic (`Status: In Production`) + its Pieces | Content Hub (Notion, cloud) | N/A — created once schemas are approved |

`<YYYY-WNN>` and `<slug>` are **reused as-is** from the `topic-deep-research/results/` folder being
read — this stage never invents a new week label or slug.

There is deliberately **no JSON artifact**. This stage's output is for Santiago to read while
recording/writing, not for another automated stage to consume — see
[`data/example/schema.md`](data/example/schema.md) for the exact shape.

---

## `schema.md` shape

```markdown
# <Título> — Plan de contenido

**Semana:** 2026-W28 · **Slug:** hyperframes · **Generado:** 2026-07-09

## Piezas aprobadas
- 🎥 YouTube (Long Form)
- 📱 YouTube Shorts × 3 (Short Form)
- 𝕏 X (Text Post)

## Ángulo / tesis general
...

---

## 🎥 YouTube — Long Form

### Hook (apertura)
...

### Estructura

#### 1. <Título de sección> (media)
- idea clave
- idea clave

**Fuentes:** hn:47797513, discovered:https://hyperframes.app

### Contrapuntos
- ...

### Cierre
...

---

## 📱 YouTube Shorts #1
**Ángulo:** ... (o "extraído de la sección 2 del long-form")
**Puntos clave:** ...
**Fuentes:** ...
**Hook:** ...

---

## 𝕏 X
**Idea central:** ...
**Puntos de apoyo:** ...
**Fuentes:** ...
**Gancho (primera línea):** ...

---

## Preguntas abiertas / huecos
- ...
```

`Fuentes` entries reuse the `source:source_id` format as they appear in `digest.md` (`hn:47797513`,
`yt:RuhhLUfTXrY`), and `discovered:<url>` for entries that came from `discovered_sources.json` (no
`source_id` there).

---

## Notion Content Hub reference

Touches both databases in the Content Hub:

- **Topics** (`data_source_id: 206658fc-5314-417f-ad4b-f114d26deacd`) — creates the Topic directly
  in `Status: In Production` (there's no separate "Approved" step anymore — approving the schemas is
  the approval). Sets `Title`, `Content Type`, `Week`, `Notes`.
- **Pieces of Content** (`data_source_id: fb77522a-56b8-46b1-bf53-c0e3d836d9ae`) — creates one Piece
  per approved item from the mix (dynamic set, no fixed 6), each `Status: Pending`, `Topic` relation
  pointing back to the Topic just created, `Platform`/`Format`/`Short Form Type` matching the piece.

This stage **creates** these pages (it does not just reference or status-flip existing ones, unlike
the previous version of this stage).

---

## Scope invariants

1. **No LLM API calls beyond the conversation itself.** No automated scoring — the schema and the
   piece mix are built through dialogue, not inferred silently.
2. **Never invents content** outside `digest.md` and what Santiago contributes in the dialogue.
3. **Never overwrites an existing `schema.md`** for a topic without explicit confirmation.
4. **Never assumes a fixed set of pieces.** The mix is always negotiated in Phase 3, even when a
   long-form + shorts + X default is the common starting proposal.
5. **Output is Markdown, never JSON.** This is a human-facing recording/writing guide, not a machine
   handoff contract.
6. **Does not write a line-by-line script.** That is a distinct, not-yet-implemented future stage.
7. **Notion creation requires explicit confirmation** before writing, same as any other
   creation/change in this repo's Notion conventions.
