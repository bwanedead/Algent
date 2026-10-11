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
     "sweep":    {"draft": <SweepDraft dump>, "urls": [...], "covered_urls": [...]} | absent}
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from .brief import safe_name
from .heat import store_dir

SCHEMA = "ohmega.daily.drafts/1"


def path_for(domain: str, date: str) -> Path:
    return store_dir() / "daily_drafts" / safe_name(domain) / f"{date}.json"


def load(domain: str, date: str) -> dict | None:
    """The day's archive, or None when there is none (or it is unreadable)."""
    try:
        data = json.loads(path_for(domain, date).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("theaters"), dict) else None


def save(domain: str, date: str, *, theaters: dict, summary: dict | None = None, sweep: dict | None = None,
         merge: bool = False) -> Path:
    """Write the archive. ``merge`` (a targeted rerun) keeps the other theaters', the summary's and the sweep's
    earlier drafts and replaces only what is given; otherwise the day's archive is replaced whole."""
    prior = (load(domain, date) or {}) if merge else {}
    payload = {"schema": SCHEMA, "domain": domain, "date": date, "saved_at": datetime.now(UTC).isoformat(),
               "theaters": {**(prior.get("theaters") or {}), **theaters}}
    for key, new in (("summary", summary), ("sweep", sweep)):
        if new or prior.get(key):
            payload[key] = new or prior[key]
    path = path_for(domain, date)
    path.parent.mkdir(parents=True, exist_ok=True)
    # default=str: instrument readings may carry dates; the archive is for replay, not for exact types
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8", newline="\n")
    return path
