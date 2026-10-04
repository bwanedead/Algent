"""Source audit of a locally supplied METR ``runs.jsonl`` snapshot.

This module reads and audits third-party evidence. It is deliberately separate from the trial
estimator: METR runs record no intervention and no assigned budget, so they are never
converted into ``ohmega.research.trial/1`` records. The audit reports what the snapshot does
and does not observe. It never fetches anything, and its output holds aggregates and
identifiers only, never raw rows.
"""

from __future__ import annotations

import hashlib
import statistics
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from .. import strict_json
from ..analysis import wilson_interval

SOURCE_AUDIT_SCHEMA = "ohmega.research.source-audit/1"
HEADLINE = (
    "Non-interference not identifiable: intervention absent; tokens are not compute; "
    "this is a source audit, not horizon growth."
)
HUMAN_BASELINE_MODEL = "human"
RESOURCE_FIELDS = ("tokens_count", "generation_cost", "time_limit")
TIMESTAMP_FIELDS = ("started_at", "completed_at")
RESOURCE_NOTES = {
    "tokens_count": "Reported token count. Not compute; never converted to FLOPs.",
    "generation_cost": "Reported cost. What a zero means is unverified; no free-run conclusion.",
    "time_limit": "Unit and enforcement unverified; not treated as an assigned hard budget.",
}
CAVEATS = (
    "The snapshot records no intervention, so every run is intervention-unknown and none can "
    "enter a non-interference denominator.",
    "Rates are descriptive shares of score_binarized = 1 among a group's runs. Groups differ "
    "in task mix, so the rates are not a capability ranking.",
    "Intervals are Wilson intervals that treat runs as independent. Many runs repeat the same "
    "task, so dependence between runs may overstate precision.",
    "Evaluation timestamps are when runs were evaluated, not model release dates. No model "
    "chronology is inferred, and models evaluated in this window may not reflect the current "
    "model generation.",
    "human_minutes is task metadata (human baseline time), not this program's goal distance.",
    "Rows with model 'human' are human baselines, not a tested AI system; they are excluded "
    "from system counts.",
    "Reuse and licence terms are unverified. This audit stores aggregates and identifiers "
    "only and does not redistribute the dataset.",
)
# Unix milliseconds from 2020-01-01 to 2030-01-01 UTC. Other values are flagged, not guessed.
_PLAUSIBLE_MS = (1_577_836_800_000, 1_893_456_000_000)
_REQUIRED_TEXT = ("task_id", "task_family", "task_source", "alias", "model", "human_source")
_OPTIONAL_NUMBERS = (*RESOURCE_FIELDS, *TIMESTAMP_FIELDS, "cloned")
_OPTIONAL_TEXT = ("scaffold", "fatal_error_from")
_KNOWN = {"run_id", "task_version", "score_binarized", "score_cont", "human_minutes",
          *_REQUIRED_TEXT, *_OPTIONAL_NUMBERS, *_OPTIONAL_TEXT}
_ABSENT = object()


class SourceValidationError(ValueError):
    """The snapshot or its metadata was rejected; ``errors`` lists every problem."""

    def __init__(self, errors: Sequence[str]) -> None:
        self.errors = tuple(errors)
        super().__init__(f"{len(self.errors)} source error(s); first: {self.errors[0]}")


@dataclass(frozen=True)
class SourceMetadata:
    source_url: str
    commit: str
    sha256: str
    bytes: int
    rows: int
    license_status: str
    purpose: str


@dataclass(frozen=True)
class MetrRun:
    run_id: str
    task_id: str
    task_version: str | None
    task_family: str
    task_source: str
    alias: str
    model: str
    score_binarized: int
    observed: dict  # optional fields present in the row; None means reported as null
    extra_fields: tuple[str, ...]

    @property
    def scaffold(self) -> str | None:
        return self.observed.get("scaffold")


