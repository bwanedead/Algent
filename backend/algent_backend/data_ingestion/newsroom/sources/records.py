"""
``GkgRecord`` — the parsed shape of one GDELT GKG row we care about.

The raw GKG file is 27 tab-separated columns of mostly-unused detail. This is
the slim, typed projection the digest layer actually reads: who/what/where as
coded entities, the document's tone, and the source language. Everything here
is a plain value object — no behaviour, no I/O.

GKG codes its themes language-independently (e.g. ``ECON_STOCKMARKET`` appears
on a Spanish or Arabic article just as on an English one), which is what makes
a single deterministic digest work across all 100+ languages without lexicons.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class GkgRecord:
    """One GKG document, projected to the fields the digest uses."""

    record_id: str
    url: str
    source_name: str
    # ISO-ish language code of the *source* document. "eng" when GDELT did not
    # translate it (English source); otherwise the original-language code GDELT
    # reports in its translation metadata (e.g. "fra", "spa", "zho").
    language: str
    themes: tuple[str, ...] = ()
    persons: tuple[str, ...] = ()
    organizations: tuple[str, ...] = ()
    # Average document tone in GDELT's range (~ -100 very negative .. +100 very
    # positive; in practice mostly within ±10). None when the field was absent.
    tone: float | None = None
    # Carried through but unused by v1 lenses; kept so richer lenses can grow
    # without re-parsing.
    extra: dict[str, str] = field(default_factory=dict)
