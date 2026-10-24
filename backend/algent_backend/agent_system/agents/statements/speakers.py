"""
Speaker spellings -> one name per person, derived from the ledger itself (no hand list).

The extractor writes a speaker as the text spells it, so one person arrives as "Volodymyr Zelensky", "Zelenskyy" and
"Zelensky". A split name splits a count and a tone line, so the public export folds them. The rule is conservative and
reads only the statements: two spellings under the same affiliation are one person when the SHORTER one's surname (last
word) matches the longer one's surname and every other word of the shorter one appears in the longer one (a word matches
when equal or a near-spelling: Zelensky/Zelenskyy). A short name that fits two different people ("Khamenei" with both Ali
and Mojtaba) is left alone. The canonical spelling is the most common one (ties: the longer).
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from difflib import SequenceMatcher

from .contracts import Statement

NEAR_SPELLING = 0.88      # SequenceMatcher ratio at which two long words count as one spelling of a name (Zelensky/Zelenskyy = 0.94)
MIN_FUZZY_LEN = 5         # shorter words must match exactly: "Lee" is not "Li"


def _words(name: str) -> list[str]:
    return re.findall(r"[^\W_]+", name.casefold())


def _same_word(a: str, b: str) -> bool:
    return a == b or (min(len(a), len(b)) >= MIN_FUZZY_LEN and SequenceMatcher(None, a, b).ratio() >= NEAR_SPELLING)


def _fits(short: list[str], long: list[str]) -> bool:
    """``short`` is a spelling of the person ``long`` names: same surname, the rest found in ``long``."""
    if not short or len(short) > len(long) or not _same_word(short[-1], long[-1]):
        return False
    return all(any(_same_word(w, x) for x in long[:-1]) for w in short[:-1])


def _same_person(a: str, b: str) -> bool:
    wa, wb = _words(a), _words(b)
    return _fits(wa, wb) or _fits(wb, wa)


def canonical_map(statements: Iterable[Statement]) -> dict[str, str]:
    """{spelling as extracted: canonical spelling}, only for the spellings that change."""
    by_aff: dict[str, Counter[str]] = {}
    for s in statements:
        if s.speaker.strip():
            by_aff.setdefault(s.affiliation.strip().casefold(), Counter())[s.speaker.strip()] += 1
    out: dict[str, str] = {}
    for names in by_aff.values():
        spell = list(names)
        parent = {n: n for n in spell}

        def find(n: str) -> str:
            while parent[n] != n:
                n = parent[n]
            return n

        for short in spell:
            hits = [n for n in spell if n != short and len(_words(n)) >= len(_words(short)) and _fits(_words(short), _words(n))]
            if hits and all(_same_person(a, b) for a in hits for b in hits):      # fits one person, not two
                parent[find(short)] = find(hits[0])
        groups: dict[str, list[str]] = {}
        for n in spell:
            groups.setdefault(find(n), []).append(n)
        for members in groups.values():
            best = max(members, key=lambda n: (names[n], len(_words(n)), n))
            out.update({n: best for n in members if n != best})
    return out
