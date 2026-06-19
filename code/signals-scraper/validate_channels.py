#!/usr/bin/env python3
"""
validate_channels.py

Resolves a list of 50 YouTube channels via the YouTube Data API v3,
captures canonical metadata, and flags issues. Writes results to
channels_validated.json and prints a markdown summary to stdout.

Usage:
    export YOUTUBE_API_KEY="your_key_here"
    python validate_channels.py
"""

import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

API_KEY = os.environ.get("YOUTUBE_API_KEY")
BASE_URL = "https://www.googleapis.com/youtube/v3"
SLEEP_BETWEEN_CALLS = 0.1
STALE_THRESHOLD_DAYS = 30
SEARCH_CALL_BUDGET = 5  # hard cap on expensive search.list calls
OUTPUT_FILE = "channels_validated.json"

# Quota costs per endpoint (per the YouTube API docs)
COST_CHANNELS_LIST = 1
COST_PLAYLIST_ITEMS = 1
COST_SEARCH_LIST = 100

# AI-niche keyword heuristic for WRONG_NICHE flag
AI_KEYWORDS = {
    "ai", "a.i.", "artificial intelligence", "machine learning", "ml",
    "llm", "gpt", "chatgpt", "claude", "gemini", "agent", "agents",
    "automation", "n8n", "make.com", "no-code", "no code", "nocode",
    "rag", "openai", "anthropic", "prompt", "neural", "transformer",
    "ia", "inteligencia artificial", "automatización", "automatizacion",
    "agentes", "modelo", "modelos",
}

# ---------------------------------------------------------------------------
# Input list — (row, input_name, input_handle, input_tier)
# Use None for handle when we need to search by name (rows 39, 46)
# ---------------------------------------------------------------------------

CHANNELS = [
    # EN Tier 1 — News / Analysis
    (1,  "Matt Wolfe",          "mreflow",                 "EN-Tier1"),
    (2,  "AI Explained",        "aiexplained-official",    "EN-Tier1"),
    (3,  "Wes Roth",            "WesRoth",                 "EN-Tier1"),
    (4,  "Matthew Berman",      "matthew_berman",          "EN-Tier1"),
    (5,  "MattVidPro AI",       "MattVidProAI",            "EN-Tier1"),
    (6,  "Cole Medin",          "ColeMedin",               "EN-Tier1"),
    (7,  "AI Jason",            "AIJasonZ",                "EN-Tier1"),
    (8,  "Two Minute Papers",   "TwoMinutePapers",         "EN-Tier1"),
    (9,  "David Shapiro",       "DavidShapiroAutomator",   "EN-Tier1"),
    (10, "Fireship",            "Fireship",                "EN-Tier1"),

    # EN Tier 2 — Automation / Agents
    (11, "Nate Herk",           "nateherk",                "EN-Tier2"),
    (12, "David Ondrej",        "DavidOndrej",             "EN-Tier2"),
    (13, "Liam Ottley",         "LiamOttley",              "EN-Tier2"),
    (14, "Nick Saraev",         "nicksaraev",              "EN-Tier2"),
    (15, "AI Foundations",      "AI-Foundations",          "EN-Tier2"),
    (16, "Indie Dev Dan",       "indydevdan",              "EN-Tier2"),
    (17, "Riley Brown",         "rileybrownai",            "EN-Tier2"),
    (18, "Jono Catliff",        "jonocatliff",             "EN-Tier2"),
    (19, "Jack Roberts",        "JackRobertsAI",           "EN-Tier2"),
    (20, "The AI Advantage",    "aiadvantage",             "EN-Tier2"),
    (21, "Sabrina Ramonov",     "sabrinaramonov",          "EN-Tier2"),
    (22, "Mervin Praison",      "MervinPraison",           "EN-Tier2"),

    # EN Tier 3 — Engineering / Technical
    (23, "Yannic Kilcher",      "YannicKilcher",           "EN-Tier3"),
    (24, "Andrej Karpathy",     "AndrejKarpathy",          "EN-Tier3"),
    (25, "Sam Witteveen",       "samwitteveenai",          "EN-Tier3"),
    (26, "1littlecoder",        "1littlecoder",            "EN-Tier3"),
    (27, "AI Anytime",          "AIAnytime",               "EN-Tier3"),
    (28, "LangChain",           "LangChain",               "EN-Tier3"),
    (29, "AssemblyAI",          "AssemblyAI",              "EN-Tier3"),

    # EN Tier 4 — Business / Opinion
    (30, "Greg Isenberg",       "GregIsenberg",            "EN-Tier4"),
    (31, "Nate B Jones",        "natebjones",              "EN-Tier4"),
    (32, "Alex Finn",           "alexfinnX",               "EN-Tier4"),
    (33, "AI Search",           "TheAISearch",             "EN-Tier4"),
    (34, "All About AI",        "AllAboutAI",              "EN-Tier4"),
    (35, "Corbin Brown",        "corbinai",                "EN-Tier4"),

    # ES Tier 1 — Anchor channels
    (36, "Dot CSV",             "DotCSV",                  "ES-Tier1"),
    (37, "Dot CSV Lab",         "DotCSVLab",               "ES-Tier1"),
    (38, "Xavier Mitjana",      "XavierMitjana",           "ES-Tier1"),
    (39, "Xavier Mitjana Lab",  None,                      "ES-Tier1"),  # search needed
    (40, "La Hora Maker",       "LaHoraMaker",             "ES-Tier1"),

    # ES Tier 2 — Automation / Agents in Spanish
    (41, "Adrián Sáenz / Divisual Project", "AdrianSaenz", "ES-Tier2"),
    (42, "Víctor Robles WEB",   "VictorRoblesWEB",         "ES-Tier2"),
    (43, "Basdonax",            "Basdonax",                "ES-Tier2"),
    (44, "Imperio Digital IA",  "imperiodigitalmx",        "ES-Tier2"),
    (45, "Benjamín Cordero",    "bencord",                 "ES-Tier2"),
    (46, "Futuro Digital",      None,                      "ES-Tier2"),  # search needed
    (47, "Hub IA Automatización", "hubia-automatizacion",  "ES-Tier2"),

    # ES Tier 3 — Broader Spanish AI
    (48, "Machinelearnear",     "machinelearnear",         "ES-Tier3"),
    (49, "Platzi",              "platzi",                  "ES-Tier3"),
    (50, "EDteam",              "EDteam",                  "ES-Tier3"),
]

