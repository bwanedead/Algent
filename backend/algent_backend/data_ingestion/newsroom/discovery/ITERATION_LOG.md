# Deterministic Discovery — Iteration Log

A running record of how the deterministic GKG + NGrams digestion was tuned, and
**why**. The point is retro-traceability: if the system later looks like it
over-fit to some information shape we didn't want, this log should let us see the
decision that put it there and undo it deliberately.

Scope: deterministic processing only — no LLM/agent in the loop. The output we're
optimizing is the `InsightsReport` (ranked candidates + per-language view) and the
`LongtailSample`.

## 2026-07-24 — the beat channel was dead (variety root cause)

**Problem.** Discovery kept returning the same super-topics (the live site ran 4
Strait-of-Hormuz pieces and 2 ICE pieces out of 22). The suspicion was ranking; the
cause was the **pool**.

Measured on `pool_20260724084500`: `{gkg: 23, x: 24, market: 12}` — **zero beat
items**. The standing sheet was `beats_20260625204107`: 29 days old, 2 beats swept,
both failed, 0 hits. So the entire beat registry — 11 pillar beats (science, health,
energy, gaming, …) plus 30 country beats, i.e. the *whole* anti-rut mechanism — had
been contributing nothing for a month, and every pool was built purely from three
loudness channels: GKG wire volume, X trends, Polymarket. `ensure_t0` only ever *read*
a sheet off disk; nothing refreshed it.

**Why it died (the deeper cause).** A live 14-beat sweep came back **12/14 throttled**
(`rate_limited` / non-JSON soft throttle). The DOC limiter is stateful and escalating,
and the old sweep fought it: a flat 6s gap plus an immediate retry per beat, so a
throttle doubled our request rate exactly when we were being told to stop. The June
sheet wasn't neglected — the sweep could not complete.

**Change.**
- `beat_refresh` — rotating refresh inside `ensure_t0`: re-sweep the **stalest slice**
  (14/cycle), merge into the standing sheet, per-beat `swept_at`. Cold start takes the
  pillars first (registry order breaks ties), so cycle one buys topical breadth.
- **Age guard** (`prune_stale`, 24h): a stale sheet contributes *nothing*. Before this,
  had the June sheet held hits, t0 would have folded month-old articles in as today's.
- Sweep pacing rebuilt for a stateful limiter: adaptive gap that **carries across
  beats** (doubles on throttle, decays on success), **no immediate retry** (the retry
  is the next rotation — a failed beat stays unstamped and goes first), and a
  wall-clock **budget** so it is safe to call inline.
- Soft throttle (non-JSON 200) now raises `RateLimited` like a 429 — same signal.
- Pool: sweep capped (`ALGENT_T0_BEATS_CAP`, 28) and spent on the **least-alike**
  stories (`pool._diversify`, greedy on headline-vocabulary overlap).
- Pool dedup now collapses **syndicated headlines**, not just repeated URLs (the same
  measles story arrived at 3 URLs and took 3 of 28 slots).
- Promotion gets a second, coarser reference beside headline cooldown: **what recent
  output keeps circling** (recurring subjects/places/topics off published frontmatter),
  as a tie-break only.

**Framing correction (same day, operator).** The first cut spent the cap *round-robin
per query* — one hit per beat before any beat got a second. Rejected, correctly: that
is a quota system, and it trades a wire rut for a taxonomy rut. Hard categories were
only ever a heuristic for variety, and the goal is a genuine long tail of many kinds of
thing, not a checklist of buckets to satiate. Selection is now purely **dissimilarity**
— no query is owed a slot, and a query whose hits are all redundant gets nothing. The
registry stays, reframed as a *sampling frame*: a set of nets cast into parts of the
corpus the loudness channels cannot see, with no claim on the output.

**Observation.** Rotation works end to end; the diversifier drops near-duplicate
coverage in favour of unlike stories. Throughput is the open item — see below.

**Still open.** Even with backoff, DOC throttling is the binding constraint on how much
of the registry stays fresh. If a rotation keeps landing <50% of its slice, the answer
is a smaller slice at a wider gap (more cycles), not more retries.

---

## 2026-07-23 — event grain + sports kill (unit-of-discovery shift)

**Problem.** Theme/entity ranking (even with novelty/curiosity weights) still
surfaced standing tags (`ENV_NATURALGAS`, `united states :: armedconflict`) and
sports leaks (X JUST-IN, LeBron markets). Grade: D/C.

