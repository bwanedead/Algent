"""
Ad-hoc visuals for the daily — the reader's picture where the prose is the harder way to understand something.

After the day's sections are final, ONE planning call reads the whole report's sourced material (``visuals_facts``)
and proposes 1-3 visuals when the material supports them (none only with a stated reason), each tied to a theater and each answering a question prose answers worse. Each is then
drawn by the EXISTING article analytics machinery (``editorial.analytics_worker.fulfill_request``: scratch folder,
coding harness grok/codex, escape guard, figure check, geometry check) through a small adapter, uploaded through
``publishing.asset_store`` and attached to its section as ``section["visuals"]`` (additive; older readers ignore it).

Doctrine of the planner (full text in ``PLAN_ROLE``): value over form; every number, dimension and fact comes from a
cited fact (or a public spec the harness fetches and names); a schematic says it is one. Code-rendered only.

Failure of any visual (planning, readiness, drawing, upload) is a line in the returned report, never a failed day.
Cost: one house-model call plus, per visual, one subscription harness run (and one canary run per day that draws).
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import Any, Literal

from pydantic import BaseModel, Field

from . import flags
from . import visuals_facts as vf
from . import visuals_store
from .visuals_grounding import ungrounded as _ungrounded      # the one grounding rule (scene_spec shares it)

#: What a visual can BE. ``kind`` in the record. Chart-like forms are drawn as charts, the rest as illustrations.
Form = Literal["chart", "timeline", "mapstory", "network", "flow", "tracker_compare", "comparison", "map", "scale", "schematic", "before_after", "scene3d"]
_CHARTLIKE = {"chart", "comparison"}
#: Forms the SITE draws natively and interactively from a validated data spec (no coding harness): a second
#: structured model call after planning (``native_forms``), like ``scene3d`` (``scene3d.py``).
_NATIVE = {"timeline", "mapstory", "network", "flow", "tracker_compare"}
#: Forms that are drawings of a structure or system, not measurements: they must say so under the picture.
_SIGNPOSTED = {"schematic"}
SIGNPOST = "Schematic, not to exact detail."
_SIGNPOST_WORDS = re.compile(r"schematic|illustrat|not to (exact|scale)|diagram", re.I)

MIN_FACTS = 4               # below this the day holds too little to draw from; skip the planning call
FACT_CHARS = 600
PROMPT_CHARS = 45_000       # the planner's reading budget
SITE_DIR = "/analytics/daily"



class VisualAsk(BaseModel):
    theater_id: str
    form: Form = "chart"
    finding: str = ""            # the title: the FINDING a reader gets in three seconds
    caption: str = ""            # one line under the picture, written to the reader
    reader_question: str = ""    # the question this answers, in reader words
    why_not_prose: str = ""      # why this form beats the paragraph
    fact_ids: list[str] = Field(default_factory=list)
    spec: str = ""               # what to draw: marks, units, labels, direct annotation
    source_hint: str = ""        # ONLY for a form that needs a public spec the facts lack (hull dimensions, ranges)


class VisualPlan(BaseModel):
    visuals: list[VisualAsk] = Field(default_factory=list)
    none_because: str = ""


PLAN_ROLE = """\
You are the visuals editor of an intelligence daily. You have the day's SOURCED FACTS, numbered.

PURPOSE. A visual earns its place when it makes the reader understand the world more richly than the words alone:
how something works, how things relate, how something unfolded, how resources, power or support move. It may be
grasped at a glance, or be something worth exploring for minutes because it is dense with information that is easy
to absorb. Richness and real understanding are the goal, not speed.

IT MAY GO BEYOND THE TEXT. A visual need not restate a section. It can bring in related context the reader did not
know they needed: the grain flows behind a Black Sea story, the power grid behind a strike campaign, the funding web
behind a militia. It must be genuinely connected to what is happening; a tangent with no bearing on the situation
does not qualify. Every visual should stand on its own as a piece of content: posted alone (on X, say), it would
still tell someone something real about the world.

FORMS (choose whichever conveys the most; name the question it answers in `reader_question` and why it beats prose
in `why_not_prose`):
- How something UNFOLDED: events, strikes or moves played in order with their consequences, over a map: `mapstory`.
- A LIVING NETWORK: who backs, funds, arms, opposes, sanctions or depends on whom, and how those ties changed over
  time; the reader taps a party to see its ties: `network`. Every tie must be stated by a cited fact naming both ends.
- FLOWS between places: goods, energy, money, weapons or people moving along routes, with widths where the facts
  give amounts, and what happens when a route breaks and the traffic reroutes: `flow`.
