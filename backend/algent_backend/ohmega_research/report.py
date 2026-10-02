"""Offline report artefacts: ``analysis.json`` plus one standalone ``report.html``.

The page loads nothing external (no fonts, scripts, stylesheets or images). Every
input-derived string is HTML-escaped, and the embedded JSON is escaped so it cannot close
its script element.
"""

from __future__ import annotations

import hashlib
import json
from html import escape
from pathlib import Path

from .analysis import build_analysis
from .contracts import decode_trials

ANALYSIS_FILE = "analysis.json"
REPORT_FILE = "report.html"


def write_report(input_path: Path, output_dir: Path) -> dict[str, Path]:
    """Validate ``input_path`` and write both artefacts; nothing is written if it is rejected."""
    raw = input_path.read_bytes()
    records = decode_trials(raw)
    analysis = build_analysis(
        records, input_name=input_path.name, input_sha256=hashlib.sha256(raw).hexdigest()
    )
    artefacts = {ANALYSIS_FILE: analysis_json(analysis), REPORT_FILE: render_html(analysis)}
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, text in artefacts.items():
        (output_dir / name).write_text(text, encoding="utf-8", newline="\n")
    return {"analysis": output_dir / ANALYSIS_FILE, "report": output_dir / REPORT_FILE}


def analysis_json(analysis: dict) -> str:
    return json.dumps(analysis, indent=2, ensure_ascii=False) + "\n"


def render_html(analysis: dict) -> str:
    sections = [
        _banner(analysis),
        _overview(analysis),
        _filters(analysis),
        *(_partition(p) for p in analysis["partitions"]),
        _provenance(analysis),
    ]
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>Ohmega Research: exploratory trial report</title>"
        f"<style>{_CSS}</style></head><body><main>{''.join(sections)}</main>"
        f'<script type="application/json" id="ohmega-research-analysis">{_script_json(analysis)}'
        f"</script><script>{_FILTER_JS}</script></body></html>\n"
    )


def _e(value: object) -> str:
    return escape(str(value), quote=True)


def _script_json(data: dict) -> str:
    text = json.dumps(data, ensure_ascii=False)
    for char, code in (("&", "\\u0026"), ("<", "\\u003c"), (">", "\\u003e"),
                       ("\u2028", "\\u2028"), ("\u2029", "\\u2029")):
        text = text.replace(char, code)
    return text


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.0f}%"


def _signed(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:+.0f} pts"


def _interval(rate: dict) -> str:
    if rate["wilson95"] is None:
        return "n/a"
    low, high = rate["wilson95"]
    return f"{_pct(rate['rate'])} [{_pct(low)}, {_pct(high)}]"


def _system_label(system: dict) -> str:
    return f"{system['model']} / {system['harness']} / {system['config_version']}"


def _demands_label(demands: dict) -> str:
    return ", ".join(f"{label} {level}" for label, level in demands.items())


def _policy_label(policy: dict) -> str:
    return f"max {policy['max_allowed']} attempt(s): {policy['retry_policy']}"


def _series_label(item: dict) -> str:
    """Escaped "task vN · system · budget · attempt policy" label shared by all views."""
    return (f'{_e(item["task"]["id"])} v{_e(item["task"]["version"])} · '
            f'{_e(_system_label(item["system"]))} · {_e(item["budget_label"])} · '
            f'max {_e(item["attempt_policy"]["max_allowed"])} attempt(s)')


def _banner(analysis: dict) -> str:
    if not analysis["contains_synthetic"]:
        return ""
    if analysis["mixed_dataset_kinds"]:
        return (
            '<div class="synthetic" role="alert">MIXED INPUT: this file holds both observed and '
            "SYNTHETIC records, analysed in separate partitions and never pooled. The SYNTHETIC "
            "partition was generated to exercise the pipeline and measures no real model or "
            "harness. The OBSERVED partition remains observed evidence, read under its own "
            "coverage and caveats.</div>"
        )
    return (
        '<div class="synthetic" role="alert">SYNTHETIC DATA: generated to exercise the '
        "pipeline. Nothing on this page measures any real model or harness, and no conclusion "
        "about AI capability may be drawn from it.</div>"
    )


