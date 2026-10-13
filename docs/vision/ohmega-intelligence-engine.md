# Ohmega Monster — the intelligence engine

> Canonical vision for what Ohmega is becoming. Architecture lives in
> `docs/architecture/pulse-system.md`; editorial doctrine lives in the newsroom's `spirit.md`.
> Extend this doc rather than starting a parallel one.

## What Ohmega is

Ohmega is not an AI news site. It is an **intelligence engine**: a system that continuously takes
in noisy external reality, pulls signal out of it, checks it, grades it, and keeps what it learns.
Articles are one output of that engine. They are not the engine.

The durable asset is the **accumulating model of the world** underneath the articles:

- **graded claims** (confirmed, likely, contested…) with sources, snapshots and as-of dates;
- **situations**: enduring subjects like Russia–NATO or China–Taiwan, which stories attach to;
- **Pulses**: persistent, auditable belief states about those situations, revised as evidence
  arrives, each with a full history of what moved it and why;
- **watches**: forward conditions whose outcomes teach the system how well it reads the world;
- a visible **corrections record**.

Prose is being commoditised. Graded, sourced, dated, revisable judgment is not.

## The loop

A media organisation does *observe → publish*. Ohmega does:

    observe → research → grade → update the model → publish → feed the result back into the model

Every article run leaves the model a little better informed. The next run starts from what we
already know instead of from zero. That is what makes the system **compound**: research gets
cheaper per article, judgments get steadier, and the history itself becomes valuable.

## The products are views onto one substrate

| Surface | For | What it shows |
|---|---|---|
| Articles | people | one story, researched, graded, readable |
| Headline radar | people | what crossed the wire today, clearly marked unverified |
| Pulse Gallery | people | the wall of Ohmega's current reads, with movement and confidence |
| Atlas (working name) | people | the geopolitics surface: situations on an off-axis globe |
| Intelligence desk (/intel) | people | Pulse board, emergent theaters and their heat, deep briefs, the forecast track record |
| Daily report (/geopolitics) | people | the daily curated rundown per theater: who said what, what happened, the older context that explains it, temperature, Pulses, outlook, maps |
| Agent API / MCP | AI agents | dossiers, claim checks, Pulse states, what changed |
| X | people | articles, the daily radar, and Pulse state changes |

The agent-facing product matters as much as the human one. Agents want the ledger, not the
prose: "what is established about X as of today, on what evidence, and how sure are you?"

## Principles that do not bend

1. **Legible trust, not borrowed authority.** Every reading shows how sure we are and how fresh
   it is. We say "Ohmega's current assessment", never "the truth". Unverified headlines can make
   a Pulse *stale*; only researched evidence can *move* it.
2. **Position, not mood.** A Pulse is a position on an anchored ruler, re-estimated each time,
   never a running sum of reactions to news. News over-reports escalation; the design must not
   inherit that.
3. **Nothing is overwritten.** Profiles, Pulse influences and corrections are append-only. The
   history of what Ohmega believed, and why, is part of the product.
4. **Self-audit.** Blind reassessments check whether our own priors have captured us. Watches
   check whether our forward reads were useful. Disagreement is a signal to surface, not hide.
5. **The reader's words.** Internal vocabulary (vectors, profiles, gauntlet) never reaches a
   reader. Neither does a source's regional idiom.
6. **Domain-agnostic machinery.** Geopolitics is the first domain. The same Situation/Pulse
   machinery must carry sports, markets or technology later without being rebuilt.

## For agents, today

Every published article has a machine-readable twin at `/data/articles/<slug>.json` (schema
`ohmega.article/1`: graded claims, citable sources only, corrections), indexed at
`/data/index.json` and described in `/llms.txt`. Source texts are never republished: we expose our
claims and link to theirs. Pulse states join this layer once the calibration period ends.

## The intelligence desk: craft over resources (operator, 10-01)

Our edge is analytic craft, not data access. The desk runs on the radar's headlines plus our own
graded research, and earns trust the way the best analytic shops do:
- **Emergent theaters.** Nothing is hard-coded to a conflict. Theaters are found in what is being
  reported, measured by their *share* of coverage (not our publishing cadence), and they persist or
  fade on their own. A theater that lasts becomes a Pulse situation.
- **Briefs are intelligence, not articles.** Researched facts kept apart from reported headlines;
  estimative language; continuity (lead with what changed since our last brief); indicators tracked
  by their exact wording over time; a red team of competing explanations weighed by what the
  evidence rules out; what would change our mind.
