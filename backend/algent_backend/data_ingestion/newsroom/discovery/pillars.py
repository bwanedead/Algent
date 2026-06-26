"""
Pillars — stable, multilingual topic categories via GDELT theme-code prefixes.

A *pillar* is a broad standing area of coverage we always want a read on
(economy, politics, science, environment, ...), the way a monitoring desk keeps
permanent beats. We get them for free and language-independently by matching the
prefixes of GDELT's coded themes: ``ECON_*`` is economic on an English, Spanish,
or Arabic article alike, so no per-language lexicon is ever needed.

This is deliberately coarse and prefix-based. It is a routing hint for the
digest, not a classifier — a theme may map to more than one pillar, and many
themes map to none (that's fine; those feed the open-ended novelty lenses).
"""

from __future__ import annotations

# Ordered so the economy beat (the first one we care to monitor well) is richest.
# Each pillar lists theme-code prefixes; a theme belongs to the pillar if it
# starts with any of them. Prefixes use GDELT's GKG theme vocabulary.
_PILLAR_PREFIXES: dict[str, tuple[str, ...]] = {
    "economy": (
        "ECON_",
        "EPU_ECONOMY",
        "WB_",  # World Bank development/economic themes
        "BUS_",
        "MACROECONOMIC",
        "UNGP_CRIME_FINANCIAL",
    ),
    "politics": (
        "ELECTION",
        "DEMOCRACY",
        "GENERAL_GOVERNMENT",
        "GOV_",
        "LEGISLATION",
        "POLITICAL_TURMOIL",
        "CORRUPTION",
        "EPU_POLICY",
        "TAX_POLITICAL",
    ),
    "science": (
        "SCIENCE",
        "TECH_",
        "MEDICAL",
        "HEALTH_",
        "INNOVATION",
        "SPACE",
        "ENERGY_",
    ),
    "environment": (
        "ENV_",
        "CLIMATE",
        "NATURAL_DISASTER",
        "UNGP_FORESTS_RIVERS_OCEANS",
        "UNGP_CLEAN_ENERGY",
        "SELF_IDENTIFIED_ENVIRON",
    ),
}

# Iterated in a fixed order so pillar tagging is deterministic.
PILLARS: tuple[str, ...] = tuple(_PILLAR_PREFIXES)


def pillar_for_theme(theme: str) -> str | None:
    """Return the first pillar whose prefix matches ``theme``, or None."""
    for pillar, prefixes in _PILLAR_PREFIXES.items():
        if theme.startswith(prefixes):
            return pillar
    return None
