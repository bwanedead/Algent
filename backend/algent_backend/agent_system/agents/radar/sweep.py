"""The radar sweep: one t0 pool in, a handful of candidates out.

The sweep SELECTS. A later search pass writes the post or drops the lead. That split is the
whole design: a wire line cannot tell you whether specifics exist, which is what the search
finds out, so this pass is generous and cheap.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from algent_backend.agent_system.foundation import cost
from algent_backend.agent_system.foundation.models import ModelSpec, house_spec
from algent_backend.agent_system.foundation.models.resolver import ModelResolver

from .contracts import RadarSweep
from .prompts import SYSTEM_PROMPT

GENERATOR = "radar_sweep/1.0"
#: Cheap by design: one call over headlines, no tools, no research. The lane only earns its
#: place if it costs a fraction of an article.
DEFAULT_MODEL: ModelSpec = house_spec(reasoning_effort="low", temperature=0.4)
COST_CAP_USD = 0.20

#: A prompt-size bound, not a judgement. Set above a normal pool (~110) so nothing is
#: silently excluded from consideration: a cap below the pool size is a hidden editorial
#: decision made by list order rather than by merit.
_MAX_ITEMS = 200


def _render_items(pool: dict[str, Any]) -> str:
    lines = []
    for item in (pool.get("items") or [])[:_MAX_ITEMS]:
        if not isinstance(item, dict):
            continue
        pillars = "/".join(item.get("pillars") or []) or "-"
        label = str(item.get("label") or "").strip()
        if not label:
            continue
        lines.append(f"- id: {item.get('id')}\n  [{item.get('channel','?')}|{pillars}] {label}")
    return "\n".join(lines)


def sweep_pool(
    pool: dict[str, Any],
    *,
    model_spec: ModelSpec | None = None,
    already_posted: set[str] | None = None,
    resolver: ModelResolver | None = None,
) -> RadarSweep:
    """Judge a t0 pool and return candidates worth looking up. Empty is a normal outcome.

    Takes a resolver rather than a full run context: this lane uses no tools and writes no
    artifacts, so requiring the run machinery would be ceremony around a single model call.
    """
    from algent_backend.agent_system.foundation.models.budget_gate import gate_chat_model

    spec = model_spec or DEFAULT_MODEL
    rendered = _render_items(pool)
    if not rendered.strip():
        return RadarSweep(considered=0, note="empty pool")

    message = "\n".join([
        "# T0 POOL — pick the few worth looking up right now",
        "",
        "Each line is a raw discovery item. Most are not worth a post; say so by leaving them out.",
        "Return source_key (the item's id exactly) and a short rationale. Leave text empty.",
        "",
        rendered,
        "",
        "Return a RadarSweep.",
    ])

    model = gate_chat_model((resolver or ModelResolver()).resolve(spec).client)
    with cost.scoped(COST_CAP_USD, spec.model):
        result = model.with_structured_output(RadarSweep).invoke(
            [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=message)],
        )

    if not isinstance(result, RadarSweep):
        return RadarSweep(considered=len(pool.get("items") or []),
                          note="model returned no structured sweep")

    seen = already_posted or set()
    kept = []
    for post in result.posts:
        key = (post.source_key or "").strip()
        if not key or key in seen:
            continue
        post.source_key = key
        kept.append(post)
        seen.add(key)

    result.posts = kept
    result.considered = len(pool.get("items") or [])
    result.generated_at = datetime.now(UTC).isoformat()
    result.generator = GENERATOR
    result.model = spec.model
    return result
