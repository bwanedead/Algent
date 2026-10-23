# Corpus index: one queryable view of the record (Phase A)

> Code: `backend/algent_backend/corpus/`. Registry product `corpus_index` (derived, not backed up, rebuildable). CLI: `newsroom corpus build|stats|ask`.
> Why: the record is many JSON stores; nothing could answer "everything we know about X since Y, with sources" without loading files ad hoc, and the
> site aggregates raw documents at render time. This is the substrate for the knowledge graph AI agents will use (`agent-api.md`, `foundation.md` step 6).

## Principle: derived, so safe
The JSON stores stay the record. The index is a SQLite file (`<corpus_store>/corpus.db`, WAL) built *from* them through each product's own reader
functions (no format is re-parsed here) and can be deleted and rebuilt at any time: `newsroom corpus build --full`. It can never corrupt the corpus.
Nothing writes to a store through it. Every content row carries `product` (registry id), `origin` (the unit of the store it came from; `ingest_state.path`
says which file) and `ingested_at`. Ids are pure functions of source ids, so rebuilds are byte-for-byte reproducible (modulo `ingested_at`).

## Schema
| Table | Holds |
|---|---|
| `entities` (+ `entity_alias`) | id, kind (country, person, org, actor, place, vessel, aircraft, situation, pulse, market, model, lab, topic), name, aliases, iso2, lat/lon, attrs JSON. Materialised from `entity_decl` (what each source said) at the end of a build |
| `documents` | daily section/summary, brief, profile, article, statement, sanction, calendar item, geo status event, forecast, pulse reading: id, kind, domain, date, title, site url, status, body |
| `claims`, `sources`, `claim_sources` | claim text, status, grounding, confidence, document; sources by url (domain, title, fetched_at); supports/contradicts edges |
| `mentions` | entity <-> document/claim with a role (speaker, about, theater, in text, ...) |
| `relations` | typed entity <-> entity edges with evidence document/claim, date, note (`head_of_state`, `affiliated_with`, `stance:threat`, `has_pulse`, `bears_on`, `built_by`, `flagged_in`, brief relation kinds...) |
| `observations` | series points: entity, metric, ts, value, unit, **basis** (`official` / `our_count` / `our_derived` / `model` / `reported` / `measured` / `self_reported`, following the stats registry), label, source url |
| `events` + `event_actors` | dated happenings: developments, brief timelines, status events, sanctions changes, calendar items, maritime notable events, market resolutions, watches; place (resolved to an entity when it can be), actors |
| `search` | FTS5 (porter, titles weighted double) over document titles/bodies, claims and events; a LIKE-scanned plain table when FTS5 is absent (`meta.fts`) |

## Sources ingested (adapter -> product -> reader used)
countries+capitals (`actors.registry`), leaders and yearly indicators (`actors.store`); dailies, briefs, theater registry (`intel` daily/brief files, `heat.registry`);
Pulses: situations, pulses, readings, events, watches (`PulseStore`); profiles (`JsonProfileStore`); articles (site content files + `publish.front_matter`);
statements (`statements.store`, speaker folding via `speakers.canonical_map`); sanctions events; calendar items; geoledger assets and status events (`Ledger`);
maritime daily summaries (`maritime.rollup`); Polymarket markets, prices, forecasts, decisions, equity; instruments series; AI benchmark results.
Adding one = a `sources/<name>.py` with a `SOURCE`, one line in `sources/__init__.py`, a fixture test.

## Build (`newsroom corpus build [--full] [--since D] [--only a,b]`)
Incremental by default, two watermarks: a source whose store-level stat mark is unchanged is not read at all; a unit (file, profile, ledger record) whose
content hash is unchanged is read but not written. A changed unit is replaced whole (delete by `origin`, insert); a unit gone from its store is removed.
`--since` considers only recent units and never deletes. `--full` writes a new file and swaps it in (also the vacuum; the canonical form: an incremental
build of the same record equals it, tested). A failing source or unit is reported and skipped, never fatal.

