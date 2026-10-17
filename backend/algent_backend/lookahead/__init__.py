"""
Lookahead — the forward-looking calendar: dated upcoming things (elections, central-bank decisions, summits, UN Security Council
meetings, OPEC+ meetings, deadlines our own daily reports mention) from free official schedules and from the corpus.

Programmatic end to end (no model). The store is append-only revisions; sources are best-effort and isolated; the daily reads a
per-theater "COMING UP" block from here (``desk``). See ``docs/architecture/sanctions-calendar.md``.
"""
