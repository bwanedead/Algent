"""
Radar contracts — the light lane from a t0 pool item to a short X post.

Deliberately NOT the editorial rail in miniature. There is no profile, no treatment, no
gauntlet: a radar post says one true thing about something that just happened and stops. The
whole point is that most of what a newsroom notices does not merit an article and is still
worth saying.

A sweep SELECTS candidates from the pool. A search pass then looks each one up, and either
writes the post or drops it. The search is what makes the lane worth running: a wire line
alone is a headline flip, and those carry almost no information.

Radar and editorial are INDEPENDENT and unaware of each other. The same t0 item may be posted
here and also promoted to a full article, or either, or neither. Coupling them would mean one
lane's judgement silently vetoing the other's, and the failure mode is the same in both
directions: a story worth an article going unmentioned for a day because it was already
"handled", or a radar post suppressed because an article might happen later.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

#: Legacy labels the harness used to stamp on every post. Radar is the internal lane name;
#: the tweet is just the news. ``stamp`` peels these so queued rows and model leakage do not
#: ship a header, and ``body_key`` still matches a sentence we already posted with the label.
_PREFIXES = ("Radar:", "Ohmega Radar:")


def stamp(text: str) -> str:
    """The bytes we send: whitespace-normalized news, no lane label."""
    body = " ".join((text or "").split()).strip()
    peeled = True
    while peeled and body:
        peeled = False
        for variant in _PREFIXES:
            if body.lower().startswith(variant.lower()):
                body = body[len(variant):].lstrip()
                peeled = True
                break
    return body


def body_key(text: str) -> str:
    """Identity of the tweet we actually send, independent of which wire it came from.

    Source keys differ across rewrites of the same event; X duplicates on the sentence.
    Peeling a leftover ``Radar:`` means a queued row from the labeled era and a new unlabeled
    post compare equal, so we do not say the same thing twice just because the header died.
    """
    return " ".join(stamp(text).casefold().split())


class RadarPost(BaseModel):
    """One post: what happened, and the clause that makes it mean something.

    There is deliberately NO urgency or liveness field. Judging "is this happening right now"
    from a pool line is fragile in the direction that costs most — the model cannot see how old
    the pool is, and a first sweep confidently marked a two-day-old wildfire as live and would
    have jumped it to the front of the queue. A misjudgement that grants priority is worse than
    having no priority at all, and the information reads the same either way: the post says what
    happened, and the reader can tell how fresh that is without being told.
    """

    #: The t0 item id this came from — the dedup identity across sweeps.
    source_key: str
    #: The post as it will appear. Empty on a sweep candidate — the search pass writes it.
    #: A radar post usually links nowhere, so it IS the claim rather than a pointer.
    text: str = ""
    #: Why this one was worth saying at all, for the operator's review — never posted.
    rationale: str = ""


class RadarSweep(BaseModel):
    """What one pass over a t0 pool judged worth posting. Empty is a normal outcome."""

    posts: list[RadarPost] = Field(default_factory=list)
    considered: int = 0
    note: str = ""
    generated_at: str = ""
    generator: str = ""
    model: str = ""
