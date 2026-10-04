"""
Consumption side of the ledger: evidence blocks for writers.

``recall`` answers "what has been said on this subject lately" with a block the daily and the briefs
can drop in beside their other evidence. ``speaker_history`` answers "what has this person said
before" so an analyst can judge whether today's words are a shift against their own record. Both
return text with links — never the transcripts themselves.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from . import store
from .contracts import Statement

DEFAULT_LIMIT = 12


def _line(s: Statement) -> str:
    who = f"{s.speaker}" + (f", {s.role}" if s.role else "") + (f" ({s.affiliation})" if s.affiliation else "")
    said = f'"{s.quote}"' if s.quote else s.paraphrase
    gist = f" — {s.paraphrase}" if s.quote and s.paraphrase else ""
    about = f" about {', '.join(s.about)}" if s.about else ""
    note = f"\n  why it matters: {s.significance}" if s.significance else ""
    return (f"- {s.date} · {who}{about} [{s.signal}, stance {s.stance:+d}]: {said}{gist}{note}\n  {s.source_url}")


def recall(terms: list[str], *, days: int = 14, limit: int = DEFAULT_LIMIT, today: date | None = None,
           root: Path | None = None) -> str:
    """STATEMENTS ON RECORD matching any of ``terms`` in the last ``days`` days, newest first.
    Empty string when nothing matches, so callers can omit the block."""
    rows = store.query(terms=terms, days=days, today=today, limit=limit, root=root)
    if not rows:
        return ""
    return (f"STATEMENTS ON RECORD (last {days} days, newest first; official sources, wording as stated):\n"
            + "\n".join(_line(s) for s in rows))


def speaker_history(speaker: str, days: int = 90, *, limit: int = 20, today: date | None = None,
                    root: Path | None = None) -> str:
    """One speaker's earlier statements, oldest first, so tone can be read as a trajectory."""
    rows = store.query(speaker=speaker, days=days, today=today, root=root)[:limit]
    if not rows:
        return ""
    return (f"STATEMENT HISTORY: {speaker} (last {days} days, oldest first):\n"
            + "\n".join(_line(s) for s in reversed(rows)))
