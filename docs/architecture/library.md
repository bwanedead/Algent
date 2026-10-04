# Source library — architecture

> Ohmega's own search index over the sources it trusts. No model anywhere in it. Vision: `docs/vision/ohmega-intelligence-engine.md` ("Sensing"), sibling of `instruments.md` and `statements.md`.
> Code: `backend/algent_backend/library/`. CLI: `newsroom library`.

## Why it exists

Research depended on outside engines' ranking and quotas: a starved agent guesses URLs, and the open web ranks wire brands and SEO above the institution that actually said the thing. The library crawls a curated list of sources we trust (primary institutions, central banks, think tanks, wires and regional outlets across regions and viewpoints, per the spirit's "source spectrum" rule), keeps the text locally in SQLite with a full-text index, and answers searches over it. `web_search` consults it first.

Copyright rule: the index is **internal, for finding and grounding**. Agents and the site receive links and short snippets (FTS5 `snippet()`, ~28 tokens), never republished full texts. Stored text is capped (12,000 chars) and is never served whole by any API in this package.

## Layout

| Module | Role |
|---|---|
| `sources.py` | the registry: `Source` (id, name, domains, kind, region, feeds, note) and `Feed` (url, `rss` or `sitemap`, beat, crawl flag). Canonical — `news_feeds` reads it, and the statements desk's feeds are folded in (`statement_sources()`), not copied |
| `parse.py` | pure: `parse_feed` (RSS/Atom via feedparser), `parse_sitemap` (flat `urlset`, Google News tags `news:title`, `news:publication_date`), `canonical_url` |
| `net.py` | the crawler's network seam: honest user-agent, per-host pacing, robots.txt, conditional GET; injectable for tests |
| `crawl.py` | `crawl(source_ids, max_total, per_source, max_seconds)`: poll, pick new, read, index; returns one report |
| `store.py` | SQLite + FTS5, revisions, crawl state, retention, stats |
| `search.py` | `search(query, days=, kinds=, limit=)` and the ranking |
| `cli/newsroom/library.py` | `crawl`, `search`, `stats` (each prints one JSON document) |

## Registry and kinds

`kind` is one of: `government`, `ministry`, `international_org`, `central_bank`, `statistics_office` (primary record); `think_tank`, `research`, `ngo` (analysis); `wire`, `regional_news` (coverage). The kind sets the ranking weight and the retention tier. `note` says why a source is trusted — and, for state-affiliated outlets (TASS, CGTN, Anadolu, France 24, Al Jazeera), whose voice it is: the spectrum rule wants them labelled and present, not absent.

Verified 2026-10-04 with an honest bot user-agent (fresh items returned):

| Group | Sources |
|---|---|
| International orgs | UN News, ReliefWeb, UN OCHA, IAEA (top news), ICRC, WTO, UN press meetings (statements catalog), European Commission press corner (statements catalog) |
| Central banks | Federal Reserve press + speeches, ECB press, Bank of England news + speeches, Bank of Japan, BIS central-bank speeches |
| Governments / ministries | UK MoD, UK FCDO, UK PMO, White House, Kremlin (transcripts + news), US EIA Today in Energy |
| Think tanks / research / NGOs | Atlantic Council, War on the Rocks, Lowy Interpreter, Bellingcat, Human Rights Watch, Amnesty |
| Wires / broad outlets | Al Jazeera (rss + news sitemap), BBC (3 rss + news sitemap), Guardian (rss + news sitemap), DW, France 24, NPR, Anadolu, TASS, CGTN, Yonhap, ABC Australia |
| Regional | Kyiv Independent (rss + sitemap), Al-Monitor, Middle East Eye, Jerusalem Post, Arab News, Moscow Times, Meduza, Politico Europe, SCMP, The Hindu (rss + sitemap), Dawn, CNA, Straits Times, Japan Times, Taipei Times, The Diplomat, Africanews, allAfrica, Premium Times, Daily Maverick, MercoPress |
| Listed, not indexed | NYT World/Business (paywalled; readable by `rss_feed` only) |

