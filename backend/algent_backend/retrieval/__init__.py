"""
Retrieval over the desk's own corpus: given a question, find the daily sections, statements, sanctions events, calendar items, geoledger
status events and profile claims that bear on it.

    flags.py     the windows, sizes and the embeddings switch (OFF by default)
    docs.py      loaders: every source becomes ``Doc`` rows with a citable id (best-effort; a missing store is simply absent)
    lexical.py   BM25 (in-process, no dependency): the default and always-available ranker
    embed.py     the OPTIONAL dense ranker (EmbeddingGemma), import-guarded and cached on disk; absent unless switched on AND installed
    search.py    ``Index``: build once per run, ``search(query, k)`` -> ``Hit`` rows; lexical, or lexical+dense fused when embeddings are on

Consumers (the markets forecaster and trader today) ask for hits; they never see how they were ranked. The module knows nothing about prices.
Docs: ``docs/architecture/markets-track-record.md`` (retrieval section).
"""