- OUR OWN TRACKERS COMPARED: several of our measured series (chokepoint transits, tanker counts, aircraft or fire
  counts, energy storage, rates) on one interactive chart, indexed to a common start, with the day's developments
  marked on it: `tracker_compare`. It carries no number you write: name the theater story it illuminates in `spec`
  and the series are chosen from our catalog when it is built. Use it whenever setting our tracked series side by
  side shows more than any one of them (transits against tanker counts, a route against its alternative).
- A CAUSE-AND-EFFECT CHAIN: one decision rippling to concrete outcomes with the real numbers: `schematic`
  (labelled as one), or a `timeline` when the order is the point.
- SYSTEM STATE: how much of a grid, fleet, supply or alliance is intact versus lost, and how that is changing:
  `chart`, `comparison` or `before_after`.
- A BEFORE/AFTER of a structure, a balance of power or a network: `before_after`.
- Quantities, trends, comparisons when a chart is simply clearest: `chart`, `comparison`.
- A dated sequence the reader may want for reference: `timeline` (shown collapsed, opt-in; use sparingly).
- `scene3d` ONLY when depth or true relative size IS the understanding and nothing flat can show it (a mechanism's
  layout, a to-scale comparison that changes what the reader thinks is possible). Never for scenery.
`map`, `scale` and `schematic` remain available when an annotated map, a to-scale drawing or a cutaway explains a
mechanism; never as decoration.

THE QUALITY GATE. Every proposed visual must pass ALL of these, or do not propose it:
1. NOT LAME: would a reader actually stop and engage, or scroll past? Novelty for novelty's sake fails.
2. REAL VALUE: does it noticeably increase understanding of an important dynamic, a confusing relationship or the
   wider system? Decorating what the text already says plainly fails.
3. RELEVANT: clearly connected to the situation, even if it is background context.
4. WE CAN MAKE IT WELL: polished, legible and accurate with the facts we hold. If the material would make it rough,
   thin or clunky, do not make it; a mediocre visual is worse than none.
5. TRUE: every number, place, date and relationship traces to a cited fact (see GROUNDING); anything illustrative is
   labelled as such.
6. STANDALONE: it would still mean something posted on its own.
RULED OUT: scenery or terrain for its own sake (map services already do that better), decorative 3D, restating a
single number as a picture, a diagram of a sentence, a status or evidence ledger, anything whose main appeal is
"it's 3D" or "it moves".

HOW MANY. None on a day when nothing passes the gate (say why in `none_because`); several on a day whose material is
rich (at most 3). The bar never moves to fill a quota.

GROUNDING. Every number, date, dimension and relationship in a visual comes from a cited fact: list its id in
`fact_ids` (at least two facts, or one plus a `source_hint`). You may NOT write a number of your own in `finding`,
`caption` or `spec` that is not in the cited facts (dates as the facts give them are fine; quote a figure exactly,
never round or derive one). A `timeline`, `mapstory`, `network` or `flow` is built from the cited facts ALONE, so cite every fact that
gives one of its events, steps, ties or routes (its dates, places, parties and figures all come from them; a tie or a
route whose two ends no cited fact names is dropped). A `tracker_compare` draws only from our instruments store; cite
the facts that give the dated developments to mark on it. A form that needs published specifications the facts lack (a
submarine's length, a missile's range) sets `source_hint` to the exact public source to fetch; it is drawn only if
the source can be named under the picture. Never invent positions, boundaries, ranges or capabilities.

