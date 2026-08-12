"""
The radar check — does the post claim more than its source item does?

Radar has no research pass and no claim ledger, by design: it is the lane that exists because
most of what a newsroom notices does not merit either. But "no research" cannot mean "no
verification", and it did. A sweep took *"Baby was rescued from rubble after Colombia
earthquake"* and posted it as *"...following the earthquake that has left deaths rising"* — a
casualty claim nobody sourced, invented by the sentence wanting a fuller ending.

So the check here is not "is this true in the world" — radar cannot afford to find out — but
the question it CAN answer for free: **is every event-specific assertion in this post carried by
the item it came from?** The source line is the evidence, and anything the post adds beyond it
is the thing to catch.

THE DISTINCTION THAT MAKES THIS USABLE. Banning every addition would also delete what makes a
radar post worth reading, because the significance clause is almost always background the wire
line does not restate:

- *"Novorossiysk, Russia's main oil-export and naval hub"* — stable background. A reader needs
  it to know why the attack matters, it does not change with the event, and it is the kind of
  thing that is either settled or plainly wrong. ALLOWED.
- *"the earthquake that has left deaths rising"* — an event-specific claim: a casualty
  trajectory, true only of this event, unknowable from the line, and exactly the sort of detail
  a reader would take as reported fact. NOT ALLOWED.

Same rule the newsroom already draws between a primitive and a claim, applied to one sentence.

The remedy is a trim, never a research trip. A radar post is short enough that the honest fix
for an unsupported clause is to delete the clause.
"""

from __future__ import annotations

from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from algent_backend.agent_system.foundation import cost
from algent_backend.agent_system.foundation.models import ModelSpec, house_spec
from algent_backend.agent_system.foundation.models.resolver import ModelResolver
from algent_backend.agent_system.prompting import UNIVERSAL_AGENT_BASE, compose_system_prompt
from algent_backend.publishing.x_client import LIMIT, billable_length

#: Cheap and toolless: the whole batch in one call. The check must never cost more than the
#: lane it guards.
DEFAULT_MODEL: ModelSpec = house_spec(reasoning_effort="low", temperature=0.0)
COST_CAP_USD = 0.10

Verdict = Literal["keep", "trim", "drop"]


class RadarCheck(BaseModel):
    """One post, judged against the item it came from."""

    source_key: str
    verdict: Verdict = "keep"
    #: For ``trim``: the post with the unsupported parts removed. Must still read as a sentence,
    #: not a truncation. Ignored for keep/drop.
    text: str = ""
    #: What was unsupported, named specifically. "Vague" is not a reason; "asserts a casualty
    #: trajectory the item does not mention" is.
    reason: str = ""


class RadarCheckBatch(BaseModel):
    checks: list[RadarCheck] = Field(default_factory=list)


CHECK_ROLE = """\
You are the last look before a short post goes out from a newsroom account. Each one was written
from a single wire line. You decide whether it says more than that line supports.

You are NOT judging whether the post is true in the world, interesting, or well written. One
question only: **is every EVENT-SPECIFIC assertion carried by the source line?**

ALLOWED — stable background that orients the reader:
- what a place, body or company IS ("Novorossiysk, Russia's main oil-export and naval hub")
- durable, uncontested context that does not change with this event
This is what makes a post worth reading rather than a bare headline. Do not strip it.

NOT ALLOWED — event-specific claims the line does not make:
- casualty numbers, tolls, or trajectories ("deaths rising", "at least 20 killed")
- causes, motives or blame not stated in the line
- outcomes, magnitudes, timings or quantities not in the line
- characterisations of scale ("the largest since...") unless the line says so
A reader takes these as reported fact, and we did not report them.

VERDICTS
- `keep` — everything event-specific traces to the line.
- `trim` — it mostly holds, but something must go. Return `text` as the post rewritten WITHOUT
  the unsupported part, still reading as a natural sentence rather than a stump. Change nothing
  else: do not improve the prose, do not add.
- `drop` — what is unsupported is the point of the post, or so little is left that it says
  nothing. Dropping is cheap and normal; there will be another sweep.

Also drop a post whose subject is not really the news: a wire line about an earthquake becomes a
post about the earthquake, not about one rescue, unless the line itself is about the rescue.

And drop the wholesome miracle item outright — the baby pulled from rubble, the animal that found
its way home, the improbable act of kindness. Not because it is false, but because it is the
category we can least check and the one that costs most when wrong: these travel furthest, get
embellished at each retelling, and are rarely corrected. Be most suspicious of the item you most
want to be true.

DROP A REPEAT OF SOMETHING ALREADY POSTED. You are shown what recently went out. The same event
routinely arrives as several wire lines with different ids, so identity of source is not identity
of story — an Indonesia ferry fire went out once, and a second line about the same fire off Bali
was queued behind it. Judge by the EVENT, not the wording: same incident, same decision, same
release is a repeat, even when one version has better detail. If the queued one is clearly better
than what already went out, still drop it — we cannot unpost the first.

Name the specific problem in `reason`. Echo `source_key` exactly.
"""

