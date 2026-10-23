"""
Corpus-index knobs (in-repo, no ``.env``). The index is derived and rebuildable, so none of these is precious.
"""

from __future__ import annotations

#: The index file inside the corpus store directory (``ALGENT_CORPUS_STORE``, default ``corpus_store``; ``ops/products/locations.py``).
DB_NAME = "corpus.db"
#: Bumped when the table layout changes. A mismatch makes an incremental build fall back to a full rebuild (nothing is migrated: the index is derived).
SCHEMA_VERSION = 1
#: Seconds a writer waits for a lock before giving up (a reader never blocks a writer in WAL mode).
BUSY_TIMEOUT_S = 30
#: Text kept per document/claim/event body in the index (the record keeps the whole thing); bounds the file size.
BODY_CHARS = 6000
#: ``VACUUM`` an incrementally built index when this share of its pages is free (a full rebuild writes a fresh, compact file anyway).
VACUUM_FREE_SHARE = 0.25
#: Search: most terms taken from a long query (retrieval passes whole paragraphs), and the default result count.
QUERY_TERMS_MAX = 40
DEFAULT_LIMIT = 20
#: Entity ranks when several sources declare the same entity: the lowest rank names it (a country registry beats a story's mention of one).
RANK_AUTHORITY = 0
RANK_DECLARED = 5
RANK_MENTIONED = 9
#: A speaker on the record is a person or an institution and the statement does not say which: declared at this rank with kind ``actor``, so a
#: typed declaration (a research profile's person, a country's leader) names it whenever one exists.
RANK_INFERRED = 10
