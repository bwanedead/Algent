"""
The statements store — append-only, on disk, the single home of persistence for this desk.

    statements_store/
      transcripts/<id>.json   raw collected texts (internal; never republished)
      statements.jsonl        one extracted statement per line, append-only; ids dedupe
      seen.json               collection state: urls collected, failed attempts, titles (cross-feed dedupe),
                              transcripts extracted, reported-lane search times per target

Root: env ``ALGENT_STATEMENTS_STORE`` or ``statements_store`` (relative to the working directory,
like ``intel_store``). Every function takes an optional ``root`` so tests and callers can pin it.
"""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from . import dedupe
from .contracts import Statement, Transcript

_STORE_ENV = "ALGENT_STATEMENTS_STORE"
_DEFAULT_DIR = "statements_store"


def store_dir(root: Path | None = None) -> Path:
    return root or Path(os.environ.get(_STORE_ENV) or _DEFAULT_DIR)


# ── seen / state ──────────────────────────────────────────────────────────────────────────────
def load_seen(root: Path | None = None) -> dict:
    path = store_dir(root) / "seen.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    return {"collected": raw.get("collected", {}), "failed": raw.get("failed", {}),
            "extracted": raw.get("extracted", {}), "titles": raw.get("titles", {}),
            "reported": raw.get("reported", {})}


def save_seen(seen: dict, root: Path | None = None) -> None:
    path = store_dir(root) / "seen.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(seen, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    tmp.replace(path)                                  # a crash mid-write must not corrupt the seen-set


# ── transcripts ───────────────────────────────────────────────────────────────────────────────
def save_transcript(t: Transcript, root: Path | None = None) -> None:
    path = store_dir(root) / "transcripts" / f"{t.id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(t.model_dump_json(indent=1) + "\n", encoding="utf-8", newline="\n")


def load_transcript(transcript_id: str, root: Path | None = None) -> Transcript | None:
    path = store_dir(root) / "transcripts" / f"{transcript_id}.json"
    try:
        return Transcript.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def transcript_ids(root: Path | None = None) -> list[str]:
    folder = store_dir(root) / "transcripts"
    return sorted(p.stem for p in folder.glob("*.json")) if folder.is_dir() else []


# ── statements ────────────────────────────────────────────────────────────────────────────────
def _ledger(root: Path | None) -> Path:
    return store_dir(root) / "statements.jsonl"


def load_statements(root: Path | None = None) -> list[Statement]:
    path = _ledger(root)
    out: list[Statement] = []
    for raw in path.read_text(encoding="utf-8").splitlines() if path.is_file() else []:
        try:
            out.append(Statement.model_validate_json(raw))
        except ValueError:
            continue                                   # a torn line must not hide the rest of the ledger
    return out


def append_statements(statements: list[Statement], root: Path | None = None) -> int:
    """Append statements whose id is not already in the ledger, and that no statement already on file covers
    (``dedupe``: the same speaker's near-identical words within a day — a report of what a primary already
    says, or a second outlet's report of the same remark). Returns how many were written."""
    on_file = load_statements(root)
    fresh = []
    for s in statements:
        if dedupe.covered_by(s, on_file) is None:
            on_file.append(s)
            fresh.append(s)
    if fresh:
        path = _ledger(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as fh:
            for s in fresh:
                fh.write(s.model_dump_json() + "\n")
    return len(fresh)


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.casefold()))


def names_match(a: str, b: str) -> bool:
    """Word-level match, either direction: 'Putin' matches 'Vladimir Putin'; 'US' never matches 'Russia'."""
    ta, tb = _tokens(a), _tokens(b)
    return bool(ta and tb and (ta <= tb or tb <= ta))


def _mentions(term: str, text: str) -> bool:
    """Every word of ``term`` appears in ``text`` (any order)."""
    tt = _tokens(term)
    return bool(tt and tt <= _tokens(text))


def _haystack(s: Statement) -> str:
    return " | ".join([s.speaker, s.role, s.affiliation, *s.about, *s.topics, s.paraphrase, s.quote])


def query(*, terms: list[str] | None = None, about: str = "", speaker: str = "", affiliation: str = "",
          topic: str = "", days: int | None = None, today: date | None = None, limit: int | None = None,
          root: Path | None = None) -> list[Statement]:
    """Statements newest first. ``terms`` match ANY of them anywhere in the statement (the recall
    path); ``about``/``speaker``/``affiliation``/``topic`` are specific filters that must all hold.
    ``days`` bounds the statement date to the window ending ``today``."""
    floor = ((today or datetime.now(UTC).date()) - timedelta(days=days)).isoformat() if days is not None else ""
    wanted = [t for t in (terms or []) if t.strip()]
    rows = []
    for s in dedupe.visible(load_statements(root)):
        if floor and s.date < floor:
            continue
        if speaker and not names_match(speaker, s.speaker):
            continue
        if affiliation and not names_match(affiliation, s.affiliation):
            continue
        if about and not any(names_match(about, a) for a in s.about):
            continue
        if topic and not any(_mentions(topic, t) for t in [*s.topics, s.paraphrase]):
            continue
        if wanted and not any(_mentions(w, _haystack(s)) for w in wanted):
            continue
        rows.append(s)
    rows.sort(key=lambda s: s.date, reverse=True)      # stable: ties keep ledger order
    return rows[:limit] if limit else rows
