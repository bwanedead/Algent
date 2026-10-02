# Ohmega Research — operator guide

How to validate trial records and build the offline report. The why and the roadmap are in
`docs/vision/ohmega-research.md`.

## Commands (run from `backend/`)

```powershell
.venv\Scripts\python.exe -m algent_backend.ohmega_research validate --input PATH
.venv\Scripts\python.exe -m algent_backend.ohmega_research report --input PATH --output DIR
.venv\Scripts\python.exe -m algent_backend.ohmega_research demo --output DIR
.venv\Scripts\python.exe -m algent_backend.ohmega_research audit-metr --input PATH --source-metadata PATH --output DIR
```

- `validate` checks the whole file and prints a short JSON summary. On failure it prints
  every problem with its line number and exits 1.
- `report` writes `analysis.json` and `report.html` to `DIR`. An invalid input writes nothing.
- `demo` writes `synthetic_trials.jsonl` (deterministic, **SYNTHETIC**) and its report.
- `audit-metr` writes `source-audit.json` and `source-audit.html` for a local METR
  `runs.jsonl` snapshot (see "METR source audit" below). It never produces trial records.
- Without `--output`, results go to `<runs-data>/ohmega_research/{report,demo,audit-metr}`. The
  runs-data root is `backend/runs_data` (gitignored), or `ALGENT_RUNS_DIR` if that is set.
  Inside the repository the CLI refuses any output directory outside the runs-data root, so
  nothing lands in the source tree.
- Offline only: no network, no model calls, standard library only.

## Trial record (`ohmega.research.trial/1`)

One JSON object per line, one line per terminal trial. Unknown fields, duplicate keys,
duplicate `trial_id`s, NaN/Infinity, negative or boolean numbers, and invalid dates are all
rejected.

```json
{"schema": "ohmega.research.trial/1", "trial_id": "pilot-0001",
 "study_id": "noninterference-pilot", "protocol_version": "p1",
 "dataset_kind": "observed", "cohort": "2026-11", "trial_date": "2026-11-03",
 "task": {"id": "repo-repair-07", "version": "2", "family": "repo-repair",
          "demands": {"abstraction": 2, "branching": 1, "recovery": 2}},
 "system": {"model": "...", "harness": "...", "config_version": "..."},
 "evaluation": {"rubric": "goal-check", "rubric_version": "3", "evaluator": "test-suite@1.4"},
 "provenance": {"source": "algent-harness", "reference": "runs_data/.../audit"},
 "outcome": "success", "terminal_reason": "completed",
 "intervention": {"status": "observed_none", "evidence": "full transcript reviewed"},
 "attempts": {"count": 1, "max_allowed": 2, "retry_policy": "retry once on harness error",
              "resources_scope": "all_attempts"},
 "budget": [{"metric": "cost", "unit": "USD", "limit": 2.0}],
 "resources_used": [{"metric": "cost", "unit": "USD", "value": 1.12},
                    {"metric": "input_tokens", "unit": "tokens", "value": null}],
 "notes": "optional"}
```

| Field | Rule |
|---|---|
| `dataset_kind` | `observed` or `synthetic`. The two are analysed in separate partitions and never pooled. |
| `task.demands` | The prespecified demand vector: label → integer level ≥ 0. Family and demands are fixed per `(task.id, task.version)`. |
| `outcome` | `success`, `failure`, `indeterminate`. A success must have `terminal_reason: completed`. An `evaluator_error` or `environment_error` lies outside the tested system, so the goal outcome was not observed and must be `indeterminate`. |
| `terminal_reason` | `completed`, `gave_up`, `timeout`, `budget_exhausted`, `system_error`, `evaluator_error`, `environment_error`. |
| `intervention` | `observed_none` / `observed_present` require `evidence`. `unknown` may leave it null. |
| `attempts` | `count` ≤ `max_allowed`. Resources are totals over all attempts (`resources_scope: all_attempts`). |
| `budget` | The limits assigned before the trial (`[]` = unbudgeted). Each metric appears once. |
| `resources_used` | Measured totals. `value: null` = measured as unknown; a metric that is absent = not reported. Neither is ever zero. Units must match the budget's unit. |

## How the numbers are computed

The canonical wording is `METHODOLOGY` in `ohmega_research/analysis.py`, and every
`analysis.json` embeds it. In short:

- **Credited** = success, `observed_none`, and the budget respected (or no budget assigned).
- **Credited operational yield** (`all_outcomes`) = credited ÷ every terminal trial in the
  cell, including evaluator and environment outages. It is a conservative floor on what the
  operation delivered. It is not an estimate of capability where outcomes were unobservable.
- **Confirmed capability rate** (`confirmed`) = credited ÷ trials whose credit status was
  ascertained (intervention observed, goal outcome observed, budgeted resources measured).
  Membership requires ascertainment; it never selects on success versus failure. Always
  shown with its coverage.
- **Cells** group by dataset kind, study, protocol, evaluator rubric/version, exact system
  config, task id/version, the assigned budget (exact structured limits), the declared
  attempt policy (`max_allowed`, `retry_policy`, `resources_scope`) and cohort. Attempts
  actually used are an outcome, not a grouping key. Display labels such as `budget_label`
  never affect identity. Every rate carries a 95% Wilson interval, which is descriptive and
  assumes independent trials.