- **Scored forecasts.** Every brief makes falsifiable, dated, probability-tagged judgments into an
  append-only ledger. A scorekeeper settles them against supplied evidence only, and the public
  track record (Brier score, calibration) is shown on the site. The analyst sees its own misses.
- **The daily report** is the regularly produced product (run like an article run): per theater,
  the substance of what happened and who said what, older items that explain today, temperature,
  Pulses with their 24h/7d moves, outlook and what to watch, and maps where they make it clearer
  (front lines and day-over-day territorial change for Russia–Ukraine first). Maps are only drawn
  from sources we may lawfully reuse, credited, and accurate enough to stake the brand on.
  A fault in one theater never costs a whole new run: `intel daily --date D --theater <id|name>` rewrites only
  that section of the day's existing record (every other section, the sweep and the spotlight stay as they were),
  republishes, and notes the correction (when, why) in the record's `corrections`. `--repair` reuses the saved
  research and, when its claims lost their links to their sources, ties them back with one cheap call (no new
  research); research runs only if nothing is saved or `--fresh-research` is given.
  **Paid model work is kept, not re-bought.** The daily's guards are destructive (a place off the basemap, an
  uncited source are dropped from the published section), so every model output the day used (section drafts,
  the summary, the sweep) is saved raw, with the inputs the guards need, in `intel_store/daily_drafts/<domain>/<date>.json`
  (internal; never mirrored to the site). `intel daily --date D --rerender [--theater ids]` re-derives the
  record from it with zero model calls: guards, places and maps, numbers panels, Pulse table, on-record
  order, the summary's cross-theater links and the sweep's validation. So fixing the environment (a missing
  basemap) or adding a display feature costs nothing. For a report made before drafts were kept,
  `--tag-places` is a one-off repair: one low-effort call per report places the existing developments (text
  untouched, every place checked against the basemap, maps rebuilt).
