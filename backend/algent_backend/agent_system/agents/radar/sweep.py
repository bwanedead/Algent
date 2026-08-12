"""The radar sweep: one t0 pool in, a few standalone posts out."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from algent_backend.agent_system.foundation import cost
from algent_backend.agent_system.foundation.models import ModelSpec, house_spec
from algent_backend.agent_system.foundation.models.resolver import ModelResolver
from algent_backend.publishing.x_client import LIMIT, billable_length

from .contracts import RadarSweep
from .prompts import SYSTEM_PROMPT

GENERATOR = "radar_sweep/1.0"
#: Cheap by design: one call over headlines, no tools, no research. The lane only earns its
#: place if it costs a fraction of an article.
DEFAULT_MODEL: ModelSpec = house_spec(reasoning_effort="low", temperature=0.4)
COST_CAP_USD = 0.20

#: How many pool items to show. The pool is already novelty-filtered and significance-ranked
#: upstream, so this is a prompt-size bound, not a judgement.
_MAX_ITEMS = 90

#: Applied by the harness, not written by the model, so it is identical on every post and cannot
#: drift into "RADAR!!" or get dropped.
#:
#: It earns its place by being a LABEL rather than a claim: it says what kind of post this is —
#: a short notice off the wire, not a piece we researched — which is honest framing and still
#: catches an eye in a feed. That is the opposite of "BREAKING:", which asserts an urgency the
#: item usually does not have and which the platform discounts anyway. The handle already
#: supplies the brand, so this stays one plain word.
RADAR_PREFIX = "Radar: "


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
    """Judge a t0 pool and return the posts worth making. Empty is a normal outcome.

    Takes a resolver rather than a full run context: this lane uses no tools and writes no
    artifacts, so requiring the run machinery would be ceremony around a single model call.
    """
    from algent_backend.agent_system.foundation.models.budget_gate import gate_chat_model

    spec = model_spec or DEFAULT_MODEL
    rendered = _render_items(pool)
    if not rendered.strip():
        return RadarSweep(considered=0, note="empty pool")

    message = "\n".join([
        "# T0 POOL — pick the few worth posting right now",
        "",
        "Each line is a raw discovery item. Most are not worth a post; say so by leaving them out.",
        "",
        rendered,
        "",
        "Return a RadarSweep. `source_key` must be the item's id exactly as given above.",
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
        text = (post.text or "").strip()
        # The harness enforces what the prompt asks for: a post that cannot be sent is not a
        # post, and an over-length one would fail at the API with a worse error much later.
        if not text or post.source_key in seen:
            continue
        # Tolerate a model that prefixed it anyway rather than shipping "Radar: Radar: ...".
        for variant in (RADAR_PREFIX, "Radar:", "RADAR:", "Ohmega Radar:"):
            if text.lower().startswith(variant.strip().lower()):
                text = text[len(variant.strip()):].lstrip()
                break
        text = RADAR_PREFIX + text
        if billable_length(text) > LIMIT:
            continue
        post.text = text
        kept.append(post)

    result.posts = kept
    result.considered = len(pool.get("items") or [])
    result.generated_at = datetime.now(UTC).isoformat()
    result.generator = GENERATOR
    result.model = spec.model
    return result