- **Temporal view**: a series is a cell key without the cohort. Cohorts are compared only
  inside one series and only when their dates do not overlap. Everything else is reported
  as "growth not estimable", and same-task series that differ in conditions are listed as
  "kept apart".
- `analysis.json` (`ohmega.research.analysis/1`) is deterministic for a given input and is
  the export a future site `/research` page would read. The HTML embeds the same JSON.
  Top level: `input` (name, sha256, records), `contains_synthetic`, `mixed_dataset_kinds`,
  `methodology`, `provenance`, `partitions[]`. Each partition holds `dataset_kind`,
  `inventory` (counts only, no pooled rate), `temporal_statement`, `matched_series`,
  `warnings`, `cells[]`, `series[]`, `unpooled[]` and `family_rollups[]`. Cells, series and
  rollups carry their fixed conditions: `budget` (a list of `{metric, unit, limit}` with exact
  limits), `budget_label` (for display only) and `attempt_policy`. Every cell or
  rollup carries a `summary` with `n`, `credited_success`, `all_outcomes`/`confirmed`
  (`k`, `n`, `rate`, `wilson95`, plus `coverage` on `confirmed`), outcome, intervention,
  budget and terminal-reason counts, `helped_success`, `attempts`, `resources[]` and
  `clustering`.
- **Report layout.** The first screen keeps the synthetic/mixed banner and the key coverage
  numbers visible. Data-quality notes and the method sit behind `<details>`. Tables scroll
  inside their own container, and below 760px the cell rows stack so the page itself never
  scrolls sideways. The filters hide rows only; the "full-file inventory" counts in each
  section never change with a filter.

## METR source audit (`ohmega.research.source-audit/1`)

An inspection of third-party evidence, kept apart from the trial estimator in
`ohmega_research/benchmarks/`. It reads only local files and never fetches anything.

- **Metadata file** (JSON, all fields required, no others): `source_url`, `commit`,
  `sha256` (64 lowercase hex), `bytes`, `rows`, `license_status`, `purpose`. Byte count,
  SHA-256 are checked before parsing; row count is checked after parsing. All checks finish
  before output. A mismatch is an error.
- **Rows** need `run_id` (string, or non-negative integer for human baselines), `task_id`,
  `task_version` (present; may be null), `task_family`, `task_source`, `alias`, `model`,
  `score_binarized` (0 or 1, not a boolean), `score_cont` (within [0, 1]), `human_minutes`
  and `human_source`. The optional fields `scaffold`, `tokens_count`, `generation_cost`,
  `time_limit`, `started_at`, `completed_at`, `cloned` and `fatal_error_from` are validated
  when present. Other fields (`human_score`, …) are allowed, unused and counted. Duplicate
  keys, duplicate `run_id`s, malformed JSON, NaN/Infinity, negative or boolean numbers are
  rejected with line numbers, and a rejected snapshot writes nothing.
- **Never inferred**: intervention (every run is `unknown`), budgets (`time_limit` has no
  verified unit or enforcement), compute (tokens are not FLOPs), a "free run" from a zero
  cost, or goal distance (`human_minutes` is task metadata). A missing scaffold is "unknown".
- **Timestamps**: `plausible_ms` (Unix ms from 2020 to 2030) gives the evaluation-date range.
  `null`, `absent`, `zero`, `short` (below 2020 as ms) and `above_range` are counted and
  flagged; those runs stay in every other count.
- **Output keys**: `schema`, `kind`, `headline`, `source` (metadata, `input_name`,
  `verified`, `raw_rows_copied: false`), `overview` (runs, AI and human-baseline runs,
  aliases, models, `(model, scaffold)` systems, tasks, versions, families, sources),
  `intervention`, `resources[]` (records, absent, null, zero, positive, min, median, p95,
  max, note), `timestamps[]`, `data_quality`, `outcomes_by_system[]`,
  `outcomes_by_task_group[]` (each with `n`, `score_binarized_1`, `rate`, `wilson95`, task
  count, `max_runs_per_task`, `task_version_mix`) and `caveats[]`. Output is deterministic
  and holds aggregates only, never raw rows.
- Rows with `model: "human"` are human baselines. They are listed with their own label and
  excluded from AI system counts.

## Checks

Use a repo-local pytest temp directory, so tests never write outside the repo:

```powershell
cd backend
.venv\Scripts\python.exe -m pytest tests/test_ohmega_research.py tests/test_ohmega_research_metr.py --basetemp=runs_data/pytest-ohmega-research -p no:cacheprovider
.venv\Scripts\python.exe -m ruff check algent_backend/ohmega_research tests/test_ohmega_research.py tests/test_ohmega_research_metr.py
.venv\Scripts\python.exe -m algent_backend.ohmega_research demo --output runs_data/ohmega_research/smoke
```

## Limitations

Every standardized trial so far is synthetic. The METR source audit is an inspection of a
third-party file, not converted trial records, and no ingestion adapter exists. Intervals
have no clustering adjustment, and the temporal view runs no significance test and fits no
trend.
See the vision doc for the roadmap.
