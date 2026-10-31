# Experiment framework (phase 1: design and a vertical slice; phase 2: faithful controls, acquisition time, common set)

> Code: `backend/algent_backend/experiment/` (+ `acquisition/` for the ledger). Registry products `experiments` (manual, off by default, not backed up) and `acquisition` (irreplaceable, backed up). CLI: `newsroom lab ...`. Tests: `tests/test_experiment_lab.py`, `test_experiment_phase2.py`, `test_acquisition_ledger.py`, `test_origin_chains.py`, `test_experiment_decision.py`, `test_experiment_qset.py`.
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
- **Acquisition time (phase 2, closed).** The corpus index is derived and a full rebuild resets `ingested_at`, so `CorpusSource` no longer uses it. The append-only
  acquisition ledger (`acquisition/store.py`, `ledger.jsonl`, one line per (unit key, content fingerprint), written by every corpus build, never reset by a rebuild)
  supplies `acquired_at`. `first_seen` is the build that first saw the content, an upper bound on when we held it. The first build against an empty ledger indexes a
  record that already existed, so those entries are `backfill: true` and read as *unknown*, never as "now"; an edited unit is a new entry. `acquired_known` is true only
  when the ledger vouches for every candidate (`n_acquired` says how many). Replay at cutoffs before the ledger began therefore still relies on publish time alone, and says so.

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
a protocol may weigh it differently. **Phase 2 computes it** (`origins.py`, method `origin-chain@1`, deterministic, no model): same canonical URL, or near-duplicate text
(shared 4-word shingles, Jaccard >= `flags.DUP_JACCARD`, only for texts of 12+ words), connected components over the documents visible at the cutoff; the earliest is the
chain's origin and every repeat's `origin_chain` names it. Snapshots store it, each run manifest records `chains` (`n_shown`, `n_independent`) and score rows carry both.

## 8. Case categories
**Historically resolved** (replay under a cutoff; cheap, risk is leakage), **live unresolved** (the real test; frozen forecasts, scored later; the track-record
discipline of `markets-track-record.md`), **synthetic worlds with known hidden mechanisms** (the only way to test whether a protocol *discovers* a mechanism;
`category: "synthetic"`, evidence from `ListSource`). Each reports separately.

## 9. Migration: today's bots become a frozen, audited control
1. **Snapshot, don't reconstruct.** `policies.freeze_blind_forecaster()` copies, once, the live `markets/forecast.py` role text (+ research addendum), output fields,
   the task format, the model settings (effort, temperature, max tokens, per-call cap) and the probability bounds into the store (`frozen/p0.json` points at it). Later calls
   return the stored capture whatever the code says. `test_frozen_task_format_matches_production_today` is a drift detector, not a dependency.
2. **Phase 2, done:** `controls.freeze_production_research()` (P0b: P0 with `evidence/production-research@1`, superseding P0 which stays as is), `freeze_trader()` and `freeze_day_bot()`
   (prompts, model settings, guards and flags; new `decision` policy kind). The trader is replayable (section 11); the day bot is frozen but NOT replayable (live multi-turn tool use).
   Still open: capture the books' *state* (ledgers, decisions, gap files) by digest as the controls' L3.
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
| Method-versioned L2 stamps in the corpus index (`derived_at`, method version on claims/events) | the lab hides derived rows by date and by source visibility, not yet by method version |
| Independent mode runner; synthetic-world generator | designed above, fields present |
| Day-bot replay (tool-capable harness over historical market state); trader/day-book L3 state capture | phase 3+ |
| Bootstrap CIs over many questions; backup of the experiment store | after the first live result matters |
| `related` and entity situations/relations in the cutoff corpus | not time-indexed, so omitted (`dropped`); the P0b control is slightly poorer than production there |

## 11. What phase 2 closed
1. **Faithful P0 (P0b).** `research_policy.py` runs production's `markets/research.py` (planner call, six corpus tools, renderer) through `cutoff_corpus.CutoffCorpus`: a document is visible
   only if it is in the cutoff snapshot, a claim/event only with a known date <= cutoff and a visible source document, observations only up to the cutoff, entity profiles are
   rebuilt from bounded queries. Test: a post-cutoff document that is the best match is invisible. The planner prompt and knobs are frozen as params; `knob_drift` and
   `controls.impl_drift` report production moving since the freeze. Planner spend is added to the run's cost.
