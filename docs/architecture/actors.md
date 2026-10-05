# Actors (power profiles of states)

The desk shows news; it never showed WHAT each power is. Actors answers that with numbers: people,
economy, trade, energy, military and leadership of each state, from free open-licence sources, so a
reader (and a writer) can build a model of every actor in a story. Vision:
`docs/vision/ohmega-intelligence-engine.md` ("Depth: from dashboard to model").

Code: `backend/algent_backend/actors/` (no model anywhere). CLI: `newsroom actors`. Publish:
`publishing/actors_feed.py`. Site: `/intel/actors`, `/intel/actors/[iso]`, and the theater dossier's
"Actors" strip. Sibling layers: `instruments.md` (same store discipline), `statements.md`.

## The registry is the one country table

`registry.py` + `countries.json` (World Bank country list, aggregates removed; re-seed with
`newsroom actors registry --write`). Curation is code: common English names, aliases, territories
(shown, never ranked), Taiwan and the EU (the Bank lacks them), the G20 and UNSC P5 sets.
`publishing/tagging.py` reads its display names and name-to-ISO fallback from here (its duplicated
tables are gone). Doctrine unchanged: `registry.resolve(name)` renders a name an agent ALREADY CHOSE
into an ISO2; it never scans stories, and a string that is not exactly a name/alias/code is None.

## Sources (all keyless; credited on every page with the years used)

| Key | Source | Licence | Gives | Status 2026-10-04 |
|-----|--------|---------|-------|--------|
| `wb` | World Bank WDI API (military series: SIPRI) | CC BY 4.0 | population, GDP/PPP/per person, growth, inflation, debt, trade shares, fuel exports, military spend/personnel/arms, land | ok, ~0.5 s per indicator |
| `owid` | Our World in Data energy dataset (streamed CSV) | CC BY 4.0 | primary energy use, oil/gas/coal production and consumption, electricity and its mix | ok, ~1 s |
| `imf` | IMF DataMapper (WEO) | IMF open data | this/last year GDP growth and gross debt | ok with the descriptive User-Agent; **403 with a browser UA** |
| `wikidata` | SPARQL, P35 head of state / P6 head of government | CC0 | current leaders with start dates | ok, ~4 s, ~196 states |
| (curated) | `nuclear.py`, FAS Status of World Nuclear Forces 2026 | cited public estimates | nuclear status, stockpile | edit by hand yearly |

Foreign and defence ministers are not fetched: Wikidata coverage is too patchy to publish as fact.
Requests use `polite_http.py` (shared with instruments) and the User-Agent in `catalog.HEADERS`.

## Catalog and store

`catalog.INDICATORS`: adding an indicator is one entry (an existing source's code). Ids are
permanent. `store.py`: `actors_store/obs/<indicator>.jsonl` (env `ALGENT_ACTORS_STORE`), append-only
per (country, year): new, or revised (`revised=True`), unchanged writes nothing. `leaders.jsonl`
appends when an office-holder changed or the last line is 30 days old (honest "as of").
The store is git-ignored runtime data (~4 MB).

## Profile, compare, evidence

`profile(iso2)` returns `headline` (population, GDP, GDP per person, fossil production, military
spending: value, year, world rank, percentile among STATES), `groups` (people, economy, trade, energy,
military; each field value + year + source), `energy_role` (per fuel, production above or below
consumption: a plain sign, only where both are on record; not a trade claim), `leadership` (offices, as-of,
nuclear). `compare(iso2s)` gives each metric's rows on one shared scale (`max`). `evidence_block(iso2s)`
is one compact cited line per actor for writers (not yet wired into daily/brief).

## Publish

`write_intel` also writes `content/intel/actors/<ISO2>.json` (`ohmega.actor/1`) and `index.json`,
mirrored to `public/data/actors/`. Set: G20 + UNSC P5 always, plus up to 60 countries the desk names,
found the SEMANTIC way: theater dossier `actors`/`relations`/validated `places[].country` and a
statement's `affiliation`, each resolved through `registry.resolve`; headlines are never regexed.
Pulses carry no actor field, so they attach through their theater. Shapes: `actors_feed.py` docstring.

## Site

`/intel/actors` (sortable table, shared-scale bars, flags) and `/intel/actors/[iso]` (claim heading,
leaders, five headline numbers with rank, People/Economy/Trade/Energy/Military, what its leaders said,
involved theaters and Pulses, credits). The theater dossier gets an "Actors" strip of its actors on
shared scales. Doctrine: `docs/ethos/information-ergonomics-ethos.md`.