# ---------------------------------------------------------------------------
# Quota tracker
# ---------------------------------------------------------------------------

class QuotaTracker:
    def __init__(self):
        self.units = 0
        self.search_calls = 0

    def spend(self, units: int):
        self.units += units

    def can_search(self) -> bool:
        return self.search_calls < SEARCH_CALL_BUDGET

    def record_search(self):
        self.search_calls += 1
        self.spend(COST_SEARCH_LIST)

quota = QuotaTracker()

# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def api_get(endpoint: str, params: dict) -> Optional[dict]:
    """GET wrapper with API key injection and basic error handling."""
    params = {**params, "key": API_KEY}
    url = f"{BASE_URL}/{endpoint}"
    try:
        resp = requests.get(url, params=params, timeout=15)
        time.sleep(SLEEP_BETWEEN_CALLS)
        if resp.status_code == 200:
            return resp.json()
        else:
            sys.stderr.write(
                f"  [HTTP {resp.status_code}] {endpoint} params={params.get('forHandle') or params.get('q') or params.get('id')}: "
                f"{resp.text[:200]}\n"
            )
            return None
    except requests.RequestException as e:
        sys.stderr.write(f"  [ERROR] {endpoint}: {e}\n")
        return None


def resolve_by_handle(handle: str) -> Optional[dict]:
    """channels.list with forHandle. Cost: 1 unit."""
    data = api_get("channels", {
        "part": "snippet,contentDetails,statistics",
        "forHandle": handle,
    })
    quota.spend(COST_CHANNELS_LIST)
    if data and data.get("items"):
        return data["items"][0]
    return None


