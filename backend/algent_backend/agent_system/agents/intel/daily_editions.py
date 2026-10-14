"""
The daily's LATER PARTS of the day — an APPEND to one report, never a second report.

The day's record (``daily/<domain>/<date>.json``) is built in editions (``flags.EDITIONS``): edition 1 is the normal
run (``daily.produce_daily``); edition 2 (this module) re-reads what is new since edition 1 and ADDS to the same
record. It never rewrites edition 1's sections and never buys their research again.

* NOVELTY SINCE THE EARLIER PART. The board's novelty is day-granular ("since the last dated section"), which cannot
  say "since the morning". For a theater an earlier part covered, newness is membership (``novelty.measure_since_seen``):
  a headline source, a statement transcript or a flagged series that part's writer was not shown (its draft archive
  keeps exactly what it was shown). A theater no earlier part covered keeps the board's date-based novelty. The
  existing focus plan then decides, unchanged: ``top`` is a ceiling, a theater with nothing new is not written.
* TWO KINDS OF ADDITION. A theater NOT in the record gets a new section (``edition`` n), research and all. A theater
  the record already covers gets an UPDATE: a section written against the morning's one (``kind: "update"``), stored
  nested as ``updates`` on that section so the report reads as one piece, and dropped if the writer found nothing
  that actually moved. An update reuses the morning's saved research (same profile id, inside the research window):
  new material arrives as headlines/statements/readings, never as a second research bill.
* ONE REPORT. The summary ("the day so far"), cross-theater links and the sweep are recomputed over everything;
  ``editions`` records who added what and when (provenance, and what ``--rerender`` replays per part). The sweep
  excludes what earlier parts covered and never nominates a second Spotlight.

Nothing here is persisted unless at least one section was attempted and one written, or nothing qualified (a quiet
second half is a recorded fact, not a failure).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from algent_backend.geoledger import ask as geo_ask
from algent_backend.geoledger import ingest as geo_ingest

from . import brief as br
from . import daily, daily_drafts, desk, flags, focus, novelty, render
from . import sensing as sensing_mod
from . import visuals as visuals_mod
from .contracts import Theater


def load_record(domain: str, as_of: str) -> dict | None:
    import json

    try:
        rec = json.loads((daily.daily_dir(domain) / f"{as_of}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return rec if isinstance(rec, dict) else None


def editions_of(record: dict | None) -> list[dict]:
    """The record's ``editions``; a record from before editions is one part (edition 1)."""
    if not record:
        return []
    return list(record.get("editions") or [daily.edition_entry(
        1, record.get("built_at", ""), record.get("theaters") or [], record.get("summary") or {})])


def next_edition(domain: str, as_of: str, now: datetime | None = None) -> int:
    """The edition a bare ``--edition auto`` means: the next part when its start time has passed, else 1."""
    now = now or datetime.now(UTC)
    have = [e["n"] for e in editions_of(load_record(domain, as_of))]
    nxt = max(have, default=0) + 1
    due = next((e for e in flags.EDITIONS if e.n == nxt), None)
    return nxt if have and due is not None and now.strftime("%H:%M") >= due.utc else 1


# ── what the earlier parts were shown ─────────────────────────────────────────────────────────
def seen_by_earlier(domain: str, as_of: str, upto: int) -> dict[str, dict[str, set[str]]]:
    """theater id -> the source URLs, statement transcripts and series ids the writers of editions < ``upto``
    were shown, from their draft archives. A theater with no archived draft is absent (nothing to compare with)."""
    seen: dict[str, dict[str, set[str]]] = {}
    for n in range(1, upto):
        for tid, saved in ((daily_drafts.load(domain, as_of, n) or {}).get("theaters") or {}).items():
            inp = saved.get("inputs") or {}
            row = seen.setdefault(tid, {"urls": set(), "statements": set(), "series": set()})
            row["urls"] |= {u.strip().rstrip("/") for u in inp.get("reported_urls") or []}
            row["statements"] |= set(inp.get("statement_urls") or [])
            row["series"] |= {r.get("series_id") for r in inp.get("instrument_rows") or [] if r.get("series_id")}
    return seen


def _hhmm(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).astimezone(UTC).strftime("%H:%M")
    except ValueError:
        return "?"


def part_heats(board: dict, theaters: dict[str, Theater], record: dict, seen: dict, *, as_of: str,
               since_label: str) -> list[dict]:
    """The board's heat rows with ``novelty`` re-measured since the earlier part for theaters it covered."""
    sections = {s.get("theater_id"): s for s in record.get("theaters") or []}
    day = date.fromisoformat(as_of)
    rows = []
    for h in board.get("heat", []):
        tid, t = h["theater_id"], theaters.get(h["theater_id"])
        if t is None or tid not in sections:
            rows.append(h)
            continue
        mine = seen.get(tid)
        if mine is None:        # covered, but no archived draft to compare with: never spend on a guess
            nov = {"since": since_label, "headlines": {}, "statements": 0, "instruments": 0, "total": 0, "newest": ""}
        else:
            actors = sensing_mod.prior_actors(desk.previous_brief(tid), sections[tid])
            ev = sensing_mod.for_theater(t, as_of=as_of, actors=actors)
            nov = novelty.measure_since_seen(t, since=since_label, as_of=day, ev=ev, seen_urls=mine["urls"],
                                             seen_statements=mine["statements"], seen_series=mine["series"])
        rows.append({**h, "novelty": nov})
    return rows


