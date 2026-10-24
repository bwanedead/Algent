"""
Site smoke-test knobs (in-repo, no ``.env``). The checker (``run.py``) asks a deployed site - production or a preview - for every route the product
registry lists, a sample of its dynamic routes and the agent API, and judges what comes back. Each number says why it is that number.
"""

from __future__ import annotations

#: The production site; ``newsroom site smoke`` without ``--base`` checks this (the hourly ``site-smoke`` job).
PRODUCTION_BASE = "https://www.ohmega.monster"
#: Cloudflare and Vercel answer 403 to urllib's default agent, so the checker names itself.
USER_AGENT = "ohmega-smoke/1.0 (+https://www.ohmega.monster/developers)"
#: One request may take this long before it counts as failed (a cold ISR render of the biggest view is a few seconds).
TIMEOUT_S = 25.0
#: A page slower than this is a warning (the response time is always in the report).
SLOW_MS = 6000
#: Pause between requests: /api/v1 is rate limited to a burst of 40 and 120 a minute per client (lib/api/ratelimit.ts); a run makes ~20 API calls.
PACE_S = 0.25
#: A product is late when its freshness stamp is older than this many of its own cadences (the registry's shortest job interval): the timers can slip a
#: cycle, so one missed run is not late, three are. (A bare-day stamp is read the way the site reads it: from the start of today.)
FRESH_CADENCES = 3
#: How many dynamic pages to sample per route template and group (a group is the template's parent path: one sample per desk, per kind).
SAMPLES_PER_GROUP = 1
MAX_GROUPS = 3
#: The entity the agent endpoints are asked about: it must resolve in any corpus (a country the dailies cover every day).
ENTITY_PROBE = "Iran"
#: A page that shows one of these where data must exist is a failure: the fallback copy the site renders for "not published". Matched case-insensitively
#: against the page text. Error pages and Next's own failure markers are in the second group.
FALLBACK_PATTERNS = (
    r"not (yet )?been published", r"been published yet", r"not published yet", r"nothing (has been )?published", r"could not be found",
    r"no report published",
    r"application error", r"internal server error", r"this page could not be found",
)
#: Routes where the fallback copy is a legitimate state (listed by exact path, with the reason). Empty: a fallback on production is a finding.
MAY_BE_EMPTY: dict[str, str] = {}
#: Retired routes that must keep redirecting, to exactly this place (next.config.mjs).
REDIRECTS = (("/geopolitics", "/daily/geopolitics"), ("/ai", "/daily/ai"), ("/headlines", "/daily/headlines"), ("/radar", "/daily/headlines"),
             ("/intel/theaters", "/situations"), ("/intel", "/explore"), ("/data", "/explore"))
#: Freshness probes on the agent API: (path template, registry product whose cadence applies, severity of lateness). ``{desk}`` runs over the desks.
FRESHNESS = (("/api/v1/daily/{desk}/latest", "dailies", "fail"), ("/api/v1/track-record", "markets", "warn"), ("/api/v1/sanctions", "sanctions", "warn"),
             ("/api/v1/calendar", "calendar", "warn"), ("/api/v1/ai-benchmarks", "ai_benchmarks", "warn"))
#: Products whose liveness is judged from their published status file (``ops/status.py``: ``checked_at``, the end of their last successful run) instead of the
#: ``as_of`` of their data: a product with nothing new to say (no new sanctions designation) keeps an old ``as_of`` while its job runs fine, so ``as_of`` is
#: only the fallback while no status file is published yet. Dailies are not here on purpose: a missing report is a failure whatever the job did.
STATUS_JUDGED = ("markets", "sanctions", "calendar", "ai_benchmarks")
#: Pages that also carry a visible stale marker (components/Fresh.tsx renders ``is-stale``): seeing it there is a warning.
STALE_MARKER_PAGES = ("/", "/daily", "/situations", "/explore")
#: The state file's neighbours: the checker keeps the last report here so the doctor row and the ops-log transitions can read it.
STATE_FILE = "site_smoke.json"
#: The doctor row warns when the last run is older than this many hours (the job is hourly).
STATE_STALE_H = 3.0