**Change.**
- Candidate unit: **URL-slug stories** + **actor×action events** (not mega themes).
- Ranking: specificity + standing-topic tax; demote mega-actor×weak-action.
- Shared `topic_filters.is_sports_text` on X / markets / GKG entities.
- X novelty probes retargeted to event morphology; per-author spectrum/novelty caps.

**Observation (batch 20260723103000).** Shortlist became 100% story/event kinds;
sports markets gone; GKG labels read as headlines (e.g. Iran envoys in Pakistan,
FDA peptides, Novo/Lilly suit) rather than taxonomy codes. Residual noise:
entity OCR (sergei laurel), local crime/commercial slugs — filterable.

---

## What "high signal" means here (the target)

An insight is useful to us if it points at a **real, specific, moving** thing in
the world that we might want to research/produce on — not a broad standing topic
everyone already covers. Concretely we want the shortlist to favor:

- **movement over magnitude** — what's *rising* this batch vs. its own recent
  baseline, not what's perennially large (large-and-flat = the rut);
- **specific objects over abstract tags** — named entities (people/orgs) and
  narrow themes over generic GKG meta-themes;
- **the margins** — emerging in non-English coverage first, never-seen-before,
  under-covered-but-intense — protected from being crowded out by incumbents;
- **corroboration** — signals that show up across languages/outlets (real, not
  one-outlet noise).

Reliability target: the same batch sequence replayed yields the same report
(pure/deterministic), and the top of the list shouldn't be dominated by the same
structural junk every time.

## Method

We replay **real consecutive historical batches** (GKG every 15 min; downloadable
by timestamp) through the pipeline, accumulating rolling memory, so velocity and
novelty are exercised on actual data rather than synthetic fixtures. Each
iteration: observe the current output → form a hypothesis about what's weak →
change one thing → re-run the same sequence → compare → record the decision.

---

## Iteration 0 — baseline (starting point)

**State.** First working pipeline: candidates = themes + entities by record
frequency; score = 0.40·significance + 0.30·velocity + 0.20·cross-language +
0.10·novelty; protected quota of 10/40 for rising/novel/non-English; boilerplate
theme stoplist (TAX_FNCACT, CRISISLEX_, …).

**Observation (single live batch, no history).** Top candidates were broad,
high-volume cross-language themes — `UNGP_FORESTS_RIVERS_OCEANS`, `EPU_POLICY`,
`WB_696_PUBLIC_SECTOR_MANAGEMENT`, `GENERAL_GOVERNMENT`, `GENERAL_HEALTH`. Every
top item carried only the `cross-language` reason. No entities in the top 10.
Velocity unexercised (no baseline on a single batch).

**Read.** With no history, score collapses to significance + cross-language, and
at high volume *everything* is cross-language — so that term doesn't discriminate
at the top; it just re-ranks the loudest themes. The list is "big standing topics"
= exactly the rut. Entities never surface because a single named entity can't
out-count a broad theme on raw frequency.

**Hypotheses to test in the replay loop:**
1. Velocity, exercised over real consecutive batches, should pull genuinely
   moving items up — need to see whether it does and how noisy it is.
2. `cross-language = language_count` is non-discriminating; a *relative* breadth
   or a *non-English-lead* signal would be sharper.
3. Themes and entities should probably be scored/served on separate tracks (or
   per-kind normalized) so specific objects aren't buried by broad tags.
4. Significance weight is likely too high for a discovery (vs. monitoring) goal.

(Decisions recorded below as each is tested.)

---

## Iteration 1 — exercise velocity on a real 8-batch sequence

**Setup.** Built `gdelt_gkg.fetch_batch(id)` (pull a specific historical batch),
`discovery/replay.py` (thread memory through a sequence), and
`scripts/discovery_eval.py` (fetch + cache the last N batches, replay, read out
top-by-score vs top-by-velocity). Ran on 8 consecutive batches (2h of real news).

**Observation (final batch, with real baseline).**
- *Top by score* = broad cross-language themes (`UNGP_FORESTS_RIVERS_OCEANS`,
  `EPU_POLICY`, `WB_696…`, `GENERAL_HEALTH`) — **all with negative velocity**
  (−0.10 … −0.27). The shortlist is ranking things that are big *and shrinking*.
- *Top by velocity* = specific and genuinely interesting: a nuclear-testing /
  royal-commission story cluster (`elizabeth tynan`, `nuclear archipelago`,
  `UNREST_NATIONAL_SELF_DEFENSE`), a rising cross-language hurricane
  (`NATURAL_DISASTER_HURRICANE`, langs=3, v=+3.2). Entities surface well here.
