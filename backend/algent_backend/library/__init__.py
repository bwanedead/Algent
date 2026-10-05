"""
The source library — Ohmega's own search index over the sources it trusts.

Research otherwise depends on outside engines' ranking and quotas. The library crawls a curated registry
(``sources``: feeds and news sitemaps of primary institutions, think tanks, wires and regional outlets),
stores the text in SQLite with an FTS5 index (``store``), and answers ``search`` ranked by relevance,
recency and primary-source preference. ``web_search`` consults it first. Internal use only: agents and the
site get links and short snippets, never republished full texts. Design: docs/architecture/library.md.
"""

