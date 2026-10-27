# Experiment framework (phase 1: design and a minimal vertical slice)

> Code: `backend/algent_backend/experiment/`. Registry product `experiments` (manual, off by default, not backed up). CLI: `newsroom lab ...`. Tests: `tests/test_experiment_lab.py`.
> Philosophy: `docs/vision/world-model.md` v2 ("preserve evidence, version interpretation, isolate experimentation, judge methods by their consequences").
> **Safety rule: additive and isolated.** No bot, the corpus index, publishing or the site imports this package. It only *reads* the markets store and the corpus index.

**Governing requirement: every major choice in constructing an intelligence is identifiable, versionable and, where feasible, replaceable.** A choice that
cannot be named in a manifest (a prompt edit, a retrieval heuristic, a memory rule, a model swap) is not yet an experiment variable, and the framework treats
that as a defect to fix, not a detail.

## 1. Layers and boundaries

| Layer | What it holds | Writes | Who may read |
|---|---|---|---|
| **L1 evidence archive** | Original records, never altered; acquisition history; provenance (`source`, `origin_chain`); three timestamps | append / revise as new record | everyone, through the access gate |
| **L2 observations / features** | Extractions, entity resolutions, summaries, each attributed to the **method and version** that produced it and to its **source ids**; stored once | append; a re-extraction is a new revision | shared, subject to the cutoff rules (section 3); a method's output may be marked private to one branch |
| **L3 per-protocol worldview** | Beliefs, hypotheses, memory, forecasts of one protocol branch | only that branch | only that branch (and the experiment runner for scoring) |

No L3 conclusion ever overwrites L1/L2. Interpretation that lives in L2 (entity resolution, dedup, extraction) is versioned and reversible; a protocol may disagree with it.
In code: `contracts.Evidence` (L1), `contracts.Observation` (L2 when `branch == ""`, L3 otherwise), `branches` (L3 namespaces).

## 2. Time semantics
Every evidence record carries **event time** (it happened), **publish time** (it became public) and **acquired time** (we held it). A derived object adds
**derivation time** (`derived_at`, wall clock) and, for branch-private objects, **as-of** (the information time the producer worked under). A revision of a
derived object is a new `revision`, never an edit. Rules: an unknown publish time is never visible; a date-only publish time means the *end* of that day;
an unknown acquired time is allowed but recorded in the manifest (`acquired_known: false`) because it weakens a historical replay.

## 3. Information access (historical replay)
A protocol sees the world only through `access.Reader`, built per (cutoff, branch) and re-checking on every read:
- **Evidence** is visible iff `publish_time <= cutoff` and (`acquired_at` unknown or `<= cutoff`).
- **Shared derived objects** are visible iff `derived_at <= cutoff` **and every source is visible** (checked transitively through chains of derived objects).
  A summary written after the cutoff is excluded even if it only mentions old things: derivation can import hindsight, and so can an entity-resolution pass.
- **Branch-private objects** are visible to their own branch only, and only when `as_of <= cutoff`.
- A derived object without sources or without a method/version is refused outright.
- Whatever a retrieval policy returns is intersected with what the reader allows, so a buggy or greedy policy cannot widen access.
- Known hole, stated plainly: the corpus index is derived and a full rebuild resets `ingested_at`, so for *historical* replay `CorpusSource` cannot vouch for
  acquired time (`acquired_known: false`). The fix is the L1 acquisition ledger (phase 2). Live questions (cutoff = now) are unaffected.

## 4. Policies, protocols, branches
Independently versioned **policies**: attention, extraction, memory, interpretation, hypothesis, evidence, investigation, prediction, learning, plus
**model**, **prompts**, **tools** (`contracts.POLICY_KINDS`). A policy version = `(kind, name, version, params, impl_sha)`, content-addressed and stored write-once.
`params` holds everything as-is (the full prompt text, model settings, bounds); `impl_sha` is the hash of the code that interprets it. A **protocol** is a
composition of one version per kind, identified by the digest of the composition. Changing anything makes a new policy version and a new protocol; nothing is edited in place.
A **branch** is mutable state for one protocol (a private memory namespace). `branches.fork` snapshots the parent's memory (digest recorded), copies it, links
the parent and starts a new protocol; the parent's protocol file and memory bytes are untouched (tested). Rolling back is selecting the earlier protocol/branch.