def load_metadata(path: Path) -> SourceMetadata:
    try:
        obj = strict_json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise SourceValidationError([f"source metadata: not valid JSON ({exc})"]) from None
    if not isinstance(obj, dict):
        raise SourceValidationError(["source metadata: must be a JSON object"])
    names = SourceMetadata.__dataclass_fields__
    errors = [f"source metadata: {k}: required field is missing" for k in names if k not in obj]
    errors += [f"source metadata: {k}: unexpected field" for k in sorted(set(obj) - set(names))]
    for key in names:
        value = obj.get(key)
        if key in ("bytes", "rows"):
            ok = isinstance(value, int) and not isinstance(value, bool) and value >= 0
        elif key == "sha256":
            ok = isinstance(value, str) and len(value) == 64 and set(value) <= set("0123456789abcdef")
        else:
            ok = isinstance(value, str) and bool(value.strip())
        if key in obj and not ok:
            errors.append(f"source metadata: {key}: invalid value")
    if errors:
        raise SourceValidationError(errors)
    return SourceMetadata(**{k: obj[k] for k in names})


def _verified_text(raw: bytes, metadata: SourceMetadata) -> str:
    if len(raw) != metadata.bytes:
        raise SourceValidationError([f"snapshot is {len(raw)} bytes; metadata says {metadata.bytes}"])
    digest = hashlib.sha256(raw).hexdigest()
    if digest != metadata.sha256:
        raise SourceValidationError([f"snapshot sha256 {digest} does not match metadata"])
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SourceValidationError([f"snapshot is not valid UTF-8 ({exc})"]) from None


def read_snapshot(raw: bytes, metadata: SourceMetadata) -> list[MetrRun]:
    """Verify bytes and hash against the metadata, then parse every row strictly."""
    text = _verified_text(raw, metadata)
    errors: list[str] = []
    runs: list[MetrRun] = []
    first_line: dict[str, int] = {}
    rows = 0
    for line_no, line in enumerate(text.split("\n"), start=1):
        if not line.strip():
            continue
        rows += 1
        run = _parse_row(line.removesuffix("\r"), line_no, errors)
        if run is None:
            continue
        seen = first_line.setdefault(run.run_id, line_no)
        if seen != line_no:
            errors.append(f"line {line_no}: run_id {run.run_id!r} duplicates line {seen}")
        runs.append(run)
    if rows != metadata.rows:
        errors.append(f"snapshot has {rows} rows; metadata says {metadata.rows}")
    if not rows:
        errors.append("snapshot contains no rows")
    if errors:
        raise SourceValidationError(errors)
    return runs


def _parse_row(line: str, line_no: int, errors: list[str]) -> MetrRun | None:
    try:
        obj = strict_json.loads(line)
    except ValueError as exc:
        errors.append(f"line {line_no}: not valid JSON ({exc})")
        return None
    if not isinstance(obj, dict):
        errors.append(f"line {line_no}: a run must be a JSON object")
        return None
    problems: list[str] = []
    text = {key: _required_text(obj, key, problems) for key in _REQUIRED_TEXT}
    run = MetrRun(
        run_id=_run_id(obj, problems),
        task_id=text["task_id"],
        task_version=_optional_text(obj, "task_version", problems, required=True),
        task_family=text["task_family"],
        task_source=text["task_source"],
        alias=text["alias"],
        model=text["model"],
        score_binarized=_binary(obj, problems),
        observed=_observed(obj, problems),
        extra_fields=tuple(sorted(set(obj) - _KNOWN)),
    )
    _unit_interval(obj, "score_cont", problems)  # validated so bad scores are never dropped
    _amount(obj, "human_minutes", problems)  # validated; task metadata only
    errors.extend(f"line {line_no}: {problem}" for problem in problems)
    return None if problems else run


def _get(obj: dict, key: str, problems: list[str], *, required: bool) -> object:
    if key in obj:
        return obj[key]
    if required:
        problems.append(f"{key}: required field is missing")
    return _ABSENT


def _required_text(obj: dict, key: str, problems: list[str]) -> str:
    value = _get(obj, key, problems, required=True)
    if isinstance(value, str) and value.strip():
        return value
    if value is not _ABSENT:
        problems.append(f"{key}: must be a non-empty string")
    return ""


