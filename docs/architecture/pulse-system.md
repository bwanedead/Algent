# Pulse system — architecture

> Canonical reference for Ohmega's persistent belief states. Vision: `docs/vision/ohmega-intelligence-engine.md`.
> Code: `backend/algent_backend/agent_system/agents/pulse/`. Schema: `backend/migrations/`.

## The objects

| Object | What it is | Example |
|---|---|---|
| **Situation** | an enduring real-world subject; domain-agnostic; can split and merge with provenance | Russia–NATO |
| **Pulse** | one assessed dimension of a situation, measured against a versioned, anchored ruler | Russia–NATO · military confrontation |
| **Definition** | the ruler: the question plus anchors (what 0/25/50/75/100 mean, with historical examples); new versions are appended, never edited | v1, v2… |
| **Event** | a canonical real-world occurrence, so fifty articles about one incident update a Pulse once | Sep 27 arrests near RAF Fairford |
| **Influence** | one immutable log entry: something touched a Pulse, including "no material change" | article run 0103 held the position at 62 |
| **Watch** | a forward condition with linked Pulses, expected direction, horizon and one-way resolution | permanent Russian basing in Belarus |

Three kinds of change are kept apart: an **influence** (evidence considered), a **value move**
(61 → 66, which feeds velocity and sparklines) and a **band change** (elevated → severe, the
publishable subset).

## Rules the design encodes

- **The log is the truth; state is a projection.** A Pulse's position, band, velocity, history
  and band changes are computed by replaying its influences (`pulse/projection.py`). "What did we
  believe on Aug 14?" is the same replay with a cutoff. A cached current state in the database
  is only a speed-up and can always be rebuilt.
- **Position, not delta.** Assessments propose where the Pulse sits against its anchors. The
  position is the latest *applied* proposal. Repeated news cannot ratchet the value.
- **Versioned rulers.** Every influence records the definition version it was made under.
- **Idempotent history.** An influence's key is `pulse + event + run + mode`. A retried run
  cannot write the same act twice; the store and the database both refuse it.
- **Blind reassessment.** On a schedule, a Pulse is re-scored *without* seeing its prior. The
  gap is stored; a gap wider than one band flags `needs_reconciliation`, resolved by a full
  reassessment. The two are never silently averaged.
- **Confidence keeps its reasons:** evidence quality, coverage and agreement, compressed to
  high/medium/low only for display.
- **Freshness is coverage, not age.** It shows evidence covered through a date, plus the count of
  relevant events not yet processed. The daily headline radar can raise that count (the
  Pulse is going stale) but can never move a position: unverified headlines are not evidence.
- **Pulse never fetches the web.** It consumes research the newsroom has already graded.

## Flows

| Flow | Trigger | Does |
|---|---|---|
| Seed | once per situation, reviewed by a human | Defines Pulses and anchors; sets starting positions citing claims; opens initial watches |
| Article update | after each article run | Finds the situations and event the story touches; proposes positions for touched Pulses; checks watches; always logs, including no-change |
| Radar freshness | every daily headline scan | Counts unprocessed relevant events per situation; moves nothing |
| Weekly reassessment | scheduled | Runs an anchored pass and a blind pass; records the anchoring gap; expires or keeps watches |

## Storage

- **Live store:** managed Postgres (Supabase as the host; no Supabase-specific features in the
  core). Pulse objects are relational from day one. Research profiles start as JSONB documents
  plus indexed fields; claims, sources and entities are extracted when a query needs them.
- **Schema lives in migrations** in `backend/migrations/`, applied in order by a small runner
  that records what has run. Tables are never created by hand.
- **Access** goes through repository interfaces. The file-backed `PulseStore` is the reference
  implementation and the test double; a Postgres implementation sits behind the same surface.
- **Access classes:** the backend holds the only write credential. The public site reads only
  published objects through row-level-security policies. User data comes later.
- **Archive:** the private `bwanedead/algent-data` repo mirrors the stores after every run and
  menu build. It only adds and updates files, never deletes. It is the independent
  disaster-recovery copy.

## Rollout

1. Contracts, the file store and the projection, with tests. *(done)*
2. Postgres migrations *(written: `backend/migrations/`)* and runner *(done)*; the Postgres
   repository and the corpus load wait on the driver install and `DATABASE_URL`.
3. Seed the first ten situations; review with the operator; persist. *(`newsroom pulse seed` →
   review → `newsroom pulse commit`; seed doctrine v2 after the first review found circular
   anchors, mixed ruler direction and duplicate Pulses across situations)*
4. Article-update hook *(wired into the rail)*, radar freshness *(wired into menu builds)*, weekly
   reassessment with blind pass *(`newsroom pulse reassess`)*, watches. *(done)*

Seeding rules learned the hard way: anchor examples must predate the evidence (a ruler built from
today's events measures nothing); every ruler runs 0 = calm → 100 = extreme; one dimension gets
one Pulse across all situations.
5. A private calibration period (1–3 weeks): nothing published externally. Check how often
   Pulses move, whether anchors are applied consistently, the anchoring gaps, and whether events
   are mapped to the right situations.
6. Public: the Pulse Gallery, embeds, JSON twins, X posts on band changes.