def resolve_by_search(name: str) -> tuple[Optional[dict], list]:
    """
    search.list fallback. Cost: 100 units.
    Returns (best_match, all_candidates). best_match is None if ambiguous/none.
    """
    if not quota.can_search():
        sys.stderr.write(f"  [BUDGET] search budget exhausted, skipping search for '{name}'\n")
        return None, []

    data = api_get("search", {
        "part": "snippet",
        "q": name,
        "type": "channel",
        "maxResults": 3,
    })
    quota.record_search()
    if not data or not data.get("items"):
        return None, []

    candidates = data["items"]
    # Score each candidate by AI-keyword overlap in title+description
    scored = []
    for c in candidates:
        snip = c.get("snippet", {})
        text = (snip.get("title", "") + " " + snip.get("description", "")).lower()
        score = sum(1 for kw in AI_KEYWORDS if kw in text)
        scored.append((score, c))

    scored.sort(key=lambda x: -x[0])
    top_score = scored[0][0]
    # If top candidate has at least one AI keyword AND outscores the runner-up, take it.
    if top_score > 0 and (len(scored) == 1 or scored[0][0] > scored[1][0]):
        channel_id = scored[0][1]["snippet"]["channelId"]
        # Hydrate with a channels.list call to get full metadata
        full = api_get("channels", {
            "part": "snippet,contentDetails,statistics",
            "id": channel_id,
        })
        quota.spend(COST_CHANNELS_LIST)
        if full and full.get("items"):
            return full["items"][0], candidates
    return None, candidates


def get_last_video_date(uploads_playlist_id: str) -> Optional[str]:
    """playlistItems.list to fetch most recent upload date. Cost: 1 unit."""
    data = api_get("playlistItems", {
        "part": "snippet",
        "playlistId": uploads_playlist_id,
        "maxResults": 1,
    })
    quota.spend(COST_PLAYLIST_ITEMS)
    if data and data.get("items"):
        return data["items"][0]["snippet"].get("publishedAt")
    return None


# ---------------------------------------------------------------------------
# Main processing per channel
# ---------------------------------------------------------------------------

def has_ai_keywords(text: str) -> bool:
    text_l = text.lower()
    return any(kw in text_l for kw in AI_KEYWORDS)


def process_channel(row: int, name: str, handle: Optional[str], tier: str) -> dict:
    print(f"[{row:>2}/50] {name} (@{handle or 'SEARCH'})...", file=sys.stderr)

    result = {
        "row": row,
        "input_handle": f"@{handle}" if handle else None,
        "input_name": name,
        "input_tier": tier,
        "channel_id": None,
        "canonical_title": None,
        "canonical_handle": None,
        "uploads_playlist_id": None,
        "subscriber_count": None,
        "video_count": None,
        "view_count": None,
        "country": None,
        "published_at": None,
        "description": None,
        "last_video_published_at": None,
        "status": "NOT_FOUND",
        "notes": None,
    }

    # STEP 1 — try forHandle
    channel = None
    if handle:
        channel = resolve_by_handle(handle)
        # Cheap retry with lowercase variant before spending search units
        if not channel and handle != handle.lower():
            channel = resolve_by_handle(handle.lower())

    # STEP 2 — fall back to search if needed
    candidates_for_notes = []
    if not channel:
        channel, candidates_for_notes = resolve_by_search(name)
        if not channel and candidates_for_notes:
            # Got results but none confidently match — flag as ambiguous
            top_titles = [c["snippet"]["title"] for c in candidates_for_notes[:3]]
            result["status"] = "AMBIGUOUS"
            result["notes"] = f"search returned: {top_titles}"
            return result
        if not channel:
            result["notes"] = "forHandle and search both returned nothing"
            return result

    # Populate fields
    snip = channel.get("snippet", {})
    stats = channel.get("statistics", {})
    content = channel.get("contentDetails", {})
    uploads_pid = content.get("relatedPlaylists", {}).get("uploads")

    result["channel_id"] = channel.get("id")
    result["canonical_title"] = snip.get("title")
    result["canonical_handle"] = (
        f"@{snip.get('customUrl', '').lstrip('@')}" if snip.get("customUrl") else None
    )
    result["uploads_playlist_id"] = uploads_pid
    result["subscriber_count"] = int(stats["subscriberCount"]) if stats.get("subscriberCount") else None
    result["video_count"] = int(stats["videoCount"]) if stats.get("videoCount") else None
    result["view_count"] = int(stats["viewCount"]) if stats.get("viewCount") else None
    result["country"] = snip.get("country")
    result["published_at"] = snip.get("publishedAt")
    desc = snip.get("description", "") or ""
    result["description"] = desc[:200]

    # STEP 3 — last video date
    if uploads_pid:
        result["last_video_published_at"] = get_last_video_date(uploads_pid)

    # STEP 4 — status
    notes_parts = []

    if candidates_for_notes:
        notes_parts.append("resolved via search.list fallback")

    # Niche check
    haystack = (result["canonical_title"] or "") + " " + desc
    if not has_ai_keywords(haystack):
        result["status"] = "WRONG_NICHE"
        notes_parts.append("no AI keywords in title/description")
    else:
        # Staleness check
        last = result["last_video_published_at"]
        if last:
            try:
                last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
                age_days = (datetime.now(timezone.utc) - last_dt).days
                if age_days > STALE_THRESHOLD_DAYS:
                    result["status"] = "STALE"
                    notes_parts.append(f"last upload {age_days}d ago")
                else:
                    result["status"] = "OK"
            except ValueError:
                result["status"] = "OK"
                notes_parts.append(f"unparseable date: {last}")
        else:
            result["status"] = "STALE"
            notes_parts.append("no uploads found")

    if notes_parts:
        result["notes"] = "; ".join(notes_parts)
    return result