Probed and **not** in the registry (reason as observed; retry later, add as one line in `sources.py`):

| Source | Observation |
|---|---|
| IMF, UNHCR, Chatham House, RAND, IISS, ECFR, MoFA Japan, OECD, UNCTAD, Euractiv, Times of Israel, Haaretz, AP, IAEA press-releases feed | HTTP 403 to the honest bot user-agent (several serve a browser UA; we do not impersonate one for feeds) |
| World Bank, Brookings, Carnegie, EEAS, ISW, Iran International, India MEA, Korea Herald, RFE/RL, RNZ | URL answers 200 but not a feed (HTML or empty); no working feed URL found |
| BIS press, NATO, CSIS, CFR, SIPRI, FAO, WFP, IEA, TRT World, ORF, MERICS, Focus Taiwan | HTTP 404 on every known feed URL |
| WHO, NHK World, Xinhua, Global Times | feed alive but stale (newest item months/years old) |
| Treasury (kept, flaky), DW/SCMP sitemaps | Treasury times out intermittently; DW and SCMP publish no news sitemap at the tried URLs |

Registry entries that fail at crawl time are kept, not hidden. Seen in the first live crawl: Crisis Group, defense.gov, consilium.europa.eu and state.gov answer 403 to robots.txt for the bot agent (treated as closed, like `urllib.robotparser`), and Treasury times out. They are recorded in `stats`, parked after repeated failure and retried weekly.

## Crawl politeness and bounds

- **Identity**: feeds, sitemaps and robots.txt are fetched as `OhmegaLibraryBot/0.1 (...; honours robots.txt; low volume)`. Page text is read by the repo's shared free reader (`fetch_content._fetch(url, allow_paid_fallback=False)`, one extraction ladder for everything), which sends browser-style headers; it is only reached after robots.txt clears the URL. See open questions.
- **robots.txt**: fetched once per host per run and honoured for every feed and page URL. A 401/403 on robots.txt closes the host for the run (as `urllib.robotparser` does), 404 opens it, 5xx or timeout closes it for the run. A disallowed page is parked; an unreachable robots.txt only counts as a failure. `Crawl-delay` is honoured up to 10 s.
- **Pacing**: at least 2 s between requests to one host.
- **Conditional GET**: ETag / Last-Modified are stored per feed and sent back. They are saved only once that source's backlog is fully read, so a 304 can never hide unread items.
- **Bounds per run**: `--max` pages overall (default 120), `--per-source` pages per source (default 6), 900 s wall clock. Pages are read round-robin across sources, so a small cap still samples every outlet. Pending items beyond the cap are picked up on later runs while they are still in the feed. No daemon: run `newsroom library crawl` by hand or from a scheduler (a few times a day is plenty).
- **Idempotent**: a URL already indexed is skipped unless the feed's own updated/lastmod stamp changed; then the page is re-read and, if the text differs, stored as a new revision.
- **Failures** are recorded, never raised. A feed failing 4 times in a row is parked for 7 days; a page failing 3 times is parked for good (no retry); non-text URLs (xlsx, pdf, media) are skipped. If a page will not read but its feed carried a summary of at least 15 words, the summary is indexed (`via=feed_summary`) so the item is still findable.
- **Free only**: no paid fallback, no model call.

## Store and retention

`library_store/library.db` under the working directory, or `$ALGENT_LIBRARY_STORE` (relative paths resolve from the working directory, like `instruments_store`). Git-ignore it (the lead wires `.gitignore` / backups).

Tables: `documents` (all kept revisions; `latest=1` is what search sees), `docs_fts` (FTS5, external-content over `title`+`text`, porter + unicode61 tokenizer, latest revisions only so text is stored once), `feed_state` (validators, failures, parked_until), `page_failures`.

Documents are append-only: a changed page is a new row (`revision+1`) and the previous one stops being `latest`; an unchanged re-read changes only the stamp. Only retention deletes.

