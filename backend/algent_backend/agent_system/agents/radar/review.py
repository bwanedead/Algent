"""
The radar queue review — the whole pending queue against everything already posted.

A sweep can only see its own candidates. Two problems live across sweeps:

- DUPLICATION. Two sweeps hours apart can each queue the same story from different wire
  lines, and neither knew about the other.
- RECIRCULATION. Wires re-run a story days later. Without memory of what we already said,
  it reads as a bot with no recollection of its own timeline.

The queue file is the memory: posted rows are never deleted, which makes "did we say this
already" answerable weeks later rather than only within one sweep.

This also runs before a backlog drains after a gap (laptop closed overnight). A post that
was worth saying at noon can be expired by midnight, and releasing it on resume would be
posting yesterday as though it were now.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from algent_backend.agent_system.foundation import cost
from algent_backend.agent_system.foundation.models import ModelSpec, house_spec
from algent_backend.agent_system.foundation.models.resolver import ModelResolver
from algent_backend.agent_system.prompting import UNIVERSAL_AGENT_BASE, compose_system_prompt

DEFAULT_MODEL: ModelSpec = house_spec(reasoning_effort="low", temperature=0.0)
COST_CAP_USD = 0.10

#: How far back the review looks for repeats. Long enough to catch a wire re-running a story,
#: short enough that the prompt stays small on a queue with months of history behind it.
HISTORY_DAYS = 14


class QueueVerdict(BaseModel):
    """One queued post the review wants gone."""

    post_id: str
    reason: str = ""


class QueueReview(BaseModel):
    drop: list[QueueVerdict] = Field(default_factory=list)
    note: str = ""


REVIEW_ROLE = """\
You are reviewing a newsroom account's PENDING post queue before any of it goes out. You also see
what the account has already published.

Drop a pending post when:
- IT REPEATS SOMETHING ALREADY PUBLISHED. Judge by the event, not the wording: same incident,
  same decision, same release. Wires re-run stories for days, so a post can be a repeat even
  when its wording is entirely fresh. Drop it even if it is better written than what went out —
  the first is public and cannot be unposted.
- IT REPEATS ANOTHER PENDING POST. Keep the one that says more; drop the other. Say which you
  kept.
- IT HAS EXPIRED. A queue drains over hours, and some items go stale in that time: a scheduled
  vote that has since happened, a "so far" count, a primary projection, a "today" that the
  queued-ago stamp says is now yesterday. You are shown how old each post is. After a long gap,
  be stricter on time-bound claims — not on whether the story was ever worth saying.
- IT READS AS NONSENSE ON ITS OWN. Not merely dull — genuinely unclear, mangled, or missing the
  thing that makes it a statement.

Do NOT drop for being dry, promotional-looking, or similar in TOPIC. Two separate earthquakes
are two events. Two updates on one earthquake are one. Newsworthiness was already judged when
the post was written.

Dropping nothing is a perfectly good review. Name the specific reason for each drop.
"""

REVIEW_PROMPT = compose_system_prompt(UNIVERSAL_AGENT_BASE, REVIEW_ROLE)


def review_queue(
    pending: list[Any],
    published: list[str],
    *,
    model_spec: ModelSpec | None = None,
    resolver: ModelResolver | None = None,
) -> QueueReview:
    """Judge the pending queue against what already went out. Fails OPEN."""
    from algent_backend.agent_system.foundation.models.budget_gate import gate_chat_model

    if not pending:
        return QueueReview(note="empty queue")
    spec = model_spec or DEFAULT_MODEL
    now = datetime.now(UTC)

    lines: list[str] = [f"TODAY: {now.date().isoformat()}", ""]
    if published:
        lines += ["# ALREADY PUBLISHED", ""]
        lines += [f"- {t}" for t in published]
        lines.append("")
    lines += ["# PENDING QUEUE (in send order)", ""]
    for post in pending:
        age = ""
        created = getattr(post, "created_at", "") or ""
        if created:
            try:
                hours = (now - datetime.fromisoformat(created)).total_seconds() / 3600.0
                age = f"  queued {hours:.1f}h ago"
            except ValueError:
                age = ""
        lines.append(f"- post_id: {post.id}{age}\n  {post.text}")
    lines += ["", "Return a QueueReview listing only the posts to drop."]

    model = gate_chat_model((resolver or ModelResolver()).resolve(spec).client)
    with cost.scoped(COST_CAP_USD, spec.model):
        result = model.with_structured_output(QueueReview).invoke(
            [SystemMessage(content=REVIEW_PROMPT), HumanMessage(content="\n".join(lines))],
        )
    if not isinstance(result, QueueReview):
        return QueueReview(note="review returned nothing usable")
    # Only ever act on ids we actually asked about.
    ids = {p.id for p in pending}
    result.drop = [d for d in result.drop if d.post_id in ids]
    return result