- *But* velocity-top is polluted by a **securities class-action PR cluster**
  (`rosen law firm`, `securities class action services`, `phillip kim`,
  `laurence rosen`) — single-language English newswire spam, all v=+5.5 (0→11).

**Reads / decisions.**
1. **Significance weight is way too high.** Volume-led scoring surfaces declining
   incumbents. The shortlist must be *velocity-led*; significance becomes a gentle
   floor (and the only signal during cold start). → change in Iter 2.
2. **Isolated single-language spikes are the dominant noise** (PR/promo). Real
   stories corroborate across languages. → weight velocity by language breadth so
   a rise seen in many languages outranks an isolated one. → Iter 2.
3. **Low-count velocity is degenerate** (0→3 ties at huge ratios). → gate "rising"
   behind a minimum support count. → Iter 2.
4. **Newswire/legal PR spam** (`rosen law firm`, `securities class action…`) is a
   real, recurring GDELT artifact a general signal may not fully kill. Noted as a
   candidate for a small, explicit, *reversible* stoplist — flagged here as the
   most over-fit-prone lever, to revisit. → tested in Iter 3 only if the general
   corroboration fix doesn't demote it.

---

## Iteration 2 — velocity-led, corroboration-weighted scoring

**Change.** Replaced the additive volume-led blend with a momentum-led score:

```
momentum     = log1p(language_count) · min(positive_velocity, CAP)   # rise × breadth
significance = log1p(count) + 0.5·log1p(source_spread)               # cold-start floor
score        = W_MOM·momentum + W_SIG·significance + W_NOV·novelty
```

with a **min-support gate**: velocity only counts toward momentum once a
candidate clears `MIN_RISING_COUNT` records (kills 0→3 ratio spikes), and velocity
is capped so one explosive item can't dominate purely on ratio. Breadth
(`log1p(language_count)`) multiplies velocity, so a rise corroborated across many
languages outranks an isolated single-language spike — the principled lever
against PR/promo noise, applied before reaching for any blacklist.

**Result (same 8-batch sequence).** Big improvement at the very top: the
shortlist now *leads* with corroborated movers — `NATURAL_DISASTER_HURRICANE`
(langs=3, v=+3.2), `ELECTION_FRAUD` (langs=4, v=+2.0), `twitter` (langs=2) —
instead of big declining incumbents. The flat high-volume themes correctly fell
away. Velocity-led + breadth-weighted scoring validated.

**New problem exposed.** Slots 4–14 are flooded by a *single story*: ~10
co-occurring entities of one Australian nuclear-testing / royal-commission cluster
(`elizabeth tynan`, `royal australian navy`, `nuclear archipelago`, `a royal
commission`, `james cook university`, `robert menzies`…), all identical
(n=7, v=+3.5, tone=−2.7, novel) because they appear in the *same 7 records*. One
story consumes ten slots. The Rosen PR cluster behaves the same way (5 entities,
same records). `rising` is now on 40/40 candidates — no longer discriminating.

**Read.** Individual entities are the wrong final unit: co-occurring entities ARE
one information object. We need diversity by *supporting-record overlap* — collapse
a cluster to one representative carrying its co-occurring members as related
context. This also quietly kills the PR cluster (5 entities → 1 entry). → Iter 3.

---

## Iteration 3 — co-occurrence de-duplication (entities → information objects)

**Change.** Each candidate now carries its supporting record-index set. Selection
collapses candidates whose support Jaccard-overlaps an already-chosen one above a
threshold: the highest-scoring becomes the representative and the rest attach to
it as `related` members (capped). So one story = one shortlist entry, annotated
with its co-occurring entities — a real information object, not ten near-dupes.
Applied before the top/quota cut, so the deduped representatives are what compete.

**Result.** The flood is gone — the shortlist became a diverse set of distinct
stories, each carrying its co-occurring members: `keith urban +{nicole kidman,
…}`, `ECON_DEBT +{WB_450_DEBT, …}`, `NATURAL_DISASTER_VOLCANIC +{VOLCANO,
VOLCANOES}` (morphological variants merged cleanly), `POWER_OUTAGE +{SNOWSTORMS,
…}`. Co-occurrence dedup turns raw entities into information objects. Validated.

