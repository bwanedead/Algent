"""Ohmega Research: trial contract, denominator policy, comparability, report safety, CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import algent_backend.ohmega_research as research
from algent_backend.agent_system.runs.control_plane.layout import RUNS_DIR_ENV
from algent_backend.ohmega_research import (
    TRIAL_SCHEMA,
    TrialValidationError,
    budget_status,
    build_analysis,
    decode_trials,
    is_confirmed,
    is_credited,
    parse_trials,
    render_html,
    summarize,
    wilson_interval,
)
from algent_backend.ohmega_research.__main__ import _RUNS_DIR_ENV, main

NO_EVIDENCE = {"status": "unknown", "evidence": None}


def _trial(trial_id: str = "t-1", **overrides) -> dict:
    record = {
        "schema": TRIAL_SCHEMA,
        "trial_id": trial_id,
        "study_id": "study-a",
        "protocol_version": "p1",
        "dataset_kind": "observed",
        "cohort": "2026-07",
        "trial_date": "2026-07-01",
        "task": {"id": "task-a", "version": "1", "family": "repair",
                 "demands": {"abstraction": 2, "branching": 1, "recovery": 1}},
        "system": {"model": "m", "harness": "h", "config_version": "c1"},
        "evaluation": {"rubric": "r", "rubric_version": "1", "evaluator": "checker-1"},
        "provenance": {"source": "unit-test", "reference": "tests/test_ohmega_research.py"},
        "outcome": "success",
        "terminal_reason": "completed",
        "intervention": {"status": "observed_none", "evidence": "full transcript reviewed"},
        "attempts": {"count": 1, "max_allowed": 1, "retry_policy": "single attempt",
                     "resources_scope": "all_attempts"},
        "budget": [{"metric": "cost", "unit": "USD", "limit": 2.0}],
        "resources_used": [{"metric": "cost", "unit": "USD", "value": 1.0}],
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(record.get(key), dict):
            record[key] = {**record[key], **value}
        else:
            record[key] = value
    return record


def _failure(trial_id: str, reason: str = "gave_up", **overrides) -> dict:
    return _trial(trial_id, outcome="failure", terminal_reason=reason, **overrides)


def _parse(*records: dict) -> list:
    return parse_trials(json.dumps(r) for r in records)


def _errors(*lines: str) -> tuple[str, ...]:
    with pytest.raises(TrialValidationError) as caught:
        parse_trials(lines)
    return caught.value.errors


def _analysis(*records: dict) -> dict:
    return build_analysis(_parse(*records), input_name="unit.jsonl", input_sha256="0" * 64)


# --- denominator policy -------------------------------------------------------------------

def test_rescued_success_is_not_zero_interference_success():
    records = _parse(
        _trial("a"),
        _trial("b", intervention={"status": "observed_present", "evidence": "operator fixed env"}),
    )
    summary = summarize(records)
    assert summary["outcomes"]["success"] == 2
    assert summary["credited_success"] == 1
    assert summary["helped_success"] == 1
    assert (summary["confirmed"]["k"], summary["confirmed"]["n"]) == (1, 2)
    assert not is_credited(records[1]) and is_confirmed(records[1])


def test_unknown_intervention_stays_out_of_the_confirmed_denominator():
    records = _parse(
        _trial("a"),
        _trial("b", intervention=NO_EVIDENCE),
        _failure("c", intervention=NO_EVIDENCE),
    )
    summary = summarize(records)
    assert summary["intervention"]["unknown"] == 2
    assert (summary["all_outcomes"]["k"], summary["all_outcomes"]["n"]) == (1, 3)
    assert (summary["confirmed"]["k"], summary["confirmed"]["n"]) == (1, 1)
    assert summary["confirmed"]["coverage"] == pytest.approx(1 / 3, abs=1e-6)


def test_failures_and_indeterminate_outcomes_keep_their_denominators():
    records = _parse(
        _trial("ok"),
        _failure("quit"),
        _failure("slow", "timeout"),
        _failure("broke", "budget_exhausted"),
        _failure("crash", "system_error"),
        _trial("unjudged", outcome="indeterminate", terminal_reason="evaluator_error"),
    )
    summary = summarize(records)
    assert summary["outcomes"] == {"success": 1, "failure": 4, "indeterminate": 1}
    assert summary["terminal_reasons"]["system_error"] == 1
    assert summary["terminal_reasons"]["evaluator_error"] == 1
    assert (summary["all_outcomes"]["k"], summary["all_outcomes"]["n"]) == (1, 6)
    assert (summary["confirmed"]["k"], summary["confirmed"]["n"]) == (1, 5)


def test_environment_outage_lowers_yield_but_not_confirmed_capability():
    records = _parse(
        _trial("ok"),
        _failure("quit"),
        _trial("outage", outcome="indeterminate", terminal_reason="environment_error"),
    )
    assert not is_confirmed(records[2]) and not is_credited(records[2])
    summary = summarize(records)
    assert summary["terminal_reasons"]["environment_error"] == 1
    assert summary["outcomes"]["indeterminate"] == 1
    assert (summary["all_outcomes"]["k"], summary["all_outcomes"]["n"]) == (1, 3)
    assert (summary["confirmed"]["k"], summary["confirmed"]["n"]) == (1, 2)


def test_missing_resources_are_unknown_never_zero():
    records = _parse(
        _trial("absent", resources_used=[]),
        _trial("null", resources_used=[{"metric": "cost", "unit": "USD", "value": None}]),
        _trial("seen", resources_used=[{"metric": "cost", "unit": "USD", "value": 1.0},
                                       {"metric": "output_tokens", "unit": "tokens",
                                        "value": 100}]),
    )
    assert [budget_status(r) for r in records] == ["unverified", "unverified", "within"]
    assert [is_credited(r) for r in records] == [False, False, True]
    summary = summarize(records)
    cost, tokens = summary["resources"]
    assert (cost["metric"], cost["observed"], cost["reported_unknown"], cost["not_reported"]) == (
        "cost", 1, 1, 1)
    assert cost["coverage"] == pytest.approx(1 / 3, abs=1e-6)
    assert cost["min"] == cost["max"] == 1.0
    assert (tokens["metric"], tokens["observed"], tokens["not_reported"]) == ("output_tokens", 1, 2)
    assert (summary["confirmed"]["n"], summary["all_outcomes"]["n"]) == (1, 3)


def test_budget_overrun_voids_credit_but_stays_visible():
    records = _parse(
        _trial("over", resources_used=[{"metric": "cost", "unit": "USD", "value": 2.5}]),
        _trial("edge", resources_used=[{"metric": "cost", "unit": "USD", "value": 2.0}]),
        _trial("free", budget=[], resources_used=[]),
    )
    assert [budget_status(r) for r in records] == ["violated", "within", "unbudgeted"]
    assert [is_credited(r) for r in records] == [False, True, True]
    summary = summarize(records)
    assert summary["budget"]["violated"] == 1
    assert (summary["confirmed"]["k"], summary["confirmed"]["n"]) == (2, 3)


# --- Wilson interval ----------------------------------------------------------------------

@pytest.mark.parametrize(
    ("k", "n", "low", "high"),
    [(0, 10, 0.0, 0.2775), (10, 10, 0.7225, 1.0), (5, 10, 0.2366, 0.7634), (1, 1, 0.2065, 1.0)],
)
def test_wilson_interval_known_values(k, n, low, high):
    interval = wilson_interval(k, n)
    assert interval == pytest.approx((low, high), abs=1e-4)


def test_wilson_interval_edges():
    assert wilson_interval(0, 0) is None
    assert wilson_interval(0, 5)[0] == 0.0
    assert wilson_interval(5, 5)[1] == 1.0
    for k, n in ((3, 2), (-1, 4), (0, -1)):
        with pytest.raises(ValueError):
            wilson_interval(k, n)


# --- strict validation --------------------------------------------------------------------

def _line(**overrides) -> str:
    return json.dumps(_trial(**overrides))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("{not json", "not valid JSON"),
        ("[1, 2]", "must be a JSON object"),
        ('{"trial_id": "a", "trial_id": "b"}', "duplicate key"),
        (_line().replace('"value": 1.0', '"value": NaN'), "non-finite number NaN"),
        (_line().replace('"value": 1.0', '"value": 1e999'), "must be finite"),
        (_line(resources_used=[{"metric": "cost", "unit": "USD", "value": -1}]), "non-negative"),
        (_line(resources_used=[{"metric": "cost", "unit": "USD", "value": True}]), "booleans"),
        (_line(resources_used=[{"metric": "cost", "unit": "USD", "value": "1.0"}]), "a number"),
        (_line(resources_used=[{"metric": "cost", "unit": "USD"}]), "value: required"),
        (_line(resources_used=[{"metric": "cost", "unit": "EUR", "value": 1}]), "never converted"),
        (_line(budget=[{"metric": "cost", "unit": "USD", "limit": float("inf")}]), "Infinity"),
        (_line(extra_field=1), "extra_field: unexpected field"),
        (_line(schema="other/9"), "schema: must be"),
        (_line(trial_date="2026-02-30"), "ISO date"),
        (_line(trial_date="20260701"), "ISO date"),
        (_line(trial_date="2026-W27-1"), "ISO date"),
        (_line(outcome="partial"), "outcome: must be one of"),
        (_line(intervention={"status": "observed_present", "evidence": None}),
         "intervention.evidence: required"),
        (_line(intervention={"status": "observed_none", "evidence": ""}), "non-empty string"),
        (_line(terminal_reason="timeout"), "a success must have terminal_reason"),
        (_line(outcome="failure", terminal_reason="evaluator_error"), "indeterminate"),
        (_line(outcome="failure", terminal_reason="environment_error"),
         "environment_error is outside the tested system"),
        (_line(attempts={"count": 3}), "exceeds attempts.max_allowed"),
        (_line(attempts={"count": True}), "attempts.count: must be an integer"),
        (_line(attempts={"resources_scope": "best_attempt"}), "resources_scope"),
        (_line(task={"demands": {}}), "task.demands"),
        (_line(task={"demands": {"branching": 1.5}}), "task.demands"),
        (_line(system="m/h/c1"), "system: must be an object"),
        (_line(budget=[{"metric": "cost", "unit": "USD", "limit": 1},
                       {"metric": "cost", "unit": "USD", "limit": 2}]), "assigned more than once"),
    ],
)
def test_malformed_records_are_rejected_with_line_numbers(text, expected):
    errors = _errors(text)
    assert all(error.startswith("line 1: ") for error in errors), errors
    assert any(expected in error for error in errors), errors


def test_missing_required_field_is_reported_once():
    record = _trial()
    del record["system"]
    errors = _errors(json.dumps(record))
    assert errors == ("line 1: system: required field is missing",)


def test_every_problem_is_reported_and_blank_lines_keep_numbering():
    errors = _errors(_line(trial_id="a"), "", _line(trial_id="b", outcome="maybe"), "{oops")
    assert any(e.startswith("line 3: outcome") for e in errors)
    assert any(e.startswith("line 4: not valid JSON") for e in errors)


def test_duplicate_trial_ids_are_rejected_not_merged():
    errors = _errors(_line(trial_id="same"), _line(trial_id="same"))
    assert errors == (
        "line 2: trial_id 'same' duplicates line 1; duplicates are rejected, never merged or "
        "reweighted",
    )


def test_task_version_definition_is_fixed():
    errors = _errors(
        _line(trial_id="a"),
        _line(trial_id="b", task={"demands": {"abstraction": 3}}),
    )
    assert any("line 2: task 'task-a' version '1' conflicts" in e for e in errors)


def test_empty_input_is_rejected():
    assert _errors("", "  ") == ("input contains no trial records",)


def test_decoding_splits_records_only_on_newlines():
    raw_separator = json.dumps(_trial("a", notes="line\u2028separator"), ensure_ascii=False)
    data = ("\ufeff" + raw_separator + "\r\n" + _line(trial_id="b") + "\n").encode("utf-8")
    records = decode_trials(data)
    assert [r.trial_id for r in records] == ["a", "b"]
    assert records[0].notes == "line\u2028separator"
    with pytest.raises(TrialValidationError, match="not valid UTF-8"):
        decode_trials(b"\xff\xfe")


# --- comparability ------------------------------------------------------------------------

def test_synthetic_and_observed_records_are_never_pooled():
    analysis = _analysis(_trial("obs"), _trial("syn", dataset_kind="synthetic"))
    assert analysis["contains_synthetic"] and analysis["mixed_dataset_kinds"]
    kinds = [p["dataset_kind"] for p in analysis["partitions"]]
    assert kinds == ["observed", "synthetic"]
    for partition in analysis["partitions"]:
        assert [c["summary"]["n"] for c in partition["cells"]] == [1]


def test_mixed_banner_disclaims_only_the_synthetic_partition():
    mixed = render_html(_analysis(_trial("obs"), _trial("syn", dataset_kind="synthetic")))
    assert "MIXED INPUT" in mixed
    assert "The OBSERVED partition remains observed evidence" in mixed
    assert "Nothing on this page measures" not in mixed
    assert "SYNTHETIC records: generated, measures no real model or harness" in mixed
    assert "OBSERVED records</h2>" in mixed
    synthetic_only = render_html(_analysis(_trial("syn", dataset_kind="synthetic")))
    assert "Nothing on this page measures any real model or harness" in synthetic_only
    observed_only = render_html(_analysis(_trial("obs")))
    assert 'class="synthetic"' not in observed_only


def test_matched_cohorts_give_a_descriptive_comparison_only():
    analysis = _analysis(
        _trial("a"),
        _failure("b", trial_date="2026-07-02"),
        _trial("c", cohort="2026-09", trial_date="2026-09-01"),
        _trial("d", cohort="2026-09", trial_date="2026-09-02"),
    )
    (partition,) = analysis["partitions"]
    (series,) = partition["series"]
    assert series["status"] == "matched_descriptive"
    assert [p["cohort"] for p in series["points"]] == ["2026-07", "2026-09"]
    (change,) = series["changes"]
    assert change["confirmed_rate_delta"] == pytest.approx(0.5)
    assert "no trend fitted" in series["statement"]
    assert "growth" not in json.dumps(partition["series"]).replace("growth not estimable", "")


@pytest.mark.parametrize(
    ("later", "differing"),
    [
        ({"task": {"version": "2"}}, ["task.version"]),
        ({"protocol_version": "p2"}, ["protocol_version"]),
        ({"evaluation": {"rubric_version": "2"}}, ["evaluation"]),
        ({"budget": [{"metric": "cost", "unit": "USD", "limit": 5.0}]}, ["budget"]),
        ({"attempts": {"max_allowed": 3, "retry_policy": "retry up to twice"}},
         ["attempt_policy"]),
    ],
)
def test_changed_conditions_split_series_and_block_growth(later, differing):
    analysis = _analysis(
        _trial("early"),
        _trial("late", cohort="2026-09", trial_date="2026-09-01", **later),
    )
    (partition,) = analysis["partitions"]
    assert len(partition["series"]) == 2
    assert all(s["status"] == "not_estimable" for s in partition["series"])
    assert partition["temporal_statement"].startswith("Growth not estimable")
    (unpooled,) = partition["unpooled"]
    assert unpooled["differing"] == differing


def test_declared_attempt_policy_is_a_condition_and_attempts_used_an_outcome():
    three = {"max_allowed": 3, "retry_policy": "retry up to twice"}
    analysis = _analysis(
        _trial("single"),
        _trial("retry-a", attempts={**three, "count": 1}, trial_date="2026-07-02"),
        _trial("retry-b", attempts={**three, "count": 3}, trial_date="2026-07-03"),
        _trial("single-late", cohort="2026-09", trial_date="2026-09-01"),
        _trial("retry-late", cohort="2026-09", trial_date="2026-09-02", attempts=three),
    )
    (partition,) = analysis["partitions"]
    july = [c for c in partition["cells"] if c["cohort"] == "2026-07"]
    assert sorted((c["attempt_policy"]["max_allowed"], c["summary"]["n"]) for c in july) == [
        (1, 1), (3, 2)]
    retry_cell = next(c for c in july if c["attempt_policy"]["max_allowed"] == 3)
    assert retry_cell["summary"]["attempts"] == {
        "total": 4, "max_per_trial": 3, "retry_policies": ["retry up to twice"]}
    assert len(partition["series"]) == 2
    for series in partition["series"]:
        policies = {c["attempt_policy"]["max_allowed"] for c in partition["cells"]
                    if c["series_id"] == series["series_id"]}
        assert len(policies) == 1
    (unpooled,) = partition["unpooled"]
    assert unpooled["differing"] == ["attempt_policy"]
    assert "max 3 attempt(s)" in render_html(analysis)


def test_neighbouring_budget_limits_never_share_a_cell_or_series():
    def at(trial_id: str, limit: float, cohort: str, day: str) -> dict:
        return _trial(trial_id, cohort=cohort, trial_date=day,
                      budget=[{"metric": "cost", "unit": "USD", "limit": limit}])

    analysis = _analysis(
        at("a", 1000.0001, "2026-07", "2026-07-01"),
        at("b", 1000.0002, "2026-07", "2026-07-01"),
        at("c", 1000.0001, "2026-09", "2026-09-01"),
        at("d", 1000.0002, "2026-09", "2026-09-01"),
    )
    (partition,) = analysis["partitions"]
    assert len(partition["cells"]) == 4
    assert len(partition["series"]) == 2
    assert all(s["status"] == "matched_descriptive" for s in partition["series"])
    assert sorted(s["budget"][0]["limit"] for s in partition["series"]) == [1000.0001, 1000.0002]
    assert sorted(s["budget_label"] for s in partition["series"]) == [
        "cost <= 1000.0001 USD", "cost <= 1000.0002 USD"]
    (unpooled,) = partition["unpooled"]
    assert unpooled["differing"] == ["budget"]


def test_different_system_configs_are_separate_series():
    analysis = _analysis(
        _trial("early"),
        _trial("late", cohort="2026-09", trial_date="2026-09-01", system={"config_version": "c2"}),
    )
    (partition,) = analysis["partitions"]
    assert len(partition["series"]) == 2
    assert partition["unpooled"] == []
    assert partition["temporal_statement"].startswith("Growth not estimable")


def test_overlapping_cohort_dates_are_not_ordered():
    analysis = _analysis(
        _trial("a1", trial_date="2026-07-01"),
        _trial("a2", trial_date="2026-07-10"),
        _trial("b", cohort="2026-07b", trial_date="2026-07-05"),
    )
    (series,) = analysis["partitions"][0]["series"]
    assert series["status"] == "not_estimable"
    assert "overlap" in series["statement"]


# --- report safety ------------------------------------------------------------------------

PAYLOAD = "</script><script>alert(1)</script><img src=x onerror=alert(2)>\u2028&"


def test_report_escapes_hostile_input_and_loads_nothing_external():
    analysis = _analysis(
        _trial("x", cohort=PAYLOAD, notes=PAYLOAD,
               task={"id": PAYLOAD, "family": PAYLOAD},
               provenance={"reference": PAYLOAD}),
    )
    page = render_html(analysis)
    assert "<script>alert(1)" not in page
    assert "<img src=x" not in page
    assert page.count("</script>") == 2
    assert "\u2028" not in page.split('id="ohmega-research-analysis">', 1)[1]
    for external in ("<link", "@import", 'src="http', "url(http"):
        assert external not in page
    embedded = page.split('id="ohmega-research-analysis">', 1)[1].split("</script>", 1)[0]
    assert json.loads(embedded) == json.loads(json.dumps(analysis))


def test_report_layout_stays_narrow_screen_safe():
    page = render_html(_analysis(_trial("a"), _failure("b")))
    assert ".row{grid-template-columns:minmax(0,1fr) auto" in page  # trial rows stack
    assert 'class="tablewrap"' in page
    assert "Full-file inventory (filters do not change these counts)" in page
    assert 'class="notes"' in page and "data-shown" in page
    assert page.index("Credited success per cell") < page.index("data-quality notes")


# --- CLI ----------------------------------------------------------------------------------

def test_cli_demo_validate_report_happy_path(tmp_path, capsys):
    out = tmp_path / "runs_data" / "demo"
    assert main(["demo", "--output", str(out)]) == 0
    trials = out / "synthetic_trials.jsonl"
    analysis = json.loads((out / "analysis.json").read_text(encoding="utf-8"))
    assert analysis["contains_synthetic"] and not analysis["mixed_dataset_kinds"]
    (partition,) = analysis["partitions"]
    assert partition["dataset_kind"] == "synthetic"
    assert partition["inventory"]["n"] == 72
    statuses = [s["status"] for s in partition["series"]]
    assert statuses.count("matched_descriptive") == 3 and len(statuses) == 6
    assert sorted(u["differing"] for u in partition["unpooled"]) == [["budget"], ["task.version"]]
    assert "SYNTHETIC DATA" in (out / "report.html").read_text(encoding="utf-8")

    assert main(["validate", "--input", str(trials)]) == 0
    assert '"valid": true' in capsys.readouterr().out
    again = tmp_path / "runs_data" / "again"
    assert main(["report", "--input", str(trials), "--output", str(again)]) == 0
    for name in ("analysis.json", "report.html"):
        assert (again / name).read_bytes() == (out / name).read_bytes()


def test_cli_demo_defaults_under_runs_data_root(tmp_path):
    assert main(["demo"]) == 0
    assert (tmp_path / "runs_data" / "ohmega_research" / "demo" / "report.html").is_file()


def test_cli_rejects_invalid_input_and_writes_nothing(tmp_path, capsys):
    source = tmp_path / "runs_data" / "bad.jsonl"
    source.parent.mkdir(parents=True)
    source.write_text(_line(trial_id="a") + "\n" + _line(trial_id="a") + "\n", encoding="utf-8")
    out = tmp_path / "runs_data" / "never"
    assert main(["report", "--input", str(source), "--output", str(out)]) == 1
    assert not out.exists()
    assert "line 2: trial_id 'a' duplicates line 1" in capsys.readouterr().err


def test_cli_refuses_to_write_into_the_source_tree():
    target = Path(research.__file__).parent / "should_not_exist"
    assert main(["demo", "--output", str(target)]) == 2
    assert not target.exists()


def test_cli_refuses_a_runs_root_that_contains_the_source_tree(monkeypatch):
    monkeypatch.setenv(RUNS_DIR_ENV, str(Path(research.__file__).parents[2]))
    assert main(["demo"]) == 2


def test_cli_honours_the_control_plane_runs_dir_contract():
    assert _RUNS_DIR_ENV == RUNS_DIR_ENV