- **The daily explains itself to a newcomer** (operator, 10-11). Three reader aids, none of which costs a model call:
  (1) every theater section opens with a `saga`, 1-3 plain sentences of big picture (who is against whom, since when, why it
  matters) under its headline. The writer produces it inside the section call it already makes, grounded on the theater's
  stored primer (`primers.py`, written once a week for the dossier) when there is one, and leaves it empty for a one-off event;
  an older record with no saga shows the first sentences of the dossier primer instead. It lives on the draft, so `--rerender`
  carries it. (2) One glossary: the instrument catalog's `Series.plain` (and `actors/plain.py` for annual statistics) is
  published inside the record as `tracker.plain` / `metric.plain`, and the site's `lib/glossary.ts` holds the desk and
  interface terms; both surface through a dotted-underline or corner "i" hint (`Tip.tsx`, `Term.tsx`) that opens on hover,
  tap or keyboard, at most two sentences each. (3) The strip under the title says when the report went out ("Published 05:30 UTC
  · updated 17:30 UTC", from each cycle's `built_at`), never "part 1/2". The section `headline` (one complete sentence) is
  requested of every writer, part two's updates and new sections included.
- **Pulses grow from the work.** Every daily report and brief feeds research into Pulses; when a
  theater bears on a dimension no Pulse measures, the writer proposes one, and proposals become
  stable Pulses through a registry agents can also read and propose to (one dimension, one Pulse).
- **The recipe is domain-generic.** Geopolitics first; the same machinery serves medicine,
  politics, sports.

## Sensing: from headlines to the record (operator, 10-04)

Diagnosis. The desk only knows what the headline radar happened to catch, one edition a day of
roughly 40 headlines. Heat is measured on single-digit counts. A whole register of evidence never
arrives: what leaders actually said (a long Putin speech, NATO's chief, European leaders on troops in
Ukraine), and the hard numbers a situation moves (ship transits, prices, storage, yields). Daily
reports read alike because the same thin input is re-summarised. Research is starved by paid search
quotas, and starved agents guess URLs. In the 10-01 to 10-03 runs, 77% of page reads failed, mostly on
URLs the agent made up. The fix is more and better sensing, not more prose.

Three sensing layers, each its own module, each free at the margin, each feeding the same model of
the world:

1. **Free search and honest reads.** Free engines (DuckDuckGo HTML, Google News RSS) answer first,
   and paid engines become the fallback. A read that hits a missing page says so plainly ("does not
   exist: find it by search, do not construct URLs") and is never escalated to the paid crawler.
   Abundant search is what lets research find the actual transcript instead of a summary of it.
2. **Instruments: the numbers layer.** Programmatic, no model: a catalogue of series (chokepoint
   transits from IMF PortWatch, energy prices, EU gas storage, yields, FX, inflation, debt,
   prediction-market odds, quakes...). Each series is fetched on a schedule into an append-only
   store and tagged to the regions and dynamics it bears on. The desk gets "what moved": changes
   against each series' own history, flagged when unusual. Instruments are evidence with a URL and an
   as-of date, so they ground research for free. They are the natural substrate for later Pulses and
   watches ("Hormuz transits back above 50/day"), and Pulses consume them only once that design is
   settled.
3. **Statements: the record of who said what.** Primary-source transcripts and official statements
   (Kremlin, White House, State Department, UK government, UN, foreign ministries, NATO), collected
   independently of which theaters are hot, plus a free news search for major leaders' remarks. An
   extractor turns each into a ledger: actor, role, date, exact wording where wording matters, the
   relationship it speaks to (who about whom), and what kind of signal it is (threat, commitment,
   red line, offer, reassurance, shift in tone). Rhetoric is a leading indicator. The ledger lets the
   desk see a tone shift against the speaker's own earlier statements, and it makes the dynamics
   between powers (Russia–NATO, Russia–EU) visible even on days without a kinetic event.

Then the desk changes how it reads. Heat comes from a broad base (GDELT GKG, Wikipedia Current
Events), not our own radar. The daily and the briefs get three evidence blocks (researched claims,
instrument moves, statements on record), so a day with no new strikes still has texture. Maps become
utilitarian instruments: a light, legible base, readable labels, rivers and chokepoints, a scale and an
inset, and overlays that carry data (transit counts at the strait, not just a dot). Pulse logic is
left alone until its next design pass. The ideas parked for that pass: Pulses seeded from instruments,
and a reassessment that reads the condensed state plus new evidence rather than a raw re-read of the
whole history.

## Depth: from dashboard to model (operator, 10-04)

North star, in the operator's words: understand the larger, complex dynamics of the world more
accurately — acquire, research, process and present information so it is maximally useful for
understanding them. The dashboard (/geopolitics, /intel) is the right FIRST surface; it must be the top
of a stack the reader can descend, never the whole of it:

    day (what changed) → theater (the dynamic, its record, its numbers, its map)
      → actor (what this power is: people, economy, energy, military, leaders, what it has said)
      → record (every statement and reading, filterable) → source

- **Actors are modelled.** Every state the desk touches has a power profile built from open data
  (World Bank, Our World in Data energy, Wikidata leaders, IMF): population, GDP and GDP per capita,
  growth, debt, trade exposure, energy produced and consumed by fuel, military spending and size, who
  leads it. A theater shows its actors side by side on shared scales, so the reader sees the balance of
  power, not just the news. Non-state actors follow from the research corpus.
- **The record is visible.** What leaders said is shown as what they said: speaker, office, flag,
  date, the exact words where they matter, the link — deterministically selected from the statements
  ledger for each theater and actor, not left to a writer's choice. Tone toward a counterpart is a
  series the reader can follow.
- **Focus follows the world.** Theaters enter the day's focus when something new happens (headlines,
  statements, unusual readings, our library) and leave it after a week with nothing new, kept on a quiet
  strip with their last change and still one click deep. Detection draws on a broad base, not only our
  own radar.
- **The world is swept, not only focused (operator, 10-10).** Heat x novelty favours volume, so the same loud
  theaters returned daily while subtle, consequential dynamics (Africa, Asia, Latin and Central America, the
  Arctic, space) never got attention, and researching everything is neither affordable nor fast. The daily
  therefore adds, after the focus, an "Around the world" sweep: ONE house-model call over the last ~48h of
  material the desk already holds for free (headlines of theaters not in focus, recent library titles no
  theater claimed, the statements ledger, flagged instrument moves) that writes a short region-grouped digest.
  Regions are a scaffold, not a quota (empty is a finding); each item is one sentence with the countries
  involved and the source links it rests on, and an item without a source from the material is dropped. The
  same call may nominate ONE **Spotlight**: the item most deserving depth that the daily has not covered in the
  last week; with `--research` it becomes one extra researched section (a board theater if it is one, else an
  ad-hoc theater built from its headlines; no Pulses are created). One extra section per run is a flag
  (`intel/flags.py`: `SPOTLIGHT_SECTIONS`), a budget decision. Code: `agents/intel/sweep.py`. A world map with
  pins for sweep items is a follow-up; today the site shows a region-grouped list with flags.
- **Names are explicit.** A Pulse, a theater or a figure says who and what in its title (flags allowed):
  "🇺🇸🇨🇳 US–China: diplomatic deadlock", never a bare "Relationship deadlock" the reader must click
  to decode. Clicking gives the definition, not the identity.
- **Territory is shown honestly.** Disputed and occupied areas from public-domain data; front lines only
  from a source we are licensed to redraw (DeepState, on written permission); otherwise our own dated,
  researched event points, labelled as such.

## Research subdivision: Ohmega Research

Ohmega Research is the subdivision that conducts **reproducible studies** of AI systems: a
prespecified protocol, auditable trial records, and analysis under stated rules. Its first
program is the **non-interference goal frontier**. That program asks how far a tested system
(model + harness + settings) carries a goal to completion without human intervention, within
an assigned budget. Goal distance is a prespecified vector of task demands, not human task
duration. Research follows the same trust rules as the rest of the engine: every terminal
trial recorded, rescued runs never counted as unaided, unknowns kept visible, and no growth
claim without matched cohorts. Today it has instrumentation (trial contract, validator,
offline report, a synthetic demo) and one third-party source audit; its standardized trials
are still synthetic. The clean `analysis.json` export is meant to feed a future `/research`
page. Canonical doc: `docs/vision/ohmega-research.md`.

## Where it is going

- **Now:** the Pulse layer (situations, Pulses, events, watches) on a real database, seeded from
  the existing research corpus, running privately while it calibrates.
- **Next:** the Pulse Gallery, Pulse embeds in articles, the geopolitics surface, and a
  machine-readable twin of everything for agents.
- **Later:** an agent API and MCP server, calibration reports ("when we said severe, what
  happened?"), user-followed and user-authored Pulses, possibly Ohmega Sports on the same
  machinery, and eventually metered agent access once there is measured demand.

The phrase to keep in mind: **a continuously revised, provenance-bearing model of the world**,
with everything else a way of looking at it.

## Live listening

The desk no longer only reads the news: the worker server listens 24/7 to free live data (internet outages, earthquakes,
military ADS-B, satellite fire hotspots, AIS ship traffic at chokepoints) and computes our own series from it. Those series
join the instruments layer (so numbers, freshness and moves machinery see them) and live events reach the section writers
with a public source URL, so a daily can say "IODA shows a nationwide outage in X since 14:00 UTC". Readers see the same
data on the /live page. Details: `docs/guides/worker-server.md` (Live feeds).

## Runway: what we build next, and why (operator, 10-12)

**Original intelligence.** Two kinds of knowledge compound here. *Aggregated* intelligence gathers what others found
(news, statements, official statistics): context, breadth, inputs. *Original* intelligence is what we derive ourselves
from raw signals: our own chokepoint counts, baselines and anomalies, a ship that went dark, a site that changed
between satellite passes, a forecast that settled. Grow the original-intelligence surface steadily; label it on the
site and API as Ohmega-derived; track how much of each daily rests on our own signals.

**Priority tiers** (value = uniqueness × compounding × feeds-existing × visible wow, over effort):
1. *Tier 1, next:* live feeds into memory + anomalies (grid baselines by hour/weekday, flags high or low, daily
   rollups and anomalies stored in the corpus, linked to theaters/actors, fed to the writer); a "what's coming"
   calendar + sanctions and diplomatic events; shadow-fleet and maritime behaviour from our own AIS (dark gaps,
   ship-to-ship transfers, loitering, flag hopping).
2. *Tier 2:* satellite imagery change detection on watched sites (free Sentinel); GPS jamming + military flight
   patterns; physical-economy dashboard (freight, commodity flows, grid stress, night-time lights).
3. *Tier 3:* state-media narrative tracking; human and environmental stress (displacement, outbreaks, food,
   water); tech and space; ownership and finance networks.
Alongside: views beyond maps (country dashboards, calendar, anomalies page, timelines, relationship graphs),
tasteful 3D where a story warrants it, and every new dataset flowing to the agent API/MCP.

**The globe viewer (soon, not now).** A spinnable globe, Google-Earth-style navigation but in our illustrated line-art
style rather than satellite imagery, where each country's fill is set by *information channels*: what's new there,
how recent our latest coverage is (fresh vs stale), by category (conflict, economy, politics, disaster…), with
context on tap. Scrub around the world, look top-down at a place, and read what's happening there while rooted in
its geography. Overlays as further channels: resource and trade flows as animated directional routes (wheat, oil,
LNG, metals, GPUs/chips: the economic pipes), chokepoints, traces, live layers. Why it matters: ergonomics as a
reasoning aid. Seeing trackables in spatial relation to each other helps build and retain a model of how their
states affect one another, which is what a model *is*. Start soon after Tier 1; reuse the live map, the globe
spinner's projection, and the corpus's per-country recency.
