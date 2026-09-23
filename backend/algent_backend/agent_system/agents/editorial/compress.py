"""
The cut — bring an overlong first draft to the length its own plan set, before review.

Drafts land far past their target: 2,046 and 2,251 words against a ~1,100 digest and a 1,500
ceiling, in consecutive runs. The review stage then spent three laps trimming about ten per cent
each time — its role forbids dropping anything load-bearing, so it shaves rather than cuts — and
still shipped over the ceiling, three minutes and three rewrites later. A model cannot count
its own output while writing it, so asking the drafter harder did not fix it.

So this is one call with one job: here is the measured length, here is the plan's band, cut to
it. It runs only when the draft is over the band the planner itself chose (``read_minutes`` via
``length.word_band``) — the plan's number, not a new one — and the review that follows then
works on a piece of the right size. The body carries no citation markers (cited claims are
tracked on the draft), so cutting prose cannot break the citation audit already passed.

Advisory and bounded: one call, and the cut is kept only if it is shorter and not hollow.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from .length import count_words, digest_words, word_band

GENERATOR = "draft_compressor@v1"
DRAFT_COMPRESSED = "editorial_pipeline.draft_compressed"

_ROLE = """\
You are cutting a finished news article down to the length its editor planned. You are not
rewriting its argument, reframing it, or improving its style. You are making the same piece
shorter, and you have been told exactly how long it is and how long it should be.

CUT, IN THIS ORDER:
1. Repetition — a fact, figure or point stated more than once. Keep the best statement of it.
2. Member lists — six named items, dates or figures where a reader holds only the pattern.
   Replace the list with the pattern in one clause ("three main stretches of contested border").
3. Mechanism past what the reader needs — how the apparatus works in more detail than the
   significance requires.
4. Adjacent worlds — stretches that leave the story's own question for a neighbouring one.
   Keep one clause saying the connection exists.
5. Scaffolding — full institutional titles on second mention, repeated qualifiers, throat-clearing.

NEVER CUT:
- a side of the dispute, or a perspective the piece represents — shorten it, keep it;
- a hedge or limit that governs how far to trust a claim ("the company says", "not yet
  independently checked") — it stays in the sentence it qualifies;
- a heading, unless everything under it is being cut; keep the ones you keep word for word;
- the opening sentence's substance.
Never add a fact, a claim or a stronger word than the draft has.

Return the whole cut body. Count before you answer: come in under the target, not near it.
"""


class Compressed(BaseModel):
    body: str = ""
    cut_note: str = ""       # one line: what went (for the run record, not the reader)


def target_band(treatment: dict[str, Any] | None) -> tuple[int, int]:
    """The (low, high) words this piece was planned to land in."""
    t = treatment or {}
    minutes = int(t.get("read_minutes") or 0)
    if minutes <= 0:
        return 0, digest_words()
    return word_band(minutes, survey=str(t.get("shape") or "") == "survey")


def compress(
    context: Any, config: Any, draft: dict[str, Any], treatment: dict[str, Any] | None,
    *, model_spec: Any, min_words: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Cut ``draft`` to its planned band when it is over. Returns (draft, record). Never raises."""
    body = str(draft.get("body") or "")
    words = count_words(body)
    low, high = target_band(treatment)
    record: dict[str, Any] = {"prior_words": words, "target_high": high, "applied": False}
    if not body or words <= high:
        return draft, {**record, "reason": "within band"}

    from langchain_core.messages import HumanMessage, SystemMessage

    from algent_backend.agent_system.agents.newsroom import doctrine
    from algent_backend.agent_system.prompting import UNIVERSAL_AGENT_BASE, compose_system_prompt

    prompt = compose_system_prompt(UNIVERSAL_AGENT_BASE, doctrine("writing-ergonomics"), _ROLE)
    task = (f"This draft is {words} words. Its planned length is {low}-{high} words. Cut it to "
            f"under {high} words.\n\nTITLE: {draft.get('title') or ''}\n\n{body}")
    try:
        model = context.model_resolver.resolve(model_spec).client.with_structured_output(Compressed)
        out = model.invoke([SystemMessage(content=prompt), HumanMessage(content=task)], config=config)
    except Exception as exc:  # noqa: BLE001 — the uncut draft still goes to review
        return draft, {**record, "reason": f"compressor failed: {type(exc).__name__}"}
    if not isinstance(out, Compressed) or not out.body.strip():
        return draft, {**record, "reason": "compressor returned nothing"}

    new_words = count_words(out.body)
    if new_words >= words:
        return draft, {**record, "new_words": new_words, "reason": "not shorter"}
    if new_words < min_words:
        return draft, {**record, "new_words": new_words, "reason": "hollow cut discarded"}
    return {**draft, "body": out.body.strip()}, {
        **record, "applied": True, "new_words": new_words, "cut_note": out.cut_note[:300]}
