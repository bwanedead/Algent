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
