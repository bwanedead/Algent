"""
Sensing — which numbers and which words a theater's writers should see.

The desk's two newest inputs are programmatic: ``instruments`` (hard numbers) and the statements
ledger (who said what, from primary transcripts). Neither knows about theaters, so this module is the
one place that turns "a theater" into "the readings and statements that bear on it", and nothing here
names a country, a leader or a commodity.

SELECTION IS MECHANICAL AND DERIVED FROM THE DATA, NOT FROM A LIST OF OURS
* Presence. The instruments' vocabulary is the catalog's tags; the statements' is the ledger's entities
  (speakers, affiliations, `about`). An item is present when it occurs as a word or contiguous phrase
  (a plain suffix such as -n/-an/-ian/-s allowed; one- and two-letter items must be capitalised, or "us"
  would match every pronoun). A speaker's surname stands for the speaker only when the ledger shows it
  belongs to that speaker alone: it is not part of their title and not a word of any other entity
  ("States" belongs to "United States", "Minister" to every minister).
* Corroboration. An item counts for a theater only when it is in the theater's own account of itself
  (name, description, why, previous actors) or in at least two of its member headlines: one headline
  mentioning a country in passing does not make the theater about it.
* Distinctiveness (``Rarity``). Items are weighted by idf over their own vocabulary (statements for
  entities, series for tags), and a statement/series qualifies only through at least one DISTINCTIVE
  item: rarer than the median mention. In a Kremlin-heavy ledger "Russia" is the typical mention and
  cannot alone tie a statement to a theater; a tag carried by many series ("energy", "risk") cannot alone
  tie a series. Qualifiers rank by summed idf (then recency / unusual-first).
* Histories: a speaker's earlier statements are shown only for speakers whose shown statements qualified,
  and only those about the same distinctive counterparts (tone toward them, not the speaker's other news).
* A theater that meets no distinctive item gets nothing; the blocks are then simply absent.

BUDGETS exist only because every line is prompt the writer must read: ``MAX_INSTRUMENT_LINES`` readings,
a statement budget per call (a daily wants the last fortnight's most relevant, a brief the month's), up
to ``MAX_SPEAKER_HISTORIES`` speakers' earlier statements (the most frequent in the recall), and for
the cross-theater view ``CROSS_MOVES`` flagged readings and ``CROSS_STATEMENTS`` statements with at
most ``PER_SPEAKER_CAP`` per speaker so one long speech cannot take the whole top.

Every function here is best-effort: a broken store yields an empty ``Evidence``, never an exception.
"""

from __future__ import annotations

import math
import re
import statistics
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from algent_backend.instruments import catalog, evidence
from algent_backend.instruments import store as istore
from algent_backend.instruments import moves
from algent_backend.instruments.contracts import period_date

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
    shown: list[Statement] = field(default_factory=list)     # the statements in the block, in the order shown
    tags: list[str] = field(default_factory=list)
    terms: list[str] = field(default_factory=list)
    n_instruments: int = 0
    n_statements: int = 0
    instrument_rows: list[dict[str, Any]] = field(default_factory=list)   # the readings shown (for novelty)
    statement_dates: list[str] = field(default_factory=list)              # EVERY qualifying statement's date, not just those shown
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
    return any(words[i:i + n - 1] == phrase[:-1] and _same(words[i + n - 1], phrase[-1]) for i in range(len(words) - n + 1))


def _same(a: str, b: str) -> bool:
    """Equal, or one is the other plus a plain suffix ("Houthi"/"Houthis", "Iran"/"Iranian"), stem of 4+ letters."""
    short, long_ = sorted((a, b), key=len)
    return a == b or (len(short) >= 4 and long_.startswith(short) and long_[len(short):] in _SUFFIXES)


def corroborated(find: Callable[[str], set[str]], theater: Theater, actors: list[str] | tuple[str, ...] = ()) -> set[str]:
    """Items ``find`` extracts from the theater that it stands behind: those in its own account (name,
    description, why, previous actors) or in at least two member headlines (two independent mentions)."""
    core = find("\n".join(p for p in (theater.name, theater.description, theater.why, *actors) if p))
    members = Counter(k for m in theater.members for k in find(f"{m.title}\n{m.thesis}"))
    return core | {k for k, n in members.items() if n >= 2}


