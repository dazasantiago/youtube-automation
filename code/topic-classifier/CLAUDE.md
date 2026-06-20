# Claude Code rules — topic-classifier

## Purpose

This stage takes a week's worth of raw signals (scraped by `signals-scraper`) and groups
them into **emerging topics** that represent what the AI/tech space is discussing. The output
drives which topics get deep-researched and eventually turned into YouTube videos.

This stage is executed by Claude reading `prompt.md` as an instruction set — it is not a
Python project. There is no runnable package here, only a prompt and a post-processing script.

---

## Pipeline position

```
signals-scraper  →  topic-classifier  →  topic-deep-research
   intel.db            topics-YYYY-WNN.json   <slug>.json
   handoff.json        topic_inputs/
```

---

## How to run this stage

### Step 1 — Generate signals export

The signals-scraper must have run recently. Its outputs are at:
- `code/signals-scraper/data/handoff.json` — minimal flat list of `{id, title, url}` used as classifier input
- `code/signals-scraper/data/intel.db` — SQLite DB used by `build_topic_inputs.py` to resolve signal IDs

If they are stale, run the export manually from the signals-scraper project:
```bash
uv run --project code/signals-scraper content-intel export
```

### Step 2 — Run the classifier (Claude prompt)

Give Claude the contents of `prompt.md` as instructions. Claude will:
1. Read `code/signals-scraper/data/handoff.json`
2. Group signals into topics following the rules in the prompt
3. Write `code/topic-classifier/data/topics-YYYY-WNN.json` (e.g. `topics-2026-W26.json`)

### Step 3 — Build per-topic input files

```bash
python code/topic-classifier/build_topic_inputs.py code/topic-classifier/data/topics-YYYY-WNN.json
```

This resolves signal IDs from `topics.json` against `intel.db` and writes one JSON per topic
to `code/topic-classifier/data/topic_inputs/`. **This folder is cleared on every run** —
previous week's files are always replaced.

### Step 4 — Run deep research on a topic

```bash
uv run --project code/topic-deep-research deep-research \
  --input code/topic-classifier/data/topic_inputs/<slug>.json
```

---

## Files in this folder

| File / Folder | Purpose |
|---|---|
| `prompt.md` | Instruction set for Claude — defines input, classification rules, output schema, and post-processing step |
| `build_topic_inputs.py` | Stdlib Python script — resolves signal IDs against `intel.db` and writes `topic_inputs/` |
| `data/topics-YYYY-WNN.json` | Weekly output of the Claude classifier — one file per run, never overwritten |
| `data/topic_inputs/<slug>.json` | One file per topic in the format expected by `topic-deep-research` |

`data/` is gitignored. Do not commit output files.

---

## Classification rules (summary)

Full rules live in `prompt.md`. Key decisions:

- **Domain filter**: only AI, automation, developer tools, tech industry. Off-domain signals are
  discarded entirely — not even added to `uncategorized`.
- **Minimum 2 signals** to form a topic. Single-signal items go to `uncategorized`.
- **Specificity**: "AI Agents" is too broad. "Claude Computer Use" is good.
- **Each signal belongs to exactly one topic.**
- **Signal strength hierarchy** (strongest → weakest):
  1. `yt_competitor_videos` with `outlier_ratio ≥ 2.0` — a competitor video is already viral
  2. `hn`, `reddit`, `x_apify` — community engagement
  3. `rss`, `product_hunt`, `github_trending`, `hf` — product/launch signals
  4. `gtrends` — search interest, weak corroboration only
  5. `yt_underperformer_videos` with `outlier_ratio < 0.5` — anti-signal (topic flopped on YT)

**Strongest content opportunity**: `has_viral_yt: true` + signals from 3+ distinct sources.

---

## Signal ID format

The classifier references signals as `source:id`:

| Prefix | Table in DB | Example |
|---|---|---|
| `hn` | `signals` | `hn:48567759` |
| `reddit` | `signals` | `reddit:r_LocalLLaMA_1u8ai2a` |
| `x_apify` | `signals` | `x_apify:jietang_206578475` |
| `rss` | `signals` | `rss:anthropic-blog-2026-06-10` |
| `github_trending` | `signals` | `github_trending:modelcontextprotocol-servers` |
| `hf` | `signals` | `hf:zai-org-GLM-5.2` |
| `product_hunt` | `signals` | `product_hunt:some-tool` |
| `gtrends` | `signals` | `gtrends:ai_coding_assistants` |
| `yt` | `yt_videos` | `yt:RuhhLUfTXrY` |
| `yt_under` | `yt_videos` | `yt_under:Nn7EbMJRRGo` |

`build_topic_inputs.py` uses these prefixes to route queries between the `signals` and
`yt_videos` tables in `intel.db`.

---

## Output schema (`topics-YYYY-WNN.json`)

```json
{
  "generated_at": "2026-06-19T14:00:00Z",
  "window_days": 7,
  "topics": [
    {
      "topic": "GLM 5.2 Open Weights Release",
      "rationale": "One sentence explaining why this is trending this week.",
      "signal_count": 11,
      "has_viral_yt": true,
      "has_yt_flop": false,
      "sources": ["hn", "reddit", "x_apify", "hf", "yt_competitor_videos"],
      "signal_ids": ["hn:48567759", "yt:RuhhLUfTXrY", "..."]
    }
  ],
  "uncategorized": ["gtrends:some_query", "..."]
}
```

Topics are sorted by `signal_count` descending.

---

## `build_topic_inputs.py` behavior

- **Input**: `data/topics-YYYY-WNN.json` (passed as arg, or auto-resolved to most recent) + `../signals-scraper/data/intel.db`
- **Output**: `data/topic_inputs/<slug>.json` per topic
- **Weekly overwrite**: deletes and recreates `data/topic_inputs/` on every run
- **Missing signals**: IDs not found in DB are reported on stdout but don't abort the run
- **yt videos**: `outlier_ratio < 0.5` → role `"saturator"`, otherwise `"signal"`
- **No external dependencies**: pure Python stdlib, runs with any `python3`