**New problem exposed.** With the story flood cleared, the remaining entity noise
became visible: **media-attribution artifacts** — `getty imagespascal
lesegretain`, `getty imagescredit` (photo credits extracted as entities), plus
generic org fragments. → Iter 4.

---

## Iteration 4 — entity noise filter (media attribution)

**Change.** New `discovery/noise.py` consolidating the vocabulary stoplists
(moved the boilerplate-theme list here too, so all noise rules live in one
reviewable place). Added `is_noise_entity` filtering photo/wire-credit artifacts
(Getty Images, Reuters, AFP, Shutterstock, "credit:", …) and degenerate
entity strings. Applied in candidate extraction and the per-language view.

**Result (fresh 8-batch sequence).** Media-credit junk gone. The shortlist now
reads as real, specific, corroborated information objects:
`WB_445_FISCAL_POLICY +{buckingham palace reservicing programme, king charles}`
(UK royal-finance story), `DISCRIMINATION_RACE +{catriona paton, police scotland,
john swinney}` (Scotland policing story), `UNGP_TRANSPORTATION_ROADS` (langs=5,
tone=−5.1, cross-language road-safety), a coherent agriculture cluster
(fertilizers/irrigation/crop-production, all cross-language). Cross-language
corroboration is prominent at the top; entities attach as story context.

**Residual noise noted (not yet acted on, to avoid over-fitting):**
- News-outlet names extracted as entities (`akita sakigake shimpo` = a Japanese
  newspaper) — a *source*, not a topic. Candidate for a future outlet stoplist;
  left in for now since it's low-frequency and outlet lists risk over-fitting.
- Representation is theme-anchored (entities ride along as related). Acceptable —
  the entity context is preserved; surfacing entities as primary is a future knob.

---

## Iteration 5 — cold-start warmup (make the *live* command high-signal on run 1)

**Problem.** The replay proves the signal, but a fresh `insights` call has no
memory, so velocity is unavailable and the score falls back to volume — the rut.
The tool would only become good after ~8 live runs accumulated baselines.

**Change.** Added `insights --warmup N`: when invoked, backfill rolling memory
from the N preceding historical batches (via `fetch_batch`) before scoring the
latest, so the very first run is already velocity-aware. Explicit flag (no
surprise downloads); documented as the bootstrap step.

**Result.** Cold start (fresh memory) with `--warmup 6` produced
`has_velocity_baseline: true`, 39/40 candidates rising, 6 batches warmed — the
first live run is already velocity-aware, no longer falling back to the volume
rut. Bootstrap validated.

---

## Current state & reliability notes (end of this pass)

**Where it landed.** Across iterations 1→5 the GKG channel went from "broad
declining themes / one-story floods / PR spam / photo-credit junk" to a diverse
shortlist of **specific, corroborated, rising information objects**, each a story
with its co-occurring entities attached (`WB_445_FISCAL_POLICY +{buckingham palace
reservicing programme, king charles}`, `DISCRIMINATION_RACE +{police scotland,
john swinney}`, agriculture and natural-disaster clusters, …). Cross-language
corroboration leads; isolated single-language spikes are demoted, not surfaced.

**Reliability.**
- *Deterministic*: the core (`extract_candidates` → `score` → `select` →
  `build_insights`) is pure; identical batches → identical report. Only `memory`
  carries state, and it's append-trim with a fixed window.
- *Reproducible evaluation*: `scripts/discovery_eval.py` + `replay.py` re-run the
  same cached sequence offline, so any future parameter change can be compared on
  identical data. Caveat: a no-arg eval uses the latest available window (data
  moves); pin batch ids in the cache for strict A/B.

**Tunable knobs (all in `ranking.py` / `noise.py`, one place each):**
`MIN_RISING_COUNT`, `VELOCITY_CAP`, the three blend weights, `OVERLAP_THRESHOLD`
/ `MAX_RELATED` (dedup), and the noise stoplists. These are the levers to revisit
if we later find we over-fit to a shape we don't want.

**Known limitations / over-fitting watch (deliberately left for later):**
1. **Theme-anchored representation** — stories surface under their dominant theme
   with entities as `related`; we don't yet promote entities to primary or build
   true entity-centric story objects. The richest "information object" form is a
   future iteration.
2. **News-outlet names as entities** (`akita sakigake shimpo`) — a source, not a
   topic. Left unfiltered to avoid an over-fit outlet blacklist; revisit if it
   proves frequent.
3. **NGrams is sample-only** — the second channel currently feeds the long-tail
   slice, not its own velocity/emergence signal. A deterministic NGrams
   trending-phrase channel (with the same memory mechanism) is the next big lever.