# ---------------------------------------------------------------------------
# Duplicate detection (second pass)
# ---------------------------------------------------------------------------

def mark_duplicates(results: list) -> None:
    seen = {}
    for r in results:
        cid = r.get("channel_id")
        if not cid:
            continue
        if cid in seen:
            r["status"] = "DUPLICATE"
            prior = seen[cid]
            note = f"duplicate of row {prior['row']} ({prior['input_name']})"
            r["notes"] = f"{r['notes']}; {note}" if r["notes"] else note
        else:
            seen[cid] = r


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_summary(results: list) -> None:
    print("\n## Channel Validation Summary\n")
    print("| Row | Channel | Status | Subscribers | Last Video |")
    print("|----:|---------|--------|------------:|------------|")
    for r in results:
        subs = f"{r['subscriber_count']:,}" if r["subscriber_count"] is not None else "—"
        last = r["last_video_published_at"][:10] if r["last_video_published_at"] else "—"
        name = r["input_name"]
        print(f"| {r['row']} | {name} | {r['status']} | {subs} | {last} |")

    needs_attention = [r for r in results if r["status"] != "OK"]
    if needs_attention:
        print(f"\n### Needs manual attention ({len(needs_attention)} channels)\n")
        for r in needs_attention:
            print(f"- **Row {r['row']} — {r['input_name']}** [{r['status']}]: {r['notes'] or '—'}")
    else:
        print("\n_All 50 channels resolved cleanly. ✓_")

    # Status counts
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("\n### Stats\n")
    print(f"- Total processed: {len(results)}")
    for status in ["OK", "STALE", "AMBIGUOUS", "NOT_FOUND", "WRONG_NICHE", "DUPLICATE"]:
        print(f"- {status}: {counts.get(status, 0)}")
    print(f"- Quota units used: **{quota.units}** (of 10,000 daily)")
    print(f"- search.list calls: {quota.search_calls} (of {SEARCH_CALL_BUDGET} budgeted)")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    if not API_KEY:
        sys.stderr.write("ERROR: YOUTUBE_API_KEY env var not set.\n")
        sys.exit(1)

    results = []
    for row, name, handle, tier in CHANNELS:
        try:
            results.append(process_channel(row, name, handle, tier))
        except Exception as e:
            sys.stderr.write(f"  [FATAL on row {row}] {e}\n")
            results.append({
                "row": row,
                "input_handle": f"@{handle}" if handle else None,
                "input_name": name,
                "input_tier": tier,
                "channel_id": None,
                "status": "NOT_FOUND",
                "notes": f"exception: {e}",
            })

    mark_duplicates(results)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print_summary(results)
    sys.stderr.write(f"\n→ Wrote {OUTPUT_FILE}\n")


if __name__ == "__main__":
    main()