def _optional_text(obj: dict, key: str, problems: list[str], *, required: bool = False) -> str | None:
    value = _get(obj, key, problems, required=required)
    if value is _ABSENT or value is None:
        return None
    if isinstance(value, str) and value.strip():
        return value
    problems.append(f"{key}: must be a non-empty string or null")
    return None


def _run_id(obj: dict, problems: list[str]) -> str:
    value = _get(obj, "run_id", problems, required=True)
    if isinstance(value, str) and value.strip():
        return value
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return str(value)
    if value is not _ABSENT:
        problems.append("run_id: must be a non-empty string or a non-negative integer")
    return ""


def _amount(obj: dict, key: str, problems: list[str], *, optional: bool = False) -> float | None:
    value = _get(obj, key, problems, required=not optional)
    if value is _ABSENT or (value is None and optional):
        return None
    parsed, problem = strict_json.parse_amount(value)
    if problem:
        problems.append(f"{key}: {problem}")
    return parsed


def _binary(obj: dict, problems: list[str]) -> int:
    value = _amount(obj, "score_binarized", problems)
    if value is not None and value not in (0.0, 1.0):
        problems.append("score_binarized: must be 0 or 1")
    return int(value or 0)


def _unit_interval(obj: dict, key: str, problems: list[str]) -> None:
    value = _amount(obj, key, problems)
    if value is not None and value > 1:
        problems.append(f"{key}: must be within [0, 1]")


def _observed(obj: dict, problems: list[str]) -> dict:
    observed: dict = {}
    for key in _OPTIONAL_NUMBERS:
        if key in obj:
            observed[key] = _amount(obj, key, problems, optional=True)
    for key in _OPTIONAL_TEXT:
        if key in obj:
            observed[key] = _optional_text(obj, key, problems)
    return observed


def audit(runs: Sequence[MetrRun], metadata: SourceMetadata, *, input_name: str) -> dict:
    return {
        "schema": SOURCE_AUDIT_SCHEMA,
        "kind": "source_audit",
        "headline": HEADLINE,
        "source": {**asdict(metadata), "input_name": input_name,
                   "verified": ["bytes", "sha256", "rows"], "raw_rows_copied": False},
        "overview": _overview(runs),
        "intervention": {"unknown": len(runs), "observed_none": 0, "observed_present": 0,
                         "basis": "The snapshot has no intervention field; nothing is inferred."},
        "resources": [{**_profile(runs, key), "note": RESOURCE_NOTES[key]} for key in RESOURCE_FIELDS],
        "timestamps": [_timestamps(runs, key) for key in TIMESTAMP_FIELDS],
        "data_quality": _data_quality(runs),
        "outcomes_by_system": _outcomes(runs, _system_fields),
        "outcomes_by_task_group": _outcomes(runs, _task_group_fields),
        "caveats": list(CAVEATS),
    }


def _ai(runs: Sequence[MetrRun]) -> list[MetrRun]:
    return [r for r in runs if r.model != HUMAN_BASELINE_MODEL]


def _overview(runs: Sequence[MetrRun]) -> dict:
    ai = _ai(runs)
    systems = {(r.model, r.scaffold) for r in ai}
    return {
        "runs": len(runs),
        "ai_runs": len(ai),
        "human_baseline_runs": len(runs) - len(ai),
        "model_aliases": len({r.alias for r in runs}),
        "ai_models": len({r.model for r in ai}),
        "ai_systems": len(systems),
        "ai_systems_with_unknown_scaffold": sum(1 for _, scaffold in systems if scaffold is None),
        "tasks": len({r.task_id for r in runs}),
        "task_versions": len({(r.task_id, r.task_version) for r in runs}),
        "task_families": len({r.task_family for r in runs}),
        "task_sources": dict(sorted(Counter(r.task_source for r in runs).items())),
    }