2. **Acquisition ledger** (section 3). Registered as the irreplaceable `acquisition` product and backed up nightly.
3. **Controls and decision replay.** `decision.replay` shows the frozen trader the market state at the cutoff (price and daily path up to it, the desk probability and evidence of a
   named forecast run, a flat book), passes its answer through the frozen guards and fills hypothetically at the cutoff price (+ slippage). `decision.board` scores by realised P&L
   once the market resolves, per protocol with a standard error and paired differences, apart from the forecast board (`lab score` prints both).
4. **Common question set.** `lab questions --set build` (resolved markets, one per event, topic round-robin, cutoff 48 h before resolution, price on file; at least 20 when
   available, else it says `short_of_target`), stored write-once and versioned under `sets/`. `lab run --set` runs each named protocol on every question in controlled mode under a
   TOTAL cap (`flags.SET_RUN_CAP_USD`, `--cap`); re-running continues where the cap stopped it. The set scoreboard has per-protocol Brier/log with standard errors, abstentions, cost, and
   paired differences with standard errors.
5. **Origin chains** (section 7).

**Phase 3 recommendation: Protocol B (delineation).** With P0b as the faithful control and a common set to judge on, the first method worth testing is a delineation step: before forecasting,
split the question into its resolution trigger, the actors and the evidence that would bear on each, and retrieve per part (an `attention`/`interpretation` policy change, one component varied).
Judge it on the common set against P0b with paired differences, and read `n_independent` to see whether it finds more independent witnesses rather than more repeats.

## 12. Production forecasting data flow (and the rule for lab protocols)
Production has ONE probability-estimation method; the bots differ in what they do with it.

| Step | Who | Where |
|---|---|---|
| Select which markets to forecast | the forecast pass: open, priced inside the skip band, not forecast recently, theater-mapped first then by volume; the fast book adds a horizon filter | `markets/forecast.candidates` |
| Research | one model-planned corpus research per forecast (planner call, six corpus tools, renderer) | `markets/research.py` |
| Set the probability | **the desk**: one blind structured call per market, never shown the price | `markets/forecast.py` (`ForecastOut.probability_pct`) |
| Trade | the **daily trader** (desk probability + price + book), the **fast book** (same forecast code via `forecast.run(book="fast")`, horizon-filtered, own trader) and the **fixed-rule book** all consume the desk's forecasts; they differ only in trading | `trader.py`, `paper.py`, `books.py` |
| Form its own judgement | only the **day bot**: an agentic loop over corpus and market tools, which picks markets, researches, states `p_yes` with each order and trades | `day_prompt.py`, `day_tools.py` |

So there is no separate "forecasting method" per bot to compare: the lab's **unit of experiment is an independent forecasting mind**. Each protocol owns its research -> probability chain end to end
and never sees another protocol's output, or the market price, before it commits. The market price may be shown afterwards, as a separately stored second output (section 14). A protocol that
reads the desk's forecast is not a forecaster; it is a decision policy (`decision.replay`), scored on money apart from the forecast board.

**Probability schema (strict).** Forecast output is `probability_pct`, a whole number 0..100, read by `markets.forecast.read_probability`. A fraction written there ("0.07"), a value outside
0..100 or a non-number is NOT rescaled or guessed at: it becomes a visible failure row (`forecast_failures.jsonl` in production with forecast id, raw value, reason and cost; `failures.jsonl` in the
lab). `forecast.as_probability` (the old lenient reading, "2" = 2%) remains only as the read path for rows written before the change. The day bot keeps `p_yes` as a fraction strictly inside (0, 1),
already refused with a message otherwise; the trader emits no probability.

## 13. Phase 3: making the lab trustworthy
1. **Replay integrity audit** (`audit.py`, `lab audit RUN|QUESTION|--set`). Lists every evidence item, derived feature (origin chains are recomputed and compared), memory item and the reference price with event /
   publish / acquired / derived times against the cutoff and a verdict `ok | unproven | LEAK`. Findings it produced and the fixes: (a) `question_from_market` read the market's LAST stored revision, which can carry
   rules text or an end date added after resolution; it now reads the revision known at the cutoff (`sources.market_as_of`), a corrected text gets a new question id (`-rXXXX`), and a market first stored after the cutoff is reported `unproven`. (b) Claim and event rows
   with no source document passed on their own event date alone; `CutoffCorpus` now asks the acquisition ledger and hides those whose unit first reached us after the cutoff (unknown acquisition is kept and counted in the run's research trace
   as `unproven_derived_rows`). Runs made before these fixes are flagged by `lab audit` (code drift / question text) and should be re-run, not trusted.
