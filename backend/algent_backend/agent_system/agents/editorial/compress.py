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

from .length import count_words, paragraphs_for, planned_band

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
    return planned_band(treatment or {})


def _cut_task(current_words: int, low: int, high: int, *, again: bool) -> str:
    """The size of the cut in units a model can execute. "Cut to under 1,500" got 2,305 → 1,834
    over two passes: it shaves words. Told the share and the paragraphs to lose, it removes them."""
    goal = (low + high) // 2 if low else high
    remove = max(0, current_words - goal)
    share = round(100 * remove / max(1, current_words))
    return (f"This draft is {current_words} words. Its planned length is {low}-{high} words. "
            f"Remove about {remove} words — {share}% of it, the length of roughly "
            f"{paragraphs_for(remove)} whole paragraphs. Trimming a word here and there will not "
            "get there: whole sentences and paragraphs go."
            + (" Your previous cut was measured, not estimated — it is still over." if again else ""))


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

    from algent_backend.agent_system.prompting import UNIVERSAL_AGENT_BASE, compose_system_prompt

    # Role only. With the whole writing doctrine composed in, the model's reasoning over it ran
    # past the output ceiling and the reply was cut off mid-object — the first live cut
    # returned nothing. Cutting has its own short rules; it does not need the essay.
    prompt = compose_system_prompt(UNIVERSAL_AGENT_BASE, _ROLE)
    current, current_words, note = body, words, ""
    # Two passes at most. The first live cut reported "~1,390 words" and delivered 1,671: the
    # model cannot count its output either. The second pass is shown the real number.
    for attempt in range(2):
        task = (_cut_task(current_words, low, high, again=bool(attempt))
                + f"\n\nTITLE: {draft.get('title') or ''}\n\n{current}")
        try:
            model = context.model_resolver.resolve(model_spec).client.with_structured_output(Compressed)
            out = model.invoke([SystemMessage(content=prompt), HumanMessage(content=task)], config=config)
        except Exception as exc:  # noqa: BLE001 — the best cut so far (or the uncut draft) goes on
            record["reason"] = f"compressor failed: {type(exc).__name__}"
            break
        if not isinstance(out, Compressed) or not out.body.strip():
            record["reason"] = "compressor returned nothing"
            break
        new_words = count_words(out.body)
        if new_words >= current_words:
            record["reason"] = "not shorter"
            break
        if new_words < min_words:
            record["reason"] = "hollow cut discarded"
            break
        current, current_words, note = out.body.strip(), new_words, out.cut_note[:300]
        record["passes"] = attempt + 1
        if current_words <= high:
            break

    if current_words >= words:
        return draft, {**record, "new_words": current_words}
    return {**draft, "body": current}, {
        **record, "applied": True, "new_words": current_words, "cut_note": note}
