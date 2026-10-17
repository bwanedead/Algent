"""
Which of our theaters and countries a market is about.

SOFT BY DESIGN. A mapping only chooses which of our evidence a forecast is shown, and whether a market is worth mirroring at all; it never
gates a score (every forecast of ours on a resolved market is scored, mapped well or not). So it is plain overlap, not a classifier:

* countries: names and aliases from the one country table (``actors.registry``) found as whole words in the question and event title
  (a demonym such as "Iranian" counts via a plain suffix; a short alias such as "US" or "EU" must be written in capitals);
* theaters: the latest daily's sections each give a vocabulary (name, headline, the actors and places its developments name) and a country
  set; a market scores 2 per shared country and 1 per shared distinctive word, and a theater is mapped when its score reaches
  ``flags.MIN_MAP_SCORE``.

Calendar items (elections, central-bank dates) need no mapping step: they are matched at evidence time by country.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from . import flags

_WORD = re.compile(r"[a-z0-9]+")
_SUFFIX = ("", "s", "es", "n", "an", "ian", "ians", "ans", "i", "is", "ese", "ish", "ic")
_STOP = frozenset("""will would could should about after again against also because before between both during each from have into more most
other over same than that their them then there these they this those through under until what when where which while with within without
year years month months week weeks today tomorrow yesterday next last end before june july august september october november december january
february march april may price market yes win wins winner party president presidential election elections announce announces agreement
deal military state states government country official leader minister whether""".split())


def words(text: str) -> list[str]:
    return _WORD.findall((text or "").casefold().replace("’", "'"))


def _same(word: str, alias: str) -> bool:
    return word == alias or (len(alias) >= 4 and word.startswith(alias) and word[len(alias):] in _SUFFIX)


@lru_cache(maxsize=1)
def _aliases() -> tuple[tuple[str, tuple[str, ...], bool], ...]:
    """(iso2, alias words, must be capitalised) for every country name and alias."""
    from algent_backend.actors import registry

    out = []
    for c in registry.load().values():
        for label in {c.name, *c.aliases}:
            w = tuple(words(label))
            if w:
                out.append((c.iso2, w, len(label.replace(".", "")) <= 3))
    return tuple(out)


def countries_in(text: str) -> set[str]:
    """ISO2 codes whose name or alias occurs in ``text`` as whole words (see the module doc for the demonym and short-alias rules)."""
    ws = words(text)
    found: set[str] = set()
    for iso2, alias, caps in _aliases():
        n = len(alias)
        for i in range(len(ws) - n + 1):
            if all(_same(ws[i + k], alias[k]) if k == n - 1 else ws[i + k] == alias[k] for k in range(n)):
                if caps and not re.search(rf"\b{re.escape(''.join(alias).upper())}\b", text.replace(".", "")):
                    continue
                found.add(iso2)
                break
    return found


def distinctive(text: str) -> set[str]:
    return {w for w in words(text) if len(w) >= 5 and w not in _STOP and not w.isdigit()}


@dataclass
class TheaterVocab:
    id: str
    name: str
    countries: set[str] = field(default_factory=set)
    terms: set[str] = field(default_factory=set)


def vocab_from_record(record: dict[str, Any]) -> list[TheaterVocab]:
    """One vocabulary per section of a daily record."""
    out = []
    for s in record.get("theaters") or []:
        if not isinstance(s, dict) or not s.get("theater_id"):
            continue
        parts = [s.get("name", ""), s.get("headline", "")]
        for d in s.get("developments") or []:
            parts += [d.get("headline", ""), d.get("where", ""), *(d.get("actors") or [])]
        text = " ".join(str(p) for p in parts if p)
        out.append(TheaterVocab(id=s["theater_id"], name=str(s.get("name", "")), countries=countries_in(text), terms=distinctive(text)))
    return out


def latest_vocab(domain: str = "geopolitics", root: Path | None = None) -> list[TheaterVocab]:
    """The vocabulary of the newest daily on disk ([] when there is none)."""
    import json

    from algent_backend.agent_system.agents.intel.daily import daily_dir

    folder = root or daily_dir(domain)
    files = sorted(folder.glob("*.json")) if folder.is_dir() else []
    for p in reversed(files):
        try:
            return vocab_from_record(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return []


def map_market(question: str, event_title: str, vocab: list[TheaterVocab]) -> tuple[list[str], list[str], int]:
    """(theater ids best first, countries found, best score)."""
    text = f"{question}. {event_title}"
    cs, ts = countries_in(text), distinctive(text)
    scored = sorted(((2 * len(cs & v.countries) + len(ts & v.terms), v.id) for v in vocab), reverse=True)
    hit = [(s, i) for s, i in scored if s >= flags.MIN_MAP_SCORE]
    return [i for _s, i in hit], sorted(cs), (hit[0][0] if hit else 2 * len(cs))