def _profile(runs: Sequence[MetrRun], key: str) -> dict:
    present = [r.observed[key] for r in runs if key in r.observed]
    values = sorted(v for v in present if v is not None)
    return {
        "field": key,
        "records": len(runs),
        "absent": len(runs) - len(present),
        "null": len(present) - len(values),
        "zero": sum(1 for v in values if v == 0),
        "positive": sum(1 for v in values if v > 0),
        "min": values[0] if values else None,
        "median": statistics.median(values) if values else None,
        "p95": values[(95 * len(values) + 99) // 100 - 1] if values else None,  # nearest rank
        "max": values[-1] if values else None,
    }


_TIMESTAMP_CLASSES = ("plausible_ms", "null", "absent", "zero", "short", "above_range")


def _timestamp_class(value: object) -> str:
    if value is _ABSENT:
        return "absent"
    if not isinstance(value, float):
        return "null"
    if value == 0:
        return "zero"
    if value < _PLAUSIBLE_MS[0]:
        return "short"
    return "above_range" if value >= _PLAUSIBLE_MS[1] else "plausible_ms"


def _day(ms: float) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=UTC).date().isoformat()


def _timestamps(runs: Sequence[MetrRun], key: str) -> dict:
    classified = [(value, _timestamp_class(value))
                  for value in (run.observed.get(key, _ABSENT) for run in runs)]
    counts = Counter(name for _, name in classified)
    plausible = [value for value, name in classified if name == "plausible_ms"]
    return {
        "field": key,
        **{name: counts[name] for name in _TIMESTAMP_CLASSES},
        "questionable": counts["zero"] + counts["short"] + counts["above_range"],
        "evaluation_dates": [_day(min(plausible)), _day(max(plausible))] if plausible else None,
    }


def _data_quality(runs: Sequence[MetrRun]) -> dict:
    fatal = [r.observed.get("fatal_error_from", _ABSENT) for r in runs]
    return {
        "scaffold": _presence(r.observed.get("scaffold", _ABSENT) for r in runs),
        "task_version_null": sum(1 for r in runs if r.task_version is None),
        "fatal_error_from": {
            **_presence(fatal),
            "values": dict(sorted(Counter(v for v in fatal if isinstance(v, str)).items())),
        },
        "cloned": _profile(runs, "cloned"),
        "extra_fields": dict(sorted(Counter(f for r in runs for f in r.extra_fields).items())),
    }


def _presence(values: Iterable[object]) -> dict:
    observed = list(values)
    absent = sum(1 for v in observed if v is _ABSENT)
    null = sum(1 for v in observed if v is None)
    return {"reported": len(observed) - absent - null, "null": null, "absent": absent}


def _system_fields(run: MetrRun) -> dict:
    return {"model": run.model, "scaffold": run.scaffold or "unknown",
            "scaffold_reported": run.scaffold is not None,
            "human_baseline": run.model == HUMAN_BASELINE_MODEL}


def _task_group_fields(run: MetrRun) -> dict:
    return {"task_source": run.task_source, "task_family": run.task_family}


def _outcomes(runs: Sequence[MetrRun], fields: Callable[[MetrRun], dict]) -> list[dict]:
    groups: dict[tuple, list[MetrRun]] = defaultdict(list)
    for run in runs:
        groups[tuple(fields(run).items())].append(run)
    rows = []
    for key, members in sorted(groups.items()):
        n, k = len(members), sum(r.score_binarized for r in members)
        low, high = wilson_interval(k, n) or (0.0, 0.0)
        per_task = Counter(r.task_id for r in members)
        rows.append({
            **dict(key),
            "aliases": sorted({r.alias for r in members}),
            "n": n,
            "score_binarized_1": k,
            "rate": round(k / n, 6),
            "wilson95": [round(low, 6), round(high, 6)],
            "tasks": len(per_task),
            "max_runs_per_task": max(per_task.values()),
            "task_version_mix": dict(sorted(
                Counter(r.task_version or "unknown" for r in members).items())),
            "systems": len({(r.model, r.scaffold) for r in members}),
        })
    return rows