# ── the notes the writers are given ───────────────────────────────────────────────────────────
def _update_note(edition: int, morning: dict, built_at: str) -> str:
    info = flags.edition_info(edition)
    return (f"THIS IS AN UPDATE (part {edition} of today's report, the {info.label} cycle). This theater already has "
            f"a section earlier today (built {_hhmm(built_at)} UTC), shown below as the PREVIOUS DAILY SECTION. The "
            f"reader has read it. Write ONLY what moved since: lead with the change, do not restate the morning. "
            f"`since_yesterday` here means since that earlier section. If nothing material moved, leave "
            f"`developments` empty and say so in `bottom_line`. Leave `saga` empty: the morning section carries it.")


def _new_note(edition: int) -> str:
    info = flags.edition_info(edition)
    return (f"This section is added in part {edition} of today's report (the {info.label} cycle), for a theater "
            f"the earlier part did not cover. Write it as an ordinary section.")


def _summary_note(edition: int, built_at: str) -> str:
    info = flags.edition_info(edition)
    return (f"THIS IS THE DAY SO FAR: the report was built in parts and part {edition} (the {info.label} cycle, "
            f"{_hhmm(built_at)} UTC) has just added sections and updates. Write ONE summary of the whole day, "
            f"earlier parts included, newest developments weighed as they deserve (the day's biggest story may "
            f"still be the morning's). Do not describe the report as having parts.")


# ── merging ───────────────────────────────────────────────────────────────────────────────────
def merge_regions(old: list[dict], new: list[dict], edition: int) -> list[dict]:
    """``new`` sweep regions appended to ``old``, their items tagged with the part that added them."""
    regions = {r["region"]: {"region": r["region"], "items": list(r["items"])} for r in old}
    for r in new:
        tagged = [{**i, "edition": edition} for i in r["items"]]
        regions.setdefault(r["region"], {"region": r["region"], "items": []})["items"] += tagged
    return list(regions.values())


def _attach(record: dict, sections: list[dict]) -> None:
    """Updates nest under their morning section; anything else is appended."""
    for sec in sections:
        parent = next((s for s in record["theaters"] if s.get("theater_id") == sec["theater_id"]), None) \
            if sec.get("kind") == "update" else None
        if parent is not None:
            parent.setdefault("updates", []).append(sec)
        else:
            record["theaters"].append(sec)


def _skeleton(domain: str, as_of: str) -> dict:
    return {"schema": daily.SCHEMA, "domain": domain, "date": as_of, "built_at": "", "researched": False,
            "summary": {"headline": "", "the_day": []}, "theaters": [], "cross_theater": [], "watch": [],
            "quiet": [], "pulse_proposals": [], "editions": []}


