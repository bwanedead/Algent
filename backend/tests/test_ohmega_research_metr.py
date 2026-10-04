"""Ohmega Research METR source audit.

Every fixture is a tiny METR-shaped test row written to a temp dir. No third-party data is
committed or read here.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from algent_backend.ohmega_research.__main__ import main
from algent_backend.ohmega_research.benchmarks import (
    SourceValidationError,
    audit,
    load_metadata,
    read_snapshot,
    render_source_audit,
)

PLAUSIBLE_MS = 1_750_000_000_000.0  # 2025-06-15 UTC


def _row(run_id: object = "r-1", **overrides) -> dict:
    row = {
        "run_id": run_id, "task_id": "fam_a/task_1", "task_version": "1.0",
        "task_family": "fam_a", "task_source": "HCAST", "alias": "Model A (test)",
        "model": "model_a", "score_binarized": 1, "score_cont": 1.0, "human_minutes": 12.5,
        "human_source": "baseline", "human_score": 3.2, "scaffold": "test/react",
        "tokens_count": 1000.0, "generation_cost": 0.0, "time_limit": None,
        "started_at": PLAUSIBLE_MS, "completed_at": PLAUSIBLE_MS + 60_000, "cloned": 0.0,
        "fatal_error_from": None,
    }
    row.update(overrides)
    return row


def _without(row: dict, *keys: str) -> dict:
    return {k: v for k, v in row.items() if k not in keys}


def _files(tmp_path, lines: list[str], **meta):
    snapshot = tmp_path / "runs_data" / "fixture-runs.jsonl"
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    raw = ("\n".join(lines) + "\n").encode("utf-8")
    snapshot.write_bytes(raw)
    metadata = {
        "source_url": "https://example.invalid/test-fixture.jsonl", "commit": "0" * 40,
        "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "rows": len(lines),
        "license_status": "test fixture", "purpose": "unit test", **meta,
    }
    meta_path = snapshot.with_name("fixture-source.json")
    meta_path.write_text(json.dumps(metadata), encoding="utf-8")
    return snapshot, meta_path


def _audit(tmp_path, *rows: dict) -> dict:
    snapshot, meta_path = _files(tmp_path, [json.dumps(r) for r in rows])
    metadata = load_metadata(meta_path)
    return audit(read_snapshot(snapshot.read_bytes(), metadata), metadata,
                 input_name=snapshot.name)


def _errors(tmp_path, lines: list[str], **meta) -> tuple[str, ...]:
    snapshot, meta_path = _files(tmp_path, lines, **meta)
    with pytest.raises(SourceValidationError) as caught:
        read_snapshot(snapshot.read_bytes(), load_metadata(meta_path))
    return caught.value.errors


# --- identity and metadata ----------------------------------------------------------------

def test_duplicate_run_ids_are_rejected_including_int_and_string_forms(tmp_path):
    errors = _errors(tmp_path, [json.dumps(_row(0)), json.dumps(_row("0"))])
    assert errors == ("line 2: run_id '0' duplicates line 1",)


def test_duplicate_json_keys_are_rejected(tmp_path):
    errors = _errors(tmp_path, ['{"run_id": "a", "run_id": "b"}'])
    assert any("line 1: not valid JSON (duplicate key 'run_id')" in e for e in errors)


@pytest.mark.parametrize(
    ("meta", "expected"),
    [
        ({"sha256": "f" * 64}, "does not match metadata"),
        ({"bytes": 3}, "metadata says 3"),
        ({"rows": 5}, "snapshot has 1 rows; metadata says 5"),
        ({"bytes": True}, "bytes: invalid value"),
        ({"sha256": "ABC"}, "sha256: invalid value"),
        ({"extra": "x"}, "extra: unexpected field"),
    ],
)
def test_metadata_mismatches_are_errors(tmp_path, meta, expected):
    errors = _errors(tmp_path, [json.dumps(_row())], **meta)
    assert any(expected in e for e in errors), errors


# --- consumed values ----------------------------------------------------------------------

@pytest.mark.parametrize(
    ("row", "expected"),
    [
        (_row(score_binarized=0.5), "score_binarized: must be 0 or 1"),
        (_row(score_binarized=2), "score_binarized: must be 0 or 1"),
        (_row(score_binarized=True), "score_binarized: must be a number"),
        (_row(score_binarized="1"), "score_binarized: must be a number"),
        (_row(score_cont=1.2), "score_cont: must be within [0, 1]"),
        (_row(score_cont=-0.1), "score_cont: must be non-negative"),
        (_row(score_cont=None), "score_cont: must be a number"),
        (_row(tokens_count=-1), "tokens_count: must be non-negative"),
        (_row(generation_cost=False), "generation_cost: must be a number"),
        (_row(human_minutes=-3), "human_minutes: must be non-negative"),
        (_row(started_at=-1), "started_at: must be non-negative"),
        (_row(task_id=""), "task_id: must be a non-empty string"),
        (_row(scaffold=""), "scaffold: must be a non-empty string or null"),
        (_row(run_id=True), "run_id: must be a non-empty string"),
        (_without(_row(), "alias"), "alias: required field is missing"),
        (_without(_row(), "task_version"), "task_version: required field is missing"),
    ],
)
def test_malformed_rows_are_rejected_with_line_numbers(tmp_path, row, expected):
    errors = _errors(tmp_path, [json.dumps(row)])
    assert all(e.startswith("line 1: ") for e in errors), errors
    assert any(expected in e for e in errors), errors


@pytest.mark.parametrize("token", ["NaN", "Infinity", "1e999"])
def test_nonfinite_metrics_are_rejected(tmp_path, token):
    line = json.dumps(_row(tokens_count=7.5)).replace("7.5", token)
    errors = _errors(tmp_path, [line])
    assert errors and all(e.startswith("line 1: ") for e in errors), errors


def test_unconstrained_extra_fields_are_allowed_but_listed(tmp_path):
    result = _audit(tmp_path, _row(human_score=4.7, equal_task_weight=0.1))
    assert result["data_quality"]["extra_fields"] == {"equal_task_weight": 1, "human_score": 1}


# --- observations -------------------------------------------------------------------------

def test_absent_null_and_zero_are_counted_separately(tmp_path):
    result = _audit(
        tmp_path,
        _row("zero", generation_cost=0.0),
        _row("null", generation_cost=None),
        _without(_row("absent"), "generation_cost"),
        _row("paid", generation_cost=2.5),
    )
    cost = next(r for r in result["resources"] if r["field"] == "generation_cost")
    assert {k: cost[k] for k in ("records", "absent", "null", "zero", "positive")} == {
        "records": 4, "absent": 1, "null": 1, "zero": 1, "positive": 1}
    assert (cost["min"], cost["max"]) == (0.0, 2.5)
    assert "unverified" in cost["note"]


def test_missing_scaffold_is_unknown_and_never_invented(tmp_path):
    result = _audit(
        tmp_path,
        _row("a", scaffold=None),
        _without(_row("b"), "scaffold"),
        _row("c", scaffold="other/agent"),
    )
    systems = {(s["model"], s["scaffold"]): s for s in result["outcomes_by_system"]}
    assert set(systems) == {("model_a", "unknown"), ("model_a", "other/agent")}
    assert systems[("model_a", "unknown")]["n"] == 2
    assert systems[("model_a", "unknown")]["scaffold_reported"] is False
    assert result["overview"]["ai_systems_with_unknown_scaffold"] == 1
    assert result["data_quality"]["scaffold"] == {"reported": 1, "null": 1, "absent": 1}


def test_timestamp_sentinels_are_flagged_and_runs_kept(tmp_path):
    result = _audit(
        tmp_path,
        _row("ok"),
        _row("zero", started_at=0.0),
        _row("short", started_at=1_020_000.0),
        _row("null", started_at=None),
        _without(_row("absent"), "started_at"),
        _row("future", started_at=9e12),
    )
    started = next(t for t in result["timestamps"] if t["field"] == "started_at")
    assert {k: started[k] for k in ("plausible_ms", "zero", "short", "null", "absent",
                                    "above_range", "questionable")} == {
        "plausible_ms": 1, "zero": 1, "short": 1, "null": 1, "absent": 1, "above_range": 1,
        "questionable": 3}
    assert started["evaluation_dates"] == ["2025-06-15", "2025-06-15"]
    assert result["overview"]["runs"] == 6


def test_human_baselines_are_not_tested_systems(tmp_path):
    result = _audit(
        tmp_path,
        _row("ai"),
        _row(0, alias="human", model="human", task_version=None, scaffold=None),
    )
    overview = result["overview"]
    assert (overview["runs"], overview["ai_runs"], overview["human_baseline_runs"]) == (2, 1, 1)
    assert overview["ai_systems"] == 1
    human = next(s for s in result["outcomes_by_system"] if s["model"] == "human")
    assert human["human_baseline"] is True
    assert human["task_version_mix"] == {"unknown": 1}


def test_intervention_is_never_inferred(tmp_path):
    result = _audit(tmp_path, _row("a"), _row("b", intervention="none", fatal_error_from="x"))
    assert result["intervention"]["unknown"] == 2
    assert result["intervention"]["observed_none"] == 0
    assert result["data_quality"]["extra_fields"] == {"human_score": 2, "intervention": 1}
    assert result["data_quality"]["fatal_error_from"]["values"] == {"x": 1}
    assert "Non-interference not identifiable" in result["headline"]


def test_outcomes_are_descriptive_by_exact_group(tmp_path):
    result = _audit(
        tmp_path,
        _row("a"),
        _row("b", score_binarized=0, score_cont=0.2),
        _row("c", task_id="fam_b/task_9", task_family="fam_b", task_version=None),
    )
    (system,) = result["outcomes_by_system"]
    assert (system["n"], system["score_binarized_1"], system["rate"]) == (3, 2, 0.666667)
    assert system["task_version_mix"] == {"1.0": 2, "unknown": 1}
    families = {g["task_family"]: g["n"] for g in result["outcomes_by_task_group"]}
    assert families == {"fam_a": 2, "fam_b": 1}


# --- rendering ----------------------------------------------------------------------------

PAYLOAD = "</script><script>alert(1)</script><img src=x onerror=alert(2)>"


def test_source_audit_html_escapes_input_and_loads_nothing_external(tmp_path):
    result = _audit(tmp_path, _row(alias=PAYLOAD, model=PAYLOAD, scaffold=PAYLOAD,
                                   task_family=PAYLOAD, fatal_error_from=PAYLOAD))
    page = render_source_audit(result)
    assert "<script>alert(1)" not in page and "<img src=x" not in page
    assert page.count("</script>") == 1
    for external in ("<link", "@import", 'src="http', "url(http"):
        assert external not in page
    embedded = page.split('id="ohmega-source-audit">', 1)[1].split("</script>", 1)[0]
    assert json.loads(embedded) == json.loads(json.dumps(result))


# --- CLI ----------------------------------------------------------------------------------

def test_cli_audit_metr_happy_path(tmp_path, capsys):
    rows = [_row("r-1"), _row("r-2"), _row("r-3", score_binarized=0, score_cont=0.0)]
    snapshot, meta_path = _files(tmp_path, [json.dumps(r) for r in rows])
    out = tmp_path / "runs_data" / "audit"
    argv = ["audit-metr", "--input", str(snapshot), "--source-metadata", str(meta_path)]
    assert main([*argv, "--output", str(out)]) == 0
    text = (out / "source-audit.json").read_text(encoding="utf-8")
    result = json.loads(text)
    assert result["schema"] == "ohmega.research.source-audit/1"
    assert result["overview"]["runs"] == 3
    assert result["outcomes_by_system"][0]["score_binarized_1"] == 2
    assert "r-1" not in text  # aggregates only, no raw rows
    assert "Non-interference not identifiable" in (out / "source-audit.html").read_text(
        encoding="utf-8")
    assert "Source audit only" in capsys.readouterr().out
    assert main(argv) == 0
    default = tmp_path / "runs_data" / "ohmega_research" / "audit-metr" / "source-audit.json"
    assert default.read_bytes() == (out / "source-audit.json").read_bytes()


def test_cli_audit_metr_rejection_writes_nothing(tmp_path, capsys):
    snapshot, meta_path = _files(tmp_path, [json.dumps(_row())], sha256="f" * 64)
    out = tmp_path / "runs_data" / "never"
    argv = ["audit-metr", "--input", str(snapshot), "--source-metadata", str(meta_path),
            "--output", str(out)]
    assert main(argv) == 1
    assert not out.exists()
    assert "does not match metadata" in capsys.readouterr().err
