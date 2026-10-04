"""
Sensing — which numbers and which words a theater's writers should see.

The desk's two newest inputs are programmatic: ``instruments`` (hard numbers) and the statements
ledger (who said what, from primary transcripts). Neither knows about theaters, so this module is the
one place that turns "a theater" into "the readings and statements that bear on it", and nothing here
names a country, a leader or a commodity.

SELECTION IS MECHANICAL AND DERIVED FROM THE DATA, NOT FROM A LIST OF OURS
* Instruments: the vocabulary is the catalog's own tags. A tag is present when it occurs as a word
  (or contiguous phrase, with a plain suffix such as -n/-an/-ian/-s allowed) in the theater's text:
  name, description, why, member headlines, and the actors of the previous brief/section. Tags of one
  or two letters ("US", "EU") must be capitalised in the text, or "us" would match every pronoun.
  Series sharing a present tag are ranked by the sum of 1/(series carrying that tag), so a rare tag
  ("hormuz") outweighs a common one ("risk"); ties put unusual readings first.
* Statements: the vocabulary is the ledger's own entities (speakers, affiliations, `about`). An entity
  is a term when it occurs in the theater's text; a person's surname also counts when it appears
  capitalised in the text (speakers with an office only: institutions are not given surnames). A
  statement is relevant by how many terms it mentions, then by recency.
* A theater whose text meets no tag and no entity gets nothing; the blocks are then simply absent.

BUDGETS exist only because every line is prompt the writer must read: ``MAX_INSTRUMENT_LINES`` readings,
a statement budget per call (a daily wants the last fortnight's most relevant, a brief the month's), up
to ``MAX_SPEAKER_HISTORIES`` speakers' earlier statements (the most frequent in the recall), and for
the cross-theater view ``CROSS_MOVES`` flagged readings and ``CROSS_STATEMENTS`` statements with at
most ``PER_SPEAKER_CAP`` per speaker so one long speech cannot take the whole top.

Every function here is best-effort: a broken store yields an empty ``Evidence``, never an exception.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from algent_backend.instruments import catalog, evidence

from ..statements import store
from ..statements.recall import block as statements_block, history_block
from ..statements.contracts import Statement
from .contracts import Theater

MAX_INSTRUMENT_LINES = 8
MAX_SPEAKER_HISTORIES = 3
HISTORY_LINES = 6
CROSS_MOVES = 10
CROSS_STATEMENTS = 8
PER_SPEAKER_CAP = 2
DAILY_STATEMENT_DAYS = 14
DAILY_STATEMENTS = 10
HISTORY_DAYS = 60
CROSS_DAYS = 3

_SUFFIXES = ("", "s", "es", "n", "an", "ian", "ians", "ans")


@dataclass
class Evidence:
    """What sensing contributed for one writer call: the prompt blocks and the URLs they make citable."""

    instruments: str = ""
    statements: str = ""
    histories: list[str] = field(default_factory=list)
    instrument_urls: set[str] = field(default_factory=set)      # public-display sources only
    statement_urls: set[str] = field(default_factory=set)
    tags: list[str] = field(default_factory=list)
    terms: list[str] = field(default_factory=list)
    n_instruments: int = 0
    n_statements: int = 0
    error: str = ""

    @property
    def primary_urls(self) -> set[str]:
        return self.instrument_urls | self.statement_urls

    def render(self) -> str:
        """The blocks for a writer's task text ('' when there are none), ending in a blank line."""
        parts = [p for p in (self.instruments, self.statements, *self.histories) if p]
        return "\n\n".join(parts) + "\n\n" if parts else ""