**Size budget**: `MAX_DB_BYTES` = 400 MB. Text is capped at 12,000 chars per page (the lead and body of an article; enough to find a page by its content). At about 300 pages a day that is roughly 3 MB/day including the index.

**Retention rule** (`store.enforce_retention`, run at the end of every crawl):

1. superseded revisions are dropped after 14 days;
2. a page is dropped when older than its tier's age limit (by published date, fetch date if none): news (wire, regional_news) 90 days, analysis (think tanks, research, NGOs) 365 days, primary (government, ministries, international orgs, central banks, statistics offices) 730 days;
3. if live data still exceeds the budget, the oldest pages go first, news before analysis before primary, until the db is under 90% of the budget.

## Search and ranking

`search(query, *, days=None, kinds=None, limit=10)` returns dicts with `title, url, source, kind, published, snippet`.

`score = relevance * kind_weight * recency`

- `relevance`: FTS5 `bm25` with the title weighted 5x the text, sign flipped. It is the only query-dependent term, so the others are multipliers: they re-order near-equal matches without letting a fresh press release outrank a page that really answers the question.
- `kind_weight`: primary kinds 1.5, analysis kinds 1.2, wire/regional news 1.0. On equal relevance the primary record wins; a clearly better-matching news page still beats a weak primary one.
- `recency`: `0.5 ** (age_days / 30)`, floored at 0.3 so an old primary document stays findable. Age is the published date.

No hard gates: nothing is dropped for being old or low-weight; `days` and `kinds` are the caller's explicit filters. The constants live at the top of `search.py` and are tuning surfaces, not rules. Query handling: words are AND-ed; if that yields fewer than `limit` hits, pages matching only some words top the list up after the all-words matches. `"quoted phrases"` are kept, `site:host` restricts to a domain (the same idiom `web_search` teaches the agent), FTS syntax characters in a query are inert. A missing store returns `[]` and creates nothing.

## `web_search` integration

For `kind="keyword"` and `kind="news"`, `_search_web` asks the library first (up to 5 hits, free, local). If it has hits, the answering engine's results are returned with the library hits **first**, each marked `provider: "library"` with `source`, `source_kind`, `published` and a snippet in `content`; the response also carries `library_hits` and `library_style` (a `_PROVIDER_STYLE`-like note: these are our curated, dated sources, the snippet is a pointer, `read_url` the hit to cite it). The top-level `provider` / `provider_style` still describe the external engine. If every external engine fails but the library answered, the library hits are returned alone (`provider: "library"`, `external_search_unavailable` names the errors). If the library has nothing, errors, or does not exist, the response is exactly what it was. Semantic, scholar, read and X paths are untouched; the library never touches the cost meter.

## Adding a source

One entry in `sources.py` (`SOURCES`): `_s(id, name, domain, kind, region, feed, note)`, or pass a tuple of `_rss(...)` / `_map(...)` feeds (a `_map` is a flat Google-News-style sitemap; sitemap indexes are not followed, point at the child). Probe it first: `python -c` a GET with the bot user-agent, confirm a 200 with fresh items. Statement-desk feeds stay in the statements catalog and are mapped to a kind in `_STATEMENT_KINDS`. Then `newsroom library crawl --source <id>` and `newsroom library search "<a headline you saw there>"`.

## CLI

```
newsroom library crawl [--source ID ...] [--max N] [--per-source N]
newsroom library search "<query>" [--days N] [--kind KIND ...] [--limit N]
newsroom library stats
```

`stats`: documents per source with newest published and last fetch, failing feeds (with error and parked_until), failing/parked pages per source, live and file bytes against the budget.

## Tests

`backend/tests/test_library_{parse_net,store_search,crawl_websearch}.py` — offline: captured real UN News and Federal Reserve feeds and a Kyiv Independent news sitemap (`tests/fixtures/library/`), robots refusal and pacing, validators, idempotent crawl, revisions, parking, summary fallback, round-robin caps, ranking order, retention, and the `web_search` merge / fall-through.
