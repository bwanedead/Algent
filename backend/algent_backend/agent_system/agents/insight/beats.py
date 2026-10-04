"""Coverage bias for insight warrant — a tie-break, not an inventory of allowed topics."""

from __future__ import annotations

from typing import Any

LENSES: tuple[dict[str, Any], ...] = (
    {
        "id": "energy",
        "label": "energy and power",
        "hint": "grids, GW/MW, fuels, interconnect queues, EIA/IEA/Ember — scale a stranger can hold.",
    },
    {
        "id": "ai_power",
        "label": "AI and power",
        "hint": "data-center load, private generation, campus GW vs a city or a nuclear plant.",
    },
    {
        "id": "chips",
        "label": "chips and capex",
        "hint": "foundry/GPU capex, capacity, CHIPS awards — concentration and trajectory.",
    },
    {
        "id": "finance",
        "label": "markets and finance",
        "hint": "rates, credit, listed-company spend, public filings. Not a ticker call.",
    },
    {
        "id": "economics",
        "label": "macroeconomics",
        "hint": "inflation, labor, debt, trade, fiscal stock vs a real-world series.",
    },
    {
        "id": "labor",
        "label": "work and wages",
        "hint": "employment, participation, strikes, real wages — BLS and peers.",
    },
    {
        "id": "geopolitics",
        "label": "geopolitics and security",
        "hint": "force, aid, arms, chokepoints — counts and shares, not a mood.",
    },
    {
        "id": "migration",
        "label": "migration and borders",
        "hint": "official crossings, asylum stocks, remittances. Named statistical agency.",
    },
    {
        "id": "public_health",
        "label": "public health",
        "hint": "outbreaks, vaccines, excess deaths — WHO/MoH sitreps, not a blog.",
    },
    {
        "id": "climate",
        "label": "climate and environment",
        "hint": "emissions, ice, disasters with a published tally — Copernicus, NOAA, EM-DAT.",
    },
    {
        "id": "science",
        "label": "science and space",
        "hint": "missions, papers, instruments only when a public number series exists.",
    },
    {
        "id": "mma",
        "label": "MMA / UFC",
        "hint": "Public fight records, rankings, purses or PPV when a named outlet published them.",
    },
)


def render_beats() -> str:
    return "\n".join(f"- {b['id']} ({b['label']}): {b['hint']}" for b in LENSES)
