"""
Headline contract — the truthful title + dek for a finished piece.

A value object (no id): the pipeline applies it onto the draft. The whole standard lives in
newsroom/headline-guidance.md — convey the article's real meaning at the confidence its evidence
supports, no deception in either direction.
"""

from __future__ import annotations

from pydantic import BaseModel


class Headline(BaseModel):
    title: str = ""       # plain, specific, honest — conveys the piece, no clickbait/overstatement
    standfirst: str = ""  # one dek sentence adding the load-bearing nuance/caveat
    note: str = ""        # optional: any honesty tension the writer wants to flag
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
