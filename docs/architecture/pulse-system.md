# Pulse system — architecture

> Canonical reference for Ohmega's persistent belief states. Vision: `docs/vision/ohmega-intelligence-engine.md`.
> Code: `backend/algent_backend/agent_system/agents/pulse/`. Schema: `backend/migrations/`.

## The objects

| Object | What it is | Example |
|---|---|---|
| **Situation** | an enduring real-world subject; domain-agnostic; can split and merge with provenance | Russia–NATO |
| **Pulse** | one assessed dimension of a situation, placed between a calm (0) and an extreme (100) end | Russia–NATO · military confrontation |
| **Definition** | the frame: the question plus what the calm and extreme ends look like; new versions are appended, never edited | v1, v2… |
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
- **The scale is the Pulse's own history (doctrine v3).** Only the direction and the two ends are
  fixed. Each reading is placed by comparison with the Pulse's past readings and their reasoning
  ("worse than when we said 58 on Aug 14, because…"), so the scale grows from experience and flexes
  with a messy world instead of being boxed into the first seed's picture. Fixed 0/25/50/75/100
  anchors were tried first and dropped for exactly that reason.
- **History is memory, not truth: absolute votes (doctrine v4).** Every reading also gives an
  `absolute_position`: where the reader thinks reality sits if the history is ignored. No reader
  holds the whole picture. The Pulse *is* the net of many partial readings (articles, radars,
  side research), and holding the whole graph in one agent would be neither possible nor
  economical. So a vote never moves the Pulse. Instead, the latest vote of each of the recent
  independent sources (`projection.absolute_votes`; one research effort = one voter) is shown to
  every later reader beside the past readings, with their collective view: a median weighted by recency rank, so newer votes count for more but no single vote decides. There is no arbiter above the collective; the weekly reassessment is one more reader. When readers working from
  different research keep pulling the same way, the history has drifted, and the next reading
  moves toward them and says why. A sharper model corrects the record the same way, at the pace
  the evidence it touches allows. An adjudicator that "sees everything" was considered and
  rejected for that reason. Both numbers stay on every reading, so once watches resolve, how much
  each kind of reading deserves can be *scored*, not guessed.
- **Position, not delta.** Assessments propose where the Pulse sits. The position is the latest
  *applied* proposal. Repeated news cannot ratchet the value.
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

Seeding rules learned the hard way: every Pulse runs 0 = calm → 100 = extreme (name "good-high"
dimensions from their risk side); one dimension gets one Pulse across all situations, and the catalog
order decides which situation owns a shared one; the blind check is what keeps a history-measured
scale from drifting, so it must never see the history.
5. A private calibration period (1–3 weeks): nothing published externally. Check how often
   Pulses move, whether anchors are applied consistently, the anchoring gaps, and whether events
   are mapped to the right situations.
6. Public: the Pulse Gallery, embeds, JSON twins, X posts on band changes.
