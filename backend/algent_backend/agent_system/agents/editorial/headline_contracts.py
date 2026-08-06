"""
Headline contract — the truthful title + dek + cold-reader gist for a finished piece.

A value object (no id): the pipeline applies it onto the draft. The whole standard lives in
newsroom/headline-guidance.md — crisp wrapper for topic + angle; hedges live in the dek /
quick_take, not the title spine. ``quick_take`` is the first-screen gist layer for readers who
will not open the full body.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .draft import QuickTake


class Headline(BaseModel):
    title: str = ""       # crisp wrapper for topic + angle — no clickbait, no overstatement, no caveat spine
    standfirst: str = ""  # one dek sentence adding the load-bearing nuance/caveat
    note: str = ""        # optional: any honesty tension the writer wants to flag
    # Cold-reader gist — three one-sentence fields; rendered under the dek on the site.
    quick_take: QuickTake = Field(default_factory=QuickTake)
    # The concrete physical thing a hero illustration should show — "an orca surfacing in
    # coastal water", "a juvenile feathered tyrannosaur". Written here because this stage has
    # just read the whole piece. It is NOT the headline and must never contain a figure, an
    # institution, or the word chart: an image model given numbers draws numbers, and drawn
    # numbers read as data. See ``hero_image`` for why that is a hard line.
    image_subject: str = ""
    # A few words set over the hero image, thumbnail-style — the gist that makes someone
    # scrolling a feed stop. Written fresh, NOT the headline trimmed: a headline compressed
    # into an image reads as awkwardly as it sounds, because it was built to survive an
    # index page, not to be read in one glance beside a picture.
    image_hook: str = ""
