# The AI desk — benchmark tracker and the AI daily

> The second intelligence domain after geopolitics. Code: `backend/algent_backend/ai_benchmarks/` (numbers),
> `backend/algent_backend/agent_system/agents/intel/domains.py` (the domain recipe), `library/ai_sources.py` (sources).
> CLI: `newsroom ai-benchmarks ...`, `newsroom intel daily --domain ai`. Site: `/intel/ai`, `/ai`, `/api/v1/ai-benchmarks`.
> Numbers layer: no model in any collector. Vision: `docs/vision/ohmega-intelligence-engine.md`.

## 1. The benchmark tracker (`ai_benchmarks/`)

Why a sibling package and not `instruments/`: an instrument is one series (a value per period); a benchmark is many models' scores on one test.
The shape is the same (catalog, source modules with a pure `parse` and a `fetch`, append-only log, consumers read the store only).

| Source | What | Access | Verified 2026-10-17 |
|---|---|---|---|
| Epoch AI Benchmarking Hub (`epoch`) | `https://epoch.ai/data/benchmark_data.zip`: 85 benchmarks (GPQA, FrontierMath, SWE-bench Verified, HLE, ARC-AGI 1/2, METR time horizons, Terminal Bench, OSWorld, Aider, LiveBench, SciCode, WebDev Arena, ...) plus the Epoch Capabilities Index; per-model release date, organisation, weights accessibility | free, no key, CC BY 4.0 (credit Epoch AI) | 85 benchmarks, 6,864 scores, full history in one download |
| SWE-bench leaderboards (`swebench`) | `leaderboards.json` in the swe-bench GitHub repo: Verified, Lite, Full, Multimodal, Multilingual submissions (agent + model, org, open flag, date) | free, public | 5 boards, 323 submissions. Upstream's newest entry is 2026-02-26, so the doctor correctly reports it "not updating" |
| LMArena (`lmarena`) | Elo ratings from the public `lmarena-ai/leaderboard-dataset` through the Hugging Face dataset viewer JSON API (text, webdev, vision, search; category `overall`) | free, public, CC BY 4.0 | webdev 144 models reliably; the viewer answers HTTP 500 "index is loading" after idle, so `lmarena._get` retries patiently (3 rounds, 20 s) |

Covered through Epoch, so no separate collector: ARC Prize, METR, Aider polyglot, LiveBench, HLE, GPQA, MMLU-family, FrontierMath, SciCode, OSWorld.
Not available keyless: the Open LLM Leaderboard (retired), LMArena's own site (403 to scripts), ARC Prize's JSON (404).
Not added, possible later: OpenRouter `/api/v1/models` (public; model catalogue with release time and prices: an AI-economics series, not a score);
LMArena history before our first fetch (the `full` split is a 1.2 M-row parquet; needs pyarrow, which the maintainer would install).
Keyed sources to add later if wanted: none required. (Artificial Analysis offers a free key at artificialanalysis.ai/api for speed and price series.)

### Store and contracts

