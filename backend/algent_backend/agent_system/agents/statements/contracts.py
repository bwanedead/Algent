"""
Contracts for the statements ledger: who said what, about whom, collected from primary transcripts.

``Transcript`` is the raw record we keep internally (never republished); ``Statement`` is the
extracted, linkable unit the desk and its writers consume. ``Extracted*`` is the model-facing shape:
the model proposes statements, and the harness stamps identity, source and provenance mechanically
(see ``extract.py``), so the model can never forge where a statement came from.
"""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, Field

VenueKind = Literal["speech", "press_conference", "interview", "statement", "readout", "post", "other"]
Signal = Literal["threat", "warning", "red_line", "commitment", "offer", "demand", "reassurance",
                 "accusation", "denial", "policy_announcement", "tone_shift", "other"]
SourceKind = Literal["primary", "secondary"]

QUOTE_WORD_LIMIT = 60


class Transcript(BaseModel):
    """A collected primary text (transcript, press release, readout). Kept internally for extraction."""

    id: str
    feed: str
    url: str
    title: str
    published: str = ""             # ISO timestamp as the source gave it
    text: str
    fetched_at: str
    language: str = "en"


class ExtractedStatement(BaseModel):
    """One statement as the model proposes it. Identity and provenance are added by the harness."""

    speaker: str = Field(description="Who said it: a person's full name, or the institution when no individual is named.")
    role: str = Field(default="", description="Their office or title as of the statement, e.g. 'President of Russia'.")
    affiliation: str = Field(default="", description="Country or organisation they speak for, e.g. 'Russia', 'NATO'.")
    date: str = Field(default="", description="Date the statement was made, ISO YYYY-MM-DD, when the text says; else empty.")
    venue_kind: VenueKind = "other"
    quote: str = Field(default="", description="EXACT words copied from the text, at most 60 words; only when the wording itself matters.")
    paraphrase: str = Field(default="", description="A faithful, neutral paraphrase of what was said; always give one unless the quote alone is the statement.")
    about: list[str] = Field(default_factory=list, description="The actors or targets it concerns, e.g. ['NATO', 'EU', 'Ukraine'].")
    topics: list[str] = Field(default_factory=list, description="Short topic keywords, e.g. ['sanctions', 'troops in Ukraine'].")
    signal: Signal = "other"
    stance: int = Field(default=0, description="Stance toward `about`: -2 hostile, -1 critical, 0 neutral, +1 constructive, +2 conciliatory.")
    significance: str = Field(default="", description="One line: why an analyst would care.")


class ExtractionPlan(BaseModel):
    statements: list[ExtractedStatement] = Field(default_factory=list)


class Statement(BaseModel):
    """A validated statement on the record, linked to the transcript it came from."""

    id: str
    speaker: str
    role: str = ""
    affiliation: str = ""
    date: str
    venue_kind: VenueKind = "other"
    quote: str = ""
    paraphrase: str = ""
    about: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    signal: Signal = "other"
    stance: int = 0
    significance: str = ""
    source_url: str
    source_kind: SourceKind = "primary"
    transcript_id: str


def statement_id(source_url: str, speaker: str, text: str) -> str:
    """Stable across reruns: the same speaker saying the same thing at the same URL is one statement."""
    basis = "\n".join(" ".join(part.casefold().split()) for part in (source_url, speaker, text))
    return "st_" + hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]