def _overview(analysis: dict) -> str:
    claims = "".join(
        f'<p class="claim"><b>{_e(p["dataset_kind"])}:</b> {_e(p["temporal_statement"])}</p>'
        for p in analysis["partitions"]
    )
    return (
        "<h1>Non-interference goal frontier: exploratory trial report</h1>"
        f'<p class="muted">{analysis["input"]["records"]} terminal trials from '
        f"<code>{_e(analysis['input']['name'])}</code>. Credited success = solved with no "
        "observed human intervention and within the assigned budget. The confirmed rate covers "
        "trials whose outcome and intervention were ascertained; the operational yield counts "
        "every terminal trial and is a floor, not a capability estimate. Descriptive only.</p>"
        f"{claims}"
    )


_FILTERS = (
    ("kind", "dataset", lambda kind, cell: kind),
    ("system", "system", lambda kind, cell: _system_label(cell["system"])),
    ("family", "task family", lambda kind, cell: cell["task"]["family"]),
    ("cohort", "cohort", lambda kind, cell: cell["cohort"]),
)


def _filter_attrs(kind: str, cell: dict,
                  keys: tuple[str, ...] = ("kind", "system", "family", "cohort")) -> str:
    return " ".join(
        f'data-{name}="{_e(get(kind, cell))}"' for name, _, get in _FILTERS if name in keys
    )


def _filters(analysis: dict) -> str:
    cells = [(p["dataset_kind"], c) for p in analysis["partitions"] for c in p["cells"]]
    selects = []
    for name, label, get in _FILTERS:
        values = sorted({get(kind, cell) for kind, cell in cells})
        options = "".join(f'<option value="{_e(v)}">{_e(v)}</option>' for v in values)
        selects.append(
            f'<label>{_e(label)} <select data-filter="{name}"><option value="">all</option>'
            f"{options}</select></label>"
        )
    return f'<div class="filters">{"".join(selects)}</div>'


def _scale(confirmed: dict, all_outcomes: dict) -> str:
    marks = []
    if confirmed["wilson95"] is not None:
        low, high = confirmed["wilson95"]
        marks.append(f'<span class="ci" style="left:{low * 100:.1f}%;'
                     f'width:{(high - low) * 100:.1f}%"></span>')
    if all_outcomes["rate"] is not None:
        marks.append(f'<span class="pt all" style="left:{all_outcomes["rate"] * 100:.1f}%" '
                     f'title="operational yield {_pct(all_outcomes["rate"])}"></span>')
    if confirmed["rate"] is not None:
        marks.append(f'<span class="pt conf" style="left:{confirmed["rate"] * 100:.1f}%" '
                     f'title="confirmed {_interval(confirmed)}"></span>')
    return f'<span class="scale">{"".join(marks)}</span>'


_AXIS = (
    '<div class="row axis muted"><span></span><span></span><span></span>'
    '<span class="ticks"><i>0%</i><i>25%</i><i>50%</i><i>75%</i><i>100%</i></span>'
    "<span></span></div>"
)
_LEGEND = (
    '<p class="muted legend"><span class="key conf"></span> confirmed capability rate, bar = '
    '95% Wilson interval &nbsp; <span class="key all"></span> credited operational yield over '
    "every terminal trial (conservative floor, not a capability estimate)</p>"
)


def _flags(summary: dict) -> str:
    flags = [
        ("helped", summary["helped_success"]),
        ("unknown intervention", summary["intervention"]["unknown"]),
        ("indeterminate", summary["outcomes"]["indeterminate"]),
        ("over budget", summary["budget"]["violated"]),
        ("unmetered", summary["budget"]["unverified"]),
    ]
    return " · ".join(f"{label} {count}" for label, count in flags if count) or "complete"


def _rate_spans(confirmed: dict, all_outcomes: dict) -> str:
    """The n / confirmed k of n / scale columns shared by cell rows and series rows."""
    return (
        f'<span>n {all_outcomes["n"]}</span>'
        f'<span>{confirmed["k"]}/{confirmed["n"]} confirmed<br>'
        f'<span class="muted">coverage {_pct(confirmed["coverage"])}</span></span>'
        f"{_scale(confirmed, all_outcomes)}"
    )