# ── text matching ─────────────────────────────────────────────────────────────────────────────
def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _find(words: list[str], phrase: list[str], raw: str) -> bool:
    """``phrase`` occurs contiguously in ``words`` (its last word may carry a plain suffix)."""
    n = len(phrase)
    if not n or n > len(words):
        return False
    if n == 1 and len(phrase[0]) <= 2 and not re.search(rf"\b(?:{phrase[0].capitalize()}|{phrase[0].upper()})\b", raw):
        return False                                    # "us" the pronoun is not "US" the country
    last = {phrase[-1] + suf for suf in (_SUFFIXES if len(phrase[-1]) >= 4 else ("", "s"))}
    return any(words[i:i + n - 1] == phrase[:-1] and words[i + n - 1] in last for i in range(len(words) - n + 1))


def theater_text(theater: Theater, actors: list[str] | tuple[str, ...] = ()) -> str:
    """Everything the theater says about itself, plus the actors of its previous brief/section."""
    parts = [theater.name, theater.description, theater.why, *actors]
    for m in theater.members:
        parts += [m.title, m.thesis]
    return "\n".join(p for p in parts if p)


def prior_actors(brief: dict | None = None, section: dict | None = None) -> list[str]:
    """Actor names from the previous brief's relations and the previous daily section's developments."""
    names: list[str] = []
    for r in (brief or {}).get("relations") or []:
        names += [r.get("source", ""), r.get("target", "")]
    for d in (section or {}).get("developments") or []:
        names += d.get("actors") or []
    return list(dict.fromkeys(n.strip() for n in names if isinstance(n, str) and n.strip()))


# ── instruments ───────────────────────────────────────────────────────────────────────────────
def instrument_tags(text: str) -> list[str]:
    """Catalog tags present in ``text`` (see module docstring)."""
    words = _words(text)
    vocab = sorted({t for s in catalog.CATALOG for t in s.tags})
    return [t for t in vocab if _find(words, _words(t), text)]


def _instrument_block(text: str, as_of: date | None) -> tuple[str, set[str], list[str], int]:
    tags = instrument_tags(text)
    if not tags:
        return "", set(), [], 0
    carriers = Counter(t for s in catalog.CATALOG for t in set(s.tags))
    rows = evidence.moves_board(tags, as_of=as_of)
    present = set(tags)
    score = {r["series_id"]: sum(1 / carriers[t] for t in present & set(r["tags"])) for r in rows}
    rows = sorted(rows, key=lambda r: (-score[r["series_id"]], not r["unusual"]))[:MAX_INSTRUMENT_LINES]
    return (evidence.render_block(rows, as_of=as_of), {r["source_url"] for r in rows if r["public_display"]},
            tags, len(rows))


# ── statements ────────────────────────────────────────────────────────────────────────────────
def statement_terms(text: str, rows: list[Statement]) -> list[str]:
    """Ledger entities (and office-holders' surnames) that occur in ``text``."""
    words = _words(text)
    found: dict[str, str] = {}
    for s in rows:
        for entity in {s.speaker, s.affiliation, *s.about}:
            if entity and _find(words, _words(entity), text):
                found.setdefault(entity.casefold(), entity)
        sw = _words(s.speaker)
        if s.role and len(sw) > 1 and len(sw[-1]) >= 4 and re.search(rf"\b(?:{sw[-1].capitalize()}|{sw[-1].upper()})\b", text):
            found.setdefault(sw[-1], sw[-1])
    return list(found.values())


def _by_relevance(rows: list[Statement], terms: list[str]) -> list[Statement]:
    newest = sorted(rows, key=lambda s: s.date, reverse=True)
    return sorted(newest, key=lambda s: -store.mention_count(s, terms))


def _histories(shown: list[Statement], *, as_of: date | None, days: int) -> tuple[list[str], set[str]]:
    """Earlier statements by the most frequent speakers in ``shown``, so tone can be read as a trajectory."""
    seen = {s.id for s in shown}
    blocks, urls = [], set()
    for speaker, _n in Counter(s.speaker for s in shown).most_common(MAX_SPEAKER_HISTORIES):
        earlier = [s for s in store.query(speaker=speaker, days=days, today=as_of) if s.id not in seen][:HISTORY_LINES]
        if earlier:
            blocks.append(history_block(speaker, earlier, days))
            urls |= {s.source_url for s in earlier}
    return blocks, urls


