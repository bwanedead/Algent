"""
The visible record — what leaders said, shown as what they said.

The statements ledger holds who said what; ``sensing`` selects the ones that bear on a theater. This
module makes that selection VISIBLE, deterministically, instead of leaving it to a writer's choice:

* ``build`` turns the statements a writer was shown into ``on_record`` rows (persisted on every daily
  section and brief, in the order sensing chose). Nothing is paraphrased or re-judged here: the quote was
  validated against the transcript at extraction, the affiliation is the extractor's semantic judgment,
  and the flag is only the ISO renderer spelling that country name.
* ``merge`` unions rows across reports (the theater dossier), deduped by statement id, newest first.
* ``export`` is the bounded public ledger (``/intel/record``): the last ``WINDOW_DAYS`` days of
  statements plus per-dyad tone series. The bound is the window and ``MAX_STATEMENTS``; older rows stay in
  the ledger but are not published.

A statement proves it was SAID, not that it is true; the site says so once.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import date
from typing import Any

from ..statements import store
from ..statements.contracts import Statement

EXPORT_SCHEMA = "ohmega.record/1"
WINDOW_DAYS = 60            # the public ledger covers the last 60 days
MAX_STATEMENTS = 1500       # hard ceiling on the export, newest first (the file the site loads at build)
MIN_TONE_STATEMENTS = 4     # a dyad needs this many statements ...
MIN_TONE_DAYS = 2           # ... on at least this many days before a "series" means anything
MAX_TONE_DYADS = 12


def _iso2(name: str) -> str:
    from algent_backend.publishing.tagging import iso2_for_name   # the renderer lives in publishing; lazy, like dossier

    return iso2_for_name(name)


def entry(s: Statement) -> dict[str, Any]:
    """One statement as a published row. ``iso2``/``about_iso2`` are "" / omitted where the name is not a country."""
    about_iso = list(dict.fromkeys(i for i in (_iso2(a) for a in s.about) if i))
    return {"id": s.id, "speaker": s.speaker, "role": s.role, "affiliation": s.affiliation,
            "iso2": _iso2(s.affiliation), "date": s.date, "venue": s.venue_kind, "quote": s.quote,
            "paraphrase": s.paraphrase, "about": list(s.about), "about_iso2": about_iso, "signal": s.signal,
            "stance": s.stance, "significance": s.significance, "url": s.source_url}


def build(shown: Iterable[Statement]) -> list[dict[str, Any]]:
    """``on_record`` for one section or brief: the statements the writer was shown, in the order sensing
    chose, each once."""
    seen: set[str] = set()
    out = []
    for s in shown:
        if s.id not in seen:
            seen.add(s.id)
            out.append(entry(s))
    return out


def lead_with(rows: list[dict[str, Any]], tags: Iterable[str]) -> list[dict[str, Any]]:
    """``rows`` (in the order the writer saw them as [S1], [S2]…) with the writer's ``key_statements`` first, in
    its order; unknown or repeated tags are ignored, and every row is kept. Which statements matter most is a
    judgment, so the model makes it; this only applies it."""
    picked: list[int] = []
    for t in tags or []:
        digits = "".join(c for c in str(t) if c.isdigit())
        i = int(digits) - 1 if digits else -1
        if 0 <= i < len(rows) and i not in picked:
            picked.append(i)
    return [rows[i] for i in picked] + [r for i, r in enumerate(rows) if i not in picked]


def merge(lists: Iterable[Iterable[dict[str, Any]]], *, limit: int = 0) -> list[dict[str, Any]]:
    """Union of ``on_record`` lists (records without one contribute nothing), deduped by statement id,
    newest first (ties keep first-seen order). ``limit`` 0 means all."""
    rows: dict[str, dict[str, Any]] = {}
    for rows_in in lists:
        for r in rows_in or []:
            if isinstance(r, dict) and r.get("id") and r["id"] not in rows:
                rows[r["id"]] = r
    out = sorted(rows.values(), key=lambda r: r.get("date", ""), reverse=True)
    return out[:limit] if limit else out


# ── tone ──────────────────────────────────────────────────────────────────────────────────────
def tone_series(rows: list[Statement]) -> list[dict[str, Any]]:
    """Stance over time for (speaker's affiliation -> counterpart in ``about``) dyads with enough
    statements. Stance is the extractor's -2 (hostile) .. +2 (conciliatory) toward the counterpart; a day's
    point is the mean of that day's statements. Strongest dyads (most statements) first."""
    groups: dict[tuple[str, str], list[Statement]] = defaultdict(list)
    for s in rows:
        if not s.affiliation.strip():
            continue
        for target in dict.fromkeys(a.strip() for a in s.about if a.strip()):
            if target.casefold() != s.affiliation.strip().casefold():
                groups[(s.affiliation.strip(), target)].append(s)
    out = []
    for (who, about), sts in groups.items():
        by_day: dict[str, list[int]] = defaultdict(list)
        for s in sts:
            by_day[s.date].append(s.stance)
        if len(sts) < MIN_TONE_STATEMENTS or len(by_day) < MIN_TONE_DAYS:
            continue
        out.append({"affiliation": who, "iso2": _iso2(who), "about": about, "about_iso2": _iso2(about),
                    "n": len(sts), "mean": round(sum(s.stance for s in sts) / len(sts), 2),
                    "points": [{"date": d, "stance": round(sum(v) / len(v), 2), "n": len(v)}
                               for d, v in sorted(by_day.items())]})
    return sorted(out, key=lambda t: (-t["n"], t["affiliation"], t["about"]))[:MAX_TONE_DYADS]


def export(*, today: date | None = None) -> dict[str, Any]:
    """The bounded public ledger (see module docstring). Pure read of the statements store; it carries the
    newest statement's date (``newest``) and the window's ``as_of``; no wall-clock stamp, so a rebuild with no
    new statements on the same day is byte-identical."""
    today = today or date.today()
    rows = store.query(days=WINDOW_DAYS, today=today, limit=MAX_STATEMENTS)     # newest first
    return {"schema": EXPORT_SCHEMA, "window_days": WINDOW_DAYS, "max_statements": MAX_STATEMENTS,
            "as_of": today.isoformat(), "count": len(rows),
            "statements": [entry(s) for s in rows], "tone": tone_series(rows),
            "newest": rows[0].date if rows else ""}
