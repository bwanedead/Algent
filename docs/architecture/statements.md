# Statements ledger (intel desk)

The record of **who said what**, collected from primary transcripts independently of which
theaters are hot. Rhetoric is a leading indicator: a threat, a new condition, a softened tone or a
reassurance aimed at a third party shows up in words before events. The desk's headline radar never
sees most of it (a long Putin speech, NATO's chief on Russia, European leaders on troops in Ukraine),
so reports lose texture. Vision: `docs/vision/ohmega-intelligence-engine.md` ("Sensing", layer 3).

Code: `backend/algent_backend/agent_system/agents/statements/`. CLI: `newsroom statements`.

## Pipeline

```
sources.py  (catalog) -> collect.py (free) -> store: transcripts/ + seen.json
                                           -> extract.py (1 model call / transcript) -> statements.jsonl
                                           -> recall.py  (evidence block for writers)
```

| Module | Owns |
|--------|------|
| `contracts.py` | `Transcript`, `Statement`, the model-facing `ExtractedStatement`/`ExtractionPlan`, `statement_id` |
| `sources.py` | code-defined feed catalog (`Source`) |
| `collect.py` | polling, new-item detection, full text (feed body or FREE page read), per-feed reports |
| `extract.py` | the extractor doctrine (`EXTRACTOR_ROLE`), chunking, mechanical validation |
| `store.py` | append-only persistence and `query` |
| `reported.py` | the reported (secondary) lane: targets, search, read, budget, cache |
| `dedupe.py` | primary-over-secondary and cross-outlet de-duplication |
| `recall.py` | `recall(terms, days, limit)`, `speaker_history(speaker, days)` |

Harness ethos split: the model reads and judges (what is load-bearing, the signal, the stance);
the harness does only mechanics (fetching, dedupe, persistence, quote-substring validation,
stamping `id` / `source_url` / `transcript_id`).

## Contracts

`Statement`: `id` (hash of source URL + speaker + quote-or-paraphrase), `speaker`, `role`,
`affiliation`, `date`, `venue_kind` (speech, press_conference, interview, statement, readout, post,
other), `quote` (exact, at most 60 words, only when wording matters), `paraphrase`, `about`
(actors/targets), `topics`, `signal` (threat, warning, red_line, commitment, offer, demand,
reassurance, accusation, denial, policy_announcement, tone_shift, other), `stance` (-2 hostile to
+2 conciliatory, toward `about`), `significance` (one line), `source_url`, `source_kind`
(primary/secondary), `transcript_id`.

Validation after extraction: a `quote` that is not a substring of the transcript (whitespace and
typography normalized) is dropped to the paraphrase, and the statement is dropped if nothing is left;
quotes over 60 words are cut to a verbatim prefix; `source_url` is forced to the transcript URL; an
invalid date falls back to the transcript's published date; `stance` is clamped.

## Store

`statements_store/` (git-ignored; override with env `ALGENT_STATEMENTS_STORE`; relative paths
resolve from the working directory, like `intel_store`):

- `transcripts/<id>.json` raw collected text. Internal only.
- `statements.jsonl` append-only; ids dedupe, torn lines are skipped.
- `seen.json` urls collected, failed attempts (parked after 3), `titles` (the same event from two
  feeds is collected once), and which transcripts were extracted (extraction is never paid twice;
  a failed one is retried next run).

`store.query(terms=, about=, speaker=, affiliation=, topic=, days=, limit=)` returns statements
newest first. Matching is word-level (`Putin` matches `Vladimir Putin`; `US` never matches `Russia`).

## Consumption (not yet wired into intel)

- `recall(["NATO", "Ukraine"], days=14)` returns a `STATEMENTS ON RECORD` block, newest first:
  speaker and role, date, quote or paraphrase, signal and stance, why it matters, URL. Empty string
  when nothing matches.
- `speaker_history("Putin", 90)` returns that speaker's earlier statements oldest first so a writer
  can judge tone against the speaker's own record.

## CLI

```
newsroom statements collect [--no-extract] [--feed ID ...] [--days 14] [--max-new 15] [--reported | --no-reported]
newsroom statements show [--about X] [--speaker Y] [--affiliation Z] [--topic T] [--days 14] [--limit 40]
```

`collect` polls the catalog, then extracts every not-yet-extracted transcript with one structured
call each on the house cheap spec. `--no-extract` is free (no model). Each command prints one JSON
document with per-feed counts and errors. One feed failing never aborts the run.

## Feeds (verified 2026-10-04)

| id | Source | Route | Status |
|----|--------|-------|--------|
| `kremlin_transcripts` | en.kremlin.ru transcripts | feed, full text in feed | working; slow (timeouts 45s, 3 retries). Includes the long events (Valdai, 130k chars) |
| `kremlin_news` | en.kremlin.ru news | feed, full text in feed | working; mostly greetings and readouts; events already in transcripts are deduped |
| `whitehouse` | whitehouse.gov/news | feed, full text | working; much ceremonial filler (extractor returns empty) |
| `state_dept` | state.gov press releases | feed, full text | working |
| `fcdo` | UK Foreign Office (Atom) | page read | working; travel advice and guidance titles skipped by regex |
| `uk_pmo` | 10 Downing Street (Atom) | page read | working |
| `un_press` | press.un.org | page read | partial: most pages behind a JS client challenge, so reads fail and are parked after 3 tries |
| `ec_presscorner` | European Commission | RSS + press-corner JSON API (`/api/documents?reference=`) | working |
| `china_mfa` | mfa.gov.cn spokesperson remarks | HTML listing + page read | working; no RSS, listing parsed by link pattern (dates from the URL) |
| `nato_transcripts` | nato.int SecGen speeches, remarks, press conferences | JSON listing (the site's own search servlet, `.../transcripts/jcr:content/root/container/general_search_copy.search.json?sortBy=dateDesc`) + page read | working; the date is in each link (/YYYY/MM/DD/); old `/cps/` pages redirect to the new site |
| `elysee` | Elysee (Macron) | RSS (French titles) + page read of the French page | working; the feed links `/en/...` pages that 404, so urls are rewritten to `/emmanuel-macron/...`; ministers' council minutes and appointments skipped |
| `presidentti_fi` | President of Finland (Stubb) | RSS, full text in feed | working |
| `pm_au` | Prime Minister of Australia | RSS + page read | working; feed dates like "Monday 5 October 2026" are parsed from text; full press-conference transcripts |
| `un_sg` | UN Secretary-General quotes | RSS, text in feed | working but sparse (a few items a month); `un_press` stays partial |
| `auswaertiges_amt` | German Foreign Office newsroom (Wadephul speeches, statements) | HTML listing + page read | working; the listing has no dates (ledger date falls back to the collection day unless the text states it) |
| `tccb` | Presidency of Turkiye (Erdogan) | HTML listing (date before link) + page read | working |
| `kantei` | Prime Minister of Japan | HTML listing from the home page + page read | working; only the latest few are listed; dates from the url (two filename styles) |
| `iran_mfa` | Iran MFA English (spokesperson, FM statements) | HTML listing (date after link) + page read | working; some items undated |
| `brazil_mre` | Brazil MRE press notes | HTML listing + page read | working; mostly condolences and consular notes |
| `president_lv` | President of Latvia (Rinkevics) | HTML listing + page read | working; image links are titled from the slug; photo posts skipped |
| `mfa_lv` | Latvia MFA | HTML listing + page read | working; includes Latvian-language articles |

Open (checked 2026-10-04, not added; reason):

- Ukrainian presidency (`president.gov.ua`): Akamai 403 to plain fetch; the free read ladder got through once (likely a Wayback copy) and was blocked the next time. MFA (`mfa.gov.ua`): Cloudflare challenge. Covered by the reported lane.
- Poland: `gov.pl` returns its portal home for every RSS/news path (JS app); `president.pl` Cloudflare challenge. Lithuania `lrp.lt`, `urm.lt` and Finland MFA `um.fi`: Cloudflare "Just a moment". Estonia: `president.ee` is a JS shell, `vm.ee/en/news` 404. Latvian PM host does not resolve. Norway and Sweden governments: Cloudflare.
- Russian MFA (`mid.ru`): JS bot challenge, no usable feed or listing for plain HTTP.
- European Council (`consilium.europa.eu`): browser-check page (403). EEAS: press page has no feed.
- Germany government (`bundesregierung.de`): speech listings are JS-loaded; the Foreign Office listing is used instead. France MFA RSS 404.
- India MEA: press-release listing is JS-filled (no item links); `/rss-feeds.htm` 404. Japan MOFA: 403. South Korea MOFA: list page has no item links (JS).
- Israel (`gov.il`): Cloudflare. Saudi SPA: TLS timeouts, HTML only. UAE WAM: JS shell. Qatar MOFA: 404. Turkey MFA: press page redirects home. Canada PM: listing has no item links (JS). Brazil Planalto: login redirect.
- NATO news articles (`/articles/news`) use the same servlet and could be added; transcripts were chosen as the Secretary General's own words.

## The reported lane (secondary statements)

`reported.py`. For the voices whose own sites we cannot read, find news reports of what they said in
the last 3 days and keep them as **secondary** statements: `source_kind="secondary"`, `reported_by` =
the outlet, `source_url` = the article, quotes validated against the ARTICLE text (a quote the outlet
printed must still be a substring of what we read). The extractor is told the text is a report: the
speaker is the person quoted, only words the outlet puts in quotation marks may be `quote`, the rest is
paraphrase, the outlet's gloss is not the speaker's tone.

Flow: `plan_targets` -> per target, library search (our trusted outlets; primary-kind documents are
excluded, they are the speakers' own text) then free news search (`gnews`, resolved links only) ->
keep recent articles whose headline/snippet mention the person -> read (the library's stored text when
it has the page, else the free read ladder, paced) -> `Transcript(feed="reported", outlet=...)` ->
the ordinary `extract_pending`.

Targets, in tiers: 0 = heads of state/government (actors store, Wikidata) and foreign/defence
ministers named on the ledger, of countries named by live geopolitical theaters, **excluding countries
whose own site the primary lane already reads** (those drop to tier 3); 1 = standing offices (NATO
SecGen, Commission, European Council, EU foreign-policy chief, UN SecGen); 2 = the standing list of
other states (UA PL LT LV EE FI FR DE TR JP IN IR IL SA QA AE KR AU CA BR).

Budget (constants in `reported.py`, each with its reason): 24 targets/run (40% reserved for tiers 0-1,
the rest rotates by longest-unsearched), 2 articles/target, 20 articles/run (a target not fully served
when the budget ends is not stamped, so it leads next run), 12h search cooldown per target, 120-word
minimum for an article, URL cache in `seen.json` (a URL read once is never read or extracted again;
three failures park it). Free throughout; extraction (one cheap call per article) is the only spend.

Dedupe (`dedupe.py`): same speaker, dates within a day, shared verbatim quote or >=50% of content words.
A secondary is skipped on write if anything on file covers it, and hidden on read if a primary (arriving
later) covers it; two outlets reporting one remark keep one. Primaries are only ever deduped by id.
`recall` marks secondary rows "as reported by <outlet>"; consumers that show the ledger as "official
text" should filter on `source_kind` or show `reported_by`.

CLI: `newsroom statements collect --reported` (or `--no-reported`; `reported.RUN_BY_DEFAULT = False`).
Theaters come from `intel_store/theaters.json` (new/active geopolitics). Callers (the intel refresh) use
`reported.collect_reported(theaters=[...])` then `extract.extract_pending`.

## Social (X): design only

Many leaders speak first on X. A leader-account lane would reuse the same shape: targets = the same
people with their handles (a small curated map; handles are not in the actors store), posts become
`Transcript(feed="x", outlet="@handle")` with `venue_kind="post"`, and the posts are PRIMARY (the leader's own
words), so quotes validate against the post text. Routes in the repo: `x_native`/`x_search` (X API,
paid per call: not for a standing lane under the paid-API-sparingly rule) and `x_grok_cli` (Grok Build CLI,
subscription quota, no metered spend, but built for topic discovery with lanes, not per-account timelines,
and slow: up to 600s per lane). Cheapest viable path: one Grok CLI instance per ~10 handles asked for each
account's posts of the last 48h as JSONL, off by default behind a flag in `agents/newsroom/flags.py`. Not
implemented: it needs a handle map, a per-run time budget decision, and a check that Grok returns verbatim
post text (quote validation drops anything it paraphrased).

## Adding a feed

Add a `Source(...)` to `SOURCES` in `sources.py`: `id`, `url`, `affiliation`, `body` (`feed` when the
entry carries the full text, `page` for a free page read, `ec_api` is Commission-specific), `kind="listing"`
plus `link_pattern` for an HTML index, and `skip_title` for titles that are never statements. Order
matters when two feeds overlap: put the fuller one first (cross-feed dedupe keeps the first). Verify
live with `newsroom statements collect --no-extract --feed <id>` against a scratch
`ALGENT_STATEMENTS_STORE`, add a trimmed real fixture under `backend/tests/fixtures/statements/`, then
list it in the table above.

## Copyright

Transcripts are kept internally so extraction and quote validation have the source text. The site and
agents receive our extracted statements with links back to the original; full texts are never
republished. Quotes are limited to 60 words and only where the wording matters.

## Consumers

The intelligence desk reads the ledger through `agent_system/agents/intel/sensing.py` (read-only; `recall.block` / `recall.history_block` print chosen rows in the canonical format):

- **Daily section writer** and **brief analyst** (`daily.write_section`, `brief.write_brief` via `desk.produce`): STATEMENTS ON RECORD for the theater (a fortnight for the daily, `desk.BRIEF_WINDOW_DAYS` for a brief). Terms are the ledger's own entities (speakers, affiliations, `about`, plus restricted office-holder surnames) that the theater corroborates (in its own account, or in 2+ member headlines). A statement qualifies only through a DISTINCTIVE shared entity (rarity at or above the ledger's median-mention idf, so "Russia" or "United States" in a Kremlin-heavy ledger cannot qualify one alone) and at least two shared entities when the theater has two; qualifiers rank by summed rarity, then recency, within a per-call budget. Speakers whose statements qualified get a `STATEMENT HISTORY` (~60 days) restricted to earlier statements about the same distinctive counterparts, so it shows tone toward them, not the speaker's other news. Rules and their derivation: `sensing.py` docstring.
- **Daily summary writer** (`daily.write_summary`): the weightiest statements of the last ~3 days across ALL actors (strong stance and a stated kind of act first, at most two per speaker), so a major speech lands in the day's top even when no hot theater claims it.
- **Grounding**: transcript URLs of shown statements are primary evidence in `normalise_section` / `brief.normalise` (they may ground `researched`, meaning *said*; they are never a source for key figures). A statement proves it was said, not that it is true.
- **The visible record**: `sensing.Evidence.shown` (the statements the writer saw, in sensing's order) becomes `on_record` on every daily section and brief (`intel/on_record.py`: speaker, role, affiliation, `iso2` via the ISO renderer, date, venue, verbatim quote or paraphrase, signal, stance, significance, URL). Deterministic, so the record shows whatever the writer did with it; old records without it render as before. `normalise_section` also attaches a statement to any development that cites its transcript but left `statements` empty (the failure behind the 10-04 daily, where every `statements` list was empty). Dossiers union `on_record` across reports (by id, newest first, <=150).
- **The ledger export**: the desk publish writes `record.json` (`content/intel/` and `public/data/`): statements of the last 60 days (`on_record.WINDOW_DAYS`), newest first, at most 1500, plus tone series for (affiliation -> about) dyads with >=4 statements on >=2 days (mean stance per day, -2 hostile .. +2 conciliatory). Site: `/intel/record`.
- **Refresh**: `newsroom intel daily` / `cycle` run `collect` then `extract_pending` first (best-effort; `--no-refresh` skips; transcripts already extracted cost nothing), reported as `sensing_refresh.statements`.