# ── the engine ────────────────────────────────────────────────────────────────────────────────
def produce(ctx: Any, *, domain: str = "geopolitics", top: int = 5, research: bool = False, model_spec: Any = None,
            as_of: str, board: dict | None = None, out: Path | None = None, fresh_research: bool = False,
            edition: int = 2) -> dict:
    """Append edition ``edition`` to ``as_of``'s record. Same return shape as ``daily.produce_daily`` (``error``
    set and nothing persisted when theaters were attempted and none was written, or when the part exists)."""
    board = board if board is not None else (desk.latest_board() or {"theaters": [], "heat": []})
    existing = load_record(domain, as_of)
    record = existing or _skeleton(domain, as_of)
    parts = editions_of(existing)
    if any(e["n"] == edition for e in parts):
        return {"report": None, "theaters": [], "research_usd": 0.0,
                "error": f"edition {edition} of {as_of} already exists; it is never rebuilt (that would buy it twice). "
                         f"Use --rerender, or --theater to redo one section"}
    if parts and not existing.get("editions"):
        record["editions"] = parts                       # a record from before editions becomes part 1
    theaters = {t["id"]: Theater.model_validate(t) for t in board.get("theaters", [])}
    since_label = (f"the {flags.edition_info(parts[-1]['n']).label} part ({_hhmm(parts[-1]['built_at'])} UTC)"
                   if parts else "")
    seen = seen_by_earlier(domain, as_of, edition)
    rows_heat = part_heats(board, theaters, record, seen, as_of=as_of, since_label=since_label) if parts else board.get("heat", [])
    heats = {h["theater_id"]: h for h in rows_heat}
    covered_ids = {s.get("theater_id") for s in record["theaters"]}
    plan = focus.plan({**board, "heat": rows_heat}, top, [domain])
    todo = [tid for tid in plan.focus if tid in theaters
            and (tid not in covered_ids or (heats.get(tid, {}).get("novelty") or {}).get("total", 0) > 0)]
    run = daily.make_run(ctx, domain=domain, as_of=as_of, research=research, model_spec=model_spec,
                         fresh_research=fresh_research, edition=edition)
    morning = {s["theater_id"]: s for s in record["theaters"]}
    built_prev = parts[-1]["built_at"] if parts else ""
    added, rows = [], []
    for tid in todo:
        is_update = tid in morning
        prev = {**morning[tid], "_date": f"{as_of}, earlier part"} if is_update else None
        section, row = daily._cover(run, theaters[tid], heats.get(tid, {}), previous=prev,
                                    edition_note=_update_note(edition, morning[tid], built_prev) if is_update
                                    else _new_note(edition))
        rows.append(row)
        if section is None:
            continue
        if is_update:
            if not section["developments"]:              # the writer found nothing that moved: no clutter
                row["dropped"] = "update with no development that moved"
                continue
            section["kind"] = "update"
            section["update_of"] = tid
        added.append(section)
    if rows and not added and all(r.get("error") for r in rows):
        errors = "; ".join(f"{r['theater']}: {r.get('error', 'no section')}" for r in rows)
        print(f"[daily] edition {edition}: no section was written; nothing persisted: {errors}", flush=True)
        return {"report": None, "theaters": rows, "research_usd": round(sum(r["research_usd"] for r in rows), 4),
                "error": f"no section was written for edition {edition} ({len(rows)} attempted); not persisted: {errors}"}
    swept = daily._sweep_and_spotlight(run, board, added, rows, [*plan.focus, *covered_ids], heats,
                                       earlier=record if parts else None)
    visual_run = visuals_mod.attach(
        added, ctx=ctx, domain=domain, as_of=as_of, prior=None,
        ask=lambda schema, role, task: daily._ask(ctx, None, model_spec, schema, role, task))
    geo_run = geo_ingest.attach(added, as_of=as_of,
                                ask=lambda schema, role, task: daily._ask(ctx, None, geo_ask.extraction_spec(), schema, role, task))
    built_at = datetime.now(UTC).isoformat()
    _attach(record, added)
    summary, summary_error = None, ""
    if added:
        try:
            summary = daily.write_summary(ctx, None, record["theaters"], as_of=as_of, domain=domain,
                                          model_spec=model_spec, sensing=sensing_mod.across_theaters(as_of=as_of),
                                          archive=run.summary_archive, edition_note=_summary_note(edition, built_at))
        except Exception as exc:  # noqa: BLE001 - the additions stand; the earlier top is kept
            summary_error = br.describe_failure(exc)
            print(f"[daily] summary writer failed; keeping the earlier top: {summary_error}", flush=True)
    if summary:
        record["summary"] = {"headline": summary.headline, "the_day": summary.the_day}
        record["cross_theater"] = [c.model_dump() for c in summary.cross_theater]
    elif not record["summary"].get("headline"):
        record["summary"] = {"headline": "Nothing new in the theaters we are watching.", "the_day": []}
    record["built_at"] = built_at
    record["researched"] = bool(record.get("researched")) or any(r.get("researched") for r in rows)
    record["watch"] = [w for w in plan.watch if w["theater_id"] not in covered_ids | {s["theater_id"] for s in added}]
    record["quiet"] = plan.quiet
    record["pulse_proposals"] = [*record.get("pulse_proposals", []), *(p for r in rows for p in r.get("proposals", []))]
    if swept is not None and (swept.regions or swept.spotlight):
        old = record.get("sweep") or {"window_days": swept.record()["window_days"], "regions": [], "spotlight": None}
        record["sweep"] = {**old, "regions": merge_regions(old.get("regions") or [], swept.regions, edition),
                           "spotlight": old.get("spotlight") or swept.spotlight}
    entry = daily.edition_entry(edition, built_at, added, dict(record["summary"]))
    if visual_run:
        entry["visuals_run"] = visual_run
    if geo_run:
        entry["geoledger_run"] = geo_run
    record["editions"].append(entry)
    path = daily.daily_dir(domain) / f"{as_of}.json"
    desk._write(path, record)
    result: dict[str, Any] = {"report": record, "path": str(path), "theaters": rows, "edition": edition,
                              "research_usd": round(sum(r["research_usd"] for r in rows), 4)}
    daily._archive(run, result, merge=False)
    if summary_error:
        result["summary_error"] = summary_error
    if swept is not None and swept.error:
        result["sweep_error"] = swept.error
    if out is not None:
        html = out / f"daily_{br.safe_name(domain)}.html"
        html.write_text(render.render_daily(record), encoding="utf-8")
        result["html"] = str(html)
    return result
