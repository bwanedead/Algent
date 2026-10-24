"""
Retrieval knobs (in-repo, no ``.env``). Windows say how far back each source is searched; they bound index size and RAM, not relevance.
"""

from __future__ import annotations

#: Dense (embedding) ranking. OFF: the system is fully functional on BM25 alone. Turning it on also needs ``sentence-transformers`` installed
#: (the maintainer's call, see docs/architecture/markets-track-record.md); if it is on but missing, retrieval logs nothing and stays lexical.
EMBEDDINGS_ENABLED = False
#: Which dense backend: "sentence-transformers" (default) or "fastembed" (ONNX; lighter RAM, model support depends on the fastembed release).
EMBED_BACKEND = "sentence-transformers"
EMBED_MODEL = "google/embeddinggemma-300m"
#: Texts are cut to this many characters before embedding (a section's gist is in its first lines; keeps the encode cost flat).
EMBED_MAX_CHARS = 1200

#: How far back each source is searched, in days (the daily is kept whole per day: one doc per theater section).
DAILY_DAYS = 60
STATEMENT_DAYS = 90
SANCTION_DAYS = 60
GEO_DAYS = 45
CONFLICT_DAYS = 30        # low-confidence (single-source machine-coded) events are left out of the index: they would crowd out better evidence
GNSS_DAYS = 21
CALENDAR_DAYS_BACK = 30
CALENDAR_DAYS_AHEAD = 150

#: Hits returned per query by default, and the most profile claims added on top of them.
DEFAULT_K = 8
CLAIMS_K = 3
#: A hit's text is cut to this many characters when shown.
HIT_CHARS = 700

#: BM25 constants (the usual defaults).
BM25_K1, BM25_B = 1.5, 0.75
#: Newer material ranks slightly higher: multiplier 1 - RECENCY_WEIGHT + RECENCY_WEIGHT * 0.5 ** (age_days / RECENCY_HALF_LIFE_DAYS). Undated or future-dated = 1.
RECENCY_WEIGHT = 0.3
RECENCY_HALF_LIFE_DAYS = 30.0
#: Reciprocal-rank-fusion constant when lexical and dense rankings are combined.
RRF_K = 60

#: Use the corpus index (``algent_backend/corpus``, built by ``newsroom corpus build``) as the document source and lexical ranker when one exists.
#: Absent, empty or unreadable: the in-process loaders and BM25 below run exactly as before.
USE_CORPUS_INDEX = True
