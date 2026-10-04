"""Offline source-audit artefacts: ``source-audit.json`` plus a standalone ``source-audit.html``.

Uses the shared ``html_page`` primitives and base stylesheet, so it reads like the trial
report. Nothing external is loaded, and the page shows aggregates only, never raw
third-party rows.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from ..html_page import CSS, escape, format_number, percent, script_json, table
from .metr import audit, load_metadata, read_snapshot

AUDIT_JSON = "source-audit.json"
AUDIT_HTML = "source-audit.html"


def write_source_audit(input_path: Path, metadata_path: Path, output_dir: Path) -> dict[str, Path]:
    """Verify and audit the snapshot, then write both files; nothing is written on rejection."""
    metadata = load_metadata(metadata_path)
    runs = read_snapshot(input_path.read_bytes(), metadata)
    result = audit(runs, metadata, input_name=input_path.name)
    artefacts = {
        AUDIT_JSON: json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        AUDIT_HTML: render_source_audit(result),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, text in artefacts.items():
        (output_dir / name).write_text(text, encoding="utf-8", newline="\n")
    return {"audit": output_dir / AUDIT_JSON, "report": output_dir / AUDIT_HTML}


def render_source_audit(result: dict) -> str:
    groups = result["outcomes_by_task_group"]
    sections = [
        _first_screen(result),
        "<h2>Outcomes by reported model + scaffold</h2>"
        '<p class="muted">Descriptive share of score_binarized = 1 per group. Task mix differs '
        "between groups, so this is not a capability ranking.</p>"
        + _rate_table(result["outcomes_by_system"], "system", _system_label),
        f"<details><summary><b>Outcomes by task source and family</b> ({len(groups)} groups)"
        "</summary>" + _rate_table(groups, "task group", _task_label) + "</details>",
        _resources(result),
        _timestamps(result),
        _quality(result),
        _provenance(result),
        "<h2>Caveats</h2><ul>" + "".join(f"<li>{escape(c)}</li>" for c in result["caveats"]) + "</ul>",
    ]
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>Ohmega Research: METR source audit</title>"
        f"<style>{CSS}{_AUDIT_CSS}</style></head><body><main>{''.join(sections)}</main>"
        f'<script type="application/json" id="ohmega-source-audit">{script_json(result)}'
        "</script></body></html>\n"
    )


def _first_screen(result: dict) -> str:
    overview, source = result["overview"], result["source"]
    kpis = (
        ("observed runs", overview["runs"]),
        ("reported AI model + scaffold groups", overview["ai_systems"]),
        ("AI models", overview["ai_models"]),
        ("tasks", overview["tasks"]),
        ("human baseline runs", overview["human_baseline_runs"]),
    )
    coverage = " · ".join(
        f"{escape(r['field'])} {percent((r['zero'] + r['positive']) / r['records'])}"
        for r in result["resources"]
    )
    return (
        f'<div class="notice" role="alert">{escape(result["headline"])}</div>'
        "<h1>METR source audit: what the snapshot observes</h1>"
        f'<p class="muted"><code>{escape(source["input_name"])}</code> · pinned commit '
        f'<code>{escape(source["commit"])}</code> · bytes, sha256 and row count verified · reuse '
        "terms unverified · source audit, not converted trials</p>"
        '<div class="kpis">'
        + "".join(f'<span class="kpi"><b>{escape(v)}</b>{escape(k)}</span>' for k, v in kpis)
        + f"</div><p>Resource fields reported: {coverage}. Intervention: unknown for all "
        f'{overview["runs"]} runs. {overview["ai_systems_with_unknown_scaffold"]} AI system '
        "group(s) have no reported scaffold and are shown as “unknown”.</p>"
    )


def _system_label(row: dict) -> str:
    human = row["human_baseline"]
    tag = ' <span class="muted">(human baseline, not a tested system)</span>' if human else ""
    return (f'<b>{escape(row["model"])}</b>{tag}<br><span class="muted">scaffold: '
            f'{escape(row["scaffold"])} · {escape(", ".join(row["aliases"]))}</span>')


def _task_label(row: dict) -> str:
    return (f'<b>{escape(row["task_source"])}</b> / {escape(row["task_family"])}<br>'
            f'<span class="muted">{row["systems"]} system group(s)</span>')


def _bar(row: dict) -> str:
    low, high = row["wilson95"]
    return (
        f'<span class="scale bar"><span class="ci" style="left:{low * 100:.1f}%;'
        f'width:{(high - low) * 100:.1f}%"></span>'
        f'<span class="pt conf" style="left:{row["rate"] * 100:.1f}%"></span></span>'
    )


def _rate_table(rows: list[dict], label: str, describe: Callable[[dict], str]) -> str:
    head = "".join(f"<th>{h}</th>" for h in (label, "runs", "score 1", "rate [95%]",
                                              "0–100%", "task mix"))
    body = "".join(
        f"<tr><td>{describe(r)}</td><td>{r['n']}</td><td>{r['score_binarized_1']}</td>"
        f"<td>{percent(r['rate'])} [{percent(r['wilson95'][0])}, {percent(r['wilson95'][1])}]</td>"
        f"<td>{_bar(r)}</td><td>{r['tasks']} tasks, {len(r['task_version_mix'])} version "
        f"label(s), up to {r['max_runs_per_task']} runs per task</td></tr>"
        for r in rows
    )
    return f'<div class="tablewrap"><table><tr>{head}</tr>{body}</table></div>'


def _resources(result: dict) -> str:
    rows = [
        (r["field"], r["records"], r["absent"], r["null"], r["zero"], r["positive"],
         *(format_number(r[k]) for k in ("min", "median", "p95", "max")), r["note"])
        for r in result["resources"]
    ]
    return (
        "<h2>Resource fields, as reported observations</h2>"
        + table(("field", "records", "absent", "null", "zero", "positive", "min", "median",
                 "p95", "max", "meaning"), rows)
        + '<p class="muted">Absent, null and zero are counted separately and never merged. '
        "Nothing is converted to FLOPs or dollars-per-compute, and no budget is inferred.</p>"
    )


def _timestamps(result: dict) -> str:
    rows = [
        (t["field"], t["plausible_ms"], t["null"], t["absent"], t["zero"], t["short"],
         t["above_range"], t["questionable"],
         " to ".join(t["evaluation_dates"]) if t["evaluation_dates"] else "n/a")
        for t in result["timestamps"]
    ]
    return (
        "<h2>Evaluation timestamps</h2>"
        + table(("field", "plausible ms", "null", "absent", "zero", "short", "above range",
                 "questionable", "evaluation dates"), rows)
        + '<p class="muted">Only Unix milliseconds between 2020 and 2030 count as evaluation '
        "dates. Zero, short and out-of-range values are flagged, not reinterpreted, and their "
        "runs stay in every other count. Evaluation dates are not model release dates.</p>"
    )


def _quality(result: dict) -> str:
    q = result["data_quality"]
    fatal = q["fatal_error_from"]
    facts = [
        ("intervention", f"unknown for all {result['intervention']['unknown']} runs (not recorded)"),
        ("scaffold", f"reported {q['scaffold']['reported']}, null {q['scaffold']['null']}, "
                     f"absent {q['scaffold']['absent']} (missing = unknown, never inferred)"),
        ("task_version", f"null {q['task_version_null']}"),
        ("fatal_error_from", f"reported {fatal['reported']}, null {fatal['null']}, absent "
                             f"{fatal['absent']}; recorded as given, no outcome is derived"),
        ("cloned", f"absent {q['cloned']['absent']}, null {q['cloned']['null']}, zero "
                   f"{q['cloned']['zero']}, positive {q['cloned']['positive']}"),
        ("unused source fields", ", ".join(f"{k} ({v})" for k, v in q["extra_fields"].items())
         or "none"),
    ]
    return (
        "<h2>Data quality</h2>" + table(("aspect", "observation"), facts)
        + "<details><summary>fatal_error_from values</summary>"
        + table(("value", "runs"), list(fatal["values"].items())) + "</details>"
    )


def _provenance(result: dict) -> str:
    source = result["source"]
    keys = ("source_url", "commit", "sha256", "bytes", "rows", "license_status", "purpose")
    rows = [(k, source[k]) for k in keys]
    rows += [("verified", ", ".join(source["verified"])),
             ("raw rows copied", "no: aggregates and identifiers only")]
    return "<h2>Source provenance</h2>" + table(("field", "value"), rows)


_AUDIT_CSS = """
.notice{border:3px solid var(--ink);padding:12px 16px;font-weight:700;margin-bottom:18px}
.bar{min-width:140px}
"""