HONESTY OF FORM. Code-drawn only, no generated art. A schematic says so in `caption` ("Schematic, not to
exact detail"). `finding` states the finding ("Strikes tripled in four days"), not the measure; `caption` is one
plain sentence to the reader, never about "the reader" or why we made it. Label directly on the plot; units in
words; no legends to match; no dual axes. Prefer the whole field to a hand-picked handful.
"""


def validate(plan: Any, facts: list[vf.Fact], theater_ids: set[str], cap: int) -> tuple[list[tuple[VisualAsk, list[vf.Fact]]], list[str]]:
    """The asks that survive, each with its cited facts, and a reason for every one that did not. Mechanical floor:
    a real theater, resolvable facts, enough of them, no number of the planner's own, a reader-facing title, one
    visual per theater, at most ``cap``."""
    if not isinstance(plan, VisualPlan):
        return [], ["planner returned no plan"]
    by_id = {f.id: f for f in facts}
    kept: list[tuple[VisualAsk, list[vf.Fact]]] = []
    dropped: list[str] = []
    from algent_backend.agent_system.agents.editorial.analytics_router import is_reader_facing
    from algent_backend.agent_system.agents.editorial.analytics_contracts import AnalyticsRequest
    for ask in plan.visuals:
        tag = f"{ask.theater_id}/{ask.form}"
        hint = "" if ask.form in _NATIVE else ask.source_hint.strip()      # native forms stand on the day's facts alone
        cited = [by_id[i] for i in dict.fromkeys(ask.fact_ids) if i in by_id]
        if ask.theater_id not in theater_ids:
            dropped.append(f"{tag}: not a theater in the report")
        elif any(a.theater_id == ask.theater_id for a, _ in kept):
            dropped.append(f"{tag}: theater already has a visual")
        elif ask.form == "scene3d" and not flags.scene3d_enabled():
            dropped.append(f"{tag}: 3D scenes are switched off")
        elif ask.form in _NATIVE and not flags.native_forms_enabled():
            dropped.append(f"{tag}: native interactive forms are switched off")
        elif len(kept) >= cap:
            dropped.append(f"{tag}: over the daily cap of {cap}")
        elif not (ask.finding.strip() and ask.caption.strip() and ask.spec.strip()):
            dropped.append(f"{tag}: missing finding, caption or spec")
        elif len(cited) < (1 if hint else 2):
            dropped.append(f"{tag}: cites too few of the report's facts")
        elif bad := _ungrounded(" ".join((ask.finding, ask.caption, ask.spec)), " ".join(f.text for f in cited)) \
                if not hint else []:
            dropped.append(f"{tag}: numbers not in the cited facts ({', '.join(bad[:4])})")
        elif not is_reader_facing(AnalyticsRequest(id="x", kind="chart", title=ask.finding, question=ask.caption,
                                                   spec=ask.spec)):
            dropped.append(f"{tag}: an evidence ledger, not a picture")
        else:
            kept.append((ask, cited))
    return kept, dropped


def _request(ask: VisualAsk, cited: list[vf.Fact], n: int, as_of: str):
    from algent_backend.agent_system.agents.editorial.analytics_contracts import AnalyticsRequest

    caption = ask.caption.strip()
    if ask.form in _SIGNPOSTED and not _SIGNPOST_WORDS.search(caption):
        caption = f"{caption.rstrip()} {SIGNPOST}"
    klass = {"chart": "data_chart", "comparison": "comparison", "map": "locator_map"}.get(
        ask.form, "process_diagram" if ask.form in ("schematic", "flow") else "other")
    # "anx_": the worker only treats anx_*/req_* folders as its own scratch (see its _is_scratch_dir)
    return AnalyticsRequest(
        id=f"anx_dv{as_of.replace('-', '')}_{n}", kind="chart" if ask.form in _CHARTLIKE else "image",
        title=ask.finding.strip(), question=caption, spec=ask.spec.strip(), data_refs=[f.id for f in cited],
        may_source=bool(ask.source_hint.strip()), source_hint=ask.source_hint.strip(), visual_class=klass,
        priority="high_value", placement="after_opening", reader_gap=ask.why_not_prose.strip(),
        factual_basis="the daily's cited facts" + (f" and {ask.source_hint.strip()}" if ask.source_hint.strip() else ""),
        rationale=ask.reader_question.strip())


def _message(facts: list[vf.Fact], sections: list[dict], cap: int) -> str:
    heads = "\n".join(f"- {s.get('theater_id')}: {s.get('name')} -- {s.get('headline') or s.get('bottom_line', '')[:160]}"
                      for s in sections)
    lines, used = [], 0
    for f in facts:
        src = ", ".join(vf.source_label(s)[0] for s in f.sources[:3]) or "unsourced"
        line = f"[{f.id}] ({f.kind}, {f.theater_id}) {f.text[:FACT_CHARS]} -- {src}"
        used += len(line)
        if used > PROMPT_CHARS:
            break
        lines.append(line)
    return (f"THEATERS:\n{heads}\n\nSOURCED FACTS (cite by id):\n" + "\n".join(lines) +
            f"\n\nTASK: look for where a picture beats the paragraph and propose up to {cap} visuals (one to {cap} when the "
            f"material supports it; none only with `none_because`). Cite fact ids; write no numbers of your own.")


class _Capture:
    """The worker's context seam: it writes finished figures through ``artifacts`` and reports through ``emit``.
    Here the bytes stay in memory for the upload instead of landing in a run folder."""

    def __init__(self, emit: Callable[..., Any] | None) -> None:
        self.files: dict[str, bytes] = {}
        self._emit = emit
        self.artifacts = self

    def write_bytes(self, name: str, data: bytes, kind: str = "") -> None:
        self.files[name] = data

    def write_text(self, name: str, text: str, kind: str = "") -> None:
        self.files[name] = text.encode("utf-8")

    def write_json(self, name: str, payload: Any, kind: str = "") -> None:
        pass

    def emit(self, *a: Any, **k: Any) -> None:
        if self._emit is not None:
            try:
                self._emit(*a, **k)
            except Exception:  # noqa: BLE001 - telemetry never gates a figure
                pass


@contextmanager
def _harness_env(name: str):
    """The analytics harness is chosen from the environment at call time; scope the daily's choice to this block."""
    key, old = "ALGENT_ANALYTICS_HARNESS", os.environ.get("ALGENT_ANALYTICS_HARNESS")
    if name:
        os.environ[key] = name
    try:
        yield
    finally:
        if name:
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


def _ready() -> tuple[bool, str]:
    from algent_backend.agent_system.agents.editorial import analytics_worker as w

    ok, note = w.workspace_stack_ready()
    if not ok:
        return False, note
    return w.canary(w.default_workspace())


def _upload(files: dict[str, bytes]) -> dict:
    """Local first (``visuals_store``: the server keeps a copy under intel_store/visuals/), then the bucket."""
    from algent_backend.publishing import asset_store

    return visuals_store.local_first(asset_store.upload)(files)


def _record(art: Any, ask: VisualAsk, cited: list[vf.Fact], path: str, raster: str) -> dict:
    srcs: dict[str, str] = {}
    for f in cited:
        for s in f.sources:
            label, url = vf.source_label(s)
            srcs.setdefault(url or label, label)
    for url in re.findall(r"https?://[^\s)\]>,;]+", art.caption or ""):
        srcs.setdefault(url.rstrip(".'\""), vf.source_label(url)[0])
    caption = art.question or ask.caption
    return {"id": art.request_id, "kind": ask.form, "title": art.title, "caption": caption,
            "reader_question": ask.reader_question, "asset": path, "raster": raster,
            "schematic": ask.form in _SIGNPOSTED, "as_of": art.as_of, "ai_label": art.ai_label,
            "sources": [{"label": label, "url": url if url.startswith("http") else ""} for url, label in srcs.items()],
            "detail": art.caption, "generator": art.generator, "model": art.model}


def _trustworthy(art: Any) -> bool:
    """Produced, and the figure check found nothing it could not trace. A diagram with no data table is
    unchecked, not untrue; a plotted number the facts do not hold is refused."""
    fc = art.figure_check or {}
    return art.status == "produced" and not fc.get("unverified") and (fc.get("verified") or not fc.get("checked"))


def reuse_prior(sections: list[dict], prior: dict | None) -> int:
    """Carry an earlier run's visuals for the same day onto matching sections (paid, drawn work is not redone)."""
    old = {s.get("theater_id"): s["visuals"] for s in (prior or {}).get("theaters") or [] if s.get("visuals")}
    n = 0
    for s in sections:
        if s.get("theater_id") in old:
            s["visuals"] = old[s["theater_id"]]
            n += len(s["visuals"])
    return n


def attach(sections: list[dict], *, ctx: Any, domain: str, as_of: str, ask: Callable[[Any, str, str], Any],
           prior: dict | None = None, ready: Callable[[], tuple[bool, str]] | None = None, runner: Any = None,
           uploader: Callable[[dict[str, bytes]], dict] | None = None) -> dict | None:
    """Plan, draw, upload and attach the day's visuals to ``sections`` in place. Returns a small report for the
    record (``None`` when switched off or when there was nothing to do). Never raises."""
    if not flags.visuals_enabled() or flags.visuals_max() < 1 or not sections:
        return None
    try:
        if prior is not None and (n := reuse_prior(sections, prior)):
            return {"reused": n}
        facts = vf.collect(sections)
        if len(facts) < MIN_FACTS or sum(f.has_number for f in facts) < 2:
            return None
        cap = flags.visuals_max()
        uploader = visuals_store.local_first(uploader) if uploader else _upload     # every producer below publishes through this, never around it
        plan = ask(VisualPlan, PLAN_ROLE, _message(facts, sections, cap))
        kept, dropped = validate(plan, facts, {s.get("theater_id") for s in sections}, cap)
        report: dict[str, Any] = {"planned": len(getattr(plan, "visuals", []) or []), "produced": 0, "skipped": dropped,
                                  "none_because": getattr(plan, "none_because", "") or ""}
        if not kept:
            return report
        specs = [k for k in kept if k[0].form == "scene3d" or k[0].form in _NATIVE]
        kept = [k for k in kept if k not in specs]           # what remains goes to the coding harness: static charts only
        if specs:
            _spec_forms(specs, sections, ask=ask, domain=domain, as_of=as_of, uploader=uploader, report=report,
                        first=len(kept) + 1)
        if not kept:
            return report
        ok, note = (ready or _ready)()
        if not ok:
            report["skipped"].append(f"harness not ready: {note[:160]}")
            return report
        profile = vf.profile_of(facts, domain=domain, as_of=as_of)
        _draw_all(kept, profile, sections, ctx=ctx, domain=domain, as_of=as_of, runner=runner,
                  uploader=uploader, report=report)
        return report
    except Exception as exc:  # noqa: BLE001 - a visual is an addition to the day, never its gate
        return {"produced": 0, "skipped": [f"visuals failed: {type(exc).__name__}: {str(exc)[:160]}"]}


def _spec_forms(specs: list[tuple[VisualAsk, list[vf.Fact]]], sections: list[dict], *, ask: Callable[[Any, str, str], Any],
                domain: str, as_of: str, uploader: Callable[[dict[str, bytes]], dict], report: dict, first: int) -> None:
    """Interactive forms the site renders from a data spec: a structured model call + mechanical validation, no
    coding harness (``scene3d`` for 3D scenes, ``native_forms`` for timelines, map stories, networks, flows and tracker comparisons)."""
    from . import native_forms, scene3d

    for n, (brief, cited) in enumerate(specs, first):
        if brief.form == "scene3d":
            rec = scene3d.produce(brief, cited, n, domain=domain, as_of=as_of, site_dir=SITE_DIR, ask=ask,
                                  uploader=uploader, report=report)
        else:
            rec = native_forms.produce(brief.form, brief, cited, n, domain=domain, as_of=as_of, site_dir=SITE_DIR,
                                       ask=ask, uploader=uploader, report=report)
        if rec is None:
            continue
        for s in sections:
            if s.get("theater_id") == brief.theater_id:
                s.setdefault("visuals", []).append(rec)
                report["produced"] += 1


def _draw_all(kept: list[tuple[VisualAsk, list[vf.Fact]]], profile: Any, sections: list[dict], *, ctx: Any, domain: str,
              as_of: str, runner: Any, uploader: Callable[[dict[str, bytes]], dict], report: dict) -> None:
    from algent_backend.agent_system.agents.editorial.analytics_worker import fulfill_request

    emit = getattr(ctx, "emit", None)

    def one(item: tuple[int, tuple[VisualAsk, list[vf.Fact]]]) -> tuple[VisualAsk, list[vf.Fact], Any, _Capture | None]:
        n, (ask, cited) = item
        cap = _Capture(emit)
        try:
            art = fulfill_request(_request(ask, cited, n, as_of), profile, context=cap, runner=runner)   # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001 - one figure's failure is that figure's
            report["skipped"].append(f"{ask.theater_id}/{ask.form}: draw failed: {type(exc).__name__}: {str(exc)[:120]}")
            return ask, cited, None, None
        return ask, cited, art, cap

    with _harness_env(flags.visuals_harness()), ThreadPoolExecutor(max_workers=max(1, len(kept))) as pool:
        results = list(pool.map(one, enumerate(kept, 1)))
    for ask, cited, art, cap in results:
        if art is None or cap is None:
            continue
        if not _trustworthy(art):
            report["skipped"].append(f"{ask.theater_id}/{ask.form}: {art.status}: {(art.note or 'no note')[:140]}")
            continue
        names = [n for n in (art.artifact_name, art.raster_name) if n and n in cap.files]
        if not names:
            report["skipped"].append(f"{ask.theater_id}/{ask.form}: no figure file captured")
            continue
        base = f"{SITE_DIR}/{domain}/{as_of}"
        sent = uploader({f"{base}/{n}": cap.files[n] for n in dict.fromkeys(names)})
        if not sent.get("ok", True) or sent.get("note") or sent.get("failed"):
            report["skipped"].append(f"{ask.theater_id}/{ask.form}: not hosted ({sent.get('note') or sent.get('failed')})")
            continue
        raster = f"{base}/{art.raster_name}" if art.raster_name in cap.files else ""
        rec = _record(art, ask, cited, f"{base}/{art.artifact_name}", raster)
        for s in sections:
            if s.get("theater_id") == ask.theater_id:
                s.setdefault("visuals", []).append(rec)
                report["produced"] += 1
