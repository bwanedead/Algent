"""Standing beats the insight lane may chart. Closed on purpose — a flywheel needs repetition."""

from __future__ import annotations

from typing import Any

BEATS: tuple[dict[str, Any], ...] = (
    {
        "id": "ai_power",
        "label": "AI and power",
        "hint": (
            "Utility-scale MW/GW for data centers and AI campuses, private generation, "
            "grid interconnect queues, EIA electricity, IEA, company GW announcements "
            "compared to a city or a nuclear plant a stranger already knows."
        ),
    },
    {
        "id": "chips",
        "label": "chips and capex",
        "hint": (
            "Foundry and GPU-maker capex, TSMC/Samsung/Intel spend, CHIPS Act awards, "
            "public shipment or capacity figures — concentration and trajectory, not a product launch."
        ),
    },
)


def render_beats() -> str:
    lines = []
    for b in BEATS:
        lines.append(f"- {b['id']} ({b['label']}): {b['hint']}")
    return "\n".join(lines)
