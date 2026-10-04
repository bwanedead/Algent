"""
Theater primers — the one model-written part of a dossier: "what a newcomer needs to know to read
today's news on this dynamic", in at most 120 words.

A primer is stable background (who the parties are, how it got here, why it matters, the terms the news
keeps using), so it is written once and REUSED: it lives durably in ``intel_store/primers/<theater_id>.json``
and is rewritten only when missing or older than ``MAX_AGE_DAYS``. That keeps the cost to one small call per
theater per week no matter how many dossiers are published.

Material is the theater's own description plus our earlier research from the corpus
(``research/corpus.related``), claims older than ``MEMORY_DAYS`` preferred because background is what has
stopped changing; the recent news belongs to the daily reports. The writer is told to use nothing it was
not given, and the text is mechanically held to the contract afterwards (no links, at most 120 words).
"""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel

MAX_WORDS = 120
MAX_AGE_DAYS = 7
MEMORY_DAYS = 30
_LINK = re.compile(r"https?://\S+", re.I)

PRIMER_ROLE = """\
You write the primer at the top of a theater's dossier: the background a newcomer needs before today's
news on this dynamic makes sense. The dossier below it already carries the news, so the primer is the one
thing that must still be true next month.

WHAT BELONGS: who the main parties are and what each is after; how the contest got to where it is; the
mechanism that makes it matter (why a strait, a vote or a model release moves other things); the two or
three terms the news keeps using, in plain words.

WHAT DOES NOT: current events. Nothing from the last month, no "today", "now" or "recently". A dated item
in a primer goes stale and the reader cannot tell it has. If you are unsure whether something is
still background or already news, leave it out.

USE ONLY WHAT YOU WERE GIVEN. Every fact must come from the description or the earlier research below. Add
no number, date, name, quote or source from memory, and give no links: a primer that cites something we
did not hold would be believed for being ours. When the material is thin, write less; a short true primer
beats a full one with a guess in it.

FORM: at most 120 words, one or two short paragraphs, plain prose for a reader who has not followed the
story. No heading, no bullets, no estimates about the future.
"""


class Primer(BaseModel):
    text: str


def primers_dir(intel_dir: Path) -> Path:
    return intel_dir / "primers"


def _path(intel_dir: Path, theater_id: str) -> Path:
    return primers_dir(intel_dir) / f"{re.sub(r'[^A-Za-z0-9_-]+', '_', theater_id)}.json"


def load(intel_dir: Path) -> dict[str, dict]:
    """Every stored primer, keyed by theater id (a corrupt file is skipped, not fatal)."""
    out: dict[str, dict] = {}
    for path in sorted(primers_dir(intel_dir).glob("*.json")) if primers_dir(intel_dir).is_dir() else []:
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(row, dict) and row.get("theater_id") and str(row.get("text") or "").strip():
            out[row["theater_id"]] = row
    return out


def is_due(entry: dict | None, *, now: datetime, max_age_days: int = MAX_AGE_DAYS) -> bool:
    """Missing, unreadable-dated or older than ``max_age_days``."""
    if not entry:
        return True
    try:
        built = datetime.fromisoformat(str(entry.get("built_at", "")).replace("Z", "+00:00"))
    except ValueError:
        return True
    built = built if built.tzinfo else built.replace(tzinfo=UTC)
    return now - built > timedelta(days=max_age_days)


def fit(text: str) -> str:
    """The text held to the contract: links dropped, whitespace tidied, at most ``MAX_WORDS`` words (cut at
    the last full sentence inside the limit when there is one)."""
    out = " ".join(_LINK.sub("", text or "").split())
    words = out.split()
    if len(words) <= MAX_WORDS:
        return out
    head = " ".join(words[:MAX_WORDS])
    cut = max(head.rfind(". "), head.rfind("? "), head.rfind("! "))
    if cut > len(head) // 2:
        return head[:cut + 1]
    return head.rstrip(" ,;:-") + "…"


def recall(theater: dict, *, today: date, store: Any = None) -> Any:
    """Our earlier research on the theater, older-than-``MEMORY_DAYS`` claims first; never raises (an empty
    CorpusContext when the corpus has nothing, which just means a thinner primer)."""
    from ..research import corpus
    from ..research.store import JsonProfileStore

    query = "\n".join(p for p in (theater.get("name"), theater.get("why"), theater.get("description")) if p)
    try:
        store = store or JsonProfileStore()
        found = corpus.related(store, query_text=query, as_of=today.isoformat(),
                               older_than=(today - timedelta(days=MEMORY_DAYS)).isoformat())
        return found if not found.empty else corpus.related(store, query_text=query, as_of=today.isoformat())
    except Exception:  # noqa: BLE001 - memory is an aid, not a dependency
        return corpus.CorpusContext()


def write(context: Any, config: Any, model_spec: Any, theater: dict, memory: Any) -> str:
    """One call: the primer text for a theater ('' when the model gave nothing usable)."""
    from langchain_core.messages import HumanMessage, SystemMessage

    from algent_backend.agent_system.prompting import UNIVERSAL_AGENT_BASE, compose_system_prompt

    held = ("OUR EARLIER RESEARCH (graded, dated; use as background, never as news):\n"
            f"{memory.render()}\n\n") if memory is not None and not memory.empty else ""
    task = (f"THEATER: {theater['name']}\nDESCRIPTION: {theater.get('description') or '-'}\n"
            f"WHY THESE EVENTS BELONG TOGETHER: {theater.get('why') or '-'}\n\n{held}TASK: write the primer.")
    model = context.model_resolver.resolve(model_spec).client.with_structured_output(Primer)
    out = model.invoke([SystemMessage(content=compose_system_prompt(UNIVERSAL_AGENT_BASE, PRIMER_ROLE)),
                        HumanMessage(content=task)], config=config)
    return fit(getattr(out, "text", "") or "")


def ensure(context: Any, intel_dir: Path, theaters: list[dict], *, model_spec: Any, now: datetime | None = None,
           max_age_days: int = MAX_AGE_DAYS, store: Any = None, config: Any = None) -> list[dict]:
    """Write a primer for every theater (``{id, name, description, why}``) that has none or whose primer is
    older than ``max_age_days``; reuse the rest untouched. One theater's failure never stops the others.
    Returns a row per theater: ``status`` is built | reused | empty | failed."""
    now = now or datetime.now(UTC)
    stored, rows = load(intel_dir), []
    for t in theaters:
        if not is_due(stored.get(t["id"]), now=now, max_age_days=max_age_days):
            rows.append({"theater": t["id"], "status": "reused"})
            continue
        try:
            memory = recall(t, today=now.date(), store=store)
            text = write(context, config, model_spec, t, memory)
        except Exception as exc:  # noqa: BLE001 - a primer is an extra; the dossier stands without it
            rows.append({"theater": t["id"], "status": "failed", "error": f"{type(exc).__name__}: {str(exc)[:160]}"})
            continue
        if not text:
            rows.append({"theater": t["id"], "status": "empty"})
            continue
        path = _path(intel_dir, t["id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {"theater_id": t["id"], "text": text, "built_at": now.isoformat(), "words": len(text.split()),
                  "memory_claims": len(memory.claims) if memory is not None else 0}
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        rows.append({"theater": t["id"], "status": "built", "words": record["words"]})
    return rows