2. **Error breakdown** (`errors.py`, `lab errors --set latest`): per question and protocol, p, outcome, Brier, market at the cutoff, evidence count, independent chains, whether research found anything used, and a deterministic tag (extreme/overconfident,
   wrong base rate, retrieval miss, out-of-coverage, possible leak, invalid output) or blank. Tag thresholds are operator knobs in `experiment/flags.py` and the tags are hints for a human.
3. **Minds** (`minds.py`; names for `lab run --set --protocols`): `p0b+prior` (stated reference class and base rate first, then the update; weak evidence stays near the stated prior, not 50%) and `b` (delineation alone:
   proposition, possibility set, discriminating evidence, per-observation accounting with hard/soft/restructure assumptions, unmodelled possibilities, prior and its movement, final probability, one research request, all stored in the run's `output.json`
   under `structured`). Both change only the prompt and schema relative to P0b (`b` also raises the output ceiling, `model/house-low@2`, for the longer object); the evidence policy and model are P0b's, digest for digest.
4. **Two outputs per forecast.** The independent estimate is stored and scored first; `--aware` then shows the same mind the price once and stores a market-aware estimate apart (`runs/<id>/aware.json`). The board reports, per protocol,
   `independent_minus_market` (independent skill), `aware_minus_market` (what seeing the price buys) and `aware_minus_independent`.
5. **Genealogy** (`genealogy.py`, `lab tree`, `lab retire`). Each protocol names its parent; the policies changed are derived from the two stored compositions. A retired protocol is only marked: its evidence, runs and scores stay on the boards.

## 14. Server commands (common set, controlled; cost bound is per run: forecast cap $0.05 plus, for the planned research, planner caps)
`lab questions --set build` -> `lab run --set latest --protocols p0b,p0b+prior,b` (dry run: prints what would run and the maximum cost) -> add `--live --cap USD` -> `lab run ... --aware --live` for the second output -> `lab score --set latest` -> `lab errors --set latest` -> `lab audit --set latest` -> `lab tree`.

## 15. The recipe search (calibration, tournament, mutation)
Goal: turn the lab into a search for winning forecasting recipes, starting with the cheapest win. Finding that prompted it: every protocol scored worse than the market (Brier minus market +0.13..+0.16 on 14-28 questions) and the production-research mind's "under 20%" bin
(mean 7.7%, n=16) resolved YES 56% of the time, a strong status-quo lean. Code: `calibration.py`, `calibrate.py`, `genome.py`, `tournament.py`, `mutate.py`; tests `test_experiment_calibration.py`, `_tournament.py`, `_mutate.py`, `_qset.py`.

**A bigger question pool (set version 2).** `lab questions --set build --multi` lets one market give a question at each of `flags.SET_MULTI_HOURS` (168, 48, 12 h before resolution) where a price is on file at that cutoff
(`SNAPSHOT_MAX_AGE_H`), still one market per event family (the family keeps the market covering most cutoffs), topics round-robin, no cap. `--dry-run` prints the yield from the live store and stores nothing: resolved markets seen,
event families, markets and questions kept, questions per hours-before, and what was skipped. The market is the unit of independence, not the question, so standard errors over the multi-cutoff set are optimistic; the set records `n_markets` beside the
question count. Old sets are untouched (their params, and so their ids, do not change). `question_from_market` now reads the reference price from time-ordered snapshots (a history backfill is appended after live rows and `price_at` needs order); a stored
question whose content would differ keeps its id and the new one gets a `-pXXXX` suffix.