4. **Per-language velocity** — the world-news view is volume-only per language;
   per-language rising needs per-(language,candidate) memory keys.
5. **Single-language English breaking news** is demoted by the breadth weighting —
   precision-over-recall choice. If we find we're missing real early English-only
   stories, relax the breadth multiplier or add a source-spread corroboration path.

These are recorded so a later review can see *which* deliberate choices shaped the
output, and undo any that turn out to bias us toward an unwanted information shape.

---

## Iteration 6 — NGrams emergence: empirical probe + decision (not yet shipped)

**What we tried.** A throwaway probe of an NGrams emergence channel: fetch a few
consecutive minute batches, clean tokens (strip punctuation, drop short/stopword/
non-capitalised), count per token, velocity = last vs prior-mean. Goal: see if a
deterministic "trending phrases" signal is high enough quality to ship as the
second channel.

**What it showed (real, but immature).** It does catch live things fast: the top
emergers were a live Premier League match (`Bournemouth`, `Wolves`), tennis/music
names (`Osaka`, `Naomi`, `Keys`, `Alicia`), and brands (`Albertsons`, `Spectrum`,
`WD-40`, `Vanderbilt`). So per-minute NGrams genuinely surfaces emerging events
GKG's 15-min coded themes would lag. But the quality isn't there yet:
- **Word-level lacks context** — `Naomi`/`Osaka`/`Alicia`/`Keys` are really "Naomi
  Osaka" and "Alicia Keys". The signal needs **phrase reconstruction** (chain
  adjacent tokens sharing a `url` by `pos`) to become named entities.
- **Noise**: sentence-initial capitals and single-article bursts (`Algebra`,
  `Applied`, `ARRAY`) leak through a pure capitalisation heuristic.
- **Skew**: heavily sports/entertainment.
- **Operational**: minute files publish *partially* (caught one at 222k vs 865k
  records) and aren't always present — velocity is skewed unless we gate on a
  settled, complete batch.

**Decision.** Do **not** ship a half-tuned second channel — it would contradict
the "reliable / high-signal" bar and invite over-fit heuristics. NGrams stays in
its current deterministic role (the language-stratified anti-rut **sample**),
which is a deliberate, useful processing of the channel. The emergence channel is
scoped as the **defined next iteration** with a concrete, non-hand-wavy plan:

1. **Phrase reconstruction** — group a batch's records by `url`, order by `pos`,
   chain runs of capitalised tokens into phrases (named entities) before counting.
2. **Proper-noun gating** — use `pos` to drop sentence-initial false capitals;
   require min support; for non-Latin scripts fall back to raw-token frequency
   (capitalisation is Latin-only).
3. **Settled-batch gate** — only process a minute once its record count looks
   complete (vs the running norm), to avoid partial-publish velocity spikes.
4. **Same memory mechanism** — reuse `RollingMemory` keyed per phrase for velocity,
   exactly as GKG does, so the two channels share one signal model.
5. **Evaluate via replay** on a real minute-sequence before shipping, same as GKG.

This keeps the deterministic system honest: GKG is the shipped high-signal
channel; NGrams emergence is a scoped, evidence-backed next step rather than a
rushed addition.

---

## Iteration 7 — targeted beat sweeps (the DOC API "scalpel" beside the net)

**Why.** The general GKG net finds broad thematic trends but leaves niche
coverage to chance ("India economics" only shows if the sweep happened to contain
it). To guarantee per-niche freshness we add *targeted* fetching: a registry of
addressable **beats** (pillars + per-country general), each fetched on purpose via
the free GDELT DOC API. Floors-by-construction: every beat gets its own query, so
a niche is never starved. Deterministic — no LLM in the sweep.

**DOC API facts established by probing (the non-obvious ones):**
- Filters live **inside the query string**: `theme:ECON_STOCKMARKET sourcecountry:China`
  (country by *name*). A separate `sourcecountry=` URL param is silently ignored.
- `sourcecountry:Japan` as a standalone query returns that country's general feed
  (verified: 8/8 Japan sources). `sort=datedesc` for recency, `timespan` window.
- The **rate limit is strict and stateful**: ~1 req/5s, and bursting escalates a
  cooldown such that even an 11s retry can still 429. So the sweep paces (~6s),
  backs off (~15s) + retries once on 429, then records the beat's error and moves
  on. A skipped beat is fine — the floor/refresh model fills it next cycle. A full
  ~40-beat sweep therefore takes minutes by design (not interactive).

