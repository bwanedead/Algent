# Ohmega Research — reproducible studies of AI systems

> Canonical vision for the Research subdivision. Operating instructions live in
> `docs/guides/ohmega-research.md`; code lives in `backend/algent_backend/ohmega_research/`.
> The engine-level summary is in `docs/vision/ohmega-intelligence-engine.md` (Research section).
> Extend this doc rather than starting a parallel one.

## Charter

Ohmega Research is the subdivision that **conducts reproducible studies** of AI systems. It
prespecifies a protocol, records every trial in a form anyone can audit, analyses the records
under stated rules, and publishes only what the evidence supports. The subdivision is
general. Programs are its individual lines of study, and each program declares its own
measure, protocol and evidence bar on the shared trial and report machinery.

Shared commitments across all programs:
- **Tested system** = model + harness + the settings that change behaviour (config version).
  A result belongs to that exact combination. It never belongs to "the model".
- **Resources** (tokens, dollars, seconds, FLOPs) are separate observations. They are never
  converted into one another and never treated as interchangeable "compute".
- **Every terminal trial is a record.** Failures, outages and unknowns stay visible.
- **Synthetic, observed and third-party evidence are kept apart.** Each is labelled, and a
  source audit is never presented as our own trials.

## First program: the non-interference goal frontier

The first program asks **how far a tested system can carry a goal to completion without a
human stepping in**, under an assigned resource budget.

- **Goal distance** is a **prespecified vector of task properties**: demand labels such as
  abstraction, branching and recovery, each with a level fixed per task version *before*
  any trial runs. It is not how long a human takes, and not how many actions the system took.
- **Credited success** = the goal was met, **no intervention was observed**, and the assigned
  budget was respected. A run a human rescued is a *helped* success. It is visible, but it is
  not credited.
- **Two rates, never conflated.** The *confirmed capability rate* covers trials whose outcome,
  intervention and budget compliance were ascertained. The *credited operational yield* counts
  every terminal trial, outages included. That makes it a conservative floor on what the
  operation delivered, not an estimate of capability where outcomes went unobserved.

**North star:** a dated, auditable frontier showing which goal distances each tested system
crosses without interference, under which budgets and attempt policies, with denominators
and coverage visible at every point.

## Hypothesis vs finding

The motivating hypothesis is that the non-interference frontier moves outward over time for
systems at fixed budgets. **That is a hypothesis, not a finding.** This program exists to
test it, and it ships nothing that presents it as established.

A **finding** needs all of the following:
- observed (not synthetic) trial records that pass validation;
- matched cohorts: same task versions, protocol, evaluator and rubric version, exact system
  config, assigned budget and declared attempt policy, with dates that do not overlap;
- a confirmed denominator with adequate coverage, reported next to the operational yield;
- a stated sampling and clustering caveat (repeated trials on one task are not independent).

Until then the report says "growth not estimable" or "descriptive comparison only". It does
not interpolate, extrapolate, fit trends, or publish any horizon headline (e.g. AGH95).

## Minimum trial protocol

One JSONL record per **terminal** trial (schema `ohmega.research.trial/1`). The exact fields
are listed in the guide. The rules that matter scientifically:

1. **Prespecify** the study, protocol version, task versions with their demand vectors, the
   rubric/evaluator version, the system configs, the budgets and the attempt policy. Do all
   of this before running anything. Changing any of them starts a new series.
2. **Assign a budget per trial** (metric, unit, exact limit). Group by the budget that was
   *assigned*. Never fit a frontier to consumption chosen after seeing outcomes.
3. **Record every terminal trial.** Failures, timeouts, budget exhaustion and system errors
   are outcomes of the tested system. Evaluator and environment outages are recorded as
   `indeterminate`: they lower the operational yield but never enter the confirmed
   denominator. Nothing becomes "missing" quietly.
4. **Record interventions with evidence.** `observed_none` and `observed_present` need
   supporting evidence (a transcript review, an operator log). Without it the status is
   `unknown`, and an unknown never enters the confirmed denominator.
5. **Declare the attempt policy and count resources over all attempts.** The allowed
   attempts and the retry policy are fixed conditions. The attempts actually used are an
   outcome. Resources are totals across attempts, not the best attempt.
6. **Never write zero for unknown.** A resource that was not measured is null or absent. A
   success that exceeded its budget is a budget violation, not a credited success.

## Exploratory pilot (72 attempts)

The pilot validates the instrumentation and shows directional contrasts. **It does not
establish 95% reliability or any growth claim.**