def prior_actors(brief: dict | None = None, section: dict | None = None) -> list[str]:
    """Actor names from the previous brief's relations and the previous daily section's developments."""
    names: list[str] = []
    for r in (brief or {}).get("relations") or []:
        names += [r.get("source", ""), r.get("target", "")]
    for d in (section or {}).get("developments") or []:
        names += d.get("actors") or []
    return list(dict.fromkeys(n.strip() for n in names if isinstance(n, str) and n.strip()))


# ── informativeness (shared by both layers) ───────────────────────────────────────────────────
@dataclass
class Rarity:
    """How informative each item of a vocabulary is, from the vocabulary's own statistics.

    ``idf`` is ln(N / df): N documents (ledger statements; catalog series), df those carrying the item.
    An item in every document has idf 0 and says nothing. ``cut`` is the idf of the MEDIAN MENTION: sort
    all mentions by idf and take the one halfway through, so the cut sits where the typical mention sits,
    not where the typical (mostly one-off) item sits. An item is DISTINCTIVE when its idf is above the
    cut, i.e. at least as rare as the typical thing people are said to talk about ("at least" because a flat
    vocabulary such as the catalog's tags has many items at the median and none above it). In a Kremlin-heavy ledger
    "Russia", "Putin", "NATO" and "EU" are the typical mentions and so cannot, alone, tie a statement to
    a theater; a ledger where every item is equally common has no distinctive item at all."""

    idf: dict[str, float]
    cut: float

    def distinctive(self, key: str) -> bool:
        return self.idf.get(key, 0.0) > 0 and self.idf[key] >= self.cut


def rarity(documents: list[set[str]]) -> Rarity:
    n = len(documents)
    df = Counter(k for doc in documents for k in doc)
    idf = {k: math.log(n / c) for k, c in df.items()}
    half, seen, cut = sum(df.values()) / 2, 0, 0.0
    for k in sorted(df, key=lambda k: idf[k]):
        seen += df[k]
        if seen >= half:
            cut = idf[k]
            break
    return Rarity(idf, cut)


# ── instruments ───────────────────────────────────────────────────────────────────────────────
def instrument_tags(text: str) -> list[str]:
    """Catalog tags present in ``text`` (see module docstring)."""
    words = _words(text)
    vocab = sorted({t for s in catalog.CATALOG for t in s.tags})
    return [t for t in vocab if _find(words, _words(t), text)]


def _instrument_block(theater: Theater, actors: Any, as_of: date | None
                      ) -> tuple[str, set[str], list[str], int, list[dict]]:
    """Readings for series that share at least one DISTINCTIVE corroborated tag (a tag carried by few series,
    see ``Rarity``); generic tags only add weight to a series that already qualifies. Ranked by summed idf."""
    tags = sorted(corroborated(lambda t: set(instrument_tags(t)), theater, actors))
    if not tags:
        return "", set(), [], 0, []
    rar = rarity([set(s.tags) for s in catalog.CATALOG])
    present = set(tags)
    distinctive = {t for t in present if rar.distinctive(t)}
    # A series qualifies on STRENGTH >= 2: each shared distinctive tag counts once, twice when the tag names
    # what the series IS (it is a word of the series' name: "hormuz", "brent"). One shared tag that merely
    # relates ("africa" is on a shipping lane, "risk" on a volatility index) is a coincidence; a second
    # independent one, or a tag that is the series' own subject, is a topic.
    def strength(r: dict) -> int:
        name = set(_words(r["name"]))
        return sum(2 if set(_words(t)) <= name else 1 for t in distinctive & set(r["tags"]))

    rows = [r for r in evidence.moves_board(tags, as_of=as_of) if strength(r) >= 2]
    score = {r["series_id"]: sum(rar.idf[t] for t in present & set(r["tags"])) for r in rows}
    rows = sorted(rows, key=lambda r: (-score[r["series_id"]], not r["unusual"]))[:MAX_INSTRUMENT_LINES]
    return (evidence.render_block(rows, as_of=as_of), {r["source_url"] for r in rows if r["public_display"]},
            tags, len(rows), rows)