def _cell(kind: str, cell: dict) -> str:
    summary = cell["summary"]
    head = (
        f'<summary class="row"><span><b>{_e(cell["cohort"])}</b> · {_series_label(cell)}</span>'
        f'{_rate_spans(summary["confirmed"], summary["all_outcomes"])}'
        f'<span class="muted">{_e(_flags(summary))}</span></summary>'
    )
    attrs = _filter_attrs(kind, cell)
    return f'<details class="cell" data-row {attrs}>{head}{_drill(cell)}</details>'


def _table(header: tuple[str, ...], rows: list[tuple]) -> str:
    head = "".join(f"<th>{_e(h)}</th>" for h in header)
    body = "".join("<tr>" + "".join(f"<td>{_e(v)}</td>" for v in row) + "</tr>" for row in rows)
    return f"<table><tr>{head}</tr>{body}</table>"


def _counts(counts: dict) -> str:
    return ", ".join(f"{k} {v}" for k, v in counts.items())


def _drill(cell: dict) -> str:
    s = cell["summary"]
    evaluation = cell["evaluation"]
    facts = [
        ("operational yield (all terminal)", f"{s['all_outcomes']['k']}/{s['all_outcomes']['n']} "
                                             f"= {_interval(s['all_outcomes'])}"),
        ("confirmed capability", f"{s['confirmed']['k']}/{s['confirmed']['n']} = "
                                 f"{_interval(s['confirmed'])}"),
        ("outcomes", _counts(s["outcomes"])),
        ("terminal reasons", _counts(s["terminal_reasons"])),
        ("intervention", _counts(s["intervention"]) + f"; helped successes {s['helped_success']}"),
        ("budget", f"{cell['budget_label']}; {_counts(s['budget'])}"),
        ("attempt policy (fixed)", f"{_policy_label(cell['attempt_policy'])}; resources "
                                   f"{cell['attempt_policy']['resources_scope']}"),
        ("attempts used", f"{s['attempts']['total']} total, max "
                          f"{s['attempts']['max_per_trial']} per trial"),
        ("task", f"{cell['task']['family']}; demands {_demands_label(cell['task']['demands'])}"),
        ("clustering", f"{s['clustering']['distinct_tasks']} task(s), up to "
                       f"{s['clustering']['max_trials_per_task']} trials each"),
        ("study / protocol", f"{cell['study_id']} / {cell['protocol_version']}"),
        ("evaluation", f"{evaluation['rubric']} v{evaluation['rubric_version']} by "
                       f"{evaluation['evaluator']}"),
        ("dates", f"{cell['dates'][0]} to {cell['dates'][1]}"),
        ("cell id", cell["cell_id"]),
    ]
    resources = [
        (r["metric"], r["unit"], r["observed"], r["reported_unknown"], r["not_reported"],
         _pct(r["coverage"]), _fmt(r["min"]), _fmt(r["median"]), _fmt(r["max"]))
        for r in s["resources"]
    ]
    return (
        '<div class="drill">'
        + _table(("fact", "value"), facts)
        + "<h4>Resources (each metric separately; unreported is unknown, never zero)</h4>"
        + _table(("metric", "unit", "observed", "null", "absent", "coverage", "min", "median",
                  "max"), resources)
        + "</div>"
    )


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:g}"


def _series(kind: str, series: dict) -> str:
    rows = "".join(
        f'<div class="row"><span>{_e(p["cohort"])} <span class="muted">{_e(p["dates"][0])} to '
        f'{_e(p["dates"][1])}</span></span>{_rate_spans(p["confirmed"], p["all_outcomes"])}'
        "<span></span></div>"
        for p in series["points"]
    )
    changes = "".join(
        f'<li>{_e(c["from"])} → {_e(c["to"])}: confirmed '
        f'<span class="delta">{_signed(c["confirmed_rate_delta"])}</span>, operational yield '
        f'<span class="delta">{_signed(c["all_outcomes_rate_delta"])}</span>; intervals '
        f'{_overlap(c["confirmed_intervals_overlap"])}</li>'
        for c in series["changes"]
    )
    attrs = _filter_attrs(kind, series, ("kind", "system", "family"))
    return (
        f'<div class="series" data-row {attrs}><h4>{_series_label(series)}</h4>{rows}'
        f'<ul>{changes}</ul><p class="muted">{_e(series["statement"])}</p></div>'
    )


