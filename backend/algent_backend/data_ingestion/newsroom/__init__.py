"""
``newsroom`` — the news-domain data work inside ``data_ingestion``.

This is the first concrete domain built on the generic ingestion machinery: the
data feeding an autonomous news discovery → research → production pipeline.
Other domains would sit beside this one under ``data_ingestion``.

- ``sources``   — raw dataset fetchers + parsers (e.g. GDELT GKG batches).
- ``discovery`` — deterministic stats digests over those records, the pre-LLM
  signal that discovery agents read instead of raw firehoses.
"""
