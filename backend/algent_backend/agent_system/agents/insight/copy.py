"""Tweet body for an insight post — takeaway, then the source. No lane label."""

from __future__ import annotations

from algent_backend.agent_system.agents.insight.contracts import InsightSpec
from algent_backend.publishing.x_client import CARD, billable_length


def format_copy(spec: InsightSpec) -> str:
    takeaway = " ".join((spec.takeaway or "").split()).strip()
    source = " ".join((spec.source_name or "").split()).strip()
    url = (spec.source_url or "").strip()
    parts = [takeaway]
    if source and url:
        parts.append(f"\n{source} {url}")
    elif url:
        parts.append(f"\n{url}")
    elif source:
        parts.append(f"\n{source}")
    text = "\n".join(parts).strip()
    if billable_length(text) <= CARD:
        return text
    # Keep the takeaway; drop the source name before dropping the URL.
    shorter = takeaway if not url else f"{takeaway}\n{url}"
    return shorter if billable_length(shorter) <= CARD else takeaway[: CARD - 1]