## 5. Experiment modes (separate scoreboards)
- **Controlled.** Same evidence snapshot (built once per question, stored by digest), same questions, comparable budget (same `k`, same per-call cap), **one component varied**. Answers "does this policy help?". Cost recorded.
- **Independent.** Each protocol chooses what to investigate and its own evidence; scored on what it chose **plus a mandatory common question set** (`Question.common_set`) that every protocol must answer, so choosing easy questions cannot win. Answers "is the whole system better?". Cost recorded, including investigation spend.
Scoreboards are computed per `mode` and never mixed. Phase 1 implements controlled; `RunRecord.mode` and `common_set` exist so independent runs slot in.

## 6. Scoring
Per forecast: Brier and log score (clipped to [0.001, 0.999]); calibration bins; the same two scores for the **market price at the cutoff** and for a **base rate**
when the question carries them (never shown to the protocol); skill = score difference (negative Brier difference = better). **Separate from trading P&L**
and from market selection. **Abstentions** (no usable probability) are stored, counted and listed, not dropped. Differences between protocols are paired over
shared questions with a standard error (`None` until there are two questions: one question is an anecdote). One **resolution rule** per question, stored
write-once the first time the outcome is known, applies to every protocol; a later change to the source cannot move a score. Scores are computed from stored
forecasts and resolutions only.

## 7. Evidence independence
Ten outlets repeating one source are one **chain**, not ten witnesses. `Evidence.origin_chain` names the records an item repeats or cites; corroboration is
counted across *chains*, and independent investigations that reach the same fact by different routes do corroborate. **No mechanical dedupe**: repeats are kept
(they carry timing, amplification and attribution signal); independence is a modelled property of the evidence graph, computed by a versioned L2 method, and
a protocol may weigh it differently. Phase 1 stores the field and does not yet compute it.

## 8. Case categories
**Historically resolved** (replay under a cutoff; cheap, risk is leakage), **live unresolved** (the real test; frozen forecasts, scored later; the track-record
discipline of `markets-track-record.md`), **synthetic worlds with known hidden mechanisms** (the only way to test whether a protocol *discovers* a mechanism;
`category: "synthetic"`, evidence from `ListSource`). Each reports separately.

## 9. Migration: today's bots become a frozen, audited control
1. **Snapshot, don't reconstruct.** `policies.freeze_blind_forecaster()` copies, once, the live `markets/forecast.py` role text (+ research addendum), output fields,
   the task format, the model settings (effort, temperature, max tokens, per-call cap) and the probability bounds into the store (`frozen/p0.json` points at it). Later calls
   return the stored capture whatever the code says. `test_frozen_task_format_matches_production_today` is a drift detector, not a dependency.
2. **Next:** do the same for the trader and day books (prompt, tool specs, guards, books' flags), and capture their *state* (ledgers, decisions, gap files) by digest as the control's L3.
3. **Corpus index -> L1/L2.** `documents` map to L1 (`date` -> publish, `ingested_at` -> acquired, `product/kind` -> source); `claims`, `mentions`, `relations`, `events`, `entities`
   are L2 (derived by versioned adapters; today they carry `product`/`origin` but not method version or derivation time, which phase 2 adds). The index stays the production read path; the lab reads it read-only.
4. Production is never changed: nothing imports `experiment/`, there is no timer, a live run needs `--live` and is capped (`flags.RUN_CAP_USD`) under the existing budget gate.

## 10. The phase-1 slice (what exists)
`newsroom lab run --market ID --cutoff ISO [--live]` builds one question from a **resolved market already in the markets store** (rules text, end date; the price at the
cutoff kept as a hidden reference), takes one evidence snapshot from the corpus index at the cutoff, and runs two branches:
**P0** = frozen blind forecaster (evidence policy `recent-k@1`, a stand-in for production's model-planned corpus queries) and **P1** = P0 forked with *only* the
evidence policy changed (`keyword-overlap@1`). Each has its own memory namespace. The runner writes, before any scoring: snapshot, manifest (ids shown, content hashes, event/publish/acquired times,
time bounds, exclusions), prompt as sent, raw output, cost, then the immutable forecast and a provenance-carrying memory note. `lab score` resolves once, scores both by the same rule, and prints per-mode boards.
Without `--live` nothing is called; it freezes P0, builds the snapshot and prints what each branch would see.

| Not in phase 1 | Why / next |
|---|---|
| L1 acquisition ledger with true acquired times; method-versioned L2 stamps in the corpus index | needed for trustworthy historical replay |
| Origin-chain computation; independent mode runner; synthetic-world generator | designed above, fields present |
| Production's model-planned research as a policy (`evidence/production-research`) | wrap `markets/research.py` over a Reader-filtered corpus |
| Trader / day-book controls; bootstrap CIs over many questions; backup of the store | after the first live result matters |