| Design element | Choice |
|---|---|
| Task families | Three, each a pair of variants (six variants total): structured-data repair, workflow recovery, file/config repair. The two variants in a pair differ in prespecified demand levels. |
| Tested systems | Two exact configurations (model + harness + config version), each its own series. |
| Budgets | Two declared resource budgets, assigned before any run. |
| Instances | Three seeded instances per variant. |
| Attempt policy | One attempt, no hints. |
| Evaluator | Machine-checkable, and hidden from the model. |
| Size | 6 variants × 2 configurations × 2 budgets × 3 instances = **72 attempts**. |

Each cell (variant × configuration × budget) holds three clustered attempts, so the
intervals stay wide. What the pilot can show is whether the instrument records outcomes,
interventions, outages and resources completely, and which way the contrasts lean between
paired variants, budgets and configurations. Exit criteria:
- every terminal attempt is recorded;
- intervention evidence exists for every attempt;
- budgeted resources are measured for every attempt;
- a report that passes a manual audit against the raw logs.

## Staged roadmap

1. **Instrumentation (done in this slice).** Trial contract, strict validator, descriptive
   analysis with an explicit denominator policy, offline report, synthetic demo.
2. **Source audit and pilot.** Audit external evidence (below) for rights, schema and what
   is actually recorded. Then run the 72-attempt pilot on our own harness.
3. **Matched longitudinal evidence.** Repeat matched cohorts over time. Add clustering-aware
   intervals before anything is called a trend.
4. **Research publication.** A `/research` page on the site, fed by the clean
   `analysis.json` export. Findings follow the engine's trust rules: dated, graded,
   corrections kept on the record.

## Evidence inventory

**Current standardized trials remain synthetic.** The METR entry below is a *source audit*
(an inspection of a third-party file), not trials converted into our schema. No third-party
raw data is committed to the repository or published. We cite and link to sources; we do not
copy them.

### METR time horizons: audited (pinned snapshot)

The lead inspected a pinned snapshot of METR's Time Horizon 1.1 run data locally.
- Repository commit: `52cb829c7a2efb2d659285c4b1768d191d97f8d2`.
- File SHA-256: `609f904f4b6ae32129388da89d036e00bac511ad94223d2be1e58fc2b45b55cd`.
- Source: <https://raw.githubusercontent.com/METR/eval-analysis-public/52cb829c7a2efb2d659285c4b1768d191d97f8d2/reports/time-horizon-1-1/data/raw/runs.jsonl>.
- Project pages: <https://metr.org/time-horizons/>, <https://github.com/METR/eval-analysis-public>.
- The audit copy lives only under the gitignored `backend/runs_data/ohmega_research_cursor/`.

| Property | Finding |
|---|---|
| Runs | 24,008 unique runs |
| Model aliases | 21 |
| `tokens_count` present | 22,179 runs |
| `scaffold` present | 22,179 runs |
| `generation_cost` present | 23,235 runs; 20,173 of them are zero, and what zero means is unverified |
| `time_limit` present | 3,187 runs; 773 of them are zero |
| Intervention | **Not recorded.** Every run maps to intervention `unknown`. |
| True compute | Absent |
| Timestamps | Evaluation timestamps are not model release dates; some are zero or malformed |
| Distance metric | Human completion time, not our prespecified demand vector |
| Reuse terms | Not verified |

What follows from this: the snapshot is candidate evidence for operational and resource
context only. If converted, intervention must stay explicitly `unknown`, so no METR run
could enter a confirmed non-interference denominator. **This audit does not establish
horizon growth.**

### Not yet audited

| Source | Primary URLs | Open questions |
|---|---|---|
| OSWorld | <https://os-world.github.io/>, <https://github.com/xlang-ai/OSWorld> | Whether interventions, budgets and resource totals are recorded; reuse terms. |
| SWE-bench | <https://www.swebench.com/>, <https://github.com/SWE-bench/SWE-bench> | Submissions differ in harness and settings; whether interventions and resources are recorded; reuse terms. |

These URLs have not been re-checked in this slice.

## Current limitations

- No observed trials yet. The only standardized dataset is the labelled synthetic demo.
- Intervals are per-cell Wilson intervals that assume independent trials. No clustering
  adjustment and no pooled population estimate exist yet.
- Temporal comparison is descriptive: deltas between matched cohorts, with interval overlap
  shown. No significance test, no trend, no extrapolation.
- Task-family pools are descriptive only; their task mix can change between cohorts.
- No ingestion adapter for external sources exists yet. The METR audit was an inspection,
  not an import.
