"""
The desk's production line — one theater in, one durable brief out.

The CLI (``newsroom intel brief``) and the unattended cycle (``newsroom intel cycle``) both call
``produce``: optionally commission research, write the brief, drop the HTML/JSON scratch copy under
``runs_data`` and — the part that matters — persist the brief to ``intel_store/briefs/<slug>.json``.
``runs_data`` is rolling-retention scratch; the intel store is backed up and is what the site
snapshot reads, so a brief only really exists once it is there.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import brief as br
from . import forecasts, render
from .contracts import Brief, Theater
from .heat import store_dir

SCHEMA = "ohmega.brief/1"
BRIEF_WINDOW_DAYS = 30          # a brief's research covers the last 30 days; earlier corpus claims are the background


def briefs_dir() -> Path:
    return store_dir() / "briefs"


def brief_slug(as_of: str, theater_name: str, focus: str = "") -> str:
    return f"{as_of}-{br.safe_name(theater_name)}" + (f"-{br.focus_tag(focus)}" if focus.strip() else "")


def persist_brief(brief: Brief, *, as_of: str, theater: Theater, heat: dict, researched: bool,
                  focus: str = "", built_at: str = "") -> dict:
    """Write the durable brief record (see module docstring) and return it."""
    slug = brief_slug(as_of, theater.name, focus)
    record = {"schema": SCHEMA, "slug": slug, "as_of": as_of,
              "built_at": built_at or datetime.now(UTC).isoformat(),
              "theater_id": theater.id, "theater_name": theater.name, "heat": heat,
              "researched": researched, "focus": focus.strip(), **brief.model_dump()}
    _write(briefs_dir() / f"{slug}.json", record)
    return record


def previous_brief(theater_id: str, *, before_slug: str = "") -> dict | None:
    """The newest persisted brief on this theater (other than ``before_slug``, which is about to be
    rewritten), so the next one can say what changed. None for a theater we have not briefed."""
    found = []
    for path in sorted(briefs_dir().glob("*.json")) if theater_id and briefs_dir().is_dir() else []:
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if rec.get("theater_id") == theater_id and rec.get("slug") != before_slug:
            found.append(rec)
    return max(found, key=lambda r: (r.get("as_of", ""), r.get("built_at", "")), default=None)


def board_headlines(board: dict) -> str:
    """Every headline on the board, as evidence for settling forecasts that are past their horizon."""
    return "\n".join(f"[{t.get('name', '')}] {br.reported(Theater.model_validate(t))}" for t in board.get("theaters", []))


def settle_overdue(ctx: Any, board: dict, *, as_of: str, model_spec: Any) -> list[dict]:
    """The cycle's once-a-run pass: forecasts past their horizon, judged against everything on the board."""
    return forecasts.resolve_due(ctx, None, model_spec, board_headlines(board), as_of=as_of)


def produce(ctx: Any, theater: Theater, heat: dict, *, as_of: str, out: Path | None = None,
            research: bool = False, focus: str = "", model_spec: Any = None, fresh_research: bool = False) -> dict:
    """Research (optional) → brief → persist. Returns a report row; ``error`` set when no brief came.

    Research already done for this theater today is reused (``research_reused``), not repeated, unless
    ``fresh_research``. A brief with no bottom line is not a brief: it is reported as an error, never persisted."""
    from algent_backend.agent_system.agents.pulse.update import update_quietly
    from algent_backend.agent_system.agents.pulse.repository import pulse_store
    from algent_backend.agent_system.foundation import cost

    from ..pulse.seed import evidence_block

    profiles, spent, research_error, reused = [], 0.0, "", False
    if research:
        # The research agent caps itself at $1; this scope makes the spend visible per theater.
        prof = None
        try:
            with cost.article_scoped(1.0):
                try:
                    prof, reused = br.obtain_research(ctx, None, theater, fresh=fresh_research, focus=focus,
                                                      on_date=as_of)
                finally:
                    spent = cost.article_spent_usd()
        except Exception as exc:  # noqa: BLE001 - fall back to a headlines-only brief rather than lose the theater
            research_error = br.describe_failure(exc)
            print(f"[brief] research failed for {theater.id}; continuing headlines-only: {research_error}",
                  flush=True)
        if prof:
            profiles.append(prof)
            update_quietly(prof, run_id=prof["id"], once=True)   # moves the Pulses once per research version
    # What we said last time, and how the desk's calls on this theater came out, go to the analyst;
    # forecasts this evidence settles are resolved first so the analyst sees the outcomes.
    try:
        settled = forecasts.resolve_due(
            ctx, None, model_spec, f"{evidence_block(profiles)[0]}\n\nREPORTED HEADLINES:\n{br.reported(theater)}",
            as_of=as_of, theater_id=theater.id)
    except Exception:  # noqa: BLE001 - settling is a side duty; it must not cost the brief
        settled = []
    earlier = br.recall(theater, as_of=as_of, window_days=BRIEF_WINDOW_DAYS, exclude_ids=[p["id"] for p in profiles])
    brief = br.write_brief(ctx, None, theater, heat, profiles=profiles, pulse_table=br.pulse_catalog(pulse_store()),
                           model_spec=model_spec, focus=focus, corpus_ctx=earlier,
                           previous=previous_brief(theater.id, before_slug=brief_slug(as_of, theater.name, focus)),
                           track_record=forecasts.track_record(theater.id))
    if brief is None:
        return {"theater": theater.id, "error": "analyst returned nothing"}
    if not brief.bottom_line.strip():
        return {"theater": theater.id, "error": "analyst returned an empty brief; not persisted"}
    record = persist_brief(brief, as_of=as_of, theater=theater, heat=heat, researched=bool(profiles),
                           focus=focus)
    forecasts.record(record["slug"], theater.id, brief.judgments, made_at=record["built_at"])
    row = {"theater": theater.id, "slug": record["slug"], "researched": bool(profiles),
           "research_usd": round(spent, 4), "research_reused": reused, "forecasts_made": len(brief.judgments),
           "forecasts_settled": len(settled)}
    if research_error:
        row["research_error"] = research_error
    if out is not None:
        name = br.safe_name(theater.name) + (f"_{br.focus_tag(focus)}" if focus.strip() else "")
        (out / f"brief_{name}.json").write_text(brief.model_dump_json(indent=2), encoding="utf-8")
        (out / f"brief_{name}.html").write_text(
            render.render_brief(brief, theater_name=theater.name, heat=heat, as_of=as_of), encoding="utf-8")
        row["brief"] = str(out / f"brief_{name}.html")
    return row


