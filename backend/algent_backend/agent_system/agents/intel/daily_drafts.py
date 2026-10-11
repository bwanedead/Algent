"""
The daily's DRAFT ARCHIVE — what the models returned, kept raw, beside the guards' inputs.

The daily's guards (``daily.finish_section``) are destructive by design: a place off the basemap, a source the
evidence does not hold, a figure that does not trace are dropped from the published section. When the drop was
the ENVIRONMENT's fault (no basemap on the machine, a display feature added later) the model's work was fine
and re-buying it is waste. So every model output the day used is saved here untouched, with the inputs the
guards need to run again (URL sets, on-record rows, readings, the Pulse names): ``daily_rerender`` re-derives
the published record from this with no model call.

Internal. Lives at ``intel_store/daily_drafts/<domain>/<date>.json`` (schema ``ohmega.daily.drafts/1``), NOT
under ``daily/`` — the site mirror and ``previous_section`` read ``daily/*.json`` and must never see it. It
carries no secrets: model output and public-evidence URLs. A day produced before the archive existed has none.

    {"schema", "domain", "date", "saved_at",
     "theaters": {<theater_id>: {"draft": <SectionDraft dump>, "inputs": {...}}},
     "summary":  {"draft": <DaySummary dump>} | absent,
     "sweep":    {"draft": <SweepDraft dump>, "urls": [...], "covered_urls": [...]} | absent,
     "editions": {"2": {"saved_at", "theaters", "summary", "sweep"}, ...} | absent}

Edition 1 is the top level (the shape that existed before editions); later editions (``daily_editions``, an append
to the same day) live under ``editions`` with the same three parts, so ``--rerender`` redoes each part from its
own drafts. ``load``/``save`` take ``edition`` and return/replace only that part.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from .brief import safe_name
from .heat import store_dir

SCHEMA = "ohmega.daily.drafts/1"
_PARTS = ("theaters", "summary", "sweep")


def path_for(domain: str, date: str) -> Path:
    return store_dir() / "daily_drafts" / safe_name(domain) / f"{date}.json"


def _read(domain: str, date: str) -> dict | None:
    try:
        data = json.loads(path_for(domain, date).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _view(raw: dict | None, edition: int) -> dict | None:
    part = raw if edition == 1 else ((raw or {}).get("editions") or {}).get(str(edition))
    return part if isinstance(part, dict) and isinstance(part.get("theaters"), dict) else None


def load(domain: str, date: str, edition: int = 1) -> dict | None:
    """One edition's archive (``theaters``, optional ``summary``/``sweep``), or None when there is none (or it
    is unreadable)."""
    return _view(_read(domain, date), edition)


def editions_present(domain: str, date: str) -> list[int]:
    """The edition numbers this day has drafts for, ascending."""
    raw = _read(domain, date)
    return [n for n in (1, *sorted(int(k) for k in ((raw or {}).get("editions") or {}) if str(k).isdigit()))
            if _view(raw, n) is not None]


def save(domain: str, date: str, *, theaters: dict, summary: dict | None = None, sweep: dict | None = None,
         merge: bool = False, edition: int = 1) -> Path:
    """Write one edition's archive. ``merge`` (a targeted rerun) keeps the other theaters', the summary's and the
    sweep's earlier drafts and replaces only what is given; otherwise that edition's archive is replaced whole.
    Other editions are never touched."""
    raw = _read(domain, date) or {}
    prior = (_view(raw, edition) or {}) if merge else {}
    part = {"saved_at": datetime.now(UTC).isoformat(), "theaters": {**(prior.get("theaters") or {}), **theaters}}
    for key, new in (("summary", summary), ("sweep", sweep)):
        if new or prior.get(key):
            part[key] = new or prior[key]
    if edition == 1:
        payload = {"schema": SCHEMA, "domain": domain, "date": date, **part}
        if raw.get("editions"):
            payload["editions"] = raw["editions"]
    else:
        payload = {**raw, "schema": SCHEMA, "domain": domain, "date": date,
                   "editions": {**(raw.get("editions") or {}), str(edition): part}}
    path = path_for(domain, date)
    path.parent.mkdir(parents=True, exist_ok=True)
    # default=str: instrument readings may carry dates; the archive is for replay, not for exact types
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8", newline="\n")
    return path