def _statement_block(text: str, as_of: date | None, *, days: int, limit: int, history_days: int
                     ) -> tuple[str, list[str], set[str], list[str], int]:
    rows = store.query(days=days, today=as_of)
    terms = statement_terms(text, rows)
    if not terms:
        return "", [], set(), [], 0
    picked = [s for s in _by_relevance(rows, terms) if store.mention_count(s, terms)][:limit]
    shown = sorted(picked, key=lambda s: s.date, reverse=True)
    histories, history_urls = _histories(shown, as_of=as_of, days=history_days)
    return (statements_block(shown, days), histories, {s.source_url for s in shown} | history_urls, terms, len(shown))


# ── the two entry points ──────────────────────────────────────────────────────────────────────
def for_theater(theater: Theater, *, as_of: str | date, actors: list[str] | tuple[str, ...] = (),
                statement_days: int = DAILY_STATEMENT_DAYS, statement_limit: int = DAILY_STATEMENTS,
                history_days: int = HISTORY_DAYS) -> Evidence:
    """The readings and statements bearing on one theater, as of ``as_of``. Never raises."""
    ev = Evidence()
    try:
        day = date.fromisoformat(as_of) if isinstance(as_of, str) else as_of
        text = theater_text(theater, actors)
        ev.instruments, ev.instrument_urls, ev.tags, ev.n_instruments = _instrument_block(text, day)
        ev.statements, ev.histories, ev.statement_urls, ev.terms, ev.n_statements = _statement_block(
            text, day, days=statement_days, limit=statement_limit, history_days=history_days)
    except Exception as exc:  # noqa: BLE001 - sensing is an aid; a broken store must not cost the report
        return Evidence(error=f"{type(exc).__name__}: {str(exc)[:160]}")
    return ev


def _weight(s: Statement) -> int:
    """How much a statement says on its face: a strong stance and a stated kind of act (a threat, a
    commitment, a tone shift) outweigh a neutral remark. No threshold: it only orders."""
    return abs(s.stance) + (s.signal != "other")


def across_theaters(*, as_of: str | date, days: int = CROSS_DAYS) -> Evidence:
    """For the day's top: the flagged moves across ALL series and the weightiest recent statements across
    ALL actors, so a major speech or number lands even when no hot theater claims it. Never raises."""
    try:
        day = date.fromisoformat(as_of) if isinstance(as_of, str) else as_of
        rows = [r for r in evidence.moves_board(None, as_of=day) if r["unusual"] or r["long_run_outside"]]
        rows = rows[:CROSS_MOVES]                                  # moves_board lists unusual ones first
        taken: Counter[str] = Counter()
        shown: list[Statement] = []
        for s in sorted(sorted(store.query(days=days, today=day), key=lambda s: s.date, reverse=True),
                        key=lambda s: -_weight(s)):
            if taken[s.speaker] < PER_SPEAKER_CAP and len(shown) < CROSS_STATEMENTS:
                taken[s.speaker] += 1
                shown.append(s)
        shown.sort(key=lambda s: s.date, reverse=True)
        return Evidence(instruments=evidence.render_block(rows, as_of=day), statements=statements_block(shown, days),
                        n_instruments=len(rows), n_statements=len(shown),
                        instrument_urls={r["source_url"] for r in rows if r["public_display"]},
                        statement_urls={s.source_url for s in shown})
    except Exception as exc:  # noqa: BLE001
        return Evidence(error=f"{type(exc).__name__}: {str(exc)[:160]}")


def summary_for_report(ev: Evidence) -> dict[str, Any]:
    """The small, JSON-friendly account of what sensing contributed, for a run report row."""
    out: dict[str, Any] = {"instruments": ev.n_instruments, "statements": ev.n_statements}
    if ev.error:
        out["error"] = ev.error
    return out