# ── statements ────────────────────────────────────────────────────────────────────────────────
def _entities(s: Statement) -> set[str]:
    return {e.casefold() for e in (s.speaker, s.affiliation, *s.about) if e and e.strip()}


Vocabulary = list[tuple[str, str, list[str], bool]]      # (key, surface form, phrase words, surname alias?)


def vocabulary(ledger: list[Statement]) -> Vocabulary:
    """The ledger's entities as matchable phrases, plus a surname alias for speakers that earn one (see the
    module docstring): the speaker holds an office, the surname is not in that office's title, and no other
    entity in the ledger contains the word."""
    forms: dict[str, str] = {}
    for st in ledger:
        for e in (st.speaker, st.affiliation, *st.about):
            if e and e.strip():
                forms.setdefault(e.casefold(), e)
    word_owners: dict[str, set[str]] = {}
    for key in forms:
        for w in _words(key):
            word_owners.setdefault(w, set()).add(key)
    vocab: Vocabulary = [(k, f, _words(f), False) for k, f in forms.items()]
    speakers = {st.speaker.casefold() for st in ledger}
    done: set[str] = set()
    for st in ledger:
        sw, key = _words(st.speaker), st.speaker.casefold()
        if key in done or not st.role or len(sw) < 2 or len(sw[-1]) < 4 or sw[-1] in _words(st.role):
            continue
        done.add(key)
        # every entity holding the word must be this speaker (or another form of the same surname's speaker)
        if all(o == key or (o in speakers and _words(o)[-1] == sw[-1]) for o in word_owners.get(sw[-1], set())):
            vocab.append((key, st.speaker, [sw[-1]], True))
    return vocab


def statement_terms(text: str, vocab: Vocabulary) -> set[str]:
    """Keys of the vocabulary's entities that occur in ``text``."""
    words = _words(text)
    out = set()
    for key, _surface, phrase, alias in vocab:
        if key in out or not _find(words, phrase, text):
            continue
        if alias and not re.search(rf"\b(?:{phrase[0].capitalize()}|{phrase[0].upper()})\b", text):
            continue
        out.add(key)
    return out


def _histories(shown: list[Statement], shared: dict[str, set[str]], *, as_of: date | None, days: int
               ) -> tuple[list[str], set[str]]:
    """Earlier statements by the most frequent speakers in ``shown`` ABOUT THE SAME distinctive counterparts
    the shown ones qualified on: the question is whether tone toward them shifted, not what else the speaker said."""
    seen = {s.id for s in shown}
    blocks, urls = [], set()
    for speaker, _n in Counter(s.speaker for s in shown).most_common(MAX_SPEAKER_HISTORIES):
        keys = shared.get(speaker, set())
        earlier = [s for s in store.query(speaker=speaker, days=days, today=as_of)
                   if s.id not in seen and keys & _entities(s)][:HISTORY_LINES]
        if earlier:
            blocks.append(history_block(speaker, earlier, days))
            urls |= {s.source_url for s in earlier}
    return blocks, urls


def _statement_block(theater: Theater, actors: Any, as_of: date | None, *, days: int, limit: int,
                     history_days: int) -> tuple[str, list[str], set[str], list[str], list[Statement], list[str]]:
    """A statement qualifies when it shares at least one DISTINCTIVE corroborated entity with the theater
    (rarity is measured over the whole ledger, see ``Rarity``). Qualifiers rank by the summed idf of the
    shared entities, then recency; common entities add weight but never qualify a statement alone."""
    ledger = store.load_statements()
    rar = rarity([_entities(s) for s in ledger])
    vocab = vocabulary(ledger)
    keys = corroborated(lambda t: statement_terms(t, vocab), theater, actors)
    distinctive = {k for k in keys if rar.distinctive(k)}
    if len(keys) == 1:        # a lone entity must be rarer than the typical mention, not merely as rare
        distinctive = {k for k in distinctive if rar.idf[k] > rar.cut}
    rows = store.query(days=days, today=as_of)
    need = min(2, len(keys))                      # one shared entity is a coincidence when two were available
    scored = [(s, sum(rar.idf[k] for k in keys & _entities(s))) for s in rows
              if distinctive & _entities(s) and len(keys & _entities(s)) >= need]
    terms = sorted(keys)
    if not scored:
        return "", [], set(), terms, [], []
    newest = sorted(scored, key=lambda p: p[0].date, reverse=True)
    picked = [s for s, _w in sorted(newest, key=lambda p: -p[1])][:limit]
    shown = sorted(picked, key=lambda s: s.date, reverse=True)
    shared: dict[str, set[str]] = {}
    for s in shown:
        shared.setdefault(s.speaker, set()).update(distinctive & _entities(s))
    histories, history_urls = _histories(shown, shared, as_of=as_of, days=history_days)
    return (statements_block(shown, days), histories, {s.source_url for s in shown} | history_urls, terms, shown,
            sorted(s.date for s, _w in scored))


