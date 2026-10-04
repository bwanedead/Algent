"""
Illustrations INSIDE the piece — one per thing the reader is being asked to picture.

The hero is orientation: one banner so the article does not open as a wall of text. It does
nothing for the body, and for a whole class of story the body is exactly where the pictures
belong. A tour of proposed megastructures shipped as 1,772 unbroken words with a single hero,
and the reader's verdict was that he did not want to start it — he had come to *see* a 2 km
pyramid in Tokyo Bay and a ribbon to orbit, and got prose about cost overruns.

So: when a piece asks the reader to hold a physical thing they have never seen, we draw it,
next to the passage that describes it.

Three rules the design follows
------------------------------
1. **Earned, not decorative.** A slot exists because a specific thing in the prose is hard to
   picture and worth picturing. Most articles get none — a policy dispute has nothing to draw,
   and pictures of nothing in particular are the stock-photo disease.
2. **Never evidence.** These go through the same subject guards as the hero (no data, no
   emblems, no real identifiable people, no documentary framing) and carry a label that says
   an artist imagined this from a description. For an unbuilt design that label is load-bearing:
   our picture is not the architect's drawing and must never be read as one.
3. **Placed by the prose, not by a counter.** Each slot names an anchor — a heading or an exact
   phrase it follows — so the picture lands where the thing is being described. A slot whose
   anchor is not in the body is dropped rather than parked somewhere arbitrary.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from algent_backend.agent_system.foundation import cost

from .hero_image import CONCEPT_LABEL, UnsafeImageSubject, check_subject
from .image_gen import estimated_usd as image_est
from .image_gen import generate_hero_image

GENERATOR = "figure_images@v1"
FIGURE_IMAGE = "editorial_pipeline.figure_image"

#: Registers a slot may ask for. ``concept`` draws an unbuilt design as an architectural
#: impression; ``editorial`` illustrates a thing that exists but that we have no photograph of.
#:
#: The editorial register was briefly removed after it drew a photoreal antenna farm beside the
#: article on China's real compound at Doraleh. The operator's ruling: real photos are preferred,
#: but a generated picture is better than none — AS LONG AS a reader knows at a glance it is
#: generated. That is the site's job, not a reason to draw nothing: every ``figure_*`` image gets
#: the AI signature (a cyan frame, a bright label, and a key at the top of the page).
REGISTERS = ("concept", "editorial")


class ImageSlot(BaseModel):
    """One picture the piece wants, and where it goes."""

    id: str = ""
    subject: str = ""          # the physical thing to draw, in a few words — no numbers, no charts
    setting: str = ""          # where it sits, when that is part of picturing it
    anchor: str = ""           # heading, or an exact phrase from the body, that the image follows
    alt: str = ""              # what a reader who cannot see it is told
    style: str = "concept"        # which register to draw in — see REGISTERS
    why: str = ""              # what the reader cannot picture without it
    photo_query: str = ""      # editorial only: the real thing's name, for a photo archive search


class ImagePlan(BaseModel):
    slots: list[ImageSlot] = Field(default_factory=list)
    none_because: str = ""     # why this piece has nothing worth drawing (empty plans are normal)


PLAN_ROLE = """\
You are choosing the illustrations that go INSIDE an article, beside the passages they belong to.

Ask one question of the finished prose: is the reader being asked to picture a physical thing
they have almost certainly never seen? A proposed tower in a bay, a ribbon running to orbit, a
floating neighbourhood, an antenna compound nobody outside the region has looked at. Those are
worth drawing, and a piece that describes several of them wants several.

For a thing or place that EXISTS, we first look for a real, freely licensed photograph of it,
and draw only when none fits. So a real place at the heart of the story — a strait, a dam, a
factory, a compound — is worth a slot even in a hard-news piece: a reader who has never seen it
gets to. Any picture that is drawn is shown framed and labelled as AI-generated, so draw only
what the prose describes, never invented specifics presented as the real site's layout.

