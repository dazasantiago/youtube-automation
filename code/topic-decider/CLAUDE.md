# Claude Code rules — topic-decider

## Purpose

This stage is the **editorial decision layer** between classification and deep research. It reads
the classified topics from `topic-classifier`, cross-references them against the Notion Content Hub
(to avoid repeating already-approved topics), and runs a dialogue with Santiago to decide which
topics are worth producing this week.

Once a topic is approved, this stage:
1. Creates a Topic entry (`Approved`) + 6 platform Pieces (`Pending`) in the Notion Content Hub.
2. Generates a standalone JSON input file for `topic-deep-research` — one file per approved topic.
3. Optionally executes `topic-deep-research` immediately on the chosen topic.

This stage is executed by Claude invoking the `topic-decider` skill. It is not a Python project —
no runnable package, no scripts. The skill lives at `.claude/skills/topic-decider/SKILL.md`.

---

## Pipeline position

```
signals-scraper  →  topic-classifier  →  topic-decider  →  topic-deep-research
   intel.db            topics-YYYY-WNN.json  (this stage)     data/<slug>.json
   handoff.json        topic_inputs/         Notion Hub        results/<week>/<slug>/
```

---

## How to run this stage

### Prerequisites

- At least one `code/topic-classifier/data/topics-YYYY-WNN.json` must exist (run `topic-classifier` first). The skill reads the most recent one.
- `code/signals-scraper/data/intel.db` must exist (used by `build_topic_inputs.py` to resolve signals).
- Notion MCP connector must be active in the session (claude.ai or Claude Code with Notion integration).

### Invoke the skill

Trigger the skill with any phrase like:

- "revisemos los topics de la semana"
- "qué temas valen la pena esta semana"
- "decidamos los temas"
- "aprobar temas para deep research"

The `topic-decider` skill auto-triggers on these phrases. No slash command needed.

### What the skill does (phases)

1. **Preconditions** — reads the most recent `topics-YYYY-WNN.json`; fetches existing topics from Notion to detect duplicates.
2. **Ranking table** — scores and ranks every topic (viral YT + signal count + source diversity −
   flop penalty); presents a table with a recommendation.
3. **Dialogue** — discusses signal strength and overlap until Santiago approves one or more topics.
4. **Per approved topic**:
   - Creates Topic (`Approved`) + 6 Pieces (`Pending`) in Notion.
   - Runs `python code/topic-classifier/build_topic_inputs.py` and copies the relevant
     `<slug>.json` to `code/topic-deep-research/data/<slug>.json`.
5. **Summary** — reports Notion entries created and input files written.
6. **Execute deep research** — offers to run `topic-deep-research` immediately on the strongest
   approved topic; executes it if confirmed.

---

## Files in this folder

| File | Purpose |
|---|---|
| `CLAUDE.md` | This file — stage documentation |
| `content-hub-manager.skill` | Reference copy of the Notion Content Hub skill (read-only; not modified by this stage) |

The active skill is at: `.claude/skills/topic-decider/SKILL.md`

---

## Outputs produced

| Output | Location | Committed? |
|---|---|---|
| Topic + 6 Pieces in Notion | Content Hub (cloud) | N/A |
| Deep-research input (one per topic) | `code/topic-deep-research/data/<slug>.json` | No (`data/*.json` is gitignored) |
| Deep-research results (if executed) | `code/topic-deep-research/results/<YYYY-WNN>/<slug>/` | Yes |

---

## Scoring / ranking logic (summary)

Full rules live in `.claude/skills/topic-decider/SKILL.md`. Key formula:

```
score = signal_count
        + 100  (if has_viral_yt)
        + 10 × distinct_sources
        − 50   (if has_yt_flop and NOT has_viral_yt)
```

Strength labels (first match wins):
- 🔥 **Fuerte** — `has_viral_yt` and `distinct_sources ≥ 3`
- ⚠️ **Saturado/Flop** — `has_yt_flop` and not `has_viral_yt`
- ✅ **Sólido** — `score ≥ 50`
- 🟡 **Medio** — everything else
- 🔻 **Débil** — `distinct_sources ≤ 1` or `score < 20`

Signal quality hierarchy (strongest → weakest):
1. `yt_competitor_videos` viral (`outlier_ratio ≥ 2.0`)
2. `hn`, `reddit`, `x_apify` — community engagement
3. `rss`, `product_hunt`, `github_trending`, `hf` — product/launch
4. `gtrends` — search interest, weak corroboration only
5. `yt_underperformer_videos` — anti-signal (topic flopped on YouTube)

---

## Notion Content Hub reference

Two linked databases inside **🎬 Content Hub**:

| Database | collection ID | Used for |
|---|---|---|
| Topics | `206658fc-5314-417f-ad4b-f114d26deacd` | One entry per approved topic |
| Pieces of Content | `fb77522a-56b8-46b1-bf53-c0e3d836d9ae` | 6 platform pieces per topic |

Six pieces are created per topic: 🎥 YouTube (Long Form) · 📱 YouTube Shorts · 🎵 TikTok ·
📸 Reels (Short Form) · 𝕏 X · 💼 LinkedIn (Text Post). All start as `Pending`.

Full property schemas and creation payloads are in `.claude/skills/topic-decider/SKILL.md`.
