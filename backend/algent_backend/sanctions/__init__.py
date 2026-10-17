"""
Sanctions designations — a free, programmatic feed of who was put on (or taken off) the big three sanctions lists.

OFAC's SDN list, the UK Sanctions List and the EU consolidated financial sanctions list are downloaded, diffed
against the previous snapshot and turned into append-only designation / delisting events (no model anywhere).
See ``docs/architecture/sanctions-calendar.md``.
"""