**Beat suite (my call, per "make solid pillars you think are good").** ai,
technology, economics, finance, geopolitics, politics, world_events, science,
health, energy — with economics/finance/geopolitics as the intended strength
cluster. Plus ~30 per-country general beats (top news producers), widenable later.
Pillar queries are broad keyword/theme sets; overlap is fine because hits are
**multi-tagged, not bucketed** (an AI-chip story tags both ai and tech), so the
BeatSheet slices downstream by pillar/country.

**Architecture (the future-proofing).** A beat is an addressable spec with
*pluggable fulfillment*: today a targeted DOC query; later a dedicated agent — same
registry, swap the backend. The sweep orchestrator is pure over an injected
`search` + `sleep`, so it's fully testable offline. Output is a `BeatSheet`
(tagged hits), retained one-in-one-out beside the GKG insights.

**Result (live subset).** A first 3-pillar sweep (`datedesc`) worked end-to-end —
18 hits across India/Chile/Morocco/Colombia/US — but relevance was loose: a broad
keyword OR-query sorted by recency returns the *newest loosely-matching* articles
(the AI beat surfaced a Stripe piece and Chilean bomb threats). **Fix:** pillars
sort by `hybridrel` (relevance), country beats keep `datedesc`. Re-run: the AI
beat became genuinely on-topic and multi-country — Getty/OpenAI deal, OpenAI–
Samsung, Russia's foreign-neural-net policy, AI tort litigation. High-signal.

One beat returned **0 hits with no error**, which exposed a reliability gap: a
non-JSON 200 body (GDELT soft-throttling) was being parsed as an empty result,
masking a throttle as "no news." Hardened `gdelt_doc` to raise on a non-JSON body
so the sweep records it as a (retryable) failure — a genuine empty list still
reads as 0. So "0 hits" now always means *no news*, never *silently throttled*.

**Net.** Two complementary deterministic channels now exist: the GKG **net**
(broad, tagged, velocity-ranked information objects) and the DOC **scalpel**
(targeted per-beat hit sheets, relevance-sorted, guaranteed niche coverage). Both
no-LLM. The beat registry is the seam where coverage grows and where fulfillment
later swaps to agents.

**Residual / next (recorded, not over-fit now):**
- Pillar **query specs are first-draft** — broad keyword sets. They're the obvious
  tuning surface (tighten phrases, add `theme:` operators) as we see real sheets.
- **No cross-channel merge yet** — GKG net and the beat sheet are separate
  artifacts; unifying them into one tagged pool with floor+proportional allocation
  (the earlier design) is the next integration step.
- **Velocity on beats** — DOC `timelinevol` could add per-beat rising/falling, at
  the cost of a second query per beat (rate-limit pressure). Deferred.

---

## Iteration 8 — pool consolidation (leg 1 of the funnel)

**Why.** The net and the sweep are two differently-shaped artifacts. The synthesis
(discovery) agent should read *one* grounded, tagged tray, not juggle both.

**Change.** `discovery/pool.py` folds the latest `InsightsReport` + `BeatSheet`
into one `DiscoveryPool` of uniform `PoolItem`s, with a pillar facet index. CLI
`pool` consolidates the on-disk artifacts (deterministic, no LLM).

**Deliberate scope decision (the over-fit-watch entry).** We do *not* attempt
deterministic cross-channel **fusion** (matching a GKG theme-aggregate to a beat
article as "the same story"). There's no shared key — beat hits carry no GKG
themes — so reliable linking isn't possible deterministically. So the pool only
*organizes and grounds*: normalise both channels to one shape, dedupe beat
articles recurring across beats (merge their pillars), align the trivially-
overlapping pillar names (`economy`→`economics`), and index facets. The actual
*weaving* of related items into research vectors is the agent's job (it can read
titles), which keeps deterministic claims honest and traceable.

**Result (live).** 46 items (40 GKG objects + 6 beat articles), faceted
economics 13 / ai 6 / politics 3 / … Untagged GKG items (GKG's pillar vocabulary
is narrow) are left for the agent to tag semantically. This is the discovery
agent's input tray — leg 2 is the agent that turns it into a research-vector
portfolio.

**Noted follow-up:** GKG items aren't yet grounded with article URLs (the net's
candidates are aggregates); beat items are. Threading a few example source URLs
onto GKG candidates is a small leg-2 enabler so every pool item is clickable.
