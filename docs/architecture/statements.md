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
newsroom statements collect [--no-extract] [--feed ID ...] [--days 14] [--max-new 15]
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

Open (checked, not added):

- NATO: old `nato.int/cps/...rss` is 404; the new site (`/en/news-and-events/...`) is JS-rendered with no feed found.
- Russian MFA (`mid.ru`): behind a JS bot challenge, no usable feed or listing for plain HTTP.
- Ukrainian presidency (`president.gov.ua`): 403.
- European Council (`consilium.europa.eu`): the press-release RSS works but entries are one-line stubs and the article pages return 403.
- EEAS: no RSS at the tried URLs (404); press-material page has no feed link.
- Iran MFA 404; Elysee `/en/rss` 404; German government `/breg-en/service/rss` 404; Israeli PMO TLS handshake failure and `gov.il` 403; Japan MOFA 403; India MEA returns HTML, not a feed.
- Candidates to try next: a free news search for major leaders' remarks (the vision's secondary lane), NATO press conferences via YouTube transcripts, Kremlin Russian-language feeds for fuller Q&A.

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