# ── the two entry points ──────────────────────────────────────────────────────────────────────
def for_theater(theater: Theater, *, as_of: str | date, actors: list[str] | tuple[str, ...] = (),
                statement_days: int = DAILY_STATEMENT_DAYS, statement_limit: int = DAILY_STATEMENTS,
                history_days: int = HISTORY_DAYS) -> Evidence:
    """The readings and statements bearing on one theater, as of ``as_of``. Never raises."""
    ev = Evidence()
    try:
        day = date.fromisoformat(as_of) if isinstance(as_of, str) else as_of
        ev.instruments, ev.instrument_urls, ev.tags, ev.n_instruments, ev.instrument_rows = _instrument_block(
            theater, actors, day)
        (ev.statements, ev.histories, ev.statement_urls, ev.terms, ev.shown,
         ev.statement_dates) = _statement_block(
            theater, actors, day, days=statement_days, limit=statement_limit, history_days=history_days)
        ev.n_statements = len(ev.shown)
    except Exception as exc:  # noqa: BLE001 - sensing is an aid; a broken store must not cost the report
        return Evidence(error=f"{type(exc).__name__}: {str(exc)[:160]}")
    return ev


def _weight(s: Statement) -> int:
    """How much a statement says on its face: a strong stance and a stated kind of act (a threat, a
    commitment, a tone shift) outweigh a neutral remark. No threshold: it only orders."""
    return abs(s.stance) + (s.signal != "other")


def _trending(series_id: str, day: date) -> bool:
    """A series that keeps drifting one way is not departing from anything: a debt total is always rising, so
    "unusual" or "outside its full-history range" says nothing about it. Test: over the last 90 days (the
    longest recent window ``moves`` uses), is the mean period-over-period change distinguishable from zero
    against the scatter of those changes (a t-statistic above ``moves.Z_LIMIT``, the same two-sigma convention,
    with at least ``moves.MIN_SAMPLE`` changes)? A collapse is different: one or two large steps and then
    noise around the new level, so the scatter swamps the mean."""
    obs = [(period_date(o.period), o.value) for o in istore.history(series_id) if period_date(o.period) <= day]
    if not obs:
        return False
    recent = [v for d, v in obs if (obs[-1][0] - d).days <= 90]
    steps = [b - a for a, b in zip(recent, recent[1:])]
    if len(steps) < moves.MIN_SAMPLE:
        return False
    sd = statistics.pstdev(steps)
    return sd > 0 and abs(statistics.fmean(steps)) / (sd / math.sqrt(len(steps))) > moves.Z_LIMIT


def across_theaters(*, as_of: str | date, days: int = CROSS_DAYS) -> Evidence:
    """For the day's top: the flagged moves across ALL series (except ones that merely trend) and the weightiest
    recent statements across ALL actors, so a major speech or number lands even when no hot theater claims
    it. Never raises."""
    try:
        day = date.fromisoformat(as_of) if isinstance(as_of, str) else as_of
        rows = [r for r in evidence.moves_board(None, as_of=day)
                if (r["unusual"] or r["long_run_outside"]) and not _trending(r["series_id"], day)]
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
                        n_instruments=len(rows), n_statements=len(shown), shown=shown,
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