def latest_board() -> dict | None:
    boards = sorted((store_dir() / "boards").glob("*.json"))
    return json.loads(boards[-1].read_text(encoding="utf-8")) if boards else None


def pick_theaters(board: dict, top: int, domains: list[str] | None = None) -> list[str]:
    """The ``top`` hottest theaters; on equal heat, ones heating or new come first. ``domains``
    (case-insensitive, from ``board.theaters[].domain``) restricts which theaters are eligible; the board
    itself is untouched. Empty/None means every domain."""
    rank = {"heating": 0, "new": 0, "steady": 1, "cooling": 2}
    wanted = {d.strip().lower() for d in domains or [] if d.strip()}
    domain_of = {t["id"]: (t.get("domain") or "").lower() for t in board.get("theaters", [])}
    rows = [h for h in board.get("heat", []) if not wanted or domain_of.get(h["theater_id"]) in wanted]
    heat = sorted(rows, key=lambda h: (-h.get("heat", 0), rank.get(h.get("trend"), 1)))
    return [h["theater_id"] for h in heat[:max(top, 0)]]


def import_briefs(runs_intel: Path) -> dict:
    """One-off: copy ``runs_data/intel/<as_of>/brief_*.json`` into the durable store. Idempotent —
    an existing record is never overwritten. Theater identity comes from that day's board when the
    file's name matches a theater by ``safe_name``; otherwise the name is the file's brief title."""
    imported, skipped = [], []
    for path in sorted(runs_intel.glob("*/brief_*.json")):
        as_of = path.parent.name
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            brief = Brief.model_validate(raw)
        except (OSError, ValueError):
            skipped.append(str(path))
            continue
        stem = path.stem.removeprefix("brief_")
        board_path = store_dir() / "boards" / f"{as_of}.json"
        board = json.loads(board_path.read_text(encoding="utf-8")) if board_path.is_file() else {}
        match = next((t for t in board.get("theaters", [])
                      if stem == br.safe_name(t["name"]) or stem.startswith(br.safe_name(t["name"]) + "_")), None)
        theater = Theater.model_validate(match) if match else Theater(id="", name=brief.title)
        # a "_<tag>" suffix marks a focused brief; its text is unknown, so the tag is kept as the slug tail
        tail = stem[len(br.safe_name(theater.name)) + 1:] if match and stem != br.safe_name(theater.name) else ""
        slug = f"{as_of}-{br.safe_name(theater.name)}" + (f"-{tail}" if tail else "")
        target = briefs_dir() / f"{slug}.json"
        if target.exists():
            skipped.append(slug)
            continue
        heat = next((h for h in board.get("heat", []) if h.get("theater_id") == theater.id), {})
        built = datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()
        record = {"schema": SCHEMA, "slug": slug, "as_of": as_of, "built_at": built,
                  "theater_id": theater.id, "theater_name": theater.name, "heat": heat,
                  "researched": True, "focus": "",
                  **brief.model_dump()}
        _write(target, record)
        imported.append(slug)
    return {"imported": imported, "skipped": skipped}


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
