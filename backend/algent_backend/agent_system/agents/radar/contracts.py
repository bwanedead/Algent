"""
Radar contracts — the light lane from a t0 pool item straight to an X post.

Deliberately NOT the editorial rail in miniature. There is no profile, no treatment, no
gauntlet: a radar post says one true thing about something that just happened and stops. The
whole point is that most of what a newsroom notices does not merit an article and is still
worth saying.

Radar and editorial are INDEPENDENT and unaware of each other. The same t0 item may be posted
here and also promoted to a full article, or either, or neither. Coupling them would mean one
lane's judgement silently vetoing the other's, and the failure mode is the same in both
directions: a story worth an article going unmentioned for a day because it was already
"handled", or a radar post suppressed because an article might happen later.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

#: How much the value of this post decays with time — a release decision, not an importance one.
#:
#: - ``live``     happening now; being early is most of the value, and an hour's delay wastes it.
#: - ``today``    real news, no race. Worth saying today, not worth jumping the queue for.
#: - ``whenever`` durable. A finding or a number that reads the same tomorrow.
Urgency = Literal["live", "today", "whenever"]


class RadarPost(BaseModel):
    """One post: what happened, and the clause that makes it mean something."""

    #: The t0 item id this came from — the dedup identity across sweeps.
    source_key: str
    #: The post as it will appear. Written to stand alone: a radar post usually links nowhere,
    #: so it IS the claim rather than a pointer to where the claim is defended.
    text: str
    urgency: Urgency = "today"
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
