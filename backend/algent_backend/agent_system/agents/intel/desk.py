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
from . import render
from .contracts import Brief, Theater
from .heat import store_dir

SCHEMA = "ohmega.brief/1"


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


def produce(ctx: Any, theater: Theater, heat: dict, *, as_of: str, out: Path | None = None,
            research: bool = False, focus: str = "", model_spec: Any = None) -> dict:
    """Research (optional) → brief → persist. Returns a report row; ``error`` set when no brief came."""
    from algent_backend.agent_system.agents.pulse.update import update_quietly
    from algent_backend.agent_system.foundation import cost

    profiles, spent = [], 0.0
    if research:
        # The research agent caps itself at $1; this scope makes the spend visible per theater.
        with cost.article_scoped(1.0):
            prof = br.commission_research(ctx, None, theater, focus=focus)
            spent = cost.article_spent_usd()
        if prof:
            profiles.append(prof)
            update_quietly(prof, run_id=prof["id"])   # the brief's research moves the Pulses
    brief = br.write_brief(ctx, None, theater, heat, profiles=profiles, pulse_lines=[],
                           model_spec=model_spec, focus=focus)
    if brief is None:
        return {"theater": theater.id, "error": "analyst returned nothing"}
    record = persist_brief(brief, as_of=as_of, theater=theater, heat=heat, researched=bool(profiles),
                           focus=focus)
    row = {"theater": theater.id, "slug": record["slug"], "researched": bool(profiles),
           "research_usd": round(spent, 4)}
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


def pick_theaters(board: dict, top: int) -> list[str]:
    """The ``top`` hottest theaters; on equal heat, ones heating or new come first."""
    rank = {"heating": 0, "new": 0, "steady": 1, "cooling": 2}
    heat = sorted(board.get("heat", []), key=lambda h: (-h.get("heat", 0), rank.get(h.get("trend"), 1)))
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