def _overlap(value: bool | None) -> str:
    if value is None:
        return "not comparable (an empty confirmed denominator)"
    return "overlap" if value else "do not overlap (still descriptive, not a test)"


def _temporal(kind: str, partition: dict) -> str:
    matched = [s for s in partition["series"] if s["status"] == "matched_descriptive"]
    single = [s for s in partition["series"] if s["status"] != "matched_descriptive"]
    body = "".join(_series(kind, s) for s in matched) or (
        '<p class="muted">No series spans two ordered, matched cohorts.</p>'
    )
    rest = "".join(f'<li>{_series_label(s)}: {_e(s["statement"])}</li>' for s in single)
    if rest:
        body += (f"<details><summary>{len(single)} series not comparable over time"
                 f"</summary><ul>{rest}</ul></details>")
    return f"<h3>Matched cohorts over time: {_e(partition['temporal_statement'])}</h3>{body}"


def _unpooled(partition: dict) -> str:
    if not partition["unpooled"]:
        return ""
    items = "".join(
        f'<li><b>{_e(u["task_id"])}</b> · {_e(_system_label(u["system"]))}: '
        f'{_e(u["statement"])} ('
        + "; ".join(f'v{_e(s["task_version"])}, {_e(s["budget_label"])}, '
                    f'{_e(_policy_label(s["attempt_policy"]))}, cohorts '
                    f'{_e(", ".join(s["cohorts"]))}' for s in u["series"])
        + ")</li>"
        for u in partition["unpooled"]
    )
    return f"<h3>Kept apart: same task, different conditions</h3><ul>{items}</ul>"


def _rollups(partition: dict) -> str:
    rows = [
        (r["task"]["family"], _demands_label(r["task"]["demands"]), _system_label(r["system"]),
         r["budget_label"], _policy_label(r["attempt_policy"]), r["cohort"],
         ", ".join(f'{m["id"]} v{m["version"]} ({m["n"]})' for m in r["task_mix"]),
         f'{r["summary"]["confirmed"]["k"]}/{r["summary"]["confirmed"]["n"]}',
         _interval(r["summary"]["confirmed"]), _pct(r["summary"]["confirmed"]["coverage"]))
        for r in partition["family_rollups"]
    ]
    return (
        "<details><summary><b>Task-family pools</b> (descriptive task mix; no temporal claims)"
        "</summary>"
        + _table(("family", "demands", "system", "budget", "attempt policy", "cohort",
                  "task mix", "confirmed", "rate [95%]", "coverage"), rows)
        + "</details>"
    )


_PARTITION_NOTES = {"synthetic": ": generated, measures no real model or harness"}


def _partition(partition: dict) -> str:
    kind = partition["dataset_kind"]
    inventory = partition["inventory"]
    kpis = (
        ("trials", inventory["n"]),
        ("cells", len(partition["cells"])),
        ("confirmed coverage", _pct(inventory["confirmed_coverage"])),
        ("matched series", partition["matched_series"]),
    )
    warnings = "".join(f"<li>{_e(w)}</li>" for w in partition["warnings"])
    cells = "".join(_cell(kind, c) for c in partition["cells"])
    return (
        f'<section class="partition" data-row data-kind="{_e(kind)}">'
        f"<h2>{_e(kind.upper())} records{_PARTITION_NOTES.get(kind, '')}</h2>"
        '<div class="kpis">'
        + "".join(f'<span class="kpi"><b>{_e(v)}</b>{_e(k)}</span>' for k, v in kpis)
        + f'</div><ul class="warnings">{warnings}</ul>'
        "<h3>Credited success per cell, on one 0–100% scale</h3>"
        f"{_LEGEND}{_AXIS}{cells}"
        f"{_temporal(kind, partition)}{_unpooled(partition)}{_rollups(partition)}"
        "</section>"
    )