**Calibration policies** (`calibration.py`, policy kind `calibration`, applied AFTER the mind commits, no model call). `identity@1` is the control. `platt@1` is Platt scaling on logit(p), `p' = sigmoid(a*logit(p) + b)`, fitted as a ridge-penalised logistic regression
pulled toward (a=1, b=0) (`flags.CALIB_LAMBDA`, slope kept in [0, `CALIB_A_MAX`]) on the protocol's OWN lab forecasts. `platt-live@1` also fits on the live bots' resolved `BotForecast`s (optionally only named strategies), a much larger sample from another mind family, so it is a separate policy
and never the default. **No peeking:** a map for a question with cutoff T is fitted only on forecasts whose market resolved strictly before T (`Pool.before`, time-ordered; unknown resolution time is never used), so neither the question's own outcome nor any later outcome reaches it
(tests flip later outcomes and require identical results). With fewer than `CALIB_MIN_FIT` forecasts, or fewer than `CALIB_MIN_CLASS` of either outcome, the map is the identity and says why (`kind`: `too_few`, `one_sided`); the board counts how many forecasts were really recalibrated (`n_fitted`).
A protocol may carry one calibration policy; `calibration.split` finds the RAW protocol (same composition without it) whose stored runs it re-reads, so a calibrated candidate never pays for a second run. `lab calibrate [--set] [--live-strategies a,b]` re-scores every stored protocol
with every policy for free and prints raw and calibrated side by side (`lab score` carries the same block); `lab live-board [--strategies]` scores the live strategies' resolved forecasts with the same scorer: one forecast per (strategy, market), the last before resolution, vs the market price stored on
the forecast, with the map fitted on earlier-RESOLVED forecasts of the same group; its headline is "if we had recalibrated, Brier vs market would be X instead of Y on N resolved". Data shapes relied on and not verified against the server: `BotForecast.p`, `.market`, `.at`, and `Market.resolved_at` / `.outcome` as ISO strings.
`lab block` writes `lab_block.json` beside the store; `markets/lab_block.py` reads it defensively into the optional `lab` object of the track record (the lab package is still imported by nothing).

**Tournament** (`tournament.py`, `lab tournament --set latest --candidates SPEC,SPEC,... [--first N] [--budget USD] [--live] [--dry-run]`). Candidates are specs (`genome.parse`): a named mind or stored protocol with at most ONE changed policy (`;calibration=platt`, `;evidence=keyword-overlap@1`, `;k=4`).
Successive halving: round one, every candidate answers the first `first` questions of the set (fixed order by id digest); rank by PAIRED Brier-vs-market on the questions all of them answered (mean with standard error; an abstention counts as 50%; means within `TOURNAMENT_TIE_EPS` tie and the cheaper wins);
keep the top half, double the slice, and let survivors answer only the NEW questions (stored runs are reused). It ends at one candidate; once the slice is the whole set the remaining halvings are free, and the result says whether the winner is separated from the runner-up (lead beyond two standard errors) or merely first.
`flags.TOURNAMENT_USD` (default 1.00; `--budget`) is checked BEFORE every call against that call's maximum cost; the first call that would exceed it stops the tournament, which then declares no winner. Without `--live`, or with `--dry-run`, nothing is called: the plan, rounds and an upper-bound cost are printed.
The outcome is stored write-once at `tournaments/<id>.json` (id = digest of its content) with each candidate's parent and changed policy, and indexed in `tournaments/index.jsonl`.

**Mutation** (`mutate.py`, `lab mutate PROTOCOL [--set] [--live]`). Reads the deterministic `errors` tags and the protocol's calibration table. A lean the table shows (`status-quo bias`: bins below 50% whose hit rate exceeds what was said by `MUTATE_BIAS_GAP` with at least `MUTATE_BIAS_MIN_N`; `overclaiming yes`) is a measured,
quantified failure and outranks per-question tags. Free children (no model): swap the calibration policy (expected effect read from the stored runs), swap the evidence policy, halve or double the evidence size; ordered by how directly they answer the top failure. Each is a new protocol naming the parent and
changing exactly one policy (visible in `lab tree`). One paid child with `--live` (cap `MUTATE_CAP_USD` = 0.05 USD, under the budget gate): the house model drafts a short addendum to the protocol's prompt for the top prompt-addressable failure, written under `docs/ethos/doctrine-drafting-ethos.md`
(why, failure mode, room for judgment, no invented numbers, no incident pasted in), stored as a NEW version of that prompt policy (`prompts/<name>@N+1`; the old version is never edited) in a child protocol. It is asked once per (parent, failure); asking again returns the stored draft. The printed last line is a ready `lab tournament` command over the parent and its best children.

**Promotion of a winner to a live desk (not done; deliberate later step).** Nothing in this patch changes trading or any bot. A recipe that wins a tournament AND holds on the live board would be promoted by adding it as a roster strategy (`markets/strategies.py`) whose forecast step uses the frozen protocol's policies
(prompts, model, evidence, and for calibration the stored map fitted on everything resolved so far, applied after the mind commits), run beside the incumbent with its own book, scored by `lab live-board` and the track record for a pre-declared number of resolved markets before it replaces anything. Calibration is the exception worth doing first: it is a pure
post-processing map, so it can be applied to the existing forecasts in shadow (`BotForecast` kept as said, calibrated p stored beside it) before any sizing reads it.
