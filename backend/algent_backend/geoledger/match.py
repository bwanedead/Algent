"""
Matching a name found in text to an asset of the ledger: transliteration-tolerant fuzzy names, hard guards (unit
numbers must agree, type and country must be compatible), a nearness bonus, and a refusal when two assets tie.

The same plant is written Darnytska, Darnitsa, ТЕЦ-5, TEC-5, CHP-5, Zmiivska, Zmiyivska... so names are folded to
bare content tokens (the generic words "power plant", "TPP", "CHP" carry the type, not the identity) and compared by
similarity. A wrong merge is worse than a duplicate (it hangs one plant's status on another), so the unit number is a
hard guard and an ambiguous top match resolves to nothing; the caller then mints a new, approximate asset.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Protocol

from .contracts import Asset, fold

MATCH_MIN = 0.84          # a name must be this similar (0..1) to be taken as the same place
TIE_MARGIN = 0.03         # a second asset this close to the best makes the match ambiguous
NEAR_KM = 25.0            # a candidate this close to an asset gains NEAR_BONUS
NEAR_BONUS = 0.08

#: Words that say what a thing is or who runs it, not which one it is.
STOP = frozenset("""power plant plants station stations thermal tpp chp tec tets tes hpp npp gres hes pp heat electric
electricity energy company co ltd jsc pjsc llc the of and de la el unit units oil refinery depot port airbase air base
substation sub dam bridge hydro hydroelectric nuclear solar wind facility complex terminal storage fuel
aes hres ges tetz""".split())

#: The generic words that name a plant's kind, in every spelling the desk meets (Latin and transliterated Cyrillic:
#: CHP = TEC = TETs = ТЕЦ = ТЭЦ; TPP = TES = ТЕС; HPP = GES = HES = ГЕС; NPP = AES = АЕС). Kind is a guard, not an identity.
PLANT_CLASS: dict[str, str] = {**dict.fromkeys(("chp", "tec", "tets", "tetz", "tes", "tpp", "gres", "hres"), "thermal"),
                               **dict.fromkeys(("hpp", "ges", "hes", "hydro", "hydroelectric"), "hydro"),
                               **dict.fromkeys(("npp", "aes", "zaes", "nuclear"), "nuclear")}

_CYR = dict(zip("абвгґдеєжзиіїйклмнопрстуфхцчшщьюяыэё",
                ["a", "b", "v", "h", "g", "d", "e", "ie", "zh", "z", "y", "i", "yi", "i", "k", "l", "m", "n", "o", "p",
                 "r", "s", "t", "u", "f", "kh", "ts", "ch", "sh", "shch", "", "iu", "ia", "y", "e", "e"], strict=True))
_WORD = re.compile(r"[a-z]+|[0-9]+")           # "chp5" is "chp" and "5"


def _translit(text: str) -> str:
    return "".join(_CYR.get(c, c) for c in text)


def fold_token(t: str) -> str:
    """One word reduced so spellings of one name meet: y/i/j, kh/h, ph/f, w/v, doubled letters."""
    t = t.replace("kh", "h").replace("ph", "f").replace("ck", "k").replace("w", "v").replace("yi", "i").replace("ya", "ia")
    t = t.replace("y", "i").replace("j", "i").replace("q", "k").replace("ie", "i")
    return re.sub(r"(.)\1+", r"\1", t)


_ADJ = ("skaia", "skoie", "skoe", "skii", "ska", "ske", "ski", "sk")      # Kharkivska, Zaporizka: "of Kharkiv" names the town too


def stem(w: str) -> str:
    """A folded word without its adjectival ending, when enough of it is left to name something."""
    for suf in _ADJ:
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: -len(suf)]
    return w


def tokens(name: str) -> tuple[list[str], set[str]]:
    """(content words folded, unit numbers) of a name: ``Kyiv CHP-5`` -> (["kiiv"], {"5"})."""
    words, nums = [], set()
    for w in _WORD.findall(_translit(fold(name))):
        if w.isdigit():
            nums.add(w.lstrip("0") or "0")
        elif w not in STOP and len(w) > 1:
            words.append(fold_token(w))
    return words, nums


def plant_class(name: str) -> str:
    """"thermal" | "hydro" | "nuclear" when the name says what kind of plant it is, else "" (``Kyiv TETs-5`` -> thermal)."""
    return next((PLANT_CLASS[w] for w in _WORD.findall(_translit(fold(name))) if w in PLANT_CLASS), "")


def name_score(a: str, b: str) -> float:
    """0..1 similarity of two names; 0 when their unit numbers disagree or neither has any content word."""
    aw, an = tokens(a)
    bw, bn = tokens(b)
    if an and bn and an != bn:
        return 0.0                                 # CHP-5 is not CHP-6
    ca, cb = plant_class(a), plant_class(b)
    if ca and cb and ca != cb:
        return 0.0                                 # Dnipro HPP is not Dnipro CHP
    if not aw or not bw:
        return 0.0
    score = max(SequenceMatcher(None, " ".join(sorted(aw)), " ".join(sorted(bw))).ratio(),
                SequenceMatcher(None, " ".join(sorted(map(stem, aw))), " ".join(sorted(map(stem, bw)))).ratio())
    if bool(an) != bool(bn):
        score -= 0.1                               # one names a unit, the other does not: weaker
    return max(0.0, score)


def km_between(a: tuple[float, float], b: tuple[float, float]) -> float:
    (la1, lo1), (la2, lo2) = a, b
    p1, p2 = math.radians(la1), math.radians(la2)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lo2 - lo1) / 2) ** 2
    return 12742.0 * math.asin(math.sqrt(h))


class _Index(Protocol):
    def candidates(self, words: set[str], country: str) -> list[Asset]: ...


@dataclass(frozen=True)
class Match:
    asset: Asset | None
    score: float
    reason: str = ""            # why no asset: "no candidate" | "ambiguous" | "below threshold"


def _compatible(a: Asset, type_: str, country: str) -> bool:
    return (not country or not a.country or a.country == country) and (type_ == "other" or a.type in (type_, "other"))


def find(index: _Index, names: list[str], *, type_: str = "other", country: str = "",
         at: tuple[float, float] | None = None) -> Match:
    """The asset ``names`` (the name as written, then any known-as variants) refers to, or why none."""
    names = [n for n in dict.fromkeys(n.strip() for n in names) if n]
    words = {w for n in names for w in tokens(n)[0]}
    if not words:
        return Match(None, 0.0, "no candidate")
    scored: list[tuple[float, Asset]] = []
    for a in index.candidates(words, country):
        if not _compatible(a, type_, country):
            continue
        best = max((name_score(n, m) for n in names for m in (a.name, *a.aliases)), default=0.0)
        if best and at is not None and a.lat is not None and a.lon is not None and km_between(at, (a.lat, a.lon)) <= NEAR_KM:
            best = min(1.0, best + NEAR_BONUS)
        if best >= MATCH_MIN:
            scored.append((best, a))
    if not scored:
        return Match(None, 0.0, "below threshold" if index.candidates(words, country) else "no candidate")
    scored.sort(key=lambda s: -s[0])
    if len(scored) > 1 and scored[0][0] - scored[1][0] < TIE_MARGIN:
        if (winner := _nearer(scored[0][1], scored[1][1], at)) is None:
            return Match(None, scored[0][0], "ambiguous")
        return Match(winner, scored[0][0] if winner is scored[0][1] else scored[1][0])
    return Match(scored[0][1], scored[0][0])


def _nearer(a: Asset, b: Asset, at: tuple[float, float] | None) -> Asset | None:
    """Of two equally good matches, the one clearly nearer the stated position; None when position cannot tell them apart."""
    if at is None or a.lat is None or a.lon is None or b.lat is None or b.lon is None:
        return None
    da, db = km_between(at, (a.lat, a.lon)), km_between(at, (b.lat, b.lon))
    return None if abs(da - db) < 5.0 else (a if da < db else b)
