"""Trial-record contract: one JSONL line per terminal trial.

The record is the unit of evidence. Validation is strict and total: every problem is reported
with its line number and an input with any problem is rejected whole. Nothing is dropped,
defaulted, merged or reweighted to make a file "mostly" usable.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable
from dataclasses import dataclass
from dataclasses import fields as dataclass_fields
from datetime import date
from pathlib import Path
from typing import TypeVar

TRIAL_SCHEMA = "ohmega.research.trial/1"

DATASET_KINDS = ("observed", "synthetic")
OUTCOMES = ("success", "failure", "indeterminate")
INTERVENTION_STATUSES = ("observed_none", "observed_present", "unknown")
TERMINAL_REASONS = (
    "completed",          # the system declared the goal done and was evaluated
    "gave_up",
    "timeout",
    "budget_exhausted",
    "system_error",       # model or harness fault: a failure of the tested system
    "evaluator_error",    # the judge failed, so the outcome cannot be known
    "environment_error",  # task infrastructure fault outside the tested system
)
# Outages outside the tested system: the goal outcome was never observed.
_UNOBSERVABLE_REASONS = ("evaluator_error", "environment_error")
RESOURCES_SCOPE = "all_attempts"

_MISSING = object()
_T = TypeVar("_T")


class TrialValidationError(ValueError):
    """An input was rejected; ``errors`` lists every problem, each with its line number."""

    def __init__(self, errors: Iterable[str]) -> None:
        self.errors = tuple(errors)
        super().__init__(f"{len(self.errors)} validation error(s); first: {self.errors[0]}")


@dataclass(frozen=True)
class Task:
    id: str
    version: str
    family: str
    demands: tuple[tuple[str, int], ...]  # prespecified demand vector, sorted by label


@dataclass(frozen=True)
class System:
    """The tested system: model + harness + the settings that change behaviour."""

    model: str
    harness: str
    config_version: str


@dataclass(frozen=True)
class Evaluation:
    rubric: str
    rubric_version: str
    evaluator: str


@dataclass(frozen=True)
class Provenance:
    source: str
    reference: str


@dataclass(frozen=True)
class Intervention:
    status: str
    evidence: str | None


@dataclass(frozen=True)
class Attempts:
    count: int
    max_allowed: int
    retry_policy: str
    resources_scope: str


@dataclass(frozen=True)
class BudgetLimit:
    """A resource limit assigned before the trial ran."""

    metric: str
    unit: str
    limit: float


@dataclass(frozen=True)
class ResourceObservation:
    """Measured consumption over all attempts; ``value`` None means reported as unknown."""

    metric: str
    unit: str
    value: float | None


@dataclass(frozen=True)
class TrialRecord:
    line: int
    trial_id: str
    study_id: str
    protocol_version: str
    dataset_kind: str
    cohort: str
    trial_date: date
    task: Task
    system: System
    evaluation: Evaluation
    provenance: Provenance
    outcome: str
    terminal_reason: str
    intervention: Intervention
    attempts: Attempts
    budget: tuple[BudgetLimit, ...]
    resources_used: tuple[ResourceObservation, ...]
    notes: str | None


def load_trials(path: Path) -> list[TrialRecord]:
    return decode_trials(path.read_bytes())


def decode_trials(raw: bytes) -> list[TrialRecord]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise TrialValidationError([f"input is not valid UTF-8 ({exc})"]) from None
    # Only "\n" ends a record: str.splitlines() would also split on U+2028 and friends,
    # which are legal raw characters inside JSON strings.
    return parse_trials(line.removesuffix("\r") for line in text.split("\n"))


def parse_trials(lines: Iterable[str]) -> list[TrialRecord]:
    """Parse and validate JSONL lines; raise ``TrialValidationError`` listing every problem."""
    errors: list[str] = []
    records: list[TrialRecord] = []
    for line_no, text in enumerate(lines, start=1):
        if not text.strip():
            continue
        record = _parse_line(text, line_no, errors)
        if record is not None:
            records.append(record)
    errors.extend(_cross_record_problems(records))
    if not records and not errors:
        errors.append("input contains no trial records")
    if errors:
        raise TrialValidationError(errors)
    return records


def _parse_line(text: str, line_no: int, errors: list[str]) -> TrialRecord | None:
    try:
        obj = json.loads(text, parse_constant=_reject_constant, object_pairs_hook=_unique_keys)
    except ValueError as exc:
        errors.append(f"line {line_no}: not valid JSON ({exc})")
        return None
    if not isinstance(obj, dict):
        errors.append(f"line {line_no}: a trial record must be a JSON object")
        return None
    local: list[str] = []
    record = _parse_record(obj, line_no, local)
    local.extend(_semantic_problems(record))
    errors.extend(f"line {line_no}: {message}" for message in local)
    return None if local else record


def _reject_constant(name: str) -> float:
    raise ValueError(f"non-finite number {name} is not allowed")


def _unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    obj: dict[str, object] = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"duplicate key {key!r}")
        obj[key] = value
    return obj


class _Fields:
    """Typed, error-collecting reads from one JSON object. Bad data is reported, never raised.

    A ``silent`` instance stands in for a child object that was missing or malformed (already
    reported once), so its own fields do not each report "missing" again.
    """

    def __init__(self, obj: dict, path: str, errors: list[str], *, silent: bool = False) -> None:
        self._obj = obj
        self._path = path
        self._errors = errors
        self._silent = silent
        self._read: set[str] = set()

    def where(self, key: str) -> str:
        return f"{self._path}.{key}" if self._path else key

    def fail(self, key: str, message: str) -> None:
        self._errors.append(f"{self.where(key)}: {message}")

    def raw(self, key: str, *, optional: bool = False) -> object:
        self._read.add(key)
        if key in self._obj:
            return self._obj[key]
        if not optional and not self._silent:
            self.fail(key, "required field is missing")
        return _MISSING

    def text(self, key: str) -> str:
        value = self.raw(key)
        if value is _MISSING:
            return ""
        if not isinstance(value, str) or not value.strip():
            self.fail(key, "must be a non-empty string")
            return ""
        return value

    def optional_text(self, key: str) -> str | None:
        value = self.raw(key, optional=True)
        if value is _MISSING or value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            self.fail(key, "must be a non-empty string or null")
            return None
        return value

    def choice(self, key: str, options: tuple[str, ...]) -> str:
        value = self.raw(key)
        if value is _MISSING:
            return ""
        if not isinstance(value, str) or value not in options:
            self.fail(key, f"must be one of: {', '.join(options)}")
            return ""
        return value

    def count(self, key: str, *, minimum: int) -> int:
        value = self.raw(key)
        if value is _MISSING:
            return 0
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            self.fail(key, f"must be an integer >= {minimum}")
            return 0
        return value

    def amount(self, key: str, *, nullable: bool = False) -> float | None:
        """A finite, non-negative number. With ``nullable``, explicit null means unknown."""
        value = self.raw(key)
        if value is _MISSING or (value is None and nullable):
            return None
        parsed, problem = _parse_amount(value)
        if problem:
            self.fail(key, problem)
        return parsed

    def child(self, key: str) -> _Fields:
        value = self.raw(key)
        if isinstance(value, dict):
            return _Fields(value, self.where(key), self._errors)
        if value is not _MISSING:
            self.fail(key, "must be an object")
        return _Fields({}, self.where(key), self._errors, silent=True)

    def children(self, key: str) -> list[_Fields]:
        value = self.raw(key)
        if value is _MISSING:
            return []
        if not isinstance(value, list):
            self.fail(key, "must be a list (empty list = none)")
            return []
        found: list[_Fields] = []
        for index, item in enumerate(value):
            where = f"{self.where(key)}[{index}]"
            if isinstance(item, dict):
                found.append(_Fields(item, where, self._errors))
            else:
                self._errors.append(f"{where}: must be an object")
        return found

    def close(self) -> None:
        for key in sorted(set(self._obj) - self._read):
            self.fail(key, "unexpected field (not in the trial schema)")


def _parse_amount(value: object) -> tuple[float | None, str | None]:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None, "must be a number (booleans and strings are not numbers)"
    try:
        as_float = float(value)
    except OverflowError:
        return None, "must be finite"
    if not math.isfinite(as_float):
        return None, "must be finite"
    if as_float < 0:
        return None, "must be non-negative"
    return as_float, None


def _parse_record(obj: dict, line_no: int, errors: list[str]) -> TrialRecord:
    fields = _Fields(obj, "", errors)
    schema = fields.raw("schema")
    if schema is not _MISSING and schema != TRIAL_SCHEMA:
        fields.fail("schema", f"must be {TRIAL_SCHEMA!r}")
    record = TrialRecord(
        line=line_no,
        trial_id=fields.text("trial_id"),
        study_id=fields.text("study_id"),
        protocol_version=fields.text("protocol_version"),
        dataset_kind=fields.choice("dataset_kind", DATASET_KINDS),
        cohort=fields.text("cohort"),
        trial_date=_iso_date(fields, "trial_date"),
        task=_task(fields.child("task")),
        system=_text_object(System, fields.child("system")),
        evaluation=_text_object(Evaluation, fields.child("evaluation")),
        provenance=_text_object(Provenance, fields.child("provenance")),
        outcome=fields.choice("outcome", OUTCOMES),
        terminal_reason=fields.choice("terminal_reason", TERMINAL_REASONS),
        intervention=_intervention(fields.child("intervention")),
        attempts=_attempts(fields.child("attempts")),
        budget=_budget(fields.children("budget")),
        resources_used=_resources(fields.children("resources_used")),
        notes=fields.optional_text("notes"),
    )
    fields.close()
    return record


def _iso_date(fields: _Fields, key: str) -> date:
    value = fields.text(key)
    if not value:
        return date.min
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        parsed = None
    if parsed is None or parsed.isoformat() != value:  # rejects week and basic formats
        fields.fail(key, "must be an ISO date YYYY-MM-DD")
        return date.min
    return parsed


def _task(fields: _Fields) -> Task:
    task = Task(
        id=fields.text("id"),
        version=fields.text("version"),
        family=fields.text("family"),
        demands=_demands(fields),
    )
    fields.close()
    return task


def _demands(fields: _Fields) -> tuple[tuple[str, int], ...]:
    raw = fields.raw("demands")
    if raw is _MISSING:
        return ()
    if not isinstance(raw, dict) or not raw:
        fields.fail("demands", "must be a non-empty object of demand label -> integer level")
        return ()
    vector: list[tuple[str, int]] = []
    for label, level in raw.items():
        if not label.strip() or isinstance(level, bool) or not isinstance(level, int) or level < 0:
            fields.fail("demands", f"{label!r} must be a named demand with an integer level >= 0")
            continue
        vector.append((label, level))
    return tuple(sorted(vector))


def _text_object(cls: type[_T], fields: _Fields) -> _T:
    """Build a dataclass whose fields are all required non-empty strings."""
    value = cls(**{f.name: fields.text(f.name) for f in dataclass_fields(cls)})
    fields.close()
    return value


def _intervention(fields: _Fields) -> Intervention:
    intervention = Intervention(
        status=fields.choice("status", INTERVENTION_STATUSES),
        evidence=fields.optional_text("evidence"),
    )
    fields.close()
    return intervention


def _attempts(fields: _Fields) -> Attempts:
    attempts = Attempts(
        count=fields.count("count", minimum=1),
        max_allowed=fields.count("max_allowed", minimum=1),
        retry_policy=fields.text("retry_policy"),
        resources_scope=fields.choice("resources_scope", (RESOURCES_SCOPE,)),
    )
    fields.close()
    return attempts


def _budget(items: list[_Fields]) -> tuple[BudgetLimit, ...]:
    limits = []
    for item in items:
        limits.append(
            BudgetLimit(
                metric=item.text("metric"),
                unit=item.text("unit"),
                limit=item.amount("limit") or 0.0,
            )
        )
        item.close()
    return tuple(sorted(limits, key=lambda b: (b.metric, b.unit)))


def _resources(items: list[_Fields]) -> tuple[ResourceObservation, ...]:
    observations = []
    for item in items:
        observations.append(
            ResourceObservation(
                metric=item.text("metric"),
                unit=item.text("unit"),
                value=item.amount("value", nullable=True),
            )
        )
        item.close()
    return tuple(sorted(observations, key=lambda o: (o.metric, o.unit)))


def _semantic_problems(record: TrialRecord) -> list[str]:
    """Rules that span fields of one record."""
    problems: list[str] = []
    status = record.intervention.status
    if status in ("observed_none", "observed_present") and not record.intervention.evidence:
        problems.append(f"intervention.evidence: required when status is {status}")
    if record.outcome == "success" and record.terminal_reason != "completed":
        problems.append("terminal_reason: a success must have terminal_reason 'completed'")
    if record.terminal_reason in _UNOBSERVABLE_REASONS and record.outcome != "indeterminate":
        problems.append(
            f"outcome: {record.terminal_reason} is outside the tested system, so the goal "
            "outcome was not observed and must be 'indeterminate'"
        )
    if record.attempts.count > record.attempts.max_allowed:
        problems.append("attempts.count: exceeds attempts.max_allowed of the declared policy")
    problems.extend(_resource_problems(record))
    return problems


def _resource_problems(record: TrialRecord) -> list[str]:
    problems: list[str] = []
    budget_metrics = [b.metric for b in record.budget]
    used_metrics = [o.metric for o in record.resources_used]
    for metric in sorted({m for m in budget_metrics if budget_metrics.count(m) > 1}):
        problems.append(f"budget: metric {metric!r} is assigned more than once")
    for metric in sorted({m for m in used_metrics if used_metrics.count(m) > 1}):
        problems.append(f"resources_used: metric {metric!r} is reported more than once")
    units = {o.metric: o.unit for o in record.resources_used}
    for limit in record.budget:
        if limit.metric in units and units[limit.metric] != limit.unit:
            problems.append(
                f"resources_used: {limit.metric!r} is reported in {units[limit.metric]!r} "
                f"but budgeted in {limit.unit!r}; units are never converted"
            )
    return problems


def _cross_record_problems(records: list[TrialRecord]) -> list[str]:
    problems: list[str] = []
    first_line: dict[str, int] = {}
    task_definition: dict[tuple[str, str], TrialRecord] = {}
    for record in records:
        seen = first_line.setdefault(record.trial_id, record.line)
        if seen != record.line:
            problems.append(
                f"line {record.line}: trial_id {record.trial_id!r} duplicates line {seen}; "
                "duplicates are rejected, never merged or reweighted"
            )
        first = task_definition.setdefault((record.task.id, record.task.version), record)
        if (first.task.family, first.task.demands) != (record.task.family, record.task.demands):
            problems.append(
                f"line {record.line}: task {record.task.id!r} version {record.task.version!r} "
                f"conflicts with its definition at line {first.line}; family and demands are "
                "fixed per task version"
            )
    return problems
