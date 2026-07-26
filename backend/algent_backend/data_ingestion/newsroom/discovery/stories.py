"""
Story-shaped candidates — event grain from GKG, not abstract theme tags.

GKG gives us coded themes + entities + article URLs. Theme codes alone produce
broad standing topics ("naturalgas", "Iran war vibes"). The *story* usually lives
in the URL slug (headline-shaped path) and in co-occurring actor+action bundles.

This module extracts two complementary candidate kinds:

- **story** — clustered by normalized URL path slug (headline proxy, free)
- **event** — person/org × action-theme co-occurrence within the same documents

Both feed the same ranking surface as theme/entity candidates. Pure / deterministic.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import urlparse

from dataclasses import dataclass, field

from ..sources.records import GkgRecord
from ..topic_filters import is_sports_text
from .candidates import CandidateStats
from .noise import is_boilerplate_theme, is_noise_entity
from .pillars import pillar_for_theme


@dataclass
class _Acc:
    count: int = 0
    tone_sum: float = 0.0
    tone_n: int = 0
    display: str = ""
    theme: str = ""
    languages: set[str] = field(default_factory=set)
    sources: set[str] = field(default_factory=set)
    support: set[int] = field(default_factory=set)
    examples: list[str] = field(default_factory=list)

# Theme fragments that look like *moves* / ruptures / feats — not standing tags.
_ACTION_MARKERS: tuple[str, ...] = (
    "WAR", "ARMED", "MILITARY", "TERROR", "PROTEST", "SANCTION", "STRIKE",
    "BOMB", "MISSILE", "CEASEFIRE", "BLOCKADE", "SIEGE", "SEIGE", "ASSAULT",
    "KILL", "ARREST", "INDICT", "IMPEACH", "ASSASSIN", "COUP", "INVASION",
    "OCCUP", "NUCLEAR", "EXPLOSION", "REFUGEE", "EVACUAT", "EMBARGO",
    "DEFAULT", "BANKRUPT", "SHUTDOWN", "ELECTION", "DIPLOMA", "TREATY",
    "NEGOTIAT", "PEACE", "ALLIANCE", "DISASTER", "EARTHQUAKE", "FLOOD",
    "WILDFIRE", "EPIDEMIC", "OUTBREAK", "SCIENCE", "DISCOVER", "LAUNCH",
    "CRISIS", "ATTACK", "DEFENSE", "DEFENCE", "HOSTAGE", "RANSOM",
    "EXPEL", "DEPORT", "TARIFF", "EXPORT", "PIPELINE", "REFINERY",
    "CYBER", "HACK", "LEAK", "WHISTLE", "RULING", "VERDICT", "CONVICT",
)

# Standing mega-themes — never promote as the *story* action alone.
_BROAD_ACTION_DENY: tuple[str, ...] = (
    "ECON_", "GENERAL_", "POPULATION_", "WB_696_", "UNGP_", "EPU_POLICY",
    "TAX_FNCACT", "MEDIA_", "SOC_GENERAL", "ENV_CLIMATECHANGE",
)

# Actor×action pairs that are still "Iran war broadly" — mega actor + weak action.
_MEGA_ACTORS = frozenset({
    "united states", "donald trump", "vladimir putin", "china", "russia",
    "european union", "union european", "nato", "white house", "joe biden",
    "benjamin netanyahu", "iran", "israel",
})
# Action humanizations that are still theater-level without a specific object.
_WEAK_ACTION_TOKENS = (
    "armedconflict", "military", "war", "disaster", "kill", "terror",
    "political violence", "negotiation", "protest", "employability",
    "science", "peace operations", "conflict management", "military title",
)

# URL-slug entertainment / lifestyle junk (not news events).
_STORY_JUNK = (
    "bobby bones", "can you date", "dating", "crime series", "film series",
    "netflix", "box office", "red carpet", "onlyfans", "podcast",
    "vocabulary challenge", "word of the day", "tropical radio", "maluma",
    "artisan gelato", "fahrtest", "skoda", "diner now open", "richtig lueften",
    "raumklima", "assassin", "man child porn", "vape shop", "kayak acquires",
)

_MIN_SLUG_TOKENS = 4
_MAX_SLUG_TOKENS = 18
_MAX_EXAMPLES = 3
_MAX_ACTIONS_PER_RECORD = 2
_MAX_ACTORS_PER_RECORD = 3

_SLUG_NOISE = re.compile(
    r"^(index|article|story|news|world|local|sports|video|photos?|html?)$",
    re.I,
)
_HEXISH = re.compile(r"^[a-f0-9]{8,}$", re.I)
_DATEISH = re.compile(r"^\d{4}[-/]?\d{0,2}[-/]?\d{0,2}$")


def extract_story_candidates(
    records: Iterable[GkgRecord], *, min_count: int = 1
) -> list[CandidateStats]:
    """Headline-proxy candidates from URL path slugs, aggregated across the batch.

    Most GKG URLs appear once; ``min_count`` defaults to 1. Singleton stories must
    still look *eventful* (action theme or named actor) so we do not flood ranking
    with every blog slug in the batch.
    """
    batch = list(records)
    acc: dict[str, _Acc] = {}
    quality: dict[str, int] = {}  # eventfulness score for ranking among singletons
    for index, record in enumerate(batch):
        label = url_slug_label(record.url)
        if not label or is_sports_text(label) or _is_junk_story(label):
            continue
        key = label.casefold()
        entry = acc.setdefault(key, _Acc())
        entry.count += 1
        entry.support.add(index)
        entry.languages.add(record.language)
        if record.source_name:
            entry.sources.add(record.source_name)
        if record.url and len(entry.examples) < _MAX_EXAMPLES and record.url not in entry.examples:
            entry.examples.append(record.url)
        if record.tone is not None:
            entry.tone_sum += record.tone
            entry.tone_n += 1
        if not entry.display:
            entry.display = label
        quality[key] = max(quality.get(key, 0), _eventfulness(record, label))

    stats: list[CandidateStats] = []
    for key, entry in acc.items():
        if entry.count < min_count:
            continue
        # Singletons need event signal; multi-outlet clusters always pass.
        if entry.count == 1 and quality.get(key, 0) < 2:
            continue
        if entry.count == 1 and len(entry.sources) < 1:
            continue
        stats.append(
            CandidateStats(
                kind="story",
                key=entry.display,
                count=entry.count,
                languages=tuple(sorted(entry.languages)),
                avg_tone=round(entry.tone_sum / entry.tone_n, 3) if entry.tone_n else None,
                source_spread=len(entry.sources),
                pillar=_story_pillar(batch, entry.support),
                support=frozenset(entry.support),
                examples=tuple(entry.examples),
            )
        )
    # Prefer multi-outlet, then eventful, then longer concrete labels.
    stats.sort(
        key=lambda s: (
            s.count,
            s.source_spread,
            quality.get(s.key.casefold(), 0),
            len(s.key.split()),
        ),
        reverse=True,
    )
    return stats


def extract_event_candidates(
    records: Iterable[GkgRecord], *, min_count: int = 2
) -> list[CandidateStats]:
    """Actor × action co-occurrence events (granular than lone theme codes)."""
    batch = list(records)
    acc: dict[str, _Acc] = {}
    for index, record in enumerate(batch):
        actors = _actors(record)
        actions = _actions(record)
        if not actors or not actions:
            continue
        # Prefer pairs of actors when available (more specific than one name alone).
        actor_keys = _actor_keys(actors)
        for actor_key in actor_keys:
            if is_sports_text(actor_key):
                continue
            for action in actions:
                action_h = _humanize_theme(action)
                if _is_weak_event(actor_key, action_h):
                    continue
                display = f"{actor_key} :: {action_h}"
                ck = display.casefold()
                entry = acc.setdefault(ck, _Acc())
                entry.count += 1
                entry.support.add(index)
                entry.languages.add(record.language)
                if record.source_name:
                    entry.sources.add(record.source_name)
                if record.url and len(entry.examples) < _MAX_EXAMPLES and record.url not in entry.examples:
                    entry.examples.append(record.url)
                if record.tone is not None:
                    entry.tone_sum += record.tone
                    entry.tone_n += 1
                if not entry.display:
                    entry.display = display
                if not entry.theme:
                    entry.theme = action

    stats: list[CandidateStats] = []
    for entry in acc.values():
        if entry.count < min_count:
            continue
        stats.append(
            CandidateStats(
                kind="event",
                key=entry.display or "event",
                count=entry.count,
                languages=tuple(sorted(entry.languages)),
                avg_tone=round(entry.tone_sum / entry.tone_n, 3) if entry.tone_n else None,
                source_spread=len(entry.sources),
                pillar=pillar_for_theme(entry.theme) if entry.theme else None,
                support=frozenset(entry.support),
                examples=tuple(entry.examples),
            )
        )
    stats.sort(key=lambda s: s.count, reverse=True)
    return stats


def url_slug_label(url: str) -> str | None:
    """Best-effort headline from a news URL path (GKG has no title field)."""
    if not url:
        return None
    try:
        path = urlparse(url).path or ""
    except ValueError:
        return None
    parts = [p for p in path.split("/") if p]
    # Prefer the longest hyphenated segment (typical CMS slug).
    candidates: list[str] = []
    for part in reversed(parts):
        raw = part
        # strip extension
        if "." in raw and not raw.startswith("."):
            raw = raw.rsplit(".", 1)[0]
        if _HEXISH.match(raw) or _DATEISH.match(raw) or _SLUG_NOISE.match(raw):
            continue
        if "-" in raw or "_" in raw:
            tokens = [t for t in re.split(r"[-_]+", raw) if t and not t.isdigit()]
            if _MIN_SLUG_TOKENS <= len(tokens) <= _MAX_SLUG_TOKENS:
                candidates.append(" ".join(tokens))
        elif len(raw) >= 24 and raw.isalpha():
            candidates.append(raw)
    if not candidates:
        return None
    # Longest informative slug
    label = max(candidates, key=len)
    label = re.sub(r"\s+", " ", label).strip().lower()
    if len(label.split()) < _MIN_SLUG_TOKENS:
        return None
    return label


def _is_weak_event(actor_key: str, action_h: str) -> bool:
    """True for standing-theater pairs (US/Trump × war/terror), not discrete moves.

    Keep: multi-actor pairs, or a non-mega actor with a multi-word specific action.
    Drop: mega/single-token actors with bucket actions (armedconflict, terror, …).
    """
    action = action_h.casefold().strip()
    actor = actor_key.casefold().strip()
    weak_action = any(tok in action for tok in _WEAK_ACTION_TOKENS)
    if " + " in actor_key:
        # Pairs with only the weakest buckets are still usually noise.
        return weak_action and any(
            tok in action for tok in ("armedconflict", "military", "war", "kill", "terror")
        )
    if actor in _MEGA_ACTORS or len(actor.split()) <= 1:
        return True  # never promote "united states :: X" alone
    if weak_action and len(action.split()) < 3:
        return True
    return False


def _is_junk_story(label: str) -> bool:
    blob = label.casefold()
    return any(j in blob for j in _STORY_JUNK)


def is_broad_theme(theme: str) -> bool:
    """Standing/mega GKG themes that should not win as discovery objects."""
    t = theme.upper()
    if t.startswith(_BROAD_ACTION_DENY):
        return True
    # Short mega codes with no specificity
    broad_exact = {
        "ECON_STOCKMARKET", "ECON_CURRENCIES", "ECON_INFLATION", "ECON_EMERGINGECON",
        "ENV_NATURALGAS", "ENV_OIL", "ENV_BIOFUEL", "GENERAL_GOVERNMENT",
        "GENERAL_HEALTH", "POPULATION_DENSITY", "UNREST_CHECKPOINT", "SEPARATISTS",
        "SEIGE", "TAX_FNCACT", "MANMADE_DISASTER_POWER_OUTAGES",
    }
    if t in broad_exact:
        return True
    # Taxonomy noise (animals as codes, etc.) without a story wrapper
    if t.startswith("TAX_WORLDMAMMALS") or t.startswith("TAX_WORLDINSECTS"):
        return True
    if t.startswith("TAX_DISEASE_") and t.count("_") <= 2:
        return True
    return False


def _actors(record: GkgRecord) -> list[str]:
    out: list[str] = []
    for p in record.persons:
        if is_noise_entity(p) or is_sports_text(p):
            continue
        out.append(p.strip())
        if len(out) >= _MAX_ACTORS_PER_RECORD:
            return out
    for o in record.organizations:
        if is_noise_entity(o) or is_sports_text(o):
            continue
        out.append(o.strip())
        if len(out) >= _MAX_ACTORS_PER_RECORD:
            break
    return out


def _actions(record: GkgRecord) -> list[str]:
    out: list[str] = []
    for t in record.themes:
        if is_boilerplate_theme(t) or is_broad_theme(t):
            continue
        up = t.upper()
        if any(m in up for m in _ACTION_MARKERS):
            out.append(t)
        if len(out) >= _MAX_ACTIONS_PER_RECORD:
            break
    return out


def _actor_keys(actors: list[str]) -> list[str]:
    """Single actors plus one pair (most specific available)."""
    keys = [a for a in actors[:2]]
    if len(actors) >= 2:
        pair = " + ".join(sorted(actors[:2], key=str.casefold))
        keys.insert(0, pair)
    return keys


def _humanize_theme(code: str) -> str:
    parts = code.split("_")
    prefixes = {
        "WB", "TAX", "ECON", "EPU", "ENV", "GOV", "MANMADE", "NATURAL",
        "CRISISLEX", "SOC", "UNGP", "WTO", "GENERAL", "POLICY",
    }
    while parts and (parts[0] in prefixes or parts[0].isdigit()):
        parts.pop(0)
    return " ".join(parts).lower() if parts else code.lower()


def _eventfulness(record: GkgRecord, label: str) -> int:
    """0..n rough score — action themes, actors, kinetic words in the slug."""
    score = 0
    if _actions(record):
        score += 2
    if _actors(record):
        score += 2
    blob = label.casefold()
    for w in (
        "strike", "struck", "bomb", "missile", "sanction", "indict", "ceasefire",
        "invade", "attack", "arrest", "blockade", "expel", "default", "launch",
        "discover", "breakthrough", "collapse", "halt", "ban", "ruling", "war",
        "drone", "refinery", "tanker", "hostage", "nuclear", "talks",
    ):
        if w in blob:
            score += 1
    return score


def _story_pillar(records: list[GkgRecord], support: set[int]) -> str | None:
    """Best-effort pillar from themes on supporting records."""
    # Avoid scanning all records if support is large — sample a few.
    sample = list(support)[:5]
    for idx in sample:
        if idx < 0 or idx >= len(records):
            continue
        for t in records[idx].themes:
            p = pillar_for_theme(t)
            if p:
                return p
    return None
