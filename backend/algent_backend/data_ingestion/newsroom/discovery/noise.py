"""
Noise filters — the things we deliberately exclude as non-signal.

One audited home for "this is structurally not news", so the retroflection
question ("did we over-filter into a shape we didn't want?") has a single file to
review. Two kinds, both observed on real GDELT batches (see ITERATION_LOG):

- **Boilerplate themes** — structural GKG theme tags (functional actors,
  ethnicity/language tags, the broad crisis lexicon) that get stamped on a huge
  fraction of articles, so by raw volume they top every list while telling us
  nothing about *what's happening*.
- **Noise entities** — media-attribution artifacts GDELT extracts as named
  entities: photo credits and wire-service bylines ("Getty Images / …", "Anadolu
  Agency", "Shutterstock"). They ride along on unrelated stories as junk.

Both are conservative and prefix/substring based — widen only on observed noise,
and record the change in the log so it stays reversible.
"""

from __future__ import annotations

# Structural GKG theme prefixes — the "stopwords" of the theme vocabulary.
_BOILERPLATE_THEME_PREFIXES: tuple[str, ...] = (
    "TAX_FNCACT",
    "TAX_ETHNICITY",
    "TAX_WORLDLANGUAGES",
    "TAX_RELIGION",
    "CRISISLEX_",
    "MEDIA_MSM",
    "MEDIA_SOCIAL",
    "LEADER",
    "USPEC_",
    "EPU_CATS_",
)

# Substrings that mark an "entity" as a photo credit / wire-service byline rather
# than a subject of the news. Matched case-insensitively anywhere in the name, so
# mangled extractions like "getty imagescredit" / "getty imagespascal…" are caught.
_ENTITY_NOISE_MARKERS: tuple[str, ...] = (
    "getty image",
    "associated press",
    "agence france",
    "anadolu agency",
    "shutterstock",
    "istockphoto",
    "istock",
    "alamy",
    "via getty",
    "via reuters",
)


def is_boilerplate_theme(theme: str) -> bool:
    """True for structural GKG tags that swamp volume without signalling a topic."""
    return theme.startswith(_BOILERPLATE_THEME_PREFIXES)


def is_noise_entity(name: str) -> bool:
    """True for media-attribution artifacts (photo credits / wire bylines)."""
    lowered = name.lower()
    return any(marker in lowered for marker in _ENTITY_NOISE_MARKERS)