`ai_benchmarks_store/` (or `$ALGENT_AI_BENCHMARKS_STORE`): `results.jsonl` (append-only; one `Result` per line), `benchmarks.json` (catalog, replaced atomically),
`status.json` (per source), `discovery/<day>.json` (the self-reported pass). A `Result` is
(benchmark, model, model_id, lab, score, unit via its benchmark, `date` = model release or leaderboard publish date, `observed_on` = the day we first saw it,
`weights` open/closed/unknown, `verification` measured | self_reported, source, url). Key = benchmark + model variant + verification + source + date; a changed score
for a key appends a line with `revised=true`, an unchanged one writes nothing. Bounded scores are stored as fractions (Epoch's percent columns are scaled by the metadata);
open-ended ones (Elo, minutes, index points) have no ceiling. The store is in the nightly backup (forward-captured Arena snapshots and lab claims cannot be re-fetched).

### Derived series (`derive.py`, pure, data-driven)

Per benchmark: the **frontier** (best measured score so far, as the list of record-setting results), **open vs closed** frontiers and how many days the open one trails
(`open_lag_days`: when the closed frontier first reached today's best open score), **per-lab** frontiers for the top labs, **saturation** (best / ceiling), **velocity**
(frontier move in 12 months), `new_records` (last 45 days), the top 10 models and the lab **claims**. Self-reported scores never enter any of these. Thresholds
(`MIN_MODELS_FOR_FRONTIER`, `TOP_LABS`, windows) are in `ai_benchmarks/flags.py`; lab spellings are folded by `labs.py` (an alias table that names no models).

### Publishing

One document, `data/ai-benchmarks.json` (schema `ohmega.ai-benchmarks/1`, ~0.5 MB), upserted into `published_intel_documents` like the track record: **no migration**.
Contents: sources with freshness, labs, one view per benchmark (above). Site readers fall back to nothing (an unpublished tracker renders "nothing yet").

### Freshness: it must never go stale silently (`freshness.py`)

Collection is on timers, nothing is manual: `ohmega-ai-bench` every 12 h (`jobs.sh ai-benchmarks` = `newsroom ai-benchmarks fetch`), `ohmega-ai-discovery` daily 06:50.
Per source the collector records last good fetch, last error, rows parsed, the best row count seen and the newest result date, and `source_health` flags three failures by name:
**not fetched** (no good fetch in 40 h), **broken** (the parser no longer recognises the format, or a fetch shrank below 60 % of the best row count: it is refused and nothing is
appended), **not updating** (newest result older than the source's allowance: 45 days Epoch, 30 LMArena, 120 SWE-bench). The doctor check `ai_benchmarks` warns with the reason;
`newsroom ai-benchmarks status` prints it; the page shows per source "fetched N h ago, newest result D" with a STALE tag and per benchmark "as of D". The desk's evidence block
adds a note when a source has stopped so it never writes "no new records" off a dead feed.

### Self-reported discovery (`discovery.py`) — behind its own switch, hard-capped

New frontier models post scores in lab blogs and model cards days before any leaderboard. Daily: SearXNG (free) searches generic queries (no model names), unseen fresh pages
are fetched and trimmed, then **one** low-effort structured model call extracts (model, org, benchmark, score, unit, date, url, quote). A claim is kept only if its url is a page
that was shown; percent scores are normalised against a matching benchmark. Stored as `self_reported`, drawn as hollow diamonds on the page, listed apart under "Claimed by the
labs", and marked UNVERIFIED in the desk's prompt. Limits in `flags.py`: `DISCOVERY_ENABLED` (+ `ALGENT_AI_DISCOVERY=0`), 1 call/day, `DISCOVERY_MAX_USD_PER_DAY = 0.08`,
`DISCOVERY_CALL_CAP_USD = 0.06` enforced by the budget gate. Real cost: roughly 5 pages × 3,500 characters plus a 3,000-token answer at the house model's low effort, about one to three
cents a day. SearXNG is localhost-only on the worker, so the pass runs there; elsewhere it reports the search error and spends nothing.

## 2. The AI daily (`intel daily --domain ai`)

The daily recipe (heat board -> focus -> sections -> summary -> publish) is unchanged; `domains.py` supplies the domain as data:

* **Sources** (`library/ai_sources.py`, beat `ai`, crawled by the existing library timer): OpenAI news, Google DeepMind, Hugging Face, NVIDIA, Epoch AI, CSET, Import AI, Zvi,
  MIT Technology Review AI, The Verge AI, Ars Technica AI, TechCrunch AI, The Decoder, WIRED AI (14, all answering fresh on 2026-10-17; dead or stale feeds are not listed), plus a
  Hacker News class (`base.ai_community_heads`, Algolia's public API, generic AI queries, engagement floor). They form two source classes (`ai_sources`, `ai_community`), each its own coverage denominator.
  The geopolitics base excludes them, so one crawl feeds two desks without mixing shares. The radar is not part of the AI base.
* **Topic areas** (lenses in the clustering prompt, not buckets): frontier labs race; compute, chips and supply; policy, regulation and law; AI in security and the military; open-weights
  ecosystem; AI economics and capital; safety, alignment and evaluation. Theaters stay emergent: a topic with no persistent dynamic yields none.
* **Board**: `boards/ai/<date>.json` (geopolitics keeps `boards/`); the registry is shared with each theater carrying its `domain`; the clustering is shown only that domain's tracked theaters.
  Dossiers read boards from every domain, so AI theaters get `/intel/theaters/<id>` pages and their timeline merges Daily sections from both domains.
* **Sensing**: AI theaters get an `OHMEGA AI BENCHMARKS` block (new measured records, open-weights lag, saturation, then lab claims marked unverified); the cross-theater block is the
  same. Geopolitics instruments and the statements ledger are not shown to AI theaters, and the statements extraction (paid) is not run by the AI refresh. Refresh for `--domain ai`
  = crawl of the AI sources + the benchmark collector (both free).
* **Not used**: the "Around the world" sweep (built for countries and the geopolitics library): `Domain.sweep=False`.
* **Site**: `/ai` and `/ai/<date>` reuse the Daily components with a "Geopolitics · AI" switch; `daily_url` is domain-aware. Reports are published to `daily/ai/<date>.json` and
  `/api/v1/daily/ai/latest` exactly as for geopolitics.

### Scheduling (not done; the operator's decision)

`intel/flags.py` has `AI_DAILY_SCHEDULED = False` and `AI_DAILY_UTC = "07:30"`. The one-line change to schedule the AI daily is `AI_DAILY_SCHEDULED = True`; push, and the server's
`install_schedules.sh` (which reads `newsroom schedule times`) creates `ohmega-ai-daily`, which runs `newsroom schedule run ai-daily` =
`intel daily --domain ai --research` behind the same kill switch, runner claim, spend halt and watchdog as the other paid jobs.

### Cost, relative to geopolitics

Same machinery, so the cost scales with the number of researched sections. Geopolitics runs `top=5` theaters at ~$0.3-0.8 per researched section. The AI daily would have a similar
ceiling (`--top` default 5) but typically fewer moving theaters on day one, one fewer paid step (no sweep/spotlight) and no statements extraction, so expect **roughly 0.6-0.8 of one
geopolitics part**, i.e. on the order of a dollar to two a day with `--research`; without `--research` (headlines only) a few cents to ~30 cents. Add the discovery pass (cents). A first
`--research` run should be watched once to calibrate; the per-article cost cap and the day's spend halt apply as usual.

## Tests

`backend/tests/test_ai_benchmarks.py` (parsers on fixtures, store, derivations, collector health, freshness, discovery with a stubbed model and search),
`test_intel_domains.py` and `test_intel_domains_daily.py` (domain registry, AI board isolation, HN class, sensing, refresh layers, the scheduling flag, an end-to-end AI daily with a stub model).
