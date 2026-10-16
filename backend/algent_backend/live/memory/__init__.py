"""
Live memory — the original-intelligence engine on top of the live feeds: what the sensors normally show, and when they do not.

    sampler.py     counts of ships / aircraft / fires per 1-degree cell, named area and the world, folded into hour values
    hours.py       the raw hourly detail on the server's disk (60 days), one small gzip file per hour and source
    baseline.py    learned normals by hour of the week, incremental and compact (robust.py: median + MAD)
    detect.py      score, screen out data artefacts (receiver gaps), follow sustained runs
    anomalies.py   the confirmed-run record, its plain sentence, the current picture and the site's table (migration 011)
    daily.py       completed days as ``live_mem_*`` instrument series
    desk.py        the OHMEGA LIVE ANOMALIES evidence block and the per-theater daily rollup record
    tick.py        the hourly pass that ties them together
    flags.py       every threshold, with its reason

Raw detail lives briefly on the server; condensed insight (daily rollups, anomalies) is what leaves it. Everything is derived by
Ohmega from public sensor feeds (provenance ``ohmega_derived``) and forward-only. Docs: ``docs/guides/worker-server.md`` (Live memory).
"""

from .sampler import Sampler, record_events, record_fires

__all__ = ["Sampler", "record_events", "record_fires"]