SYSTEM_PROMPT = compose_system_prompt(UNIVERSAL_AGENT_BASE, CHECK_ROLE)


def check_posts(
    pairs: list[tuple[str, str, str]],
    *,
    recent: list[str] | None = None,
    model_spec: ModelSpec | None = None,
    resolver: ModelResolver | None = None,
) -> dict[str, RadarCheck]:
    """``[(source_key, post_text, source_label)]`` -> verdicts by source_key.

    Fails OPEN on an unusable response: a check that cannot run must not silently empty the
    queue, and the posts it guards were already written under the same doctrine.
    """
    from algent_backend.agent_system.foundation.models.budget_gate import gate_chat_model

    if not pairs:
        return {}
    spec = model_spec or DEFAULT_MODEL

    lines: list[str] = []
    if recent:
        lines += ["# ALREADY POSTED RECENTLY - do not repeat these events", ""]
        lines += [f"- {r}" for r in recent[-25:]]
        lines.append("")
    lines += ["# POSTS TO CHECK", ""]
    for key, text, label in pairs:
        lines += [f"- source_key: {key}",
                  f"  source line: {label}",
                  f"  post: {text}", ""]
    lines.append("Return a RadarCheckBatch with one check per source_key above.")

    model = gate_chat_model((resolver or ModelResolver()).resolve(spec).client)
    with cost.scoped(COST_CAP_USD, spec.model):
        result = model.with_structured_output(RadarCheckBatch).invoke(
            [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content="\n".join(lines))],
        )
    if not isinstance(result, RadarCheckBatch):
        return {}
    return {c.source_key: c for c in result.checks}


def apply_checks(
    posts: list[Any], checks: dict[str, RadarCheck],
) -> tuple[list[Any], list[dict[str, str]]]:
    """Apply verdicts to RadarPost objects. Returns (survivors, rejections).

    An unchecked post survives: see the fail-open note above. A trim that comes back empty or
    over-length is treated as a drop rather than shipped broken.
    """
    kept, rejected = [], []
    for post in posts:
        check = checks.get(post.source_key)
        if check is None or check.verdict == "keep":
            kept.append(post)
            continue
        if check.verdict == "trim":
            text = (check.text or "").strip()
            if text and billable_length(text) <= LIMIT:
                post.text = text
                kept.append(post)
                continue
        rejected.append({"source_key": post.source_key, "verdict": check.verdict,
                         "reason": check.reason, "was": post.text})
    return kept, rejected


# ── the queue review ──────────────────────────────────────────────────────────────────────────
#
# The per-post check runs at sweep time and sees one post against one wire line. That is the wrong
# vantage for two problems:
#
#   - DUPLICATION ACROSS SWEEPS. Two sweeps hours apart can each queue the same story from
#     different wire lines, and neither knew about the other.
#   - RECIRCULATION. Wires re-run a story days later. Without memory of what we already said,
#     it reads as a bot with no recollection of its own timeline.
#
# So the review looks at the WHOLE pending queue against everything we have already posted, and
# prunes. The queue file is the memory: posted rows are never deleted, which makes "did we say
# this already" answerable weeks later rather than only within one sweep.

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
- IT IS NO LONGER WORTH SAYING. A queue drains over hours, and some items expire in that time:
  a scheduled vote that has since happened, a "so far" count certain to be stale, a prediction
  whose date has passed.
- IT READS AS NONSENSE ON ITS OWN. Not merely dull — genuinely unclear, mangled, or missing the
  thing that makes it a statement.

Do NOT drop for being unimportant, dry, or similar in TOPIC. Two separate earthquakes are two
events. Two updates on one earthquake are one.

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

    lines: list[str] = []
    if published:
        lines += ["# ALREADY PUBLISHED", ""]
        lines += [f"- {t}" for t in published]
        lines.append("")
    lines += ["# PENDING QUEUE (in send order)", ""]
    for post in pending:
        lines.append(f"- post_id: {post.id}\n  {post.text}")
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
