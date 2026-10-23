"""
View knobs (in-repo, no ``.env``). A view is a small, versioned JSON document the server builds so that no page and no agent has to aggregate raw
documents at request time (docs/architecture/views.md). Every list in a view is capped, every cap has its reason here, and every family has a byte
budget the build refuses to exceed (an over-budget view is not uploaded: the last good one stays, and the build says so).
"""

from __future__ import annotations

#: Documents are published through ``publishing/object_docs`` under ``docs/<path>.gz``; the views live under this document prefix.
PREFIX = "views"
SCHEMA = "ohmega.view.{name}/1"

# ── byte budgets (uncompressed canonical JSON; ~5-8x smaller gzipped) ─────────────────────────────────────────────────────────────────────
#: Why each number: what the page it feeds can actually show, with headroom of ~2x over the measured fat case in tests/test_views_*.py.
BUDGET_BYTES = {
    "country": 160_000,        # panel stats + 120 briefs (~250 B) + context + 50 sanctions rows + 10 calendar + grid + series
    "situation": 600_000,      # newest 3 full Daily sections (each up to ~120 KB with its map) + a compact index of every other day
    "situations": 150_000,     # one slim row (+ 21-day strips) per situation, a few dozen situations
    "entity": 60_000,          # profile + 15 documents + 10 claims + 15 events + 12 relations + 12 series of <=24 points
    "event": 60_000,           # the developments of one theater-day (<= ~12 developments of a few hundred bytes)
    "home": 200_000,           # two trimmed desk reports (trackers, no map/visual specs) + moving situations + facts
    "hud": 300_000,            # globe rows for ~250 countries + report block + theaters + pulses + calendar + sanctions + trader curve
    "daily-hub": 60_000,       # per desk: 12 section rows + a date list
    "graph": 80_000,           # theater refs + state names + theater-state ties
    "search-index": 2_000_000,  # entity names/aliases + document titles; the client searches it in memory
    "manifest": 200_000,       # the list of every published view key with size and hash
}

# ── caps (every list says how many it keeps, and the view carries `total` when it was cut) ───────────────────────────────────────────────────
COUNTRY_BRIEFS = 120           # briefs a country's history keeps (30 days x ~4/day); the panel scrolls, older ones are in the Dailies
COUNTRY_SANCTIONS = 50
COUNTRY_CALENDAR = 10
COUNTRY_RELATED = 30
COUNTRY_DEVELOPMENTS = 6       # the actor page's "recent developments" (the page shows 6)
COUNTRY_SAID = 5
SERIES_PER_ENTITY = 12
SERIES_POINTS = 24             # yearly indicators: 24 years; daily series: ~3 weeks of sparkline
STREAM_FULL_DAYS = 3           # newest days of a situation stream sent as full Daily sections; older days are index rows linking into the Daily
STREAM_INDEX_DAYS = 400        # index rows kept per situation (a year and more of daily coverage)
ENTITY_DOCS = 15               # newest documents mentioning the entity (an agent asks `about` with a window for more)
ENTITY_CLAIMS = 10
ENTITY_EVENTS = 15
ENTITY_RELATED = 12
EVENT_DEVELOPMENTS = 40
HUD_DAILY_ITEMS = 10
HUD_PULSES = 12
HUD_HISTORY_POINTS = 30
HUD_COMING_DAYS = 14
HUD_COMING = 10
HUD_SANCTIONS = 10
HUD_TIES_PER_THEATER = 6
HUD_CURVE_DAYS = 90
HUD_POSITIONS = 6
GLOBE_DAILIES = 21             # dailies the globe's theme tally reads (7-to-30-day band); unchanged from the page it replaces
GRAPH_REFS = 300               # theater refs the graph keeps (heaviest ties first); the pages show tens
SEARCH_ENTITIES = 6000         # entities with substance (>= SEARCH_MIN_USES uses) in the search index
SEARCH_MIN_USES = 3
SEARCH_DOCUMENTS = 4000        # newest document titles
SEARCH_ALIASES = 4

# ── desks: the site's mirror of the backend registry; tests/test_views_desks.py compares it with sites/ohmega-monster/lib/desks.ts ─────────────
DESKS = (
    {"id": "geopolitics", "domains": ("geopolitics",), "catch_all": True},
    {"id": "ai", "domains": ("ai", "technology"), "catch_all": False},
)
#: A situation with nothing new for this many days is quiet (agents/intel/focus.py FOCUS_DROP_DAYS; lib/situations.ts QUIET_AFTER_DAYS).
QUIET_AFTER_DAYS = 7
GLOBE_DOMAIN = "geopolitics"

# ── the one rule for a country brief's theme (ported from lib/globe/themes.ts + lib/visual.ts categoryOf; tests/test_views_themes.py) ──────────
HALF_LIFE_DAYS = 7.0
