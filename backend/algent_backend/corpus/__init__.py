"""
The corpus index: ONE queryable, rebuildable SQLite view over the whole record (docs/architecture/corpus-index.md).

The JSON stores stay the record. This package derives from them (never the other way round) a normalised, graph-shaped index: entities and the
typed relations between them, documents with their claims and sources, mentions, dated events and time series, every row stamped with the
product and store key it came from. Delete it and ``newsroom corpus build --full`` makes it again; that is what makes it safe.

    paths.py     where the file lives (registry store ``corpus_store``)
    schema.py    tables, FTS5 (LIKE fallback), read-only / writer connections
    sink.py      the one write path; adapters never touch SQL
    sources/     one adapter per registered product: reads the store through the product's own readers, offers units
    link.py      materialises entities from declarations and resolves names after everything is read (order-independent)
    build.py     incremental / --since / --full orchestration, watermarks and content hashes
    query/       the read-only API (entity, about, timeline, search, related, series, stats) and the slice retrieval uses

Consumers import ``Corpus`` (and ``available``) from here; nothing outside this package should open the database itself.
"""

from __future__ import annotations

from .build import build
from .paths import available, db_file, store_dir
from .query import Corpus, CorpusMissing

__all__ = ["Corpus", "CorpusMissing", "available", "build", "db_file", "store_dir"]
