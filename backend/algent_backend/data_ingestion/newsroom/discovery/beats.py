"""
The beat registry — the addressable niches we want continuous coverage of.

A *beat* is a first-class, addressable discovery target: an id, human label,
tags, and a GDELT DOC query that fetches it. Today every beat is fulfilled the
same way (a targeted DOC query in the sweep); the point of making it a registry
is that fulfillment is swappable later — a beat spec can route to a targeted
query now and a dedicated agent at scale, without changing the rest of the system.
The registry is *the* place coverage grows: add a beat, the sweep covers it.

Two kinds:
- **pillar** beats — standing topical areas most news covers (the suite below).
  Economics / finance / geopolitics are the deliberate strength cluster.
- **country** beats — general current events scoped to a country, so following
  any one country stays a current source. Top ~30 now; widen the list later.

Queries are GDELT DOC syntax: ``theme:CODE``, quoted phrases, ``OR`` for
alternation, ``sourcecountry:Name`` to scope (see ``gdelt_doc``).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Beat:
    """One addressable discovery target."""

    id: str
    label: str
    kind: str  # "pillar" | "country"
    query: str
    pillar: str | None = None  # topical tag (None for plain country beats)
    country: str | None = None
    timespan: str = "24h"
    sort: str = "datedesc"


# Pillar query specs. Broad-but-bounded keyword/theme sets — tuned in the sweep
# iterations, kept here in one reviewable place. Overlap between pillars is fine:
# a story is multi-tagged, not bucketed (an AI chip story is both ai and tech).
_PILLAR_QUERIES: dict[str, str] = {
    # Named the labs and the release language. The old query listed OpenAI and nothing
    # else, so a frontier release from anyone but OpenAI could not match it — Anthropic
    # shipping Opus 5 reached us only as a Chinese-language item picked up by the China
    # query. A frontier model release is a story we should never have to be lucky to see.
    "ai": (
        '("artificial intelligence" OR "machine learning" OR "generative AI" '
        'OR "large language model" OR "frontier model" OR "neural network" OR chatbot '
        'OR OpenAI OR Anthropic OR Claude OR Gemini OR DeepMind OR Mistral '
        'OR Llama OR DeepSeek OR Qwen OR xAI OR Grok '
        'OR "model release" OR "model card" OR benchmark)'
    ),
    "technology": (
        "(technology OR software OR semiconductor OR cybersecurity OR \"tech company\" "
        "OR startup OR smartphone)"
    ),
    "economics": (
        "(economy OR economic OR GDP OR inflation OR recession OR \"central bank\" "
        "OR \"interest rates\" OR unemployment OR tariffs)"
    ),
    # Crypto is deliberately NOT in here. Bundling it into finance gave it a standing
    # allocation it hasn't earned, and dragged the ticker-mill roundups in with it
    # (see ``topic_filters._PROMO_MARKERS``). Genuinely large crypto news still reaches
    # discovery via GKG volume and the X band — it just isn't a question we ask every
    # cycle whether or not anything happened.
    "finance": (
        '("stock market" OR stocks OR bonds OR "federal reserve" '
        'OR "financial markets" OR earnings OR IPO)'
    ),
    "geopolitics": (
        '(geopolitics OR sanctions OR "foreign policy" OR diplomacy OR "trade war" '
        'OR alliance OR territorial OR treaty)'
    ),
    "politics": (
        '(election OR government OR parliament OR legislation OR "prime minister" '
        'OR president OR policy OR coalition)'
    ),
    "world_events": (
        "(crisis OR conflict OR war OR protest OR summit OR disaster OR ceasefire)"
    ),
    "science": (
        # Breakthroughs / new knowledge — not generic "study says" SEO.
        '(breakthrough OR discovery OR "peer-reviewed" OR "for the first time" '
        'OR archaeology OR paleontology OR physics OR biology OR genome OR quantum '
        'OR telescope OR fossil OR "Nature journal" OR "Science journal" OR CRISPR '
        'OR exoplanet OR "researchers found" OR "scientists discover")'
    ),
    "health": (
        "(health OR disease OR medical OR vaccine OR outbreak OR hospital OR \"public health\")"
    ),
    "energy": (
        '(energy OR "oil prices" OR "natural gas" OR renewable OR electricity '
        'OR nuclear OR OPEC)'
    ),
    # Gaming is a wanted beat, but the trade press is overwhelmingly release calendars,
    # so a broad platform-name query returns nine slots of marketing copy (observed:
    # four delays, a DLC drop, and two "can X save Xbox" columns in one sweep). Asking
    # for the *newsworthy* subclasses instead — money, labour, law, platform power,
    # things breaking — still surfaces a big launch when a big launch is genuinely the
    # story, because those carry the same business language.
    "gaming": (
        '("video game" OR gaming OR "game studio" OR "game developer") '
        'AND (layoffs OR closure OR acquisition OR lawsuit OR antitrust OR union '
        'OR strike OR regulation OR revenue OR earnings OR outage OR breach '
        'OR "class action" OR ruling OR investigation OR "player data" '
        'OR preservation OR "record sales" OR shutdown OR delisted)'
    ),
}

# Top news-producing / high-interest countries (GDELT uses the country *name*).
# Start broad-but-finite; widen as coverage grows.
_COUNTRIES: tuple[str, ...] = (
    "United States", "China", "United Kingdom", "India", "Japan", "Germany",
    "France", "Russia", "Brazil", "Canada", "Australia", "Italy", "Spain",
    "South Korea", "Mexico", "Indonesia", "Netherlands", "Turkey", "Saudi Arabia",
    "Israel", "Ukraine", "Poland", "Sweden", "Nigeria", "South Africa",
    "Argentina", "United Arab Emirates", "Singapore", "Egypt", "Switzerland",
)


def pillar_beats() -> list[Beat]:
    # Pillars sort by relevance (hybridrel), not recency: a broad keyword OR-query
    # with datedesc just returns the newest loosely-matching articles (noise);
    # relevance surfaces the articles actually about the pillar.
    return [
        Beat(
            id=f"pillar:{name}",
            label=name,
            kind="pillar",
            query=query,
            pillar=name,
            sort="hybridrel",
        )
        for name, query in _PILLAR_QUERIES.items()
    ]


def country_beats() -> list[Beat]:
    return [
        Beat(
            id=f"country:{name}",
            label=f"{name} — general",
            kind="country",
            query=f"sourcecountry:{name}",
            country=name,
        )
        for name in _COUNTRIES
    ]


def all_beats() -> list[Beat]:
    """The full registry: pillar beats first, then country beats."""
    return pillar_beats() + country_beats()