Most articles still want few or none. A policy fight, an economic argument, a court ruling, with
no physical thing at its centre — there is nothing to show, and a picture of nothing in
particular (a generic handshake, a flag, a building's facade) is worse than no picture. Return an empty list
and say why. Do not pad, do not illustrate an abstraction, and never ask for a chart, a map, a
diagram or anything carrying data: those are built from evidence elsewhere in the newsroom, and
an image model asked for numbers invents them.

For each slot:
- `subject` — the physical thing, in at most 12 plain words, as you would describe it to someone
  who will draw it: "a vast stepped pyramid city rising from a bay". No proper nouns of companies
  or institutions, no figures, no percentages, no text to render.
- `setting` — where it sits, when that is part of seeing it ("at dusk, ships passing below").
- `anchor` — where the picture goes: the EXACT text of the heading it should follow, or an exact
  sentence fragment copied from the body. Copy it character for character; a slot whose anchor
  cannot be found in the piece is thrown away.
- `alt` — one sentence for a reader who cannot see the image, describing what is depicted.
- `style` — `concept` for something proposed or unbuilt (drawn as an architect's impression),
  `editorial` for something that exists and simply has not been shown.
- `why` — what the reader cannot picture without it.
- `photo_query` — `editorial` slots only: what a photo archive would file the real thing under,
  proper nouns welcome ("Strait of Hormuz", "Hoover Dam", "Port of Doraleh"). Plain names, no
  dates or adjectives. Leave empty for `concept`.

Order them as they appear in the piece, at most one per passage. Each image costs real money and
a page of pictures nobody needed is its own kind of noise, so the count follows the prose: as
many as there are things the reader genuinely needs to see, and no more.
"""


def _message(draft: dict[str, Any]) -> str:
    return "\n\n".join(x for x in (
        f"TITLE: {draft.get('title') or ''}",
        str(draft.get("body") or "").strip(),
        "TASK: choose the illustrations this piece wants, with an anchor copied exactly from the "
        "text above. None is a valid and common answer.",
    ) if x)


def plan_images(context: Any, config: Any, draft: dict[str, Any], *, model_spec: Any) -> ImagePlan:
    """Ask for the slots this piece wants. Never raises — no plan means no pictures."""
    from langchain_core.messages import HumanMessage, SystemMessage

    from algent_backend.agent_system.agents.newsroom import doctrine
    from algent_backend.agent_system.prompting import (
        UNIVERSAL_AGENT_BASE,
        compose_system_prompt,
    )

    body = str(draft.get("body") or "").strip()
    if not body:
        return ImagePlan(none_because="no prose")
    prompt = compose_system_prompt(UNIVERSAL_AGENT_BASE, doctrine("spirit"), PLAN_ROLE)
    model = context.model_resolver.resolve(model_spec).client.with_structured_output(ImagePlan)
    try:
        out = model.invoke(
            [SystemMessage(content=prompt), HumanMessage(content=_message(draft))], config=config,
        )
    except Exception as exc:  # noqa: BLE001 — illustrations never fail an article
        return ImagePlan(none_because=f"planner failed: {type(exc).__name__}: {str(exc)[:80]}")
    return out if isinstance(out, ImagePlan) else ImagePlan(none_because="planner returned nothing")


def usable(slot: ImageSlot, body: str) -> str:
    """Why this slot cannot be drawn or placed, or "" when it is fine."""
    if not slot.anchor.strip():
        return "no anchor"
    if _anchor_index(body, slot.anchor) is None:
        return "anchor not found in the body"
    reason = check_subject(slot.subject)
    return reason or ""


def make_figures(
    plan: ImagePlan,
    body: str,
    artifacts: Any,
    *,
    say: Any = None,
    generate: Any = None,
    essential: bool = False,
    find_photo: Any = None,
) -> list[dict[str, Any]]:
    """Fill each usable slot — a real photo when ``find_photo`` finds one, else a drawing.

    ``find_photo(slot, passage) -> (Candidate | None, bytes, note)`` is tried first for slots in
    the ``editorial`` register (things that exist). Concepts are never photographed: an unbuilt
    design has no photograph, and an architect's render is theirs, not a free file.

    Budget-aware in the ordinary way: a reservation per image, released when it fails. These
    are not essential — an article ships without them, unlike the hero — so a slim or stopped
    run simply produces no pictures.
    """
    note = say if callable(say) else (lambda _m: None)
    if artifacts is None or not plan.slots:
        return []

    fn = generate or generate_hero_image
    out: list[dict[str, Any]] = []
    for i, slot in enumerate(plan.slots, 1):
        problem = usable(slot, body)
        if problem:
            note(f"figure {i}: skipped — {problem}")
            continue
        if callable(find_photo) and slot.style == "editorial":
            photo = _real_photo(slot, body, artifacts, find_photo, note, i)
            if photo is not None:
                out.append(photo)
                continue
        est = image_est()
        # Essential for a survey: there the pictures are the point, and the soft-cap economy mode
        # once dropped two of a megaprojects tour's five. Still bounded by the article hard cap.
        res = cost.try_reserve(est, op="figure_image", essential=essential)
        if res is None and cost.is_active():
            note(f"figure {i}: skipped — budget ({cost.mode()})")
            continue
        register = slot.style if slot.style in REGISTERS else "concept"
        try:
            image = fn(slot.subject, setting=slot.setting, register=register)
        except UnsafeImageSubject as exc:
            cost.release(res)
            note(f"figure {i}: refused — {str(exc)[:90]}")
            continue
        except Exception as exc:  # noqa: BLE001 — one failed picture is not a failed article
            cost.release(res)
            note(f"figure {i}: failed — {type(exc).__name__}: {str(exc)[:80]}")
            continue
        cost.settle(res, float(getattr(image, "estimated_usd", est) or est))

        name = f"figure_{_safe(slot.id or str(i))}{image.suffix()}"
        try:
            artifacts.write_bytes(name, image.data, kind="image")
        except Exception as exc:  # noqa: BLE001
            note(f"figure {i}: not written — {str(exc)[:80]}")
            continue
        out.append({
            "artifact_name": name,
            "alt": (slot.alt or slot.subject).strip(),
            "anchor": slot.anchor,
            "label": getattr(image, "label", CONCEPT_LABEL),
            "subject": slot.subject,
            "register": register,
            "model": image.model,
            "estimated_usd": image.estimated_usd,
        })
        note(f"figure {i}: {name} ~${image.estimated_usd:.4f} — {slot.subject[:60]}")
    if out:
        try:
            artifacts.write_json("figure_images.json", {"figures": out})
        except Exception:  # noqa: BLE001 — the bytes are already safe
            pass
    return out


def _real_photo(slot: ImageSlot, body: str, artifacts: Any, find_photo: Any, note: Any,
                i: int) -> dict[str, Any] | None:
    """One slot's real photograph, written and recorded — or None, and the slot is drawn."""
    from .real_images import PHOTO_PREFIX, credit_line, suffix

    try:
        pick, data, why = find_photo(slot, _passage(body, slot.anchor))
    except Exception as exc:  # noqa: BLE001 — a failed search falls back to drawing
        pick, data, why = None, b"", f"{type(exc).__name__}"
    if pick is None or not data:
        note(f"figure {i}: no real photo — {why}")
        return None
    name = f"{PHOTO_PREFIX}{_safe(slot.id or str(i))}{suffix(pick)}"
    try:
        artifacts.write_bytes(name, data, kind="image")
    except Exception as exc:  # noqa: BLE001
        note(f"figure {i}: photo not written — {str(exc)[:80]}")
        return None
    note(f"figure {i}: {name} real photo — {pick.title[:60]} ({pick.license})")
    return {
        "artifact_name": name, "alt": (slot.alt or slot.subject).strip(), "anchor": slot.anchor,
        "kind": "photo", "credit": credit_line(pick), "source_url": pick.page_url,
        "license": pick.license, "author": pick.artist, "taken": pick.date,
        "subject": slot.subject, "estimated_usd": 0.0,
    }


def _passage(body: str, anchor: str) -> str:
    """The paragraph (or heading) an anchor sits in — what the photo must show."""
    end = _anchor_index(body, anchor)
    if end is None:
        return ""
    start = body.rfind("\n\n", 0, max(0, end - 1))
    block = body[start + 2 if start >= 0 else 0:end].strip()
    if block.startswith("#"):
        # Anchored to a heading: the thing is described in the paragraph under it.
        nxt = body.find("\n\n", end + 2)
        block += "\n\n" + body[end:nxt if nxt >= 0 else len(body)].strip()
    return block


def place(body: str, figures: list[dict[str, Any]]) -> str:
    """Put each image into the prose after its anchor, with its label underneath.

    Later anchors first, so inserting one does not move the offsets of the ones still to come.
    """
    if not body or not figures:
        return body
    located = []
    for fig in figures:
        at = _anchor_index(body, str(fig.get("anchor") or ""))
        if at is not None:
            located.append((at, fig))
    for at, fig in sorted(located, key=lambda pair: pair[0], reverse=True):
        # No label line here: the site recognises a generated picture by its ``figure_`` name
        # and gives it the page's AI signature — frame, bright label, and the key at the top.
        # A grey italic line from us as well was a second, weaker disclosure of the same fact.
        # Blank lines on both sides: an image followed by a single newline is the SAME markdown
        # paragraph as the text after it, and every illustrated piece shipped with the next
        # paragraph glued to its picture.
        block = f"\n\n![{_clean(str(fig.get('alt') or ''))}]({fig.get('artifact_name')})\n\n"
        if fig.get("credit"):
            # A real photo carries its credit on its own italic line — the site's caption style.
            block += f"{fig['credit']}\n\n"
        rest = body[at:].lstrip("\n")
        body = body[:at] + (block if rest else block.rstrip("\n") + "\n") + rest
    return body


def _anchor_index(body: str, anchor: str) -> int | None:
    """Offset of the end of the paragraph (or heading) the anchor sits in.

    An image belongs BETWEEN blocks, never spliced into the middle of a sentence, so the anchor
    only has to identify the passage — the picture then lands at the end of it.
    """
    text = (anchor or "").strip().lstrip("#").strip()
    if not text:
        return None
    at = body.find(text)
    if at < 0:
        # Whitespace in the prose is not always the whitespace the planner copied back.
        loose = re.escape(text).replace(r"\ ", r"\s+")
        match = re.search(loose, body)
        if match is None:
            return None
        at = match.start()
    end = body.find("\n\n", at)
    return len(body) if end < 0 else end


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).replace("]", ")").strip()


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "image"