def _provenance(analysis: dict) -> str:
    provenance = analysis["provenance"]
    methodology = "".join(
        f"<li><b>{_e(k.replace('_', ' '))}:</b> {_e(v)}</li>"
        for k, v in analysis["methodology"].items()
    )
    return (
        "<h2>Provenance and data quality</h2>"
        + _table(("input", "sha256", "records", "trial schema", "analysis schema"), [(
            analysis["input"]["name"], analysis["input"]["sha256"], analysis["input"]["records"],
            analysis["trial_schema"], analysis["schema"])])
        + "<h3>Sources</h3>"
        + _table(("source", "reference", "dataset", "trials"),
                 [(s["source"], s["reference"], s["dataset_kind"], s["n"])
                  for s in provenance["sources"]])
        + "<h3>Evaluation</h3>"
        + _table(("rubric", "version", "evaluator", "trials"),
                 [(e["rubric"], e["rubric_version"], e["evaluator"], e["n"])
                  for e in provenance["evaluations"]])
        + "<h3>Studies and protocols</h3>"
        + _table(("study", "protocol", "trials"),
                 [(p["study_id"], p["protocol_version"], p["n"]) for p in provenance["protocols"]])
        + f"<h3>Method</h3><ul>{methodology}</ul>"
    )


_CSS = """
:root{--ink:#1d1f21;--muted:#6b7075;--rule:#e3e5e8;--soft:#f5f6f8;--accent:#0b62d6;
--warn:#7a4f00;--warnbg:#fff3d1}
*{box-sizing:border-box}[hidden]{display:none!important}
body{margin:0;font:14px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;color:var(--ink)}
main{max-width:1200px;margin:0 auto;padding:24px 20px 64px}
h1{font-size:22px;margin:0 0 6px}h2{font-size:18px;margin:36px 0 6px}
h3{font-size:15px;margin:24px 0 6px}h4{font-size:13px;margin:12px 0 4px}
.muted{color:var(--muted)}.claim{font-size:16px;margin:6px 0}
.synthetic{border:3px dashed var(--warn);background:var(--warnbg);color:var(--warn);
padding:12px 16px;font-weight:700;margin-bottom:18px}
.kpis{display:flex;gap:32px;flex-wrap:wrap;margin:8px 0}.kpi b{display:block;font-size:22px}
.warnings{color:var(--muted);font-size:13px;padding-left:18px}
.filters{display:flex;gap:16px;flex-wrap:wrap;margin:14px 0;padding:8px 0;
border-top:1px solid var(--rule);border-bottom:1px solid var(--rule)}
.row{display:grid;grid-template-columns:minmax(240px,2.4fr) 56px 120px minmax(220px,3fr) 1.6fr;
gap:12px;align-items:center;padding:6px 4px;border-bottom:1px solid var(--rule)}
.axis{border-bottom:0;font-size:11px;padding-bottom:0}
.ticks{display:flex;justify-content:space-between}.ticks i{font-style:normal}
.scale{position:relative;display:block;height:14px;border-left:1px solid var(--rule);
border-right:1px solid var(--rule);background:linear-gradient(90deg,transparent 49.8%,
var(--rule) 49.8%,var(--rule) 50.2%,transparent 50.2%)}
.ci{position:absolute;top:6px;height:2px;background:var(--ink)}
.pt{position:absolute;top:2px;width:10px;height:10px;margin-left:-5px;border-radius:50%}
.pt.conf,.key.conf{background:var(--ink)}
.pt.all,.key.all{border:2px solid var(--muted);background:#fff}
.key{display:inline-block;width:10px;height:10px;border-radius:50%;vertical-align:middle}
details>summary{cursor:pointer}details.cell>summary{list-style:none}
details.cell>summary::-webkit-details-marker{display:none}
details[open]>summary{background:var(--soft)}
.drill{padding:8px 12px 14px;background:var(--soft);font-size:13px}
.series{margin:10px 0 18px}.series ul{margin:6px 0;padding-left:18px}
.delta{color:var(--accent);font-weight:600}
table{border-collapse:collapse;font-size:13px;margin:4px 0}
td,th{padding:3px 12px 3px 0;text-align:left;vertical-align:top}th{color:var(--muted);font-weight:600}
code{font-size:12px}
"""

_FILTER_JS = """
(function () {
  var controls = Array.prototype.slice.call(document.querySelectorAll("[data-filter]"));
  var rows = Array.prototype.slice.call(document.querySelectorAll("[data-row]"));
  function apply() {
    rows.forEach(function (row) {
      row.hidden = !controls.every(function (control) {
        var have = row.getAttribute("data-" + control.getAttribute("data-filter"));
        return !control.value || have === null || have === control.value;
      });
    });
  }
  controls.forEach(function (control) { control.addEventListener("change", apply); });
})();
"""