**Entity resolution is deterministic and runs after everything is read** (`link.py`): the country table, geoledger aliases, speaker folding and the profile
research's typed entities *declare* entities with aliases; names that are only text (a statement's `about`, a development's actors, a brief's relation ends,
an event place) are resolved against the alias table afterwards, only when exactly one entity answers (a free-text `topic` counts only if no real entity
does, so the tag "Russia" never competes with Russia). Everything else is **reported, not guessed**: `newsroom corpus stats` lists the most-used unresolved
names with the reason (`unknown` / `ambiguous`). No model calls.

## Identity: one entity per real thing, and which one a bare name means (`identity.py`)
Two deterministic, data-driven rules (tables in `flags.py`) run in the link pass. **Precedence** (`KIND_TIER`): when a normalised name answers to several entities the best kind tier wins (country, then typed
entities, then an untyped speaker, then a free-text topic): "France" is the country, not the place of the same name. **Merging** (`MERGE_FAMILY`): declarations of one family whose *name* is a name or alias of
the other are one entity (two profiles' "Houthis" / "Houthi movement"; the chokepoint a profile and the instruments both declare; an acronym and its spelled-out body), and a speaker folds into the one typed entity
of its name; the lowest-ranked declaration names the result, `entity_merge` keeps the old ids resolvable and every asserted id is rewritten to the canonical one. Geoledger assets and registry capitals never merge
on a name. A revision that would *split* an identity restarts the incremental build from nothing (`merge_is_monotone`). What still collides across typed kinds stays reported as `ambiguous`. Schema version 2.

## Query API (`corpus.Corpus`, read-only connection; every row carries provenance)
`entity(name|id)` profile (aliases, latest status/series values/leaders, linked situations, top relations, timeline, alternatives when ambiguous) /
`about(entity, since, kinds)` documents, claims, events with source URLs / `timeline(entity|situation)` / `search(text)` FTS across documents, claims, events /
`related(entity)` typed edges + shared claims, events, documents, with the parts shown / `series(entity|metric)` with basis and unit / `stats()`.
CLI: `newsroom corpus ask entity|about|timeline|search|related|series <text> [--since D] [--kinds a,b] [--limit N] [--metric M]` prints JSON.
The server-built views (`views.md`) wrap these methods for the site and the agent endpoints (a view per entity, country, situation and metric, published to R2); they return plain dicts. `graph.RelatedIndex` is the bulk form of `related` (one pass, then lookups) that the entity views use.

## Wiring
`retrieval/corpus_backend.py`: when an index exists, retrieval's documents (same ids, windows and text as `docs.py`) and its lexical ranking come from the
index (FTS5 instead of in-process BM25); absent or unreadable index = the original loaders and BM25. Switch: `retrieval/flags.py::USE_CORPUS_INDEX`.
Lifecycle: registry job `corpus-build` (free, every 4 h at :25 from 02:25 UTC, i.e. after the daily, AI and markets runs; shares the heavy-job lock). Store dir
`corpus_store` (`ALGENT_CORPUS_STORE`), excluded from backup ("derived; `newsroom corpus build --full` rebuilds it"), budget in the registry.

## Server commands
`cd ~/Algent/backend && .venv/bin/python -m algent_backend.cli newsroom corpus build --full` (first time), then the timer keeps it fresh;
`... newsroom corpus stats`; `... newsroom corpus ask search "refinery strikes" --since 2026-10-01`. After `install_schedules.sh` the `corpus-build` timer exists.

## Phase B (a later decision, not made here): writers move to SQLite as the record
Not now: JSON append-only files are simple to back up, diff and repair, and the index gives the queries. Move a product's writes into SQLite only when most of
these are true: (1) a product's own readers are slow or memory-heavy at its real size (full-file reads of a growing ledger); (2) the same facts are written to
two places and drift; (3) a write needs a transaction across products (a claim, its sources and a relation together) that file appends cannot give;
(4) concurrent writers contend on a file; (5) the backup/restore drill proves SQLite snapshots (online backup API) as reliable as the file mirror; (6) the
index has run for a quarter with rebuild == incremental holding and unresolved-name counts falling. Then migrate one product at a time, dual-writing first.

## Known limits
Speakers are kind `actor` (a person or an institution: the ledger does not say) unless a profile or a leader types them. Places from profiles and chokepoints from
instruments are separate entities until someone decides they are the same. The index does not store full profile/article text (bodies are clipped to `BODY_CHARS`).
